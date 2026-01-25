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
import tempfile

logger = get_logger(__name__)

# ==============================================================================
# 1. State Definition
# ==============================================================================

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    user_email: str
    invoices_df: pd.DataFrame
    generated_chart: Dict # JSON representation of Plotly chart
    generated_chart_file: str # Path to created HTML chart file
    generated_file: str # Path to created Excel file
    next_step: str # To guide the graph flow
    extracted_filters: Dict # Search criteria like vendor, year, or invoice #
    evidence_found: bool # Curried RAG flag for validation

# ==============================================================================
# 2. Tool Implementations
# ==============================================================================

def generate_chart_tool(data: pd.DataFrame, chart_type: str, title: str, x: str = None, y: str = "total_amount"):
    """Generates a Plotly chart based on the data."""
    try:
        # Default X to 'month' if it exists, else the first column
        if not x:
            x = "month" if "month" in data.columns else data.columns[0]
        
        # Determine available hover columns
        hover_cols = [c for c in ["vendor_name", "description"] if c in data.columns]
        
        if chart_type == "bar":
            fig = px.bar(data, x=x, y=y, title=title, hover_data=hover_cols)
        elif chart_type == "pie":
            fig = px.pie(data, values=y, names=x, title=title, hover_data=hover_cols)
        elif chart_type == "line" or chart_type == "sensex":
            # "sensex" graph is a line chart with markers
            fig = px.line(data, x=x, y=y, title=title, markers=True, hover_data=hover_cols)
            if chart_type == "sensex":
                fig.update_traces(line=dict(width=3, color='royalblue'), marker=dict(size=10, symbol='diamond'))
        else:
            return None, None
        
        # Save as interactive HTML for emailing
        filename = f"Chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        fig.write_html(filepath)
        
        return fig.to_json(), filepath
    except Exception as e:
        logger.error(f"Chart tool failed: {e}")
        return None, None

def generate_excel_tool(data: pd.DataFrame, filename: str, filters: Dict = None):
    """
    Generates an Excel report. 
    Smart Sheet Logic:
    - Multi-sheet: If target_year is provided and NO target_month/target_day is provided.
    - Single-sheet: Otherwise.
    """
    filepath = os.path.join(tempfile.gettempdir(), filename)
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

def send_email_tool(to_email: str, subject: str, body: str, attachments: List[str] = None):
    """Sends an email with optional attachments."""
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
            attachments=attachments
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
    
    # Provide the last few messages for context in the prompt
    history_context = "\n".join([f"{'User' if msg.type=='human' else 'Assistant'}: {msg.content}" for msg in state["messages"][:-1]])
    
    # Provide current filters as context
    current_filters = state.get("extracted_filters", {})
    
    prompt = f"""You are a Financial Analyst. 
    Conversational Context:
    {history_context}
    
    Current Active Filters: {json.dumps(current_filters) if current_filters else 'None'}
    
    Latest User Query: '{user_query}'
    
    TASK:
    1. Analyze the latest query considering the context above and the current active filters.
    2. If the user refers to "them", "that", "these", or asks for modifications to a previous search, resolve the references.
    3. IMPORTANT: If the query is a continuation (e.g., "Now graph them", "Filter by 2024", "Email this", "Send me the chart"), you MUST CARRY OVER relevant filters (vendor_name, invoice_number, etc.) from previous turns unless the user explicitly changes them.
    4. If the user asks to "reset" or "clear" filters, set all filter values to null.
    5. Available nodes: 'designer' (for visuals/charts), 'secretary' (for reports/emails), 'END'.
    Data available for vendors like: {df['vendor_name'].unique().tolist() if not df.empty else 'None'}
    
    Extract or Update Search Filters:
    - vendor_name: (partial or exact)
    - invoice_number: (alphanumeric identifier)
    - target_year: (4-digit year like '2025')
    - target_month: (month name or number 1-12)
    - target_day: (day of the month 1-31)
    - target_email: (email address to send reports to)
    
    Respond strictly in JSON:
    {{
      "next_node": "node_name",
      "filters": {{
        "vendor_name": "value or previous", 
        "invoice_number": "value or previous", 
        "target_year": "value or previous", 
        "target_month": "value or previous", 
        "target_day": "value or previous", 
        "target_email": "value or previous"
      }}
    }}"""
    
    try:
        response = llm.invoke(prompt)
        clean_content = response.content.replace('```json', '').replace('```', '').strip()
        decision = json.loads(clean_content)
        
        next_node = decision.get("next_node", END)
        filters = decision.get("filters", {})
        
        # Clean invoice number if present in filters
        if filters.get("invoice_number"):
            from data_normalization_utils import clean_invoice_number
            filters["invoice_number"] = clean_invoice_number(filters["invoice_number"])
        
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
        evidence_found = True
    else:
        summary = "I couldn't find any invoices matching those specific details in your records."
        evidence_found = False
        
    return {
        "invoices_df": df, 
        "messages": [AIMessage(content=summary)], 
        "next_step": next_node,
        "extracted_filters": filters,
        "evidence_found": evidence_found
    }

def validator_node(state: AgentState):
    """
    Curried RAG Guardrail: Validates if the retrieved data (evidence) 
    is sufficient for the requested action.
    """
    df = state["invoices_df"]
    user_query = state["messages"][0].content.lower()
    next_step = state.get("next_step", END)
    evidence_found = state.get("evidence_found", False)
    
    # List of intent keywords that require evidence
    data_intents = ["graph", "chart", "visual", "excel", "report", "download", "send", "email", "how much", "total spent"]
    is_data_query = any(k in user_query for k in data_intents)
    
    logger.info(f"Validator Node: Data Query={is_data_query}, Evidence Found={evidence_found}")
    
    if is_data_query and not evidence_found:
        msg = "⚠️ I lack the specific invoice evidence to perform that action or answer that question accurately. Please check your query or ensure the data is synced from Drive."
        return {
            "messages": [AIMessage(content=msg)],
            "next_step": END
        }
    
    # If evidence is found or it's a general query, allow the flow to continue
    return {"next_step": next_step}

