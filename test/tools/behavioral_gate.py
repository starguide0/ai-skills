#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PreToolUse Hook + CLI Tool: TC behavioral_check 게이트.

DUAL-MODE:
  - Hook Mode  : Write/Edit tool이 partial_results/TC-*.json 파일을 쓸 때 호출되어,
                 behavioral_check.verdict != "PASS" 이면 deny한다.
  - CLI Mode   : --mapping 인자가 주어지면 매핑 파일 전체를 검사하여 gate 결과를
                 JSON 파일로 출력한다.

CLI 사용 예시:
  python3 behavioral_gate.py --mapping ARG-XXXXX_데이터매핑.json --output ARG-XXXXX_behavioral_gate.json
"""
import argparse
import glob
import json
import os
import re
import sys

from hook_utils import resolve_content


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def find_mapping_file(partial_results_dir: str) -> str | None:
    """partial_results 디렉터리의 부모에서 *_데이터매핑.json 파일을 찾는다."""
    parent = os.path.dirname(os.path.abspath(partial_results_dir))
    candidates = glob.glob(os.path.join(parent, "*_데이터매핑.json"))
    if candidates:
        return candidates[0]
    return None


def load_json(path: str) -> dict | None:
    """JSON 파일을 읽어 dict를 반환한다. 실패 시 None."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError):
        return None


def extract_tc_id_from_path(file_path: str) -> str | None:
    """파일 경로에서 TC ID를 추출한다. 예: .../partial_results/TC-4.json → TC-4"""
    basename = os.path.basename(file_path)
    match = re.match(r"^(TC-[A-Za-z0-9.\-]+)\.json$", basename)
    if match:
        return match.group(1)
    return None


def format_conditions(conditions: list) -> str:
    """behavioral_check.conditions 목록을 읽기 좋은 문자열로 변환한다."""
    if not conditions:
        return ""
    parts = []
    for cond in conditions:
        if isinstance(cond, dict):
            parts.append(str(cond))
        else:
            parts.append(str(cond))
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Hook Mode
# ---------------------------------------------------------------------------

def is_tc_result_file(file_path: str) -> bool:
    """파일이 partial_results/TC-*.json 패턴에 해당하는지 확인한다."""
    normalized = file_path.replace("\\", "/")
    return bool(re.search(r"partial_results/TC-[A-Za-z0-9.\-]+\.json$", normalized))


def check_behavioral_gate_for_tc(tc_id: str, mapping_data: dict) -> tuple[bool, str]:
    """
    매핑 데이터에서 특정 TC의 behavioral_check를 검사한다.

    Returns:
        (valid, reason) — valid=True 이면 통과, False 이면 deny 이유 포함.
    """
    mappings = mapping_data.get("mappings", {})
    tc_entry = mappings.get(tc_id)

    if tc_entry is None:
        # 매핑에 해당 TC가 없으면 통과 (검증 범위 밖)
        return True, ""

    behavioral_check = tc_entry.get("behavioral_check")

    if behavioral_check is None:
        # behavioral_check 필드 없음 → 경고 없이 통과 (신규 필드, 기존 파일 호환)
        return True, ""

    verdict = behavioral_check.get("verdict", "")
    if verdict == "PASS":
        return True, ""

    # verdict가 PASS가 아닌 경우 → deny
    conditions = behavioral_check.get("conditions", [])
    conditions_str = format_conditions(conditions)
    reason = (
        f"{tc_id}: behavioral_check.verdict={verdict}"
        + (f" — {conditions_str}" if conditions_str else "")
        + ". 데이터 매핑의 behavioral_check를 PASS로 업데이트하거나 데이터를 수정하세요."
    )
    return False, reason


def run_hook_mode():
    """Hook Mode: stdin에서 JSON을 읽어 Write/Edit 검증을 수행한다."""
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name, file_path = resolve_content(hook_input)
    if tool_name == "Edit":
        sys.exit(0)  # Edit은 파일 일부만 제공 — 전체 구조 검증 불가

    # partial_results/TC-*.json 파일이 아니면 통과
    if not is_tc_result_file(file_path):
        sys.exit(0)

    tc_id = extract_tc_id_from_path(file_path)
    if not tc_id:
        sys.exit(0)

    # partial_results 디렉터리 기준으로 매핑 파일 탐색
    partial_results_dir = os.path.dirname(os.path.abspath(file_path))
    mapping_path = find_mapping_file(partial_results_dir)

    if not mapping_path:
        # 매핑 파일이 없으면 통과
        sys.exit(0)

    mapping_data = load_json(mapping_path)
    if not mapping_data:
        sys.exit(0)

    valid, reason = check_behavioral_gate_for_tc(tc_id, mapping_data)

    if valid:
        sys.exit(0)
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)


