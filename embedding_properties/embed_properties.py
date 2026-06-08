import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

DB_CONN  = os.environ["PROPERTY_DB_CONN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

def create_document(row):

    return f"""
    Property: {row['property_name']}
    Location: {row['location']}
    Price: {row['price']}
    Bedrooms: {row['bedrooms']}
    Bathrooms: {row['bathrooms']}
    Land Area: {row['land_area_m2']}
    Building Area: {row['building_area_m2']}
    """

def get_embedding(client, text):

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding

def insert_embedding(db_conn, property_id, content, embedding):
    try:
        conn = psycopg2.connect(db_conn)
    except psycopg2.OperationalError as exc:
        if "postgres-data" in db_conn:
            fallback_conn = db_conn.replace("postgres-data:5432", "localhost:5433")
            print('Format connection with localhost ...')
            conn = psycopg2.connect(fallback_conn)
        else:
            raise
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO property_embeddings
        (
            property_id,
            content,
            embedding
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (property_id)
        DO UPDATE SET
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding
        """,
        (
            property_id, content, embedding
        )
    )
    conn.commit()
    conn.close()

def load_property_ids(db_conn: str = DB_CONN) -> set[str]:
    """Return the set of existing property IDs from Postgres."""

    collect_data_query = """
        SELECT * FROM property_listings limit 10;
    """
    try:
        conn = psycopg2.connect(db_conn)
    except psycopg2.OperationalError as exc:
        if "postgres-data" in db_conn:
            fallback_conn = db_conn.replace("postgres-data:5432", "localhost:5433")
            conn = psycopg2.connect(fallback_conn)
        else:
            raise

    try:
        with conn.cursor() as cur:
            cur.execute(collect_data_query)
            
            # Fetch all rows
            columns = [desc[0] for desc in cur.description]
            all_data = [
                        dict(zip(columns, row))
                        for row in cur.fetchall()
                    ]
            # all_data = cur.fetchall()
    finally:
        conn.close()
    return all_data

def ingest_embedding():
    client = OpenAI(
        api_key=OPENAI_KEY
    )

    properties = load_property_ids(db_conn=DB_CONN)
    print('Ingest emebeded property data ...')

    for property_data in properties:
        print(property_data)
        document = create_document(property_data)
        print('-' * 25)
        embedding = get_embedding(client, document)
        insert_embedding(
            db_conn=DB_CONN,
            property_id=property_data["property_id"],
            content=document,
            embedding=embedding
        )

        print(f"Embedded: {property_data['property_id']}")

def ingest_embedding_dag(openai_key, properties):
    client = OpenAI(
        api_key=openai_key
    )
    print('Ingest emebeded property data ...')

    for property_data in properties:
        print(property_data)
        document = create_document(property_data)
        print('-' * 25)
        embedding = get_embedding(client, document)
        insert_embedding(
            db_conn=DB_CONN,
            property_id=property_data["property_id"],
            content=document,
            embedding=embedding
        )

    print(f"Embedded: {property_data['property_id']}")

def search_property(conn, question):
    print(f'Question : {question}')
    cursor = conn.cursor()
    query_embedding = get_embedding(
        OpenAI(api_key=OPENAI_KEY), 
        question
    )
    
    cursor.execute(
        """
        SELECT
            property_id,
            content,
            embedding <=> %s::vector AS distance
        FROM property_embeddings
        ORDER BY distance
        LIMIT 5
        """,
        (query_embedding,)
    )

    print(cursor.fetchall())

    return cursor.fetchall()

if __name__ == "__main__":
    try:
        conn = psycopg2.connect(DB_CONN)
    except psycopg2.OperationalError as exc:
        if "postgres-data" in DB_CONN:
            fallback_conn = DB_CONN.replace("postgres-data:5432", "localhost:5433")
            conn = psycopg2.connect(fallback_conn)
        else:
            raise
    search_property(
        conn=conn,
        question="tunjukan kepada saya rumah-rumah bertipe minimalis dn murah di bogor"
    )
    