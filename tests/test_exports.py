import csv
import json

import pytest
from openpyxl import load_workbook

from secure_path.reports import LMS_FIELDS

from .conftest import dump

EXPECTED_FILES = {
    "basic-lms.csv", "basic-lms.json", "basic-training-basis.md", "learning-path.md",
    "overview.html", "cost-comparison.xlsx",
}


def test_basic_assignment_matches_between_csv_json_and_professional_basis(cli):
    invoke, out = cli
    assert invoke() == 0
    assert {item.name for item in out.iterdir()} == EXPECTED_FILES
    records = json.loads((out / "basic-lms.json").read_text(encoding="utf-8"))
    assert records == [{
        "title": "Basic | Secure coding", "description": "Security practice for developers.",
        "duration_minutes": 300, "due_date_rule": "Within 30 days of assignment",
        "repeat_interval": "Every 12 months", "target_group": "Engineers",
    }]
    with (out / "basic-lms.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert tuple(reader.fieldnames) == LMS_FIELDS
        assert list(reader) == [{**records[0], "duration_minutes": "300"}]
    basis = (out / "basic-training-basis.md").read_text(encoding="utf-8")
    assert "Professional basis for Basic training" in basis
    assert "Within 30 days of assignment" in basis
    assert "A01 Broken Access Control" in basis
    assert "A10 Mishandling of Exceptional Conditions" in basis
    assert "Fictional providers and illustrative prices." in basis
    assert "java-depth" not in basis


def test_markdown_and_offline_html_show_path_and_costs(cli):
    invoke, out = cli
    assert invoke() == 0
    path = (out / "learning-path.md").read_text(encoding="utf-8")
    assert "## Basic (compulsory)" in path
    assert "## Advanced (deepening)" in path
    assert "Advanced practice objectives" in path
    assert "| lowest-cost | Basic | 5.00 | 10/10 | 19.00 USD | 4 | 76.00 USD |" in path
    assert "| shortest-time | Both levels | 3.75 | 12/12 | 85.00 USD | 4 | 340.00 USD |" in path
    assert "| lowest-cost | Advanced | Provider B | 11.00 USD | 44.00 USD |" in path
    html = (out / "overview.html").read_text(encoding="utf-8")
    for phrase in ("<style>", "OWASP Top 10:2025", "LMS assignment ready",
                   "Cost comparison for 4 learners", "Fictional providers", "76.00 USD",
                   "Introduces A01", "Meets the required depth for"):
        assert phrase in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script" not in html
    assert "https://" not in html and "http://" not in html


def test_excel_comparison_preserves_numeric_costs_and_text(cli):
    invoke, out = cli
    assert invoke() == 0
    book = load_workbook(out / "cost-comparison.xlsx", data_only=False)
    assert book.sheetnames == ["Comparison", "Providers", "Offers", "Inputs"]
    comparison = list(book["Comparison"].values)
    assert comparison[1] == ("lowest-cost", "Basic", 5, "10/10", 19, 4, 76)
    assert comparison[2] == ("lowest-cost", "Advanced", 3, "2/2", 18.5, 4, 74)
    assert comparison[3] == ("lowest-cost", "Both levels", 8, "12/12", 37.5, 4, 150)
    assert comparison[4] == ("shortest-time", "Basic", 2.5, "10/10", 45, 4, 180)
    assert comparison[5] == ("shortest-time", "Advanced", 1.25, "2/2", 40, 4, 160)
    assert ("lowest-cost", "Basic", "Provider A", 10.25, 41) in book["Providers"].values
    assert ("shortest-time", "Advanced", "Provider C", 40, 160) in book["Providers"].values
    assert book["Offers"]["D2"].value == "=1+1 <script>alert(1)</script>"
    assert book["Offers"]["D2"].data_type == "s"
    assert book["Comparison"]["E2"].number_format == "0.00"
    assert book["Inputs"]["B2"].value == "USD"
    book.close()


def test_selected_alternative_changes_assignment_duration(cli):
    invoke, out = cli
    assert invoke("--strategy", "shortest-time") == 0
    records = json.loads((out / "basic-lms.json").read_text(encoding="utf-8"))
    assert records[0]["duration_minutes"] == 150
    path = (out / "learning-path.md").read_text(encoding="utf-8")
    assert "Selected alternative **shortest-time**" in path


def test_valid_incomplete_catalog_clears_stale_lms_records(cli, inputs, capsys):
    invoke, out = cli
    assert invoke() == 0
    directory, data, _, _ = inputs
    data["entries"] = [data["entries"][0]]
    dump(directory / "offers.yml", data)
    assert invoke() == 0
    assert "LMS files contain zero assignments" in capsys.readouterr().out
    assert json.loads((out / "basic-lms.json").read_text(encoding="utf-8")) == []
    assert (out / "basic-lms.csv").read_text(encoding="utf-8").splitlines() == [
        ",".join(LMS_FIELDS),
    ]
    md = (out / "learning-path.md").read_text(encoding="utf-8")
    assert "### Coverage gaps" in md
    assert "No introductory offer" in md and "No offer meets" in md
    html = (out / "overview.html").read_text(encoding="utf-8")
    assert "Coverage gaps" in html and "LMS export withheld" in html
    assert "Gaps to close before assignment" in (
        out / "basic-training-basis.md"
    ).read_text(encoding="utf-8")


def test_custom_catalog_price_source_label(cli, inputs):
    invoke, out = cli
    directory, data, _, _ = inputs
    data["sample_data"] = False
    dump(directory / "offers.yml", data)
    assert invoke() == 0
    html = (out / "overview.html").read_text(encoding="utf-8")
    assert "Estimates from the supplied catalog." in html
    assert "Fictional providers" not in html
    book = load_workbook(out / "cost-comparison.xlsx")
    assert book["Inputs"]["B4"].value == "Supplied catalog"
    book.close()


def test_broken_catalog_reports_error_and_writes_no_exports(cli, inputs, capsys):
    invoke, out = cli
    directory, data, _, _ = inputs
    data["entries"][0]["duration_hours"] = "two"
    dump(directory / "offers.yml", data)
    with pytest.raises(SystemExit, match="2"):
        invoke()
    assert "offers.yml: entry 1 (a-cheap): duration_hours" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("size", ["0", "-3", "100001"])
def test_invalid_group_size_fails_before_export(cli, capsys, size):
    invoke, out = cli
    with pytest.raises(SystemExit, match="2"):
        invoke("--group-size", size)
    assert "group size must be between 1 and 100000" in capsys.readouterr().err
    assert not out.exists()
