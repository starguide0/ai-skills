---
name: test-plan
description: |
  Test plan creation skill. Triggers on: "테스트 계획 작성", "test plan", "테스트 설계", "test design".
  Generates test sheets with impact analysis, test scenarios, and baseline storage.
  Parameters: Feature/Ticket name (required), Planning scope (optional, default="전체").
version: 2.3.0
---

# Test Plan Skill

## Purpose

사용자가 테스트 계획 작성을 요청하면 자동으로 활성화되어:

- Jira 티켓 분석
- 테스트 범위 도출
- 영향도 분석
- 테스트 시나리오/케이스 생성

을 수행합니다.

---

## _shared/ Dependencies

이 스킬이 로드하는 `_shared/` 파일 목록 (이 외는 로드하지 않는다):
- `테스트_주의사항.md` — DB 스키마 오류, 반복 실수 방지 (가장 먼저 로드)
- `도메인/{관련_도메인}.md` — 테스트 대상 도메인 비즈니스 지식

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| ctx.test_baseline.jira_digest | test-gate | Y | 정규화된 Jira 요구사항 (test-run 경유 시) |
| ctx.test_baseline.code_digest | test-gate | Y | 정규화된 구현 사항 (test-run 경유 시) |
| ctx.test_baseline.comparison | test-gate | Y | 비교 결과 (matched, jira_only, code_only) |
| ctx.test_baseline.baseline_mode | test-gate | Y | 테스트 기준 (match/jira/code/union) |
| ctx.test_baseline.test_scope | test-gate | Y | 테스트 범위 항목 목록 |
| ctx.test_baseline.affected_services | test-gate | Y | 탐색된 서비스 목록 (repo, type, branch, commits) |
| ctx.test_baseline.test_types | test-gate | Y | api_test, db_verify, web_ui_capture, mobile_api_simulation, event_verify |
| ctx.test_baseline.behavioral_contracts | test-gate | N | 행위 계약 목록 (Step 4.3-C에서 tc_spec 생성 시 사용. 없으면 Step 4.3-A에서 직접 생성) |
| ctx.previous_sheet | test-run (Step 2) | N | REPLAN 시 기존 시트 경로 (증분 수정 참조용). NEW 시 없음. |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| 테스트시트 파일 | test-data, test-scheduler, test-reporter | {ticket}_테스트시트_v{N}_{date}.md |
| ctx.sheet | test-data, test-scheduler, test-reporter | 테스트시트 절대 경로 |
| ctx.sheet_version | test-data, test-run | v{N} — 메이저 버전 (TC 변경 시 증가) |
| Section 0: Test Baseline | 다음 test-gate (1.8) | jira_digest + code_digest + comparison + affected_services + test_types 저장 (변경 감지용) |
| Section 1: 변경 요약 | test-reporter | Jira 근거 + 핵심 변경 사항 |
| Section 2: 영향도 분석 | test-reporter | 4-Layer (Logic/API/DB/Event) + 사이드이펙트 |
| Section 3: 시나리오 목록 | test-scheduler | 시나리오 의존성 추출 |
| Section 4: 시나리오 상세 | test-data, test-run | TC별 사전조건, **행위적 조건**, 데이터 요구사항, 기대결과, 선정 이유 |
| {ticket}_tc_spec.json | test-data, test-scheduler | TC별 행위 조건·기대값·데이터 요구사항 구조화 JSON (자연어 없음) |
| ctx.tc_spec | test-data, test-scheduler, **test-run** | tc_spec.json 절대 경로 |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- Section 0~4 구조 및 템플릿 형식
- 영향도 분석 4-Layer 로직 (Logic/API/DB Schema/Event)
- TC 생성 로직 (시나리오 → 케이스 도출)
- 선정 이유 작성 규칙 (영향도 분석 → TC 필요 근거)
- 데이터 요구사항 정규화 (entity, conditions, requires_job)
- Jira 요구사항 원문 인용 형식
- 테스트시트 파일명 versioning 규칙 (major 버전만)

---

## Trigger Examples

### 한글

- "PROJ-123 테스트 계획 작성해줘"
- "{FEATURE-NAME} 테스트 계획 만들어줘"
- "{TICKET-ID} 테스트 설계해줘"
- "{기능명} 테스트 계획"

### 영어

- "Create test plan for PROJ-123"
- "Plan tests for {FEATURE-NAME}"
- "Design test cases for {TICKET-ID}"

---

## Parameter Extraction

```
Input: "PROJ-123 테스트 계획 작성해줘"

추출:
- 티켓: "PROJ-123"
- 작업: "테스트 계획"
- 범위: "전체" (기본값)
- 영향도 분석: true (기본값)
```

---

## Execution Steps

### Step 0: Gate 데이터 수신 (test-run에서 전달)

test-run의 Step 1(Gate)에서 전달받은 `test_baseline`을 사용합니다.
**Jira를 재조회하지 않습니다.**

> **ctx 복원 (Read-Through Fallback)**:
> ctx.test_baseline 없으면 → Glob `{ctx.ticket_folder}/{ticket}_gate_*.json` → 타임스탬프 최신 파일 Read → JSON parse → ctx.test_baseline 복원.
> 파일도 없으면 → 단독 호출 모드로 전환 (Step 1 자체 Jira 조회 실행).

