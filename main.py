from fastapi import FastAPI, UploadFile, File,HTTPException
from database import store_database, load_records, save_records,delete_table
from agent import workflow
import shutil
import re
import os


app = FastAPI()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    table_name = os.path.splitext(file.filename)[0]
    table_name = re.sub(r"[^\w]", "_", table_name)  # sanitize

    # 1. check if file already exists
    records = load_records()
    if table_name in records:
        return {"message": f"Table '{table_name}' already exists. Please rename your file or delete the existing one."}

    # 2. save file temporarily
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 3. store in sqlite
    result = store_database(temp_path, table_name)

    # 4. update json records
    records[table_name] = file.filename
    save_records(records)

    # 5. delete temp file
    os.remove(temp_path)

    return {"message": result}





@app.delete("/delete/{table_name}")
async def delete_table_endpoint(table_name: str):

    records = load_records()

    if table_name not in records:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' not found"
        )
    delete_table(table_name)

    del records[table_name]
    save_records(records)

    return {"message": f"Table '{table_name}' deleted successfully"}



@app.post("/query")

async def query(user_input:str,thread_id:str):
    result = workflow.invoke(
        {
            "message": user_input,
            "sql_query": "",
            "sql_result": "",
            "error": "",
            "retry_count": 0,
            "final_answer": "",
            "intent": ""
        },
        config={"configurable": {"thread_id": thread_id}}
    )
    return {"answer": result["final_answer"]}