import os
import json
import pandas as pd
import plotly.express as px
import yagmail
from typing import Annotated, List, Dict, TypedDict, Union
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from app_logger import get_logger
import db
import streamlit as st

logger = get_logger(__name__)

# ==============================================================================
# 1. State Definition
# ==============================================================================

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    user_email: str
    invoices_df: pd.DataFrame
    generated_chart: Dict # JSON representation of Plotly chart
    generated_file: str # Path to created Excel file
    next_step: str # To guide the graph flow
    extracted_filters: Dict # Search criteria like vendor, year, or invoice #

# ==============================================================================
# 2. Tool Implementations
# ==============================================================================

def generate_chart_tool(data: pd.DataFrame, chart_type: str, title: str):
    """Generates a Plotly chart based on the data."""
    try:
        if chart_type == "bar":
            fig = px.bar(data, x="vendor_name", y="total_amount", title=title)
        elif chart_type == "pie":
            fig = px.pie(data, values="total_amount", names="vendor_name", title=title)
        elif chart_type == "line":
            fig = px.line(data, x="invoice_date", y="total_amount", title=title)
        else:
            return None
        
        return fig.to_json()
    except Exception as e:
        logger.error(f"Chart tool failed: {e}")
        return None

def generate_excel_tool(data: pd.DataFrame, filename: str, filters: Dict = None):
    """
    Generates an Excel report. 
    Smart Sheet Logic:
    - Multi-sheet: If target_year is provided and NO target_month/target_day is provided.
    - Single-sheet: Otherwise.
    """
    filepath = os.path.join(os.getcwd(), filename)
    filters = filters or {}
    target_year = filters.get("target_year")
    target_month = filters.get("target_month")
    target_day = filters.get("target_day")
    
    # Multi-sheet logic: Year requested but no specific month/day focusing
    if target_year and not target_month and not target_day and not data.empty:
        # 1. Ensure 'invoice_date' is datetime
        data = data.copy()
        data['invoice_date'] = pd.to_datetime(data['invoice_date'], errors='coerce')
        
        # 2. Filter for the specific year
        year_data = data[data['invoice_date'].dt.year.astype(str) == str(target_year)]
        
        if not year_data.empty:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # 3. Group by month and create sheets
                months = ["January", "February", "March", "April", "May", "June", 
                          "July", "August", "September", "October", "November", "December"]
                
                for i, month_name in enumerate(months, 1):
                    month_df = year_data[year_data['invoice_date'].dt.month == i]
                    if not month_df.empty:
                        # Clean date for display in Excel
                        display_df = month_df.copy()
                        display_df['invoice_date'] = display_df['invoice_date'].dt.strftime('%Y-%m-%d')
                        display_df.to_excel(writer, sheet_name=month_name, index=False)
                
                if writer.sheets:
                    return filepath

    # Default single sheet behavior (Month, Day, or just Vendor)
    data.to_excel(filepath, index=False)
    return filepath

def send_email_tool(to_email: str, subject: str, body: str, attachment_path: str = None):
    """Sends an email with an optional attachment."""
    try:
        smtp_user = st.secrets.get("smtp_user")
        smtp_pass = st.secrets.get("smtp_password")
        
        if not smtp_user or not smtp_pass:
            logger.warning("Email credentials missing in secrets.")
            return False
            
        yag = yagmail.SMTP(smtp_user, smtp_pass)
        yag.send(
            to=to_email,
            subject=subject,
            contents=body,
            attachments=attachment_path
        )
        return True
    except Exception as e:
        logger.error(f"Email tool failed: {e}")
        return False

def get_llm():
    """Returns the primary LLM (Groq for speed/fallback)."""
    api_key = st.secrets.get("groq_api_key")
    if api_key:
        return ChatGroq(api_key=api_key, model_name="llama-3.3-70b-versatile")
    return ChatOpenAI(model="gpt-4o-mini")

# ==============================================================================
# 3. Agent Nodes
# ==============================================================================

