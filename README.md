# Historical Ads Backend API

FastAPI backend for searching and analyzing historical job listings from the Swedish Public Employment Service (Arbetsförmedlingen).

## API Endpoints

| Endpoint                 | Metod | Beskrivning                                            |
| ------------------------ | ----- | ------------------------------------------------------ |
| `/api/v1/search`         | GET   | Search historical job listings                         |
| `/api/v1/search/ad/{id}` | GET   | Retrieve a specific listing                            |
| `/api/v1/stats`          | GET   | Get statistics                                         |
| `/api/v1/filters`        | GET   | Retrieve filter options                                |
| `/api/v1/export`         | GET   | Export data (JSON/CSV/XLSX)                            |
| `/api/v1/export/bulk`    | GET   | Export matching ads as a ZIP file with split CSV parts |
| `/health`                | GET   | Health check                                           |

## Getting Started

```bash
# # Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
```

## Docker

```bash
# Start the API using Docker Compose
docker compose up --build

# Access the API at http://localhost:5000

# Stop the server
docker compose down
```


## API Documentation

- **Swagger UI**: http://localhost:5000/docs
- **ReDoc**: http://localhost:5000/redoc
