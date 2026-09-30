"""The design document must quote every Jev question exactly as the code sends it."""
from pathlib import Path

import pytest

import match

DESIGN = (Path(__file__).resolve().parent.parent / "DESIGN.md").read_text()
CASES = [(f"{table}.{name}", q) for table, qs in match.QUESTIONS.items() for name, q in qs.items()]


@pytest.mark.parametrize("name,question", CASES)
def test_design_quotes_the_question_verbatim(name, question):
    for text in [question.instructions, *(question.criteria or [])]:
        assert text in DESIGN, f"{name}: DESIGN.md does not quote: {text}"
