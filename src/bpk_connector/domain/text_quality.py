"""How well a text's article headings survived OCR: the damage that reaches the structure parser.

A PDF's text layer may itself be the publisher's OCR, so "it has a text layer" says nothing about
its quality. BPK's do carry damaged headings ("Pasa122" for Pasal 22), and the parser amplifies
each one: articles may only increase, so one misread heading in the KUHP hid every real article
below it (6,500 problem lines). Measured on every BPK text held on 2026-10-16: each file with a
damaged heading went to the review queue, and no file without one did. OCR character noise in body
text did not separate the two, so it isn't scored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# An inserted article takes a letter (Pasal 7B); never O, which in "Pasal 1O" is a zero misread.
CLEAN_HEADING = re.compile(r"(?m)^[ \t]*Pasal[ \t]+\d+[A-NP-Z]?[ \t]*$")
DAMAGED_HEADING = re.compile(
    r"(?m)^[ \t]*(?:"
    r"Pasa[^l\s]?[ \t]*\d[\dIlOSB]*"  # Pasa122, Pasa1 5, Pasa|279, PasaJ442: the l of "Pasal" misread or lost
    r"|Pasal[ \t]+\d+[ \t]+[\dIlO]"  # Pasal 2 I, Pasal 1 1: one number split in two
    r"|Pasal[ \t]+(?:\d+[OIlSB]\d+|[OIlSB]\d+|\d+[Ol])"  # Pasal 1O0, I5, 2O, 1l; not Roman II nor inserted 7B
    r"|P[ \t]+a[ \t]+s[ \t]+a[ \t]+l[ \t]+\d+"  # letter-spaced
    r")[ \t.]*$"  # a page's catchword ("Pasal 207 ...") damaged the same way counts too
)


@dataclass(frozen=True)
class TextQuality:
    clean_headings: int  # "Pasal N" read as such
    damaged_headings: int

    @property
    def is_damaged(self) -> bool:
        return self.damaged_headings > 0

    def reads_better_than(self, other: TextQuality) -> bool:
        """Better on both counts: more headings read cleanly, and fewer damaged.

        Fewer damaged headings alone isn't better: a garbled or blank reading has no damaged headings
        because it finds hardly any heading at all.
        """
        return self.clean_headings > other.clean_headings and self.damaged_headings < other.damaged_headings


def assess(text: str) -> TextQuality:
    return TextQuality(len(CLEAN_HEADING.findall(text)), len(DAMAGED_HEADING.findall(text)))
