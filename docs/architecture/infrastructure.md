# Infrastructure

## Local Development (Docker Compose)

All services run locally via `docker-compose.yml`.

### Services

| Service | Image | Port | Role |
|---------|-------|------|------|
| `kafka` | `confluentinc/cp-kafka:7.6.0` (KRaft) | 9092 | Message broker |
| `schema-registry` | `confluentinc/cp-schema-registry:7.6.0` | 8081 | Avro schema registry |
| `kafka-ui` | `provectuslabs/kafka-ui` | 8080 | Visual topic/message inspection |
| `postgres` | `postgres:16` | 5432 | Operational database |
| `api` | Build `Dockerfile.api` | 8000 | FastAPI (stateless, Kafka producer) |
| `consumer` | Build `Dockerfile.consumer` | — | Kafka consumer -> PostgreSQL |
| `spark-master` | `bitnami/spark:3.5` | 8082, 7077 | Spark standalone master |
| `spark-worker` | `bitnami/spark:3.5` | 8083 | Spark worker |
| `redshift-local` | `postgres:16` | 5439 | Local Redshift substitute |
| `localstack` | `localstack/localstack:3.0` | 4566 | S3 emulation for Spark staging |
| `superset` | `apache/superset:3.1.0` | 8088 | Analytics dashboards |
| `grafana` | `grafana/grafana:10.3.0` | 3000 | Real-time monitoring + alerts |

### Design Notes

**KRaft mode (no Zookeeper)**: Kafka runs in KRaft mode, eliminating the Zookeeper dependency. This is production-ready since Kafka 3.5+ and simplifies the local stack.

**Two PostgreSQL instances**: One for the operational database (port 5432), one as a local Redshift substitute (port 5439). Redshift is PostgreSQL wire-compatible, so the same drivers and SQL work.

**LocalStack for S3**: PySpark writes Parquet to S3 before Redshift COPY. LocalStack emulates S3 locally at port 4566.

**Redshift limitations locally**: DISTKEY, SORTKEY, and DISTSTYLE are Redshift-specific syntax and won't work on PostgreSQL. DDL scripts should have a local mode that strips these clauses.

### Port Map

```
http://localhost:8000   -> FastAPI (API docs at /docs)
http://localhost:8080   -> Kafka UI (topic inspection)
http://localhost:8081   -> Schema Registry API
http://localhost:8082   -> Spark Master UI
http://localhost:8088   -> Superset (dashboards)
http://localhost:3000   -> Grafana (monitoring)
http://localhost:4566   -> LocalStack (S3 API)
localhost:5432          -> PostgreSQL (operational)
localhost:5439          -> PostgreSQL (Redshift substitute)
localhost:9092          -> Kafka broker
```

### Environment Variables

```yaml
# API
KAFKA_BOOTSTRAP_SERVERS: kafka:9092
SCHEMA_REGISTRY_URL: http://schema-registry:8081

# Consumer
KAFKA_BOOTSTRAP_SERVERS: kafka:9092
SCHEMA_REGISTRY_URL: http://schema-registry:8081
DATABASE_URL: postgresql://smartlock:smartlock@postgres:5432/smartlock

# Spark
KAFKA_BOOTSTRAP_SERVERS: kafka:9092
SCHEMA_REGISTRY_URL: http://schema-registry:8081
REDSHIFT_JDBC_URL: jdbc:postgresql://redshift-local:5439/smartlock_dw
S3_ENDPOINT: http://localstack:4566
S3_TEMP_DIR: s3://smartlock-staging/temp/

# Superset
SUPERSET_SECRET_KEY: local-dev-secret-key

# Grafana
GF_SECURITY_ADMIN_PASSWORD: admin
```

### Starting the Stack

```bash
# Start all services
docker compose up -d

# Verify Kafka is ready
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Create topics (if not auto-created)
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --topic smartlock.security.events --partitions 12 --replication-factor 1

# Check API
curl http://localhost:8000/docs

# Check Kafka UI
open http://localhost:8080

# Check Superset
open http://localhost:8088

# Check Grafana
open http://localhost:3000
```

### Dockerfiles

**Dockerfile.api** (FastAPI producer):
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py schemas.py kafka/ ./
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dockerfile.consumer** (Kafka consumer -> PostgreSQL):
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements-consumer.txt .
RUN pip install --no-cache-dir -r requirements-consumer.txt
COPY kafka/ db_models.py database.py schemas.py ./
CMD ["python", "consumer.py"]
```

**Dockerfile.spark** (PySpark jobs):
```dockerfile
FROM bitnami/spark:3.5
COPY requirements-spark.txt .
RUN pip install --no-cache-dir -r requirements-spark.txt
COPY spark/ ./spark/
```

## Verification Checklist

1. **Kafka**: `docker compose up` -> hit API endpoints -> verify messages in Kafka UI (localhost:8080)
2. **Consumer**: Produce events -> verify they appear in PostgreSQL within ~1-2s
3. **API reads**: `POST /locks` -> wait 2s -> `GET /locks/{id}` returns the lock
4. **Streaming**: Produce events -> verify they appear in Redshift fact tables within ~30s
5. **Batch**: Run batch jobs -> verify aggregation tables
6. **Superset**: Connect to Redshift -> create chart -> verify data
7. **Grafana**: Connect to PostgreSQL -> verify real-time lock status dashboard
8. **Alerts**: Produce `TAMPER_DETECTED` event -> verify Grafana fires alert
9. **Scaling test**: Start 3 API instances -> produce from all 3 -> verify consistency in PostgreSQL

---

## Future: Production (Kubernetes + Terraform + AWS)

Out of scope for the current phase. To be implemented later.

### Kubernetes

Migrate from Docker Compose to K8s manifests with Kustomize (local/prod overlays).

**Stateless (Deployment + HPA)**: api, consumer, spark-workers, superset, grafana
- API with HPA: auto-scales based on CPU/request metrics

**Stateful (StatefulSet)**: kafka, postgres, spark-master
- Or better: migrate to managed services (see below)

### Terraform (AWS Infrastructure)

| Resource | AWS Service | Replaces |
|----------|------------|----------|
| Kubernetes cluster | EKS | Local Docker |
| Kafka | MSK (Managed Streaming for Kafka) | Kafka container |
| PostgreSQL | RDS | PostgreSQL container |
| Data warehouse | Redshift | PostgreSQL on port 5439 |
| Object storage | S3 | LocalStack |

### Target Structure

```
k8s/
|-- base/                    # Base manifests (kustomize)
|   |-- api/                 # Deployment + HPA + Service
|   |-- consumer/            # Deployment + ConfigMap
|   |-- kafka/               # StatefulSet (local only)
|   |-- postgres/            # StatefulSet (local only)
|   |-- spark/               # Master StatefulSet + Worker Deployment
|   |-- superset/            # Deployment + Service
|   |-- grafana/             # Deployment + Service + ConfigMap
|   '-- ingress.yaml         # External routing
|-- overlays/
|   |-- local/               # minikube: 1 replica, no HPA, everything in-cluster
|   '-- prod/                # EKS: HPA, external managed services
|
terraform/
|-- eks.tf
|-- msk.tf
|-- rds.tf
|-- redshift.tf
|-- s3.tf
'-- variables.tf
```
