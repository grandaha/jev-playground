# Jev playground UI

A small local web app for trying Jev questions by hand. Write a state, build Noul, Choice and Score questions, run them, and read the answers the way the docs describe them: a Noul as a yes probability on a 0 to 1 bar, a Choice as the picked option with every option's probability and the confidence, a Score as a position on your levels with a probability per level and the confidence.

## Run

From the repo root:

```bash
.venv/bin/python playground/server.py
```

It opens http://127.0.0.1:8765/ in your browser. The server uses only the Python standard library.

## What it does

- `server.py` reads `TYPESAFE_API_KEY` from the repo root `.env` (or the environment), serves the page and forwards `POST /run` to `https://api.typesafe.ai/v1/systemone` and `GET /models` to `/v1/models`. The API's status and JSON body come back unchanged, errors included.
- The key stays on the server. The browser never sees it, and the server refuses requests from other web pages.
- Use cases are saved in your browser's localStorage. Export and Import use `{name, model, state, questions}`, where `state` and `questions` are exactly the API shapes, so an exported file is a valid request body.
- The Examples group holds the SDK quickstart support ticket and one real request from each experiment (security alert ALT-00062 and account pair A00002 / A00146), exactly as those pipelines send them. `test_playground.py` checks that against the pipelines' own code.
- The last 50 runs are kept in History. Click one to restore its state, questions and answers.
- Instructions and criteria fields accept plain text. Text that starts with `{` or `[` and parses as JSON is sent as structured JSON.

Every run costs tokens.

Check: `.venv/bin/python playground/test_playground.py`
