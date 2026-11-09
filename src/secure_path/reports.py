import csv
import json
from collections.abc import Iterable
from dataclasses import asdict
from decimal import Decimal
from html import escape
from importlib.resources import files
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .costs import duration, estimate, money
from .models import Catalog, Model, Rules
from .planner import LevelPlan, Plan

LMS_FIELDS = ("title", "description", "duration_minutes", "due_date_rule", "repeat_interval",
              "target_group")
SAMPLE_NOTICE = "Fictional providers and illustrative prices."
COMPARISON = ("Strategy", "Level", "Hours", "Coverage", "Per person", "Group size", "Group total")


def assignment_status(level: LevelPlan) -> str:
    return "LMS assignment ready" if not level.gaps else "LMS export withheld because Basic has gaps"


def comparison_rows(plans: tuple[Plan, ...], group_size: int) -> Iterable[tuple]:
    for plan in plans:
        combined = 0
        for level in plan.levels:
            cost = estimate(level, group_size).total
            combined += cost.per_person_cents
            yield (plan.strategy, level.name, Decimal(level.minutes) / 60,
                   f"{level.covered}/{level.targets}", money(cost.per_person_cents), group_size,
                   money(cost.group_cents))
        yield (
            plan.strategy, "Both levels", Decimal(sum(level.minutes for level in plan.levels)) / 60,
            f"{sum(level.covered for level in plan.levels)}/{sum(level.targets for level in plan.levels)}",
            money(combined), group_size, money(combined * group_size),
        )


def provider_rows(plans: tuple[Plan, ...], group_size: int) -> Iterable[tuple]:
    for plan in plans:
        for level in plan.levels:
            for provider, cost in estimate(level, group_size).by_provider.items():
                yield (plan.strategy, level.name, provider, money(cost.per_person_cents),
                       money(cost.group_cents))


def md(value: object) -> str:
    result = escape(str(value))
    for char in ("\\", "|", "`", "*", "_", "[", "]", "~"):
        result = result.replace(char, f"\\{char}")
    return result


def md_table(headers: tuple[str, ...], rows: Iterable[tuple]) -> str:
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    formatted = ["| " + " | ".join(md(cell) for cell in headers) + " |", separator]
    for row in rows:
        formatted.append("| " + " | ".join(md(cell) for cell in row) + " |")
    return "\n".join(formatted)


def compare_for_display(plans: tuple[Plan, ...], group_size: int, currency: str) -> Iterable[tuple]:
    for strategy, level, hours, coverage, price, group, total in comparison_rows(plans, group_size):
        yield strategy, level, f"{hours:.2f}", coverage, f"{price:.2f} {currency}", group, (
            f"{total:.2f} {currency}"
        )


def path_markdown(model: Model, catalog: Catalog, rules: Rules, plans: tuple[Plan, ...],
                  selected: Plan, group_size: int) -> str:
    lines = [
        "# Secure coding learning path", "",
        f"OWASP Top 10:{model.edition} | Selected alternative **{selected.strategy}**", "",
        f"Basic time cap **{duration(rules.basic_max_minutes)}**. "
        f"Instruction language **{md(rules.instruction_language)}**.", "",
        assignment_status(selected.basic) + ".", "",
    ]
    if catalog.sample_data:
        lines.extend([SAMPLE_NOTICE, ""])
    for level in selected.levels:
        purpose = "compulsory" if level.name == "Basic" else "deepening"
        lines.extend([
            f"## {level.name} ({purpose})", "",
            f"{level.covered}/{level.targets} targets covered in {duration(level.minutes)}.", "",
        ])
        for index, step in enumerate(level.steps, 1):
            offer = step.offer
            price = f"{money(offer.cents):.2f} {catalog.currency}"
            lines.append(
                f"{index}. **{md(offer.title)}** ({md(offer.provider)}, {offer.kind}, "
                f"{offer.format}, {offer.level}, {duration(offer.minutes)}, {price}). "
                f"{md(step.reason)}"
            )
        if level.gaps:
            lines.extend(["", "### Coverage gaps", ""])
            lines.extend(f"- **{md(gap.target)}**. {md(gap.reason)}" for gap in level.gaps)
        lines.append("")

    competencies = {item.category: item for item in model.competencies}
    lines.extend(["## Advanced practice objectives", ""])
    for target in rules.advanced_targets:
        practice = competencies[target.category].practices[target.language]
        lines.append(f"- {target.category} / {target.language}. {md(practice)}")
    lines.extend(["", "## Cost comparison", "",
                  "Costs include the selected entries for each level.", "",
                  md_table(COMPARISON, compare_for_display(plans, group_size, catalog.currency)),
                  "", "### Provider breakdown", ""])
    lines.append(md_table(
        ("Strategy", "Level", "Provider", "Per person", "Group total"),
        ((strategy, level, provider, f"{price:.2f} {catalog.currency}",
          f"{total:.2f} {catalog.currency}")
         for strategy, level, provider, price, total in provider_rows(plans, group_size)),
    ))
    return "\n".join(lines) + "\n"


