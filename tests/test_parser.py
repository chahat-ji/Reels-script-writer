"""
tests/test_parser.py
Unit tests for screenplay element parser and metrics extractor in app/generation/parser.py.
Strictly offline, 0 external calls.
"""

from app.generation.parser import calculate_screenplay_metrics, parse_screenplay_elements


def test_parse_screenplay_elements_complete():
    script_text = (
        "# Title: Test Comedy\n"
        "INT. COFFEE SHOP - DAY\n"
        "\n"
        "RAHUL enters holding a broken laptop.\n"
        "\n"
        "RAHUL\n"
        "(whispering anxiously)\n"
        "Did anyone see what happened?\n"
        "\n"
        "PRIYA\n"
        "Only everyone on Wi-Fi.\n"
        "\n"
        "BLACKOUT.\n"
    )

    elements = parse_screenplay_elements(script_text)

    types = [e["type"] for e in elements]
    assert "meta" in types
    assert "slugline" in types
    assert "action" in types
    assert "character" in types
    assert "parenthetical" in types
    assert "dialogue" in types
    assert "button" in types
    assert "blank" in types

    # Check specific values
    slug = next(e for e in elements if e["type"] == "slugline")
    assert slug["text"] == "INT. COFFEE SHOP - DAY"

    char1 = next(e for e in elements if e["type"] == "character")
    assert char1["text"] == "RAHUL"

    button = next(e for e in elements if e["type"] == "button")
    assert button["text"] == "BLACKOUT."


def test_calculate_screenplay_metrics():
    script_text = (
        "INT. OFFICE - MORNING\n"
        "AMIT\n"
        "Why is the server down again?\n"
        "NEHA\n"
        "Because someone spilled chai on the router.\n"
        "FADE OUT."
    )

    metrics = calculate_screenplay_metrics(script_text)
    assert metrics["word_count"] > 10
    assert metrics["est_duration_sec"] >= 15
    assert metrics["scene_count"] == 1
    assert set(metrics["characters"]) == {"AMIT", "NEHA"}
    assert metrics["total_elements"] > 0


def test_calculate_screenplay_metrics_empty():
    metrics = calculate_screenplay_metrics("")
    assert metrics["word_count"] == 0
    assert metrics["est_duration_sec"] == 0
    assert metrics["scene_count"] == 0
    assert metrics["characters"] == []

