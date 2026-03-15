from dataclasses import dataclass


@dataclass
class SimulatorConfig:
    """Configuration for the smart lock traffic simulator."""

    num_locks: int = 1000
    num_shipments: int = 50
    duration: int = 3600  # seconds of virtual time
    acceleration: float = 1.0  # time multiplier (10x = 1h in 6min)
    output_mode: str = "api"  # api | kafka | json
    api_base_url: str = "http://localhost:8000"
    kafka_bootstrap: str = "localhost:9092"
    json_dir: str = "./test_data"
    location_interval: float = 6.0  # virtual seconds between location updates per lock
    status_interval: float = 600.0  # virtual seconds between status change checks
    event_probability: float = 0.005  # chance per tick of a normal event per lock
    incident_probability: float = 0.001  # chance per tick of an incident per lock
    late_event_ratio: float = 0.05  # 5% of events get delayed timestamps
