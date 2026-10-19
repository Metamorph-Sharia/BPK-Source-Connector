"""How far a text's article headings survived OCR, on headings seen in BPK's text layers (2026-10-16)."""

from __future__ import annotations

import pytest

from bpk_connector.domain.text_quality import TextQuality, assess


@pytest.mark.parametrize(
    "heading",
    [
        "Pasa122",  # "Pasal 22" with its l read as 1: the parser reads Pasal 122
        "Pasa7223",  # KUHP: one such line cost 6,500 problem lines
        "Pasa1 5",
        "PasaI 5",
        "Pasa|279",
        "Pasa] 416",
        "PasaJ442.. .",  # a damaged catchword: the next page's first heading, at the foot of a page
        "Pasat 123",
        "Pasal 1O",  # a letter O for a zero
        "Pasal I5",
        "Pasal 2 I",  # a number split in two
        "P a s a l 5",  # letter-spaced
    ],
)
def test_an_ocr_damaged_article_heading_is_counted_as_damaged(heading: str) -> None:
    assert assess(f"BAB I\n{heading}\nDalam Peraturan ini yang dimaksud dengan:") == TextQuality(0, 1)


@pytest.mark.parametrize("heading", ["Pasal 5", "Pasal 7B", "Pasal 12 ", "  Pasal 140"])
def test_a_clean_article_heading_is_counted_as_clean(heading: str) -> None:
    assert assess(f"{heading}\n(1) Setiap Orang") == TextQuality(1, 0)


@pytest.mark.parametrize(
    "line",
    [
        "Pasal II",  # an amending regulation's Roman article
        "sebagaimana dimaksud dalam Pasal 5 ayat (1)",  # a reference, not a heading
        "Pasal 5 ayat (2) huruf a",
    ],
)
def test_lines_that_are_not_damaged_headings_are_not_counted_as_damaged(line: str) -> None:
    assert assess(line).damaged_headings == 0


def test_any_damaged_heading_makes_the_text_damaged() -> None:
    # Measured: every BPK file with one went to the review queue; no file without one did.
    assert assess("Pasal 1\nPasal 2\nPasa13").is_damaged
    assert not assess("Pasal 1\nPasal 2\nPasal 3").is_damaged


def test_a_reading_is_better_when_it_reads_more_headings_cleanly() -> None:
    text_layer, ocr = TextQuality(clean_headings=13, damaged_headings=17), TextQuality(33, 0)

    assert ocr.reads_better_than(text_layer)
    assert not text_layer.reads_better_than(ocr)


def test_a_reading_that_loses_clean_headings_is_not_better_even_without_damage() -> None:
    # e.g. OCR that garbles the page: no damaged headings, because it finds hardly any heading at all
    assert not TextQuality(2, 0).reads_better_than(TextQuality(129, 1))


def test_a_reading_that_finds_nothing_is_not_better_than_a_damaged_one() -> None:
    # a blank page image: no damage left, but nothing read either
    assert not TextQuality(0, 0).reads_better_than(TextQuality(0, 2))


def test_a_reading_must_be_better_on_both_counts() -> None:
    assert not TextQuality(10, 0).reads_better_than(TextQuality(10, 2))  # where did the 2 damaged headings go?
    assert not TextQuality(40, 3).reads_better_than(TextQuality(30, 1))  # more read, but more damaged
    assert not TextQuality(10, 2).reads_better_than(TextQuality(10, 2))
