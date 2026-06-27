import sqlite3
from typing import TypedDict
from dotenv import load_dotenv
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph, END
from langgraph.types import interrupt, Command
from database import get_sql_database
import csv, io


load_dotenv()
llm = ChatGroq(
    model=model="openai/gpt-oss-120b",
    temperature=0
)

DANGEROUS_KEYWORDS = {"drop", "delete", "truncate", "alter", "insert", "update", "create"}


class ChatState(TypedDict):
    message: str
    sql_query: str
    sql_result: str
    error: str
    retry_count: int
    final_answer: str
    intent: str


def chatintent(state: ChatState):
    user_input = state["message"]

    prompt = f"""
Classify the user query into one category:

RETRIEVE -> user only wants data/query result.
ANALYZE -> user wants insights, trends, comparisons, explanations.

Return ONLY one word: RETRIEVE or ANALYZE

User Query:
{user_input}
"""
    response = llm.invoke(prompt)
    intent = response.content.strip().upper()
    if intent not in ["RETRIEVE", "ANALYZE"]:
        intent = "RETRIEVE"

    return {
        "intent": intent,
        "retry_count": 0,
        "error": ""
    }


def chatquery(state: ChatState):
    user_input = state["message"]
    db = get_sql_database()
    schema = db.get_table_info()

    prompt = f"""You are a SQL expert. Given the database schema below, write a SQLite SQL query to answer the user's question.
Return ONLY the raw SQL query, no explanation, no markdown, no backticks.

Schema:
{schema}

User Question:
{user_input}
"""
    response = llm.invoke(prompt)
    return {"sql_query": response.content.strip()}


def human_review(state: ChatState):
    sql = state["sql_query"].strip()
    first_word = sql.split()[0].lower() if sql.split() else ""

    if first_word in DANGEROUS_KEYWORDS:
        # Execution ruk jaati hai yahan — frontend ko interrupt signal milta hai
        user_decision = interrupt({
            "question": f"⚠️ This query will modify your data. Do you want to proceed?",
            "sql": sql
        })

        if user_decision != "yes":
            return {
                **state,
                "final_answer": "❌ Query cancelled by user.",
                "sql_query": "",
                "error": "cancelled"
            }

    return state  # SELECT ya confirmed — aage badho


def execute_query(state: ChatState):
    # Agar cancelled hai toh execute mat karo
    if state.get("error") == "cancelled":
        return state

    conn = sqlite3.connect("queryeye.db")
    cursor = conn.cursor()
    try:
        cursor.execute(state["sql_query"])
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(rows)
            result = output.getvalue()
        else:
            result = "Query executed successfully."
        conn.commit()
        return {"sql_result": result, "error": ""}
    except Exception as e:
        return {"sql_result": "", "error": str(e)}
    finally:
        conn.close()


def correct_query(state: ChatState):
    db = get_sql_database()
    schema = db.get_table_info()

    prompt = f"""The following SQL query failed with this error:

Error: {state["error"]}
Query: {state["sql_query"]}
Schema: {schema}

Write a corrected SQLite SQL query. Return ONLY the raw SQL, no explanation.
"""
    response = llm.invoke(prompt)
    return {
        "sql_query": response.content.strip(),
        "retry_count": (state.get("retry_count") or 0) + 1
    }


def route_execution(state: ChatState):
    """Single router: handles cancelled, retry logic, and intent branching."""
    if state.get("error") == "cancelled":
        return "output_table"  # final_answer already set hai
    if state["error"] and (state.get("retry_count") or 0) < 3:
        return "correct_query"
    if state["intent"] == "ANALYZE":
        return "output_analysis"
    return "output_table"


def chatanswer(state: ChatState):
    # Cancelled case — final_answer already set hai
    if state.get("error") == "cancelled":
        return {"final_answer": state.get("final_answer", "❌ Query cancelled.")}
    return {
        "final_answer": f"Query:\n{state['sql_query']}\n\nResult:\n{state['sql_result']}"
    }


def chatanalyze(state: ChatState):
    truncated_result = state['sql_result'][:2000]
    if len(state['sql_result']) > 2000:
        truncated_result += "\n... (truncated)"

    prompt = f"""User question: {state['message']}

SQL query used: {state['sql_query']}

Data sample:
{truncated_result}

Give a concise analytical insight answering the user's question in 3-4 sentences.
"""
    response = llm.invoke(prompt)
    return {
        "final_answer": f"**Analysis:**\n{response.content.strip()}\n\n**Query:** `{state['sql_query']}`"
    }


conn = sqlite3.connect("queryeye_history.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)

graph = StateGraph(ChatState)

graph.add_node("user_intent", chatintent)
graph.add_node("sql_query", chatquery)
graph.add_node("human_review", human_review)   # NEW
graph.add_node("retrieve_table", execute_query)
graph.add_node("correct_query", correct_query)
graph.add_node("output_table", chatanswer)
graph.add_node("output_analysis", chatanalyze)

graph.add_edge(START, "user_intent")
graph.add_edge("user_intent", "sql_query")
graph.add_edge("sql_query", "human_review")    # sql_query -> human_review -> retrieve_table
graph.add_edge("human_review", "retrieve_table")
graph.add_conditional_edges(
    "retrieve_table",
    route_execution,
    {
        "correct_query": "correct_query",
        "output_table": "output_table",
        "output_analysis": "output_analysis",
    }
)
graph.add_edge("correct_query", "retrieve_table")
graph.add_edge("output_table", END)
graph.add_edge("output_analysis", END)

workflow = graph.compile(checkpointer=checkpointer)


def retrieve_allthread():
    all_threads = set()
    for checkpoint in checkpointer.list(None):
        tid = checkpoint.config["configurable"]["thread_id"]
        all_threads.add(tid)
    return list(all_threads)
