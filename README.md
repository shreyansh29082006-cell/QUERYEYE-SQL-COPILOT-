# QueryEye 🔍

> **ChatGPT for your database** — ask questions in plain English, get SQL answers with full reasoning transparency.

QueryEye is an agentic NL-to-SQL system built on LangGraph. Upload any SQLite database, ask natural language questions, and get accurate SQL queries with a self-correction loop, human-in-the-loop approval, and LangSmith observability — all through a Streamlit interface backed by a FastAPI async backend.

---

## Demo

<!-- Add a GIF or screenshot here after deployment -->

---

## Features

- **Natural Language to SQL** — Powered by `openai/gpt-oss-120b` via OpenRouter and LangChain's `SQLDatabaseToolkit`
- **Intent Routing** — LangGraph `StateGraph` classifies queries as `RETRIEVE` (SELECT) or `ANALYZE` (aggregations, comparisons) before generation
- **Self-Correction Loop** — Auto-retries on SQL execution errors, up to 3 attempts, with error context fed back to the LLM
- **Human-in-the-Loop** — Generated SQL is surfaced for user approval via LangGraph's `interrupt` mechanism before execution
- **SQL Injection Protection** — Blocks dangerous keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, etc.) at the agent level
- **LangSmith Tracing** — Full agent observability: every node, every retry, every tool call

---

## Architecture

```
User Query (Streamlit)
        │
        ▼
  FastAPI Backend (async)
        │
        ▼
  LangGraph StateGraph
   ┌────┴────┐
   │         │
RETRIEVE   ANALYZE
   └────┬────┘
        │
   SQL Generation (gpt-oss-120b)
        │
   Human-in-the-Loop ──► User Approves/Rejects
        │
   SQL Execution
        │
   Self-Correction (on error, max 3 retries)
        │
   Result → Streamlit
```

**State managed across nodes:**
- `messages` — full conversation history
- `intent` — RETRIEVE / ANALYZE
- `generated_sql` — current SQL candidate
- `retry_count` — correction loop counter
- `approved` — HiTL flag

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI (async) |
| Agent Framework | LangGraph `StateGraph` |
| LLM | OpenRouter — `openai/gpt-oss-120b` |
| SQL Toolkit | LangChain `SQLDatabaseToolkit` |
| User DB | SQLite (ephemeral, upload per session) |
| Chat History | SQLite via `SqliteSaver` |
| Observability | LangSmith |

---

## Project Structure

```
queryeye/
├── agent.py                # LangGraph StateGraph, nodes, intent router, self-correction
├── database.py             # SQLite DB loading, schema extraction, query execution
├── main.py                 # FastAPI app, routes, session management
├── frontend_queryeye.py    # Streamlit UI
├── queryeye_test.py        # Unit + integration tests
├── requirements.txt
└── .env.example
```

---

## Setup

### Prerequisites
- Python 3.11+
- OpenRouter API key
- LangSmith API key

### Local Development

```bash
git clone https://github.com/<your-username>/queryeye.git
cd queryeye

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`):

```env
OPENROUTER_API_KEY=your_openrouter_api_key
LANGSMITH_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=queryeye
```

Run the backend:
```bash
uvicorn main:app --reload
```

Run the frontend (separate terminal):
```bash
streamlit run frontend_queryeye.py
```

---

## How It Works

1. **Upload** your SQLite `.db` file through the Streamlit UI
2. QueryEye extracts the schema and initializes the `SQLDatabaseToolkit`
3. **Ask** a question in plain English
4. The LangGraph agent **routes intent** → generates SQL → **pauses for your approval**
5. On approval, SQL executes; on error, the agent **self-corrects** (up to 3 retries)
6. Results are displayed with the final SQL for transparency

---

## Observability

All agent traces are visible in [LangSmith](https://smith.langchain.com). Each run shows:
- Intent classification decision
- SQL generation prompt + output
- Self-correction iterations
- Tool calls and execution results

---


## License

MIT
