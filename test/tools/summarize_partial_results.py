#!/usr/bin/env python3
"""summarize_partial_results.py

Aggregates all TC partial result JSON files into a single _summary.json.
This allows test-reporter to read one file instead of N individual files.

Usage:
    python3 summarize_partial_results.py \\
        --dir   {ticket_folder}/partial_results/ \\
        --output {ticket_folder}/partial_results/_summary.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def load_tc_files(directory):
    """Load all TC result JSON files (excluding _prefixed and side-car files)."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    # Side-car files produced alongside TC results — must NOT be counted as TCs.
    # stimulus_executor.py, verdict_calculator.py, compare_db_snapshots.py 등의 출력물.
    EXCLUDED_SUFFIXES = (
        "_stimulus",
        "_verdict",
        "_before",
        "_after",
        "_diff",
        "_provisioning",
    )

    tc_results = []
    for path in sorted(dir_path.glob("*.json")):
        if path.name.startswith("_"):
            continue  # skip _summary.json, _mermaid_drafts.json, etc.
        if any(path.stem.endswith(s) for s in EXCLUDED_SUFFIXES):
            continue  # skip TC-1_stimulus.json, TC-1_verdict.json, etc.
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "tc_id" in data:
                tc_results.append((path.stem, data))
        except (json.JSONDecodeError, OSError):
            pass  # skip malformed files silently
    return tc_results


def extract_api_status(tc_data):
    """Extract HTTP status code from api_response if present."""
    # "api_response" (표준) 또는 "response" (stimulus 파일 직접 참조 시 fallback)
    api = tc_data.get("api_response") or tc_data.get("response") or {}
    if isinstance(api, dict):
        for key in ("status_code", "statusCode", "status", "http_status"):
            if key in api:
                return api[key]
        # Nested: {"response": {"status_code": ...}}
        nested = api.get("response") or {}
        if isinstance(nested, dict):
            return nested.get("status_code") or nested.get("statusCode")
    return None


def count_diff_fields(tc_data):
    """Count changed fields from db_changes."""
    changes = tc_data.get("db_changes") or []
    if isinstance(changes, list):
        return len(changes)
    return 0


def summarize(tc_results):
    """Build summary dict from list of (stem, data) tuples."""
    stats = {"total": 0, "pass": 0, "fail": 0, "nt": 0, "blocked": 0, "incomplete": 0, "skipped": 0}
    tcs = []
    failed_tcs = []
    blocked_tcs = []
    checks = {}

    for stem, data in tc_results:
        tc_id  = data.get("tc_id", stem)
        status = (data.get("status") or "INCOMPLETE").upper()
        tc_type = data.get("tc_type", "ACTIVE")
        evidence = data.get("evidence") or {}

        stats["total"] += 1
        status_key = {"PASS": "pass", "FAIL": "fail", "N/T": "nt",
                      "BLOCKED": "blocked", "INCOMPLETE": "incomplete",
                      "SKIPPED": "skipped"}.get(status, "incomplete")
        stats[status_key] = stats.get(status_key, 0) + 1

        if status == "FAIL":
            failed_tcs.append(tc_id)
        if status == "BLOCKED":
            blocked_tcs.append(tc_id)

        tcs.append({
            "tc_id":           tc_id,
            "tc_type":         tc_type,
            "status":          status,
            "evidence_level":  evidence.get("level"),
            "evidence_text":   evidence.get("text"),
            "api_status_code": extract_api_status(data),
            "has_db_changes":  bool(data.get("db_changes")),
            "diff_field_count": count_diff_fields(data),
            "error":           data.get("error"),
        })

        # Preserve checklist + api_response for reporter
        checks[tc_id] = {
            "checklist":    data.get("checklist"),
            "api_response": data.get("api_response") or data.get("response"),
            "screenshots":  data.get("screenshots"),
        }

    total = stats["total"] or 1  # avoid division by zero
    pass_rate = round(stats["pass"] / total * 100, 1)
    stats["pass_rate"] = f"{pass_rate}%"

    # Sort TCs by tc_id for deterministic output
    def _tc_sort_key(tc_id: str) -> list:
        """TC-1.1, TC-10 등을 올바른 숫자 순서로 정렬."""
        return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', tc_id)]

    tcs.sort(key=lambda t: _tc_sort_key(t["tc_id"]))

    return {
        "generated_at": datetime.now().isoformat(),
        "stats":        stats,
        "tcs":          tcs,
        "failed_tcs":   failed_tcs,
        "blocked_tcs":  blocked_tcs,
        "checks":       checks,
    }


def main():
    parser = argparse.ArgumentParser(description="Aggregate partial TC results into _summary.json")
    parser.add_argument("--dir",    required=True, help="partial_results/ directory path")
    parser.add_argument("--output", required=True, help="Output _summary.json path")
    args = parser.parse_args()

    try:
        tc_results = load_tc_files(args.dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not tc_results:
        print("WARNING: No TC result files found in directory", file=sys.stderr)

    summary = summarize(tc_results)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    s = summary["stats"]
    print(
        f"✅ Summary: {s['total']} TCs — "
        f"PASS={s['pass']}, FAIL={s['fail']}, N/T={s['nt']}, "
        f"BLOCKED={s['blocked']}, INCOMPLETE={s['incomplete']} ({s['pass_rate']})"
    )


if __name__ == "__main__":
    main()
