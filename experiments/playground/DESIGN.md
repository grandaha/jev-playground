# Design: Jev playground

The playground is a tool, not a use case. It is a local web page for writing a state and a set of questions by hand, sending them to Jev and reading the answers. It has no pipeline, no dataset and no decisions. Use it to try a question before it goes into an experiment, or to replay one request from an experiment and change it.

Run it from the repo root with `.venv/bin/python experiments/playground/scripts/server.py`. It serves the page at `http://127.0.0.1:8765/`.

## Where Jev is used, and why

### The one call: Run

**Where it sits.** Each press of Run (or Cmd/Ctrl+Enter) sends one request to `POST /v1/systemone`. Code checks the questions first. It refuses to send if an id is empty or repeated, or if instructions are empty. It also refuses a Choice with no options and a Score with fewer than 2 or more than 10 levels. Nothing else happens before or after the call.

**The state sent in.** Whatever the user typed in the State pane. If the text parses as a JSON object or array, it is sent as that JSON value. Otherwise it is sent as a string. The status line under the pane says which.

**The questions.** Whatever the user built in the Questions pane, in the exact API shapes:

- Noul: `{type: "noul", instructions, criteria?: {true?, false?}}`. Criteria are sent only when the user fills in what yes or no means.
- Choice: `{type: "choice", instructions, criteria: {option: description or null}}`.
- Score: `{type: "score", instructions, criteria: [level 0, level 1, ...]}`, lowest level first.

Instructions and criteria are sent as text, unless the text starts with `{` or `[` and parses as JSON. Then they are sent as structured JSON, which the API accepts. The Request JSON view shows the exact body before it is sent. There are no fixed questions to quote, except the presets below.

**What code does with each answer.** Code only displays answers.

- Noul: the yes probability as a number, a bar from 0 to 1 with the midpoint marked, and a reading. A value of 0.9 or more is a strong yes, 0.6 or more leans yes, above 0.4 is near even, above 0.1 leans no, and the rest is a strong no.
- Choice: the chosen option, a bar per option sorted by probability, and the confidence.
- Score: the score placed on a scale of the levels, a bar per level with its probability, the nearest level's text, and the confidence.
- Every run: the model that answered, input and output tokens, round-trip time and the raw response. The run is added to History.

**Why a model is needed.** No code path stands in for Jev here. The point of the tool is to see Jev's answers directly.

### What Jev never decides

Nothing. The page never acts on an answer. It does not route, close, merge or rank anything. The reading thresholds above only label the display.

## Presets

The use case selector has an Examples group with three presets:

- Support ticket (SDK quickstart) is the support ticket from the TypeSafe Python SDK quickstart, with a billing Noul, a tone Choice and an urgency Score.
- Security alert ALT-00062 (security-alert-triage) uses alert ALT-00062 from `experiments/security-alert-triage/data/source/alerts.csv`, with the state built by `alert_state` and the questions from `ALERT_QUESTIONS` in `scripts/ask.py`. It is a real exfiltration alert that no allowlist rule settles, so the pipeline asks Jev about it.
- Account pair A00002 / A00146 (customer-matching) uses two account records from `experiments/customer-matching/data/work/accounts_norm.csv`, with the state built by `view` and the account questions from `QUESTIONS` in `scripts/match.py`. No hard rule settles the pair, so the pipeline asks Jev about it.

The two experiment presets are byte-for-byte the state and questions those pipelines send. `tests/test_playground.py` rebuilds them from the pipelines' own code and data and fails if a preset drifts. The same file checks that this document names every preset, the address and the run command.

## Server

`scripts/server.py` uses only the Python standard library.

- **Key.** It reads `TYPESAFE_API_KEY` from the repo root `.env`, or from the environment when the file has no key. If neither has one, it prints a message and exits. The key never reaches the browser and is never printed.
- **Proxy.** `POST /run` goes to `/v1/systemone` and `GET /models` goes to `/v1/models`. The API's status and JSON body come back unchanged, errors included.
- **Guard.** The server listens on 127.0.0.1 only. It refuses a request whose Host or Origin is not this server, and a POST that is not JSON. Another web page open in the same browser therefore cannot spend tokens through it.
- **Browser storage.** Saved use cases and the last 50 runs (request, response, time and tokens) are kept in the browser's localStorage. Nothing is stored on the server.

## What it does not do

- No batch runs. One state, one request per Run.
- No accounts or sharing. It is for one person on one machine.
- The editors reset on reload. Save a use case, or restore a run from History.

## Cost

Every run spends input tokens. In the three test runs, all on jev-1.13.0, input and output tokens were as follows:

| Run | Input tokens | Output tokens |
|---|---|---|
| Support ticket preset, 3 questions | 367 | 75 |
| Security alert preset, 4 questions | 1,085 | 235 |
| One Score question with one level | 284 | 17 |

The API accepted the one-level Score with HTTP 200. The page still requires 2 to 10 levels, as the docs advise.
