"""Fairness / starvation prevention (build prompt §9).

Tracks waiting duration, yields, denials; effective priority grows with age
(priority aging). A robot that repeatedly yields receives progressively more
effective priority so low-priority robots eventually make progress.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class FairnessState:
    wait_since: float = 0.0      # timestamp when current wait episode began (0 = not waiting)
    accumulated_wait: float = 0.0
    yields: int = 0
    denials: int = 0
    base_priority: float = 1.0
    urgency: float = 0.0

    def start_wait(self, now: float) -> None:
        if self.wait_since == 0.0:
            self.wait_since = now

    def stop_wait(self, now: float) -> float:
        """End the wait episode; returns episode duration."""
        if self.wait_since > 0.0:
            dur = max(0.0, now - self.wait_since)
            self.accumulated_wait += dur
            self.wait_since = 0.0
            return dur
        return 0.0

    def register_yield(self) -> None:
        self.yields += 1

    def register_denial(self) -> None:
        self.denials += 1


@dataclass
class FairnessConfig:
    aging_per_s: float = 0.15
    yield_bonus: float = 0.8
    denial_bonus: float = 0.5
    max_effective_priority: float = 25.0
    starvation_wait_s: float = 12.0

    @staticmethod
    def from_cfg(cfg: Dict) -> "FairnessConfig":
        return FairnessConfig(
            aging_per_s=cfg.get("aging_per_s", 0.15),
            yield_bonus=cfg.get("yield_bonus", 0.8),
            denial_bonus=cfg.get("denial_bonus", 0.5),
            max_effective_priority=cfg.get("max_effective_priority", 12.0),
            starvation_wait_s=cfg.get("starvation_wait_s", 12.0),
        )


def effective_priority(state: FairnessState, cfg: FairnessConfig, now: float) -> float:
    """Deterministic effective priority with aging. Higher = stronger claim."""
    current_wait = (now - state.wait_since) if state.wait_since > 0 else 0.0
    p = (state.base_priority + state.urgency
         + state.accumulated_wait * cfg.aging_per_s
         + current_wait * cfg.aging_per_s * 2.0
         + state.yields * cfg.yield_bonus
         + state.denials * cfg.denial_bonus)
    return min(cfg.max_effective_priority, p)


def is_starving(state: FairnessState, cfg: FairnessConfig, now: float) -> bool:
    current_wait = (now - state.wait_since) if state.wait_since > 0 else 0.0
    return current_wait >= cfg.starvation_wait_s or state.accumulated_wait >= cfg.starvation_wait_s * 2


def deterministic_order(rid_a: str, pr_a: float, rid_b: str, pr_b: str, pr_bv: float = 0.0) -> int:
    """Total order between two claimants: priority DESC, then robot id ASC.

    Deterministic for identical inputs — used everywhere for tie-breaking.
    Returns -1 if A precedes B, +1 if B precedes A.
    """
    if pr_a > pr_bv + 1e-9:
        return -1
    if pr_bv > pr_a + 1e-9:
        return 1
    return -1 if rid_a < rid_b else 1
