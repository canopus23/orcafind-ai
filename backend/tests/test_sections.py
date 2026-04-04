from app.main import _parse_sections


def test_parse_sections_four_headers():
    raw = """X:
Hello X

LinkedIn:
Hello LinkedIn

Instagram:
Hello IG #tag

Facebook:
Hello FB
"""
    sections = _parse_sections(raw)
    assert sections["x"] == "Hello X"
    assert sections["linkedin"] == "Hello LinkedIn"
    assert sections["instagram"].startswith("Hello IG")
    assert sections["facebook"] == "Hello FB"


def test_parse_sections_legacy_two_headers():
    raw = """X:
X content
LinkedIn:
LI content
"""
    sections = _parse_sections(raw)
    assert sections["x"] == "X content"
    assert sections["linkedin"] == "LI content"

