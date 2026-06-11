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

# LOCATION = "Bekasi"
# PAGES    = 20      # how many listing pages per daily run

DB_CONN  = os.environ["PROPERTY_DB_CONN"]   # set in .env
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

CITIES = ["bogor", "bekasi", "jakarta", "depok"]
PAGES_PER_RUN = 5

default_args = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# ── Task functions ─────────────────────────────────────────────────────────
def task_scrape(city, pages, **context):
    """Scrape listings and push raw data to XCom."""
    listings = scrape_belirumah(location=city, pages=pages)
    logger.info("Scraped %d listings.", len(listings))
    context["ti"].xcom_push(key=f"listings_{city}", value=listings)

def task_load_all(**context):
    """
        Pull listings from ALL city scrape tasks, merge, then upsert into Postgres.
        Runs once after every city scraper has finished.
    """
    ti = context["ti"]
    all_listings = []
    for city in CITIES:
        listings = ti.xcom_pull(
            key=f"listings_{city}",
            task_ids=f"scrape_property_data_{city}",
        )
        if listings:
            logger.info(f"Pulled listings from {city}")
            all_listings.extend(listings)
        else:
            logger.warning("No listings returned for %s.", city)

    if not all_listings:
        logger.warning("Nothing to load across all cities.")
        return
    
    print(f'Total listing collected: {len(all_listings)}')

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
            cur.executemany(insert_sql, all_listings)
            logger.info("Upserted %d rows.", cur.rowcount)
    finally:
        conn.close()

    # Push merged listings downstream for the embed task
    logger.info("Push all_listings to XCom")
    ti.xcom_push(key="all_listings", value=all_listings)

def task_embed_all(**context):
    """Pull listings from XCom, Embedd using embedding model upsert into Postgres."""
    listings = context["ti"].xcom_pull(
        key="all_listings",
        task_ids="load_to_postgres",
    )
    if not listings:
        logger.warning("No listings to load.")
        return
    
    ingest_embedding_dag(
        openai_key=OPENAI_KEY, 
        properties=listings
    )
    logger.info("Embedded %d listings.", len(listings))

# ── DAG definition ─────────────────────────────────────────────────────────
with DAG(
    dag_id="belirumah_daily",
    default_args=default_args,
    description="Daily scrape of BeliRumah.co",
    schedule="0 1 * * *",      # 01:00 UTC = 08:00 WIB
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["scraper", "property"],
) as dag:
    
    # One shared load task
    load = PythonOperator(
        task_id="load_to_postgres",
        python_callable=task_load_all,
    )
    
    # One shared embed task
    embed = PythonOperator(
        task_id="embed_data_using_llm",
        python_callable=task_embed_all,
    )

    for city in CITIES:
        scrape = PythonOperator(
            task_id=f"scrape_property_data_{city}",
            python_callable=task_scrape,
            op_kwargs={
                "city" : city,
                "pages"  : PAGES_PER_RUN
            }
        )

        scrape >> load
    load >> embed