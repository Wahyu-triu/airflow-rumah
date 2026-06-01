# Pipeline Diagram

```mermaid
graph TD
    A[belirumah-pipeline/] --> B[dags/]
    A --> C[scraper/]
    A --> D[sql/]
    A --> E[docker-compose.yml]
    A --> F[Dockerfile]
    A --> G[requirements.txt]
    A --> H[.env]

    B --> B1[belirumah_dag.py]
    C --> C1[__init__.py]
    C --> C2[belirumah_scraper.py]
    D --> D1[init.sql]
```

## Project structure

- `dags/`
  - `belirumah_dag.py`
- `scraper/`
  - `__init__.py`
  - `belirumah_scraper.py` — your existing scraper refactored into functions
- `sql/`
  - `init.sql`
- `docker-compose.yml`
- `Dockerfile`
- `requirements.txt`
- `.env`

## Start & stop

```bash
docker compose up --build
docker compose down
```