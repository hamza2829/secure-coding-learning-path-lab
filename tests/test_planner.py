from dataclasses import replace
from itertools import combinations

import pytest

from secure_path.costs import Cost, duration, estimate, money
from secure_path.planner import Choice, build_plans, select


def ids(level):
    return [step.offer.id for step in level.steps]


def test_rules_produce_two_ordered_complete_paths(scenario):
    cost, speed = build_plans(*scenario)
    assert cost.strategy == "lowest-cost"
    assert speed.strategy == "shortest-time"
    assert ids(cost.basic) == ["a-cheap", "b-cheap"]
    assert ids(speed.basic) == ["fast-all"]
    assert cost.basic.covered == speed.basic.covered == 10
    assert cost.basic.minutes == 300
    assert speed.basic.minutes == 150
    assert cost.basic.steps[0].reason.startswith("Introduces A01 Broken Access Control")
    assert cost.basic.steps[1].covers[-1].startswith("A10")
    assert ids(cost.advanced) == ["java-depth", "python-depth"]
    assert ids(speed.advanced) == ["fast-depth"]
    assert cost.advanced.covered == speed.advanced.covered == 2
    assert cost.advanced.minutes == 180
    assert speed.advanced.minutes == 75
    assert "/ Python (advanced)" in cost.advanced.steps[1].reason
    assert all(not level.gaps for plan in (cost, speed) for level in plan.levels)


def test_coverage_beats_cost_and_both_strategies_obey_the_cap(scenario):
    catalog, model, rules = scenario
    cost, speed = build_plans(catalog, model, replace(rules, basic_max_minutes=240))
    assert ids(cost.basic) == ids(speed.basic) == ["fast-all"]
    assert cost.basic.covered == 10


def test_gaps_distinguish_missing_entries_from_time_cap(scenario):
    catalog, model, rules = scenario
    excluded = {"fast-all", "fast-depth", "python-depth"}
    catalog = replace(catalog, offers=tuple(offer for offer in catalog.offers
                                           if offer.id not in excluded))
    cost, _ = build_plans(catalog, model, replace(rules, basic_max_minutes=240))
    assert ids(cost.basic) == ["a-cheap"]
    assert [gap.target[:3] for gap in cost.basic.gaps] == ["A07", "A08", "A09", "A10"]
    assert {gap.code for gap in cost.basic.gaps} == {"time_budget"}
    assert ids(cost.advanced) == ["java-depth"]
    assert cost.advanced.gaps[0].code == "missing_depth"
    assert "/ Python (advanced)" in cost.advanced.gaps[0].target

    offers = tuple(offer for offer in catalog.offers if offer.id != "b-cheap")
    cost, _ = build_plans(replace(catalog, offers=offers), model, rules)
    assert cost.basic.covered == 6
    assert {gap.code for gap in cost.basic.gaps} == {"missing_introductory"}


def test_catalog_with_no_eligible_offer_yields_empty_paths(scenario):
    catalog, model, rules = scenario
    cost, speed = build_plans(catalog, model, replace(rules, instruction_language="ja"))
    for plan in (cost, speed):
        assert plan.basic.covered == plan.advanced.covered == 0
        assert plan.basic.minutes == plan.advanced.minutes == 0


def test_hand_calculated_costs_for_two_alternatives(scenario):
    cost, speed = build_plans(*scenario)
    basic = estimate(cost.basic, 4)
    assert basic.total == Cost(1900, 7600)
    assert basic.by_provider == {"Provider A": Cost(1025, 4100), "Provider B": Cost(875, 3500)}
    advanced = estimate(cost.advanced, 4)
    assert advanced.total == Cost(1850, 7400)
    assert advanced.by_provider == {"Provider A": Cost(750, 3000), "Provider B": Cost(1100, 4400)}
    assert estimate(speed.basic, 4).total == Cost(4500, 18000)
    assert estimate(speed.advanced, 4).by_provider == {"Provider C": Cost(4000, 16000)}
    assert str(money(1025)) == "10.25"
    assert duration(75) == "1 h 15 min"
    assert duration(120) == "2 h"
    assert duration(45) == "45 min"
    with pytest.raises(ValueError, match="positive"):
        estimate(cost.basic, 0)


@pytest.mark.parametrize("strategy", ["lowest-cost", "shortest-time"])
@pytest.mark.parametrize("cap", [None, 150, 240, 400])
def test_optimizer_matches_exhaustive_search_with_overlap_and_ties(scenario, strategy, cap):
    catalog, _, _ = scenario
    original = catalog.offers[0]
    specs = [(5, 120, 100), (6, 60, 200), (2, 45, 80), (8, 90, 5),
             (15, 400, 0), (5, 120, 100), (1, 30, 100), (12, 105, 10)]
    offers = [(replace(original, id=f"offer-{i}", minutes=minutes, cents=cents), bits)
              for i, (bits, minutes, cents) in enumerate(specs)]
    results = []
    for count in range(len(offers) + 1):
        for group in combinations(offers, count):
            minutes = sum(offer.minutes for offer, _ in group)
            if cap is not None and minutes > cap:
                continue
            mask = 0
            for _, bits in group:
                mask |= bits
            choice = Choice(tuple(offer for offer, _ in group), minutes,
                            sum(offer.cents for offer, _ in group))
            results.append((mask, choice))
    expected = min(results, key=lambda item: (-item[0].bit_count(), item[1].rank(strategy)))
    assert select(offers, strategy, cap) == expected
