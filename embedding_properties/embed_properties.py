import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

DB_CONN  = os.environ["PROPERTY_DB_CONN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

def create_document(row):

    return f"""
    Nama properti: {row['property_name']}
    Lokasi: {row['location']}
    Harga: {row['price']}
    Jumlah Lantai: {row['floors']}
    Jumlah Tempat Tidur: {row['bedrooms']}
    Jumlah Kamar Mandi: {row['bathrooms']}
    Luas Tanah (m2): {row['land_area_m2']}
    Luas Bangunan (m2): {row['building_area_m2']}
    Jenis Sertifikat: {row['certificate']}
    Berada di Hook: {row['hoek']}
    Tegangan Listrik: {row['electrical_voltage']}
    """

def create_db_connection(db_conn):
    try:
        conn = psycopg2.connect(db_conn)
    except psycopg2.OperationalError as exc:
        if "postgres-data" in db_conn:
            fallback_conn = db_conn.replace("postgres-data:5432", "localhost:5433")
            conn = psycopg2.connect(fallback_conn)
        else:
            raise
    return conn

def get_embedding(client, text):

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding

def insert_embedding(db_conn, property_id, content, embedding):
    conn = create_db_connection(db_conn=db_conn)
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

    conn = create_db_connection(db_conn=db_conn)

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

def refine_question(question):
    prompt = f"""
        Anda adalah ahli properti, tugas anda adalah mendetailkan pertanyaan user menjadi lebih jelas.

        CONTOH pertanyaan (input) : "beri info rumah harga murah dong?"

        Dalam mendetailkan pertanyaan lakukan langkah-langkah ini:
        1. Pahami kata kunci permintaan
            - Contoh: "murah", "luas", "akses mudah", dst
        2. Cari kolom di database property ("property_name", "location", "property_id", "price", "land_area_m2", "building_area_m2", "certificate", "hoek", "bedrooms", "bathrooms", "electrical_voltage") yang represent permintaan user
            - Contoh: murah -> price, rumah luas -> land_area_m2, falitias lengkap -> bedrooms", "bathrooms", "electrical_voltage", dan seterusnya.
        3. Lalu susun ulang dari pendetailan anda menjadi sebuah pertanyaan baru yang lebih detail.

        OUTPUT: Langsung tampilkan pertanyaan baru
            - CONTOH Ekspektasi hasil : "IBisakah Anda memberikan informasi tentang rumah di daerah Bekasi dengan nomina harganya murah, serta detail mengenai harga, ukuran tanah dan bangunan, serta jumlah kamar tidur dan kamar mandi yang tersedia?"

        <pertanyaan>
        {question}
        <pertanyaan>
    """
    client = OpenAI(api_key=OPENAI_KEY)
    response = client.responses.create(
        model="gpt-4.1-mini",
        temperature=0.1,
        input=prompt
    )

    refined_question = response.output_text

    print('-' * 10)
    print(refined_question)
    print('-' * 10)

    return refined_question

def search_property(db_conn, question):
    print(f'Question : {question}')
    conn = create_db_connection(db_conn=db_conn)
    refined_question = refine_question(question)
    cursor = conn.cursor()
    query_embedding = get_embedding(
        OpenAI(api_key=OPENAI_KEY), 
        refined_question
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
    return cursor.fetchall()
    