"""Scenario tests: drive the simulator against a live collector and assert behavior."""
import urllib.request

from telemetry.simulator import run_simulator


def metric(running, name):
    return running.collector.metrics[name]


def test_normal_flow_stores_every_message(running):
    c = running.collector
    run_simulator("127.0.0.1", c.port, count=20, interval=0.0, mode="normal", seed=1)
    assert running.wait_for(lambda: c.count_rows() == 20)
    assert metric(running, "messages_invalid_total") == 0
    assert metric(running, "sequence_gaps_total") == 0


def test_dropped_packets_are_detected_as_sequence_gaps(running):
    c = running.collector
    # count=22, every=5 -> seq 5, 10, 15, 20 never sent (4 missing); seq 21 reveals the last gap
    sent = run_simulator("127.0.0.1", c.port, count=22, interval=0.0, mode="drop", every=5, seed=2)
    assert running.wait_for(lambda: c.count_rows() == sent)
    assert metric(running, "sequence_gaps_total") == 4


def test_malformed_messages_are_rejected_not_stored(running):
    c = running.collector
    # count=20, every=5 -> seq 5, 10, 15 are garbage (3 bad, 17 good)
    run_simulator("127.0.0.1", c.port, count=20, interval=0.0, mode="malformed", every=5, seed=3)
    assert running.wait_for(lambda: metric(running, "messages_invalid_total") == 3)
    assert running.wait_for(lambda: c.count_rows() == 17)


def test_silent_device_triggers_timeout(running):
    c = running.collector  # fixture timeout is 0.5s
    run_simulator("127.0.0.1", c.port, count=3, interval=0.0, mode="silent", hold=1.2, seed=4)
    assert metric(running, "device_timeouts_total") == 1
    assert c.count_rows() == 3  # data received before going silent is kept


def test_health_and_metrics_endpoints(running):
    c = running.collector
    base = f"http://127.0.0.1:{c.metrics_port}"
    assert urllib.request.urlopen(f"{base}/health", timeout=3).read() == b"ok\n"
    run_simulator("127.0.0.1", c.port, count=5, interval=0.0, seed=5)
    assert running.wait_for(lambda: c.count_rows() == 5)
    body = urllib.request.urlopen(f"{base}/metrics", timeout=3).read().decode()
    assert "telemetry_messages_received_total 5" in body
