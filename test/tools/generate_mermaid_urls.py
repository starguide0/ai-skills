#!/usr/bin/env python3
"""generate_mermaid_urls.py

Generates mermaid.ink rendering URLs for each diagram in _mermaid_drafts.json.

Usage:
    python3 generate_mermaid_urls.py \\
        --ticket {ticket} \\
        --output {ticket_folder}/.mermaid_urls_{ticket}.json

Reads _mermaid_drafts.json from {output_path.parent}/partial_results/_mermaid_drafts.json.
--output should be the ticket-level output file (e.g., {ticket_folder}/.mermaid_urls_{ticket}.json).
"""

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path


MERMAID_INK_BASE = "https://mermaid.ink"


def encode_mermaid(source):
    """Encode Mermaid source to mermaid.ink URL format."""
    payload = json.dumps({"code": source, "mermaid": {}}, ensure_ascii=False)
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return encoded


def make_url(source, diagram_type="svg"):
    """Create a mermaid.ink URL for the given Mermaid source."""
    if not source:
        return None
    encoded = encode_mermaid(source)
    return f"{MERMAID_INK_BASE}/{diagram_type}/{encoded}"


def main():
    parser = argparse.ArgumentParser(description="Generate mermaid.ink URLs from _mermaid_drafts.json")
    parser.add_argument("--ticket", required=True, help="Ticket ID (e.g. WO-55)")
    parser.add_argument("--output", required=True, help="Output .mermaid_urls_{ticket}.json path")
    args = parser.parse_args()

    output_path = Path(args.output)
    drafts_path = output_path.parent / "partial_results" / "_mermaid_drafts.json"

    if not drafts_path.exists():
        print(f"ERROR: _mermaid_drafts.json not found at {drafts_path}", file=sys.stderr)
        print("Run generate_mermaid_diagrams.py first.", file=sys.stderr)
        sys.exit(1)

    try:
        with drafts_path.open(encoding="utf-8") as f:
            drafts = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in _mermaid_drafts.json — {e}", file=sys.stderr)
        sys.exit(1)

    urls = {
        "ticket":       args.ticket,
        "generated_at": datetime.now().isoformat(),
        "drafts_file":  str(drafts_path),
        "diagrams": {},
    }

    for diagram_type in ("pie", "sequence", "state", "before_after"):
        source = drafts.get(diagram_type)
        if source:
            urls["diagrams"][diagram_type] = {
                "svg": make_url(source, "svg"),
                "img": make_url(source, "img"),
                "source_preview": source[:200] + ("..." if len(source) > 200 else ""),
            }
        else:
            urls["diagrams"][diagram_type] = None

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=2, ensure_ascii=False)

    generated = [k for k, v in urls["diagrams"].items() if v]
    skipped   = [k for k, v in urls["diagrams"].items() if not v]
    print(f"✅ URLs generated: {generated} | skipped (null): {skipped}")
    print(f"   Output: {args.output}")


if __name__ == "__main__":
    main()
