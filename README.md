# Smart Lock Manager

REST API for managing smart lock state during shipments. Smart locks report their status in real time, allowing monitoring of individual devices and overall shipment health throughout the delivery journey.

## Overview

Smart locks communicate directly with this API to register themselves, report their state, and signal when they've been released at the destination or when an incident occurs. The system aggregates individual lock statuses to provide a unified health assessment for each shipment.

## Features

- **Lock registration** – Smart locks self-register when assigned to a shipment
- **State reporting** – Locks continuously send status updates (location, battery, tamper alerts)
- **Criticality levels** – Each lock reports a criticality level based on detected events
- **Release detection** – Tracks when a lock is released at the destination
- **Event logging** – Logs anomalies or security events during transit
- **Shipment health** – Aggregates all lock statuses to determine the overall state of a shipment

## Tech Stack

- **Python 3.12**
- **FastAPI** – REST API framework
- **SQLAlchemy** – ORM and database models
- **PostgreSQL** – Production database
- **SQLite** – Development database
- **Pydantic** – Data validation and schemas

## Project Structure

```
smart_lock/
├── main.py           # FastAPI app and route definitions
├── db_models.py      # SQLAlchemy models
├── schemas.py        # Pydantic schemas
├── database.py       # Database connection and session
└── CONTEXT.md        # Project context and design notes
```

## Getting Started

### Prerequisites

- Python 3.12+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/sanmope/Smart-Lock.git
cd Smart-Lock

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload
```

API available at `http://localhost:8000`  
Interactive docs at `http://localhost:8000/docs`

## API Endpoints

### Locks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/locks` | Create a new smart lock |
| GET | `/locks/{lock_id}` | Get lock details |
| PATCH | `/locks/{lock_id}/status` | Update lock status |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events` | Create a new event |
| GET | `/events` | List all events |

### Shipments

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/shipments` | Create a new shipment |
| POST | `/shipments/{shipment_id}/locks/{lock_id}` | Assign a lock to a shipment |
| PATCH | `/shipments/{shipment_id}/locks/{lock_id}/release` | Release a lock from a shipment |
| GET | `/shipments/{shipment_id}/health` | Get aggregated health status of a shipment |

## Architecture

See [docs/architecture/](docs/architecture/) for the full data pipeline architecture documentation:

- [Overview](docs/architecture/overview.md) — End-to-end architecture, design decisions, project structure
- [Kafka](docs/architecture/kafka.md) — Topics, Avro schemas, producer and consumer design
- [Redshift](docs/architecture/redshift.md) — Star schema, DDL, materialized views
- [PySpark](docs/architecture/pyspark.md) — Streaming and batch processing jobs
- [Visualization](docs/architecture/visualization.md) — Superset (analytics) + Grafana (monitoring/alerts)
- [Infrastructure](docs/architecture/infrastructure.md) — Docker Compose (local) and future K8s/Terraform (prod)

## Roadmap

- [ ] Docker Compose setup (Kafka, PostgreSQL, Schema Registry, Spark, Superset, Grafana)
- [ ] Kafka producers in FastAPI (event-driven architecture)
- [ ] Kafka consumer -> PostgreSQL
- [ ] Redshift star schema (dimensions, facts, materialized views)
- [ ] PySpark streaming jobs (Kafka -> Redshift)
- [ ] PySpark batch jobs (daily/hourly aggregations)
- [ ] Superset + Grafana dashboards and alerts
- [ ] Kubernetes deployment manifests
- [ ] Authentication for lock devices (API keys / JWT)
- [ ] CI/CD pipeline with GitHub Actions
- [ ] AWS deployment with Terraform (EKS, MSK, RDS, Redshift, S3)

## License

MIT