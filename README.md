# Device Telemetry Pipeline & Test Harness

A small, containerized telemetry system in Python: a **device simulator** streams sensor readings over TCP to a **collector service**, which validates, stores, and monitors them. An automated **pytest harness** injects faults (dropped packets, malformed data, silent devices) and verifies the collector handles each correctly.

```
 simulator  --TCP (newline-delimited JSON)-->  collector  -->  SQLite
 (fault modes)                                    |
                                      /health, /metrics (HTTP)
```

## What it demonstrates
- Linux/Docker deployment with `docker compose`
- Network programming (asyncio TCP server, sockets, HTTP endpoints)
- Input validation, sequence-gap detection, timeout handling
- Structured JSON logging and Prometheus-style metrics
- Automated scenario testing against a simulated device, plus CI (GitHub Actions)

## Run the tests
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Run with Docker
```bash
docker compose up --build
curl localhost:8080/health
curl localhost:8080/metrics
```
Edit the simulator `--mode` in `docker-compose.yml` (`normal`, `drop`, `malformed`, `silent`) to see each fault reflected in the logs and metrics.

## Run without Docker
```bash
python -m telemetry.collector --db telemetry.db &
python -m telemetry.simulator --mode drop --count 60
```

## Fault modes
| Mode | Behavior | What the collector should do |
|---|---|---|
| normal | consecutive, valid readings | store all |
| drop | skips every Nth sequence number | count `sequence_gaps_total` |
| malformed | sends invalid JSON every Nth message | reject, count `messages_invalid_total` |
| silent | stops sending but keeps the connection open | time out, count `device_timeouts_total` |

## Ideas to extend
- Multiple concurrent simulated devices
- Swap SQLite for Postgres in `docker-compose.yml`
- Grafana/Prometheus scraping the `/metrics` endpoint
- A binary protocol (struct/protobuf) alongside JSON
- Reconnect/backoff logic in the simulator
