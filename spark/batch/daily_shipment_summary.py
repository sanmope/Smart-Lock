"""
Batch job: Daily Shipment Summary

Reads from the operational PostgreSQL database, aggregates metrics per
shipment (total events, critical events, lock count, duration), and writes
the results to the Redshift warehouse.

Intended schedule: daily at 02:00 UTC (scheduling is external — e.g. Airflow).
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

TARGET_TABLE = "public.daily_shipment_summary"


def _read_table(spark, table_name):
    """Read a full table from the operational PostgreSQL database."""
    return (
        spark.read
        .jdbc(
            url=POSTGRES_JDBC_URL,
            table=table_name,
            properties=POSTGRES_PROPS,
        )
    )


def run() -> None:
    spark = get_spark_session("DailyShipmentSummary")

    # ------------------------------------------------------------------
    # 1. Load source tables from operational DB
    # ------------------------------------------------------------------
    shipments_df = _read_table(spark, "public.shipments")
    security_events_df = _read_table(spark, "public.security_events")
    lock_assignments_df = _read_table(spark, "public.lock_assignments")

    # ------------------------------------------------------------------
    # 2. Total events per shipment
    #    Join security_events -> lock_assignments -> shipments
    # ------------------------------------------------------------------
    events_with_shipment = (
        security_events_df
        .join(
            lock_assignments_df.select("lock_id", "shipment_id"),
            on="lock_id",
            how="inner",
        )
    )

    total_events = (
        events_with_shipment
        .groupBy("shipment_id")
        .agg(
            F.count("*").alias("total_events"),
            F.sum(
                F.when(F.col("severity") == "critical", 1).otherwise(0)
            ).alias("critical_events"),
        )
    )

    # ------------------------------------------------------------------
    # 3. Lock count per shipment
    # ------------------------------------------------------------------
    lock_counts = (
        lock_assignments_df
        .groupBy("shipment_id")
        .agg(
            F.countDistinct("lock_id").alias("locks_count"),
        )
    )

    # ------------------------------------------------------------------
    # 4. Shipment duration (created_at -> updated_at as proxy)
    # ------------------------------------------------------------------
    shipment_duration = (
        shipments_df
        .select("id", "shipment_id", "status", "last_update")
        .withColumnRenamed("id", "shipment_pk")
        .withColumnRenamed("shipment_id", "shipment_code")
    )

    # ------------------------------------------------------------------
    # 5. Combine everything
    # ------------------------------------------------------------------
    summary_df = (
        shipment_duration
        .join(total_events, shipment_duration["shipment_pk"] == total_events["shipment_id"], how="left")
        .drop(total_events["shipment_id"])
        .join(lock_counts, shipment_duration["shipment_pk"] == lock_counts["shipment_id"], how="left")
        .drop(lock_counts["shipment_id"])
        .withColumn(
            "total_events",
            F.coalesce(F.col("total_events"), F.lit(0)),
        )
        .withColumn(
            "critical_events",
            F.coalesce(F.col("critical_events"), F.lit(0)),
        )
        .withColumn(
            "locks_count",
            F.coalesce(F.col("locks_count"), F.lit(0)),
        )
        .withColumn("summary_date", F.current_date())
        .select(
            F.col("shipment_code").alias("shipment_id"),
            "status",
            "total_events",
            "critical_events",
            "locks_count",
            "last_update",
            "summary_date",
        )
    )

    # ------------------------------------------------------------------
    # 6. Write to Redshift (overwrite — full daily snapshot)
    # ------------------------------------------------------------------
    write_to_redshift(summary_df, TARGET_TABLE, mode="overwrite")

    row_count = summary_df.count()
    print(f"[daily_shipment_summary] Wrote {row_count} rows to {TARGET_TABLE}")

    spark.stop()


if __name__ == "__main__":
    run()
