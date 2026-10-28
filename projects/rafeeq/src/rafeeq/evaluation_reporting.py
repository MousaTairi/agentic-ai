"""Formatting-tolerant grading and explicit coverage/availability reporting."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter


def canonical_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    text = text.translate(str.maketrans({char: "-" for char in "‐‑‒–—−﹘﹣－"}))
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    text = re.sub(r"(?<=\d)[,٬](?=\d)", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def contains_expected(text: str, value: str) -> bool:
    expected = canonical_text(value)
    if re.fullmatch(r"\d+(?:\.\d+)?", expected):
        return re.search(r"(?<!\d)" + re.escape(expected) + r"(?!\d)", text) is not None
    if re.fullmatch(r"pol-\d+", expected):
        return re.search(r"(?<!\w)" + re.escape(expected) + r"(?!\d)", text) is not None
    return expected in text


def summary_for(rows: list[dict], planned_per_config: int) -> dict:
    result = {}
    for config in ("A", "B"):
        selected = [row for row in rows if row["config"] == config]
        blocked = [row for row in selected if row.get("outcome") == "blocked_provider"]
        passed = sum(row["passed"] is True for row in selected)
        available = len(selected) - len(blocked)
        result[config] = {
            "runs": len(selected), "planned_runs": planned_per_config,
            "passed": passed,
            "failed_agent": available - passed,
            "blocked_provider": len(blocked),
            "unrun": planned_per_config - len(selected),
            "overall_pass_rate": passed / planned_per_config if planned_per_config else None,
            "available_run_pass_rate": passed / available if available else None,
            "failures": dict(Counter(error for row in selected for error in row["errors"].split("|") if error)),
        }
    by_key = {(row["config"], row["task"], row["trial"]): row for row in rows}
    provider_pairs = 0
    for row in rows:
        if row["config"] != "A":
            continue
        other = by_key.get(("B", row["task"], row["trial"]))
        if (other and row.get("outcome") != "blocked_provider" and other.get("outcome") != "blocked_provider"
                and row.get("model_steps", 0) > 0 and other.get("model_steps", 0) > 0):
            provider_pairs += 1
    result["comparison"] = {
        "complete": all(result[c]["blocked_provider"] == 0 and result[c]["unrun"] == 0 for c in ("A", "B")),
        "paired_model_task_runs": provider_pairs,
        "note": "Provider blocks and unrun tasks are not model-quality failures. Scope-only passes do not measure LLM quality.",
    }
    return result


def markdown_report(rows: list[dict], summary: dict, manifest: dict) -> str:
    """Publish aggregate evidence only; never include prompts, replies or credentials."""
    complete = summary["comparison"]["complete"]
    lines = ["# Agent evaluation evidence", "",
             "Run kind: " + str(manifest["run_kind"]),
             "", "Model: `" + manifest["model"] + "`.",
             "Source fingerprint: `" + manifest["source_sha256"] + "`.",
             "Trials per task: " + str(manifest["trials"]) + ".", "",
             ("All planned A/B cases completed without provider blocks."
              if complete else "INCOMPLETE: do not draw an A/B quality conclusion from this run."), "",
             "| Config | Passed | Agent failures | Provider blocks | Unrun | Planned |",
             "|---|---:|---:|---:|---:|---:|"]
    for config in ("A", "B"):
        stats = summary[config]
        values = [stats[key] for key in ("passed", "failed_agent", "blocked_provider", "unrun", "planned_runs")]
        lines.append("| " + config + " | " + " | ".join(map(str, values)) + " |")
    lines += ["", "Paired task/trial cases with model steps on both configurations: "
              + str(summary["comparison"]["paired_model_task_runs"]) + ".", "",
              "Scope-only passes do not measure model quality. A single trial does not establish repeated-run reliability.",
              "Scripted fixtures are not live-model evidence, even when every case passes.", "",
              "## Agent failure categories", "",
              "These are grader signals, not confirmed root causes. Review transcripts locally before diagnosing or changing code.", ""]
    failures = Counter(error for row in rows if row["outcome"] == "failed_agent"
                       for error in row["errors"].split("|") if error)
    lines.extend(f"- `{error}`: {count}" for error, count in sorted(failures.items()))
    if not failures:
        lines.append("No completed case was classified as an agent failure; blocked/unrun cases remain unevaluated.")
    blocks = Counter(row.get("provider_error") or "unspecified" for row in rows
                     if row["outcome"] == "blocked_provider")
    lines += ["", "## Provider availability", ""]
    lines.extend(f"- `{error}`: {count}" for error, count in sorted(blocks.items()))
    if not blocks:
        lines.append("No selected outcome is provider-blocked.")
    lines += ["", "A rate-limit response does not establish an invalid key or distinguish minute/daily quota from capacity.",
              "Resume blocked/unrun cases only with the original model, source, tasks, trials and request rate.",
              "", "## Manual review before submission", "",
              "- Inspect failed cases for actual answer, tool, approval and database behavior; do not weaken graders to raise scores.",
              "- Review Arabic fluency, citation support, private-data boundaries and misleading completion claims.",
              "- Record observed causes and fixes separately from this automatic report; rerun changed code as a new experiment.",
              "- Publish only reviewed synthetic-only CSVs and this report. Keep raw transcripts/checkpoints local.", ""]
    return "\n".join(lines)
