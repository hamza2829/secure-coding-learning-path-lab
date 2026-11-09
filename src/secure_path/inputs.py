import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .models import (
    CATEGORIES,
    FORMATS,
    LANGUAGES,
    LEVELS,
    Assignment,
    Catalog,
    Competency,
    Model,
    Offer,
    Rules,
    Target,
)


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        mapping = super().construct_mapping(node, deep)
        if len(mapping) != len(node.value):
            raise ValueError("duplicate YAML mapping key")
        return mapping


def read(path: Path):
    try:
        return yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueLoader)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def fields(value, names: Iterable[str], context: str) -> dict:
    expected = set(names)
    if not isinstance(value, dict) or value.keys() != expected:
        raise ValueError(f"{context}: expected keys {', '.join(sorted(expected))}")
    return value


def text(value, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: expected nonempty text")
    if any(ord(char) < 32 or char == chr(0x2014) for char in value):
        raise ValueError(f"{context}: use single-line text without control characters or long dash")
    return value.strip()


def one_of(value, allowed: Iterable[str], context: str) -> str:
    value = text(value, context)
    if value not in allowed:
        raise ValueError(f"{context}: unsupported value {value!r}")
    return value


def rows(value, context: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a list")
    return value


def names(value, allowed: Iterable[str], context: str) -> tuple[str, ...]:
    selected = tuple(one_of(item, allowed, context) for item in rows(value, context))
    if len(set(selected)) != len(selected):
        raise ValueError(f"{context}: duplicate values")
    return selected


def units(value, scale: int, context: str, *, minimum: int = 0) -> int:
    try:
        if type(value) not in (str, int, float):
            raise InvalidOperation
        quantity = Decimal(str(value))
        if not quantity.is_finite() or not 0 <= quantity <= 1_000_000:
            raise InvalidOperation
        if not quantity.is_zero() and quantity.as_tuple().exponent < -8:
            raise InvalidOperation
        numerator, denominator = quantity.as_integer_ratio()
        scaled, remainder = divmod(numerator * scale, denominator)
        if remainder or scaled < minimum:
            raise InvalidOperation
        return scaled
    except InvalidOperation as exc:
        raise ValueError(
            f"{context}: expected a quantity from {Decimal(minimum) / scale:g} to 1000000 "
            f"representable in whole units of 1/{scale}"
        ) from exc


def load_model(path: Path) -> Model:
    root = fields(read(path), ("edition", "competencies"), str(path))
    edition = one_of(root["edition"], ("2025",), f"{path}: edition")
    competencies = []
    for index, raw in enumerate(rows(root["competencies"], str(path)), 1):
        context = f"{path}: competency {index}"
        item = fields(raw, ("tag", "category", "name", "objective", "practices"), context)
        tag = text(item["tag"], f"{context}: tag")
        category = one_of(item["category"], CATEGORIES, f"{context}: category")
        practice = fields(item["practices"], LANGUAGES, f"{context}: practices")
        competencies.append(Competency(
            tag, category, text(item["name"], context), text(item["objective"], context),
            {language: text(practice[language], f"{context}: {language}") for language in LANGUAGES},
        ))
    if sorted(item.category for item in competencies) != list(CATEGORIES):
        raise ValueError(f"{path}: expected one competency for each OWASP category A01 through A10")
    if len({item.tag for item in competencies}) != len(competencies):
        raise ValueError(f"{path}: duplicate topic tag")
    return Model(edition, tuple(sorted(competencies, key=lambda item: item.category)))


def load_offer(raw, tags: set[str], context: str) -> Offer:
    item = fields(raw, ("id", "title", "kind", "provider", "topics", "duration_hours", "level",
                        "format", "language", "languages", "cost_per_person"), context)
    identifier = text(item["id"], f"{context}: id")
    context = f"{context} ({identifier})"
    topics = names(item["topics"], tags, f"{context}: topics")
    if not topics:
        raise ValueError(f"{context}: at least one topic is required")
    return Offer(
        identifier, text(item["title"], context),
        one_of(item["kind"], ("course", "module"), f"{context}: kind"),
        text(item["provider"], context), topics,
        units(item["duration_hours"], 60, f"{context}: duration_hours", minimum=1),
        one_of(item["level"], LEVELS, f"{context}: level"),
        one_of(item["format"], FORMATS, f"{context}: format"),
        text(item["language"], f"{context}: language"),
        names(item["languages"], LANGUAGES, f"{context}: languages"),
        units(item["cost_per_person"], 100, f"{context}: cost_per_person"),
    )


def load_catalog(directory: Path, model: Model) -> Catalog:
    paths = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
    if not paths:
        raise ValueError(f"{directory}: no catalog YAML files found")
    metadata = None
    offers = []
    seen = set()
    tags = {item.tag for item in model.competencies}
    for path in paths:
        root = fields(read(path), ("sample_data", "currency", "entries"), str(path))
        currency = text(root["currency"], f"{path}: currency")
        sample_data = root["sample_data"]
        if not re.fullmatch(r"[A-Z]{3}", currency) or type(sample_data) is not bool:
            raise ValueError(f"{path}: expected three-letter currency and boolean sample_data")
        if metadata is not None and metadata != (currency, sample_data):
            raise ValueError(f"{path}: catalog files must share currency and sample_data")
        metadata = currency, sample_data
        for index, raw in enumerate(rows(root["entries"], str(path)), 1):
            offer = load_offer(raw, tags, f"{path}: entry {index}")
            if offer.id in seen:
                raise ValueError(f"{path}: duplicate offer ID {offer.id!r}")
            seen.add(offer.id)
            offers.append(offer)
    if not offers:
        raise ValueError(f"{directory}: catalog has no entries")
    return Catalog(*metadata, tuple(sorted(offers, key=lambda item: item.id)))


def load_rules(path: Path) -> Rules:
    root = fields(read(path), ("basic_max_hours", "instruction_language", "advanced_targets",
                               "assignment"), str(path))
    targets = []
    for index, raw in enumerate(rows(root["advanced_targets"], str(path)), 1):
        context = f"{path}: advanced target {index}"
        item = fields(raw, ("category", "language", "minimum_level"), context)
        targets.append(Target(
            one_of(item["category"], CATEGORIES, context),
            one_of(item["language"], LANGUAGES, context),
            one_of(item["minimum_level"], LEVELS[1:], context),
        ))
    if not 1 <= len(targets) <= 12:
        raise ValueError(f"{path}: configure 1 to 12 advanced category and language targets")
    if len({(target.category, target.language) for target in targets}) != len(targets):
        raise ValueError(f"{path}: duplicate advanced category and language target")
    keys = ("title", "description", "due_date_rule", "repeat_interval", "target_group")
    policy = fields(root["assignment"], keys, f"{path}: assignment")
    return Rules(
        units(root["basic_max_hours"], 60, f"{path}: basic_max_hours", minimum=1),
        text(root["instruction_language"], f"{path}: instruction_language"),
        tuple(sorted(targets, key=lambda target: (target.category, target.language))),
        Assignment(**{key: text(policy[key], f"{path}: {key}") for key in keys}),
    )
