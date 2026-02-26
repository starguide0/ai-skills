#!/usr/bin/env python3
"""validate_report_structure.py

Validates a Confluence test result markdown file for required sections.
Runs 17 structural checks and outputs _validation.json.

Usage:
    python3 validate_report_structure.py \\
        --file   {ticket}_Confluence_테스트결과_v1.0_2026-02-22.md \\
        --output partial_results/_validation.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def load_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def check_section_exists(content, pattern, flags=0):
    """Return True if pattern matches anywhere in content."""
    return bool(re.search(pattern, content, flags))


def run_checks(content, filepath):
    """Run all 17 structural checks. Returns list of result dicts."""
    results = []
    check_id = 0

    def add(name, passed, detail=""):
        nonlocal check_id
        check_id += 1
        results.append({
            "check_id": check_id,
            "name":     name,
            "status":   "PASS" if passed else "FAIL",
            "detail":   detail,
        })

    # 1. 용어 정의
    add("용어 정의 섹션",
        check_section_exists(content, r"용어\s*정의|Terms?\s*Definition", re.I),
        "헤더 또는 섹션 제목에 '용어 정의' 포함 여부")

    # 2. API 응답 필드 안내
    add("API 응답 필드 안내",
        check_section_exists(content, r"API\s*응답\s*필드\s*안내|API\s*Response\s*Fields?", re.I))

    # 3. 코드 수정 요약
    add("코드 수정 요약 (Code Change Summary)",
        check_section_exists(content, r"코드\s*수정\s*요약|Code\s*Change\s*Summary", re.I))

    # 4. 테스트 흐름 섹션 존재
    add("테스트 흐름 섹션",
        check_section_exists(content, r"테스트\s*흐름|Test\s*Flow", re.I))

    # 5. 사전 조건 DB 검증
    add("사전 조건 DB 검증",
        check_section_exists(content, r"사전\s*조건\s*(DB\s*)?검증|Pre.?condition\s*(DB\s*)?Verification", re.I))

    # 6. 근거 작성 규칙
    add("근거 작성 규칙",
        check_section_exists(content, r"근거\s*작성\s*규칙|Evidence\s*Guidelines?", re.I))

    # 7. TC 선정 이유 blockquote
    has_reason = check_section_exists(content, r">\s*\*\*선정\s*이유\*\*\s*:")
    add("TC 선정 이유 (blockquote 형식)", has_reason,
        "> **선정 이유**: ... 형식 blockquote 존재 여부")

    # 8. TC 상세 (Pass/Fail Evidence)
    add("TC 상세 (Pass/Fail Evidence)",
        check_section_exists(content, r"TC-\d+|TC \d+\.\d+"))

    # 9. TC 기대값 도출 트리 (├─① 패턴)
    add("TC 기대값 도출 트리",
        check_section_exists(content, r"[├└]─[①-⑨]|④\s*기대결과"),
        "├─① ... ④ 기대결과 ASCII 트리 존재 여부")

    # 10. TC 검증 diff 테이블
    add("TC 검증 diff 테이블",
        check_section_exists(content, r"\|\s*검증\s*항목\s*\|\s*기대\s*\|\s*실제\s*\|\s*판정"),
        "| 검증 항목 | 기대 | 실제 | 판정 | 테이블 존재 여부")

    # 11. 전체 결과 요약 (Summary)
    add("전체 결과 요약 (Summary)",
        check_section_exists(content, r"전체\s*결과\s*요약|Overall\s*Summary|결과\s*요약", re.I))

    # 12. Mermaid 코드블록
    add("Mermaid 코드블록",
        check_section_exists(content, r"```mermaid"),
        "```mermaid 코드블록 존재 여부")

    # 13. PASS TC ✅ 판정
    has_pass = check_section_exists(content, r"✅\s*PASS|status.*PASS|PASS.*✅", re.I)
    add("PASS TC ✅ 판정 존재", has_pass)

    # 14. FAIL TC ❌ 판정 + [Fail 근거]
    has_fail_marker = check_section_exists(content, r"❌|FAIL", re.I)
    has_fail_evidence = (not has_fail_marker) or check_section_exists(content, r"\[Fail\s*근거\]|기대\s*:\s|실제\s*:\s", re.I)
    add("FAIL TC 근거 존재 (있는 경우)", has_fail_evidence,
        "FAIL TC가 있으면 [Fail 근거] 또는 기대:/실제: 쌍 필요")

    # 15. Section 0.1~0.7 (Test Baseline)
    baseline_sections = [f"0.{i}" for i in range(1, 8)]
    found = [s for s in baseline_sections if check_section_exists(content, rf"###?\s*{re.escape(s)}")]
    add("Section 0 Test Baseline (0.1~0.7)",
        len(found) >= 5,
        f"발견된 서브섹션: {found} (5개 이상 필요)")

    # 16. TC 선정 이유 내용 비어있지 않음
    reason_matches = re.findall(r">\s*\*\*선정\s*이유\*\*\s*:\s*(.+)", content)
    non_empty = [m for m in reason_matches if m.strip() and len(m.strip()) > 5]
    add("TC 선정 이유 내용 非공백",
        len(non_empty) == len(reason_matches) if reason_matches else True,
        f"총 {len(reason_matches)}개 중 내용 있음: {len(non_empty)}개")

    # 17. Summary에 Pass/Fail 수치 존재
    add("Summary Pass/Fail 수치",
        check_section_exists(content, r"Pass\s*[:=]\s*\d+|PASS\s*[:=]\s*\d+|통과\s*[:=]\s*\d+", re.I),
        "요약 섹션에 Pass/Fail 개수 수치 존재 여부")

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate Confluence test report structure (17 checks)")
    parser.add_argument("--file",   required=True, help="Confluence 테스트결과 .md file path")
    parser.add_argument("--output", required=True, help="Output _validation.json path")
    args = parser.parse_args()

    try:
        content = load_file(args.file)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    results  = run_checks(content, args.file)
    total    = len(results)
    passed   = sum(1 for r in results if r["status"] == "PASS")
    failed   = sum(1 for r in results if r["status"] == "FAIL")

    output = {
        "generated_at": datetime.now().isoformat(),
        "file":         args.file,
        "total_checks": total,
        "pass_count":   passed,
        "fail_count":   failed,
        "results":      results,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    status_icon = "✅" if failed == 0 else "❌"
    print(f"{status_icon} Validation: {passed}/{total} PASS, {failed} FAIL")
    if failed:
        print("FAIL items:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  [{r['check_id']}] {r['name']} — {r['detail']}")


if __name__ == "__main__":
    main()
