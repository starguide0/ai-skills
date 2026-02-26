#!/usr/bin/env python3
from __future__ import annotations
"""Verdict calculator: compare expected vs actual API response values for TC verification."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def snake_to_camel(snake: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def get_nested(obj, path: str):
    """
    Navigate a nested object using dot notation and array indexing.
    e.g. "response.body.outboundOrderSkuGroups"
    Returns None if any key is missing.
    """
    keys = path.split(".")
    current = obj
    for key in keys:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            # If key is numeric index
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def find_key_in_obj(obj, target_key: str):
    """
    Search for a key in an object (top-level only).
    Tries exact match, then camelCase conversion.
    Returns (value, found_key) or (None, None).
    """
    if not isinstance(obj, dict):
        return None, None

    # Exact match first
    if target_key in obj:
        return obj[target_key], target_key

    # camelCase conversion
    camel = snake_to_camel(target_key)
    if camel in obj:
        return obj[camel], camel

    return None, None


def find_array_for_count(body, base_name: str):
    """
    For a `{base_name}_count` key, find the matching array in the response body.
    Tries: exact, camelCase, common variants.
    Returns (array, path_description) or (None, None).
    """
    if not isinstance(body, dict):
        return None, None

    candidates = [
        base_name,
        snake_to_camel(base_name),
        # If base_name is e.g. "groups", also try "outboundOrderSkuGroups"
    ]

    # ⚠️ 프로젝트별 커스터마이징 포인트: 응답 필드명 → 배열 후보 매핑
    # WMS 도메인 기준. 다른 도메인에서 사용 시 아래 매핑을 수정/추가.
    known_mappings = {
        "groups": ["outboundOrderSkuGroups", "groups"],
        "orders": ["orders", "outboundOrders"],
        "items": ["items"],
        "skus": ["skus"],
        "containers": ["assignedContainers", "containers"],
    }

    if base_name in known_mappings:
        candidates = known_mappings[base_name] + candidates

    for candidate in candidates:
        if candidate in body and isinstance(body[candidate], list):
            return body[candidate], candidate

    # Last resort: search all keys for arrays whose key ends with or equals base_name (case-insensitive)
    # Use suffix/equality check (not substring) to avoid false positives like "items" matching "commitmentItems"
    base_lower = base_name.lower().replace("_", "")
    for key, val in body.items():
        key_lower = key.lower().replace("_", "")
        if isinstance(val, list) and (key_lower == base_lower or key_lower.endswith(base_lower)):
            return val, key

    return None, None


def collect_all_quantities(body) -> list:
    """
    Collect all quantity values for total_qty calculation.

    Primary path (WMS Outbound): outboundOrderSkuGroups[*].skus[*].quantity
    Fallback (generic): recursive search for any 'quantity' field in the response.
    ⚠️ 다른 도메인에서 total_qty를 사용하는 경우 fallback 경로로 자동 전환됨.
    """
    quantities = []

    groups = body.get("outboundOrderSkuGroups") if isinstance(body, dict) else None
    if groups and isinstance(groups, list):
        for group in groups:
            skus = group.get("skus") if isinstance(group, dict) else None
            if skus and isinstance(skus, list):
                for sku in skus:
                    qty = sku.get("quantity") if isinstance(sku, dict) else None
                    if qty is not None:
                        quantities.append(qty)
        if quantities:
            return quantities

    # Fallback: search recursively for 'quantity' fields
    fallback_quantities = []

    def _collect(obj):
        if isinstance(obj, dict):
            if "quantity" in obj:
                fallback_quantities.append(obj["quantity"])
            for v in obj.values():
                _collect(v)
        elif isinstance(obj, list):
            for item in obj:
                _collect(item)

    _collect(body)
    return fallback_quantities


def check_all_field(body, field_name: str, expected_value):
    """
    For all_* keys: check that ALL elements in the target array have
    field_name == expected_value.
    field_name can be dot-navigated (e.g. outboundOrderState.name).
    Returns (result, actual_description, detail).
    """
    # Determine which array to iterate
    # Strip the field to find — look for it in first-level arrays
    # Heuristic: find the first array in body
    if not isinstance(body, dict):
        return "FAIL", None, "response body is not a dict"

    # Try to find an appropriate array using field_name hint
    array_obj = None
    array_key = None

    # Strategy 1: Use field_name to find related array
    # e.g. field_name="outboundOrderState" → look for arrays containing dicts with that field
    for key, val in body.items():
        if isinstance(val, list) and len(val) > 0:
            if isinstance(val[0], dict) and any(
                field_name.split(".")[0] in item for item in val[:1] if isinstance(item, dict)
            ):
                array_obj = val
                array_key = key
                break

    # Strategy 2: Fallback to first non-empty list of dicts
    if array_obj is None:
        for key, val in body.items():
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                array_obj = val
                array_key = key
                break

    if array_obj is None:
        return "FAIL", None, "no array found in response body"

    # Navigate to field within each element
    field_parts = field_name.split(".")
    values = []
    for item in array_obj:
        current = item
        for part in field_parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break
        # If value is a dict with 'name' and expected is a string, extract 'name' for comparison
        if isinstance(current, dict) and "name" in current and isinstance(expected_value, str):
            current = current["name"]
        values.append(current)

    all_match = all(v == expected_value for v in values)
    unique_vals = list(set(str(v) for v in values))
    count = len(values)

    if all_match:
        return "PASS", f"{expected_value} (all {count})", f"checked {array_key}[*].{field_name}, all={expected_value}"
    else:
        return "FAIL", str(unique_vals), f"checked {array_key}[*].{field_name}, values={unique_vals}"


def run_checks(expected: dict, actual_data: dict, actual_path: str) -> list:
    """
    Run all checks and return list of check result dicts.
    """
    checks = []

    # Extract body from actual_path (supports any custom path, not just "response.body")
    response_obj = get_nested(actual_data, actual_path)
    body = response_obj if response_obj is not None else {}

    # HTTP status code always lives at response.status_code regardless of actual_path
    full_response = actual_data.get("response", {}) if isinstance(actual_data, dict) else {}
    status_code = full_response.get("status_code") if isinstance(full_response, dict) else None

    for key, exp_val in expected.items():

        # --- 1. http_status ---
        if key == "http_status":
            actual_val = status_code
            result = "PASS" if actual_val == exp_val else "FAIL"
            checks.append({
                "field": key,
                "expected": exp_val,
                "actual": actual_val,
                "result": result,
            })
            continue

        # --- 2. *_count keys ---
        if key.endswith("_count"):
            base_name = key[:-len("_count")]
            arr, arr_key = find_array_for_count(body, base_name)
            if arr is None:
                checks.append({
                    "field": key,
                    "expected": exp_val,
                    "actual": None,
                    "result": "FAIL",
                    "detail": f"no array found for '{base_name}'",
                })
            else:
                actual_len = len(arr)
                result = "PASS" if actual_len == exp_val else "FAIL"
                checks.append({
                    "field": key,
                    "expected": exp_val,
                    "actual": actual_len,
                    "result": result,
                    "detail": f"{arr_key}.length={actual_len}",
                })
            continue

        # --- 3. total_qty ---
        if key == "total_qty":
            quantities = collect_all_quantities(body)
            total = sum(quantities) if quantities else 0
            result = "PASS" if total == exp_val else "FAIL"
            checks.append({
                "field": key,
                "expected": exp_val,
                "actual": total,
                "result": result,
                "detail": f"sum(outboundOrderSkuGroups[*].skus[*].quantity)={total}",
            })
            continue

        # --- 4. each_qty ---
        if key == "each_qty":
            quantities = collect_all_quantities(body)
            if not quantities:
                checks.append({
                    "field": key,
                    "expected": exp_val,
                    "actual": None,
                    "result": "FAIL",
                    "detail": "no quantity values found",
                })
            else:
                all_equal = all(q == exp_val for q in quantities)
                result = "PASS" if all_equal else "FAIL"
                unique_vals = list(set(quantities))
                checks.append({
                    "field": key,
                    "expected": exp_val,
                    "actual": unique_vals[0] if len(unique_vals) == 1 else unique_vals,
                    "result": result,
                    "detail": f"all quantities={quantities}",
                })
            continue

        # --- 5. all_* keys ---
        if key.startswith("all_"):
            field_name = key[len("all_"):]
            result, actual_desc, detail = check_all_field(body, field_name, exp_val)
            checks.append({
                "field": key,
                "expected": exp_val,
                "actual": actual_desc,
                "result": result,
                "detail": detail,
            })
            continue

        # --- 6. *_non_null keys ---
        if key.endswith("_non_null"):
            field_name = key[:-len("_non_null")]
            val, found_key = find_key_in_obj(body, field_name)
            if found_key is None:
                result = "FAIL"
                actual_desc = None
                detail = f"field '{field_name}' not found"
            elif val is None:
                result = "FAIL"
                actual_desc = None
                detail = f"{found_key} is null"
            else:
                result = "PASS"
                actual_desc = f"non-null ({type(val).__name__})"
                detail = f"{found_key} is not null"
            checks.append({
                "field": key,
                "expected": "non-null",
                "actual": actual_desc,
                "result": result,
                "detail": detail,
            })
            continue

        # --- 7. *_null keys ---
        # Convention: {field_name}_null → expect field_name to be null in response body.
        # Guard: field_name must be ≥ 3 chars to avoid false positives.
        #   e.g. "is_null" → field_name="is" (2 chars) → falls through to Generic (#8)
        #   e.g. "ids_null" → field_name="ids" (3 chars) → processed here
        if key.endswith("_null") and not key.endswith("_non_null"):
            field_name = key[:-len("_null")]
            if len(field_name) >= 3:
                val, found_key = find_key_in_obj(body, field_name)
                if found_key is None:
                    # Field not found — treat as null (it's absent)
                    result = "PASS"
                    actual_desc = None
                    detail = f"field '{field_name}' not found (treated as null)"
                elif val is None:
                    result = "PASS"
                    actual_desc = None
                    detail = f"{found_key} is null"
                else:
                    result = "FAIL"
                    actual_desc = val
                    detail = f"{found_key} is not null: {val}"
                checks.append({
                    "field": key,
                    "expected": None,
                    "actual": actual_desc,
                    "result": result,
                    "detail": detail,
                })
                continue
            # field_name < 3 chars: fall through to Generic (#8)

        # --- 8. Generic keys ---
        val, found_key = find_key_in_obj(body, key)
        if found_key is None:
            checks.append({
                "field": key,
                "expected": exp_val,
                "actual": None,
                "result": "FAIL",
                "detail": f"field '{key}' (or '{snake_to_camel(key)}') not found in response body",
            })
        else:
            # If value is a dict with 'name' and expected is a string, compare .name
            compare_val = val
            if isinstance(val, dict) and "name" in val and isinstance(exp_val, str):
                compare_val = val["name"]
            result = "PASS" if compare_val == exp_val else "FAIL"
            checks.append({
                "field": key,
                "expected": exp_val,
                "actual": compare_val,
                "result": result,
                "detail": f"{found_key}={compare_val}",
            })

    return checks


def main():
    parser = argparse.ArgumentParser(
        description="Compare expected vs actual API response values for TC verification."
    )
    parser.add_argument(
        "--expected",
        required=True,
        help="JSON string of expected values (flat key-value dict)",
    )
    parser.add_argument(
        "--actual-file",
        required=True,
        help="Path to the actual API response JSON file (from stimulus_executor.py)",
    )
    parser.add_argument(
        "--tc-id",
        required=True,
        help="TC identifier (e.g. TC-4)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (optional; writes to stdout if not provided)",
    )
    parser.add_argument(
        "--actual-path",
        default="response.body",
        help="JSONPath prefix to extract actual response body from file (default: response.body)",
    )
    args = parser.parse_args()

    # Parse expected JSON
    try:
        expected = json.loads(args.expected)
    except json.JSONDecodeError as e:
        print(f"ERROR: --expected is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(expected, dict):
        print("ERROR: --expected must be a JSON object (dict)", file=sys.stderr)
        sys.exit(1)

    # Load actual file
    actual_file = args.actual_file
    if not os.path.exists(actual_file):
        print(f"ERROR: actual-file not found: {actual_file}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(actual_file, "r", encoding="utf-8") as f:
            actual_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: actual-file is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Run checks
    checks = run_checks(expected, actual_data, args.actual_path)

    # Compute verdict
    pass_count = sum(1 for c in checks if c["result"] == "PASS")
    fail_count = sum(1 for c in checks if c["result"] == "FAIL")
    verdict = "PASS" if fail_count == 0 else "FAIL"

    result = {
        "tc_id": args.tc_id,
        "timestamp": datetime.now(KST).isoformat(),
        "checks": checks,
        "verdict": verdict,
        "pass_count": pass_count,
        "fail_count": fail_count,
    }

    output_str = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Verdict written to: {args.output}", file=sys.stderr)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
