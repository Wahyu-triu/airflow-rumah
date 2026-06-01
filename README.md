# Diagram

belirumah-pipeline/
├── dags/
│   └── belirumah_dag.py
├── scraper/
│   ├── __init__.py
│   └── belirumah_scraper.py    ← your existing scraper (refactored into functions)
├── sql/
│   └── init.sql
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env

# Start & End Engine
docker compose up -build
docker compose down