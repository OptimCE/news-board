"""Tests for core/metrics.py instruments.

We attach an ``InMemoryMetricReader`` to a freshly-built ``MeterProvider``,
re-fetch a meter, and assert on the in-memory reader directly. This protects
against future OTel API/SDK upgrades silently breaking the API-to-SDK proxy
binding that ``core.metrics`` relies on.
"""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


def _collect(reader: InMemoryMetricReader) -> dict[str, list]:
    """Return a flat ``{metric_name: [data_points]}`` mapping for assertions."""
    data = reader.get_metrics_data()
    found: dict[str, list] = {}
    if data is None:
        return found
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                found.setdefault(metric.name, []).extend(metric.data.data_points)
    return found


def test_counter_records_into_in_memory_reader():
    """End-to-end check that a Counter bound to a freshly-installed
    MeterProvider exports data points via InMemoryMetricReader.
    """
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    previous_provider = metrics.get_meter_provider()
    metrics.set_meter_provider(provider)
    try:
        meter = metrics.get_meter("test")
        counter = meter.create_counter("test.counter")
        counter.add(3, {"x": "y"})

        collected = _collect(reader)
        assert "test.counter" in collected
        points = collected["test.counter"]
        assert sum(p.value for p in points) == 3
        assert any(p.attributes.get("x") == "y" for p in points)
    finally:
        metrics.set_meter_provider(previous_provider)
