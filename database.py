import pandas as pd
import os
import sqlite3
import json
from langchain_community.utilities import SQLDatabase




JSON_FILE ="uploaded_files.json"

def load_records():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE,"r") as f:
            load=json.load(f)
            return load
    return {}

def save_records(records):
    with open(JSON_FILE,"w") as f:
        json.dump(records,f,indent=4)


def store_database(file_path, table_name):
    conn = sqlite3.connect("queryeye.db")

    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)

    elif file_path.endswith(".xlsx"):
        df = pd.read_excel(file_path, engine="openpyxl")

    elif file_path.endswith(".xls"):
        df = pd.read_excel(file_path, engine="xlrd")

    elif file_path.endswith(".sql"):
        with open(file_path, "r") as f:
            sql_script = f.read()
        conn.executescript(sql_script)
        conn.close()
        return f"SQL file executed successfully"

    else:
        raise ValueError("Unsupported file format") 
    
    df.columns = df.columns.str.strip()           # remove leading/trailing spaces
    df.columns = df.columns.str.replace(" ", "_") # replace spaces with underscore
    df.columns = df.columns.str.replace(r"[^\w]", "", regex=True)

    df.to_sql(
        table_name,
        conn,
        if_exists="replace",
        index=False
    )

    conn.close()

    return f"Table '{table_name}' created successfully"



def delete_table(table_name):
    conn=sqlite3.connect("queryeye.db")
    cursor=conn.cursor()
    cursor.execute(f"DROP TABLE IF EXISTS '{table_name}'")
    conn.commit()
    conn.close()


def get_sql_database():
    db_path = os.path.join(os.path.dirname(__file__), "queryeye.db")
    return SQLDatabase.from_uri(f"sqlite:///{db_path}")


