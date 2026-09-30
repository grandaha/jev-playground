"""The design document must quote every Jev question exactly as the code sends it."""
from pathlib import Path

import pytest

import ask

DESIGN = (Path(__file__).resolve().parent.parent / "DESIGN.md").read_text()
QUESTIONS = {**ask.ALERT_QUESTIONS, **getattr(ask, "LINK_QUESTIONS", {})}


def texts(question):
    criteria = question.criteria
    if isinstance(criteria, dict):   # Choice: option name -> description
        criteria = list(criteria.values())
    return [question.instructions, *(criteria or [])]   # Score: list of levels; Noul: none


@pytest.mark.parametrize("name,question", list(QUESTIONS.items()))
def test_design_quotes_the_question_verbatim(name, question):
    for text in texts(question):
        assert text in DESIGN, f"{name}: DESIGN.md does not quote: {text}"
