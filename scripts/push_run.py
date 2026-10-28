"""Upload a finished `vf-eval --no-push` run dir to Prime Evals, as `--push` would have live.

Usage: python scripts/push_run.py <run_dir> [<run_dir> ...]   (needs `prime login` or $PRIME_API_KEY)
"""

import json
import sys
from pathlib import Path

from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.episode import Episode
from verifiers.v1.utils.platform import PushState, finish_run, log_episodes, open_run


def push(run_dir: Path) -> None:
    config = EvalConfig.model_validate(json.loads((run_dir / "configs/resolved/eval.json").read_text()))
    config.push = True
    episodes = [Episode.model_validate_json(line) for line in (run_dir / "traces.jsonl").read_text().splitlines()]
    state = PushState()
    run = open_run(config, state, num_examples=len({e.task.data.idx for e in episodes}))
    log_episodes(run, episodes)
    finish_run(run, episodes, state)
    print(f"{run_dir.name}: {len(episodes)} episodes -> {state.url or state.error}")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        push(Path(d))
