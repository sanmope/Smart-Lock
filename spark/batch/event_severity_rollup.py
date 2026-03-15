"""
Batch job: Event Severity Rollup

Reads ``security_events`` from the operational PostgreSQL database and
computes hourly counts grouped by ``event_type`` and ``severity``.

Intended schedule: every hour (scheduling is external).
"""

import sys
import os

from pyspark.sql import functions as F

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from spark.config import (
    POSTGRES_JDBC_URL,
    POSTGRES_PROPS,
    get_spark_session,
)
from spark.utils.redshift_writer import write_to_redshift

TARGET_TABLE = "public.event_severity_rollup"


def _read_table(spark, table_name):
    return (
        spark.read
        .jdbc(
            url=POSTGRES_JDBC_URL,
            table=table_name,
            properties=POSTGRES_PROPS,
        )
    )


def run() -> None:
    spark = get_spark_session("EventSeverityRollup")

    # ------------------------------------------------------------------
    # 1. Load security events
    # ------------------------------------------------------------------
    events_df = _read_table(spark, "public.security_events")

    # ------------------------------------------------------------------
    # 2. Truncate created_at to the hour
    # ------------------------------------------------------------------
    with_hour = events_df.withColumn(
        "event_hour",
        F.date_trunc("hour", F.col("event_time")),
    )

    # ------------------------------------------------------------------
    # 3. Aggregate: hourly counts by event_type and severity
    # ------------------------------------------------------------------
    rollup_df = (
        with_hour
        .groupBy("event_hour", "event_type", "severity")
        .agg(
            F.count("*").alias("event_count"),
        )
        .withColumn(
            "date_key",
            F.date_format(F.col("event_hour"), "yyyyMMdd").cast("int"),
        )
        .withColumn("calculated_at", F.current_timestamp())
        .select(
            "event_hour",
            "event_type",
            "severity",
            "event_count",
            "date_key",
            "calculated_at",
        )
        .orderBy("event_hour", "event_type", "severity")
    )

    # ------------------------------------------------------------------
    # 4. Write to Redshift (overwrite — full hourly snapshot)
    # ------------------------------------------------------------------
    write_to_redshift(rollup_df, TARGET_TABLE, mode="overwrite")

    row_count = rollup_df.count()
    print(f"[event_severity_rollup] Wrote {row_count} rows to {TARGET_TABLE}")

    spark.stop()


if __name__ == "__main__":
    run()
