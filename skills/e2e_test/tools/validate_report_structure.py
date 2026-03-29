#!/usr/bin/env python3
from __future__ import annotations
"""validate_report_structure.py

Validates a 보고서 test result markdown file against rules defined in a JSON schema.
Outputs _validation.json.

Usage:
    python3 validate_report_structure.py \
        --file   {ticket}_보고서_테스트결과_v1.0_2026-02-22.md \
        --schema ../rules/_report_output_rules.json \
        --output partial_results/_validation.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def load_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_rules(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except json.JSONDecodeError as e:
        print(f"Error: Schema file '{path}' must be a valid JSON file. ({str(e)})", file=sys.stderr)
        sys.exit(1)


def get_re_flags(flag_str):
    flags = 0
    if not flag_str:
        return flags
    if "i" in flag_str.lower():
        flags |= re.IGNORECASE
    if "m" in flag_str.lower():
        flags |= re.MULTILINE
    return flags


def check_section_exists(content, pattern, flags=0):
    """Return True if pattern matches anywhere in content."""
    return bool(re.search(pattern, content, flags))


def run_checks(content, filepath, rules):
    """Run structural checks loaded from JSON diagram. Returns list of result dicts."""
    results = []
    check_id = 0

    def add(name, passed, detail=""):
        nonlocal check_id
        check_id += 1
        results.append({
            "check_id": check_id,
            "name":     name,
            "status":   "PASS" if passed else "FAIL",
            "detail":   detail,
        })

    for rule in rules:
        name = rule.get("name", "Unknown Check")
        rule_type = rule.get("type", "pattern")
        detail = rule.get("detail", "")
        flags_str = rule.get("flags", "")
        flags = get_re_flags(flags_str)

        if rule_type == "pattern" or "pattern" in rule:
            pattern = rule.get("pattern")
            if not pattern:
                add(name, False, "Invalid rule schema: missing pattern")
                continue
            passed = check_section_exists(content, pattern, flags)
            add(name, passed, detail)

        elif rule_type == "fail_evidence":
            fail_pat = rule.get("fail_marker_pattern")
            evid_pat = rule.get("evidence_pattern")
            has_fail = check_section_exists(content, fail_pat, flags)
            has_evid = check_section_exists(content, evid_pat, flags)
            passed = (not has_fail) or has_evid
            add(name, passed, detail)

        elif rule_type == "min_match":
            patterns = rule.get("patterns", [])
            min_req = rule.get("min_required", len(patterns))
            found = [p for p in patterns if check_section_exists(content, p, flags)]
            passed = len(found) >= min_req
            add(name, passed, f"발견된 수: {len(found)} (최소 {min_req} 필요) - {detail}")

        elif rule_type == "non_empty_match":
            extract_pat = rule.get("extract_pattern")
            min_len = rule.get("min_length", 1)
            matches = re.findall(extract_pat, content, flags)
            if not matches:
                # If section doesn't exist, this check auto-passes.
                # "Tc 선정 이유 블록 존재 여부" is checked separately.
                passed = True
                curr_detail = "대상 요소 없음"
            else:
                non_empty = [m for m in matches if m.strip() and len(m.strip()) >= min_len]
                passed = len(non_empty) == len(matches)
                curr_detail = f"총 {len(matches)}개 중 내용 충족: {len(non_empty)}개"
            add(name, passed, curr_detail)

        else:
            add(name, False, f"Unknown rule type: {rule_type}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate 보고서 test report structure using JSON schema")
    parser.add_argument("--file",   required=True, help="보고서 테스트결과 .md file path")
    parser.add_argument("--schema", required=True, help="JSON schema file defining the rules")
    parser.add_argument("--output", required=True, help="Output _validation.json path")
    args = parser.parse_args()

    try:
        content = load_file(args.file)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        rules = load_rules(args.schema)
    except FileNotFoundError as e:
        print(f"ERROR loading schema: {e}", file=sys.stderr)
        sys.exit(1)

    results  = run_checks(content, args.file, rules)
    total    = len(results)
    passed   = sum(1 for r in results if r["status"] == "PASS")
    failed   = sum(1 for r in results if r["status"] == "FAIL")

    output = {
        "generated_at": datetime.now().isoformat(),
        "file":         args.file,
        "total_checks": total,
        "pass_count":   passed,
        "fail_count":   failed,
        "results":      results,
    }

    # Ensure output directory exists before writing
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    status_icon = "✅" if failed == 0 else "❌"
    print(f"{status_icon} Validation: {passed}/{total} PASS, {failed} FAIL")
    if failed:
        print("FAIL items:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  [{r['check_id']}] {r['name']} — {r['detail']}")


if __name__ == "__main__":
    main()
