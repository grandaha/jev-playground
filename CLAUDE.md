# Jev playground

Scratch space for trying use cases with Jev (TypeSafe System One). One directory per use case in `experiments/<name>/` with its own spec.md, scripts and data/.

- Python venv: `.venv` (3.13). Run with `.venv/bin/python experiments/<name>/<script>.py`.
- API key lives in `.env` as `TYPESAFE_API_KEY` (gitignored). Never commit or print it.
- SDK: `typesafe-sdk`. Live docs: https://docs.typesafe.ai/llms.txt. Load the `typesafe:typesafe-ai` skill before designing questions.
