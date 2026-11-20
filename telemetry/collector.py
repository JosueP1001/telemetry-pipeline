"""Collector service.

- Listens on a TCP port for newline-delimited JSON telemetry.
- Validates each message, detects sequence gaps, stores good data in SQLite.
- Closes connections from devices that go silent (device timeout).
- Exposes /health and /metrics (Prometheus text format) over HTTP.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3

from . import protocol
from .logging_setup import get_logger, log

logger = get_logger("collector")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    temperature_c REAL NOT NULL,
    status TEXT NOT NULL
)
"""


class Collector:
    def __init__(self, host="0.0.0.0", port=9000, metrics_port=8080,
                 db_path="telemetry.db", device_timeout=5.0):
        self.host, self.port, self.metrics_port = host, port, metrics_port
        self.db_path, self.device_timeout = db_path, device_timeout
        self.metrics = {
            "connections_total": 0,
            "messages_received_total": 0,
            "messages_invalid_total": 0,
            "sequence_gaps_total": 0,
            "device_timeouts_total": 0,
        }
        self._last_seq: dict[str, int] = {}
        self._server = None
        self._metrics_server = None
        self._db = None

    async def start(self) -> None:
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.execute(SCHEMA)
        self._db.commit()
        self._server = await asyncio.start_server(self._handle_device, self.host, self.port)
        self._metrics_server = await asyncio.start_server(
            self._handle_http, self.host, self.metrics_port)
        # Resolve real ports (useful when started with port 0 in tests).
        self.port = self._server.sockets[0].getsockname()[1]
        self.metrics_port = self._metrics_server.sockets[0].getsockname()[1]
        log(logger, logging.INFO, "collector_started", port=self.port,
            metrics_port=self.metrics_port, device_timeout=self.device_timeout)

    async def stop(self) -> None:
        for server in (self._server, self._metrics_server):
            if server:
                server.close()
                await server.wait_closed()
        if self._db:
            self._db.close()
        log(logger, logging.INFO, "collector_stopped")

    # ---- device connections -------------------------------------------------
    async def _handle_device(self, reader, writer) -> None:
        peer = writer.get_extra_info("peername")
        self.metrics["connections_total"] += 1
        log(logger, logging.INFO, "device_connected", peer=str(peer))
        try:
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), self.device_timeout)
                except asyncio.TimeoutError:
                    self.metrics["device_timeouts_total"] += 1
                    log(logger, logging.WARNING, "device_timeout", peer=str(peer),
                        timeout_s=self.device_timeout)
                    break
                if not line:  # clean EOF
                    break
                self._process_line(line)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            log(logger, logging.WARNING, "connection_reset", peer=str(peer))
        finally:
            writer.close()
            log(logger, logging.INFO, "device_disconnected", peer=str(peer))

    def _process_line(self, line: bytes) -> None:
        try:
            msg = protocol.parse(line)
            error = protocol.validate(msg)
        except ValueError as exc:
            error = str(exc)
            msg = None
        if error:
            self.metrics["messages_invalid_total"] += 1
            log(logger, logging.WARNING, "invalid_message", reason=error)
            return

        device, seq = msg["device_id"], msg["seq"]
        last = self._last_seq.get(device)
        if last is not None and seq > last + 1:
            missing = seq - last - 1
            self.metrics["sequence_gaps_total"] += missing
            log(logger, logging.WARNING, "sequence_gap", device_id=device, missing=missing,
                expected=last + 1, got=seq)
        self._last_seq[device] = max(seq, last if last is not None else seq)

        self._db.execute(
            "INSERT INTO readings (device_id, seq, ts, temperature_c, status) VALUES (?,?,?,?,?)",
            (device, seq, msg["ts"], msg["temperature_c"], msg["status"]))
        self._db.commit()
        self.metrics["messages_received_total"] += 1
        if msg["status"] == "FAULT":
            log(logger, logging.ERROR, "device_fault_reported", device_id=device, seq=seq)

    def count_rows(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    # ---- HTTP health/metrics ---------------------------------------------------
    async def _handle_http(self, reader, writer) -> None:
        try:
            request = (await asyncio.wait_for(reader.readline(), 2.0)).decode(errors="replace")
            path = request.split(" ")[1] if " " in request else "/"
            if path == "/health":
                body, status = "ok\n", "200 OK"
            elif path == "/metrics":
                body = "".join(f"telemetry_{k} {v}\n" for k, v in self.metrics.items())
                status = "200 OK"
            else:
                body, status = "not found\n", "404 Not Found"
            payload = body.encode()
            writer.write((f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\n"
                          f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n").encode()
                         + payload)
            await writer.drain()
        except (asyncio.TimeoutError, ConnectionResetError):
            pass
        finally:
            writer.close()


async def _main(args) -> None:
    collector = Collector(args.host, args.port, args.metrics_port, args.db, args.device_timeout)
    await collector.start()
    try:
        await asyncio.Event().wait()
    finally:
        await collector.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Telemetry collector")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--metrics-port", type=int, default=8080)
    parser.add_argument("--db", default="telemetry.db")
    parser.add_argument("--device-timeout", type=float, default=5.0)
    try:
        asyncio.run(_main(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