```
수신 데이터:
- ctx.test_baseline.jira_digest        → Jira 요구사항 (이미 정규화됨)
- ctx.test_baseline.code_digest        → 소스 구현 사항 (이미 분석됨)
- ctx.test_baseline.comparison         → 비교 결과 (matched, jira_only, code_only)
- ctx.test_baseline.baseline_mode      → 테스트 기준 (jira / code / union / match)
- ctx.test_baseline.test_scope         → 테스트 범위 항목 목록
- ctx.test_baseline.affected_services  → 탐색된 서비스 목록 (repo, type: BE_API/FE_WEB/FE_APP)
- ctx.test_baseline.test_types         → 테스트 유형 (api_test, db_verify, web_ui_capture, mobile_api_simulation, event_verify)

TC 작성 시 affected_services와 test_types 활용:
- BE_API 서비스 → 채널: "API"
- FE_WEB 서비스 → 채널: "WEB" (UI 캡쳐 대상)
- FE_APP 서비스 → 채널: "API (모바일 시뮬레이션)" (Gate에서 추출한 API 시퀀스 사용)
- db_verify = true → TC에 "기대 결과 (DB)" 컬럼 필수
- 각 TC에 "선정 이유" 작성 — 아래 도출 공식 준수:
    선정 사유 = {참조 체인의 어떤 변경점} → {어떤 위험/동작을 검증}
    예: "v3 API 신규 추가(C1) → 주문별 그룹화 응답 구조가 정확한지 검증"
    예: "Waterfall 로직 제거(C3) → overflow 시에도 전체 주문 반환되는지 검증"
    ❌ 금지: "구체적 증거 확인" 같은 모호한 사유. 반드시 변경점↔검증 대상을 연결.

단독 호출 시 (test-run 경유 없이):
- test_baseline이 없으면 자체적으로 Jira 조회 + 코드 분석 수행
- 이 경우 기존 Step 1(Jira 조회) 로직을 실행
```

### Step 1: 티켓 정보 수집 (필수 — Jira가 소스 오브 트루스)

> ℹ️ test-run 경유 시 이 Step은 스킵됩니다 (Gate에서 이미 Jira를 조회했으므로).
> 단독 호출 시에만 실행됩니다.

> **Jira 티켓의 요구사항이 테스트시트의 기대결과를 결정한다.**
> 코드 분석은 "어떻게 구현되었는가"를 파악하는 데 사용하고,
> "어떻게 동작해야 하는가"는 반드시 Jira 티켓에서 가져온다.

```
1. Jira 티켓 조회 (MCP: mcp__atlassian__getJiraIssue)
   - issueIdOrKey: "{티켓}"
   - 추출: summary, description, acceptance criteria, comments, sub-tasks

2. 요구사항 핵심 정리
   - 기능 목적: {무엇을 하는 기능인가}
   - 기대 동작: {어떻게 동작해야 하는가} ← 이것이 TC 기대결과의 근거
   - 변경 범위: {어떤 서비스/API가 변경되는가}
   - 엣지 케이스: {Jira에 언급된 특수 상황}

3. Jira 접근 불가 시:
   - 사용자에게 Jira 내용 공유 요청
   - 또는 WebFetch로 Jira 페이지 접근 시도
   - 티켓 정보 없이 코드만으로 테스트시트를 작성하지 않는다
```

### ⭐ 기대결과 도출 원칙

```
✅ 올바른 흐름:
   Jira 요구사항 → 기대결과 도출 → 코드 분석으로 검증 방법 결정

❌ 잘못된 흐름:
   코드 분석 → 코드 동작을 기대결과로 설정 → Jira 무시
   (이 경우 코드의 버그도 "정상"으로 판정하게 됨)
```

테스트시트에 Jira 요구사항 원문을 인용한다:

```markdown
### 1.3 핵심 변경 사항 (Jira 근거)

> **Jira 원문**: "{Jira description에서 해당 부분 발췌}"
> **출처**: [{티켓}](https://techtaka.atlassian.net/browse/{티켓})

위 요구사항을 기반으로 다음 기대결과를 도출:

1. ...
2. ...
```

### Step 2: 사전 리소스 로드

> ℹ️ **test-run 경유 시**: Step 0에서 리소스가 이미 로드되었으므로 이 Step의 [1단계]~[3단계]는 스킵합니다.
> **단독 호출 시**: 아래 전체 리소스를 순서대로 로드합니다.

```
테스트 계획 작성 전 반드시 다음 파일을 순서대로 읽는다:

[1단계] 공통 환경 + 도메인 지식 (test/_shared/):
> 로드 대상은 상단의 ## _shared/ Dependencies 선언을 따른다.
0. test/_shared/테스트_주의사항.md — 반복 실수 방지 (가장 먼저!)
1. test/_shared/도메인/{관련 도메인}.md — 테스트 대상 도메인 파일

[2단계] 템플릿 + 버전 규칙 (test/templates/):
5. test/templates/README.md — 파일 명명 규칙, 버전 결정 로직
6. test/templates/테스트시트_템플릿.md — 테스트시트 표준 형식

[3단계] 시스템 아키텍처 (선택 사항 — test-gate에서 지정 시 로드):
7. {impact_references} — test-gate에서 선택한 디렉토리 혹은 파일들
   (예: .claude/architecture/services.json, api-dependencies.json 등)

[4단계] DB 스키마 (필수):
8. 도메인 관련 schema.prisma 혹은 .sql 파일
9. .claude/architecture/data-contracts.json (존재 시)
```

