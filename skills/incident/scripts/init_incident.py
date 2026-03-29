#!/usr/bin/env python3
"""
Incident 분석 초기화 스크립트.
- 환경 초기화 (settings/ 및 providers.json 자동 생성)
- Incident ID 및 폴더 생성
- state.json 작성
- 조사 가이드(guides/) 동적 생성
"""

import sys
import json
import os
import shutil
from datetime import datetime, timezone, timedelta


def get_project_root():
    """스크립트 위치(scripts/)에서 3단계 위로 올라가 프로젝트 루트를 결정한다.
    $CLAUDE_PROJECT_DIR 환경변수가 설정된 경우 해당 값을 우선 사용한다."""
    env_root = os.environ.get('CLAUDE_PROJECT_DIR')
    if env_root:
        return env_root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(script_dir, '..', '..', '..'))

# --- 가이드 템플릿 (임베디드) ---
GUIDE_TEMPLATES = {
    "kibana": """# Kibana 로그 분석 가이드
- **URL**: {url}
- **환경**: {env}
- **추천 쿼리**:
  - `message: "*ERROR*"`
  - `traceId: "{incident_id}"` (만약 traceId를 알 수 있는 경우)
  - `serviceName: "{service}"`
""",
    "s3": """# S3 로그 조회 가이드
- **Bucket**: {bucket}
- **Region**: {region}
- **조회 방법**:
  - `aws s3 ls s3://{bucket}/logs/{date}/`
  - `aws s3 cp s3://{bucket}/path/to/log.gz .`
""",
    "postgres-mcp": """# Postgres MCP 조회 가이드
- **도구**: `postgres_dev_ai` 또는 `postgres_prod_readonly` MCP
- **조회 전략**:
  - `mcp_postgres_dev_ai_query(sql="SELECT * FROM ... LIMIT 10")`
  - 장애 발생 시점 전후의 레코드를 우선 확인하세요.
""",
    "prod-readonly": """# 운영 DB 조회 가이드 (Read-Only)
- **환경**: {env}
- **주의사항**: {note}
- **조회 방법**:
  - 직접 연결이 불가한 경우, 쿼리를 먼저 작성하여 검토 후 사용자에게 실행을 요청하세요.
""",
    "custom": """# 분석 도구 가이드 ({type})
- **설명**: {description}
- **참고**: {notes}
""",
    "document": """# 서비스 메타데이터 문서 가이드
- **대상 경로**: `{path}`
- **조사 방법**:
  - 위 경로에 포함된 아키텍처, 의존성, 필드 정의 문서를 확인하여 장애 컨텍스트를 파악하세요.
  - `ls -R {path}` 명령어로 전체 문서 구조를 확인할 수 있습니다.
""",
    "mcp": """# 서비스 메타데이터 MCP 조회 가이드
- **서버**: `{server}`
- **도구**: `{tool}`
- **조회 쿼리**:
  ```sql
  {query}
  ```
- **실행 방법**:
  - 위 쿼리를 실행하여 서비스(대상: {service})의 최신 메타데이터(아키텍처, 소유자, 의존성 등)를 수집하세요.
"""
}

