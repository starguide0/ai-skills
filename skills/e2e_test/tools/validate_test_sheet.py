#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PreToolUse Hook: 테스트 시트 파일의 구조 검증.

Write/Edit tool이 테스트 시트 파일을 쓰거나 수정할 때 호출되어,
필수 섹션 및 TC 구조 요건이 충족되지 않으면 deny한다.

검증 항목은 이제 ../rules/_test_sheet_rules.json 에 정의되어 있다.
"""
import json
import os
import re
import sys
from pathlib import Path

from hook_utils import resolve_content

# 기본 TC 파싱을 위한 정규식 (이 부분은 마크다운 구조 자체이므로 유지)
_TC_HEADING_PATTERN = re.compile(
    r"###\s+TC-([A-Za-z0-9.\-]+)\s*:(.*?)(?=\n+###\s+TC-[A-Za-z0-9.\-]+\s*:|\n+##\s|\Z)",
    re.DOTALL,
)

_ACTIVE_MARKER_PATTERN = re.compile(
    r"\|\s*TC-([A-Za-z0-9.\-]+)\s*\|[^|]*\|\s*ACTIVE\s*\|",
    re.IGNORECASE,
)


def load_rules(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
        return data.get("rules", [])


def check_section_exists(content: str, pattern: str, flags: int = 0) -> bool:
    return bool(re.search(pattern, content, flags))


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
    """시나리오 테이블에서 ACTIVE TC ID 집합을 반환한다."""
    active_ids = set(_ACTIVE_MARKER_PATTERN.findall(content))
    if not active_ids:
        return set(all_tc_ids)
    return active_ids


def get_field_value(tc_body: str, extract_pattern: str) -> str | None:
    """TC 본문에서 특정 값을 정규식 캡처 그룹으로 추출한다."""
    match = re.search(extract_pattern, tc_body)
    if not match:
        return None
    # 제일 처음으로 값이 잡힌 캡처 그룹을 반환
    for g in match.groups():
        if g is not None:
            return g.strip()
    return None


def run_checks(content: str, filepath: str, rules: list[dict]) -> tuple[bool, str]:
    """JSON 룰셋을 기반으로 검증을 수행하고 (성공여부, 실패사유)를 반환한다."""
    violations: list[str] = []

    # 전체 본문 검증 먼저 수행
    for rule in rules:
        rule_type = rule.get("type", "")
        if rule_type == "min_match":
            patterns = rule.get("patterns", [])
            min_req = rule.get("min_required", len(patterns))
            flags = rule.get("flags", 0)
            if isinstance(flags, str):
                flags = re.IGNORECASE if "i" in flags.lower() else 0

            found = [p for p in patterns if check_section_exists(content, p, flags)]
            if len(found) < min_req:
                violations.append(f"전역: {rule.get('detail')} (발견 {len(found)}개, 최소 {min_req}개 필요)")

    tcs = parse_tc_sections(content)
    if not tcs:
        if violations:
            return False, "\n".join(violations)
        return True, ""

    all_tc_ids = [tc["tc_id"] for tc in tcs]
    active_ids = get_active_tc_ids(content, all_tc_ids)

    # 전체 본문 검증 파트 2: 추출된 TC 분석 기반 전역 룰
    for rule in rules:
        if rule.get("type") == "min_active_tc":
            min_count = rule.get("min_count", 1)
            # 만약 테이블 자체가 선언되지 않아서 전체 TC가 강제로 ACTIVE 처리되었다 하더라도
            # 실제 '명시적으로' ACTIVE임을 체크하기 위해, 테이블 파싱 결과를 직접 스캔할지 
            # 아니면 fallback 된 전체 active_ids 길이를 체크할지 결정.
            # get_active_tc_ids는 마커가 하나도 없으면 전체를 ACTIVE로 만드므로, 
            # 여기서 방어하려면 정규식으로 직접 마커 개수를 세어야 함.
            actual_active_count = len(_ACTIVE_MARKER_PATTERN.findall(content))
            if actual_active_count < min_count:
                violations.append(f"전역: {rule.get('detail')} (발견 {actual_active_count}개, 최소 {min_count}개 필요)")
    
    # TC 단위 검증
    for tc in tcs:
        tc_id = tc["tc_id"]
        body = tc["body"]

        # 블록인용 줄 제거 버전 (인용된 가이드/다른 TC 내용 오탐 유발 방지)
        non_quote_lines = [
            line for line in body.splitlines()
            if not line.lstrip().startswith(">")
        ]
        body_no_quotes = "\n".join(non_quote_lines)

        for rule in rules:
            rule_type = rule.get("type", "")
            if rule_type not in ("tc_each_match", "tc_active_match", "tc_na_constraint"):
                continue

            flags = rule.get("flags", 0)
            if isinstance(flags, str):
                flags = re.IGNORECASE if "i" in flags.lower() else 0

            if rule_type == "tc_each_match":
                if "extract_pattern" in rule:
                    val = get_field_value(body, rule["extract_pattern"])
                    if val is None or len(val) < rule.get("min_length", 1):
                        violations.append(f"TC-{tc_id}: {rule.get('name')} 누락 또는 빈 값")
                elif "pattern" in rule:
                    if not check_section_exists(body_no_quotes, rule["pattern"], flags):
                        violations.append(f"TC-{tc_id}: {rule.get('name')} 누락")

            elif rule_type == "tc_active_match":
                if tc_id in active_ids:
                    if not check_section_exists(body, rule["pattern"], flags):
                        violations.append(f"TC-{tc_id}: ACTIVE TC이나 {rule.get('name')} 누락")

            elif rule_type == "tc_na_constraint":
                # get_behavioral_condition과 동일하게 동작하도록 하드코딩된 로직을 그대로 두되, 향후 정규식으로 뺄 수 있음
                # 편의상 json 룰에 extract 로직을 얹음
                val = get_field_value(body, r"(?:\|\s*(?:\*\*)?행위적 조건(?:\*\*)?\s*\|\s*(.*?)\s*\||\*\*행위적 조건\*\*\s*:\s*(.+)|행위적 조건\s*:\s*(.+))")
                if val and bool(re.search(rule["na_pattern"], val, re.IGNORECASE)):
                    if check_section_exists(body, rule["deep_layer_pattern"]):
                        violations.append(f"TC-{tc_id}: {rule.get('detail')}")

    if violations:
        return False, "\n".join(violations)

    return True, ""


def validate(file_path: str, content: str) -> tuple[bool, str]:
    """테스트 시트 파일을 검증한다."""
    if "_테스트시트_" not in file_path:
        return True, ""

    try:
        # Load rules relative to this script's directory
        script_dir = Path(__file__).resolve().parent
        schema_path = script_dir.parent / "rules" / "_test_sheet_rules.json"
        rules = load_rules(str(schema_path))
    except Exception as e:
        return False, f"Rule schema 로드 실패: {e}"

    return run_checks(content, file_path, rules)


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