### Step 3: 테스트 폴더 생성

```
# 폴더 생성: ctx.ticket_folder가 이미 설정된 경우 기존 폴더 사용 (1 Ticket = 1 Folder 원칙)
IF ctx.ticket_folder 존재:
  → ctx.ticket_folder 사용 (새 폴더 생성 금지)
ELSE (standalone 실행):
  → mkdir -p $CLAUDE_PROJECT_DIR/test/{티켓}_{기능명}/
  → ctx.ticket_folder = "test/{티켓}_{기능명}"
```

### Step 4: 테스트 계획 생성

```
0. 기존 시트 로드 (REPLAN 시)
   IF ctx.previous_sheet 존재:
     → 기존 시트를 읽어 현재 TC 목록 파악
     → 이후 단계에서 code diff 기반으로 영향받는 TC만 추가/수정/삭제
     → 영향 없는 TC는 그대로 유지
   ELSE (NEW):
     → 처음부터 작성

1. 변경 사항 분석 (코드 diff, 요구사항)

2. 영향도 분석 (참조 체인 추적)

   변경점을 기준으로 참조하는 모든 곳까지 체인을 따라가며 영향 범위를 확정한다.

   **2-1. 변경점 식별**
   코드 diff에서 변경된 항목을 구체적으로 식별:
   - 변경된 메서드/함수
   - 변경된 DB 컬럼/테이블
   - 변경된 API 응답 필드
   - 변경된 이벤트 메시지 필드

   **2-2. 참조 체인 추적 (핵심)**
   각 변경점에서 "이것을 참조하는 곳"을 끝까지 추적:

   ```
   변경점 (예: DB 컬럼 추가/수정)
     → 이 컬럼을 읽는 Repository/Query
       → 이 Repository를 호출하는 Service
         → 이 Service를 호출하는 API Controller
           → 이 API를 호출하는 화면 (WEB/APP)
           → 이 API를 호출하는 다른 서비스 (internal-api)
     → 이 컬럼을 포함하는 Kafka 메시지
       → 이 메시지를 소비하는 서비스
   ```

   추적 방향:
   - **상향 (DB→API→화면)**: DB 변경 시 해당 컬럼이 어디까지 노출되는지
   - **하향 (화면→API→DB)**: API 파라미터 변경 시 DB에 어떤 영향인지
   - **횡단 (서비스→서비스)**: 서비스 간 API 호출, Kafka 이벤트 전파

   **2-3. 영향 범위 확정**
   추적된 참조 체인에서 TC가 필요한 검증 지점을 결정:
   - 화면에서 사용 중인 API → 사용성 검증 TC
   - 다른 서비스가 호출하는 API → 연동 검증 TC
   - DB 변경이 다른 쿼리에 영향 → 사이드이펙트 TC
   - 이벤트 필드 변경이 소비자에 영향 → 이벤트 검증 TC

   **2-4. 데이터 시나리오 도출**
   변경된 코드의 분기 조건(if/filter/비교)에서 서로 다른 실행 경로를 만드는
   데이터 조합을 추론한다. 데이터가 현재 DB에 있는지 여부와 무관하게 도출.

   ```
   예) Waterfall 코드의 분기:
     - remain > batchPlanQty → 전량 할당
     - remain < batchPlanQty → 부분 감소 ← TC 필요
     - remain == 0 → 주문 제외 ← TC 필요
     - Job 매핑 주문 < 전체 주문 → 필터링 효과 ← TC 필요
     → 이 조합들의 교차 시나리오도 TC 후보
   ```

3. 테스트 시나리오 도출
   - 참조 체인에서 확정된 검증 지점별로 시나리오 생성
   - 데이터 시나리오에서 도출된 분기 조합별로 TC 생성
   - TC는 데이터 존재 여부와 무관하게 생성 (없으면 NOT_FOUND → Provisioning 후보)
   - REPLAN 시: 기존 시나리오/TC 중 영향받는 것만 식별

4. 테스트 케이스 작성
   - REPLAN 시: 영향받는 TC만 수정/추가/삭제, 나머지 유지
   - NEW 시: 전체 신규 작성
   - 각 TC에 **선정 이유** 명시 (어떤 변경/위험을 검증하는가)
   - 각 TC에 데이터 요구사항 명시 (필요한 엔티티/상태/수량)
   - TC의 사전 조건이 곧 데이터 검색 조건이 됨
   - 각 TC에 **STIMULUS 명세** 필수 (아래 4-A 참조)

5. 파일 생성: {티켓}_테스트시트_v{N}_{날짜}.md
   - **중요**: 파일 상단에 `Requirement Digest` 섹션을 반드시 포함할 것.
   - 이 섹션은 추후 `test-gate`가 변경 감지(Semantic Diff)를 수행하는 기준점이 됨.
```

### ⭐ Step 4-A: TC 필수 구조 — STIMULUS 명세 (필수 — 예외 없음)

> **원칙**: 모든 코드 변경 검증 TC는 반드시 BEFORE → STIMULUS → AFTER 3단계 구조를 갖는다.
> STIMULUS가 없는 TC는 코드 변경을 검증할 수 없다.
> DB 조회만으로 "PASS"를 판정하는 것은 테스트가 아니라 관찰이다.

#### TC 유형 분류

