# ---------------------------------------------------------------------------
# dht_probe.py
# 2026-10-02
# - Bounded DHT22 test with explicit BCM pin selection; no CNC access.
# ---------------------------------------------------------------------------
"""Read a 3.3 V DHT22; emit JSON and release GPIO on completion."""

import argparse
import json
import time
from datetime import datetime, timezone


def main():
    """Attempt ten reads and require three successful sensor responses."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpio", type=int, default=17)
    arguments = parser.parse_args()
    if not 0 <= arguments.gpio <= 27:
        parser.error("--gpio must be a BCM GPIO number from 0 to 27")

    # Import hardware libraries only after validating command-line arguments.
    import adafruit_dht
    import board

    pin = getattr(board, f"D{arguments.gpio}")
    sensor = adafruit_dht.DHT22(pin, use_pulseio=False)
    successful_reads = 0
    try:
        for attempt in range(1, 11):
            try:
                temperature = sensor.temperature
                humidity = sensor.humidity
                if temperature is None or humidity is None:
                    raise RuntimeError("No measurement returned")
                if not -40 <= temperature <= 80 or not 0 <= humidity <= 100:
                    raise RuntimeError("Measurement outside sensor range")
                successful_reads += 1
                result = {
                    "status": "ok",
                    "temperature_c": temperature,
                    "humidity_percent": humidity,
                }
            except RuntimeError as error:
                result = {"status": "error", "error": str(error)}
            result["attempt"] = attempt
            result["gpio"] = arguments.gpio
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            print(json.dumps(result), flush=True)
            if successful_reads >= 3:
                break
            # DHT22 needs at least two seconds between fresh measurements.
            if attempt < 10:
                time.sleep(2.5)
    finally:
        sensor.exit()
    return 0 if successful_reads >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
