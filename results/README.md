# us-sut-reconciliation-v1 — eval results

**Eval set:** the first 30 tasks of the default taskset (seeds 20260701–20260730). Each ledger has 30 rows plus injected
duplicates (31.2 rows on average) and the default fault rate of 0.25. In total that is 199 gold `(txn, fault)` pairs
across all six codes.
**Harness:** `null` (plain chat, no tools), `subprocess` runtime, `verifiers` 0.4.0, one rollout per task.
**Run date:** 2026-10-28.

## Summary

| run | n | reward | return_correct | fault_audit (F1) | fault P | fault R | fields_correct | parsed | lenient reward* | lenient F1* | lenient fields* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| oracle | 30 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| naive-bookkeeper | 30 | 0.013 | 0.000 | 0.033 | 0.033 | 0.033 | 0.113 | 1.000 | 0.013 | 0.033 | 0.113 |
| qwen2.5-3b-instruct-q4km | 30 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.029 | 0.071 | 0.007 |

\* Diagnostic only: also accepts a bare JSON object when the `<answer>` tags are missing.

Per-fault recall, lenient parse (hits / gold):

| run | duplicate_invoice | missing_exemption_cert | nexus_misallocation | outside_period | tax_miscalculated | tax_on_exempt_item |
|---|---|---|---|---|---|---|
| oracle | 31/31 | 45/45 | 29/29 | 40/40 | 22/22 | 32/32 |
| naive-bookkeeper | 0/31 | 0/45 | 0/29 | 0/40 | 0/22 | 0/32 |
| qwen2.5-3b-instruct-q4km | 9/31 | 3/45 | 0/29 | 0/40 | 0/22 | 0/32 |

`reward = 0.6·return_correct + 0.4·fault_audit`. `fields_correct` is the fraction of the five return figures that
match to the cent. `parsed` is the share of rollouts with a valid `<answer>{json}</answer>` block.

## Policies

| Run | What it is |
|---|---|
| `oracle` | Stub endpoint (`scripts/oracle_server.py`) that answers with `reconcile()` ground truth. It is the upper bound and an end-to-end wiring check. |
| `naive-bookkeeper` | Stub that files the ledger as recorded: it sums every sale line and its recorded tax, accrues no use tax and flags nothing. It is the lower bound. |
| `qwen2.5-3b-instruct-q4km` | Qwen2.5-3B-Instruct (Q4_K_M GGUF) served by llama.cpp on 4 CPU cores. Temperature 0, max 2048 tokens. |

## Findings

- **The env is well-posed.** The oracle scores 1.000 on every task through the full `vf-eval` → harness → reward path.
  The naive bookkeeper scores 0.013, and its only points come from a fault-free ledger where an empty fault map is
  correct.
- **The roll-up is the hard part, as the design intends.** No policy other than the oracle gets a single return
  exactly right (`return_correct` = 0). The naive bookkeeper matches 11% of individual figures, mostly `use_tax_due`
  or `gross_sales` on ledgers without duplicates or out-of-period rows.
- **The 3B model fails the output contract.** In 0 of 30 rollouts did Qwen2.5-3B emit the required `<answer>` tags,
  so it scores 0 under the strict reward. In 28 rollouts it answered with bare JSON straight away (no worked
reasoning). In the other 2 it wrote arithmetic expressions inside the JSON, which made the JSON invalid. Even with a
  lenient parse it reaches only 0.071 fault F1 and 0.7% field accuracy. It finds some `duplicate_invoice` (9/31) and
  `missing_exemption_cert` (3/45) faults, finds no rate-based fault (`tax_miscalculated`, `nexus_misallocation`,
  `tax_on_exempt_item`), and finds no `outside_period` fault. Those categories need per-row arithmetic that a 3B
  model answering in one shot does not do.
- **A reward loophole was fixed during this run.** An unparseable answer used to count as an empty fault map, which
  earns F1 = 1.0 on a fault-free ledger (task 3 scored 0.4 that way). Unparsed answers now score 0 on
  `fault_audit`. All three runs above were re-scored with `vf-replay` against the fixed rubric, and the published
  `traces.jsonl` files are those re-scored traces.

## Caveats

- No frontier-model API key was available in the environment that produced these runs, so the only LLM measured
  is a small local model. The F1-vs-roll-up gap the design predicts for instruction-tuned frontier models
  (high F1, low exact-return rate) is **not yet measured**. Reproduce it with the command below against any
  OpenAI-compatible endpoint.
- The jurisdiction is an illustrative rulebook with stylized rates. It is not current statutory law.

## Reproduce

```bash
uv pip install -e environments/us_sut_reconciliation_v1
uv run vf-eval us-sut-reconciliation-v1 -m <model> -n 30 -c 8 --env.agent.harness.id null \
  --env.agent.runtime.type subprocess --client.base-url <url> --client.api-key-var <KEY_VAR> --no-push
python scripts/summarize.py outputs/<run-dir>
```

Each `results/<run>/` folder holds the resolved `eval-config.json` and the per-rollout `traces.jsonl` (full transcripts,
rewards and metrics).
