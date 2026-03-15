"""
Structured Streaming job: smartlock.lock.location-updates -> fact_location_updates

Reads Avro-encoded location updates from Kafka, deserializes with fastavro,
applies a 5-minute watermark, and writes each micro-batch to Redshift via JDBC.
"""

import io
import json
import sys
import os

import fastavro
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from spark.config import (
    KAFKA_BOOTSTRAP,
    get_spark_session,
)
from spark.utils.schema_registry import get_avro_schema
from spark.utils.redshift_writer import write_to_redshift

# ---- constants ---------------------------------------------------------

KAFKA_TOPIC = "smartlock.lock.location-updates"
TARGET_TABLE = "public.fact_location_updates"
CHECKPOINT = "/tmp/spark-checkpoints/location_stream"

_SPARK_SCHEMA = StructType([
    StructField("lock_id", StringType(), nullable=False),
    StructField("latitude", DoubleType(), nullable=False),
    StructField("longitude", DoubleType(), nullable=False),
    StructField("timestamp", LongType(), nullable=False),
])

_AVRO_SCHEMA = fastavro.parse_schema(
    json.loads(get_avro_schema("location_update"))
)


# ---- deserialization ---------------------------------------------------

def _deserialize_batch(binary_rows):
    """Deserialize a list of binary Avro payloads into dicts."""
    records = []
    for row in binary_rows:
        raw = bytes(row["value"])
        buf = io.BytesIO(raw)
        record = fastavro.schemaless_reader(buf, _AVRO_SCHEMA)
        records.append(record)
    return records


# ---- foreachBatch handler ----------------------------------------------

def _write_micro_batch(batch_df: DataFrame, batch_id: int) -> None:
    """Process a single micro-batch: deserialize Avro and write to Redshift."""
    if batch_df.rdd.isEmpty():
        return

    spark: SparkSession = batch_df.sparkSession

    rows = batch_df.select("value").collect()
    records = _deserialize_batch(rows)

    if not records:
        return

    decoded_df = spark.createDataFrame(records, schema=_SPARK_SCHEMA)

    result_df = (
        decoded_df
        .withColumn(
            "update_time",
            (F.col("timestamp") / 1000).cast("timestamp"),
        )
        .withColumn(
            "date_key",
            F.date_format(F.col("update_time"), "yyyyMMdd").cast("int"),
        )
        .drop("timestamp")
    )

    write_to_redshift(result_df, TARGET_TABLE, mode="append")


# ---- main --------------------------------------------------------------

def run() -> None:
    spark = get_spark_session("LocationStream")

    kafka_df = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    stream_df = (
        kafka_df
        .selectExpr("value", "timestamp as kafka_timestamp")
        .withWatermark("kafka_timestamp", "5 minutes")
    )

    query = (
        stream_df.writeStream
        .foreachBatch(_write_micro_batch)
        .option("checkpointLocation", CHECKPOINT)
        .trigger(processingTime="60 seconds")
        .outputMode("append")
        .start()
    )

    print(f"[location_stream] Streaming from {KAFKA_TOPIC} -> {TARGET_TABLE}")
    query.awaitTermination()


if __name__ == "__main__":
    run()