def analyst_node(state: AgentState):
    """Deeply analyzes query, extracts filters, and explains data."""
    user_query = state["messages"][-1].content
    logger.info(f"Analyst Node: Advanced Analysis for '{user_query}'")
    
    llm = get_llm()
    df = db.read_db(user_id=state["user_email"])
    
    prompt = f"""You are a Financial Analyst. Analyze this query: '{user_query}'
    Available nodes: 'designer' (for visuals), 'secretary' (for reports/emails), 'END'.
    Data available for vendors like: {df['vendor_name'].unique().tolist() if not df.empty else 'None'}
    
    Extract Search Filters if mentioned:
    - vendor_name: (partial or exact)
    - invoice_number: (string)
    - target_year: (4-digit year like '2025')
    - target_month: (month name or number 1-12)
    - target_day: (day of the month 1-31)
    - target_email: (email address to send reports to)
    
    Respond strictly in JSON:
    {{
      "next_node": "node_name",
      "filters": {{
        "vendor_name": null, 
        "invoice_number": null, 
        "target_year": null, 
        "target_month": null, 
        "target_day": null, 
        "target_email": null
      }}
    }}"""
    
    try:
        response = llm.invoke(prompt)
        clean_content = response.content.replace('```json', '').replace('```', '').strip()
        decision = json.loads(clean_content)
        
        next_node = decision.get("next_node", END)
        filters = decision.get("filters", {})
        
        if filters.get("vendor_name"):
            df = df[df['vendor_name'].str.contains(filters['vendor_name'], case=False, na=False)]
        if filters.get("invoice_number"):
            df = df[df['invoice_number'].astype(str).str.contains(str(filters['invoice_number']))]
            
        if not df.empty and (filters.get("target_year") or filters.get("target_month") or filters.get("target_day")):
            df['temp_date'] = pd.to_datetime(df['invoice_date'], errors='coerce')
            if filters.get("target_year"):
                df = df[df['temp_date'].dt.year.astype(str) == str(filters['target_year'])]
            if filters.get("target_month"):
                month = filters["target_month"]
                if isinstance(month, str) and not month.isdigit():
                    # Handle month names
                    try:
                        month_num = datetime.strptime(month, "%B").month
                    except:
                        try:
                            month_num = datetime.strptime(month, "%b").month
                        except:
                            month_num = None
                else:
                    month_num = int(month)
                
                if month_num:
                    df = df[df['temp_date'].dt.month == month_num]
                    
            if filters.get("target_day"):
                df = df[df['temp_date'].dt.day == int(filters['target_day'])]
            
            df = df.drop(columns=['temp_date'])
            
    except Exception as e:
        logger.warning(f"Analyst failed to extract filters: {e}")
        next_node = END
        filters = {}

    if not df.empty:
        summary = f"I found {len(df)} matching records. "
        if filters.get('target_year') and not (filters.get('target_month') or filters.get('target_day')):
            summary += f"Processing yearly overview for {filters['target_year']} (multi-sheet by month)."
        elif filters.get('target_month'):
            summary += f"Filtered for {filters['target_month']} {filters.get('target_year', '')}."
        elif filters.get('invoice_number') or len(df) == 1:
            inv = df.iloc[0]
            summary += f"Details: Invoice #{inv['invoice_number']} from {inv['vendor_name']} ({inv['invoice_date']}) for ${inv['total_amount']:.2f}."
    else:
        summary = "I couldn't find any invoices matching those specific details."
        
    return {
        "invoices_df": df, 
        "messages": [AIMessage(content=summary)], 
        "next_step": next_node,
        "extracted_filters": filters
    }

def designer_node(state: AgentState):
    """Smart chart generation on FILTERED data."""
    df = state["invoices_df"]
    if df.empty:
        return {"messages": [AIMessage(content="No data found to visualize.")], "next_step": END}
        
    user_query = state["messages"][0].content
    llm = get_llm()
    prompt = f"User asked: '{user_query}'. Which chart ('bar', 'pie', 'line') is best for {len(df)} rows? "
    prompt += 'Respond with JSON: {"chart_type": "type", "title": "title"}'
    
    try:
        response = llm.invoke(prompt)
        cfg = json.loads(response.content.replace('```json', '').replace('```', '').strip())
        chart_type = cfg.get("chart_type", "bar")
        title = cfg.get("title", f"Analysis: {state['extracted_filters'].get('vendor_name', 'Expenses')}")
    except:
        chart_type, title = "bar", "Expense Analysis"

    chart_json = generate_chart_tool(df, chart_type, title)
    return {
        "generated_chart": json.loads(chart_json) if chart_json else None, 
        "messages": [AIMessage(content=f"I've generated a {chart_type} for the selected data.")], 
        "next_step": END
    }

def secretary_node(state: AgentState):
    """Dynamic delivery to custom destination emails with multi-sheet support."""
    df = state["invoices_df"]
    user_query = state["messages"][0].content
    filters = state.get("extracted_filters", {})
    dest_email = filters.get("target_email") or state["user_email"]
    
    msg = ""
    file_path = None
    
    if any(k in user_query.lower() for k in ["excel", "report", "download"]):
        # Build a descriptive suffix
        time_parts = [str(filters.get(k)) for k in ["target_day", "target_month", "target_year"] if filters.get(k)]
        suffix = "_".join(time_parts) or filters.get("vendor_name") or "Report"
        
        file_path = generate_excel_tool(df, f"Invoices_{suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx", filters=filters)
        
        is_multi = filters.get("target_year") and not (filters.get("target_month") or filters.get("target_day"))
        msg += f"Excel report generated (multi-sheet by month for {filters['target_year']}). " if is_multi else "Excel report generated. "
        
    if "email" in user_query.lower():
        subject = f"Financial Report: {filters.get('target_year', filters.get('vendor_name', 'Export'))}"
        body = f"Attached is the requested financial analysis."
        success = send_email_tool(dest_email, subject, body, file_path)
        msg += f"Email sent to {dest_email}." if success else "Email delivery failed."
        
    return {"generated_file": file_path, "messages": [AIMessage(content=msg)], "next_step": END}

# ==============================================================================
# 4. Graph Construction
# ==============================================================================

def get_agent_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("designer", designer_node)
    workflow.add_node("secretary", secretary_node)
    workflow.set_entry_point("analyst")
    
    workflow.add_conditional_edges(
        "analyst",
        lambda x: x["next_step"],
        {"designer": "designer", "secretary": "secretary", END: END}
    )
    workflow.add_edge("designer", END)
    workflow.add_edge("secretary", END)
    return workflow.compile()

def run_agent(user_query: str, user_email: str):
    app = get_agent_graph()
    inputs = {"messages": [HumanMessage(content=user_query)], "user_email": user_email}
    return app.invoke(inputs)
