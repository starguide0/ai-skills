#!/usr/bin/env python3
"""flow_visualizer.py

Generates Mermaid sequence diagrams for E2E test flows from tc_spec.json.
This tool supports multi-node and multi-protocol visualization.

Usage:
    python3 flow_visualizer.py \
        --spec {ticket_folder}/tc_spec.json \
        --tc-id TC-001 \
        --output {ticket_folder}/flows/TC-001_flow.mmd
"""

import argparse
import json
import os
import sys

def generate_mermaid(tc_id, tc_data):
    """Generates Mermaid sequence diagram string from TC spec data."""
    steps = tc_data.get("stimulus", [])
    if not steps:
        return "Note over Tester: No stimulus steps defined"

    # Identify all participating nodes
    nodes = set()
    for step in steps:
        nodes.add(step.get("node", "Unknown"))
    
    # Optional: Add checkpoints or data flow targets if needed
    # For now, focus on stimulus nodes vs Tester
    
    lines = ["sequenceDiagram", "    autonumber"]
    lines.append("    participant T as Tester")
    
    # Sort nodes to keep order consistent? Or just add as they appear
    node_map = {}
    for i, node in enumerate(sorted(list(nodes))):
        alias = f"N{i}"
        node_map[node] = alias
        lines.append(f"    participant {alias} as {node}")

    current_node = None
    for step in steps:
        node = step.get("node", "Unknown")
        alias = node_map.get(node, "Unknown")
        action = step.get("action", {})
        method = action.get("method", "Action")
        
        # Determine the arrow type (sync/async)
        # Default to sync for simplicity in flow maps
        lines.append(f"    T->>+ {alias}: {method} ({node})")
        
        # If there's a response or output, show the return
        # In tc_spec.json, we don't have explicit returns, but we can assume one
        lines.append(f"    {alias}-->>- T: Response")
        
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Generate Mermaid sequence diagrams from tc_spec.json")
    parser.add_argument("--spec", required=True, help="tc_spec.json file path")
    parser.add_argument("--tc-id", help="Target TC ID (if omitted, generates for all)")
    parser.add_argument("--output", required=True, help="Output file path (or directory if --tc-id is omitted)")
    args = parser.parse_args()

    if not os.path.exists(args.spec):
        print(f"ERROR: Spec file not found: {args.spec}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec_data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # tc_spec.json 스키마: {"metadata": {...}, "tcs": {"TC-1": {...}, ...}}
    # 또는 flat: {"TC-1": {...}, ...} — 양쪽 모두 지원
    tcs = spec_data.get("tcs") if isinstance(spec_data.get("tcs"), dict) else spec_data

    # tcs가 dict가 아닌 경우(예: list) 에러 처리
    if not isinstance(tcs, dict):
        print(f"ERROR: spec 파일에서 TC 목록을 dict 형태로 파싱할 수 없습니다 (type={type(tcs).__name__})", file=sys.stderr)
        sys.exit(1)

    if args.tc_id:
        if args.tc_id not in tcs:
            print(f"ERROR: TC ID {args.tc_id} not found in spec", file=sys.stderr)
            sys.exit(1)

        mermaid_text = generate_mermaid(args.tc_id, tcs[args.tc_id])

        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid_text)
        print(f"✅ Generated flow for {args.tc_id} -> {args.output}")
    else:
        # Batch mode: generate for all TCs
        os.makedirs(args.output, exist_ok=True)
        for tc_id, tc_data in tcs.items():
            if tc_id == "metadata": continue
            mermaid_text = generate_mermaid(tc_id, tc_data)
            out_path = os.path.join(args.output, f"{tc_id}_flow.mmd")
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(mermaid_text)
            except OSError as e:
                print(f"WARNING: Failed to write {out_path}: {e}", file=sys.stderr)
                continue
        print(f"✅ Generated flows for {len(tcs)} TCs in {args.output}")

if __name__ == "__main__":
    main()
