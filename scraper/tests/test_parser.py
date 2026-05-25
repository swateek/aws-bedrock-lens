from pathlib import Path

from bs4 import BeautifulSoup

from parser import (
    build_display_name_lookup,
    extract_rows,
    normalize_name,
    parse_price,
    per_1m_to_per_1k,
    resolve_name_to_model_id,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_price_and_conversion():
    assert parse_price("$ 0.50") == 0.5
    assert parse_price("N/A") is None
    assert per_1m_to_per_1k(0.5) == 0.0005


def test_normalize_name_strips_extended_access():
    raw = "Claude 3.5 Sonnet v2 (Public Extended Access, Effective 1 Dec 2025)"
    assert normalize_name(raw) == "Claude 3.5 Sonnet v2"


def test_catalog_driven_name_lookup():
    catalog = {
        "models": [
            {
                "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "display_name": "Claude 3.5 Sonnet v2",
            }
        ]
    }
    lookup = build_display_name_lookup(catalog)
    assert (
        resolve_name_to_model_id("Claude 3.5 Sonnet v2", lookup)
        == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    )


def test_extract_mistral_table():
    html = (FIXTURES / "mistral_us_table.html").read_text(encoding="utf-8")
    catalog = {
        "models": [
            {
                "model_id": "mistral.mistral-large-2407-v1:0",
                "display_name": "Mistral Large 3",
            }
        ]
    }
    rows, unmapped = extract_rows(BeautifulSoup(html, "html.parser"), catalog)
    by_id = {r["model_id"]: r for r in rows}
    assert "mistral.mistral-large-2407-v1:0" in by_id
    assert by_id["mistral.mistral-large-2407-v1:0"]["pricing"]["input_per_1k"] == 0.0005
    assert "Mistral Large 3" not in unmapped


def test_skips_extended_access_rows():
    html = (FIXTURES / "extended_access.html").read_text(encoding="utf-8")
    rows, unmapped = extract_rows(BeautifulSoup(html, "html.parser"), None)
    assert rows == []
    assert unmapped == []


def test_unmapped_rows_reported():
    html = """<table><tr><th>Model</th><th>In</th><th>Out</th></tr>
    <tr><td>Unknown Future Model XYZ</td><td>$1.00</td><td>$2.00</td></tr></table>"""
    rows, unmapped = extract_rows(BeautifulSoup(html, "html.parser"), {"models": []})
    assert rows == []
    assert unmapped == ["Unknown Future Model XYZ"]
