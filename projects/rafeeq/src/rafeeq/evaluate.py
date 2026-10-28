"""Real-provider A/B agent eval, or separately labelled offline retrieval benchmark."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .agent import OpenRouter, run_agent
from .config import PROJECT, Settings
from .domain import decide, verify
from .evaluation_reporting import canonical_text, contains_expected, markdown_report, summary_for
from .retrieval import search
from .schemas import Verify
from .storage import Store


def grade(task: dict, reply, store: Store, sid: str) -> list[str]:
    failures = []
    text = canonical_text(reply.reply)
    if reply.stopped != task.get("expected_stop", "completed"):
        return ["execution:" + reply.stopped]
    for group in task.get("contains", []):
        if not any(contains_expected(text, term) for term in group):
            failures.append("answer_content")
    for term in task.get("forbidden", []):
        if canonical_text(term) in text:
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


def atomic_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def experiment_manifest(base: Settings, tasks: list[dict], trials: int) -> dict:
    source = hashlib.sha256()
    paths = [*sorted((PROJECT / "src/rafeeq").glob("*.py")), PROJECT / "AGENTS.md", PROJECT / "uv.lock"]
    paths += sorted((PROJECT.parents[1] / "labs/data/policies").glob("*.md"))
    for path in paths:
        source.update(path.name.encode())
        source.update(path.read_bytes())
    return {"model": base.model, "trials": trials,
            "tasks_sha256": hashlib.sha256(json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "source_sha256": source.hexdigest(),
            "settings": {key: getattr(base, key) for key in
                         ("max_steps", "max_tokens", "max_context_chars", "max_cost", "input_rate", "output_rate")}}


def export_results(output: Path, attempts: list[dict], planned: int) -> dict:
    # Retain every attempt in the checkpoint. The current CSV selects the latest attempt per task/config/trial.
    latest = {}
    for attempt in attempts:
        row = attempt["row"]
        latest[(row["config"], row["task"], row["trial"])] = attempt
    selected = list(latest.values())
    rows = [entry["row"] for entry in selected]
    if rows:
        with (output / "agent-results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    atomic_json(output / "transcripts.json", [entry["detail"] for entry in selected])
    summary = summary_for(rows, planned)
    atomic_json(output / "summary.json", summary)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    report = output / "analysis.md"
    temporary = report.with_suffix(".md.tmp")
    temporary.write_text(markdown_report(rows, summary, manifest), encoding="utf-8")
    temporary.replace(report)
    return summary


async def live(tasks: list[dict], output: Path, trials: int, *, resume: bool = False,
               requests_per_minute: float = 10, settings: Settings | None = None, provider=None) -> int:
    base = settings or Settings()
    # Controlled A/B runs must never silently switch model identities.
    base = base.model_copy(update={"fallback_model": ""})
    if not base.api_key and provider is None:
        print("BLOCKED: OPENROUTER_API_KEY is missing. No model evaluations were executed.")
        return 2
    if base.model == "openrouter/free":
        print("BLOCKED: Pin RAFEEQ_MODEL to a specific tool-calling model for a controlled A/B comparison.")
        return 2
    if requests_per_minute <= 0:
        raise ValueError("requests_per_minute must be positive")
    manifest = experiment_manifest(base, tasks, trials)
    manifest["requests_per_minute"] = requests_per_minute
    manifest["run_kind"] = "scripted_test_fixture" if provider is not None else "live_provider"
    attempts = []
    if resume:
        previous = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        if previous != manifest:
            raise ValueError("Cannot resume with different model, code, tasks, trials or settings. Start a new output folder.")
        attempts = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
    else:
        output.mkdir(parents=True, exist_ok=False)
        atomic_json(output / "manifest.json", manifest)
        atomic_json(output / "checkpoint.json", attempts)
    completed = {(entry["row"]["config"], entry["row"]["task"], entry["row"]["trial"])
                 for entry in attempts if entry["row"]["outcome"] != "blocked_provider"}
    model = provider if provider is not None else OpenRouter(min_interval=60 / requests_per_minute)
    try:
        for trial in range(1, trials + 1):
            for index, task in enumerate(tasks):
                # Alternate paired configurations so B does not always run after A has consumed quota.
                for config in (("A", "B") if (index + trial) % 2 else ("B", "A")):
                    if (config, task["id"], trial) in completed:
                        continue
                    with tempfile.TemporaryDirectory(prefix="rafeeq-eval-") as folder:
                        current = base.model_copy(update={"runtime": Path(folder), "configuration": config})
                        store = Store(current.runtime)
                        sid = store.new_session()
                        if task.get("verify"):
                            verify(store, sid, Verify(**task["verify"]))
                        started = time.monotonic()
                        reply = await run_agent(store, sid, task["prompt"], current, model)
                        errors = grade(task, reply, store, sid)
                        blocked = reply.stopped == "provider_error"
                        row = {"config": config, "trial": trial, "task": task["id"], "category": task["category"],
                               "passed": not errors, "outcome": "blocked_provider" if blocked else "failed_agent" if errors else "passed",
                               "errors": "|".join(errors), "provider_error": reply.error_code or "",
                               "seconds": round(time.monotonic() - started, 3), "model": current.model,
                               "input_tokens": reply.usage.get("input_tokens", 0),
                               "output_tokens": reply.usage.get("output_tokens", 0),
                               "model_steps": reply.usage.get("model_steps", 0),
                               "reserved_upper_usd": reply.usage.get("reserved_upper_usd", 0)}
                        detail = {"config": config, "trial": trial, "task": task["id"],
                                  "recorded_at": datetime.now(timezone.utc).isoformat(),
                                  "reply": reply.model_dump(), "errors": errors}
                        attempts.append({"row": row, "detail": detail})
                        atomic_json(output / "checkpoint.json", attempts)
                        export_results(output, attempts, len(tasks) * trials)
                        print(config, trial, task["id"], row["outcome"], errors, flush=True)
                        if blocked:
                            print("STOPPED: provider rejected a request. Progress saved in", output)
                            print("Check provider quota/authentication; 429 may be a minute or daily limit.")
                            print("Resume the SAME experiment after recovery with --resume --output followed by that folder.")
                            return 2
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Interrupted. Completed task results are saved in", output)
        return 130
    summary = export_results(output, attempts, len(tasks) * trials)
    print("Results saved in", output)
    print(json.dumps(summary, indent=2))
    return int(any(entry["row"]["outcome"] == "failed_agent" for entry in attempts))



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
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--requests-per-minute", type=float, default=10)
    parser.add_argument("--task-ids", nargs="+", help="Run a fixed subset for diagnosis; keep it identical when resuming")
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    filename = "tasks.jsonl" if args.mode == "live" else "retrieval.jsonl"
    tasks = [json.loads(line) for line in (PROJECT / "evals" / filename).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.task_ids:
        wanted = set(args.task_ids)
        tasks = [task for task in tasks if task["id"] in wanted]
        if {task["id"] for task in tasks} != wanted:
            parser.error("Unknown task ID")
    if args.requests_per_minute <= 0:
        parser.error("--requests-per-minute must be positive")
    if args.resume and (args.output is None or args.mode != "live"):
        parser.error("--resume requires live mode and --output pointing to an existing checkpoint")
    output = args.output or PROJECT / "evals/results" / (args.mode + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    raise SystemExit(asyncio.run(live(tasks, output, args.trials, resume=args.resume, requests_per_minute=args.requests_per_minute)) if args.mode == "live" else retrieval(tasks, output))


if __name__ == "__main__":
    main()
