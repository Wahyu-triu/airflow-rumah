from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

# Your scraper lives in /opt/airflow/scraper/
import sys
sys.path.insert(0, "/opt/airflow")

from scraper.utils import scrape_belirumah
from embedding_properties.embed_properties import ingest_embedding_dag

logger = logging.getLogger(__name__)

LOCATION = "Bogor"
PAGES    = 1        # how many listing pages per daily run

DB_CONN  = os.environ["PROPERTY_DB_CONN"]   # set in .env
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

default_args = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# ── Task functions ─────────────────────────────────────────────────────────

def task_scrape(**context):
    """Scrape listings and push raw data to XCom."""
    listings = scrape_belirumah(location=LOCATION, pages=PAGES)
    logger.info("Scraped %d listings.", len(listings))
    context["ti"].xcom_push(key="listings", value=listings)


def task_load(**context):
    """Pull listings from XCom, upsert into Postgres."""
    listings = context["ti"].xcom_pull(key="listings", task_ids="scrape_listings")
    if not listings:
        logger.warning("No listings to load.")
        return

    insert_sql = """
        INSERT INTO property_listings (
            property_id, scraped_at, property_name, location, price,
            land_area_m2, building_area_m2, certificate, hoek,
            bedrooms, bathrooms, floors, electrical_voltage,
            agent_name, date_published
        ) VALUES (
            %(property_id)s, NOW(), %(property_name)s, %(location)s, %(price)s,
            %(land_area_m2)s, %(building_area_m2)s, %(certificate)s, %(hoek)s,
            %(bedrooms)s, %(bathrooms)s, %(floors)s, %(electrical_voltage)s,
            %(agent_name)s, %(date_published)s
        )
        ON CONFLICT (property_id, ((scraped_at AT TIME ZONE 'UTC')::DATE)) DO NOTHING;
    """

    conn = psycopg2.connect(DB_CONN)
    try:
        with conn, conn.cursor() as cur:
            cur.executemany(insert_sql, listings)
            logger.info("Upserted %d rows.", cur.rowcount)
    finally:
        conn.close()

def task_embedding(**context):
    """Pull listings from XCom, Embedd using embedding model upsert into Postgres."""
    listings = context["ti"].xcom_pull(key="listings", task_ids="scrape_listings")
    if not listings:
        logger.warning("No listings to load.")
        return
    
    ingest_embedding_dag(
        openai_key=OPENAI_KEY, 
        properties=listings
    )

# ── DAG definition ─────────────────────────────────────────────────────────

with DAG(
    dag_id="belirumah_daily",
    default_args=default_args,
    description="Daily scrape of BeliRumah.co listings for Bogor",
    schedule="0 1 * * *",      # 01:00 UTC = 08:00 WIB
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["scraper", "property", "bogor"],
) as dag:

    scrape = PythonOperator(
        task_id="scrape_listings",
        python_callable=task_scrape,
    )

    load = PythonOperator(
        task_id="load_to_postgres",
        python_callable=task_load,
    )
    
    embedd = PythonOperator(
        task_id="embedd_data_using_llm",
        python_callable=task_embedding,
    )

    scrape >> load >> embedd