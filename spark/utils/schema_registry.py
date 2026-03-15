"""
Avro schema helpers for the SmartLock pipeline.

Loads ``.avsc`` files from ``kafka/schemas/`` and converts them to PySpark
``StructType`` definitions so that Spark jobs can decode Avro-encoded Kafka
messages without a Confluent Schema Registry.
"""

import json
import os
from typing import Dict

from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# Path to the directory containing .avsc files
_SCHEMA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "kafka", "schemas"
)

# Mapping from schema file base-names to friendly names used by callers
_SCHEMA_FILES: Dict[str, str] = {
    "security_event": "security_event.avsc",
    "lock_status_change": "lock_status_change.avsc",
    "location_update": "location_update.avsc",
    "shipment_status_change": "shipment_status_change.avsc",
}


def get_avro_schema(name: str) -> str:
    """Return the raw JSON string of the named Avro schema.

    Parameters
    ----------
    name : str
        One of ``security_event``, ``lock_status_change``,
        ``location_update``, ``shipment_status_change``.

    Returns
    -------
    str
        The full Avro schema as a JSON string.
    """
    if name not in _SCHEMA_FILES:
        raise ValueError(
            f"Unknown schema '{name}'. "
            f"Available: {list(_SCHEMA_FILES.keys())}"
        )

    schema_path = os.path.join(_SCHEMA_DIR, _SCHEMA_FILES[name])
    with open(schema_path, "r") as fh:
        return fh.read()


# ------------------------------------------------------------------
# Manual Avro -> Spark StructType mappings
# ------------------------------------------------------------------
# Avro enum and union types have no 1-to-1 Spark equivalent, so we
# map them explicitly.  ``timestamp-millis`` logical types are kept
# as ``LongType`` here; downstream jobs cast to ``TimestampType``
# after converting epoch-millis to seconds.
# ------------------------------------------------------------------

_SPARK_SCHEMAS: Dict[str, StructType] = {
    "security_event": StructType([
        StructField("event_id", StringType(), nullable=False),
        StructField("lock_id", StringType(), nullable=False),
        StructField("event_type", StringType(), nullable=False),
        StructField("severity", StringType(), nullable=False),
        StructField("timestamp", LongType(), nullable=False),
    ]),
    "lock_status_change": StructType([
        StructField("lock_id", StringType(), nullable=False),
        StructField("action", StringType(), nullable=False),
        StructField("status", StringType(), nullable=True),
        StructField("previous_status", StringType(), nullable=True),
        StructField("latitude", DoubleType(), nullable=True),
        StructField("longitude", DoubleType(), nullable=True),
        StructField("shipment_id", StringType(), nullable=True),
        StructField("timestamp", LongType(), nullable=False),
    ]),
    "location_update": StructType([
        StructField("lock_id", StringType(), nullable=False),
        StructField("latitude", DoubleType(), nullable=False),
        StructField("longitude", DoubleType(), nullable=False),
        StructField("timestamp", LongType(), nullable=False),
    ]),
    "shipment_status_change": StructType([
        StructField("shipment_id", StringType(), nullable=False),
        StructField("action", StringType(), nullable=False),
        StructField("status", StringType(), nullable=False),
        StructField("previous_status", StringType(), nullable=True),
        StructField("timestamp", LongType(), nullable=False),
    ]),
}


def avro_to_spark_schema(avro_schema_str: str) -> StructType:
    """Convert an Avro schema JSON string to the corresponding Spark StructType.

    The mapping is done by matching the Avro schema ``name`` field against
    the pre-defined PySpark schemas.  A ``ValueError`` is raised when the
    schema name is not recognised.

    Parameters
    ----------
    avro_schema_str : str
        Raw JSON string of the Avro schema (as returned by
        :func:`get_avro_schema`).

    Returns
    -------
    pyspark.sql.types.StructType
    """
    schema_dict = json.loads(avro_schema_str)
    record_name = schema_dict.get("name", "")

    # Map Avro record name -> our friendly key
    _name_map = {
        "SecurityEvent": "security_event",
        "LockStatusChange": "lock_status_change",
        "LocationUpdate": "location_update",
        "ShipmentStatusChange": "shipment_status_change",
    }

    friendly = _name_map.get(record_name)
    if friendly is None:
        raise ValueError(
            f"No Spark schema mapping for Avro record '{record_name}'. "
            f"Known records: {list(_name_map.keys())}"
        )

    return _SPARK_SCHEMAS[friendly]


def get_spark_schema(name: str) -> StructType:
    """Shortcut: return the Spark StructType for a named schema directly.

    Parameters
    ----------
    name : str
        One of ``security_event``, ``lock_status_change``,
        ``location_update``, ``shipment_status_change``.
    """
    if name not in _SPARK_SCHEMAS:
        raise ValueError(
            f"Unknown schema '{name}'. "
            f"Available: {list(_SPARK_SCHEMAS.keys())}"
        )
    return _SPARK_SCHEMAS[name]


if __name__ == "__main__":
    for schema_name in _SCHEMA_FILES:
        avro_json = get_avro_schema(schema_name)
        spark_schema = avro_to_spark_schema(avro_json)
        print(f"\n--- {schema_name} ---")
        print(f"Avro (first 80 chars): {avro_json[:80]}...")
        print(f"Spark StructType     : {spark_schema.simpleString()}")
