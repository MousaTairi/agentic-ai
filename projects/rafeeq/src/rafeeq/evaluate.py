"""Real-provider A/B agent eval, or separately labelled offline retrieval benchmark."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .agent import run_agent
from .config import PROJECT, Settings
from .domain import decide, verify
from .retrieval import search
from .schemas import Verify
from .storage import Store


def grade(task: dict, reply, store: Store, sid: str) -> list[str]:
    failures = []
    text = reply.reply.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).replace(",", "").lower()
    if reply.stopped != task.get("expected_stop", "completed"):
        failures.append("execution:" + reply.stopped)
    for group in task.get("contains", []):
        if not any(term.lower().replace(",", "") in text for term in group):
            failures.append("answer_content")
    for term in task.get("forbidden", []):
        if term.lower() in text:
            failures.append("privacy_disclosure")
    for tool in task.get("tools", []):
        if tool not in reply.tools:
            failures.append("missing_tool:" + tool)
    for tool in task.get("forbidden_tools", []):
        if tool in reply.tools:
            failures.append("unexpected_tool:" + tool)
    for kind in task.get("ui_requests", []):
        if not any(request["type"] == kind for request in reply.ui_requests):
            failures.append("missing_chat_card:" + kind)
    if task.get("action"):
        matches = [a for a in reply.actions if a["tool"] == task["action"]]
        if not matches:
            failures.append("missing_action")
        else:
            action = matches[0]
            if task.get("confirm"):
                try:
                    result = decide(store, sid, action["id"], True)
                    if result["status"] != task["expected_status"]:
                        failures.append("action_state")
                except (PermissionError, ValueError):
                    failures.append("action_execution")
            elif action["status"] != "pending":
                failures.append("write_without_confirmation")
    if task.get("sql"):
        with store.connect() as db:
            row = db.execute(task["sql"]).fetchone()
            value = row[0] if row else None
        if value != task["expected_db"]:
            failures.append("database_assertion")
    return sorted(set(failures))


async def live(tasks: list[dict], output: Path, trials: int) -> int:
    base = Settings()
    if not base.api_key:
        print("BLOCKED: OPENROUTER_API_KEY is missing. No model evaluations were executed.")
        return 2
    if base.model == "openrouter/free":
        print("BLOCKED: Pin RAFEEQ_MODEL to a specific tool-calling model for a controlled A/B comparison.")
        return 2
    rows = []
    details = []
    for config in ("A", "B"):
        for trial in range(1, trials + 1):
            for task in tasks:
                with tempfile.TemporaryDirectory(prefix="rafeeq-eval-") as folder:
                    settings = base.model_copy(update={"runtime": Path(folder), "configuration": config})
                    store = Store(settings.runtime)
                    sid = store.new_session()
                    if task.get("verify"):
                        verify(store, sid, Verify(**task["verify"]))
                    started = time.monotonic()
                    reply = await run_agent(store, sid, task["prompt"], settings)
                    errors = grade(task, reply, store, sid)
                    rows.append({"config": config, "trial": trial, "task": task["id"],
                                 "category": task["category"], "passed": not errors,
                                 "errors": "|".join(errors), "seconds": round(time.monotonic() - started, 3),
                                 "model": settings.model, **reply.usage})
                    details.append({"config": config, "trial": trial, "task": task["id"],
                                    "reply": reply.model_dump(), "errors": errors})
                    print(config, trial, task["id"], "PASS" if not errors else errors, flush=True)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "agent-results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "transcripts.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {config: {"runs": len(selected := [r for r in rows if r["config"] == config]),
                       "passed": sum(r["passed"] for r in selected),
                       "failures": dict(Counter(e for r in selected for e in r["errors"].split("|") if e))}
               for config in ("A", "B")}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return int(any(not row["passed"] for row in rows))


def retrieval(tasks: list[dict], output: Path) -> int:
    rows = []
    for config in ("A", "B"):
        for task in tasks:
            hits = search(task["query"], config)["data"]
            ids = [h["policy_id"] for h in hits]
            rows.append({"config": config, "task": task["id"], "expected": task["policy"],
                         "top1": bool(ids and ids[0] == task["policy"]),
                         "top3": task["policy"] in ids, "retrieved": "|".join(ids)})
    output.mkdir(parents=True, exist_ok=False)
    with (output / "retrieval.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for config in ("A", "B"):
        selected = [r for r in rows if r["config"] == config]
        print(config, {"queries": len(selected), "top1": sum(r["top1"] for r in selected),
                       "top3": sum(r["top3"] for r in selected)})
        print("Retrieval misses:", [r["task"] for r in selected if not r["top3"]])
    print("RETRIEVAL ONLY: no model calls, actions or end-to-end agent behavior were evaluated.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("live", "retrieval"))
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    filename = "tasks.jsonl" if args.mode == "live" else "retrieval.jsonl"
    tasks = [json.loads(line) for line in (PROJECT / "evals" / filename).read_text(encoding="utf-8").splitlines() if line.strip()]
    output = args.output or PROJECT / "evals/results" / (args.mode + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    raise SystemExit(asyncio.run(live(tasks, output, args.trials)) if args.mode == "live" else retrieval(tasks, output))


if __name__ == "__main__":
    main()
