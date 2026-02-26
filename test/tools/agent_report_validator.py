#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PostToolUse Hook: Worker 에이전트 보고서 구조 검증.

Task 도구 완료 후 호출되어, 서브에이전트가 harness-agent-report-v1 스키마로
보고서를 반환했는지 검증하고 누락된 필드에 대해 경고를 출력한다.

이 Hook은 deny하지 않음 — 정보 제공(message 주입)만 수행.

트리거: Task 도구 완료 후 tool_result에 "$schema": "harness-agent-report-v1" 포함 시
"""
import json
import re
import sys


# harness-agent-report-v1 필수 필드 및 누락 시 경고 메시지
REQUIRED_FIELDS = [
    ("task_summary", "작업 요약(task_summary)이 누락되었습니다"),
    ("findings",     "구체적 발견사항(findings)을 보고하지 않았습니다"),
    ("decisions",    "판단 근거(decisions)가 누락되었습니다"),
]

SCHEMA_ID = "harness-agent-report-v1"


def extract_schema_json(text: str) -> dict | None:
    """tool_result 텍스트에서 harness-agent-report-v1 JSON 블록을 추출한다."""
    if not text or SCHEMA_ID not in text:
        return None

    # 1차: 코드 블록 내 JSON 탐색 (```json ... ```)
    code_block_pattern = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
    for match in code_block_pattern.finditer(text):
        try:
            obj = json.loads(match.group(1))
            if obj.get("$schema") == SCHEMA_ID:
                return obj
        except (json.JSONDecodeError, AttributeError):
            continue

    # 2차: 원시 JSON 객체 탐색 (중첩 브레이스 균형 추적)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if obj.get("$schema") == SCHEMA_ID:
                            return obj
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break
        start = text.find("{", start + 1)

    return None


def validate_report(report: dict) -> list[str]:
    """보고서 필수 필드를 검증하고 경고 메시지 목록을 반환한다."""
    warnings = []

    # 필수 필드 존재 여부 검증
    for field, message in REQUIRED_FIELDS:
        if field not in report or report[field] is None:
            warnings.append(message)
        elif isinstance(report[field], list) and len(report[field]) == 0:
            warnings.append(message)

    # verification 결과 검증
    verification = report.get("verification", {})
    if isinstance(verification, dict):
        result = verification.get("result", "")
        if result == "fail":
            warnings.append("Worker 검증이 실패(fail)했습니다 — 확인 필요")
        elif result == "partial":
            warnings.append("Worker 검증이 부분적(partial)입니다")

    return warnings


def build_message(warnings: list[str], agent_role: str) -> str:
    """경고 메시지 목록을 포맷된 문자열로 변환한다."""
    role_label = f"[{agent_role}]" if agent_role else "[Worker]"
    warning_lines = "\n".join(f"  ⚠️ {w}" for w in warnings)
    return (
        f"[agent_report_validator] {role_label} 보고서 검증:\n"
        f"{warning_lines}"
    )


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    # Task 도구 완료만 처리
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Task":
        sys.exit(0)

    # tool_result에서 harness-agent-report-v1 JSON 추출
    tool_result = hook_input.get("tool_result", "")
    if isinstance(tool_result, dict):
        # tool_result가 이미 dict인 경우 직접 확인
        report = tool_result if tool_result.get("$schema") == SCHEMA_ID else None
    elif isinstance(tool_result, str):
        report = extract_schema_json(tool_result)
    else:
        sys.exit(0)

    # 스키마 없으면 조용히 종료 (이 훅의 대상 아님)
    if report is None:
        sys.exit(0)

    # 보고서 검증
    warnings = validate_report(report)
    if not warnings:
        # 모든 필드 정상 — 메시지 없이 종료
        sys.exit(0)

    agent_role = report.get("agent_role", "")
    message = build_message(warnings, agent_role)

    output = {
        "hookSpecificOutput": {
            "message": message,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