| TC 유형 | STIMULUS 필수 | 용도 | TC 제목 규칙 |
|---------|-------------|------|-------------|
| **ACTIVE** | ✅ 필수 | 코드 변경 검증, 기능 검증, E2E 흐름 | 기본 (접두사 없음) |
| **OBSERVATION** | ❌ 생략 가능 | 기존 데이터 패턴 확인, 통계 검증 | `[관찰]` 접두사 필수 |

**제약**:
- 코드 변경을 직접 검증하는 TC는 반드시 **ACTIVE** 유형이어야 한다
- **OBSERVATION** TC만으로 코드 변경 검증을 완료할 수 없다
- 시나리오당 최소 1개 ACTIVE TC 필수

> ⚠️ **validate_test_sheet.py Hook — ACTIVE 마커 탐지 방식**
> Hook은 `| TC-xxx | ... | ACTIVE |` 패턴의 마커 테이블을 탐색함.
> **이 마커 테이블이 없으면 파일 내 모든 TC를 ACTIVE로 간주하여 전체에 STIMULUS 블록 요구.**
> OBSERVATION TC가 있는 경우, 시나리오 테이블에 반드시 `| ACTIVE |` / `| OBSERVATION |` 컬럼을 포함할 것.

#### ACTIVE TC 필수 구조 (테스트시트에 명시)

각 ACTIVE TC의 "테스트 스텝" 컬럼에 반드시 다음 3단계를 **구체적으로** 기술한다:

```
━━━ BEFORE (사전 상태 기록) ━━━
  - 대상: {테이블명.컬럼} 또는 {화면 요소}
  - 쿼리/방법: SELECT ... WHERE ... (구체적 쿼리)

━━━ STIMULUS (자극 — 핵심) ━━━
  - Method: {POST|PUT|DELETE}
  - Endpoint: {서비스 Base URL + path}
  - Headers: Authorization: Bearer {token}
  - Body: { 구체적 JSON 또는 필수 필드 명시 }
  - Expected Response: {HTTP status + 핵심 응답 필드}

  ❌ 금지: "웹에서 확인", "화면에서 조작", "API로 처리" 같은 모호한 기술
  ✅ 필수: 실행 가능한 수준의 구체적 API 명세

  UI 조작이 필요한 경우:
  - Playwright 액션으로 변환하여 기술 (click, fill, navigate 등)
  - 또는 UI 뒤의 실제 API를 추적하여 API 명세로 기술

━━━ AFTER (사후 검증) ━━━
  - 대상: BEFORE과 동일한 대상
  - 쿼리/방법: BEFORE과 동일한 쿼리 재실행
  - 비교 기준: {어떤 변화가 있어야/없어야 하는지}
```

#### STIMULUS 명세 작성 규칙

```
1. API 엔드포인트 추적 (필수):
   - 소스코드에서 해당 기능의 Controller/API 엔드포인트를 찾는다
   - test/_shared/환경/API_엔드포인트.md에서 서비스별 Base URL을 확인한다
   - 둘을 결합하여 완전한 URL을 구성한다

2. Request Body 구성 (필수):
   - Controller의 @RequestBody DTO 구조를 확인한다
   - 필수 필드와 테스트에 필요한 값을 명시한다
   - 동적 값(ID 등)은 {data.eo_id} 같은 플레이스홀더로 표기한다

3. 모바일 API 시뮬레이션:
   - 모바일 소스코드에서 API 호출 순서를 추출한다
   - 각 API를 순서대로 STIMULUS로 나열한다
   - depends_on으로 선행 API 응답에서 파라미터 추출을 명시한다

4. Kafka 이벤트 유발이 필요한 경우:
   - Kafka에 직접 발행하지 않는다
   - 이벤트를 발행하는 API를 찾아서 그 API를 STIMULUS로 사용한다
   - 예: COMPLETE 이벤트 유발 → 출고 완료 API 호출
```

#### 예시: WO-21 TC-1의 올바른 STIMULUS 명세

```
━━━ BEFORE ━━━
  SELECT state, event, cancel_state
  FROM external_outbound_order
  WHERE external_outbound_order_id = '{data.eo_id}'
  → state=REJECTED 확인

━━━ STIMULUS ━━━
  Method: POST
  Endpoint: https://oms-api.argoport.co/order/event/cancel
  Body: {
    "orderId": "{data.oms_order_id}",
    "cancelType": "FULL",
    "reason": "테스트 취소"
  }
  Expected: HTTP 200

━━━ AFTER ━━━
  동일 쿼리 재실행 → state=REJECTED 유지 확인 (CANCEL 무시됨)
```

### Step 4.1: 검증 데이터 소스 추적 (필수 — 추측 금지)

> **원칙**: TC의 기대결과에 "X가 발생/미발생"을 포함할 때, **X가 실제로 어디에 기록되는지 코드를 추적한 후** 검증 방법을 설계한다.
> 컬럼명이나 테이블명만 보고 추측하지 않는다.

```
각 TC의 검증 쿼리/방법을 작성하기 전에:

1. 코드 추적 (WHERE does the system record X?)
   - "X가 발생하면 시스템이 어디에 기록하는가?"를 소스코드에서 추적
   - Handler/Service → Repository/API/외부시스템 순으로 따라감
   - 최종 저장소가 DB 테이블인지, Elasticsearch인지, Kafka 토픽인지, 외부 API인지 확인

2. 추측 금지 (NEVER guess from column/table names)
   ❌ "event_reason 컬럼이 있으니 dead letter 지표일 것이다"
   ❌ "error_count 컬럼이 있으니 에러 횟수를 추적할 것이다"
   ✅ "DeadLetterHandler.onError() → dead-letter-api → Elasticsearch 저장 확인"
   ✅ "ErrorCountService.increment() → error_log 테이블 INSERT 확인"

3. 검증 경로 명시 (TC에 추적 결과를 기록)
   각 TC의 기대결과(DB) 작성 시 다음을 포함:
   - 검증 대상: {무엇을 확인하는가}
   - 데이터 소스: {코드 추적으로 확인한 실제 저장 위치}
   - 추적 경로: {Handler → Service → 저장소}
   - 검증 방법: {구체적 쿼리/API/로그 조회}
```

> ⚠️ 이 단계를 건너뛰면 "우연히 맞는 결과"로 PASS 판정하는 오류가 발생한다.
> 실제 사례: `outbound_order.event_reason`은 리피킹 사유 컬럼이지만, 컬럼명만 보고 dead letter 지표로 오인하여 잘못된 검증 수행.

### Step 4.3: 사전조건 통합 (test-prereq 흡수)

> **실행 순서**: 4.3-A/B (행위 조건 도출) → 4.3-C (tc_spec.json 생성) → 마크다운 시트 확정
> tc_spec.json이 먼저 생성되어야 마크다운 셀에 `contract_ref` 형식이 정상 참조됨.

TC 작성 시 다음 사전조건 항목을 각 TC에 포함합니다:

```
각 TC 사전 조건 체크리스트:
- [ ] 필요한 엔티티 및 상태 (예: {entity} {STATUS}, {related_entity} {STATE})
- [ ] DB 사전 레코드 (예: {table_name} 존재)
- [ ] 필요한 수량/날짜 조건
- [ ] API 의존성 (호출해야 할 사전 API)
- [ ] 필요한 계정/권한 (예: {ROLE_NAME} 역할)
- [ ] Feature flag 설정 (해당 시)
- [ ] 행위적 조건 (Step 4.3-A 참조)
```

> 이 정보는 test-data 스킬이 TC별 데이터 검색 조건으로 직접 사용합니다.
> **특히 행위적 조건은 test-data의 Purpose Fitness Check(Step 4.5)에서 데이터 적합성 검증에 사용됩니다.**

### ⭐ Step 4.3-A: 행위적 조건 도출 (Behavioral Condition Extraction)

> **원칙**: TC의 기대결과가 성립하려면 데이터가 어떤 런타임 상태여야 하는지를 명시한다.
> 구조적 조건(레코드 존재, 수량, 관계)과 별개로, 코드의 조건분기를 통과하기 위한 상태 조건이다.
> 행위적 조건이 누락되면 "구조적으로 맞지만 목적에 부적합한" 데이터로 테스트하게 된다.

#### 도출 방법: 기대값 역추적 (3단계)

행위적 조건은 기대값 도출의 **부산물**이다. 별도 분석이 아니라, 기대값을 계산하는 과정에서 자연스럽게 나온다:

```
Step 1: 기대값의 출처 확인
  "이 TC의 기대값(quantity=1)은 코드의 어떤 계산에서 나오는가?"
  → allocated = Math.min(remaining, demand)

Step 2: 계산의 진입 조건 확인
  "이 계산이 실행되려면 어떤 조건을 통과해야 하는가?"
  → if (currentState == PICKING) 블록 안에 있음

Step 3: 조건을 데이터 요구사항으로 변환
  "이 조건이 성립하려면 데이터가 어떤 상태여야 하는가?"
  → job_lifecycle_outbound_order_mapping.outbound_order_state = 'PICKING'
```

#### 메타데이터 활용 (필수 참조)

행위적 조건 도출 시 다음 아키텍처 메타데이터를 **반드시 참조**한다:

| 메타데이터 | 활용 | 예시 |
|-----------|------|------|
| `data-contracts.json` → `semanticContracts` | 컬럼의 비즈니스 의미, writer/reader, 상태 조건 | `outbound_order_state`는 비정규화 캐시 → 실시간 상태는 outbound에서 확인 |
| `data-contracts.json` → `dataFlowPaths` | 엔티티 상태 라이프사이클, 상태 전이 순서 | containerLifecycle: 생성→피킹중→배치완료 |
| `data-contracts.json` → `nullSemantics` | null/빈값의 비즈니스 의미 | `worker_id = null` → 작업자 미배정 (PENDING 상태) |
| `db-schemas/{service}.json` | 상태 컬럼의 가능한 값, 컬럼 간 관계 | `container_state` enum 값 목록 |
| `api-dependencies.json` | API 호출 체인에서 상태 전이 포인트 | 피킹 시작 API → 주문 상태가 PICKING으로 변경 |

```
참조 흐름:
  1. TC 기대값에 상태 관련 값이 있으면
  2. data-contracts.json의 semanticContracts에서 해당 컬럼 확인
  3. businessRule, dataFlowPath에서 해당 값이 설정되는 시점 파악
  4. 그 시점이 현재 데이터에서 이미 지나갔는지/아직인지 판단
  5. → 행위적 조건으로 기록
```

#### TC에 행위적 조건 기술 형식

> **tc_spec.json이 있는 경우 (REPLAN 시 — 이전 tc_spec.json 재사용)**: 마크다운 셀에는 contract_ref만 기재.
> **tc_spec.json이 없는 경우**: 아래 폴백 형식으로 기술.
>   ⚠️ NEW 최초 실행 시에도: tc_spec.json이 Step 4.3-C에서 먼저 생성된 후 마크다운이 확정되므로,
>      마크다운 셀에서도 contract_ref 형식(1줄)을 사용할 수 있다.
>      폴백 형식(전체 텍스트)은 tc_spec.json 생성이 실패한 경우에만 사용.

tc_spec.json 있는 경우 (기본):
```markdown
| 항목 | 내용 |
|------|------|
| 사전 조건 | container에 복수 주문, overflow 상태 |
| 기대 결과 | Waterfall 분배 적용, quantity > 0 |
| **행위적 조건** | `contract_ref: BC-1.C-1` (상세: tc_spec.json 참조) |
```

tc_spec.json 없는 경우 (폴백 — 하위 호환):
```markdown
| 항목 | 내용 |
|------|------|
| 사전 조건 | container에 복수 주문, overflow 상태 |
| 기대 결과 | Waterfall 분배 적용, quantity > 0 |
| **행위적 조건** | `outbound_order_state = 'PICKING'` (코드 근거: ContainerWebQueryApplication:668) |
```

#### 행위적 조건이 불필요한 경우

도출 트리(Step 4.3-B)에 ② Transform / ③ Filter 레이어가 없는 TC만 N/A 판정 가능.
N/A 기재 시: `N/A (상태 무관 — 도출 트리 ②③ 레이어 없음)`

**⚠️ "GET 조회 API"라는 이유만으로 N/A 판정 금지.** 코드 내부 로직(계산/필터/분기)이 기준이다.

> `validate_test_sheet.py` Hook이 N/A + ②③ 레이어 동시 존재 시 Write/Edit를 차단한다.

### ⭐ Step 4.3-B: 기대값 도출 트리 (Expected Value Derivation Tree)

> **원칙**: TC의 기대값(숫자, 상태, 배열 길이 등)이 **어떤 데이터 체인에서 도출되었는지**를
> "계산 가능한 트리"로 명시한다.
> 기대값이 "검증 질문"에만 적혀 있고 도출 근거가 없으면,
> 리뷰어는 그 숫자가 왜 맞는지 판단할 수 없다.
>
> 이 트리는 test-reporter에서 **그대로** "사전 조건 확인" 섹션에 출력되며,
> 상세확인내용에서 기대값을 재설명하지 않는다 (간소화 원칙).

#### 도출 트리 형식 (모든 TC 필수)

각 TC의 "사전 조건 확인" 블록에 ASCII 트리를 포함한다:

```
{Root Entity ID}
├─① {Source Layer}: {테이블명.컬럼 = 값}
│  └─ {세부 항목}: {키 = 값}
├─② {Transform Layer}: {계산/필터링 로직}
│  └─ {항목}: {값} (근거: {어디서 왔는지})
├─③ {Filter Layer} (해당 시): {필터 조건}
│  └─ 포함: {N개}, 제외: {M개} (이유)
└─④ 기대결과: {①+②+③에서 도출된 최종 기대값}
```

#### 레이어 분류 기준

| 레이어 | 역할 | 예시 |
|--------|------|------|
| ① Source | 원시 데이터 (DB 테이블 직접 조회) | container_lifecycle_sku.quantity = 2 |
| ② Transform | 데이터 가공/매핑 (JOIN, 집계) | batch_lifecycle_source_smu_sku.quantity 주문별 합산 |
| ③ Filter | 조건부 필터링 (WHERE, 코드 분기) | job_lifecycle_outbound_order_mapping 존재 여부 |
| ④ Outcome | 최종 기대값 (①+②+③에서 도출) | outboundOrderSkuGroups 배열 길이 = N |

> ③ Filter는 해당 시에만. 필터링이 없으면 ①→②→④ 3레이어로 충분하다.

#### 도출 예시 — 단순 (1주문 1SKU)

```
TT0000000039799
├─① container_lifecycle_sku: SMU 200408, container_qty = 2
├─② batch_lifecycle_source_smu_sku: SH152374, batch_plan_qty = 2
└─④ 기대결과: 1개 그룹, 1개 SKU, quantity=2
```

#### 도출 예시 — 복잡 (Job 필터링 포함)

```
TT0000000042925
├─① batch 전체 주문: 8개
├─② Job 매핑 (job_lifecycle_outbound_order_mapping):
│  └─ SH167714 → TT42924 (다른 컨테이너) ← 제외
│  └─ SH167715 → TT42925 (이 컨테이너)  ← 포함
├─③ 미매핑 주문: 6개 (SH167716~721) ← 제외
└─④ 기대결과: 1개 그룹 (SH167715만 반환)
```

#### 도출 트리가 불필요한 경우

- 기대값이 단순 상태 확인 (예: HTTP 200, inUse=false)
- 기대값이 고정 상수 (예: 에러 메시지 문자열)
- 존재하지 않는 엔티티 조회 (null/empty 반환)

이 경우 `④ 기대결과: {값} (고정값 — 도출 불필요)` 1줄로 갈음.

#### 종합 검증 쿼리 (선택 — 복수 TC 공유 시 권장)

여러 TC가 동일 데이터 체인을 사용하면, 종합 쿼리 1개로 전체 TC 데이터를 확인한다.
이 쿼리는 테스트시트 "사전 조건 DB 검증 (종합)" 섹션에 기재하고, 각 TC에서 결과를 참조한다.

```sql
-- 종합 검증 쿼리 예시
SELECT cl.container_code, cls.stock_management_unit_id, cls.quantity AS container_qty,
       bsms.outbound_order_id, bsms.quantity AS batch_plan_qty
FROM container_lifecycle cl
JOIN container_lifecycle_sku cls ON ...
JOIN batch_lifecycle_source_smu_sku bsms ON ...
WHERE cl.container_code IN ('TT39799', 'TT44017', ...)
ORDER BY cl.container_code, bsms.outbound_order_id
```


### ⭐ Step 4.3-C: tc_spec.json 생성 (Plan 완료 시 필수)

> **원칙**: 테스트시트 마크다운은 사람이 읽는 문서다. Data/Execute 스킬이 읽는 계약은 JSON이다.
> 마크다운의 `행위적 조건`, `사전 조건`, `기대결과` 셀은 사람을 위한 요약이고,
> 기계는 이 단계에서 생성하는 `tc_spec.json`만 참조한다.
>
> **실행 시점**: Step 4.3-A/B에서 TC별 행위 조건을 도출한 직후 실행한다.
>   ⚠️ 실행 순서 중요:
>   1. tc_spec.json 먼저 생성 (Step 4.3-C)
>   2. 그 후 마크다운 테스트시트 확정 (Step 4.3-A 셀 형식 적용)
>   → NEW 최초 실행 시에도 tc_spec.json이 같은 실행에서 생성되므로, 마크다운 셀에 contract_ref 형식 사용 가능
>
> **입력**: Gate의 `test_baseline.behavioral_contracts[]` + 이번 단계에서 도출한 TC 목록
> **behavioral_contracts가 없는 경우 (Plan 단독 실행 / SOURCE_DIRECT 미실행)**:
>   → Step 1.2-A에 준하여 직접 소스코드에서 조건분기를 분석하여 behavioral_contracts를 생성한다.
>   → 생성된 behavioral_contracts는 tc_spec.json에만 포함 (gate.json 파일 없으므로 저장 불필요)
>   → WARNING: "Gate behavioral_contracts 없음 — Plan에서 직접 생성 (정확도 저하 가능)"
> **출력**: `{ticket}_tc_spec.json`

#### tc_spec.json 스키마

```json
{
  "ticket": "PROJ-123",
  "sheet_version": "v1",
  "generated_at": "ISO8601",
  "tcs": {
    "TC-1": {
      "type": "ACTIVE | OBSERVATION",
      "stimulus": {
        "method": "GET | POST | PUT | DELETE",
        "path": "/api/경로/{param}",
        "path_params": { "param": "{data.필드명}" },
        "body": null
      },
      "behavioral_condition": {
        "contract_ref": "BC-1.C-1",
        "db_check": {
          "db": "MCP 도구명",
          "sql": "SELECT 컬럼 FROM 테이블 WHERE 조건 AND entity_code = '{data.entity_code}'",
          "assert": "all_eq('PICKING') | any_eq('VALUE') | count_gte(N) | count_eq(N) | is_null | is_not_null"
        }
      },
      "data_requirement": {
        "db": "MCP 도구명",
        "table": "테이블명",
        "where": "SQL WHERE 절 (그대로 쿼리 삽입 가능)",
        "extra_joins": ["JOIN other_table ot ON ot.id = t.id"],  // 배열 타입 — JOIN 절 목록 (복수형: data_requirement 전용)
        "min_rows": 1,
        "identifier_column": "container_code",
        "identifier_field": "container_code"
      },
      "expected": {
        "http_status": 200,
        "fields": [
          {
            "path": "응답 JSON 경로 (예: outboundOrderSkuGroups[*].skus[*].quantity)",
            "source_db": "MCP 도구명",
            "source_table": "테이블명",
            "source_column": "집계할 컬럼명 (예: quantity)",
            "source_where": "SQL WHERE 절",
            "extra_join": "JOIN 절 (선택, 예: JOIN batch_lifecycle_source_smu_sku bss ON ...)",
            "aggregation": "sum | count | max | min | null",
            "formula": "human-readable 계산식 설명 (참고용)"
          }
        ],
        "static_fields": {"http_status": 200, "inUse": false}
      }
    }
  }
}
```

> **extra_join 필드 이름 규칙**
> - `data_requirement.extra_joins`: 배열 `[]` (복수형 — JOIN 절 목록, 데이터 조회 쿼리용)
> - `expected.fields[].extra_join`: 문자열 (단수형 — 단일 JOIN 절, 기대값 계산 쿼리용)
> - 이름(단/복수)으로 타입을 구분한다. 혼용 금지.

- `identifier_column`: formula SQL의 WHERE 절에 사용할 엔티티 식별 컬럼명
- `identifier_field`: `data_mapping.data[identifier_field]`로 실제 값 조회

#### assert 함수 목록 (verdict_calculator 해석용)

| 함수 | 의미 |
|------|------|
| `all_eq('VALUE')` | 조회된 모든 행의 값이 VALUE와 동일 |
| `any_eq('VALUE')` | 하나 이상의 행이 VALUE |
| `count_eq(N)` | 행 수가 정확히 N |
| `count_gte(N)` | 행 수가 N 이상 |
| `is_null` | 값이 null |
| `is_not_null` | 값이 null이 아님 |

#### 생성 규칙

1. `behavioral_condition.contract_ref`: Gate의 `behavioral_contracts[].conditions[].condition_id` 참조 (형식: `BC-{N}.C-{M}`)
  ※ condition_id는 부모 BC 객체 내에서만 유일 (다른 BC가 동일한 condition_id "C-1"을 가질 수 있음)
  ※ contract_ref 조회 알고리즘:
     parts = contract_ref.split(".")  # ["BC-1", "C-1"]
     bc = behavioral_contracts.find(bc => bc.id == parts[0])
     condition = bc.conditions.find(c => c.condition_id == parts[1])
2. `behavioral_condition.db_check.sql`: 플레이스홀더 `{data.필드명}` 허용 — Data 단계가 실제 매핑값으로 치환
3. `data_requirement.where`: Gate `behavioral_contracts[*].conditions[*].test_data.where`에서 **그대로 복사** (재해석 금지)
4. `expected.fields[*]`: `source_where`는 behavioral_condition과 일치해야 함 (기대값 도출 조건 = 데이터 선택 조건)
5. `expected.static_fields`: formula 없는 고정값 (HTTP 상태코드, boolean 등)
6. 불확실한 값은 `null` — 추측으로 채우기 금지

#### 마크다운 테스트시트와의 관계

- 마크다운 `행위적 조건` 셀: `"contract_ref: BC-1.C-1"` 1줄만 기재 (JSON은 tc_spec.json 참조)
- 마크다운 `사전 조건` 셀: 사람이 읽는 요약 텍스트 유지 (기계는 `data_requirement.where` 사용)
- 마크다운 `기대결과` 셀: 사람이 읽는 설명 유지 (기계는 `expected.fields[*].formula` 사용)

파일 생성: `{ctx.ticket_folder}/{ticket}_tc_spec.json`

### Step 4.4: 데이터 흐름 구간 정의 (e2e TC 해당 시)

> **원칙**: e2e TC가 여러 처리 단계를 거치는 경우,
> 각 구간에서 데이터가 어떻게 변하는지를 검증 계획에 포함한다.
> 이 정의는 test-run의 CHECKPOINT 프로토콜(5.2.2)의 설계 근거가 된다.

#### 해당 조건

- TC의 STIMULUS가 여러 API 호출 시퀀스로 구성
- 비동기 이벤트 체인을 거치는 TC
- 상태 전이가 3단계 이상인 TC

#### 구간 정의 형식

각 TC에 "데이터 흐름 구간" 테이블을 포함:

```markdown
| 구간 | 트리거 | 검증 대상 (테이블.컬럼) | 기대 변화 |
|------|--------|----------------------|----------|
| ① 주문 생성 | POST /outbound/create | outbound_order.state | null → CREATED |
| ② 피킹 시작 | POST /picking/start | job_lifecycle.state | CREATED → IN_PROGRESS |
| ③ 피킹 완료 | POST /picking/complete | container_lifecycle_sku.qty | 0 → N |
| ④ 패킹 완료 | POST /packing/complete | outbound_order.state | PICKING → PACKING |
```

이 테이블이 test-run Step 5.2.2(CHECKPOINT)에서 중간 스냅샷 대상이 된다.

#### 구간 정의가 불필요한 경우

- 단일 API 호출 TC (기존 BEFORE/AFTER로 충분)
- GET 조회 TC (상태 변화 없음)

이 경우 "데이터 흐름 구간: N/A (단일 호출)" 기재.

### Step 4.5: Test Baseline 기록 (필수)

테스트시트 Section 0에 **반드시** 다음 서브섹션을 포함합니다.
이 섹션은 다음 Gate 실행 시 변경 감지(Semantic Diff)의 기준점이 됩니다.

| 서브섹션 | 내용 | 형식 |
|----------|------|------|
| 0.1 Jira Digest | 정규화된 요구사항 (ID, 요구사항, 출처) | 테이블 |
| 0.2 Code Digest | 구현 사항 (ID, 구현 내용, 변경 파일) | 테이블 |
| 0.3 비교 결과 | 합집합 기준 일치/미기재/미구현 | 리스트 |
| 0.4 영향 서비스 | 서비스명, 유형(BE_API/FE_WEB/FE_APP), 브랜치 | 테이블 |
| 0.5 테스트 유형 | api_test, db_verify, web_ui_capture 등 활성 여부 | 테이블 |
| 0.6 참조 체인 | 변경점 → 참조 경로 → 최종 소비자 | 테이블 |
| 0.7 데이터 시나리오 | 분기 조합별 TC 매핑 + 누락 식별 | 테이블 |

> `validate_test_sheet.py` Hook이 `### 0.1` ~ `### 0.7` 존재를 강제한다.
> Section 0.4~0.5는 Gate 1.8의 영향도 재검증에, 0.6~0.7은 TC 누락 방지에 사용된다.

---

## Output Format

> 출력 형식은 `test/templates/테스트시트_템플릿.md` 기준으로 작성한다.

---

## Related Skills

- **test-gate**: Gate 출력(test_baseline)을 전달받아 사용 (Jira 재조회 불필요)
- **test-data**: 테스트 데이터 매핑 (Plan 이후 실행)
- **test-run**: 테스트 실행 (Data 이후 실행)
- **test-evidence**: 근거 작성 가이드
