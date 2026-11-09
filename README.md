# Secure Coding Learning Path Lab

A Python 3.12 CLI that turns a YAML catalog into a compulsory Basic secure coding path and an optional Advanced path. It explains each selection, reports coverage gaps, compares per-person and group costs, and prepares a generic LMS record for Basic.

The supplied catalog uses fictional Provider A, Provider B and Provider C offers and illustrative USD prices. The competence model maps all ten risk categories to practice objectives for Java, JavaScript, Python and C#. [OWASP Top 10:2025](https://top10.owasp.org/2025/)

## Run

From the repository root with Python 3.12:

```text
python -m pip install .
secure-path build --group-size 25 --out reports
secure-path build --group-size 25 --strategy shortest-time --out reports-fast
```

The CLI builds both alternatives in one run. The selected strategy controls the learning path, HTML overview, professional basis and LMS assignment. Cost reports always compare both strategies. Use `--catalog`, `--model` and `--rules` to supply other inputs.

| Output | Contents |
| --- | --- |
| `learning-path.md` | Ordered Basic and Advanced paths, reasons, gaps, practice objectives, cost comparison and provider breakdown. |
| `overview.html` | Single offline overview with both levels and the cost comparison. |
| `cost-comparison.xlsx` | Numeric Basic, Advanced and combined estimates for both paths, with provider and offer breakdowns. |
| `basic-lms.csv`, `basic-lms.json` | One generic compulsory assignment when Basic covers all ten categories. |
| `basic-training-basis.md` | Audience, objectives, assigned material, expected workload and renewal policy. |

## Catalog and rules

Each `.yml` or `.yaml` file in the catalog directory has `sample_data`, `currency` and `entries` keys. The files share one currency and one sample flag. Each entry has an ID, title, kind (`course` or `module`), provider, competence tags, duration in hours, depth, format, instruction language, programming languages and per-person price. Durations must convert to whole minutes and prices to whole cents. See [the sample catalog](catalog/README.md).

- **Basic** uses introductory entries in the configured instruction language. It aims to cover all ten categories within the fixed time cap. The sample cap is eight hours.
- **Advanced** covers the configured category and programming language pairs at their specified minimum depth of intermediate or advanced. An offer qualifies only for the languages and topics it declares.
- **Selection** maximizes the number of covered targets, then minimizes cost or duration according to the strategy. Ties use the other metric, then the number of offers, then offer IDs. Within a level, entries are ordered by depth and first relevant target, with format and ID breaking ties.
- **Gaps** distinguish unavailable introductory coverage, available coverage that did not fit under the Basic cap, and missing depth or programming language for Advanced. A gap remains visible when the CLI returns a partial path.
- **Costs** sum each selected offer once per level using integer cents. Group totals assume every learner takes the indicated level or both levels. The provider sheet shows how each estimate was assembled.

Edit the Basic time cap, instruction language, Advanced targets and assignment policy in [config/path.yml](config/path.yml). The mapping and practice objectives are in [config/competencies.yml](config/competencies.yml).

## Generic LMS handoff

CSV and JSON use the same six fields. JSON uses an array of records.

```text
title,description,duration_minutes,due_date_rule,repeat_interval,target_group
```

The duration is the selected Basic path's sum in minutes. Due date and repeat rules are text for the receiving administrator or importer to map to its schedule. The sample policy assigns Basic to software development staff within 30 calendar days and repeats it every 12 months. If Basic is incomplete, the CSV contains only its header and JSON contains an empty array. A malformed input stops the build before writing exports.

## Verification

GitHub Actions runs Ruff, pytest with line coverage, and the installed CLI with both sample alternatives. The `learning-path` artifact contains the generated exports and verification evidence. [GitHub Actions workflow](https://github.com/hamza2829/secure-coding-learning-path-lab/actions/workflows/ci.yml)

## Limits

The catalog and its prices are sample data. The tool uses files on disk and has no real learning platform connection. Cost estimates cover license amounts only and exclude taxes, discounts and staff time. Coverage is inferred from catalog tags and depth labels. It measures planned exposure to topics rather than learner mastery. The optimizer supports up to 12 configured Advanced targets.
