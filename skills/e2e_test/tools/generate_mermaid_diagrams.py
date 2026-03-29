#!/usr/bin/env python3
"""generate_mermaid_diagrams.py

Generates Mermaid diagram drafts from _summary.json.

Outputs:
  pie        — Complete pie chart (pass/fail/nt/blocked counts)
  sequence   — Skeleton sequence diagram (TC execution flow)
  state      — Skeleton state diagram (status transitions)
  before_after — null (LLM fills this in, needs code understanding)

Usage:
    python3 generate_mermaid_diagrams.py \\
        --summary {ticket_folder}/partial_results/_summary.json \\
        --output  {ticket_folder}/partial_results/_mermaid_drafts.json
"""

import argparse
import json
import sys
from datetime import datetime


def load_summary(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_pie_chart(stats):
    """Build a complete Mermaid pie chart from stats."""
    lines = ['pie title 테스트 결과 분포']
    if stats.get("pass"):
        lines.append(f'    "PASS" : {stats["pass"]}')
    if stats.get("fail"):
        lines.append(f'    "FAIL" : {stats["fail"]}')
    if stats.get("nt"):
        lines.append(f'    "N/T" : {stats["nt"]}')
    if stats.get("blocked"):
        lines.append(f'    "BLOCKED" : {stats["blocked"]}')
    if stats.get("incomplete"):
        lines.append(f'    "INCOMPLETE" : {stats["incomplete"]}')
    # 데이터 세그먼트가 하나도 없으면 placeholder 추가 (Mermaid 렌더링 오류 방지)
    if len(lines) == 1:
        total = stats.get("total", 0)
        lines.append(f'    "데이터 없음 (실행된 TC: {total}개)" : 1')
    return "\n".join(lines)


def build_sequence_skeleton(tcs):
    """Build a skeleton sequence diagram showing TC execution order."""
    lines = [
        "sequenceDiagram",
        "    participant Tester",
        "    participant Server as BE API",
        "    participant DB",
    ]
    for tc in tcs:
        tc_id   = tc["tc_id"]
        status  = tc["status"]
        emoji   = {"PASS": "✅", "FAIL": "❌", "N/T": "⏭️",
                   "BLOCKED": "🚫", "INCOMPLETE": "⚠️"}.get(status, "❓")
        api_status = tc.get("api_status_code") or "?"
        lines.append(f"    Note over Tester,DB: {tc_id} {emoji}")
        if tc.get("tc_type") == "ACTIVE":
            lines.append(f"    Tester->>Server: {tc_id} API 호출")
            lines.append(f"    Server-->>Tester: HTTP {api_status}")
            if tc.get("has_db_changes"):
                lines.append(f"    Server->>DB: 상태 변경")
                lines.append(f"    DB-->>Server: 확인")
    return "\n".join(lines)


def build_state_skeleton(tcs):
    """Build a skeleton state diagram from observed status transitions."""
    pass_ids = [t["tc_id"] for t in tcs if t["status"] == "PASS"]
    fail_ids = [t["tc_id"] for t in tcs if t["status"] == "FAIL"]

    lines = [
        "stateDiagram-v2",
        "    [*] --> 실행중",
    ]
    if pass_ids:
        lines.append("    실행중 --> PASS : 검증 성공")
        lines.append(f"    note right of PASS : {', '.join(pass_ids[:3])}" +
                     (" 외" if len(pass_ids) > 3 else ""))
        lines.append("    PASS --> [*]")
    if fail_ids:
        lines.append("    실행중 --> FAIL : 검증 실패")
        lines.append(f"    note right of FAIL : {', '.join(fail_ids[:3])}" +
                     (" 외" if len(fail_ids) > 3 else ""))
        lines.append("    FAIL --> [*]")
    return "\n".join(lines)


def build_before_after_skeleton(stats):
    """Build a skeleton before/after graph showing the impact of the test."""
    lines = [
        "graph LR",
        "    subgraph Before",
        "        B1[기존 상태] --> B2[대상 데이터]",
        "    end",
        "    subgraph After",
        "        A1[검증 후 상태] --> A2[결과 반영]",
        "    end",
        "    B2 -.->|Test Execution| A1",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Mermaid diagram drafts from _summary.json")
    parser.add_argument("--summary", required=True, help="_summary.json file path")
    parser.add_argument("--output",  required=True, help="Output _mermaid_drafts.json file path")
    args = parser.parse_args()

    try:
        summary = load_summary(args.summary)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    stats = summary.get("stats", {})
    tcs   = summary.get("tcs", [])

    drafts = {
        "generated_at": datetime.now().isoformat(),
        "pie":          build_pie_chart(stats),
        "sequence":     build_sequence_skeleton(tcs),
        "state":        build_state_skeleton(tcs),
        "before_after": build_before_after_skeleton(stats),
        "note": "모든 Mermaid 다이어그램의 드래프트가 생성되었습니다. LLM은 이를 검토하고 구체적인 비즈니스 로직에 맞게 미세 조정만 수행하면 됩니다.",
    }

    if args.output:
        import os
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(drafts, f, indent=2, ensure_ascii=False)

    print(f"✅ Mermaid drafts generated: pie(완성), sequence(골격), state(골격), before_after(골격)")


if __name__ == "__main__":
    main()
