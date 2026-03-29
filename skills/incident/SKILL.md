---
name: incident
description: 장애(Incident) 분석을 위한 단계별(1-5단계) 워크플로우와 상태 관리 기능을 제공합니다.
user-invocable: true
disable-model-invocation: false
allowed-tools:
  - Bash, Bash(git:*)
  - Glob
  - Read
  - Write
  - Edit
  - Grep
  - WebSearch
---

# 🚨 장애 분석 (Incident Analysis)

이 스킬은 장애 발생 시 체계적인 분석을 돕기 위해 5단계(Stage)로 구성된 워크플로우를 제공합니다. 컨텍스트 손실을 방지하기 위해 `state.json`에 분석 상태를 유지하며, 각 단계의 조사 결과(로그, 쿼리, 코드 분석 등)를 개별 마크다운 파일로 저장합니다.

## 🛠️ 주요 워크플로우

### 1. 장애 초기화 및 가이드 생성 (Self-Initialization)
별도의 사전 설정 없이 증상을 입력하여 분석 환경을 즉시 구축합니다.
- **명령**: `python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/init_incident.py "증상 설명 (예: 출고대기 정체 발생)"`
- **결과**:
  - `settings/providers.json` 자동 생성 (없을 경우 기본값 적용)
  - **Interactive Setup Prompt**: 설정이 미비하거나 플레이스홀더(`yourcompany.com`) 상태인 경우, 터미널에 `setup_providers.py`를 통한 설정 가이드가 출력됩니다. (다중 DB 등록 및 선택적 Provider 스킵 지원)
  - `incidents/INC-YYYYMMDD-XXX/` 폴더 및 `state.json` 생성
  - `incidents/INC-YYYYMMDD-XXX/guides/` 폴더 내 도구별 수사 가이드 자동 생성
- **참고**: 생성된 가이드 문서를 먼저 읽고 조사를 시작하십시오. 다중 DB 등록을 원할 경우 `setup_providers.py --db "name:type:env"`를 여러 번 호출하세요.

### 2. 단계별 분석 (Execution)
분석은 총 5단계로 진행되며, 각 단계 완료 후 결과를 저장합니다.

1. **Stage 1: Symptom Collection (현상 수집)** → `stage1_collection.md`
2. **Stage 2: Log Analysis (로그 분석 - Kibana)** → `stage2_kibana.md`
3. **Stage 3: MCP Discovery (MCP 도구 데이터 조회)** → `stage3_mcp.md`
4. **Stage 4: DB Query (DB 쿼리 및 필드 커버리지 검증)** → `stage4_db.md`
5. **Stage 5: Root Cause & Resolution (원인 분석 및 해결책)** → `stage5_rootcause.md`

#### Stage 2 실행 절차 (Log Analysis - Kibana)

`guides/` 폴더에 생성된 Kibana 가이드를 참고하여 다음 순서로 수행합니다:

1. Kibana/Elasticsearch에 접속하여 `providers.json`의 `log.config.url` 주소를 사용합니다.
2. 장애 발생 시간대의 에러 로그, 스택트레이스, 이상 패턴을 조회합니다.
3. 관련 서비스(`affected_service`)를 기준으로 로그를 필터링합니다.
4. 분석 결과를 Stage 2로 저장합니다:
   ```
   python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/save_stage.py \
     --id <INC-ID> --stage 2 --content "Kibana 분석 결과..."
   ```

#### Stage 4 실행 절차 (DB Query)

Stage 4 시작 전 필수 필드를 확인하고, 완료 후 커버리지를 검증합니다:

```
# Stage 4 시작 전 — 필수 조회 필드 확인
python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/check_coverage.py --id <INC-ID> --pre

# Stage 4 완료 후 — 커버리지 검증 (누락 시 exit 1)
python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/check_coverage.py --id <INC-ID> --post
```

- DB 필드 기록: `save_stage.py --stage 4 --fields "table.field1,table.field2"`

#### Stage 5 실행 절차 (Root Cause & Resolution)

원인 분석 완료 후 `--root-cause` 옵션으로 핵심 원인을 state.json에 기록합니다:

```
python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/save_stage.py \
  --id <INC-ID> --stage 5 --content "원인 분석 및 해결책..." \
  --root-cause "핵심 원인 한 줄 요약"
```

#### 전체 결과 저장 형식

- **결과 저장**: `python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/save_stage.py --id <INC-ID> --stage <1-5/report>`
  - `--content` 옵션으로 내용을 전달합니다 (stdin은 파이프 연결 시에만 사용).

> **$CLAUDE_PROJECT_DIR 설정 방법**: 이 환경변수는 incident 스킬이 설치된 스킬 저장소의 루트 경로입니다.
> 실행 전 `export CLAUDE_PROJECT_DIR=/path/to/skills/repo` 로 설정하거나, 설정되지 않은 경우 스크립트가 자동으로 스크립트 위치 기준 3단계 상위 디렉토리를 루트로 사용합니다.

### 3. 상태 복원 및 지식 관리 (Restore & Knowledge Loop)
분석 상태를 복원하거나, 분석 결과를 바탕으로 지식 베이스를 개선합니다.
- **상태 복원**: `python3 $CLAUDE_PROJECT_DIR/skills/incident/scripts/load_state.py --id <INC-ID> [--stages]`
- **지식 피드백 (Feedback Loop)**:
  - **검증**: `init` 실행 시 `symptoms.json`의 필드가 실제 환경과 맞는지 자동 점검하여 힌트를 제공합니다.
  - **제안**: `save_stage --stage report` 실행 시, 이번 장애 조사에서 새로 발견된 필드들을 `report.md` 하단에 개선 사항으로 제안합니다.
  - **반영**: 제안된 내용을 검토 후 `checklists/symptoms.json`에 수동으로 반영하여 스킬의 지능을 높입니다.

---

## 🔍 분석 가이드 (Discovery Guide)

- **증상 매핑**: `init_incident.py`는 `checklists/symptoms.json`을 참조하여 해당 증상에서 반드시 확인해야 할 DB 필드나 알려진 원인을 자동으로 안내합니다.
- **가이드 문서 활용**: `guides/` 폴더에 생성된 각 도구별(Kibana, SQL 등) Markdown 파일을 열람하여 구체적인 조사 쿼리와 대상 환경을 확인하십시오.
- **DB 필수 필드(Required Fields)**: Stage 4에서는 `state.json`에 정의된 필수 필드들을 모두 조회했는지 교차 검증합니다.

---

> [!TIP]
> 장애 대응 중에는 `load_state.py`를 정기적으로 실행하여 현재 누락된 필수 조회 항목이 없는지 확인하십시오.
