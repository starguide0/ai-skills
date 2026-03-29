#!/usr/bin/env python3
"""
Stage 결과를 파일로 저장하고 state.json을 업데이트한다.
컨텍스트 압박으로 LLM이 내용을 잃어도 파일에 보존됨.
"""

import sys
import json
import os
import select
import argparse
from datetime import datetime, timezone, timedelta


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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True, help='Incident ID (e.g. INC-20260319-001)')
    parser.add_argument('--stage', required=True, help='Stage number or name (1-5, or report)')
    parser.add_argument('--content', help='Content to save (or pass via stdin)')
    parser.add_argument('--fields', help='Comma-separated list of queried fields (e.g. service-out_order.urgent,batch_lifecycle.blocked)')
    parser.add_argument('--root-cause', help='Root cause description to record in findings (state.json)')
    args = parser.parse_args()

    incident_dir = find_incident_dir(args.id)
    state_path = os.path.join(incident_dir, 'state.json')

    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)

    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    timestamp = now.isoformat()

    # Stage 파일명 결정
    stage_filenames = {
        '1': 'stage1_collection.md',
        '2': 'stage2_kibana.md',
        '3': 'stage3_mcp.md',
        '4': 'stage4_db.md',
        '5': 'stage5_rootcause.md',
        'report': 'report.md'
    }
    filename = stage_filenames.get(args.stage, f'stage{args.stage}.md')
    stage_file = os.path.join(incident_dir, filename)

    # Content 처리
    content = args.content
    if not content:
        if sys.stdin.isatty():
            print("ERROR: --content 옵션 또는 stdin으로 내용을 전달하세요.", file=sys.stderr)
            print("예시: echo '분석 결과' | python3 save_stage.py --id INC-... --stage 1", file=sys.stderr)
            sys.exit(1)
        # 비-TTY 환경(예: Claude Bash tool)에서 데이터 없이 호출 시 무한 대기 방지
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            print("ERROR: --content 옵션 또는 stdin 데이터가 필요합니다.", file=sys.stderr)
            print("예시: echo '분석 결과' | python3 save_stage.py --id INC-... --stage 1", file=sys.stderr)
            sys.exit(1)
        content = sys.stdin.read()

    # 파일 저장
    with open(stage_file, 'w', encoding='utf-8') as f:
        f.write(f"# {args.id} — Stage {args.stage}\n")
        f.write(f"Saved at: {timestamp}\n\n")
        f.write(content)

    # DB 필드 기록 (--fields 옵션)
    if args.fields:
        field_list = [f.strip() for f in args.fields.split(',')]
        for field_path in field_list:
            if '.' in field_path:
                table, field = field_path.split('.', 1)
                if table not in state['db_fields_queried']:
                    state['db_fields_queried'][table] = []
                if field not in state['db_fields_queried'][table]:
                    state['db_fields_queried'][table].append(field)

    # Root cause 기록 (--root-cause 옵션)
    if args.root_cause:
        if 'findings' not in state:
            state['findings'] = {}
        state['findings']['root_cause'] = args.root_cause

    # state 업데이트
    stage_num = args.stage
    if stage_num.isdigit():
        stage_num = int(stage_num)
        if stage_num not in state['stages_completed']:
            state['stages_completed'].append(stage_num)
        state['current_stage'] = max(stage_num + 1, state.get('current_stage', 1))

    if args.stage == 'report':
        state['status'] = 'completed'
        # [지식 개선 제안] 기존 체크리스트와 비교
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            symptoms_path = os.path.join(script_dir, '..', 'checklists', 'symptoms.json')
            if os.path.exists(symptoms_path):
                with open(symptoms_path, 'r', encoding='utf-8') as f:
                    all_symptoms = json.load(f)
                
                s_type = state.get('symptom_type', 'unknown')
                required = all_symptoms.get(s_type, {}).get('required_db_fields', {})
                queried = state.get('db_fields_queried', {})
                
                suggestions = []
                # 1. 새 필드 발견 (New Findings)
                for q_table, q_fields in queried.items():
                    req_fields = required.get(q_table, [])
                    new_fields = [f for f in q_fields if f not in req_fields]
                    if new_fields:
                        suggestions.append(f"   - [추가 제안] Table `{q_table}`: {', '.join(new_fields)}")
                
                if suggestions:
                    suggestion_block = "\n\n---\n## 💡 지식 베이스(symptoms.json) 개선 제안\n"
                    suggestion_block += "이번 분석을 통해 발견된 새로운 필드들을 다음번 분석을 위해 체크리스트에 추가할 것을 권장합니다.\n"
                    suggestion_block += "\n".join(suggestions)
                    suggestion_block += "\n\n*승인 시 `checklists/symptoms.json` 파일을 수동으로 업데이트하세요.*"
                    
                    # 파일에 추가 기록
                    with open(stage_file, 'a', encoding='utf-8') as f:
                        f.write(suggestion_block)
                    print("💡 Knowledge Base improvement suggestions added to report.")
        except Exception as e:
            print(f"⚠️  Suggestion generation failed: {e}")

    state['last_updated'] = timestamp

    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"✅ Stage {args.stage} saved → {stage_file}")
    print(f"   Stages completed: {state['stages_completed']}")
    if args.fields:
        print(f"   DB fields recorded: {args.fields}")
    if args.root_cause:
        print(f"   Root cause recorded: {args.root_cause}")

if __name__ == '__main__':
    main()
