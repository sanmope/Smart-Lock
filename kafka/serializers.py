import io
import json
import os
import fastavro


_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")
_PARSED_SCHEMAS = {}


def _get_parsed_schema(name: str):
    if name not in _PARSED_SCHEMAS:
        path = os.path.join(_SCHEMA_DIR, f"{name}.avsc")
        with open(path) as f:
            raw = json.load(f)
        _PARSED_SCHEMAS[name] = fastavro.parse_schema(raw)
    return _PARSED_SCHEMAS[name]


class AvroSerializer:
    def __init__(self, schema_name: str):
        self._schema = _get_parsed_schema(schema_name)

    def serialize(self, data: dict) -> bytes:
        buf = io.BytesIO()
        fastavro.schemaless_writer(buf, self._schema, data)
        return buf.getvalue()


class AvroDeserializer:
    def __init__(self, schema_name: str):
        self._schema = _get_parsed_schema(schema_name)

    def deserialize(self, data: bytes) -> dict:
        buf = io.BytesIO(data)
        return fastavro.schemaless_reader(buf, self._schema)
