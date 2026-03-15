"""
Utility for writing Spark DataFrames to Redshift (PostgreSQL locally).

In production the Redshift COPY command (via S3 staging) would be used.
For local development we write directly over JDBC, which is functionally
equivalent for the volumes we handle during testing.
"""

from pyspark.sql import DataFrame

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from spark.config import REDSHIFT_JDBC_URL, REDSHIFT_PROPS


def write_to_redshift(
    df: DataFrame,
    table_name: str,
    mode: str = "append",
) -> None:
    """Write a Spark DataFrame to Redshift (PostgreSQL) via JDBC.

    Parameters
    ----------
    df : pyspark.sql.DataFrame
        The DataFrame to write.
    table_name : str
        Fully-qualified target table (e.g. ``public.fact_security_events``).
    mode : str, optional
        Spark write mode — ``append``, ``overwrite``, ``ignore``, or
        ``error``/``errorifexists``.  Defaults to ``append``.
    """
    (
        df.write
        .mode(mode)
        .jdbc(
            url=REDSHIFT_JDBC_URL,
            table=table_name,
            properties=REDSHIFT_PROPS,
        )
    )


if __name__ == "__main__":
    from spark.config import get_spark_session

    spark = get_spark_session("RedshiftWriterTest")

    test_data = [("test-lock-001", "active", 40.7128, -74.0060)]
    columns = ["lock_id", "status", "latitude", "longitude"]
    test_df = spark.createDataFrame(test_data, columns)

    print("Test DataFrame:")
    test_df.show()
    print("RedshiftWriter is ready. Skipping actual write in test mode.")

    spark.stop()
