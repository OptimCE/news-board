"""Application metrics for the optimce-news-board service.

All instruments are created at module import. The OTel API ships a
``_ProxyMeterProvider`` until ``metrics.set_meter_provider(...)`` runs
(inside ``core.tracing.setup_tracer_provider``), and instruments created
against the proxy rebind to the real provider when it is installed —
so import order between this module and tracing setup does not matter.

In LOCAL ``setup_tracer_provider`` returns early and the proxy stays a
no-op, meaning every ``.add(...)`` call below becomes a cheap function
dispatch with no side effects.

Naming follows OTel semantic conventions: dotted lowercase, ``.total``
suffix on monotonically increasing counters.
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("optimce-news-board")

health_checks = _meter.create_counter(
    name="health.checks.total",
    description="Readiness probe component outcomes",
    unit="1",
)
