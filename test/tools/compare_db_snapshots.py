#!/usr/bin/env python3
"""compare_db_snapshots.py

Compares two DB snapshot JSON files (before/after an API call) and outputs
a structured diff report.

Usage:
    python3 compare_db_snapshots.py \\
        --before partial_results/TC-1.1_before.json \\
        --after  partial_results/TC-1.1_after.json \\
        --output partial_results/TC-1.1_diff.json

Input format (each snapshot file):
    {"rows": [...], "row_count": N}   OR   a bare JSON array

Output format:
    {
      "changed":   [{"key": ..., "pk_column": ..., "before": {...}, "after": {...}, "diff_fields": {...}}],
      "unchanged": [...],
      "added":     [...],
      "removed":   [...],
      "summary":   {"changed_count": N, ...}
    }
"""

import argparse
import json
import sys
from datetime import datetime


def load_snapshot(path):
    """Load a DB snapshot JSON file. Returns a list of row dicts."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("rows", "data", "results", "result"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # Single-row dict
        return [data]
    return []


def detect_pk_column(rows):
    """Heuristically find a primary key column that uniquely identifies rows."""
    if not rows:
        return None
    all_keys = list(rows[0].keys())
    # Priority: 'id', then columns ending with '_id'
    candidates = ["id"] + [k for k in all_keys if k.endswith("_id") and k != "id"]
    for col in candidates:
        if all(col in row for row in rows):
            values = [str(row[col]) for row in rows]
            if len(set(values)) == len(values):  # unique
                return col
    return None


def row_fingerprint(row):
    """Stable string fingerprint for a row dict."""
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)


def compare_snapshots(before_rows, after_rows):
    """Compare two lists of row dicts and return categorized diff."""
    pk = detect_pk_column(before_rows + after_rows)

    if pk:
        before_map = {str(row[pk]): row for row in before_rows if pk in row}
        after_map  = {str(row[pk]): row for row in after_rows  if pk in row}
    else:
        before_map = {row_fingerprint(row): row for row in before_rows}
        after_map  = {row_fingerprint(row): row for row in after_rows}

    before_keys = set(before_map)
    after_keys  = set(after_map)

    changed   = []
    unchanged = []
    added     = []
    removed   = []

    # Rows present in both snapshots
    for k in before_keys & after_keys:
        b = before_map[k]
        a = after_map[k]
        if row_fingerprint(b) == row_fingerprint(a):
            unchanged.append(b)
        else:
            diff_fields = {}
            for field in set(b) | set(a):
                bv = b.get(field)
                av = a.get(field)
                if bv != av:
                    diff_fields[field] = {"before": bv, "after": av}
            changed.append({
                "key":        k,
                "pk_column":  pk,
                "before":     b,
                "after":      a,
                "diff_fields": diff_fields,
            })

    # Rows only in before → removed
    for k in before_keys - after_keys:
        removed.append(before_map[k])

    # Rows only in after → added
    for k in after_keys - before_keys:
        added.append(after_map[k])

    return {
        "changed":   changed,
        "unchanged": unchanged,
        "added":     added,
        "removed":   removed,
        "summary": {
            "changed_count":   len(changed),
            "unchanged_count": len(unchanged),
            "added_count":     len(added),
            "removed_count":   len(removed),
            "pk_column_used":  pk,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Compare DB snapshots (before/after API call)")
    parser.add_argument("--before", required=True, help="Before-snapshot JSON file path")
    parser.add_argument("--after",  required=True, help="After-snapshot JSON file path")
    parser.add_argument("--output", required=True, help="Output diff JSON file path")
    args = parser.parse_args()

    try:
        before_rows = load_snapshot(args.before)
        after_rows  = load_snapshot(args.after)
    except FileNotFoundError as e:
        print(f"ERROR: File not found — {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    diff = compare_snapshots(before_rows, after_rows)
    diff["generated_at"] = datetime.now().isoformat()
    diff["before_file"]  = args.before
    diff["after_file"]   = args.after

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(diff, f, indent=2, ensure_ascii=False, default=str)

    s = diff["summary"]
    print(
        f"✅ Diff complete — "
        f"changed={s['changed_count']}, added={s['added_count']}, "
        f"removed={s['removed_count']}, unchanged={s['unchanged_count']} "
        f"(pk: {s['pk_column_used'] or 'fingerprint'})"
    )


if __name__ == "__main__":
    main()
