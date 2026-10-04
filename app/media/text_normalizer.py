"""
app/media/text_normalizer.py
Natural conversational Roman Hinglish transliterator with Hindi schwa deletion.
"""

import re
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")


def contains_devanagari(text: str) -> bool:
    return bool(DEVANAGARI_RANGE.search(text))


def devanagari_to_roman(text: str) -> str:
    """
    Converts Hindi Devanagari into natural conversational Roman Hinglish.
    Example: 'ओए देख तेरे डब्बे में' -> 'oye dekh tere dabbe me'
    """
    if not text or not contains_devanagari(text):
        return text

    # Standardize vowel signs & nuktas before transliterating
    text = text.replace("ॉ", "o").replace("ऑ", "o").replace("ॅ", "e")

    # Transliterate via ITRANS
    raw = transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)

    # Convert common Sanskrit/ITRANS markers to natural Hindi conversational forms
    cleaned = raw
    cleaned = re.sub(r"\.n", "n", cleaned)
    cleaned = re.sub(r"M", "n", cleaned)
    cleaned = re.sub(r"~N|~n|N", "n", cleaned)

    # Fix nasalized forms
    cleaned = re.sub(r"mem\b", "me", cleaned)
    cleaned = re.sub(r"haim\b", "hain", cleaned)
    cleaned = re.sub(r"hum\b|hu\.n\b", "hoon", cleaned)

    # Schwa Deletion: Remove unnecessary silent 'a' at word endings
    # e.g., 'dekha' -> 'dekh', 'kucha' -> 'kuch', 'dasa' -> 'das', 'logam' -> 'log'
    cleaned = re.sub(r"([bcdfghjklmnpqrstvwxyz])a\b", r"\1", cleaned, flags=re.IGNORECASE)

    # Word-level natural phonetic normalization
    replacements = [
        (r"\bmai[nm]\b", "maine"),
        (r"\bkoI\b", "koi"),
        (r"\bchupa\b", "chup"),
        (r"\bkucha\b", "kuch"),
        (r"\bhama\b", "hum"),
        (r"\bhamaloga\b", "humlog"),
        (r"\bhama\b", "hum"),
        (r"\bplija\b", "please"),
        (r"\bchiza\b", "cheese"),
        (r"\bbaॉlsa\b", "balls"),
        (r"\bchaza\b", "cheez"),
        (r"\bsaॉri\b", "sorry"),
        (r"\bnota\b", "note"),
        (r"\bpaiketa\b", "packet"),
        (r"\bsharma\b", "sharam"),
        (r"\bgariba\b", "gareeb"),
        (r"\bijjatadara\b", "izzatdaar"),
        (r"\bde\.dha\b", "dedh"),
    ]

    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    # Final cleanup: lowercase, remove orphan artifacts, trim spaces
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[\|\।\॥]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned