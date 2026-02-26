---
name: test-gate
description: "Compares Jira vs source implementation, discovers services, verifies server connectivity, and determines test baseline."
version: 4.1.0
---

# Test Gate Skill

## Principles

1. **사람이 판단한다** — Jira와 구현이 다를 때 어느 쪽이 정답인지는 Gate가 결정하지 않는다. 판단 재료만 제공한다.
2. **서버 없으면 중단** — BE API 서버에 접속할 수 없으면 테스트를 진행하지 않는다. DB만으로 대체하지 않는다.
3. **모바일은 API 시뮬레이션** — 모바일 앱은 직접 실행 불가. 소스코드에서 API 호출 흐름을 추출하여 동일 순서로 BE API를 호출한다.

---

## _shared/ Dependencies

이 스킬이 로드하는 `_shared/` 파일 목록 (이 외는 로드하지 않는다):
- `test/_shared/환경/URL.md` — 환경별 서비스 URL (서버 연결 확인에 사용)
- `test/_shared/환경/API_엔드포인트.md` — 서비스별 API 목록 (접속 검증 대상)

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| 티켓 ID | 사용자 요청 | Y | Jira 티켓 식별자 (예: PROJ-123) |
| 브랜치명 | 사용자 요청 | Y | 소스 브랜치 이름 |
| 이전 gate 결과 | 이전 실행 파일 | N | 이전 gate의 analysis_mode 재사용 |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| mode | test-run (Step 2) | NEW/REUSE/REPLAN — 시트 판정 결과 |
| baseline_mode | test-plan | match/jira/code/union — 테스트 기준 |
| analysis_mode | test-run | METADATA/HYBRID/SOURCE_DIRECT — 코드 분석 방법 |
| jira_digest | test-plan | 정규화된 Jira 요구사항 (id, content, source) |
| code_digest | test-plan | 정규화된 구현 사항 (id, content, files) |
| comparison | test-plan | matched/jira_only/code_only 비교 결과 |
| test_scope | test-plan, test-run | 테스트 대상 항목 목록 |
| affected_services | test-plan | 탐색된 서비스 (repo, type: BE_API/FE_WEB/FE_APP, branch, commits) |
| test_types | test-plan | api_test, db_verify, web_ui_capture, mobile_api_simulation, event_verify |
| server_connectivity | test-run | 각 서버 접속 결과 (성공/실패) |
| server_env_map | test-run, test-scheduler, test-provisioning | 수정 서비스별 환경 맵 (서비스명 → {env, url}) |
| reason | test-run | mode 판정 근거 |
| behavioral_contracts[] | test-run, test-plan, test-data | 메서드별 행위 계약 JSON — 조건분기→응답필드 매핑 + 데이터 요구사항 (자연어 없음) |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- Q0: 분석 모드 선택 (METADATA/HYBRID/SOURCE_DIRECT)
- Q1: 불일치 시 진행 여부 (계속/중단)
- Q2: 기준 선택 (Jira/Code/Union)
- 1.0: 메타데이터 파일 스캔 + 사용 가능한 모드 산출 + 이전 mode 로드 + Q0 실행
- 1.1: Jira 요구사항 수집
- 1.2: 소스 브랜치 구현 분석 (analysis_mode에 따라 메타데이터 또는 소스 직접)
- 1.3: 비교 리포트 (의미적 매칭)
- 1.4: 사용자 의사결정 (Q1, Q2)
- 1.5: 서비스 탐색 (티켓명 기반 브랜치/커밋 검색)
- 1.6: 테스트 범위 판단 (파일 유형별 test_types 자동 결정)
- 1.7: 서버 접속 확인 (실패 시 즉시 중단)
- 1.8: 기존 시트와 비교 (Section 0 digest 비교)
- analysis_mode 자동 판정 로직: 메타데이터 파일 존재 여부 + 이전 mode 우선순위

---

## Logic Flow

```
참조 데이터 확인 (1.0) → Jira 수집 (1.1) → 코드 분석 (1.2) → 비교 리포트 (1.3)
    → 사용자 의사결정 (1.4) → 서비스 탐색 (1.5) → 범위 판단 (1.6)
    → 서버 접속 확인 (1.7, ❌ 실패 → 중단!) → 시트 비교 (1.8) → baseline 확정
```

---

## Steps

### 1.0 참조 데이터 확인 + 분석 모드 선택

`.claude/architecture/manifest.json`을 읽어 메타데이터 상태를 확인하고, 사용자가 분석 모드를 선택한다.

**1단계: manifest.json 기반 메타데이터 상태 확인**

```
Read: .claude/architecture/manifest.json
→ manifest = 파싱된 JSON (없으면 null)
```

| manifest 상태 | 판정 |
|---------------|------|
| manifest 없음 | 메타데이터 미생성. `SOURCE_DIRECT`만 가능 |
| manifest.fullScanComplete = true | 모든 메타데이터 완비. `METADATA`, `HYBRID`, `SOURCE_DIRECT` 모두 가능 |
| manifest.fullScanComplete = false | 부분 완비. `completeness` 필드로 상세 확인 |
| manifest.incomplete 항목 존재 | 미완료 항목과 사유를 사용자에게 안내 |

**completeness 기반 모드 산출:**

| 필수 파일 | 용도 |
|-----------|------|
| services.json | 서비스 목록, 역할, 의존성 |
| api-dependencies.json | 서비스 간 API 호출 관계 |
| kafka-topics.json | Kafka 토픽, Producer/Consumer |
| data-contracts.json | 서비스 간 데이터 계약 |
| db-schemas/ | DB 스키마 정보 |

```
IF manifest == null OR 모든 completeness == false
  → SOURCE_DIRECT만 가능
ELSE IF 모든 completeness == true
  → METADATA, HYBRID, SOURCE_DIRECT 모두 가능
ELSE (일부만 true)
  → HYBRID, SOURCE_DIRECT 가능 (METADATA 불가)
  → 사용자에게 미완료 항목 안내: manifest.incomplete 내용 표시
```

> **manifest.json은 데이터 레이어의 자기 기술 파일**이다.
> 누가 메타데이터를 생성했는지(refresh-architecture, 수동 편집, CI 등)와 무관하게
> 메타데이터 상태는 오직 manifest.json만 참조한다.

**2단계: 이전 gate 결과 로드**

```
Glob: {ctx.ticket_folder}/{티켓}_gate_*.json → 타임스탬프 기준 최신 파일 로드
# IO Scope: ctx.ticket_folder 내부만 검색 (backup, 다른 티켓 폴더 접근 금지)
→ previous_gate = 이전 gate의 test_baseline 전체 (없으면 null)
→ previous_mode = previous_gate.analysis_mode (없으면 null)

저장 주체: test-run (Step 1 완료 후 자동 저장)
파일 형식: {티켓}_gate_{YYYYMMDD_HHmmss}.json
저장 위치: {ctx.ticket_folder}/
내용: test_baseline 전체 (analysis_mode, affected_services, test_types 등 포함)
```

**3단계: 분석 모드 선택 (Q0)**

사용자에게 AskUserQuestion으로 모드를 선택받는다.

```
기본값 결정:
  IF previous_mode 존재 AND previous_mode가 사용 가능한 모드에 포함
    → previous_mode를 (Recommended)로 표시
  ELSE
    → 사용 가능한 모드 중 가장 상위를 (Recommended)로 표시
    (우선순위: METADATA > HYBRID > SOURCE_DIRECT)

선택지 구성:
  - 사용 가능한 모드만 선택지로 표시
  - (Recommended) 모드를 첫 번째에 배치
  - 각 모드에 이전 사용 여부 표시 (예: "이전 실행에서 사용")
```

| 모드 | 설명 | 장점 | 단점 |
|------|------|------|------|
| METADATA | 아키텍처 메타데이터 기반 분석 | 빠름, 의존성 정확 | 메타데이터가 outdated일 수 있음 |
| HYBRID | 메타데이터 + 소스 직접 분석 | 균형 잡힌 분석 | 시간 소요 |
| SOURCE_DIRECT | 소스코드 직접 분석만 | 가장 정확 (현재 코드 기준) | 느림, 의존성 파악 한계 |

### 1.1 Jira 요구사항 수집

- Jira 티켓 조회 (MCP 또는 WebFetch)
- 요구사항을 항목별로 정규화: `{ id, content, source }`
- Jira 접근 불가 시 사용자에게 직접 입력 요청. **Jira 없이 Gate 통과 불가.**

### 1.2 소스 브랜치 구현 분석

- 브랜치 diff 또는 소스 직접 분석으로 변경사항 추출
- 분석 모드(1.0)에 따라 메타데이터 참조 또는 소스 직접 탐색
- 구현 사항을 항목별로 정규화: `{ id, content, files }`
- 분석 대상: API 엔드포인트, DTO/Response, 비즈니스 로직, DB 스키마/쿼리, Kafka 메시지


### 1.2-A: behavioral_contracts 생성 (1.2 직후 수행)

> **목적**: 코드 분석 결과를 자연어 없이 기계가 직접 사용할 수 있는 JSON으로 변환한다.
> Plan → Data → Execute 파이프라인이 이 JSON을 자연어 재해석 없이 그대로 참조한다.
>
> **입력**: 1.2에서 분석한 코드 조건분기(if/switch/filter)
> **출력**: `test_baseline.behavioral_contracts[]`

#### behavioral_contracts 스키마

```json
{
  "behavioral_contracts": [
    {
      "id": "BC-1",
      "method": "메서드명 또는 기능명",
      "source_ref": "파일경로:라인번호",
      "conditions": [
        {
          "condition_id": "C-1",  // condition_id: 부모 BC 객체 내에서만 유일. 다른 BC는 동일한 condition_id를 가질 수 있음.
          // contract_ref 형식: "{bc.id}.{condition.condition_id}" (예: "BC-1.C-1")
          "when": {
            "field": "DB 컬럼 또는 API 파라미터 (코드 변수명 아님)",
            "op": "eq | ne | gt | lt | in | not_in | is_null | is_not_null",
            "value": "값 또는 null"
          },
          "result": {
            "field": "API 응답 JSON 경로 (예: skus[*].quantity)",
            "constraint": "==0 | >0 | is_null | not_null",
            "formula": "SQL 집계 표현식 또는 null (예: sum(container_lifecycle_sku.quantity))"
          },
          "test_data": {
            "db": "MCP 도구명 (예: job | outbound | inventory | metadata)",
            "table": "테이블명",
            "where": "SQL WHERE 절 — 그대로 쿼리에 삽입 가능한 형태",
            "min_rows": 1
          }
        }
      ]
    }
  ]
}
```

#### 생성 규칙

1. 변경된 코드의 조건분기(if/switch/filter)를 모두 식별
2. 각 분기 경로(참/거짓)를 `condition` 1개로 변환
3. `when.field`: 코드 변수명이 아닌 **데이터 출처** (DB 컬럼명 또는 API 파라미터명)
4. `result.field`: API 응답 JSON의 실제 경로 — 코드 `@JsonProperty` / Response DTO에서 직접 추출
5. `result.formula`: 집계/계산이 있으면 SQL 집계 함수로 표현, 없으면 `null`
6. `test_data.where`: Data 단계 `data_requirement.where`로 그대로 복사 가능한 SQL 조건
7. 불확실한 필드는 `null` 표기 — 추측으로 자연어 채우기 금지

#### 예시 (ARG-33725 기준)

```json
{
  "id": "BC-1",
  "method": "listContainerSkuGrouped",
  "source_ref": "ContainerWebQueryApplication.java:668",
  "conditions": [
    {
      "condition_id": "C-1",
      "when": { "field": "outbound_order_state", "op": "eq", "value": "PICKING" },
      "result": {
        "field": "outboundOrderSkuGroups[*].skus[*].quantity",
        "constraint": ">0",
        "formula": "sum(container_lifecycle_sku.quantity)"
      },
      "test_data": {
        "db": "job",
        "table": "job_lifecycle_outbound_order_mapping",
        "where": "outbound_order_state = 'PICKING'",
        "min_rows": 1
      }
    },
    {
      "condition_id": "C-2",
      "when": { "field": "outbound_order_state", "op": "ne", "value": "PICKING" },
      "result": {
        "field": "outboundOrderSkuGroups[*].skus[*].quantity",
        "constraint": "==0",
        "formula": null
      },
      "test_data": {
        "db": "job",
        "table": "job_lifecycle_outbound_order_mapping",
        "where": "outbound_order_state != 'PICKING'",
        "min_rows": 1
      }
    }
  ]
}
```

### 1.3 비교 리포트

Jira 항목과 Code 항목을 **의미적(semantic)으로 매칭**하여 3가지로 분류:

| 분류 | 의미 |
|------|------|
| matched | Jira와 Code 모두 존재 |
| jira_only | Jira에 있지만 미구현 |
| code_only | 구현되었지만 Jira 미기재 |

결과를 사용자에게 표시한다.

### 1.4 사용자 의사결정

> 서비스 탐색/서버 확인 전에 사용자 의사를 먼저 확인. "중단" 선택 시 불필요한 작업을 하지 않는다.

- **불일치 없음** → `baseline_mode = "match"`, 자동 진행
- **불일치 있음** → Q1: 진행 여부, Q2: 기준 선택 (Jira / Code / Union)

### 1.5 서비스 탐색 (티켓명 기반)

티켓명으로 워크스페이스 내 모든 레포를 검색하여 관련 서비스를 식별한다.

**검색 방법**: 각 레포에서 `git branch -a --list "*{티켓명}*"` 및 `git log --grep="{티켓명}"`

**서비스 유형 분류**:

| 유형 | 대상 | 테스트 방법 |
|------|------|------------|
| BE_API | {backend-service-a}, {backend-service-b} 등 백엔드 | API 직접 호출 |
| FE_WEB | {frontend-web} 등 웹 프론트 | Playwright UI 캡쳐 |
| FE_APP | {frontend-mobile} 등 모바일 | 소스에서 API 흐름 추출 → API 직접 호출 |

결과를 사용자에게 표시하고 `ctx.affected_services`에 저장한다.

### 1.6 테스트 범위 판단

각 서비스의 코드 변경을 분석하여 테스트 유형을 자동 결정한다.

| 변경 파일 유형 | 테스트 유형 |
|---------------|------------|
| Controller/API | `api_test` (항상 true) |
| Repository/Entity/쿼리 | `db_verify` — 영향 테이블 목록도 추출 (아래 참조) |
| Vue/React/Component | `web_ui_capture` — 캡쳐 대상 화면 식별 |
| Swift/Kotlin/Dart | `mobile_api_simulation` — 아래 모바일 분석 수행 |
| Kafka/Event | `event_verify` |

**DB 검증 테이블 추출** (`Repository/Entity/쿼리` 변경 시):
```
1. test_types.db_verify = true 설정
2. test_types.db_verify_tables = extract_affected_tables(변경된 엔티티/리포지토리)
   # Entity/Repository 변경 → 관련 DB 테이블명 추출
   # 예: OutboundOrderEntity → outbound_order 테이블
   # JPA @Table 어노테이션, 리포지토리 쿼리, Native Query 등에서 추출
3. 결과를 ctx.test_types.db_verify_tables에 배열로 저장
   # 예: ["outbound_order", "outbound_order_item", "shipment"]
```

**모바일 API 시뮬레이션** (`FE_APP` 변경 시):
1. 변경된 화면(Screen/Activity)에서 호출하는 API 엔드포인트 추출
2. API 호출 순서 및 파라미터 패턴 파악
3. 화면 네비게이션 흐름에서 API 체인 생성
4. TC "채널" 컬럼에 "API (모바일 시뮬레이션)" 표기

결과를 사용자에게 표시하고 `ctx.test_types`에 저장한다.

### 1.7 서버 접속 확인 + 환경 전략 판단 (필수 Gate)

> **수정 서비스 접속 실패 → 즉시 중단. 예외 없음.**
> 환경 선택은 **수정(affected) 서비스별**로 지정한다. 수정하지 않은 서비스는 개발서버 고정.

#### 1.7.1 URL 조회

`test/_shared/환경/URL.md`에서 서비스별 URL 확인 (이미 로드됨).
URL 없으면 사용자에게 문의 → 입력값을 환경 파일에 저장 (다음 실행 시 재사용).

#### 1.7.2 수정 서비스별 환경 선택 (서비스 단위)

> 이전 로직: "로컬/개발서버" 한 번 선택 → 모든 서비스에 동일 적용
> **변경 후: 수정 서비스 각각에 대해 로컬/개발서버를 선택**

수정 서비스 목록(1.5 affected_services 중 BE_API 유형)을 사용자에게 표시하고,
**각 서비스별로** 환경을 지정받는다.

```
AskUserQuestion (multiSelect: false, 서비스별 반복 또는 일괄 테이블):

수정 서비스 환경 선택:
┌─────────────────┬──────────────────────────────────────┐
│ 서비스           │ 환경                                  │
├─────────────────┼──────────────────────────────────────┤
│ wms-outbound    │ ○ 로컬 (localhost:8080)               │
│                 │ ● 개발서버 (wms-outbound-api.argoport.co) │
├─────────────────┼──────────────────────────────────────┤
│ wms-job         │ ● 로컬 (localhost:8083)               │
│                 │ ○ 개발서버 (wms-job-api.argoport.co)    │
└─────────────────┴──────────────────────────────────────┘
수정하지 않은 의존 서비스는 자동으로 개발서버를 사용합니다.
```

**구현 방법**: AskUserQuestion의 multiSelect를 활용하거나, 서비스가 1개이면 단일 질문,
2개 이상이면 서비스별 순차 질문 또는 "전체 개발서버 / 전체 로컬 / 개별 지정" 선택지를 먼저 제공.

```
IF affected BE_API 서비스 == 1개
  → 해당 서비스에 대해 로컬/개발서버 선택 (단일 질문)
ELSE IF affected BE_API 서비스 >= 2개
  → 먼저 일괄 질문: "전체 개발서버(Recommended) / 전체 로컬 / 개별 지정"
  → "개별 지정" 선택 시 서비스별 순차 질문
```

결과를 `ctx.server_env_map`에 저장:

```json
{
  "wms-outbound": { "env": "dev", "url": "https://wms-outbound-api.argoport.co" },
  "wms-job": { "env": "local", "url": "http://localhost:8083" }
}
```

#### 1.7.3 Health Check

각 수정 서비스에 대해 **지정된 환경의 URL**로 접속 확인:
- `ctx.server_env_map`에서 URL 조회
- HTTP 요청 (actuator/health 또는 HEAD)
- `FE_APP` 서비스는 모바일 서버가 아닌 **BE API 서버** 접속 확인
- **접속 실패 → 즉시 중단**

#### 1.7.4 로컬 서비스의 의존 서비스 확인

`ctx.server_env_map`에서 `env: "local"`인 서비스가 있는 경우에만 수행:

1. `.claude/architecture/api-dependencies.json`에서 로컬 서비스의 의존 서비스 추출
2. 의존 서비스 중 `ctx.server_env_map`에 없는 것(= 수정하지 않은 서비스)은 **개발서버 자동 할당**
3. 의존 서비스가 로컬 서비스를 호출하는 경우 → Hybrid 환경 안내

**Hybrid 감지 시 사용자 안내** (로컬 서비스가 1개 이상일 때만):

```
⚠️ Hybrid 환경 감지:
- 로컬: wms-job (localhost:8083) ✅
- 개발서버: wms-outbound (wms-outbound-api.argoport.co) ✅
- 개발서버(의존): wms-inventory (wms-inventory-api.argoport.co) — 자동

로컬 서비스(wms-job)가 의존하는 서비스(wms-outbound, wms-inventory)는 개발서버를 바라봐야 합니다.
application-local.yml의 Feign 설정을 확인해주세요.
```

선택지:
1. **확인 완료, 진행** — 로컬 서비스가 개발서버 의존 서비스를 바라보도록 설정 완료
2. **의존 서비스도 로컬 기동** — 사용자가 의존 서비스를 로컬에서 기동 후 "완료" 응답
3. **현재 상태로 진행** — 의존 서비스 관련 TC는 BLOCKED 처리

#### 1.7.5 DB 접속 확인

`db_verify = true`인 경우 MCP postgres tool로 `SELECT 1` 실행.

#### ctx.server_env_map 활용 (하위 스킬)

`ctx.server_env_map`은 이후 단계(test-scheduler, test-provisioning)에서 API 호출 시
**서비스별로 올바른 URL**을 선택하는 데 사용된다.

```
API 호출 시:
  target_service = API의 대상 서비스 판별
  url = ctx.server_env_map[target_service].url
  → 해당 URL로 요청
```

### 1.8 기존 시트와 비교 (Digest + 영향도 검증)

기존 시트가 있는 경우, **2단계 비교**를 수행한다.

**1단계: Digest 비교 (기존 로직)**
- 검색 범위: ctx.ticket_folder 내부만 (IO Scope Enforcement)
- Glob: {ctx.ticket_folder}/{티켓}_테스트시트_v*.md → 최신 버전 선택
- 최신 테스트시트의 Section 0.1~0.3 (jira_digest, code_digest, comparison)과 현재 값을 비교
- 다름 → `REPLAN` (reason: "요구사항/구현 변경 감지")
- 시트 없음 → `NEW`
- 동일 → 2단계로 진행

**2단계: 영향도 입력값 비교 (신규)**

Digest가 동일해도 영향도 분석의 **입력**이 변경되었을 수 있다.

| 비교 항목 | 비교 방법 | 변경 시 |
|-----------|----------|---------|
| affected_services | Section 0.4의 서비스 목록 vs 현재 1.5 결과 (서비스 추가/제거/유형 변경) | REPLAN |
| test_types | Section 0.5의 테스트 유형 vs 현재 1.6 결과 (플래그 변경) | REPLAN |
| 아키텍처 메타데이터 | `.claude/architecture/manifest.json`의 `lastUpdated` vs 시트 생성일 | REPLAN |

> **주의**: 아키텍처 메타데이터 비교는 파일 시스템 수정일(mtime)이 아닌
> `manifest.json`의 `lastUpdated` 필드를 기준으로 한다.
> 이는 git checkout 등으로 mtime이 변경되어도 실제 내용 변경 없이 REPLAN이 트리거되는 것을 방지한다.

**판정**:
- 1단계 + 2단계 모두 동일 → `REUSE`
- 1단계 동일 + 2단계 다름 → `REPLAN` (reason: "영향도 입력 변경: {변경 항목}")
- 1단계 다름 → `REPLAN` (reason: "요구사항/구현 변경 감지")
- 시트 없음 → `NEW`

```
예시 시나리오:
  jira_digest 동일 + code_digest 동일 (1단계 PASS)
  BUT 새로운 서비스 {service-c}가 affected_services에 추가됨 (2단계 FAIL)
  → REPLAN (reason: "영향도 입력 변경: affected_services에 {service-c} 추가")
```

---

## Output (test_baseline)

Gate 통과 시 다음 필드를 포함하는 `test_baseline` 객체를 생성하여 다음 Step에 전달:

| 필드 | 설명 |
|------|------|
| ticket, branch | 티켓/브랜치 식별자 |
| mode | NEW / REUSE / REPLAN |
| baseline_mode | match / jira / code / union |
| analysis_mode | METADATA / HYBRID / SOURCE_DIRECT |
| jira_digest[] | 정규화된 Jira 요구사항 |
| code_digest[] | 정규화된 구현 사항 |
| comparison | matched, jira_only, code_only |
| test_scope[] | 테스트 대상 항목 목록 |
| affected_services[] | 탐색된 서비스 (repo, type, branch, commits) |
| test_types | api_test, db_verify, web_ui_capture, mobile_api_simulation, event_verify |
| server_connectivity | 각 서버 접속 결과 |
| behavioral_contracts[] | 메서드별 행위 계약: 코드 조건분기 → 응답 결과 매핑 + Data 단계용 SQL WHERE. test-run이 ctx.behavioral_contracts로 저장 후 Plan에 전달 |
| server_env_map | 수정 서비스별 환경 맵 (서비스명 → env, url) |
| reason | 베이스라인 결정 사유 (REUSE/REPLAN/NEW 판정 근거 요약) |

---

## Edge Cases

| 상황 | 처리 |
|------|------|
| Jira 접근 불가 | 사용자에게 내용 직접 입력 요청. Jira 없이 Gate 통과 불가 |
| 브랜치 없음 / git 미사용 | 사용자에게 변경 파일/내용 직접 입력 또는 소스 디렉토리 직접 분석 |
| 첫 테스트 (시트 없음) | mode = NEW, test-plan이 시트 생성 |
| Jira 비어있고 코드 변경 없음 | Gate 통과 불가. 사용자에게 Jira/브랜치 확인 요청 |
| BE API 서버 접속 실패 | **즉시 중단**. DB만으로 대체 불가 |
| FE_WEB만 접속 실패 | 사용자에게 선택: API만 진행 or 전체 중단 |
| 티켓 관련 레포 없음 | 사용자에게 브랜치명/레포 직접 지정 요청 |
| 모바일 소스 접근 불가 | 사용자에게 선택: API 시퀀스 직접 제공 / BE만 테스트 / 중단 |