# ---------------------------------------------------------------------------
# CLI Mode
# ---------------------------------------------------------------------------

def run_cli_mode(mapping_path: str, output_path: str):
    """CLI Mode: 매핑 파일 전체를 검사하여 gate 결과를 JSON으로 출력한다."""
    mapping_data = load_json(mapping_path)
    if mapping_data is None:
        print(f"ERROR: 매핑 파일을 읽을 수 없습니다: {mapping_path}", file=sys.stderr)
        sys.exit(1)

    mappings = mapping_data.get("mappings", {})
    results = []
    pass_count = 0

    for tc_id, tc_entry in mappings.items():
        if not isinstance(tc_entry, dict):
            continue

        # NOT_FOUND 또는 SKIPPED 상태는 건너뜀
        status = tc_entry.get("status", "")
        if status in ("NOT_FOUND", "SKIPPED"):
            continue

        behavioral_check = tc_entry.get("behavioral_check")

        if behavioral_check is None:
            # Hook 모드와 동일: behavioral_check 미정의 TC는 구형 매핑 호환으로 PASS 처리
            results.append({
                "tc_id": tc_id,
                "gate": "PASS",
                "reason": "behavioral_check 필드 없음 (구형 매핑 호환)",
            })
            pass_count += 1
            continue

        verdict = behavioral_check.get("verdict", "")

        if verdict == "PASS":
            results.append({
                "tc_id": tc_id,
                "gate": "PASS",
                "reason": "behavioral_check.verdict=PASS",
            })
        else:
            conditions = behavioral_check.get("conditions", [])
            conditions_str = format_conditions(conditions)
            reason = f"behavioral_check.verdict={verdict}"
            if conditions_str:
                reason += f": {conditions_str}"
            results.append({
                "tc_id": tc_id,
                "gate": "BLOCKED",
                "reason": reason,
            })

    pass_count = sum(1 for r in results if r["gate"] == "PASS")
    blocked_count = sum(1 for r in results if r["gate"] == "BLOCKED")
    # NEEDS_CONFIRMATION is reserved for future use; the gate only ever emits
    # "PASS" or "BLOCKED", so this count is always 0.
    needs_count = sum(1 for r in results if r["gate"] == "NEEDS_CONFIRMATION")

    # results가 비어있으면(모두 NOT_FOUND/SKIPPED) 차단할 대상이 없으므로 PASS
    gate_passed = blocked_count == 0 and needs_count == 0 and (pass_count > 0 or not results)

    output_data = {
        "gate_passed": gate_passed,
        "results": results,
        "summary": {
            "pass": pass_count,
            "blocked": blocked_count,
            "needs_confirmation": needs_count,
        },
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"behavioral gate 결과 저장: {output_path}")
        print(f"  PASS: {pass_count}, BLOCKED: {blocked_count}, NEEDS_CONFIRMATION: {needs_count}")
        print(f"  gate_passed: {gate_passed}")
    except (PermissionError, OSError) as e:
        print(f"ERROR: 출력 파일 저장 실패: {e}", file=sys.stderr)
        sys.exit(1)

    if not gate_passed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="TC behavioral_check 게이트 (Hook + CLI 듀얼 모드)",
        add_help=True,
    )
    parser.add_argument(
        "--mapping",
        metavar="FILE",
        help="데이터매핑 JSON 파일 경로 (CLI 모드 활성화)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="결과 JSON 출력 파일 경로 (CLI 모드, 기본: {ticket}_behavioral_gate.json)",
    )

    # argparse는 --help 외의 알 수 없는 인자도 파싱할 수 있도록 parse_known_args 사용
    args, _ = parser.parse_known_args()

    if args.mapping:
        # CLI Mode
        output_path = args.output
        if not output_path:
            base = os.path.splitext(args.mapping)[0]
            # *_데이터매핑 → *_behavioral_gate
            if base.endswith("_데이터매핑"):
                base = base[: -len("_데이터매핑")]
            output_path = base + "_behavioral_gate.json"
        run_cli_mode(args.mapping, output_path)
    else:
        # Hook Mode
        run_hook_mode()


if __name__ == "__main__":
    main()
