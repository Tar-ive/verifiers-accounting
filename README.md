# verifiers-accounting

Accounting and tax-compliance RL environments for Prime Intellect's
[`verifiers`](https://github.com/PrimeIntellect-ai/verifiers) (v1 stack).

| Environment | What it tests |
|---|---|
| [`us-sut-reconciliation-v1`](environments/us_sut_reconciliation_v1/README.md) | US state sales & use tax return reconciliation plus a fault audit over a synthetic quarterly ledger (US analogue of `au-bas-reconciliation-v1`) |

- `scripts/oracle_server.py` serves reference policies (ground-truth oracle, naive bookkeeper) through an OpenAI-compatible endpoint.
- `scripts/summarize.py` turns `vf-eval` run dirs into results tables.
- [`results/`](results/README.md) holds the published eval runs.
