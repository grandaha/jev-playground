# Jev playground

Scratch space for trying use cases with Jev (TypeSafe System One). One script per use case in `experiments/`.

- Python venv: `.venv` (3.13). Run with `.venv/bin/python experiments/<name>.py`.
- API key lives in `.env` as `TYPESAFE_API_KEY` (gitignored). Never commit or print it.
- SDK: `typesafe-sdk`. Live docs: https://docs.typesafe.ai/llms.txt. Load the `typesafe:typesafe-ai` skill before designing questions.
