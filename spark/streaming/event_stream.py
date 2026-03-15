"""
Structured Streaming job: smartlock.security.events -> fact_security_events

Reads Avro-encoded security events from Kafka, deserializes them with
fastavro (schemaless wire format — no Confluent magic byte), applies a
10-minute watermark, and writes each micro-batch to Redshift via JDBC.
"""

import io
import sys
import os
from datetime import datetime

import fastavro
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    LongType,
    StringType,
    StructField,
    StructType,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from spark.config import (
    KAFKA_BOOTSTRAP,
    REDSHIFT_JDBC_URL,
    REDSHIFT_PROPS,
    get_spark_session,
)
from spark.utils.schema_registry import get_avro_schema
from spark.utils.redshift_writer import write_to_redshift

# ---- constants ---------------------------------------------------------

KAFKA_TOPIC = "smartlock.security.events"
TARGET_TABLE = "public.fact_security_events"
CHECKPOINT = "/tmp/spark-checkpoints/event_stream"

# Spark schema for the deserialized records
_SPARK_SCHEMA = StructType([
    StructField("event_id", StringType(), nullable=False),
    StructField("lock_id", StringType(), nullable=False),
    StructField("event_type", StringType(), nullable=False),
    StructField("severity", StringType(), nullable=False),
    StructField("timestamp", LongType(), nullable=False),
])

# Load the Avro schema once (used by the deserialization helper)
_AVRO_SCHEMA = fastavro.parse_schema(
    __import__("json").loads(get_avro_schema("security_event"))
)


# ---- deserialization ---------------------------------------------------

def _deserialize_batch(binary_rows):
    """Deserialize a list of binary Avro payloads into dicts."""
    records = []
    for row in binary_rows:
        raw = bytes(row["value"])
        buf = io.BytesIO(raw)
        record = fastavro.schemaless_reader(buf, _AVRO_SCHEMA)
        # Avro enums come back as plain strings — that is fine.
        records.append(record)
    return records


# ---- foreachBatch handler ----------------------------------------------

def _write_micro_batch(batch_df: DataFrame, batch_id: int) -> None:
    """Process a single micro-batch: deserialize Avro and write to Redshift."""
    if batch_df.rdd.isEmpty():
        return

    spark: SparkSession = batch_df.sparkSession

    # Collect the binary Kafka values to the driver for fastavro decoding
    rows = batch_df.select("value").collect()
    records = _deserialize_batch(rows)

    if not records:
        return

    decoded_df = spark.createDataFrame(records, schema=_SPARK_SCHEMA)

    # Convert epoch-millis to a proper timestamp column
    result_df = (
        decoded_df
        .withColumn("event_time", (F.col("timestamp") / 1000).cast("timestamp"))
        .withColumn("date_key", F.date_format(F.col("event_time"), "yyyyMMdd").cast("int"))
        .drop("timestamp")
    )

    write_to_redshift(result_df, TARGET_TABLE, mode="append")


# ---- main --------------------------------------------------------------

def run() -> None:
    spark = get_spark_session("SecurityEventStream")

    kafka_df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # We keep the raw binary value; deserialization happens in foreachBatch.
    # Add an ingestion-time column so we can apply a watermark even before
    # decoding the Avro payload.
    stream_df = (
        kafka_df
        .selectExpr("value", "timestamp as kafka_timestamp")
        .withWatermark("kafka_timestamp", "10 minutes")
    )

    query = (
        stream_df.writeStream
        .foreachBatch(_write_micro_batch)
        .option("checkpointLocation", CHECKPOINT)
        .trigger(processingTime="30 seconds")
        .outputMode("append")
        .start()
    )

    print(f"[event_stream] Streaming from {KAFKA_TOPIC} -> {TARGET_TABLE}")
    query.awaitTermination()


if __name__ == "__main__":
    run()
