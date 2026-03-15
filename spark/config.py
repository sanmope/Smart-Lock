"""
Spark configuration for the SmartLock IoT data pipeline.

All credentials and endpoints are read from environment variables,
falling back to the defaults defined in .env.
"""

import os
from pyspark.sql import SparkSession

# ---------------------------------------------------------------------------
# Connection constants — all from env vars
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

REDSHIFT_JDBC_URL = os.getenv(
    "REDSHIFT_JDBC_URL", "jdbc:postgresql://redshift-local:5432/smartlock_dw"
)
REDSHIFT_PROPS = {
    "user": os.getenv("REDSHIFT_USER", "redshift"),
    "password": os.getenv("REDSHIFT_PASSWORD", "redshift"),
    "driver": "org.postgresql.Driver",
}

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localstack:4566")
S3_STAGING_BUCKET = os.getenv("S3_STAGING_BUCKET", "smartlock-staging")
S3_STAGING_PATH = f"s3a://{S3_STAGING_BUCKET}"

POSTGRES_JDBC_URL = os.getenv(
    "POSTGRES_JDBC_URL", "jdbc:postgresql://postgres:5432/smartlock"
)
POSTGRES_PROPS = {
    "user": os.getenv("POSTGRES_USER", "smartlock"),
    "password": os.getenv("POSTGRES_PASSWORD", "smartlock"),
    "driver": "org.postgresql.Driver",
}


def get_spark_session(app_name: str = "SmartLockPipeline") -> SparkSession:
    """Build (or retrieve) a SparkSession pre-configured for the pipeline."""

    builder = (
        SparkSession.builder
        .appName(app_name)
        .master("spark://spark-master:7077")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
            "org.postgresql:postgresql:42.7.1",
        )
        .config("spark.hadoop.fs.s3a.endpoint", S3_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID", "test"))
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY", "test"))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.sql.streaming.checkpointLocation", "/tmp/spark-checkpoints")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.adaptive.enabled", "true")
    )

    return builder.getOrCreate()


if __name__ == "__main__":
    spark = get_spark_session("ConfigTest")
    print(f"Spark version : {spark.version}")
    print(f"Kafka bootstrap : {KAFKA_BOOTSTRAP}")
    print(f"Redshift JDBC   : {REDSHIFT_JDBC_URL}")
    print(f"Postgres JDBC   : {POSTGRES_JDBC_URL}")
    print(f"S3 staging      : {S3_STAGING_PATH}")
    spark.stop()