def training_basis(model: Model, rules: Rules, level: LevelPlan, sample_data: bool) -> str:
    policy = rules.assignment
    lines = ["# Professional basis for Basic training", "", assignment_status(level) + ".", ""]
    if sample_data:
        lines.extend([SAMPLE_NOTICE, ""])
    lines.extend([
        f"**{md(policy.title)}** is the compulsory foundation for {md(policy.target_group)}.",
        f"{md(policy.description)} The planned workload is {duration(level.minutes)}.",
        f"Completion rule: {md(policy.due_date_rule)}. Renewal: {md(policy.repeat_interval)}.",
        "", f"## Learning objectives mapped to OWASP Top 10:{model.edition}", "",
    ])
    lines.extend(f"- **{item.category} {md(item.name)}**. {md(item.objective)}"
                 for item in model.competencies)
    lines.extend(["", "## Assigned content", ""])
    lines.extend(f"{index}. {md(step.offer.title)} ({duration(step.offer.minutes)}). "
                 f"{md(step.reason)}" for index, step in enumerate(level.steps, 1))
    if level.gaps:
        lines.extend(["", "## Gaps to close before assignment", ""])
        lines.extend(f"- {md(gap.target)}. {md(gap.reason)}" for gap in level.gaps)
    return "\n".join(lines) + "\n"


