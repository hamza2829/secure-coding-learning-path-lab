from copy import deepcopy

import pytest

from secure_path.inputs import load_catalog, load_model, load_rules

from .conftest import MODEL, ROOT, dump


def test_committed_sample_catalog_and_competence_model(model):
    catalog = load_catalog(ROOT / "catalog", model)
    assert catalog.sample_data is True
    assert catalog.currency == "USD"
    assert len(catalog.offers) >= 40
    assert {item.provider for item in catalog.offers} == {"Provider A", "Provider B", "Provider C"}
    assert {item.kind for item in catalog.offers} == {"course", "module"}
    assert {item.category for item in model.competencies} == {f"A{i:02d}" for i in range(1, 11)}
    assert all(set(item.practices) == {"Java", "JavaScript", "Python", "C#"}
               for item in model.competencies)


@pytest.mark.parametrize(("field", "bad_value", "message"), [
    ("cost_per_person", -1, "cost_per_person"),
    ("cost_per_person", "9.999", "cost_per_person"),
    ("cost_per_person", "1e-1000000000", "cost_per_person"),
    ("cost_per_person", ".nan", "cost_per_person"),
    ("cost_per_person", True, "cost_per_person"),
    ("duration_hours", 0, "duration_hours"),
    ("duration_hours", .12, "duration_hours"),
    ("topics", ["made-up-topic"], "unsupported value"),
    ("topics", ["injection", "injection"], "duplicate values"),
    ("topics", [], "at least one topic"),
    ("topics", "injection", "expected a list"),
    ("level", "expert", "unsupported value"),
    ("language", " ", "nonempty text"),
    ("title", f"bad{chr(0x2014)}title", "single-line text"),
])
def test_invalid_offer_fields_report_context(inputs, model, field, bad_value, message):
    directory, data, _, _ = inputs
    data["entries"][0][field] = bad_value
    dump(directory / "offers.yml", data)
    with pytest.raises(ValueError, match=message) as error:
        load_catalog(directory, model)
    assert "offers.yml: entry 1" in str(error.value)


@pytest.mark.parametrize(("content", "message"), [
    ("[", "offers.yml"),
    ("sample_data: false\nsample_data: true\n", "duplicate YAML"),
    ("currency: USD", "expected keys"),
])
def test_bad_yaml_documents(inputs, model, content, message):
    directory, _, _, _ = inputs
    (directory / "offers.yml").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_catalog(directory, model)


def test_empty_or_missing_catalog(inputs, model, tmp_path):
    directory, data, _, _ = inputs
    with pytest.raises(ValueError, match="no catalog YAML files"):
        load_catalog(tmp_path / "missing", model)
    data["entries"] = []
    dump(directory / "offers.yml", data)
    with pytest.raises(ValueError, match="catalog has no entries"):
        load_catalog(directory, model)


def test_catalog_files_must_have_consistent_metadata_and_unique_ids(inputs, model):
    directory, data, _, _ = inputs
    second = deepcopy(data)
    second["currency"] = "EUR"
    dump(directory / "second.yaml", second)
    with pytest.raises(ValueError, match="must share currency"):
        load_catalog(directory, model)
    dump(directory / "second.yaml", data)
    with pytest.raises(ValueError, match="duplicate offer ID"):
        load_catalog(directory, model)


@pytest.mark.parametrize(("key", "value"), [("currency", "usd"), ("sample_data", "true")])
def test_invalid_catalog_metadata(inputs, model, key, value):
    directory, data, _, _ = inputs
    data[key] = value
    dump(directory / "offers.yml", data)
    with pytest.raises(ValueError, match="three-letter currency and boolean sample_data"):
        load_catalog(directory, model)


@pytest.mark.parametrize(("change", "message"), [
    (lambda source: source.replace("category: A01", "category: A02"), "one competency"),
    (lambda source: source.replace("tag: access-control", "tag: configuration"), "duplicate topic"),
    (lambda source: source.replace('"Java":', '"Ruby":', 1), "expected keys"),
    (lambda source: source.replace("'2025'", "'2021'"), "unsupported value"),
])
def test_invalid_competence_model(tmp_path, change, message):
    path = tmp_path / "model.yml"
    path.write_text(change(MODEL.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_model(path)


@pytest.mark.parametrize(("targets", "message"), [
    ([], "configure 1 to 12"),
    ([{"category": "A01", "language": "Java", "minimum_level": "introductory"}],
     "unsupported value"),
    ([{"category": "A01", "language": "Java", "minimum_level": "advanced"}] * 2,
     "duplicate advanced"),
])
def test_bad_path_rules(inputs, targets, message):
    _, _, path, rules = inputs
    rules["advanced_targets"] = targets
    with pytest.raises(ValueError, match=message):
        load_rules(dump(path, rules))


def test_unreadable_model_reports_path(tmp_path):
    with pytest.raises(ValueError, match="missing.yml"):
        load_model(tmp_path / "missing.yml")
