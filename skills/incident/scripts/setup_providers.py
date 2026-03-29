#!/usr/bin/env python3
"""
Provider 설정 마법사 (HITL).
providers.json이 없을 때 실행하여 대화형으로 설정을 생성한다.
다중 DB 지원 및 선택적 스킵 기능을 포함한다.
"""

import sys
import json
import os
import argparse

SETTINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'settings')
PROVIDERS_PATH = os.path.join(SETTINGS_DIR, 'providers.json')

LOG_TYPES = {
    '1': ('kibana', 'Kibana (Elasticsearch)'),
    '2': ('s3', 'S3 로그 파일'),
    '3': ('cloudwatch', 'AWS CloudWatch'),
    '4': ('custom', '직접 입력'),
    '0': ('skip', '건너뛰기 (설정 안 함)'),
}

DB_TYPES = {
    '1': ('postgres-mcp', 'PostgreSQL MCP (개발환경 직접 조회)'),
    '2': ('prod-readonly', '운영 DB readonly (쿼리 생성 → 사용자 실행)'),
    '3': ('mysql-cli', 'MySQL CLI'),
    '4': ('custom', '직접 입력'),
}

def print_setup_guide():
    print("=" * 60)
    print("⚙️  INCIDENT PROVIDER 설정 마법사 (v1.2.0)")
    print("=" * 60)
    print()
    print("장애 분석에 필요한 로그, 코드, DB 정보를 설정합니다.")
    print("설정 후 skills/incident/settings/providers.json에 저장됩니다.")
    print()

def print_log_question():
    print("━" * 60)
    print("📋 [1] 로그 조회 방식")
    print("━" * 60)
    for key, (_, label) in LOG_TYPES.items():
        print(f"  {key}. {label}")
    print()
    print("선택 (0-4): ")

def print_code_question():
    print("━" * 60)
    print("📋 [2] 코드 분석 도구")
    print("━" * 60)
    print("  사용하는 코드 분석 도구를 입력하거나 'skip'을 입력하세요.")
    print()
    print("입력 (또는 skip): ")

def print_db_question(index=1):
    print("━" * 60)
    print(f"📋 [3-{index}] DB 조회 방식")
    print("━" * 60)
    for key, (_, label) in DB_TYPES.items():
        print(f"  {key}. {label}")
    print()
    print("  * DB는 여러 개 등록할 수 있습니다.")
    print(f"  * 이 DB의 별칭(Name)을 정해주세요. (예: primary, inventory, billing)")
    print()
    print("선택 (1-4): ")

def save_providers(all_providers):
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    
    # 주석 추가
    output = {
        "_comment": "이 파일은 setup_providers.py에 의해 생성되었습니다."
    }
    output.update(all_providers)

    with open(PROVIDERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("✅ providers.json 저장 완료")
    print("=" * 60)
    print(f"  📁 {PROVIDERS_PATH}")
    print()
    print("  등록된 서비스:")
    for key, val in all_providers.items():
        p_type = val.get('type')
        print(f"    - {key} ({p_type})")
    print()
    print("  이제 incident 분석을 시작할 수 있습니다.")

def main():
    parser = argparse.ArgumentParser(description='Incident provider 설정 마법사')
    parser.add_argument('--log', help='로그 타입 (1-4 또는 skip)')
    parser.add_argument('--log-url', help='로그 서비스 URL')
    parser.add_argument('--code', help='코드 분석 도구 설명 (또는 skip)')
    parser.add_argument('--db', action='append', help='DB 설정 (format: "name:type:env") - 여러 번 호출 가능')
    parser.add_argument('--metadata-docs', help='메타데이터 문서 경로 (예: "skills/incident/docs")')
    parser.add_argument('--metadata-mcp', help='메타데이터 MCP 설정 (format: "server:tool:query")')
    parser.add_argument('--show-questions', action='store_true', help='질문 항목 출력')
    args = parser.parse_args()

    if args.show_questions:
        print_setup_guide()
        print_log_question()
        print()
        print_code_question()
        print()
        print_db_question()
        print()
        print("━" * 60)
        print("📋 [4] 메타데이터 조회 방식 (선택)")
        print("━" * 60)
        print("  서비스에 대한 아키텍처 문서나 MCP 메타데이터를 등록할 수 있습니다.")
        print("  --metadata-docs \"path/to/docs\"")
        print("  --metadata-mcp \"server:tool:query\"")
        print()
        print("━" * 60)
        print("📌 여러 개의 DB를 등록하려면 --db 옵션을 분석된 DB 수만큼 반복하세요.")
        print("   형식: --db \"name:type:env\" (예: --db \"primary:2:prod\" --db \"billing:1:dev\")")
        print()
        print("  python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/setup_providers.py \\")
        print("    --log 1 --log-url \"https://...\" \\")
        print("    --code \"core-system MCP\" \\")
        print("    --db \"primary:2:prod\" \\")
        print("    --metadata-docs \"skills/incident/docs/service\"")
        return

    all_providers = {}

    # 1. Log 처리
    if args.log and args.log != '0' and args.log.lower() != 'skip':
        log_type = LOG_TYPES.get(args.log, (args.log, ''))[0]
        log_config = {"env": "prod"}
        if args.log_url:
            log_config["url"] = args.log_url
        elif log_type == 'kibana':
            print("ERROR: Kibana 선택 시 --log-url이 필요합니다.", file=sys.stderr)
            print("예시: --log 1 --log-url \"https://kibana.yourcompany.com\"", file=sys.stderr)
            sys.exit(1)
        all_providers["log"] = {"type": log_type, "config": log_config}

    # 2. Code 처리
    if args.code and args.code.lower() != 'skip':
        all_providers["code"] = {
            "type": "custom",
            "description": args.code,
            "notes": "사용자가 직접 명시한 코드 분석 도구"
        }

    # 3. DB 처리
    if args.db:
        for db_entry in args.db:
            try:
                # name:type:env (예: primary:1:prod)
                parts = db_entry.split(':')
                name = parts[0]
                d_type_key = parts[1]
                env = parts[2] if len(parts) > 2 else 'prod'
                
                db_type = DB_TYPES.get(d_type_key, (d_type_key, ''))[0]
                db_config = {
                    "env": env,
                    "direct_access": db_type == 'postgres-mcp'
                }
                
                # 키 이름 중복 방지 (db-name 형식)
                provider_key = f"db-{name}" if not name.startswith('db-') else name
                all_providers[provider_key] = {
                    "type": db_type,
                    "config": db_config
                }
            except Exception as e:
                print(f"⚠️  DB 설정 파싱 오류 ({db_entry}): {e}")

    # 4. Metadata 처리
    if args.metadata_docs:
        all_providers["metadata-docs"] = {
            "type": "document",
            "config": {
                "path": args.metadata_docs,
                "recursive": True
            }
        }
    
    if args.metadata_mcp:
        try:
            parts = args.metadata_mcp.split(':')
            server = parts[0]
            tool = parts[1]
            query = parts[2] if len(parts) > 2 else "SELECT * FROM metadata WHERE service = '{service}'"
            all_providers["metadata-mcp"] = {
                "type": "mcp",
                "config": {
                    "server": server,
                    "tool": tool,
                    "query": query
                }
            }
        except Exception as e:
            print(f"⚠️  Metadata MCP 설정 파싱 오류: {e}")

    if not all_providers:
        print("⚠️  설정할 내용이 없습니다. 최소 하나 이상의 provider를 설정하세요.")
        return

    save_providers(all_providers)

if __name__ == '__main__':
    main()
