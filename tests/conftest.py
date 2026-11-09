import sys
from pathlib import Path

import pytest
import yaml

from secure_path.cli import main
from secure_path.inputs import load_catalog, load_model, load_rules

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "config" / "competencies.yml"
RULES = ROOT / "config" / "path.yml"


def dump(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def offer(identifier, topics, hours, price, *, provider="Provider A", level="introductory",
          spoken="en", languages=(), title=None):
    return {
        "id": identifier, "title": title or identifier, "kind": "module",
        "provider": provider, "topics": list(topics), "duration_hours": hours,
        "level": level, "format": "reading", "language": spoken,
        "languages": list(languages), "cost_per_person": price,
    }


@pytest.fixture
def model():
    return load_model(MODEL)


@pytest.fixture
def inputs(tmp_path, model):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    tags = [item.tag for item in model.competencies]
    offers = [
        offer("a-cheap", tags[:6], 3, "10.25", title="=1+1 <script>alert(1)</script>"),
        offer("b-cheap", tags[6:], 2, "8.75", provider="Provider B"),
        offer("fast-all", tags, 2.5, 45, provider="Provider C"),
        offer("java-depth", [tags[0]], 1, "7.50", level="intermediate", languages=["Java"]),
        offer("python-depth", [tags[4]], 2, 11, level="advanced", provider="Provider B",
              languages=["Python"]),
        offer("fast-depth", [tags[0], tags[4]], 1.25, 40, level="advanced",
              provider="Provider C", languages=["Java", "Python"]),
        offer("wrong-depth", [tags[4]], .5, 0, level="intermediate", languages=["Python"]),
        offer("wrong-language", tags, .5, 0, spoken="de"),
        offer("wrong-stack", [tags[4]], .5, 0, level="advanced", languages=["C#"]),
    ]
    catalog_data = {"sample_data": True, "currency": "USD", "entries": offers}
    dump(catalog / "offers.yml", catalog_data)
    rules_data = {
        "basic_max_hours": 5,
        "instruction_language": "en",
        "advanced_targets": [
            {"category": "A01", "language": "Java", "minimum_level": "intermediate"},
            {"category": "A05", "language": "Python", "minimum_level": "advanced"},
        ],
        "assignment": {
            "title": "Basic | Secure coding",
            "description": "Security practice for developers.",
            "due_date_rule": "Within 30 days of assignment",
            "repeat_interval": "Every 12 months",
            "target_group": "Engineers",
        },
    }
    rules = dump(tmp_path / "rules.yml", rules_data)
    return catalog, catalog_data, rules, rules_data


@pytest.fixture
def scenario(inputs, model):
    catalog, _, rules, _ = inputs
    return load_catalog(catalog, model), model, load_rules(rules)


@pytest.fixture
def cli(monkeypatch, tmp_path, inputs):
    catalog, _, rules, _ = inputs
    out = tmp_path / "reports"

    def invoke(*args):
        monkeypatch.setattr(sys, "argv", [
            "secure-path", "build", "--catalog", str(catalog), "--model", str(MODEL),
            "--rules", str(rules), "--group-size", "4", "--out", str(out), *map(str, args),
        ])
        return main()

    return invoke, out
