#!/usr/bin/env python3
"""
Stage 4 DB 조회 전/후 필수 필드 커버리지를 검증한다.
- --pre  : Stage 4 시작 전 실행. 반드시 조회해야 할 필드를 출력.
- --post : Stage 4 완료 후 실행. 누락 필드 검사. 누락 시 exit(1).
"""

import sys
import json
import os
import argparse


def get_project_root():
    """스크립트 위치(scripts/)에서 3단계 위로 올라가 프로젝트 루트를 결정한다.
    $CLAUDE_PROJECT_DIR 환경변수가 설정된 경우 해당 값을 우선 사용한다."""
    env_root = os.environ.get('CLAUDE_PROJECT_DIR')
    if env_root:
        return env_root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(script_dir, '..', '..', '..'))


def find_incident_dir(incident_id):
    incidents_dir = os.path.join(get_project_root(), 'incidents')
    incident_dir = os.path.join(incidents_dir, incident_id)

    if not os.path.exists(incident_dir):
        print(f"ERROR: Incident directory not found: {incident_dir}", file=sys.stderr)
        sys.exit(1)

    return incident_dir

def find_latest_incident():
    incidents_dir = os.path.join(get_project_root(), 'incidents')

    if not os.path.exists(incidents_dir):
        print("ERROR: No incidents directory found", file=sys.stderr)
        sys.exit(1)

    def _incident_sort_key(d):
        parts = d.split('-')
        if len(parts) == 3 and parts[2].isdigit():
            return (parts[1], int(parts[2]))
        return (d, 0)
    dirs = sorted([d for d in os.listdir(incidents_dir) if d.startswith('INC-')], key=_incident_sort_key)
    if not dirs:
        print("ERROR: No incidents found", file=sys.stderr)
        sys.exit(1)

    return dirs[-1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', help='Incident ID (e.g. INC-20260319-001). 생략 시 최신 incident 사용')
    parser.add_argument('--pre', action='store_true', help='Stage 4 시작 전 — 필수 필드 출력')
    parser.add_argument('--post', action='store_true', help='Stage 4 완료 후 — 커버리지 검증 (누락 시 exit 1)')
    args = parser.parse_args()

    # --pre 또는 --post 없으면 --pre로 동작
    if not args.pre and not args.post:
        args.pre = True

    incident_id = args.id or find_latest_incident()
    incident_dir = find_incident_dir(incident_id)
    state_path = os.path.join(incident_dir, 'state.json')

    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)

    required = state.get('required_db_fields', {})
    queried = state.get('db_fields_queried', {})

    if args.pre:
        print("=" * 60)
        print(f"🔴 STAGE 4 REQUIRED FIELDS CHECKLIST [{incident_id}]")
        print("=" * 60)
        print("아래 필드들을 Stage 4 DB 쿼리에 반드시 포함해야 합니다.")
        print()

        if not required:
            print("⚠️  Required fields가 정의되지 않음 (증상 타입 미매핑)")
            print("   → 직접 관련 필드를 판단하여 쿼리하세요.")
        else:
            for table, fields in required.items():
                print(f"  📋 [{table}]")
                for field in fields:
                    print(f"       ✗ {field}  ← SELECT에 포함 필요")

            print()
            print("━" * 60)
            print(f"⚡ Symptom type : {state.get('symptom_type', 'unknown')}")
            print(f"⚡ Affected svc : {state.get('affected_service', 'unknown')}")
            print("━" * 60)

            # Known causes도 출력
            # (symptoms.json에서 직접 읽기)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            checklist_path = os.path.join(script_dir, '..', 'checklists', 'symptoms.json')
            try:
                with open(checklist_path, 'r', encoding='utf-8') as f:
                    symptoms = json.load(f)
            except FileNotFoundError:
                print(f"⚠️  symptoms.json 없음 — known causes 출력 불가")
                symptoms = {}

            symptom_type = state.get('symptom_type', '')
            if symptom_type in symptoms:
                known_causes = symptoms[symptom_type].get('known_causes', [])
                if known_causes:
                    print()
                    print("⚠️  KNOWN CAUSES — DB에서 이 조건 해당 여부를 확인하세요:")
                    for i, cause in enumerate(known_causes, 1):
                        print(f"   {i}. {cause}")

        print()
        print("✅ 위 필드 확인 후 DB 쿼리를 작성하세요.")

    elif args.post:
        print("=" * 60)
        print(f"🔍 COVERAGE VALIDATION [{incident_id}]")
        print("=" * 60)

        if not required:
            print("⚠️  Required fields가 정의되지 않음 (증상 타입 미매핑)")
            print("   → 직접 관련 필드를 판단하여 검증하세요.")
            sys.exit(1)

        missing = {}
        for table, fields in required.items():
            queried_fields = queried.get(table, [])
            missing_fields = [f for f in fields if f not in queried_fields]
            if missing_fields:
                missing[table] = missing_fields

        if not missing:
            print("✅ ALL REQUIRED FIELDS COVERED")
            print()
            for table, fields in required.items():
                print(f"  [{table}]: {', '.join(fields)} ✓")
        else:
            print("🚨 MISSING FIELDS DETECTED — 분석 불완전")
            print()
            for table, fields in missing.items():
                print(f"  [{table}] 미조회 필드:")
                for field in fields:
                    print(f"    ✗ {field}")

            print()
            print("━" * 60)
            print("조치: save_stage.py --fields 옵션으로 조회한 필드를 기록하거나")
            print("      해당 필드를 포함한 쿼리를 추가로 실행하세요.")
            print("━" * 60)
            sys.exit(1)

if __name__ == '__main__':
    main()
