from __future__ import annotations

from teic.interoception.reportability import REFRACTORY_TICKS, ReportabilityGate


def test_low_tension_never_opens() -> None:
    gate = ReportabilityGate()
    for _ in range(20):
        assert gate.evaluate(0.0) is False


def test_high_tension_opens_once_then_cools_down() -> None:
    gate = ReportabilityGate()
    assert gate.evaluate(1.0) is True
    for _ in range(REFRACTORY_TICKS - 1):
        assert gate.evaluate(1.0) is False


def test_gate_reopens_after_cooldown_elapses() -> None:
    gate = ReportabilityGate()
    assert gate.evaluate(1.0) is True
    for _ in range(REFRACTORY_TICKS):
        assert gate.evaluate(1.0) is False
    assert gate.evaluate(1.0) is True
