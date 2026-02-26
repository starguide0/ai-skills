#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PostToolUse Hook: DB 쿼리/API 호출 후 관련 주의사항 리마인드.

Bash tool 실행 후 호출되어, 실행된 명령어를 분석하고
_caution_common_errors.md에서 관련 패턴을 추출하여 리마인드 메시지를 출력한다.

이 Hook은 deny하지 않음 — 정보 제공만 수행.

트리거 조건:
  1. stimulus_executor.py 실행 감지 → API 호출 주의사항 리마인드
  2. mcp__postgres_* 패턴 감지 → DB 쿼리 주의사항 리마인드
"""
import json
import re
import sys
from pathlib import Path


# _caution_common_errors.md 위치
CAUTION_FILE = Path(__file__).parent.parent / "rules" / "_caution_common_errors.md"

# 키워드 → 패턴 번호 매핑 캐시
_keyword_index: dict[str, list[str]] | None = None


def build_keyword_index() -> dict[str, list[str]]:
    """_caution_common_errors.md에서 키워드 인덱스를 구축한다."""
    global _keyword_index
    if _keyword_index is not None:
        return _keyword_index

    _keyword_index = {}
    if not CAUTION_FILE.exists():
        print(f"[remind_caution] WARNING: caution file not found: {CAUTION_FILE}", file=sys.stderr)
        return _keyword_index

    content = CAUTION_FILE.read_text(encoding="utf-8")

    # <!-- keywords: ... --> 패턴과 바로 뒤의 ## 제목을 추출
    pattern = re.compile(
        r"<!--\s*keywords:\s*(.+?)\s*-->\s*\n##\s+(.+?)(?:\n|$)",
        re.MULTILINE,
    )

    for match in pattern.finditer(content):
        keywords_str = match.group(1)
        section_title = match.group(2).strip()
        keywords = [k.strip().lower() for k in keywords_str.split(",")]
        for kw in keywords:
            if kw not in _keyword_index:
                _keyword_index[kw] = []
            _keyword_index[kw].append(section_title)

    return _keyword_index


def detect_db_query(tool_name: str, tool_input: dict) -> list[str]:
    """MCP postgres 쿼리 도구 사용을 감지하고 관련 키워드를 추출한다."""
    triggers = []

    # MCP postgres 도구 직접 호출 감지
    if tool_name and tool_name.startswith("mcp__postgres_"):
        triggers.append("mcp_postgres")
        triggers.append("query")

        sql = tool_input.get("sql", "")
        sql_lower = sql.lower()

        # SQL 내용에서 추가 키워드 감지
        if "join" in sql_lower:
            triggers.append("join")
            if "inner join" in sql_lower:
                triggers.append("inner_join")
            if "left join" in sql_lower:
                triggers.append("left_join")

        if "is null" in sql_lower or "is not null" in sql_lower:
            triggers.append("null")
            triggers.append("is_null")

        if "state" in sql_lower or "status" in sql_lower:
            triggers.append("state")
            triggers.append("enum")

        if "timestamp" in sql_lower or "created_at" in sql_lower or "updated_at" in sql_lower:
            triggers.append("timestamp")

        if not re.search(r"\blimit\b", sql_lower):
            triggers.append("limit")

        # 크로스 서비스 감지: 도구명에서 서비스 추출 + cross_service 키워드 추가
        service = tool_name.replace("mcp__postgres_", "").replace("__query", "")
        triggers.append(service)
        triggers.append("cross_service")

    return triggers


def detect_bash_command(tool_input: dict) -> list[str]:
    """Bash 명령어에서 API 호출/stimulus 관련 키워드를 추출한다."""
    triggers = []
    command = tool_input.get("command", "")

    if "stimulus_executor" in command:
        triggers.extend(["api", "stimulus", "http", "endpoint", "auth", "token"])

    if "curl" in command:
        triggers.extend(["api", "curl", "http"])

    return triggers


def match_cautions(trigger_keywords: list[str]) -> list[str]:
    """트리거 키워드와 caution 파일의 키워드를 매칭하여 관련 섹션 제목을 반환한다."""
    index = build_keyword_index()
    matched_sections = set()

    for kw in trigger_keywords:
        kw_lower = kw.lower()
        if kw_lower in index:
            matched_sections.update(index[kw_lower])

    return sorted(matched_sections)


def format_remind_message(sections: list[str], trigger_keywords: list[str]) -> str:
    """리마인드 메시지를 포맷한다."""
    if not sections:
        return ""

    kw_str = ", ".join(sorted(set(trigger_keywords))[:5])  # 유니크 키워드 중 상위 5개
    section_list = "\n".join(f"  - {s}" for s in sections)

    return (
        f"[Caution Remind] 관련 주의사항 ({kw_str}):\n"
        f"{section_list}\n"
        f"상세 내용: rules/_caution_common_errors.md 참조"
    )


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    trigger_keywords = []

    # 1. MCP postgres 도구 감지
    if tool_name.startswith("mcp__postgres_"):
        trigger_keywords.extend(detect_db_query(tool_name, tool_input))

    # 2. Bash 명령어 감지 (stimulus_executor, curl 등)
    if tool_name == "Bash":
        trigger_keywords.extend(detect_bash_command(tool_input))

    # 트리거 없으면 조용히 종료
    if not trigger_keywords:
        sys.exit(0)

    # 3. caution 파일 매칭
    matched_sections = match_cautions(trigger_keywords)
    if not matched_sections:
        sys.exit(0)

    # 4. 리마인드 메시지 출력 (deny가 아닌 정보 제공)
    message = format_remind_message(matched_sections, trigger_keywords)
    output = {
        "hookSpecificOutput": {
            "message": message,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
