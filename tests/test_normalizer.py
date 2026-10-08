"""
tests/test_normalizer.py
Unit tests for the defensive timestamp normalizer.
Verifies detection and repair of LLM MM:SS concatenation artifacts,
turn monotonicity, and scene boundary encapsulation.
"""

from app.extraction.normalizer import (
    normalize_timestamp_ms,
    normalize_scene_turns,
    normalize_extraction,
)
from app.models.extraction import (
    VideoExtraction,
    CompactScene,
    SpeakerEntry,
    CompactCreativeDynamics,
)


def test_normalize_timestamp_under_one_minute():
    """Timestamps under 60 seconds should remain unchanged."""
    assert normalize_timestamp_ms(0) == 0
    assert normalize_timestamp_ms(1500) == 1500
    assert normalize_timestamp_ms(36000) == 36000
    assert normalize_timestamp_ms(59999) == 59999


def test_normalize_timestamp_concatenation_patterns():
    """Verify correction of MM:SS concatenated into hundreds of seconds."""
    # 1:08 -> 68s -> 68,000 ms
    assert normalize_timestamp_ms(108000) == 68000

    # 1:09 -> 69s -> 69,000 ms
    assert normalize_timestamp_ms(109000) == 69000

    # 1:13.1 -> 73.1s -> 73,100 ms
    assert normalize_timestamp_ms(113100) == 73100

    # 1:35 -> 95s -> 95,000 ms
    assert normalize_timestamp_ms(135000) == 95000

    # 2:15 -> 135s -> 135,000 ms
    assert normalize_timestamp_ms(215000) == 135000


def test_normalize_with_max_duration_clamping():
    """Timestamps exceeding total video duration should be corrected or clamped."""
    max_dur = 96336

    # 108000 ms > 96336 ms -> converts to 68000 ms (fits within video)
    assert normalize_timestamp_ms(108000, max_dur) == 68000

    # 136000 ms -> converts to 96000 ms (fits within video)
    assert normalize_timestamp_ms(136000, max_dur) == 96000

    # An invalid timestamp that cannot be converted should clamp to max_dur
    assert normalize_timestamp_ms(999999, max_dur) == max_dur


def test_normalize_turns_ordering_and_duration():
    """Verify turns are strictly monotonic and have positive duration."""
    raw_turns = [
        [60600, 108000, "B", "Chhodo na Nani!", "pleading"],
        [109000, 110800, "A", "Oye galti!", "accusing"],
    ]
    max_dur = 96336

    clean = normalize_scene_turns(raw_turns, max_duration_ms=max_dur)
    assert len(clean) == 2

    turn1 = clean[0]
    assert turn1[0] == 60600
    assert turn1[1] == 68000  # Corrected from 108000
    assert turn1[1] > turn1[0]

    turn2 = clean[1]
    assert turn2[0] == 69000  # Corrected from 109000
    assert turn2[1] == 70800  # Corrected from 110800
    assert turn2[0] >= turn1[1]


def test_normalize_full_extraction_model():
    """Verify end-to-end normalization on VideoExtraction Pydantic model."""
    extraction = VideoExtraction(
        v=1,
        sp=[SpeakerEntry(c="A", n="Speaker A"), SpeakerEntry(c="B", n="Speaker B")],
        sc=[
            CompactScene(
                s=36000,
                e=108000,
                loc="Kitchen",
                sit="Argument",
                x=[
                    [60600, 108000, "B", "Line 1"],
                ],
            ),
            CompactScene(
                s=108000,
                e=136000,
                loc="Living room",
                sit="Con",
                x=[
                    [109000, 110800, "A", "Line 2"],
                    [130800, 135000, "B", "Line 3"],
                ],
            ),
        ],
        cd=CompactCreativeDynamics(mech=["status-reversal"]),
        lang="hi",
    )

    clean_ext = normalize_extraction(extraction, max_duration_ms=96336)
    assert isinstance(clean_ext, VideoExtraction)

    # Scene 1 check
    assert clean_ext.sc[0].e == 68000
    assert clean_ext.sc[0].x[0][1] == 68000

    # Scene 2 check
    assert clean_ext.sc[1].s == 68000
    assert clean_ext.sc[1].e == 96000
    assert clean_ext.sc[1].x[0][0] == 69000
    assert clean_ext.sc[1].x[1][1] == 95000