def html_table(headers: tuple[str, ...], rows: Iterable[tuple]) -> str:
    head = "".join(f'<th scope="col">{escape(title)}</th>' for title in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def level_html(level: LevelPlan, purpose: str) -> str:
    steps = "".join(
        f"<li><strong>{escape(step.offer.title)}</strong> "
        f'<span class="meta">| {escape(step.offer.provider)} | {duration(step.offer.minutes)}</span>'
        f"<br>{escape(step.reason)}</li>"
        for step in level.steps
    )
    gaps = "".join(f"<li><strong>{escape(gap.target)}</strong>. {escape(gap.reason)}</li>"
                   for gap in level.gaps)
    gap_html = f'<h3 class="warning">Coverage gaps</h3><ul>{gaps}</ul>' if gaps else ""
    return (f'<article class="panel"><h2>{level.name} <span class="meta">| {purpose}</span></h2>'
            f'<p class="big">{level.covered}/{level.targets} targets</p>'
            f'<p class="meta">{duration(level.minutes)}</p><ol>{steps}</ol>{gap_html}</article>')


def overview(model: Model, catalog: Catalog, rules: Rules, plans: tuple[Plan, ...],
             selected: Plan, group_size: int) -> str:
    css = files("secure_path").joinpath("overview.css").read_text(encoding="utf-8")
    status = "warning" if selected.basic.gaps else "ok"
    label = SAMPLE_NOTICE if catalog.sample_data else "Estimates from the supplied catalog."
    cost_table = html_table(COMPARISON, compare_for_display(plans, group_size, catalog.currency))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Secure coding learning path</title>
<style>{css}</style>
</head>
<body>
<header><div class="wrap">
  <div class="kicker">SECURE CODING LEARNING PATH LAB</div>
  <h1>Training plan overview</h1>
  <p>OWASP Top 10:{model.edition} | {label}</p>
</div></header>
<main class="wrap">
  <div class="notice">
    <div class="panel"><h2>Selected alternative</h2><p class="big">{selected.strategy}</p>
      <p class="meta">Basic cap {duration(rules.basic_max_minutes)} |
        Instruction language {escape(rules.instruction_language)}</p></div>
    <div class="panel"><h2>Compulsory training</h2>
      <p class="{status}">{assignment_status(selected.basic)}</p>
      <p>{escape(rules.assignment.target_group)} | {escape(rules.assignment.due_date_rule)}</p>
      <p class="meta">{escape(rules.assignment.repeat_interval)}</p></div>
  </div>
  <section class="panel"><h2>Cost comparison for {group_size} learners</h2>
    <p class="meta">Costs cover the selected entries at each level.</p>{cost_table}
  </section>
  <section class="grid" aria-label="Learning levels">
    {level_html(selected.basic, "Compulsory")}
    {level_html(selected.advanced, "Deepening")}
  </section>
</main>
<footer class="wrap">The learning path document includes practice objectives and provider costs.</footer>
</body>
</html>
"""


def worksheet(book: Workbook, name: str, headers: tuple, rows: Iterable[tuple]) -> None:
    sheet = book.create_sheet(name)
    sheet.append(headers)
    widths = [len(header) + 3 for header in headers]
    for row in rows:
        sheet.append(row)
        for index, (cell, value) in enumerate(zip(sheet[sheet.max_row], row, strict=True)):
            if isinstance(value, str):
                cell.data_type = "s"
            if isinstance(value, Decimal):
                cell.number_format = "0.00"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            widths[index] = min(65, max(widths[index], len(str(value)) + 3))
    for index, cell in enumerate(sheet[1], 1):
        cell.fill = PatternFill("solid", fgColor="173E50")
        cell.font = Font(color="FFFFFF", bold=True)
        sheet.column_dimensions[get_column_letter(index)].width = widths[index - 1]
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions


def cost_workbook(path: Path, catalog: Catalog, plans: tuple[Plan, ...], group_size: int) -> None:
    book = Workbook()
    book.remove(book.active)
    worksheet(book, "Comparison", COMPARISON, comparison_rows(plans, group_size))
    worksheet(book, "Providers", ("Strategy", "Level", "Provider", "Per person", "Group total"),
              provider_rows(plans, group_size))
    worksheet(book, "Offers", ("Strategy", "Level", "Offer ID", "Title", "Provider", "Hours",
                               "Per person", "Selection reason"), (
        (plan.strategy, level.name, step.offer.id, step.offer.title, step.offer.provider,
         Decimal(step.offer.minutes) / 60, money(step.offer.cents), step.reason)
        for plan in plans for level in plan.levels for step in level.steps
    ))
    worksheet(book, "Inputs", ("Setting", "Value"), [
        ("Currency", catalog.currency), ("Group size", group_size),
        ("Price source", SAMPLE_NOTICE if catalog.sample_data else "Supplied catalog"),
    ])
    book.save(path)


def write_exports(out: Path, model: Model, catalog: Catalog, rules: Rules,
                  plans: tuple[Plan, ...], selected: Plan, group_size: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    assignments = [] if selected.basic.gaps else [
        {**asdict(rules.assignment), "duration_minutes": selected.basic.minutes}
    ]
    with (out / "basic-lms.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LMS_FIELDS)
        writer.writeheader()
        writer.writerows(assignments)
    (out / "basic-lms.json").write_text(
        json.dumps(assignments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (out / "basic-training-basis.md").write_text(
        training_basis(model, rules, selected.basic, catalog.sample_data), encoding="utf-8",
    )
    (out / "learning-path.md").write_text(
        path_markdown(model, catalog, rules, plans, selected, group_size), encoding="utf-8",
    )
    (out / "overview.html").write_text(
        overview(model, catalog, rules, plans, selected, group_size), encoding="utf-8",
    )
    cost_workbook(out / "cost-comparison.xlsx", catalog, plans, group_size)
