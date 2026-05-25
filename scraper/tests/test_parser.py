from pathlib import Path

from bs4 import BeautifulSoup

from parser import extract_rows, normalize_name, parse_price, per_1m_to_per_1k

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_price_and_conversion():
    assert parse_price("$ 0.50") == 0.5
    assert parse_price("N/A") is None
    assert per_1m_to_per_1k(0.5) == 0.0005


def test_normalize_name_strips_extended_access():
    raw = "Claude 3.5 Sonnet v2 (Public Extended Access, Effective 1 Dec 2025)"
    assert normalize_name(raw) == "Claude 3.5 Sonnet v2"


def test_extract_mistral_table():
    html = (FIXTURES / "mistral_us_table.html").read_text(encoding="utf-8")
    rows = extract_rows(BeautifulSoup(html, "html.parser"))
    by_id = {r["model_id"]: r for r in rows}
    assert "mistral.mistral-large-2407-v1:0" in by_id
    assert by_id["mistral.mistral-large-2407-v1:0"]["pricing"]["input_per_1k"] == 0.0005
    assert by_id["mistral.mistral-large-2407-v1:0"]["pricing"]["output_per_1k"] == 0.0015


def test_skips_extended_access_rows():
    html = (FIXTURES / "extended_access.html").read_text(encoding="utf-8")
    rows = extract_rows(BeautifulSoup(html, "html.parser"))
    assert rows == []
