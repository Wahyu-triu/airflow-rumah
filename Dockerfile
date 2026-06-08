FROM apache/airflow:2.9.1-python3.11

USER root
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

USER root
RUN playwright install --with-deps chromium

# Make the scraper importable inside DAGs
COPY scraper/ /opt/airflow/scraper/
COPY embedding_properties/ /opt/airflow/embedding_properties/