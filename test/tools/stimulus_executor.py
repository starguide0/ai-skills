#!/usr/bin/env python3
from __future__ import annotations
"""
STIMULUS Executor: ACTIVE TC의 API 호출을 기계적으로 실행한다.

Claude Code가 Bash tool로 이 스크립트를 호출하면,
지정된 HTTP 요청을 실행하고 구조화된 JSON 증거를 반환한다.
LLM이 "판단"할 여지 없이 코드가 HTTP 요청을 실행한다.

Usage:
  # API 호출
  python3 stimulus_executor.py \\
    --method POST \\
    --url "https://oms-api.argoport.co/order/event/cancel" \\
    --header "Authorization: Bearer TOKEN" \\
    --header "Content-Type: application/json" \\
    --body '{"orderId": "12345"}' \\
    --tc-id TC-1 \\
    --output {ctx.ticket_folder}/partial_results/TC-1_stimulus.json  # 절대 경로 필수

  # 인증 토큰 발급
  python3 stimulus_executor.py \\
    --auth-login \\
    --auth-url "https://sugar-api.argoport.co/api/auth/login" \\
    --auth-body '{"loginId": "user", "password": "pass"}'

  # 인증 + API 호출 한번에
  python3 stimulus_executor.py \\
    --method POST \\
    --url "https://oms-api.argoport.co/order/event/cancel" \\
    --header "Content-Type: application/json" \\
    --body '{"orderId": "12345"}' \\
    --tc-id TC-1 \\
    --auth-url "https://sugar-api.argoport.co/api/auth/login" \\
    --auth-body '{"loginId": "user", "password": "pass"}' \\
    --output {ctx.ticket_folder}/partial_results/TC-1_stimulus.json  # 절대 경로 필수
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("ERROR: requests 라이브러리가 필요합니다.", file=sys.stderr)
    print("설치: pip3 install -r .claude/skills/test/tools/requirements.txt", file=sys.stderr)
    sys.exit(1)


KST = timezone(timedelta(hours=9))


def login(auth_url: str, auth_body: dict, timeout: int = 30) -> str:
    """인증 토큰을 발급받는다."""
    resp = requests.post(
        auth_url,
        json=auth_body,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    token = (
        data.get("accessToken")
        or data.get("data", {}).get("token")
        or data.get("token")
    )
    if not token:
        raise ValueError(f"토큰을 찾을 수 없습니다. 응답: {json.dumps(data, ensure_ascii=False)[:200]}")
    return token


def execute_stimulus(
    method: str,
    url: str,
    headers: dict,
    body: dict | None,
    timeout: int = 30,
) -> dict:
    """HTTP 요청을 실행하고 구조화된 결과를 반환한다."""
    start = time.monotonic()
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None,
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        try:
            resp_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            resp_body = resp.text[:2000] if resp.text else None

        # 민감 헤더 필터링 (파일 저장 시 보안)
        SENSITIVE_HEADERS = {"set-cookie", "authorization", "x-api-key", "cookie"}
        safe_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in SENSITIVE_HEADERS
        }

        return {
            "status_code": resp.status_code,
            "headers": safe_headers,
            "body": resp_body,
            "elapsed_ms": elapsed_ms,
        }
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status_code": None,
            "error": "TIMEOUT",
            "elapsed_ms": elapsed_ms,
        }
    except requests.exceptions.ConnectionError as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status_code": None,
            "error": f"CONNECTION_ERROR: {str(e)[:200]}",
            "elapsed_ms": elapsed_ms,
        }


def parse_headers(header_list: list[str]) -> dict:
    """CLI --header 인자를 dict로 변환한다."""
    headers = {}
    for h in header_list:
        if ":" in h:
            key, value = h.split(":", 1)
            headers[key.strip()] = value.strip()
    return headers


def main():
    parser = argparse.ArgumentParser(
        description="STIMULUS Executor: ACTIVE TC의 API 호출을 기계적으로 실행"
    )
    parser.add_argument("--method", help="HTTP 메서드 (GET/POST/PUT/DELETE/PATCH)")
    parser.add_argument("--url", help="요청 URL")
    parser.add_argument("--header", action="append", default=[], help="헤더 (Key: Value)")
    parser.add_argument("--body", help="요청 본문 (JSON 문자열)")
    parser.add_argument("--body-file", help="요청 본문 파일 경로")
    parser.add_argument("--tc-id", help="TC ID (출력 JSON에 포함)")
    parser.add_argument("--output", help="출력 파일 경로 (미지정 시 stdout)")
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃 (초)")

    parser.add_argument("--auth-login", action="store_true", help="인증 토큰 발급 모드")
    parser.add_argument("--auth-url", help="인증 엔드포인트 URL")
    parser.add_argument("--auth-body", help="인증 요청 본문 (JSON 문자열)")

    args = parser.parse_args()

    # --- 인증 처리 ---
    token = None
    if args.auth_login or args.auth_url:
        if not args.auth_url:
            print("ERROR: --auth-url 필수", file=sys.stderr)
            sys.exit(1)

        auth_body = None
        if args.auth_body:
            auth_body = json.loads(args.auth_body)
        else:
            print("ERROR: --auth-body 필수 (JSON 문자열)", file=sys.stderr)
            sys.exit(1)

        try:
            token = login(args.auth_url, auth_body, args.timeout)
        except Exception as e:
            print(f"ERROR: 인증 실패 — {e}", file=sys.stderr)
            sys.exit(1)

        if args.auth_login and not args.method:
            print(f"Bearer {token}")
            sys.exit(0)

    # --- API 호출 ---
    if not args.method or not args.url:
        if token:
            print(f"Bearer {token}")
            sys.exit(0)
        parser.print_help()
        sys.exit(1)

    headers = parse_headers(args.header)

    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"

    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    body = None
    if args.body:
        body = json.loads(args.body)
    elif args.body_file:
        with open(args.body_file) as f:
            body = json.load(f)

    response = execute_stimulus(args.method, args.url, headers, body, args.timeout)

    result = {
        "tc_id": args.tc_id or "unknown",
        "timestamp": datetime.now(KST).isoformat(),
        "request": {
            "method": args.method.upper(),
            "url": args.url,
            "headers": {k: (v[:20] + "..." if k == "Authorization" else v) for k, v in headers.items()},
            "body": body,
        },
        "response": response,
        # 네트워크 연결 성공 여부 (HTTP 상태 코드와 무관)
        # HTTP 레벨 PASS/FAIL 판정은 verdict_calculator.py의 http_status 체크가 담당
        "success": response.get("status_code") is not None,
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"STIMULUS 결과 저장: {args.output}", file=sys.stderr)
        sc = response.get("status_code", "N/A")
        ms = response.get("elapsed_ms", "?")
        print(f"{args.method.upper()} {args.url} → HTTP {sc} ({ms}ms)")
    else:
        print(output_json)

    if response.get("error"):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
