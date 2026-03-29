#!/usr/bin/env python3
from __future__ import annotations
"""
Claude Code PreToolUse Hook: 데이터 매핑 JSON 파일의 구조 검증.

Write/Edit tool이 데이터 매핑 파일을 쓰거나 수정할 때 호출되어,
필수 키, 상태 값, 통계 일치 여부 등을 검증하여 요건 미달 시 deny한다.

검증 항목은 이제 ../rules/_data_mapping_rules.json 에 정의되어 있다.
"""
import json
import sys
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from hook_utils import resolve_content


def load_schema(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def run_checks(data: dict, filepath: str, schema: dict) -> tuple[bool, str]:
    """JSON Schema를 기반으로 데이터 매핑 JSON을 검증하고 (성공여부, 실패사유)를 반환한다."""
    violations: list[str] = []

    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.exceptions.ValidationError as e:
            violations.append(f"Schema Validation Error: {e.message} at path: {' -> '.join([str(p) for p in e.absolute_path])}")
            return False, "\n".join(violations)
        except Exception as e:
            violations.append(f"Unexpected validation error: {e}")
            return False, "\n".join(violations)
    else:
        # jsonschema 모듈이 없는 환경을 위한 매우 희박한 권고
        sys.stderr.write("WARNING: 'jsonschema' module is not installed. Structural validation is skipped.\n")

    # 2. Summary Stats 점검 (Dynamic Summation - JSON schema 로는 불가)
    summary = data.get("summary", {})
    mappings = data.get("mappings", {})
    
    s_total = summary.get("total_tcs", 0)
    s_mapped = summary.get("mapped", 0)
    s_not_found = summary.get("not_found", 0)
    s_provisioning = summary.get("provisioning_needed", 0)
    s_provisioned = summary.get("provisioned", 0)
    s_skipped = summary.get("skipped", 0)
    s_mismatch = summary.get("behavioral_mismatch", 0)
    s_capture = summary.get("capture_planned", 0)
    s_blocked = summary.get("blocked", 0)
    s_partial_mapped = summary.get("partial_mapped", 0)

    # test-data.md 산식 기준:
    # mapped + not_found + provisioning_needed + provisioned + skipped + behavioral_mismatch + capture_planned + blocked + partial_mapped == total_tcs
    calc_sum = s_mapped + s_not_found + s_provisioning + s_provisioned + s_skipped + s_mismatch + s_capture + s_blocked + s_partial_mapped
    if s_total != calc_sum:
        violations.append(f"Summary total_tcs({s_total})이 세부 상태 합계({calc_sum})와 다름")

    actual_total = len(mappings)
    if s_total != actual_total:
        violations.append(f"Summary total_tcs({s_total})이 실제 mappings 내 TC 갯수({actual_total})와 다름")

    if violations:
        return False, "\n".join(violations)

    return True, ""


def validate(file_path: str, content: str) -> tuple[bool, str]:
    """데이터 매핑 파일을 검증한다. (valid, reason) 반환."""
    if "_data_mapping" not in file_path and "_mapping" not in file_path:
        return True, ""

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"JSON 파싱 실패: {str(e)}"

    try:
        script_dir = Path(__file__).resolve().parent
        schema_path = script_dir.parent / "rules" / "_data_mapping_rules.json"
        schema = load_schema(str(schema_path))
    except Exception as e:
        return False, f"Rule schema 로드 실패: {e}"

    return run_checks(data, file_path, schema)


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name, file_path = resolve_content(hook_input)
    # 데이터매핑 파일은 보통 전체 구조를 덮어쓰므로 Edit 도 함께 검증 시도 가능하지만,
    # Edit으로 일부만 수정될 경우 파싱 에러가 날 수 있으므로 Write만 강하게 잡을 수도 있다.
    # 일단은 두 경우 모두 JSON 구조가 올바른지 검사한다.
    
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
