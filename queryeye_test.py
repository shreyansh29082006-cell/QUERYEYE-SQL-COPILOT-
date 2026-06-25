from database import store_database
from agent import workflow
import ast
import pandas as pd


result = workflow.invoke(
    {
        "message": "show me all rows from the FINAL450",
        "sql_query": "",
        "sql_result": "",
        "error": "",
        "retry_count": 0,
        "final_answer": "",
        "intent": ""
    },
    config={"configurable": {"thread_id": "test_1"}}
)

result_str = result["final_answer"]

# extract just the result part
raw = result_str.split("Result:\n")[1]

# parse tuples and convert to dataframe
rows = ast.literal_eval(raw)
df = pd.DataFrame(rows)
print(df.to_string())