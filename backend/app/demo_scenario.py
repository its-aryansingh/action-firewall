"""Action Firewall — Demo Fault Injection State & Controller.

Per Invariant 17 and Defect D2, fault injection is never an argument on money-path
or external MCP buyer contracts. Fault injection is restricted to loopback demo runners
under DEMO_MODE=true.
"""
from __future__ import annotations

from pydantic import BaseModel
from .models import AutopilotScenario

_active_scenario: AutopilotScenario = AutopilotScenario.NORMAL


class DemoScenarioRequest(BaseModel):
    scenario: AutopilotScenario = AutopilotScenario.NORMAL


class DemoScenarioResponse(BaseModel):
    scenario: AutopilotScenario
    message: str


def get_active_scenario() -> AutopilotScenario:
    return _active_scenario


def set_active_scenario(scenario: AutopilotScenario) -> None:
    global _active_scenario
    _active_scenario = scenario


def reset_active_scenario() -> None:
    global _active_scenario
    _active_scenario = AutopilotScenario.NORMAL
