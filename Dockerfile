FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY telemetry ./telemetry
# Default command runs the collector; docker-compose overrides it for the simulator.
CMD ["python", "-m", "telemetry.collector", "--db", "/data/telemetry.db"]
