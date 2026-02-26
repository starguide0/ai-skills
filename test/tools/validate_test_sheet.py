#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PreToolUse Hook: 테스트 시트 파일의 구조 검증.

Write/Edit tool이 테스트 시트 파일을 쓰거나 수정할 때 호출되어,
필수 섹션 및 TC 구조 요건이 충족되지 않으면 deny한다.

검증 항목:
  1. Section 0 (Test Baseline) 존재 여부 — ## 0. Test Baseline + ### 0.1 ~ ### 0.7
  2. 각 TC의 선정 이유 존재 및 비어있지 않음
  3. 각 TC의 행위적 조건 필드 존재
  4. N/A 행위적 조건 적합성 (도출 트리에 ②③ 레이어가 있으면 N/A 불가)
  5. 기대값 도출 트리 (├─① 패턴) 존재
  6. ACTIVE TC에 ━━━ STIMULUS ━━━ 블록 존재
"""
import json
import os
import re
import sys

from hook_utils import resolve_content


# TC 섹션 헤딩 패턴: ### TC-{id}: {title}
_TC_HEADING_PATTERN = re.compile(
    r"###\s+TC-([A-Za-z0-9.\-]+)\s*:(.*?)(?=\n+###\s+TC-[A-Za-z0-9.\-]+\s*:|\n+##\s|\Z)",
    re.DOTALL,
)

# 시나리오 테이블의 ACTIVE 마커 패턴
_ACTIVE_MARKER_PATTERN = re.compile(
    r"\|\s*TC-([A-Za-z0-9.\-]+)\s*\|[^|]*\|\s*ACTIVE\s*\|",
    re.IGNORECASE,
)


def check_section0(content: str) -> list[str]:
    """Section 0 (Test Baseline) 구조를 검증하고 위반 목록을 반환한다."""
    violations = []

    if "## 0. Test Baseline" not in content:
        violations.append("Section 0 누락: ## 0. Test Baseline 필요")
        return violations  # 상위 섹션 없으면 하위 체크 무의미

    for n in range(1, 8):
        if f"### 0.{n}" not in content:
            violations.append(f"Section 0 하위 섹션 누락: ### 0.{n}")

    return violations


def parse_tc_sections(content: str) -> list[dict]:
    """마크다운에서 TC 섹션을 추출한다."""
    tcs = []
    for match in _TC_HEADING_PATTERN.finditer(content):
        tc_id = match.group(1)
        rest = match.group(2)  # ": {title}\n{body}"
        lines = rest.split("\n")
        title = lines[0].strip()
        body = "\n".join(lines[1:])
        tcs.append({
            "tc_id": tc_id,
            "title": title,
            "body": body,
        })
    return tcs


def get_active_tc_ids(content: str, all_tc_ids: list[str]) -> set[str]:
    """시나리오 테이블에서 ACTIVE TC ID 집합을 반환한다.

    ACTIVE 마커가 담긴 테이블이 없으면 모든 TC를 ACTIVE로 간주한다.
    """
    active_ids = set(_ACTIVE_MARKER_PATTERN.findall(content))
    if not active_ids:
        return set(all_tc_ids)
    return active_ids


def get_selection_reason(tc_body: str) -> str | None:
    """TC 본문에서 선정 이유 값을 추출한다. 없으면 None 반환."""
    # 마크다운 테이블 형식: | 선정 이유 | value |
    table_match = re.search(
        r"\|\s*(?:\*\*)?선정 이유(?:\*\*)?\s*\|\s*(.*?)\s*\|",
        tc_body,
    )
    if table_match:
        return table_match.group(1).strip()

    # 볼드 필드 형식: **선정 이유**: value
    bold_match = re.search(
        r"\*\*선정 이유\*\*\s*:\s*(.+)",
        tc_body,
    )
    if bold_match:
        return bold_match.group(1).strip()

    # 일반 필드 형식: 선정 이유: value
    plain_match = re.search(
        r"선정 이유\s*:\s*(.+)",
        tc_body,
    )
    if plain_match:
        return plain_match.group(1).strip()

    return None


def get_behavioral_condition(tc_body: str) -> str | None:
    """TC 본문에서 행위적 조건 값을 추출한다. 필드 자체가 없으면 None 반환."""
    # 마크다운 테이블 형식: | 행위적 조건 | value |
    table_match = re.search(
        r"\|\s*(?:\*\*)?행위적 조건(?:\*\*)?\s*\|\s*(.*?)\s*\|",
        tc_body,
    )
    if table_match:
        return table_match.group(1).strip()

    # 볼드 필드 형식: **행위적 조건**: value
    bold_match = re.search(
        r"\*\*행위적 조건\*\*\s*:\s*(.+)",
        tc_body,
    )
    if bold_match:
        return bold_match.group(1).strip()

    # 일반 필드 형식: 행위적 조건: value
    plain_match = re.search(
        r"행위적 조건\s*:\s*(.+)",
        tc_body,
    )
    if plain_match:
        return plain_match.group(1).strip()

    return None


def has_derivation_tree(tc_body: str) -> bool:
    """TC 본문에 기대값 도출 트리 (├─① 패턴) 또는 도출 불필요 short form이 있는지 확인한다.

    블록인용(>) 줄은 제외하여 다른 TC나 가이드 텍스트를 인용한 경우의 오탐을 방지한다.
    """
    # 블록인용 줄 제거 (인용된 가이드/다른 TC 내용이 오탐 유발 방지)
    non_quote_lines = [
        line for line in tc_body.splitlines()
        if not line.lstrip().startswith(">")
    ]
    body = "\n".join(non_quote_lines)

    if "기대값 도출 트리" in body:
        return True
    if "├─①" in body:
        return True
    # 프롬프트 허용 short form: "④ 기대결과: {값} (고정값 — 도출 불필요)"
    # 콜론 포함 패턴으로 제한하여 단순 참조 텍스트와 구분
    if re.search(r"④\s*기대결과\s*:", body):
        return True
    return False


def tree_has_deep_layers(tc_body: str) -> bool:
    """도출 트리에 ②③ 레이어 마커가 있는지 확인한다."""
    return "├─②" in tc_body or "├─③" in tc_body


def is_na_condition(value: str) -> bool:
    """행위적 조건 값이 N/A인지 판별한다 (대소문자 무관, 부가 텍스트 허용)."""
    return bool(re.search(r"\bN/A\b", value, re.IGNORECASE))


def validate(file_path: str, content: str) -> tuple[bool, str]:
    """테스트 시트 파일을 검증한다. (valid, reason) 반환."""
    if "_테스트시트_" not in file_path:
        return True, ""

    violations: list[str] = []

    # 1. Section 0 검증
    violations.extend(check_section0(content))

    # 2~6. TC 단위 검증
    tcs = parse_tc_sections(content)
    if not tcs:
        if violations:
            return False, "\n".join(violations)
        return True, ""

    all_tc_ids = [tc["tc_id"] for tc in tcs]
    active_ids = get_active_tc_ids(content, all_tc_ids)

    for tc in tcs:
        tc_id = tc["tc_id"]
        body = tc["body"]

        # 2. 선정 이유 검증
        reason_value = get_selection_reason(body)
        if reason_value is None or reason_value == "":
            violations.append(f"TC-{tc_id}: 선정 이유 누락 또는 빈 값")

        # 3. 행위적 조건 필드 존재 검증
        cond_value = get_behavioral_condition(body)
        if cond_value is None:
            violations.append(f"TC-{tc_id}: 행위적 조건 필드 누락")
        else:
            # 4. N/A 행위적 조건 적합성 검증
            if is_na_condition(cond_value):
                if has_derivation_tree(body) and tree_has_deep_layers(body):
                    violations.append(
                        f"TC-{tc_id}: N/A 부적합 — 도출 트리에 ②③ 레이어 존재"
                    )

        # 5. 기대값 도출 트리 검증
        if not has_derivation_tree(body):
            violations.append(
                f"TC-{tc_id}: 기대값 도출 트리 누락 (├─① 패턴 없음)"
            )

        # 6. ACTIVE TC STIMULUS 블록 검증
        if tc_id in active_ids:
            if "━━━ STIMULUS ━━━" not in body:
                violations.append(
                    f"TC-{tc_id}: ACTIVE TC이나 ━━━ STIMULUS ━━━ 블록 없음"
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
