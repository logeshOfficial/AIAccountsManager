import os
import json
import re
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
        # Default X to 'month' if it exists, else use the first column or 'vendor_name'
        if not x:
            if "month" in data.columns:
                x = "month"
            elif "vendor_name" in data.columns:
                x = "vendor_name"
            else:
                x = data.columns[0]
        
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

def extract_json_from_text(text: str) -> Dict:
    """Robustly extracts JSON from LLM output using Regex."""
    try:
        # Try direct load first
        return json.loads(text.strip())
    except Exception:
        # Look for JSON block between curly braces
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try:
                # Basic cleaning of common markdown noise
                clean_json = match.group(0).replace('```json', '').replace('```', '').strip()
                return json.loads(clean_json)
            except Exception:
                pass
    return {}

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
    6. CRITICAL: If the user asks for a "report", "overview", or data for a specific year/month, always favor 'designer' first so a visual chart is generated. The designer will handle handing off to the secretary for the Excel file.
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
        summary = f"🔍 [V2.0] I found {len(df)} matching records. "
        
        # --- Descriptive Analysis Hook ---
        is_descriptive = any(k in user_query.lower() for k in ["describe", "explain", "detailed", "brief", "overview", "summary"])
        if is_descriptive:
            try:
                # Quick financial snapshot for the summary
                total_spent = df['total_amount'].sum()
                top_vendor = df.groupby('vendor_name')['total_amount'].sum().idxmax()
                avg_val = df['total_amount'].mean()
                
                summary += f"\n\n**Financial Overview:**\n"
                summary += f"- **Total Expenditure:** ${total_spent:,.2f}\n"
                summary += f"- **Primary Vendor:** {top_vendor}\n"
                summary += f"- **Average Invoice Value:** ${avg_val:,.2f}\n"
                summary += "\nThis dataset provides a comprehensive look at your financial activity for the requested period."
            except Exception:
                pass

        if filters.get('target_year') and not (filters.get('target_month') or filters.get('target_day')):
            summary += f"\n\nProcessing yearly overview for {filters['target_year']} (multi-sheet by month)."
        elif filters.get('target_month'):
            summary += f"\n\nFiltered for {filters['target_month']} {filters.get('target_year', '')}."
        elif filters.get('invoice_number') or len(df) == 1:
            inv = df.iloc[0]
            summary += f"\n\nDetails: Invoice #{inv['invoice_number']} from {inv['vendor_name']} ({inv['invoice_date']}) for ${inv['total_amount']:.2f}."
        evidence_found = True
    else:
        summary = "I couldn't find any invoices matching those specific details in your records."
        evidence_found = False
        
    # Show summary if it's descriptive OR if we are ending the graph (END)
    # This ensures "describe 2012" shows the text AND the chart/report.
    is_descriptive = any(k in user_query.lower() for k in ["describe", "explain", "detailed", "brief", "overview", "summary"])
    display_summary = summary if (next_node == END or is_descriptive) else ""
    
    return {
        "invoices_df": df, 
        "messages": [AIMessage(content=display_summary)], 
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
        
    # Find the latest human message for intent check
    user_query = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
            
    llm = get_llm()
    prompt = f"User asked: '{user_query}'. Which chart ('bar', 'pie', 'line', 'sensex') is best for {len(df)} rows? "
    prompt += 'IMPORTANT: If the user explicitly asks for a specific type (e.g., "pie" or "bar"), you MUST use that. '
    prompt += 'If the user wants a trend or "sensex" graph, use "sensex". '
    prompt += 'Identify if they specified X or Y axis columns. '
    prompt += 'Respond with JSON: {"chart_type": "type", "title": "title", "aggregate_by": "month | vendor | none", "x_axis": "col_name", "y_axis": "col_name"}'
    
    try:
        # Determine chart type with overrides
        explicit_chart_type = None
        lower_query = user_query.lower()
        if "sensex" in lower_query or "trend" in lower_query:
            explicit_chart_type = "sensex"
        elif "pie" in lower_query or "pei" in lower_query: # Handle user typo
            explicit_chart_type = "pie"
        elif "line" in lower_query:
            explicit_chart_type = "line"
        elif "bar" in lower_query:
            explicit_chart_type = "bar"
            
        explicit_axes = any(k in lower_query for k in ["axis", "x-axis", "y-axis", "param"])
        
        if not explicit_chart_type and not explicit_axes:
            # Apply defaults based on filters
            filters = state.get("extracted_filters", {})
            if filters.get("target_year") and not filters.get("target_month"):
                chart_type = "bar"
                aggregate_by = "month"
                x_axis = "month"
                y_axis = "total_amount"
                title = f"Monthly Expenses for {filters['target_year']}"
            elif filters.get("target_month"):
                chart_type = "bar"
                aggregate_by = "none" # Use raw date for day-level detail
                x_axis = "date"
                y_axis = "total_amount"
                month_name = filters["target_month"]
                title = f"Daily Expenses for {month_name} {filters.get('target_year', '')}"
            else:
                # Fallback to LLM for other cases
                response = llm.invoke(prompt)
                cfg = extract_json_from_text(response.content)
                chart_type = cfg.get("chart_type", "bar")
                aggregate_by = cfg.get("aggregate_by", "none")
                x_axis = cfg.get("x_axis", "")
                y_axis = cfg.get("y_axis", "total_amount")
                title = cfg.get("title", f"Analysis: {state['extracted_filters'].get('vendor_name', 'Expenses')}")
        else:
            # User is asking to change something, use LLM to interpret
            response = llm.invoke(prompt)
            cfg = extract_json_from_text(response.content)
            chart_type = explicit_chart_type or cfg.get("chart_type", "bar")
            aggregate_by = cfg.get("aggregate_by", "none")
            x_axis = cfg.get("x_axis", "")
            y_axis = cfg.get("y_axis", "total_amount")
            title = cfg.get("title", f"Analysis: {state['extracted_filters'].get('vendor_name', 'Expenses')}")
        
        if aggregate_by == "month":
            df = df.copy()
            df['month'] = pd.to_datetime(df['invoice_date']).dt.strftime('%b') # Abbreviated month
            
            agg_dict = {y_axis: 'sum' if y_axis in df.columns else 'count'}
            if 'vendor_name' in df.columns: 
                agg_dict['vendor_name'] = lambda x: ', '.join(pd.Series(x).unique())
            
            df = df.groupby('month').agg(agg_dict).reset_index()
            # Sort months correctly
            month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            df['month'] = pd.Categorical(df['month'], categories=month_order, ordered=True)
            df = df.sort_values('month')
            x_axis = "month"
        elif x_axis == "date":
            df = df.copy()
            df['date'] = pd.to_datetime(df['invoice_date']).dt.strftime('%d') # Day of month
            df = df.sort_values('invoice_date')
            x_axis = "date"
            
    except Exception as e:
        logger.warning(f"Designer failed to select chart: {e}")
        chart_type, title, x_axis, y_axis = "bar", "Expense Analysis", None, "total_amount"

    chart_json, chart_file = generate_chart_tool(df, chart_type, title, x=x_axis, y=y_axis)
    
    # Detailed response with interactive prompt
    msg = f"📊 [V2.0] I've generated a {chart_type} chart for the selected data.\n\n"
    msg += "📍 **Next Steps:**\n"
    msg += "- **Customize:** Would you like to change the chart type (e.g., sensex, trend, pie) or modify the X/Y axes parameters?\n"
    msg += "- **Email:** If you'd like to email this graph to yourself or others, just reply with the email addresses!"
    
    additional_kwargs = {"chart_file": chart_file}
    
    # Handoff to secretary if email or report is requested
    handoff_keywords = ["email", "send", "mail", "report", "excel", "download", "delivery"]
    if any(k in user_query.lower() for k in handoff_keywords):
        next_step = "secretary"
    else:
        next_step = END

    return {
        "generated_chart": json.loads(chart_json) if chart_json else None, 
        "generated_chart_file": chart_file,
        "messages": [AIMessage(content=msg, additional_kwargs=additional_kwargs)], 
        "next_step": next_step
    }

def secretary_node(state: AgentState):
    """Dynamic delivery to custom destination emails with multi-sheet support."""
    df = state["invoices_df"]
    
    # Find the latest human message for intent check
    user_query = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
            
    filters = state.get("extracted_filters", {})
    dest_email_raw = filters.get("target_email") or state["user_email"]
    
    # Handle multiple emails if provided as comma-separated string
    if isinstance(dest_email_raw, str):
        dest_emails = [e.strip() for e in dest_email_raw.split(',') if '@' in e]
    else:
        dest_emails = [dest_email_raw]

    msg = ""
    attachments = []
    
    # Check for Excel report request
    is_report_request = any(k in user_query.lower() for k in ["excel", "report", "download"])
    if is_report_request:
        time_parts = [str(filters.get(k)) for k in ["target_day", "target_month", "target_year"] if filters.get(k)]
        suffix = "_".join(time_parts) or filters.get("vendor_name") or "Report"
        file_path = generate_excel_tool(df, f"Invoices_{suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx", filters=filters)
        attachments.append(file_path)
        
    elif state.get("generated_file") and any(k in user_query.lower() for k in ["email", "send", "mail"]):
        attachments.append(state["generated_file"])
        
    # Check for Graph/Email chart request
    if state.get("generated_chart_file") and any(k in user_query.lower() for k in ["email", "send", "mail"]):
        if any(k in user_query.lower() for k in ["graph", "chart", "visual", "it", "visuals"]):
            attachments.append(state["generated_chart_file"])

    send_confirm = ""
    if "email" in user_query.lower() or "send" in user_query.lower():
        subject = f"Financial Analysis Report"
        body = f"Hello,\n\nPlease find the requested financial data attached."
        
        # Send to each email
        success_count = 0
        for email in dest_emails:
            if send_email_tool(email, subject, body, [a for a in attachments if a]):
                success_count += 1
        
        if success_count > 0:
            send_confirm = f"✅ Report sent successfully to {', '.join(dest_emails[:2])}{' and others' if len(dest_emails)>2 else ''}."
        else:
            send_confirm = "❌ Email delivery failed. Please check your credentials or recipient addresses."

    # Build detailed user-facing response
    if is_report_request:
        msg = (
            f"📁 [V2.0] Success! I found {len(df)} matching records. Processing the report overview.\n\n"
            "**The Excel report has been generated successfully!**\n\n"
            "📍 **Next Steps:**\n"
            "- **Download:** Click the **Download Excel Report** button below to save it to your device.\n"
            "- **Email:** If you want to send this report (and any generated graphs) to clients or colleagues, just reply with their email addresses (e.g., `user1@example.com, user2@example.com`). I'll handle the delivery for you.\n"
            "- **Visualize:** I can also create more charts or summaries if you need a different perspective on these records.\n\n"
            f"{send_confirm}"
        )
    elif send_confirm:
        msg = send_confirm
    else:
        msg = "I've processed your request. Is there anything else you'd like to do with these records?"
    
    # Include Excel file path in message metadata for UI download button
    additional_kwargs = {}
    if attachments and attachments[0].endswith('.xlsx'):
        additional_kwargs["file"] = attachments[0]
    elif state.get("generated_file"):
        additional_kwargs["file"] = state["generated_file"]
        
    return {"messages": [AIMessage(content=msg, additional_kwargs=additional_kwargs)], "next_step": END}

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
    
    # Designer can go to secretary or END
    workflow.add_conditional_edges(
        "designer",
        lambda x: x["next_step"],
        {"secretary": "secretary", END: END}
    )
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
