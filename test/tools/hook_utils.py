from __future__ import annotations
"""공통 Hook 유틸리티 — 모든 PreToolUse/PostToolUse hook 스크립트에서 공유."""


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
        path = ""

    return tool_name, path