def load_symptoms():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    checklist_path = os.path.join(script_dir, '..', 'checklists', 'symptoms.json')
    if not os.path.exists(checklist_path):
        # 기본 symptoms.json이 없는 경우 최소한의 구조 반환
        return {"unknown": {"keywords": [], "required_db_fields": {}, "known_causes": ["원인 미상"]}}
    with open(checklist_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def detect_symptom_type(symptom_text, symptoms):
    symptom_lower = symptom_text.lower()
    for symptom_type, config in symptoms.items():
        for keyword in config.get('keywords', []):
            if keyword in symptom_lower or keyword in symptom_text:
                return symptom_type
    return 'unknown'

def ensure_settings():
    """settings/ 폴더와 providers.json이 없으면 자동 생성."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_dir = os.path.normpath(os.path.join(script_dir, '..', 'settings'))
    providers_path = os.path.join(settings_dir, 'providers.json')
    example_path = os.path.join(settings_dir, 'providers.json.example')

    if not os.path.exists(settings_dir):
        os.makedirs(settings_dir, exist_ok=True)

    if not os.path.exists(providers_path):
        if os.path.exists(example_path):
            shutil.copy(example_path, providers_path)
            print(f"ℹ️  '{providers_path}' 파일을 생성했습니다. (example 복사)")
        else:
            # 완전 초기값
            default_providers = {
                "log": {"type": "kibana", "config": {"url": "https://log-kibana.yourcompany.com", "env": "prod"}},
                "code": {"type": "custom", "description": "Code analysis tools"},
                "db": {"type": "prod-readonly", "config": {"env": "prod", "direct_access": False}}
            }
            with open(providers_path, 'w', encoding='utf-8') as f:
                json.dump(default_providers, f, indent=2, ensure_ascii=False)
            print(f"ℹ️  '{providers_path}' 파일을 생성했습니다. (기본 템플릿)")
    
    # 설정값 검증 (플레이스홀더 여부 확인)
    try:
        with open(providers_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            log_url = config.get('log', {}).get('config', {}).get('url', '')
            if 'yourcompany.com' in log_url or 'example.com' in log_url or not log_url:
                print("\n" + "!" * 65)
                print("⚠️  ACTION REQUIRED: PROVIDER 설정이 완료되지 않았습니다.")
                print("!" * 65)
                print("  현재 'yourcompany.com' 플레이스홀더가 포함되어 있습니다.")
                print("  정확한 분석을 위해 아래 명령어로 설정을 완료해주세요:")
                print(f"\n  python3 {os.path.join(script_dir, 'setup_providers.py')} --show-questions")
                print("!" * 65 + "\n")
    except Exception:
        pass

    return providers_path

def create_guides(incident_dir, incident_id, symptom_config, providers):
    """Incident 전용 조사 가이드 생성."""
    guides_dir = os.path.join(incident_dir, 'guides')
    os.makedirs(guides_dir, exist_ok=True)

    for p_key, p_val in providers.items():
        if not isinstance(p_val, dict):
            continue
            
        p_type = p_val.get('type')
        template = GUIDE_TEMPLATES.get(p_type, GUIDE_TEMPLATES['custom'])
        
        # 데이터 병합용 컨텍스트 (기본값 제공으로 KeyError 방지)
        context = {
            "incident_id": incident_id,
            "service": symptom_config.get('affected_service', 'unknown'),
            "date": datetime.now().strftime('%Y%m%d'),
            "type": p_type,
            "url": "N/A",
            "env": "N/A",
            "bucket": "N/A",
            "region": "N/A",
            "description": "N/A",
            "notes": "정보 없음",
            "note": "정보 없음"
        }
        # providers.json의 config 내용을 context에 업데이트
        if 'config' in p_val:
            context.update(p_val['config'])
        if 'description' in p_val:
            context['description'] = p_val['description']
        if 'notes' in p_val:
            context['notes'] = p_val['notes']
            context['note'] = p_val['notes'] # 별칭 대응
        
        # 쿼리에 {service} 등이 포함된 경우 미리 치환 (Recursive formatting 지원)
        if 'query' in context and isinstance(context['query'], str):
            try:
                context['query'] = context['query'].format(**context)
            except Exception:
                pass

        try:
            # 템플릿에 정의된 키가 context에 없어도 에러가 나지 않도록 처리
            guide_content = template.format(**context)
            guide_path = os.path.join(guides_dir, f"{p_key}_{p_type}.md")
            with open(guide_path, 'w', encoding='utf-8') as f:
                f.write(guide_content)
        except Exception as e:
            print(f"⚠️  가이드 생성 실패 ({p_key}): {e}")

def get_next_incident_id(incidents_dir, date_str):
    if not os.path.exists(incidents_dir):
        return f"INC-{date_str}-001"

    existing = [d for d in os.listdir(incidents_dir) if d.startswith(f"INC-{date_str}-")]
    if not existing:
        return f"INC-{date_str}-001"

    numbers = []
    for d in existing:
        parts = d.split('-')
        if len(parts) == 3 and parts[2].isdigit():
            numbers.append(int(parts[2]))

    next_num = max(numbers) + 1 if numbers else 1
    return f"INC-{date_str}-{next_num:03d}"

def ensure_checklists():
    """checklists/ 폴더와 symptoms.json이 없으면 자동 생성."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    checklists_dir = os.path.join(script_dir, '..', 'checklists')
    symptoms_path = os.path.join(checklists_dir, 'symptoms.json')

    if not os.path.exists(checklists_dir):
        os.makedirs(checklists_dir, exist_ok=True)

    if not os.path.exists(symptoms_path):
        # 완전 초기값
        default_symptoms = {
            "pipeline_blocked": {
                "keywords": ["blocked", "delay", "정체", "지연"],
                "affected_service": "service-out-service",
                "required_db_fields": {
                    "service-out_summary": ["status", "is_blocked", "last_updated_at"]
                },
                "known_causes": ["인프라 부하", "비정상 데이터 유입", "락(Lock) 경합"]
            },
            "unknown": {
                "keywords": [],
                "affected_service": "unknown",
                "required_db_fields": {},
                "known_causes": ["원인 미상 - 분석 필요"]
            }
        }
        with open(symptoms_path, 'w', encoding='utf-8') as f:
            json.dump(default_symptoms, f, indent=2, ensure_ascii=False)
        print(f"ℹ️  '{symptoms_path}' 파일을 생성했습니다. (기본 템플릿)")

def validate_checklist(symptom_config):
    """체크리스트와 실제 환경의 정합성 검증 힌트 출력."""
    required_fields = symptom_config.get('required_db_fields', {})
    if not required_fields:
        return

    print("🔍 CHECKLIST VALIDATION HINT:")
    print("   이 장애 타입에 정의된 아래 테이블/필드의 실체 여부를 분석 중에 확인하세요:")
    for table, fields in required_fields.items():
        print(f"   - Table: {table} (Fields: {', '.join(fields)})")
    print("   (정보가 낡았을 경우 Stage 5에서 지식 베이스 업데이트가 제안됩니다.)\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: init_incident.py <symptom_description>", file=sys.stderr)
        sys.exit(1)

    symptom_text = ' '.join(sys.argv[1:])

    # 1. 환경 및 체크리스트 초기화
    providers_path = ensure_settings()
    ensure_checklists()
    
    with open(providers_path, 'r', encoding='utf-8') as f:
        providers = json.load(f)

    # 2. 증상 패턴 매핑
    symptoms = load_symptoms()
    symptom_type = detect_symptom_type(symptom_text, symptoms)
    symptom_config = symptoms.get(symptom_type, {})

    # [검증] 체크리스트 정합성 확인 (비동기적 제안)
    if symptom_type != 'unknown':
        validate_checklist(symptom_config)
    
    # 3. Incident 생성
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    date_str = now.strftime('%Y%m%d')
    incidents_dir = os.path.join(get_project_root(), 'incidents')
    incident_id = get_next_incident_id(incidents_dir, date_str)
    incident_dir = os.path.join(incidents_dir, incident_id)
    os.makedirs(incident_dir, exist_ok=True)

    # 4. state.json 작성
    state = {
        "incident_id": incident_id,
        "incident_dir": incident_dir,
        "created_at": now.isoformat(),
        "symptom_raw": symptom_text,
        "symptom_type": symptom_type,
        "affected_service": symptom_config.get('affected_service', 'unknown'),
        "status": "in_progress",
        "current_stage": 1,
        "stages_completed": [],
        "findings": {"log_patterns": [], "related_ids": [], "root_cause": None},
        "required_db_fields": symptom_config.get('required_db_fields', {}),
        "db_fields_queried": {},
        "metadata_sources": {k: v for k, v in providers.items() if k.startswith('metadata-')}
    }
    with open(os.path.join(incident_dir, 'state.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    # 5. 수사 가이드 생성
    create_guides(incident_dir, incident_id, symptom_config, providers)

    # 6. 결과 출력
    print("=" * 60)
    print(f"🚨 INCIDENT INITIALIZED: {incident_id}")
    print("=" * 60)
    print(f"📁 Dir      : {incident_dir}")
    print(f"📖 Guides   : {incident_id}/guides/ 폴더의 가이드 문서를 확인하세요.")
    print(f"🔍 Symptom  : {symptom_text}")
    print(f"📋 Type     : {symptom_type}")
    print("=" * 60)

if __name__ == '__main__':
    main()
