import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from langchain_core.messages import HumanMessage, AIMessage
from embedding_properties.embed_properties import create_db_connection
import os

DB_CONN  = os.environ["PROPERTY_DB_CONN"]

def save_message(user_id: int, chat_id: int, role : str, message: str, db_conn_=DB_CONN):
    db_conn = create_db_connection(db_conn_)

    query = """
        INSERT INTO chat_messages_history (user_id, chat_id, role, message)
        VALUES (%s, %s, %s, %s);
    """
    try:
        # Use the connection passed into the function
        with db_conn.cursor() as cursor:
            cursor.execute(query, (user_id, chat_id, role, message,))
            db_conn.commit()
    except Exception as e:
        db_conn.rollback()
        print(f"Failed to save log chat history: {e}")

def retrieve_message(chat_id, db_conn_=DB_CONN):
    db_conn = create_db_connection(db_conn_)
    langchain_history = []

    # print(inputs)

    # chat_id = inputs.get("chat_id")

    query = """
        SELECT role, message FROM chat_messages_history 
        WHERE chat_id = %s
        ORDER BY created_at DESC
        LIMIT 10
        ;
    """

    try:
        with db_conn.cursor() as cursor:
            cursor.execute(query, (chat_id,))
            db_conn.commit()
            db_rows = cursor.fetchall()
            langchain_history = []
            if len(db_rows) != 0:
                for sender, message in db_rows:
                    if sender == "user":
                        langchain_history.append(HumanMessage(content=message))
                    elif sender == "bot":
                        langchain_history.append(AIMessage(content=message))
    
    except Exception as e:
        db_conn.rollback()
        print(f"Failed to retrieve log chat history: {e}")

    return langchain_history


