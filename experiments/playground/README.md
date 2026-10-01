# Jev playground

A small local web app for trying Jev questions by hand. Write a state, build Noul, Choice and Score questions, run them, and read the answers the way the docs describe them:

- A Noul shows as a yes probability on a bar from 0 to 1.
- A Choice shows the picked option, every option's probability and the confidence.
- A Score shows a position on your levels, the probability of each level and the confidence.

It is a tool rather than a use case, so it has no dataset. [DESIGN.md](DESIGN.md) explains how it uses Jev.

## Run

From the repo root:

```bash
.venv/bin/python experiments/playground/scripts/server.py
```

It opens http://127.0.0.1:8765/ in your browser. The server uses only the Python standard library.

## What it does

- `scripts/server.py` reads `TYPESAFE_API_KEY` from the repo root `.env`, or from the environment. It serves the page and passes requests on to TypeSafe. `POST /run` goes to `/v1/systemone` and `GET /models` goes to `/v1/models`. The API's status and JSON body come back unchanged, errors included.
- The key stays on the server. The browser never sees it, and the server refuses requests from other web pages.
- Use cases are saved in your browser's localStorage. Export and Import use `{name, model, state, questions}`. The state and questions are exactly the API shapes, so an exported file is a valid request body.
- The Examples group holds three presets. One is the SDK quickstart support ticket. The other two are real requests from the experiments: security alert ALT-00062 and account pair A00002 / A00146. Each matches what its pipeline sends, and the tests check this against the pipelines' own code.
- History keeps the last 50 runs. Select one to restore its state, questions and answers.
- Instructions and criteria fields take plain text. Text that starts with `{` or `[` and parses as JSON is sent as structured JSON.

Every run costs tokens.

## Tests

From `experiments/playground`:

```bash
../../.venv/bin/python -m pytest -q
```
