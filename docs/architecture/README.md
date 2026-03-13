# Data Pipeline Architecture

Architecture documentation for the Smart Lock data pipeline.

## Documents

| Document | Description |
|----------|-------------|
| [Overview](overview.md) | High-level architecture, data flow, and design decisions |
| [Kafka](kafka.md) | Topics, schemas, producer and consumer design |
| [Redshift](redshift.md) | Star schema, DDL, materialized views |
| [PySpark](pyspark.md) | Streaming and batch jobs |
| [Visualization](visualization.md) | Superset and Grafana setup |
| [Infrastructure](infrastructure.md) | Docker Compose (local) and future Kubernetes/Terraform (prod) |

## Architecture Diagram

```
Smart Lock Device
    |  (HTTPS)
    v
FastAPI (stateless) --> Kafka (Avro + Schema Registry)
                            |
                            |--> Consumer A --> PostgreSQL --> Grafana (real-time)
                            |                             --> Superset (operational)
                            |
                            '--> Consumer B: PySpark Streaming --> S3 --> Redshift
                                                                           |
                                                                           |--> Superset (analytics)
                                                                           '--> Grafana (aggregated)
```

## Design Principles

- **Event-driven**: API only writes to Kafka. A separate consumer writes to PostgreSQL.
- **Eventual consistency**: Reads have ~1-2s delay. Acceptable for IoT.
- **Horizontally scalable**: API is stateless, scales with load balancer.
- **Kafka as source of truth**: All data flows through Kafka first.
- **Star schema for analytics**: Optimized for Redshift columnar queries.
