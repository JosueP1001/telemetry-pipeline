"""Device simulator with fault injection.

Modes:
  normal     - well-formed readings with consecutive sequence numbers
  drop       - skips every Nth sequence number (simulates lost packets)
  malformed  - sends garbage/invalid data every Nth message
  silent     - sends `count` readings, then holds the connection open and stays quiet
"""
from __future__ import annotations

import argparse
import logging
import random
import socket
import time

from . import protocol
from .logging_setup import get_logger, log

logger = get_logger("simulator")
MODES = ("normal", "drop", "malformed", "silent")


def make_reading(device_id: str, seq: int, rng: random.Random) -> dict:
    temp = round(rng.gauss(40.0, 3.0), 2)
    status = "OK" if temp < 48 else "WARN"
    return {"device_id": device_id, "seq": seq, "ts": time.time(),
            "temperature_c": temp, "status": status}


def run_simulator(host: str, port: int, device_id: str = "dev-001", count: int = 20,
                  interval: float = 0.05, mode: str = "normal", every: int = 5,
                  hold: float = 0.0, seed: int | None = None) -> int:
    """Send `count` messages. Returns how many lines were written to the socket."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    rng = random.Random(seed)
    sent = 0
    with socket.create_connection((host, port), timeout=5) as sock:
        for seq in range(count):
            if mode == "drop" and seq > 0 and seq % every == 0:
                continue  # sequence number consumed but never sent
            if mode == "malformed" and seq > 0 and seq % every == 0:
                sock.sendall(b"{this is not valid json\n")
            else:
                sock.sendall(protocol.encode(make_reading(device_id, seq, rng)))
            sent += 1
            time.sleep(interval)
        if mode == "silent" and hold > 0:
            log(logger, logging.INFO, "going_silent", hold_s=hold)
            time.sleep(hold)
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description="Telemetry device simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--device-id", default="dev-001")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--mode", choices=MODES, default="normal")
    parser.add_argument("--every", type=int, default=5)
    parser.add_argument("--hold", type=float, default=10.0)
    args = parser.parse_args()
    # Retry briefly so `docker compose up` works even if the collector is still starting.
    for attempt in range(10):
        try:
            sent = run_simulator(args.host, args.port, args.device_id, args.count,
                                 args.interval, args.mode, args.every, args.hold)
            log(logger, logging.INFO, "simulator_done", sent=sent, mode=args.mode)
            return
        except ConnectionRefusedError:
            log(logger, logging.WARNING, "collector_not_ready", attempt=attempt + 1)
            time.sleep(1)


if __name__ == "__main__":
    main()
