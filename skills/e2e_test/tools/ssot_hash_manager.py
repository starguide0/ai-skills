#!/usr/bin/env python3
import sys
import json
import hashlib
import argparse

def compute_hash(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: file not found ({file_path})", file=sys.stderr)
        return None
    # Strip BOM if present (Windows 환경에서 생성된 파일 호환)
    content = content.lstrip('\ufeff')
    # Normalize line endings to avoid issues across OS
    content = content.replace('\r\n', '\n')
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def update_hash(markdown_path, json_path):
    md_hash = compute_hash(markdown_path)
    if md_hash is None:
        return 1
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: file not found ({json_path})", file=sys.stderr)
        return 1

    if not content.strip():
        print(f"❌ Error: json file is empty ({json_path})", file=sys.stderr)
        return 1

    try:
        spec = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"❌ Error: json file is not valid JSON ({json_path}): {e}", file=sys.stderr)
        return 1

    spec["markdown_hash"] = md_hash
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    
    print(f"✅ SSOT Hash updated in {json_path}")
    return 0

def verify_hash(markdown_path, json_path):
    md_hash = compute_hash(markdown_path)
    if md_hash is None:
        return 1
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: file not found ({json_path})", file=sys.stderr)
        return 1

    if not content.strip():
        print(f"❌ Error: json file is empty ({json_path})", file=sys.stderr)
        return 1

    try:
        spec = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"❌ Error: json file is not valid JSON ({json_path}): {e}", file=sys.stderr)
        return 1

    stored_hash = spec.get("markdown_hash")
    if not stored_hash:
        print(f"⚠️ markdown_hash not found in {json_path}. Skipping SSOT validation.", file=sys.stderr)
        return 0
    
    if md_hash != stored_hash:
        print(f"❌ SSOT Hash Mismatch: The test sheet ({markdown_path}) has been modified since it was generated. tc_spec.json is out of sync. Re-plan required.", file=sys.stderr)
        return 1
    
    print(f"✅ SSOT Hash validation passed.")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Manage SSOT Hash between Markdown Test Sheet and tc_spec.json")
    parser.add_argument("--mode", choices=["update", "verify"], required=True)
    parser.add_argument("--markdown", required=True, help="Path to the markdown test sheet")
    parser.add_argument("--json", required=True, help="Path to tc_spec.json")
    
    args = parser.parse_args()
    
    if args.mode == "update":
        sys.exit(update_hash(args.markdown, args.json))
    else:
        sys.exit(verify_hash(args.markdown, args.json))

if __name__ == "__main__":
    main()
