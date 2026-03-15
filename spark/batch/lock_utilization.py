"""
Batch job: Lock Utilization

Reads ``lock_assignments`` from the operational PostgreSQL database and
calculates per-lock utilization metrics:

- **utilization_rate**: fraction of total observed time a lock was assigned.
- **avg_assignment_duration_hours**: mean assignment length.
- **total_assignments**: number of assignments.

Intended schedule: daily at 03:00 UTC (scheduling is external).
"""

import sys
import os

from pyspark.sql import functions as F
from pyspark.sql.window import Window

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from spark.config import (
    POSTGRES_JDBC_URL,
    POSTGRES_PROPS,
    get_spark_session,
)
from spark.utils.redshift_writer import write_to_redshift

TARGET_TABLE = "public.lock_utilization"


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
    spark = get_spark_session("LockUtilization")

    # ------------------------------------------------------------------
    # 1. Load lock_assignments
    # ------------------------------------------------------------------
    assignments_df = _read_table(spark, "public.lock_assignments")
    locks_df = _read_table(spark, "public.locks")

    # ------------------------------------------------------------------
    # 2. Calculate assignment duration
    #    assigned_at -> unassigned_at (NULL means still active -> use now())
    # ------------------------------------------------------------------
    with_duration = (
        assignments_df
        .withColumn(
            "end_time",
            F.coalesce(F.col("released_at"), F.current_timestamp()),
        )
        .withColumn(
            "assignment_duration_hours",
            (
                F.unix_timestamp(F.col("end_time"))
                - F.unix_timestamp(F.col("assigned_at"))
            ) / 3600.0,
        )
    )

    # ------------------------------------------------------------------
    # 3. Per-lock aggregation
    # ------------------------------------------------------------------
    per_lock = (
        with_duration
        .groupBy("lock_id")
        .agg(
            F.count("*").alias("total_assignments"),
            F.avg("assignment_duration_hours").alias("avg_assignment_duration_hours"),
            F.sum("assignment_duration_hours").alias("total_assigned_hours"),
            F.min("assigned_at").alias("first_assignment"),
            F.max("end_time").alias("last_observation"),
        )
    )

    # ------------------------------------------------------------------
    # 4. Utilization rate = total_assigned_hours / total_observed_hours
    # ------------------------------------------------------------------
    utilization_df = (
        per_lock
        .withColumn(
            "total_observed_hours",
            (
                F.unix_timestamp(F.col("last_observation"))
                - F.unix_timestamp(F.col("first_assignment"))
            ) / 3600.0,
        )
        .withColumn(
            "utilization_rate",
            F.when(
                F.col("total_observed_hours") > 0,
                F.least(
                    F.col("total_assigned_hours") / F.col("total_observed_hours"),
                    F.lit(1.0),
                ),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn("calculated_at", F.current_timestamp())
        .select(
            "lock_id",
            "total_assignments",
            F.round("avg_assignment_duration_hours", 2).alias(
                "avg_assignment_duration_hours"
            ),
            F.round("utilization_rate", 4).alias("utilization_rate"),
            F.round("total_assigned_hours", 2).alias("total_assigned_hours"),
            "calculated_at",
        )
    )

    # ------------------------------------------------------------------
    # 5. Write to Redshift (overwrite — daily snapshot)
    # ------------------------------------------------------------------
    write_to_redshift(utilization_df, TARGET_TABLE, mode="overwrite")

    row_count = utilization_df.count()
    print(f"[lock_utilization] Wrote {row_count} rows to {TARGET_TABLE}")

    spark.stop()


if __name__ == "__main__":
    run()
