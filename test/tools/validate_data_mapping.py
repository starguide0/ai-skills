#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PreToolUse Hook: 데이터 매핑 파일의 구조 및 정합성 검증.

Write/Edit tool이 _데이터매핑.json 파일을 쓰거나 수정할 때 호출되어,
필수 필드 누락, behavioral_check 구조 오류, summary 정합성 오류 등을 deny한다.

검증 항목:
  1. JSON 파싱 가능 여부
  2. 최상위 필수 필드: sheet_version, created_at, mappings
  3. mappings가 dict 타입인지
  4. 각 매핑 엔트리의 status별 필수 필드
  5. MAPPED 상태 시 behavioral_check 및 하위 필드 존재 여부
  6. NOT_FOUND 상태 시 reason 필드 존재 여부
  7. summary 필드의 수치 정합성 (mapped + not_found == total_tcs)
"""
import json
import sys

from hook_utils import resolve_content


def validate(file_path: str, content: str) -> tuple[bool, str]:
    """데이터 매핑 파일을 검증한다. (valid, reason) 반환."""
    if "_데이터매핑.json" not in file_path:
        return True, ""

    if not content:
        return True, ""

    violations = []

    # Rule 1: JSON parsability
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"JSON 파싱 실패: {e}"

    # Rule 2: Top-level required fields
    for field in ("sheet_version", "created_at", "mappings"):
        if field not in data:
            violations.append(f"필수 필드 누락: {field}")

    if violations:
        return False, "\n".join(violations)

    # Rule 3: mappings must be a dict
    mappings = data["mappings"]
    if not isinstance(mappings, dict):
        return False, "필수 필드 누락: mappings (dict 타입이어야 함)"

    # Rule 4 & 5: Each mapping entry validation
    for tc_id, entry in mappings.items():
        if not isinstance(entry, dict):
            continue

        status = entry.get("status")

        if status == "MAPPED":
            # behavioral_check must exist
            if "behavioral_check" not in entry:
                violations.append(f"{tc_id}: MAPPED 상태이나 behavioral_check 누락")
            else:
                bc = entry["behavioral_check"]
                if isinstance(bc, dict):
                    if "verdict" not in bc:
                        violations.append(f"{tc_id}: behavioral_check에 verdict 필드 누락")
                    if "conditions" not in bc:
                        violations.append(f"{tc_id}: behavioral_check에 conditions 필드 누락")
                    if "method" not in bc:
                        violations.append(f"{tc_id}: behavioral_check에 method 필드 누락")

        elif status == "NOT_FOUND":
            reason = entry.get("reason")
            if not reason or not isinstance(reason, str) or not reason.strip():
                violations.append(f"{tc_id}: NOT_FOUND 상태이나 reason 누락")

        elif status == "PROVISIONED":
            if "provisioned_data" not in entry:
                violations.append(f"{tc_id}: PROVISIONED 상태이나 provisioned_data 누락")

        elif status == "PROVISIONING_NEEDED":
            if "provision_target" not in entry:
                violations.append(f"{tc_id}: PROVISIONING_NEEDED 상태이나 provision_target 누락")

        elif status == "BEHAVIORAL_MISMATCH":
            if "expected" not in entry:
                violations.append(f"{tc_id}: BEHAVIORAL_MISMATCH 상태이나 expected 누락")
            if "actual" not in entry:
                violations.append(f"{tc_id}: BEHAVIORAL_MISMATCH 상태이나 actual 누락")

        elif status == "CAPTURE_PLANNED":
            pass  # TC ID는 이미 mappings key로 식별됨 — CAPTURE_PLANNED에 추가 필수 필드 없음

    # Rule 6: Summary consistency (모든 상태 카운트 합산)
    if "summary" in data:
        summary = data["summary"]
        if isinstance(summary, dict):
            total_tcs = summary.get("total_tcs")
            if total_tcs is not None:
                status_sum = sum(
                    summary.get(k, 0)
                    for k in (
                        "mapped",
                        "not_found",
                        "provisioning_needed",
                        "provisioned",
                        "skipped",
                        "behavioral_mismatch",
                        "capture_planned",
                    )
                )
                if status_sum != total_tcs:
                    violations.append(
                        f"summary 정합성 오류: 상태 합계({status_sum}) != total_tcs({total_tcs})"
                    )

    if violations:
        return False, "\n".join(violations)

    return True, ""


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name, file_path = resolve_content(hook_input)
    if tool_name == "Edit":
        sys.exit(0)  # Edit은 파일 일부만 제공 — 전체 구조 검증 불가
    content = hook_input.get("tool_input", {}).get("content", "")

    valid, reason = validate(file_path, content)

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


if __name__ == "__main__":
    main()
