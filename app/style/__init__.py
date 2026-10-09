"""
app/style package
Cross-video style synthesis, corpus aggregation, and versioned Style Bible generation.

Implements Sections 11, 12, 21, and 22 of description.txt.
"""

from app.style.aggregator import CorpusStats, StyleAggregator, StyleCorpus
from app.style.service import StyleService
from app.style.synthesizer import StyleSynthesizer
from app.style.versioning import StyleVersioning

__all__ = [
    "CorpusStats",
    "StyleCorpus",
    "StyleAggregator",
    "StyleSynthesizer",
    "StyleVersioning",
    "StyleService",
]

