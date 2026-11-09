from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from .planner import LevelPlan


@dataclass(frozen=True)
class Cost:
    per_person_cents: int
    group_cents: int


@dataclass(frozen=True)
class Estimate:
    total: Cost
    by_provider: dict[str, Cost]


def estimate(level: LevelPlan, group_size: int) -> Estimate:
    if group_size < 1:
        raise ValueError("group size must be positive")
    amounts: Counter[str] = Counter()
    for step in level.steps:
        amounts[step.offer.provider] += step.offer.cents
    total = sum(amounts.values())
    return Estimate(
        Cost(total, total * group_size),
        {provider: Cost(cents, cents * group_size) for provider, cents in sorted(amounts.items())},
    )


def money(cents: int) -> Decimal:
    return Decimal(cents) / 100


def duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours} h {remainder} min"
    return f"{hours} h" if hours else f"{remainder} min"
