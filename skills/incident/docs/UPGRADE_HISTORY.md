# UPGRADE_HISTORY (incident)

## [2.3.5] - 2026-03-19

### 🚀 Added
- 범용 장애 분석(Incident Analysis) 스킬 추가
- 5단계(Stage) 기반 분석 워크플로우 도입
- `state.json`을 통한 분석 상태 영속성 관리 스크립트 (`init_incident.py`, `save_stage.py`, `load_state.py`) 추가
- HITL 방식의 Provider 설정 도구 (`setup_providers.py`) 추가
- 증상별 필수 DB 필드 및 원인 매핑 (`checklists/symptoms.json`) 추가
- Kibana, S3, SQL 등 다양한 Provider 인터페이스 가이드 문서 추가

### 🔧 Changed
- `init_incident.py` 고도화: `settings/` 폴더 자동 생성 및 가이드 문서 동적 생성 기능 추가 (Self-Initialization).
- `load_provider.py` 및 `providers/` 폴더 제거: 가이드 템플릿을 스크립트 내부로 통합하여 범용성 개선.
- `_settings` 폴더명을 `settings`로 변경하여 직관성 개선.

## [v1.2.0] - 2026-03-20

### 🚀 Added
- **다중 DB 지원 (Multi-DB Registration)**: `setup_providers.py`에서 `--db "name:type:env"`를 통해 여러 DB 동시 등록 기능 추가.
- **선택적 Provider 스킵**: 로그(Kibana)나 코드 분석 도구가 없는 환경에서도 장애 분석을 시작할 수 있도록 `skip` 지원.
- **대화형 설정 마법사 고도화**: 설정 미비 시 CLI 옵션과 예시를 포함한 가이드 메시지 출력.

### 🔧 Changed
- **정합성 및 견고함**: `init_incident.py`에서 가이드 생성 시 템플릿 키 누락으로 인한 `KeyError` 방지 (기본값 제공 및 예외 처리 강화).
- **범용 플레이스홀더**: 모든 설정 템플릿의 특정 도메인 정보를 `yourcompany.com`으로 교체.
