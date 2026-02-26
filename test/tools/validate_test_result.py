#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PreToolUse Hook: 테스트 결과 파일의 STIMULUS 증거 + 증거 포맷 검증.

Write/Edit tool이 테스트 결과 파일을 쓰거나 수정할 때 호출되어,
ACTIVE TC에 STIMULUS 증거가 없으면 deny한다.

검증 단계:
  1. 텍스트 패턴: HTTP 메서드 + URL + 상태코드 존재 여부
  2. 파일 증거: partial_results/{TC_ID}_stimulus.json 존재 여부
  3. INCOMPLETE 허용: 정직한 미완료는 통과
  4. 증거 포맷 (P5):
     - Pass TC: 검증 결과 diff 테이블 (| 검증 항목 |) 존재
     - Fail TC: [Fail 근거] 섹션 + 기대:/실제: 키워드 쌍 존재
"""
import json
import os
import re
import sys

from hook_utils import resolve_content

# ⚠️ = U+26A0 + U+FE0F(variation selector). raw string 아님 — \uFE0F를 실제 유니코드로 해석.
_TC_EMOJI = "(?:✅|❌|⚠\uFE0F?)"
# TC-001, TC-ABC-001, TC-1.1 등 다양한 형식 지원 (점/하이픈 포함)
_TC_HEADING = rf"###\s+{_TC_EMOJI}\s+(TC-[A-Za-z0-9.\-]+):?\s*"


def parse_tc_sections(content: str) -> list[dict]:
    """마크다운에서 TC 섹션을 추출한다."""
    # lookahead에서는 non-capturing 버전 사용 (그룹 번호 오염 방지)
    _tc_heading_nc = rf"###\s+{_TC_EMOJI}\s+TC-[A-Za-z0-9.\-]+:?\s*"
    tc_pattern = re.compile(
        rf"{_TC_HEADING}(.*?)(?=\n{_tc_heading_nc}|\n+##\s|\Z)",
        re.DOTALL,
    )
    tcs = []
    for match in tc_pattern.finditer(content):
        tc_id = match.group(1)
        title_and_body = match.group(2)
        title_line = title_and_body.split("\n")[0].strip()
        body = "\n".join(title_and_body.split("\n")[1:])
        tcs.append({
            "tc_id": tc_id,
            "title": title_line,
            "body": body,
        })
    return tcs


def is_observation_tc(tc: dict) -> bool:
    """TC가 관찰(OBSERVATION) 타입인지 판별한다."""
    return "[관찰]" in tc["title"]


def is_incomplete_tc(tc: dict) -> bool:
    """TC가 INCOMPLETE로 표기되었는지 확인한다."""
    full_text = tc["title"] + "\n" + tc["body"]
    return "INCOMPLETE" in full_text.upper()


def has_stimulus_evidence(tc: dict) -> bool:
    """TC 본문에 STIMULUS 증거 텍스트가 있는지 확인한다."""
    body = tc["body"]

    # Pattern 1: 7-step checklist format
    if re.search(r"\[✅\]\s*3\.\s*STIMULUS", body):
        return True

    # Pattern 2: HTTP method + URL
    if re.search(r"(POST|PUT|GET|DELETE|PATCH)\s+https?://\S+", body):
        return True

    # Pattern 3: stimulus_executor output reference
    if "stimulus_executor" in body or "_stimulus.json" in body:
        return True

    # Pattern 4: HTTP status code in context
    if re.search(r"(→\s*HTTP\s+\d{3}|status_code[\"']?\s*[:=]\s*\d{3})", body):
        return True

    return False


def has_stimulus_file(tc_id: str, result_file_path: str) -> bool:
    """TC의 stimulus.json 파일이 디스크에 존재하는지 확인한다."""
    dir_path = os.path.dirname(result_file_path)
    partial_results_dir = os.path.join(dir_path, "partial_results")
    if not os.path.isdir(partial_results_dir):
        return False
    stimulus_path = os.path.join(partial_results_dir, f"{tc_id}_stimulus.json")
    return os.path.exists(stimulus_path)


def is_pass_tc(tc: dict) -> bool:
    """TC가 PASS (✅) 판정인지 확인한다."""
    body = tc["body"]
    # 1. [Pass 근거] 또는 **Pass 근거** 패턴
    if re.search(r"\[Pass 근거\]|\*\*Pass 근거\*\*|Pass 근거", body):
        return True
    # 2. 검증 결과 diff 테이블 존재 (Pass TC의 핵심 산출물)
    if re.search(r"\|\s*검증\s*항목\s*\|", body):
        return True
    # 3. 판정/결과가 PASS인 경우
    if re.search(r"(?:결과|판정|verdict)\s*[:\|]\s*(?:✅\s*)?PASS", body, re.IGNORECASE):
        return True
    return False


def is_fail_tc(tc: dict) -> bool:
    """TC가 FAIL (❌) 판정인지 확인한다."""
    body = tc["body"]
    # 체크: [Fail 근거] 또는 FAIL 근거 패턴이 있으면 Fail TC
    if re.search(r"\[Fail 근거\]|FAIL 근거|Fail 근거", body):
        return True
    # 판정이 FAIL인 경우 (체크리스트 verdict)
    if re.search(r"판정\s*[:\|]\s*FAIL|결과\s*[:\|]\s*FAIL|verdict\s*[:\|]\s*FAIL", body, re.IGNORECASE):
        return True
    return False


def has_verification_table(tc: dict) -> bool:
    """TC 본문에 검증 결과 diff 테이블 (| 검증 항목 |) 이 있는지 확인한다."""
    body = tc["body"]
    return bool(re.search(r"\|\s*검증\s*항목\s*\|", body))


def has_fail_basis(tc: dict) -> bool:
    """TC 본문에 [Fail 근거] 또는 동등한 Fail 설명 섹션이 있는지 확인한다."""
    body = tc["body"]
    return bool(re.search(
        r"\[Fail 근거\]|FAIL 근거|\*\*Fail 근거\*\*|\*\*FAIL 근거\*\*",
        body,
    ))


def has_expected_actual_pair(tc: dict) -> bool:
    """TC 본문에 기대:/실제: 키워드 쌍이 존재하는지 확인한다."""
    body = tc["body"]
    has_expected = bool(re.search(r"기대\s*[:：]", body))
    has_actual = bool(re.search(r"실제\s*[:：]", body))
    return has_expected and has_actual


def validate(file_path: str, content: str) -> tuple[bool, str]:
    """테스트 결과 파일을 검증한다. (valid, reason) 반환."""
    if "_테스트결과_" not in file_path:
        return True, ""

    tcs = parse_tc_sections(content)
    if not tcs:
        return True, ""

    violations = []
    for tc in tcs:
        if is_observation_tc(tc):
            continue
        if is_incomplete_tc(tc):
            continue

        has_text = has_stimulus_evidence(tc)
        has_file = has_stimulus_file(tc["tc_id"], file_path)

        if not has_text and not has_file:
            violations.append(
                f"- {tc['tc_id']}: STIMULUS 증거 없음 "
                f"(텍스트 패턴 미발견 + stimulus.json 파일 미존재)"
            )
        elif has_text and not has_file:
            violations.append(
                f"- {tc['tc_id']}: STIMULUS 텍스트는 있으나 stimulus.json 파일 미존재 "
                f"(stimulus_executor.py로 실행하세요)"
            )

    # --- P5: 증거 포맷 검증 ---
    evidence_violations = []
    for tc in tcs:
        if is_observation_tc(tc):
            continue
        if is_incomplete_tc(tc):
            continue

        # Pass TC 증거 포맷
        if is_pass_tc(tc):
            if not has_verification_table(tc):
                evidence_violations.append(
                    f"- {tc['tc_id']}: Pass TC이나 검증 결과 diff 테이블 누락 "
                    f"(| 검증 항목 | 패턴 필요)"
                )

        # Fail TC 증거 포맷
        if is_fail_tc(tc):
            if not has_fail_basis(tc):
                evidence_violations.append(
                    f"- {tc['tc_id']}: Fail TC이나 [Fail 근거] 섹션 누락"
                )
            if not has_expected_actual_pair(tc):
                evidence_violations.append(
                    f"- {tc['tc_id']}: Fail TC이나 기대:/실제: 키워드 쌍 누락"
                )

    # 모든 위반사항 종합
    all_violations = violations + evidence_violations

    if all_violations:
        parts = []
        if violations:
            parts.append(
                "ACTIVE TC에 STIMULUS 증거 누락:\n"
                + "\n".join(violations)
                + "\n\n"
                + "stimulus_executor.py로 API 호출을 실행하거나, "
                + "해당 TC를 INCOMPLETE로 표기하세요.\n"
                + "참고: .claude/skills/test/tools/stimulus_executor.py --help"
            )
        if evidence_violations:
            parts.append(
                "증거 포맷 요건 미충족:\n"
                + "\n".join(evidence_violations)
            )
        return False, "\n\n".join(parts)

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
