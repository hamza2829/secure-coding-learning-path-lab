from dataclasses import dataclass

LANGUAGES = ("Java", "JavaScript", "Python", "C#")
LEVELS = ("introductory", "intermediate", "advanced")
FORMATS = ("reading", "video", "hands on lab")
STRATEGIES = ("lowest-cost", "shortest-time")
CATEGORIES = tuple(f"A{number:02d}" for number in range(1, 11))


@dataclass(frozen=True)
class Competency:
    tag: str
    category: str
    name: str
    objective: str
    practices: dict[str, str]


@dataclass(frozen=True)
class Model:
    edition: str
    competencies: tuple[Competency, ...]


@dataclass(frozen=True)
class Offer:
    id: str
    title: str
    kind: str
    provider: str
    topics: tuple[str, ...]
    minutes: int
    level: str
    format: str
    language: str
    languages: tuple[str, ...]
    cents: int


@dataclass(frozen=True)
class Catalog:
    currency: str
    sample_data: bool
    offers: tuple[Offer, ...]


@dataclass(frozen=True)
class Target:
    category: str
    language: str
    minimum_level: str


@dataclass(frozen=True)
class Assignment:
    title: str
    description: str
    due_date_rule: str
    repeat_interval: str
    target_group: str


@dataclass(frozen=True)
class Rules:
    basic_max_minutes: int
    instruction_language: str
    advanced_targets: tuple[Target, ...]
    assignment: Assignment
