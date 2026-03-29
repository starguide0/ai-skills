from __future__ import annotations
"""공통 Hook 유틸리티 — 모든 PreToolUse/PostToolUse hook 스크립트에서 공유."""

import re
import sys

# TC ID 패턴: TC-1, TC-1.1, TC-ABC-001 등 지원
TC_ID_PATTERN = r"TC-[A-Za-z0-9.\-]+"


def _tc_sort_key(tc_id: str) -> list:
    """TC-1.1, TC-10 등을 올바른 숫자 순서로 정렬."""
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', tc_id)]


def resolve_content(hook_input: dict) -> tuple[str, str]:
    """hook_input에서 tool_name과 파일 경로(또는 커맨드)를 추출한다.

    Returns:
        (tool_name, path_or_command) 튜플
    """
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    if tool_name in ("Write", "Edit", "Read"):
        path = tool_input.get("file_path", "")
    elif tool_name == "Bash":
        path = tool_input.get("command", "")
    else:
        if tool_name:
            sys.stderr.write(f"Warning: resolve_content — unknown tool_name: {tool_name!r}\n")
        path = ""

    return tool_name, path
