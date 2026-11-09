from collections.abc import Callable
from dataclasses import dataclass

from .models import FORMATS, LEVELS, STRATEGIES, Catalog, Model, Offer, Rules


@dataclass(frozen=True)
class Step:
    offer: Offer
    covers: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Gap:
    target: str
    code: str
    reason: str


@dataclass(frozen=True)
class LevelPlan:
    name: str
    steps: tuple[Step, ...]
    gaps: tuple[Gap, ...]
    targets: int

    @property
    def minutes(self) -> int:
        return sum(step.offer.minutes for step in self.steps)

    @property
    def covered(self) -> int:
        return self.targets - len(self.gaps)


@dataclass(frozen=True)
class Plan:
    strategy: str
    basic: LevelPlan
    advanced: LevelPlan

    @property
    def levels(self) -> tuple[LevelPlan, LevelPlan]:
        return self.basic, self.advanced


@dataclass(frozen=True)
class Choice:
    offers: tuple[Offer, ...] = ()
    minutes: int = 0
    cents: int = 0

    def add(self, offer: Offer) -> "Choice":
        return Choice((*self.offers, offer), self.minutes + offer.minutes, self.cents + offer.cents)

    def rank(self, strategy: str) -> tuple[int, int, int, tuple[str, ...]]:
        primary = (self.cents, self.minutes) if strategy == "lowest-cost" else (
            self.minutes, self.cents,
        )
        return *primary, len(self.offers), tuple(offer.id for offer in self.offers)


def prune(choices: dict[tuple[int, int], Choice]) -> dict[tuple[int, int], Choice]:
    """Keep choices with lower cost than every shorter choice for the same mask."""
    retained = {}
    cheapest: dict[int, int] = {}
    for key, choice in sorted(choices.items()):
        mask, _ = key
        if mask not in cheapest or choice.cents < cheapest[mask]:
            cheapest[mask] = choice.cents
            retained[key] = choice
    return retained


def select(candidates: list[tuple[Offer, int]], strategy: str,
           cap: int | None) -> tuple[int, Choice]:
    # Each state represents the covered targets and, when capped, the duration used.
    states = {(0, 0): Choice()}
    for offer, coverage in candidates:
        next_states = states.copy()
        for (mask, _), choice in states.items():
            combined = mask | coverage
            minutes = choice.minutes + offer.minutes
            if combined == mask or (cap is not None and minutes > cap):
                continue
            key = combined, minutes if cap is not None else 0
            proposed = choice.add(offer)
            previous = next_states.get(key)
            if previous is None or proposed.rank(strategy) < previous.rank(strategy):
                next_states[key] = proposed
        states = prune(next_states) if cap is not None else next_states
    (mask, _), result = min(
        states.items(),
        key=lambda item: (-item[0][0].bit_count(), item[1].rank(strategy)),
    )
    return mask, result


def plan_level(name: str, offers: tuple[Offer, ...], labels: tuple[str, ...],
               matches: Callable[[Offer], int], strategy: str,
               cap: int | None = None) -> LevelPlan:
    candidates = [(offer, matches(offer)) for offer in offers]
    mask, selection = select(candidates, strategy, cap)
    coverage = {offer.id: bits for offer, bits in candidates}
    available = 0
    for bits in coverage.values():
        available |= bits

    steps = []
    gaps = []
    ordered = sorted(
        selection.offers,
        key=lambda offer: (LEVELS.index(offer.level), coverage[offer.id] & -coverage[offer.id],
                           FORMATS.index(offer.format), offer.id),
    )
    remaining = mask
    for offer in ordered:
        introduced = remaining & coverage[offer.id]
        remaining &= ~introduced
        targets = tuple(label for index, label in enumerate(labels) if introduced & (1 << index))
        verb = "Introduces" if name == "Basic" else "Meets the required depth for"
        steps.append(Step(offer, targets, f"{verb} {'; '.join(targets)}."))

    for index, label in enumerate(labels):
        bit = 1 << index
        if mask & bit:
            continue
        if available & bit:
            code = "time_budget"
            reason = "Eligible offers exist, but this target is outside the best fit under the time cap."
        elif name == "Basic":
            code = "missing_introductory"
            reason = "No introductory offer in the selected instruction language covers this category."
        else:
            code = "missing_depth"
            reason = "No offer meets this target's programming language and minimum depth."
        gaps.append(Gap(label, code, reason))
    return LevelPlan(name, tuple(steps), tuple(gaps), len(labels))


def build_plans(catalog: Catalog, model: Model, rules: Rules) -> tuple[Plan, ...]:
    available = tuple(sorted(
        (offer for offer in catalog.offers if offer.language == rules.instruction_language),
        key=lambda offer: offer.id,
    ))
    tags = {item.category: item.tag for item in model.competencies}
    names = {item.category: item.name for item in model.competencies}
    basic_labels = tuple(f"{item.category} {item.name}" for item in model.competencies)
    advanced_labels = tuple(
        f"{target.category} {names[target.category]} / {target.language} ({target.minimum_level})"
        for target in rules.advanced_targets
    )

    def basic_bits(offer: Offer) -> int:
        return sum(
            1 << index for index, item in enumerate(model.competencies) if item.tag in offer.topics
        )

    def advanced_bits(offer: Offer) -> int:
        return sum(
            1 << index for index, target in enumerate(rules.advanced_targets)
            if tags[target.category] in offer.topics
            and target.language in offer.languages
            and LEVELS.index(offer.level) >= LEVELS.index(target.minimum_level)
        )

    introductory = tuple(offer for offer in available if offer.level == "introductory")
    deeper = tuple(offer for offer in available if offer.level != "introductory")
    return tuple(Plan(
        strategy,
        plan_level("Basic", introductory, basic_labels, basic_bits, strategy,
                   rules.basic_max_minutes),
        plan_level("Advanced", deeper, advanced_labels, advanced_bits, strategy),
    ) for strategy in STRATEGIES)
