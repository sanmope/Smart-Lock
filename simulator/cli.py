import argparse
import asyncio
import logging
import sys

from simulator.config import SimulatorConfig
from simulator.fleet import Fleet
from simulator.outputs.base import OutputBase


def _build_output(config: SimulatorConfig) -> OutputBase:
    """Instantiate the appropriate output backend based on config."""
    if config.output_mode == "api":
        from simulator.outputs.api_output import ApiOutput
        return ApiOutput(base_url=config.api_base_url)
    elif config.output_mode == "kafka":
        from simulator.outputs.kafka_output import KafkaOutput
        return KafkaOutput(bootstrap_servers=config.kafka_bootstrap)
    elif config.output_mode == "json":
        from simulator.outputs.json_output import JsonOutput
        return JsonOutput(output_dir=config.json_dir)
    else:
        raise ValueError(f"Unknown output mode: {config.output_mode!r}")


async def _run(config: SimulatorConfig) -> None:
    """Set up and run the simulation."""
    output = _build_output(config)
    fleet = Fleet(config, output)

    try:
        await output.setup()
        await fleet.setup()
        await fleet.run()
    finally:
        await output.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="simulator",
        description="Smart Lock IoT traffic simulator",
    )
    parser.add_argument(
        "--locks", type=int, default=1000,
        help="Number of locks to simulate (default: 1000)",
    )
    parser.add_argument(
        "--shipments", type=int, default=50,
        help="Number of shipments (default: 50)",
    )
    parser.add_argument(
        "--output", choices=["api", "kafka", "json"], default="api",
        help="Output mode (default: api)",
    )
    parser.add_argument(
        "--duration", type=int, default=3600,
        help="Virtual duration in seconds (default: 3600)",
    )
    parser.add_argument(
        "--acceleration", type=float, default=1.0,
        help="Time acceleration factor (default: 1.0; 10 = 1h in 6min)",
    )
    parser.add_argument(
        "--api-url", type=str, default="http://localhost:8000",
        help="Base URL for the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--kafka-bootstrap", type=str, default="localhost:9092",
        help="Kafka bootstrap servers (default: localhost:9092)",
    )
    parser.add_argument(
        "--json-dir", type=str, default="./test_data",
        help="Output directory for JSON mode (default: ./test_data)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

    config = SimulatorConfig(
        num_locks=args.locks,
        num_shipments=args.shipments,
        duration=args.duration,
        acceleration=args.acceleration,
        output_mode=args.output,
        api_base_url=args.api_url,
        kafka_bootstrap=args.kafka_bootstrap,
        json_dir=args.json_dir,
    )

    logging.getLogger("simulator").info(
        "Config: locks=%d shipments=%d duration=%ds accel=%.1fx output=%s",
        config.num_locks, config.num_shipments, config.duration,
        config.acceleration, config.output_mode,
    )

    asyncio.run(_run(config))


if __name__ == "__main__":
    main()
