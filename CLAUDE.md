# Jev playground

Scratch space for trying use cases with Jev (TypeSafe System One). One directory per use case in `experiments/<name>/` with its own README.md, DESIGN.md, `scripts/` and one sample dataset in `data/`.

- Python venv: `.venv` (3.13). Run with `.venv/bin/python experiments/<name>/scripts/<script>.py`, or a use case's `run_all.sh`.
- API key lives in `.env` as `TYPESAFE_API_KEY` (gitignored). Never commit or print it.
- SDK: `typesafe-sdk`. Live docs: https://docs.typesafe.ai/llms.txt. Load the `typesafe:typesafe-ai` skill before designing questions.

## Design documents
A design document for a Jev experiment must say exactly how Jev is used and why. For every place Jev is called, state five things:
- Where the call sits in the pipeline, and what code settles without it.
- The state sent in.
- Each question verbatim, with its type and answer options.
- What code does with each answer.
- Why a model is needed there instead of code.

Also list what Jev never decides. Every question needs a stated job. Quote the questions exactly as they appear in the code. Keep a test that fails when the document and the code differ (see `tests/test_design_matches_code.py`).
