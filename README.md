# Jev playground

Small experiments with Jev (TypeSafe System One), a decision model that returns typed answers with probabilities instead of text. Each experiment has its own folder under `experiments/`.

## Customer record matching

Finds duplicate customers in two messy, linked files, explains every decision, and builds one golden record for each real-world entity. The data is synthetic. You can replay every result with no API key.

Start with [experiments/customer-matching/README.md](experiments/customer-matching/README.md).

## Security alert triage

Triages synthetic security alerts, groups them into incidents and ranks accounts, with a rules-only baseline beside every stage. See [experiments/security-alert-triage/README.md](experiments/security-alert-triage/README.md).

## Playground UI

A local web app for writing and running Jev questions by hand, with the experiments' real requests as examples. See [playground/README.md](playground/README.md).

## License

MIT. See [LICENSE](LICENSE).