def designer_node(state: AgentState):
    """Smart chart generation on FILTERED data."""
    df = state["invoices_df"]
    if df.empty:
        return {"messages": [AIMessage(content="No data found to visualize.")], "next_step": END}
        
    user_query = state["messages"][0].content
    llm = get_llm()
    prompt = f"User asked: '{user_query}'. Which chart ('bar', 'pie', 'line', 'sensex') is best for {len(df)} rows? "
    prompt += 'If the user wants a trend or "sensex" graph, use "sensex". '
    prompt += 'Identify if they specified X or Y axis columns. '
    prompt += 'Respond with JSON: {"chart_type": "type", "title": "title", "aggregate_by": "month | none", "x_axis": "col_name", "y_axis": "col_name"}'
    
    try:
        response = llm.invoke(prompt)
        cfg = json.loads(response.content.replace('```json', '').replace('```', '').strip())
        chart_type = cfg.get("chart_type", "bar")
        aggregate_by = cfg.get("aggregate_by", "none")
        x_axis = cfg.get("x_axis", "invoice_date")
        y_axis = cfg.get("y_axis", "total_amount")
        title = cfg.get("title", f"Analysis: {state['extracted_filters'].get('vendor_name', 'Expenses')}")
        
        if aggregate_by == "month":
            df = df.copy()
            df['month'] = pd.to_datetime(df['invoice_date']).dt.strftime('%Y-%m')
            
            # Aggregation logic to preserve hover data
            agg_dict = {y_axis: 'sum' if y_axis in df.columns else 'count'}
            if 'vendor_name' in df.columns: 
                agg_dict['vendor_name'] = lambda x: ', '.join(pd.Series(x).unique())
            if 'description' in df.columns: 
                agg_dict['description'] = lambda x: '; '.join(pd.Series(x).dropna().unique()[:3])
            
            df = df.groupby('month').agg(agg_dict).reset_index().sort_values('month')
            x_axis = "month"
            
    except Exception as e:
        logger.warning(f"Designer failed to select chart: {e}")
        chart_type, title, x_axis, y_axis = "bar", "Expense Analysis", None, "total_amount"

    chart_json, chart_file = generate_chart_tool(df, chart_type, title, x=x_axis, y=y_axis)
    return {
        "generated_chart": json.loads(chart_json) if chart_json else None, 
        "generated_chart_file": chart_file,
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
    attachments = []
    
    # Check for Excel report request
    if any(k in user_query.lower() for k in ["excel", "report", "download"]):
        time_parts = [str(filters.get(k)) for k in ["target_day", "target_month", "target_year"] if filters.get(k)]
        suffix = "_".join(time_parts) or filters.get("vendor_name") or "Report"
        file_path = generate_excel_tool(df, f"Invoices_{suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx", filters=filters)
        attachments.append(file_path)
        msg += f"Excel report generated. "
    elif state.get("generated_file") and any(k in user_query.lower() for k in ["email", "send", "mail"]):
        # Reuse existing Excel if user asks to email it
        attachments.append(state["generated_file"])
        msg += "Excel report included in email. "
        
    # Check for Graph/Email chart request
    if state.get("generated_chart_file") and any(k in user_query.lower() for k in ["email", "send", "mail"]):
        if any(k in user_query.lower() for k in ["graph", "chart", "visual", "it"]):
            attachments.append(state["generated_chart_file"])
            msg += "Graph included in email. "

    if "email" in user_query.lower() or "send" in user_query.lower():
        subject = f"Financial Analysis Request"
        body = f"Hello,\n\nPlease find the requested financial data attached."
        success = send_email_tool(dest_email, subject, body, [a for a in attachments if a])
        msg += f"Email sent to {dest_email}." if success else "Email delivery failed."
        
    return {"messages": [AIMessage(content=msg)], "next_step": END}

# ==============================================================================
# 4. Graph Construction
# ==============================================================================

def get_agent_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("designer", designer_node)
    workflow.add_node("secretary", secretary_node)
    workflow.set_entry_point("analyst")
    
    workflow.add_edge("analyst", "validator")
    
    workflow.add_conditional_edges(
        "validator",
        lambda x: x["next_step"],
        {"designer": "designer", "secretary": "secretary", END: END}
    )
    workflow.add_edge("designer", END)
    workflow.add_edge("secretary", END)
    return workflow.compile()

def run_agent(user_query: str, user_email: str, history: List[BaseMessage] = None):
    history = history or []
    
    # --- 🔄 Restore Context from History ---
    last_filters = {}
    last_chart_file = None
    last_excel_file = None
    
    for msg in reversed(history):
        if isinstance(msg, AIMessage) and hasattr(msg, "additional_kwargs"):
            if not last_filters:
                last_filters = msg.additional_kwargs.get("filters", {})
            if not last_chart_file:
                last_chart_file = msg.additional_kwargs.get("chart_file")
            if not last_excel_file:
                last_excel_file = msg.additional_kwargs.get("file")
                
    app = get_agent_graph()
    inputs = {
        "messages": history + [HumanMessage(content=user_query)], 
        "user_email": user_email,
        "extracted_filters": last_filters,
        "generated_chart_file": last_chart_file,
        "generated_file": last_excel_file
    }
    return app.invoke(inputs)
