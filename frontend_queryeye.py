import streamlit as st
from agent import workflow, retrieve_allthread
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage
from database import store_database, delete_table, load_records, save_records
import uuid
import tempfile
import pandas as pd
import io
import os


def generate_thread_id():
    return str(uuid.uuid4())

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    add_thread(thread_id)
    st.session_state["message_history"] = []

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)

def load_conversation(thread_id):
    state = workflow.get_state({"configurable": {"thread_id": thread_id}})
    values = state.values
    if not values:
        return []
    return values

def messages_to_history(messages):
    history = []
    for msg in messages:
        if isinstance(msg, (HumanMessage, AIMessage)) and msg.content:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            history.append({"role": role, "content": msg.content})
    return history

def render_assistant_message(msg):
    sql_q = msg.get("sql_query", "")
    sql_r = msg.get("sql_result", "")
    intent = msg.get("intent", "RETRIEVE")

    if sql_q:
        with st.expander("🔍 SQL Query"):
            st.code(sql_q, language="sql")

    if intent == "RETRIEVE" and sql_r:
        try:
            df = pd.read_csv(io.StringIO(sql_r))
            st.dataframe(df, use_container_width=True)
        except:
            st.markdown(msg.get("content", sql_r))
    else:
        st.markdown(msg.get("content", ""))

def display_final_state(final_state):
    """Extract from final_state and render + save to history."""
    sql_query = final_state.get("sql_query", "")
    sql_result = final_state.get("sql_result", "")
    final_answer = final_state.get("final_answer", "")
    intent = final_state.get("intent", "RETRIEVE")

    assistant_msg = {
        "role": "assistant",
        "content": final_answer,
        "sql_query": sql_query,
        "sql_result": sql_result,
        "intent": intent,
    }
    render_assistant_message(assistant_msg)
    st.session_state["message_history"].append(assistant_msg)


# --- Init ---
if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = retrieve_allthread()

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()
    add_thread(st.session_state["thread_id"])

if "message_history" not in st.session_state:
    messages = load_conversation(st.session_state["thread_id"])
    st.session_state["message_history"] = messages_to_history(messages)

if "uploaded_tables" not in st.session_state:
    st.session_state["uploaded_tables"] = load_records()

if "pending_interrupt" not in st.session_state:
    st.session_state["pending_interrupt"] = False

if "pending_config" not in st.session_state:
    st.session_state["pending_config"] = None


# --- Sidebar ---
st.sidebar.title("QueryEye")
st.sidebar.markdown("### 📂 Upload Data")

uploaded_file = st.sidebar.file_uploader(
    "CSV / Excel / SQL",
    type=["csv", "xlsx", "xls", "sql"],
    label_visibility="collapsed"
)

table_name_input = st.sidebar.text_input(
    "Table name",
    placeholder="e.g. sales_2024",
    help="Lowercase, no spaces. This is what the agent will query."
)

if st.sidebar.button("Upload & Load", disabled=(uploaded_file is None)):
    if not table_name_input.strip():
        st.sidebar.error("Table name cannot be empty.")
    else:
        table_name = table_name_input.strip().lower().replace(" ", "_")
        suffix = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name
        try:
            result = store_database(tmp_path, table_name)
            records = load_records()
            records[table_name] = uploaded_file.name
            save_records(records)
            st.session_state["uploaded_tables"] = records
            st.sidebar.success(f"✅ {result}")
        except Exception as e:
            st.sidebar.error(f"❌ {e}")
        finally:
            os.unlink(tmp_path)

# -- Loaded Tables --
if st.session_state["uploaded_tables"]:
    st.sidebar.markdown("### 🗄️ Loaded Tables")
    for tname, fname in list(st.session_state["uploaded_tables"].items()):
        col1, col2 = st.sidebar.columns([3, 1])
        col1.markdown(f"`{tname}`  \n<small>{fname}</small>", unsafe_allow_html=True)
        if col2.button("🗑️", key=f"del_{tname}", help=f"Delete {tname}"):
            delete_table(tname)
            records = load_records()
            records.pop(tname, None)
            save_records(records)
            st.session_state["uploaded_tables"] = records
            st.rerun()
else:
    st.sidebar.info("No tables loaded yet. Upload a file to get started.")

st.sidebar.divider()

# -- Conversations --
st.sidebar.markdown("### 💬 Conversations")

if st.sidebar.button("+ New Chat"):
    reset_chat()
    st.rerun()

for thread_id in st.session_state["chat_threads"][::-1]:
    is_active = thread_id == st.session_state["thread_id"]
    label = f"{'▶ ' if is_active else ''}{str(thread_id)[:8]}..."
    if st.sidebar.button(label, key=f"thread_{thread_id}"):
        st.session_state["thread_id"] = thread_id
        st.session_state["message_history"] = messages_to_history(load_conversation(thread_id))
        st.rerun()


# --- Main area ---
st.title("QueryEye 👁️")
st.caption("Chat with your data in plain English.")

# Render history
for msg in st.session_state["message_history"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_assistant_message(msg)
        else:
            st.markdown(msg["content"])

# --- HITL pending confirm/cancel ---
if st.session_state["pending_interrupt"]:
    st.warning("⚠️ Agent wants to run a data-modifying query. Confirm?")
    col1, col2 = st.columns(2)

    if col1.button("✅ Confirm", key="hitl_confirm"):
        final_state = None
        with st.spinner("Executing..."):
            for state_update in workflow.stream(
                Command(resume="yes"),
                config=st.session_state["pending_config"],
                stream_mode="values",
            ):
                final_state = state_update
        st.session_state["pending_interrupt"] = False
        if final_state:
            with st.chat_message("assistant"):
                display_final_state(final_state)
        st.rerun()

    if col2.button("❌ Cancel", key="hitl_cancel"):
        final_state = None
        with st.spinner("Cancelling..."):
            for state_update in workflow.stream(
                Command(resume="no"),
                config=st.session_state["pending_config"],
                stream_mode="values",
            ):
                final_state = state_update
        st.session_state["pending_interrupt"] = False
        if final_state:
            with st.chat_message("assistant"):
                display_final_state(final_state)
        st.rerun()


# --- Chat input ---
user_input = st.chat_input("Ask anything about your data...")

if user_input:
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    CONFIG = {
        "configurable": {"thread_id": st.session_state["thread_id"]},
        "metadata": {"thread_id": st.session_state["thread_id"]},
        "run_name": "chat_queryeye",
    }

    with st.chat_message("assistant"):
        final_state = None
        interrupted = False
        interrupt_data = None

        with st.spinner("Thinking..."):
            for state_update in workflow.stream(
                {"message": user_input},
                config=CONFIG,
                stream_mode="values",
            ):
                if "__interrupt__" in state_update:
                    interrupted = True
                    interrupt_data = state_update["__interrupt__"][0].value
                    break
                final_state = state_update

        if interrupted and interrupt_data:
            st.warning(interrupt_data.get("question", "⚠️ Confirm query?"))
            st.code(interrupt_data.get("sql", ""), language="sql")
            st.session_state["pending_interrupt"] = True
            st.session_state["pending_config"] = CONFIG

        elif final_state:
            display_final_state(final_state)

    