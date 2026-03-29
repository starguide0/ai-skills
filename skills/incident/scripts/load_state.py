#!/usr/bin/env python3
"""
세션 중단 후 컨텍스트 복원.
state.json과 완료된 stage 파일들을 읽어 현재 분석 상태를 출력.
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

def list_all_incidents():
    incidents_dir = os.path.join(get_project_root(), 'incidents')

    if not os.path.exists(incidents_dir):
        print("No incidents found.")
        return

    def _incident_sort_key(d):
        parts = d.split('-')
        if len(parts) == 3 and parts[2].isdigit():
            return (parts[1], int(parts[2]))
        return (d, 0)
    dirs = sorted([d for d in os.listdir(incidents_dir) if d.startswith('INC-')], key=_incident_sort_key, reverse=True)
    print(f"{'ID':<25} {'Status':<15} {'Symptom':<40} {'Stage'}")
    print("-" * 90)
    for d in dirs:
        state_path = os.path.join(incidents_dir, d, 'state.json')
        if os.path.exists(state_path):
            with open(state_path, 'r', encoding='utf-8') as f:
                s = json.load(f)
            symptom = s.get('symptom_raw', '')[:38]
            status = s.get('status', 'unknown')
            current = s.get('current_stage', '?')
            completed = s.get('stages_completed', [])
            print(f"{d:<25} {status:<15} {symptom:<40} {current} (done: {completed})")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', help='Incident ID. 생략 시 최신 incident 사용')
    parser.add_argument('--latest', action='store_true', help='최신 incident 로드')
    parser.add_argument('--list', action='store_true', help='모든 incident 목록 출력')
    parser.add_argument('--stages', action='store_true', help='완료된 stage 내용 포함 출력')
    args = parser.parse_args()

    if args.list:
        list_all_incidents()
        return

    if args.latest or not args.id:
        incident_id = find_latest_incident()
    else:
        incident_id = args.id

    incident_dir = find_incident_dir(incident_id)
    state_path = os.path.join(incident_dir, 'state.json')

    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)

    print("=" * 60)
    print(f"📋 INCIDENT STATE RESTORED: {incident_id}")
    print("=" * 60)
    print(f"  Status         : {state.get('status', 'unknown')}")
    print(f"  Created at     : {state.get('created_at', '-')}")
    print(f"  Symptom        : {state.get('symptom_raw', '-')}")
    print(f"  Symptom type   : {state.get('symptom_type', '-')}")
    print(f"  Affected svc   : {state.get('affected_service', '-')}")
    print(f"  Current stage  : {state.get('current_stage', '-')}")
    print(f"  Stages done    : {state.get('stages_completed', [])}")
    print()

    # 필수 필드 현황
    required = state.get('required_db_fields', {})
    queried = state.get('db_fields_queried', {})

    print("━" * 60)
    print("🔴 REQUIRED DB FIELDS STATUS")
    print("━" * 60)
    if required:
        all_covered = True
        for table, fields in required.items():
            q = queried.get(table, [])
            for field in fields:
                status = "✓" if field in q else "✗"
                if field not in q:
                    all_covered = False
                print(f"  [{table}] {field}: {status}")
        print()
        if all_covered:
            print("  ✅ All required fields covered")
        else:
            print("  ⚠️  Some required fields not yet queried")
    else:
        print("  (Not defined)")

    # Findings
    findings = state.get('findings', {})
    if findings.get('root_cause'):
        print()
        print("━" * 60)
        print("🎯 ROOT CAUSE")
        print("━" * 60)
        print(f"  {findings['root_cause']}")

    # Stage 파일 내용 (--stages 옵션)
    if args.stages:
        stage_files = [
            'stage1_collection.md',
            'stage2_kibana.md',
            'stage3_mcp.md',
            'stage4_db.md',
            'stage5_rootcause.md',
            'report.md'
        ]
        for sf in stage_files:
            sf_path = os.path.join(incident_dir, sf)
            if os.path.exists(sf_path):
                print()
                print("━" * 60)
                print(f"📄 {sf}")
                print("━" * 60)
                with open(sf_path, 'r', encoding='utf-8') as f:
                    print(f.read())

    print()
    print("━" * 60)
    print(f"📁 Incident dir: {incident_dir}")
    print(f"   Use --stages to see all saved stage content")
    print("━" * 60)

if __name__ == '__main__':
    main()
