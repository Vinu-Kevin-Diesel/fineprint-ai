"""Tests for ingestion heuristics (no LLM/API involved)."""

from app.extract_text import looks_garbled


def test_clean_prose_is_not_garbled():
    text = (
        "This residential lease agreement requires the tenant to pay a security "
        "deposit of two months' rent, due before the lease is signed. Late fees apply."
    )
    assert looks_garbled(text) is False


def test_mis_decoded_font_glyphs_are_garbled():
    # The kind of symbol junk pypdf emits for custom/ligature font encodings.
    text = "❆✠✴☎✂✂ ✟✡☎☛✒✁✂☎ ✤☛✟✁✑✁✡☎✔ ✑✥ ✴✝✒✓ ✁✘✓ ✔✛☛✁✠✣ ✡☎ ✡☎☛✗ ✟✘ ✡✁✂ ✄☎✝✂☎"
    assert looks_garbled(text) is True


def test_empty_text_is_garbled():
    assert looks_garbled("   \n  ") is True
