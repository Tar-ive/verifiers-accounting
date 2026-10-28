"""Summarize vf-eval run dirs (traces.jsonl) into a markdown table + per-fault recall.

Usage: python scripts/summarize.py <run_dir> [<run_dir> ...] > results.md
"""

import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev

from us_sut_reconciliation_v1.taskset import RETURN_FIELDS, fault_pairs, parse_answer, to_cents


def lenient(text: str) -> dict | None:
    """Diagnostic only (not the reward): accept a bare JSON object when the <answer> tags are missing."""
    parsed = parse_answer(text)
    if parsed is not None:
        return parsed
    start, end = text.find("{"), text.rfind("}")
    try:
        obj = json.loads(text[start:end + 1]) if start != -1 else None
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def f1(pred: set, gold: set) -> float:
    if not pred and not gold:
        return 1.0
    hits = len(pred & gold)
    return 2 * hits / (len(pred) + len(gold)) if hits else 0.0


def final_text(trace: dict) -> str:
    replies = [n["message"] for n in trace.get("nodes", []) if n.get("message", {}).get("role") == "assistant"]
    if not replies:
        return ""
    content = replies[-1].get("content")
    return content if isinstance(content, str) else "".join(p.get("text", "") for p in content or [])


def load(run_dir: Path) -> list[dict]:
    rows = []
    for line in (run_dir / "traces.jsonl").read_text().splitlines():
        episode = json.loads(line)
        trace = episode["traces"][0]
        rewards = {k: v["score"] for k, v in trace["rewards"].items()}
        reward = sum(v["score"] * v["weight"] for v in trace["rewards"].values())
        rows.append({"task": episode["task"]["data"], "reward": reward, **rewards, **trace["metrics"],
                     "text": final_text(trace), "out_tokens": trace.get("num_output_tokens") or 0})
    return rows


def rollout_std(rows: list[dict], key: str) -> str:
    """Std (population) across rollout means: the k-th episode of each task is rollout k. '-' with one rollout."""
    seen: Counter = Counter()
    by_rollout: dict[int, list[float]] = {}
    for r in rows:
        k = seen[r["task"]["idx"]]
        seen[r["task"]["idx"]] += 1
        by_rollout.setdefault(k, []).append(r.get(key, 0.0))
    means = [mean(v) for v in by_rollout.values()]
    return f"{pstdev(means):.3f}" if len(means) > 1 else "-"


def main(dirs: list[str]) -> None:
    print("| run | n | reward | reward σ† | return_correct | fault_audit (F1) | fault P | fault R | fields_correct | parsed "
          "| lenient reward* | lenient F1* | lenient fields* |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    per_code: dict[str, tuple[Counter, Counter]] = {}
    for d in dirs:
        rows = load(Path(d))
        for r in rows:
            exp, ans = r["task"]["expected"], lenient(r["text"])
            ok = [ans is not None and to_cents(ans.get(f)) == to_cents(exp[f]) for f in RETURN_FIELDS]
            r["l_f1"] = f1(fault_pairs(ans.get("faults")), fault_pairs(exp["faults"])) if ans is not None else 0.0
            r["l_fields"] = sum(ok) / len(ok)
            r["l_reward"] = 0.6 * all(ok) + 0.4 * r["l_f1"]
        m = lambda k: mean(r.get(k, 0.0) for r in rows)
        print(f"| {Path(d).name} | {len(rows)} | {m('reward'):.3f} | {rollout_std(rows, 'reward')} | {m('return_correct'):.3f} | {m('fault_audit'):.3f} "
              f"| {m('fault_precision'):.3f} | {m('fault_recall'):.3f} | {m('fields_correct'):.3f} | {m('answer_parsed'):.3f} "
              f"| {m('l_reward'):.3f} | {m('l_f1'):.3f} | {m('l_fields'):.3f} |")
        gold_c, hit_c = Counter(), Counter()
        for r in rows:
            gold = fault_pairs(r["task"]["expected"]["faults"])
            answer = lenient(r["text"]) or {}
            pred = fault_pairs(answer.get("faults"))
            gold_c.update(code for _, code in gold)
            hit_c.update(code for _, code in gold & pred)
        per_code[Path(d).name] = (gold_c, hit_c)
    codes = sorted({c for g, _ in per_code.values() for c in g})
    print("\n† Std across the per-rollout mean rewards (`-r` > 1 only); n counts episodes (tasks × rollouts).")
    print("\n\\* Diagnostic only: also accepts a bare JSON object when the `<answer>` tags are missing.")
    print("\nPer-fault recall, lenient parse (hits / gold):\n")
    print("| run | " + " | ".join(codes) + " |")
    print("|---|" + "---|" * len(codes))
    for name, (gold_c, hit_c) in per_code.items():
        print(f"| {name} | " + " | ".join(f"{hit_c[c]}/{gold_c[c]}" for c in codes) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
