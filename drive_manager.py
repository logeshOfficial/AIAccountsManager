import os
from pathlib import Path
import time
from googleapiclient.errors import HttpError
import random
import time
from googleapiclient.discovery import build
import pandas as pd
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import streamlit as st
from app_logger import get_logger

logger = get_logger(__name__)

class DriveManager:
    def __init__(self, creds):
        try:
            self.service = build("drive", "v3", credentials=creds)
            
        except KeyError:
            st.error("Error ocured while loading Google Drive credentials on secrets. Please contact the administrator.")
            st.stop()
            
    def get_child_folder_id(self, service, folder_name, parent_id):
        query = (
            f"name='{folder_name}' and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"'{parent_id}' in parents and "
            f"trashed=false"
        )

        result = service.files().list(
            q=query,
            fields="files(id, name)"
        ).execute()

        if not result["files"]:
            raise ValueError("Folder not found")

        return result["files"][0]["id"]


    def drive_execute(self, request, retries=8):
        for i in range(retries):
            try:
                return request.execute()
            except HttpError as e:
                if e.resp.status in [403, 429, 500, 503]:
                    wait = (2 ** i) + random.random()
                    logger.warning(f"⏳ Drive retry in {wait:.2f}s")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("❌ Drive API failed after retries")

    def get_or_create_folder(self, folder_name, parent_id=None):
        """
        Returns folder ID. Creates folder if it doesn't exist.
        parent_id: Folder ID in which this folder should be created
        """
        query = (
            f"name='{folder_name}' and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"trashed=false"
        )

        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = self.drive_execute(self.service.files().list(q=query,
            spaces="drive",
            fields="files(id, name)"))

        if results["files"]:
            return results["files"][0]["id"]
    
        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }

        if parent_id:
            metadata["parents"] = [parent_id]

        folder = self.drive_execute(self.service.files().create(body=metadata, fields="id"))
        
        return folder["id"]

    def list_files_in_folder(self, folder_id):
        """
        List *all* files in a folder (handles Drive API pagination).
        Drive API commonly returns only the first ~100 items if you don't page.
        """
        all_files = []
        page_token = None

        while True:
            results = self.drive_execute(
                self.service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    spaces="drive",
                    pageSize=1000,
                    pageToken=page_token,
                    fields="nextPageToken, files(id, name, mimeType)",
                )
            )

            all_files.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        return all_files
    
    def move_files_drive(self, files, dest_dir, drive_dirs):
        dest_folder_id = drive_dirs[dest_dir]

        for f in files:
            try:
                new_name = f"{Path(f['name']).stem}_{int(time.time())}{Path(f['name']).suffix}"
                file = self.drive_execute(
                    self.service.files().get(
                        fileId=f["id"],
                        fields="parents"
                    )
                )
                self.drive_execute(
                    self.service.files().update(
                        fileId=f["id"],
                        addParents=dest_folder_id,
                        removeParents=",".join(file["parents"]),
                        body={"name": new_name}
                    )
                )

                logger.info(f"📁 Drive moved: {new_name}")
                
            except Exception as e:
                logger.error(f"❌ Failed to move {f['name']}: {e}")

    def download_drive_file(self, file_id, local_path):
        request = self.service.files().get_media(fileId=file_id)

        with open(local_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                
    def resolve_folder_id(self, folder_name, parent_id=None):
        query = (
            f"name='{folder_name}' and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"trashed=false"
        )

        if parent_id:
            query += f" and '{parent_id}' in parents"

        result = self.drive_execute(self.service.files().list(q=query,
            fields="files(id, name)"))

        files = result.get("files", [])
        if not files:
            raise ValueError(f"❌ Folder not found in Drive: {folder_name}")

        return files[0]["id"]

    def create_and_upload_excel(self, output_folder_id, year, months_data):
        """Creates an Excel report for the year and uploads/updates it on Drive."""
        import tempfile, shutil
        filename = f"invoices_{year}.xlsx"
        tmp_dir = tempfile.mkdtemp()
        local_path = os.path.join(tmp_dir, filename)

        try:
            with pd.ExcelWriter(local_path, engine="openpyxl", mode="w") as writer:
                sheets_written = False
                for month, invoices in months_data.items():
                    if invoices:
                        pd.DataFrame(invoices).to_excel(writer, sheet_name=month, index=False)
                        sheets_written = True
                if not sheets_written: return

            time.sleep(1)
            media = MediaFileUpload(local_path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resumable=True)
            
            # Check for existing
            existing = self.drive_execute(self.service.files().list(
                q=f"name='{filename}' and '{output_folder_id}' in parents and trashed=false",
                fields="files(id)"
            )).get("files", [])

            if existing:
                self.drive_execute(self.service.files().update(fileId=existing[0]["id"], media_body=media))
            else:
                self.drive_execute(self.service.files().create(
                    body={"name": filename, "parents": [output_folder_id], "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    media_body=media
                ))
            logger.info(f"✅ Excel report uploaded: {filename}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
