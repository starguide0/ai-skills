---
name: test-data
description: This skill should be used when the user requests "테스트 데이터", "test data", "데이터 준비", "data preparation", "데이터 매핑", "data mapping", mentions preparing or finding test data for test cases, or asks to map test data to TCs. Also activates as Step 4 in test-run orchestrator pipeline.

Parameters to extract:
- Feature/Ticket name (required)
- Mode (optional): "discovery" (기본), "provisioning", "capture-plan"

version: 2.2.0
---

# Test Data Skill

## Purpose

테스트시트의 TC별 데이터 요구사항을 분석하여 실제 테스트 가능한 데이터를 매핑합니다:

---

## _shared/ Dependencies

이 스킬이 로드하는 `_shared/` 파일 목록 (이 외는 로드하지 않는다):
- `테스트_주의사항.md` — DB 스키마 오류, 반복 실수 방지 (가장 먼저 로드)
- `환경/URL.md` — 환경별 서비스 URL
- `환경/API_엔드포인트.md` — 서비스별 API 목록 (API 기반 데이터 탐색에 사용)
- `rule/_caution_mcp_usage.md` — MCP PostgreSQL 도구 안전 사용 가이드
- `rule/_caution_missing_tables.json` — DB 스키마에 누락된 테이블 목록
- `.claude/skills/test/rules/_caution_common_errors.md` — 반복 발생 오류 패턴
- `rule/_caution_error_candidates.json` — 오류 후보 패턴

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| 테스트시트 | test-plan | Y | {ticket}_테스트시트_v{N}_{date}.md — TC별 데이터 요구사항 포함 |
| 행위적 조건 | test-plan | N | TC별 행위적 조건 (테스트시트 내 포함). 없으면 CoT Fallback으로 자체 추론 |
| {ticket}_tc_spec.json | test-plan | 조건부 | TC별 행위 조건·데이터 요구사항 구조화 JSON — 없으면 마크다운 폴백 모드 (정확도 저하) |
| ctx.tc_spec | test-plan | 조건부 | tc_spec.json 절대 경로. 없으면 Glob으로 복원 |
| ctx.sheet_version | test-plan | Y | v{N} — 메이저 버전 (스킵 판정 시 사용) |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| 데이터매핑.json | test-scheduler, test-provisioning | {ticket}_데이터매핑.json — TC별 매핑 결과 |
| ctx.data_mapping | test-scheduler, test-run | 데이터매핑.json 절대 경로 |
| mappings.{tc_id}.status | test-scheduler, test-provisioning | MAPPED/NOT_FOUND/PROVISIONING_NEEDED/PROVISIONED |
| mappings.{tc_id}.data | test-run (Step 5.3) | 실제 매핑된 데이터 (entity_code, organization_id 등) |
| mappings.{tc_id}.discovery_query | (디버깅용) | 데이터 검색에 사용한 SQL 쿼리 |
| summary.total_tcs | test-run (Step 4) | 전체 TC 개수 |
| summary.mapped | test-run (Step 4) | 매핑 성공 TC 개수 |
| summary.not_found | test-run (Step 4) | 데이터 없는 TC 개수 |
| summary.provisioning_needed | test-run (Step 4) | 프로비저닝 필요 TC 개수 |
| summary.provisioned | test-run (Step 4) | 프로비저닝 완료 TC 개수 |
| summary.behavioral_mismatch | test-run (Step 4) | 행위적 조건 미충족 TC 개수 (내부적으로 NOT_FOUND로 전환) |
| summary.coverage | test-run (Step 4) | 매핑 커버리지 (백분율) |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- Phase 기반 실행 (Phase 1: 독립 쿼리 병렬, Phase 2: 의존 쿼리 순차)
- Layer 1: 자동 판정 (파라미터 출처 분석 → STATIC/DERIVED)
- Layer 2: 명시적 패턴 (known_cross_db_patterns)
- 의존성 분류 알고리즘 (STATIC → depends_on: [], DERIVED → depends_on: [소스 쿼리])
- 크로스 DB 의존성 자동 감지 (DERIVED이면 DB 달라도 순차 필수)
- shared_entity 최적화 (1회 조회 → 복수 TC 공유)
- batch_query 최적화 (동일 테이블 쿼리 병합)
- Group 분리 (MCP 도구별 Group → 같은 Group 내 순차, 다른 Group 병렬)
- known_cross_db_patterns: entity_state_verify, reference_data_enrich, snapshot_query, independent_validation
- 워크플레이스/조직 우선순위 로직 (같은 조직 우선, 여러 TC 커버 가능한 데이터 우선)
- 핵심 엔티티 존재 검증 (INNER JOIN 필수)

---

- **Discovery**: DB에서 TC 조건에 맞는 기존 데이터 검색 (크로스 조직/파티션)
- **Provisioning**: 기존 데이터가 없을 때 API로 데이터 생성 (POST/PUT 테스트용)
- **Capture Plan**: 데이터 변화 캡쳐 시점 계획 (상태 전이 테스트용)

---

## Trigger Examples

### 한글

- "PROJ-123 테스트 데이터 찾아줘"
- "PROJ-456 데이터 매핑해줘"
- "테스트 데이터 준비해줘"
- "TC별 사용할 데이터 매핑"

### 영어

- "Find test data for PROJ-123"
- "Map test data for PROJ-456"
- "Prepare test data"

---

## Parameter Extraction

```
Input: "PROJ-123 테스트 데이터 찾아줘"

추출:
- 티켓: "PROJ-123"
- 작업: "데이터 매핑"
- 모드: "discovery" (기본값)
```

---

## Execution Steps

### Step 1: 사전 리소스 로드

```
[1단계] 공통 환경 + 도메인 지식 (test/_shared/):
> 로드 대상은 상단의 ## _shared/ Dependencies 선언을 따른다.
0. test/_shared/테스트_주의사항.md — DB 스키마 오류, 반복 실수 방지 (가장 먼저!)
1. test/_shared/환경/URL.md — 환경별 서비스 URL
2. test/_shared/환경/API_엔드포인트.md — 서비스별 API 목록

[2단계] 시스템 아키텍처:
3. .claude/architecture/db-schemas/{관련 서비스}.json — DB 테이블/컬럼 구조

[3단계] DB 오류 방지 (rules/):
4. test/_shared/rule/_caution_missing_tables.json — DB 테이블 정보 (누락분)
5. .claude/skills/test/rules/_caution_common_errors.md — DB 쿼리 오류 패턴
6. test/_shared/rule/_caution_mcp_usage.md — MCP 도구 사용법
```

### Step 2: tc_spec.json 파싱 — TC별 데이터 요구사항 추출

> **tc_spec.json이 마크다운 파싱보다 우선한다.**
> 마크다운 테스트시트의 `사전 조건` / `행위적 조건` 셀은 사람을 위한 설명이다.
> 기계(Data 스킬)는 `tc_spec.json`의 JSON 필드를 그대로 사용하며 자연어를 재해석하지 않는다.

**ctx 복원 (Read-Through Fallback)**:
```
IF ctx.tc_spec 없으면:
  → Glob: {ctx.ticket_folder}/{티켓}_tc_spec.json  # ← ticket_folder 포함 (CWD 독립)
  → 발견 시: ctx.tc_spec = 파일 절대 경로 (Read/parse는 로컬 변수 tc_spec_data에)
IF 파일도 없으면:
  → WARNING: "tc_spec.json 없음 — 마크다운 폴백 모드 (정확도 저하 경고)"
  → 마크다운 테스트시트 파싱 (하위 호환)
  → NOTE: REUSE 모드로 실행 중이거나 이전 Plan 버전인 경우 정상
```

**정상 경로 (tc_spec.json 존재)**:
```
1. Read: {ctx.tc_spec} → JSON parse → tc_spec_data (로컬 변수)
   # ctx.tc_spec은 파일 경로(string)로만 유지. dict 접근은 tc_spec_data를 통해서만.

2. 각 TC에서 데이터 요구사항 추출 (자연어 파싱 없음):
   FOR each tc_id in tcs:
     data_req = tc_spec_data["tcs"][tc_id]["data_requirement"]
       → db:        MCP 도구 식별자
       → table:     검색 대상 테이블
       → where:     SQL WHERE 절 (그대로 삽입 가능, NL 변환 불필요)
                    ⚠️ null인 경우: "1=1" 로 대체 (전체 조회) + WARNING 출력
                       "TC-{id}: data_requirement.where null — 행위 조건 없이 검색"
       → extra_joins: JOIN 절 목록 (배열, 예: ["JOIN tbl t ON t.id=x.id"]) — null이면 생략
                     (복수형 필드명. expected.fields[].extra_join(문자열 단수형)과 구분)
       → min_rows:  최소 결과 행 수 (null이면 1 적용)

  ※ source_column, source_where, aggregation, identifier_column, identifier_field 필드는
     tc_spec.json의 expected.fields[]에 있으며, VERDICT 단계(test-run Step 7)에서 사용된다.
     test-data Step 2는 data_requirement.where만 사용하며 source_where를 재해석하지 않는다.

     behav_cond = tcs[tc_id].behavioral_condition
       → db_check.sql: Purpose Fitness Check (Step 4.5)에서 직접 실행할 SQL
                        null이면 Step 4.5-A 스킵 → Step 4.5-B만 실행
       → db_check.assert: 검증 함수

3. TC별 디스커버리 쿼리 생성:
   where_clause = data_req.where ?? "1=1"  # null 안전 처리
   base_query = "SELECT ... FROM {data_req.table} WHERE {where_clause}"
   # where_clause를 그대로 삽입 (NL 해석/변환 없음)
   # data_requirement.extra_joins(배열)이 있으면 각 JOIN 절을 순서대로 추가
```

**폴백 경로 (마크다운 파싱 — tc_spec.json 없는 경우)**:
```
기존 마크다운 파싱 로직 실행 (하위 호환):
- "사전 조건" 컬럼 → 자연어 파싱 → 데이터 조건 추론
- "행위적 조건" 컬럼 → CoT 추론 → Step 4.5-C 실행
```

### Step 3: 쿼리 의존성 분석 + 실행 계획

TC별 데이터 요구사항을 분석하여 **병렬/순차 실행 계획**을 자동 생성한다.

**3.1 쿼리 목록 생성**

각 TC의 데이터 조건(Step 2)을 SQL 쿼리로 변환하고, 각 쿼리에 메타정보를 태깅한다.

```
TC-1.1 → [
  { id: "Q1", db: "{primary_db}",   sql: "SELECT ... FROM {entity_lifecycle} ...", depends_on: [] },
  { id: "Q2", db: "{primary_db}",   sql: "SELECT ... FROM {entity_lifecycle_detail} WHERE lifecycle_id = Q1.result", depends_on: ["Q1"] },
  { id: "Q3", db: "{secondary_db}", sql: "SELECT ... FROM {related_entity} WHERE ...", depends_on: [] }
]
```

**3.2 의존성 분류 (2계층 판정)**

의존성 판정은 **자동 판정 + 명시적 패턴** 2계층으로 이루어진다.

**Layer 1: 자동 판정 (쿼리 파라미터 출처 분석)**

각 쿼리의 WHERE 파라미터가 어디서 오는지 분석하여 의존성을 자동 태깅한다.

```
파라미터 출처 분류:
  STATIC   — 고정값 (테스트시트/매핑 파일에 명시된 값)
             예: entity_code = '{entity_id_1}' (매핑 파일에 있음)
  DERIVED  — 다른 쿼리 결과에서 추출해야 하는 값
             예: related_entity_id = Q-primary-1.result.related_entity_id

  STATIC  → depends_on: []        (독립)
  DERIVED → depends_on: [소스 쿼리]  (순차 필수, DB가 달라도!)
```

이를 통해 크로스 DB 의존성도 자동 감지한다:

```
예: TC-2.1 related_entity_state 검증
  Q-primary-1 ({primary_db}):  SELECT related_entity_id FROM {entity_source_detail}
                                WHERE entity_code = '{entity_id_1}'  ← STATIC (매핑에 있음)
                                → depends_on: []

  Q-secondary-1 ({secondary_db}): SELECT entity_state FROM {related_entity}
                                   WHERE related_entity_id IN (Q-primary-1.result)  ← DERIVED!
                                   → depends_on: ["Q-primary-1"]  ← 다른 DB이지만 순차 필수!
```

**Layer 2: 명시적 패턴 (알려진 크로스 서비스 의존성)**

비즈니스 로직 수준에서 서비스 간 데이터 흐름이 순서를 요구하는 패턴을 정의한다.
이 패턴은 Layer 1에서 감지하지 못하는 암묵적 의존성을 보완한다.

```
known_cross_db_patterns:
  - pattern: "entity_state_verify"
    description: "엔티티 상태 검증 시 {db_1}에서 entity_id 목록 → {db_2}에서 상태 조회"
    source_db: "{db_1}"
    target_db: "{db_2}"
    link_field: "related_entity_id"
    order: SEQUENTIAL

  - pattern: "reference_data_enrich"
    description: "참조 데이터 보강 시 {db_1}에서 ref_id → {db_3}에서 상세 정보"
    source_db: "{db_1}"
    target_db: "{db_3}"
    link_field: "reference_id"
    order: SEQUENTIAL

  - pattern: "snapshot_query"
    description: "스냅샷 조회 시 {db_4}는 독립 조회 가능"
    source_db: "{db_4}"
    target_db: "*"
    order: PARALLEL

  - pattern: "independent_validation"
    description: "서로 다른 엔티티의 독립적 존재 확인"
    condition: "두 쿼리가 서로의 결과를 참조하지 않음"
    order: PARALLEL
```

> **패턴 추가 방법**: 새로운 크로스 서비스 의존성 발견 시 이 목록에 추가한다.
> 테스트 실행 중 "DERIVED인데 패턴에 없는" 케이스를 발견하면 사용자에게 알리고 패턴 추가를 제안한다.

**3.3 최종 의존성 판정 흐름**

```
FOR each 쿼리 Q:
  1. [Layer 1] 파라미터 출처 분석:
     FOR each Q의 WHERE 파라미터:
       IF 값이 매핑 파일/테스트시트에 존재 → STATIC
       IF 값이 다른 쿼리 결과에서 추출 필요 → DERIVED
         → depends_on에 소스 쿼리 추가 (DB 무관!)

  2. [Layer 2] 패턴 매칭:
     IF Q의 source_db + target_db 조합이 known_cross_db_patterns에 매칭
       → 해당 패턴의 order 적용 (SEQUENTIAL / PARALLEL)
     IF Layer 1과 Layer 2가 충돌
       → Layer 1 우선 (실제 데이터 의존성이 더 정확)
       → 충돌 사실을 로그에 기록

  3. [그룹핑] 최종 실행 계획:
     depends_on이 있는 쿼리 → 소스 쿼리 완료 후 실행 (DB 무관)
     depends_on이 없고 같은 DB → 같은 Group 내 순차 (MCP 제약)
     depends_on이 없고 다른 DB → 병렬 가능

  ━━━ 순환 참조 검증 (필수 가드) ━━━

  IF detect_cycle(dependency_graph):
    cycle_path = get_cycle_path(dependency_graph)
    → ERROR("순환 의존성 감지: {cycle_path}")
    → 사용자에게 수동 해결 요청
    → 파이프라인 중단

  # detect_cycle: Kahn's algorithm 종료 조건 활용
  # 모든 노드가 제거되지 않으면 순환 존재
```

**3.4 실행 계획 생성**

```
분석 결과 예시 (TICKET-123 기준):

Phase 1: 독립 쿼리 (병렬 실행)
  [Group A] {primary_db}
    ├── Q-primary-1: {entity_id_1} 엔티티 체인 (TC-1.3/1.4/3.2 공유)
    ├── Q-primary-2: {entity_id_2} 엔티티 체인 (TC-1.1)
    ├── Q-primary-3: {entity_id_3} 엔티티 체인 (TC-1.2)
    ├── Q-primary-4: {entity_id_4} 엔티티 체인 (TC-3.1/S.1/S.2 공유)
    └── Q-primary-5: {entity_id_5} 엔티티 체인 (TC-3.3)
         ∥
  [Group B-independent] {secondary_db}
    └── (독립 쿼리 없음 — 모든 {secondary_db} 쿼리가 {primary_db} 결과에 의존)

Phase 2: 의존 쿼리 (Phase 1 완료 후)
  [Group B-derived] {secondary_db}
    ├── Q-sec-1: {related_id_1}~{related_id_4} 상태 조회 (depends_on: Q-primary-1, batch_query)
    ├── Q-sec-2: {related_id_5} 상태 조회 (depends_on: Q-primary-2)
    └── Q-sec-3: {related_id_6} 상태 조회 (depends_on: Q-primary-3)

실행 타임라인:
  Phase 1: Group A (순차) ──────────────────→
  Phase 2:                 Group B (순차) ──→
  총 대기: Phase 1 시간 + Phase 2 시간
```

**3.5 추가 최적화**

| 최적화 유형 | 판정 기준 | 처리 |
|------------|----------|------|
| **shared_entity** | 복수 TC가 동일 엔티티 조회 (예: 같은 entity_code) | **1회 조회 → 결과 공유** |
| **batch_query** | 같은 Group+Phase 내 독립 쿼리가 동일 테이블 대상 | **단일 쿼리로 병합** (WHERE IN (...)) |

### Step 4: DB 검색 실행 — Phase 기반

Step 3에서 생성한 실행 계획에 따라 Phase별로 쿼리를 실행한다.

```
1. Phase별 실행:
   FOR each Phase (1 to N):
     a. 현재 Phase의 Group들을 확인
     b. 서로 다른 MCP 도구 Group은 동시 실행 (Task tool 병렬 호출)
     c. 같은 Group 내부는 순차 실행
     d. DERIVED 파라미터는 이전 Phase 결과에서 자동 주입
     e. 현재 Phase 모든 쿼리 완료 후 다음 Phase 진행

2. 모든 조직/파티션을 대상으로 검색 (조직 ID 고정 안 함!)

3. 각 TC에 대해 최적 데이터 후보 선정:
   - 우선순위: 같은 조직 > 다른 조직
   - 동일 조직에서 여러 TC 커버 가능한 데이터 우선

4. 핵심 엔티티 존재 여부 반드시 INNER JOIN으로 검증

핵심 검증 항목:
- 핵심 엔티티 레코드 존재 (물리 삭제 가능성 → INNER JOIN 필수)
- 연관 상세 엔티티 존재 (NULL 외래키 제외)
- 하위 엔티티 존재 (빈 레코드 제외)

5. 공유 엔티티 결과 분배:
   - 1회 조회된 결과를 해당 TC 전체에 매핑
   - 예: {entity_id_1} 결과 → TC-1.3, TC-1.4, TC-3.2에 동시 매핑

6. DERIVED 파라미터 주입 예시:
   Phase 1 실행 → Q-primary-1 결과: [{related_id_1}, {related_id_2}, {related_id_3}, {related_id_4}]
   Phase 2 실행 → Q-sec-1의 WHERE 절에 위 ID 목록 자동 주입
```

### Step 4.5: Purpose Fitness Check (행위적 조건 검증)

> **원칙**: 구조적으로 매칭된 데이터가 테스트 목적을 달성할 수 있는지 검증한다.
> "레코드가 존재하는가?"가 아니라 "이 데이터로 검증 대상 코드가 실행되는가?"를 확인한다.

#### 경로 선택

```
IF tc_spec.json 존재 AND tc_spec_data[tc_id].behavioral_condition 존재:
  → 4.5-A 실행 (JSON 직독, CoT 불필요)
ELSE:
  → 4.5-C 실행 (CoT Fallback — tc_spec.json 없는 폴백 모드)
```

#### 4.5-A: tc_spec.json 기반 검증 (기본 경로)

```
# tc_spec_data: Step 2에서 Read + JSON parse된 로컬 변수
FOR each TC where status == "MAPPED" AND tc_spec_data[tc_id].behavioral_condition exists:

  1. db_check.sql의 플레이스홀더를 매핑된 실제 데이터로 치환 (자연어 해석 없음)
     예: '{data.container_code}' → 'TT0000000026496'
     치환 소스: data_mapping.mappings[tc_id].data 객체

  2. 치환된 SQL 직접 실행
     MCP 도구: tc_spec_data[tc_id].behavioral_condition.db_check.db

  3. assert 함수로 결과 검증:
     all_eq('VALUE')  → 모든 행의 값이 VALUE와 같은지
     any_eq('VALUE')  → 하나 이상의 행이 VALUE인지
     count_gte(N)     → 행 수가 N 이상인지
     count_eq(N)      → 행 수가 정확히 N인지
     is_null          → 값이 null인지
     is_not_null      → 값이 null이 아닌지

  4. 판정:
     assert 충족 → MAPPED 유지
     assert 미충족 → status = NOT_FOUND
       reason: "behavioral_condition.db_check 미충족: {assert} 실패"
       actual: "{실제 조회된 값 목록}"
       suggestion: "Provisioning 필요: {db_check.assert 조건}을 만족하는 데이터 생성"
```

#### 4.5-B: 메타데이터 기반 검증 보강 (4.5-A 이후 추가 실행)

`$CLAUDE_PROJECT_DIR/.claude/architecture/data-contracts.json` 참조하여 검증 보강:

```
1. semanticContracts: 컬럼의 businessRule, writer/reader 관계
2. dataFlowPaths: 현재 데이터 상태가 테스트 대상 시점인지 확인
   예: step 3(배치완료) 데이터가 step 2(피킹중) 테스트에 필요한 경우 → 목적 부적합
3. nullSemantics: null 값의 비즈니스 의미 확인
```

#### 4.5-C: CoT Fallback (tc_spec.json 없는 폴백 모드에서만)

> tc_spec.json이 있으면 이 경로를 절대 실행하지 않는다.
> tc_spec.json이 없는 경우(하위 호환) 또는 마크다운 폴백 모드에서만 실행.

```
FOR each TC where status == "MAPPED" AND tc_spec_data[tc_id] 없음:
  CoT 추론:
    Q1. "이 TC가 검증하려는 코드 로직은 무엇인가?" → STIMULUS + 기대결과에서 추론
    Q2. "그 로직이 실행되려면 데이터가 어떤 상태여야 하는가?" → data-contracts.json 참조
    Q3. "현재 매핑된 데이터가 그 상태인가?" → DB 검증 쿼리로 확인
    Q4. 판정 → MAPPED 유지 또는 NOT_FOUND (사유 포함)

  추론 결과를 behavioral_check에 기록 (verdict, conditions[], method 필수)
```

#### 4.5-D: 검증 결과 기록

```
behavioral_check = {
  "verdict": "PASS | FAIL",
  "method": "tc_spec_json | cot_fallback",
  "conditions": [
    { "field": "검증 컬럼", "expected": "기대값", "actual": "실제값", "result": "PASS|FAIL" }
  ]
}
```

부적합 시 `status`를 `NOT_FOUND`로 변경하고 `reason`과 `suggestion` 기재.

### Step 5: 데이터 매핑 파일 생성

> `validate_data_mapping.py` Hook이 파일 구조를 자동 검증한다:
> - 필수 필드 (`sheet_version`, `created_at`, `mappings`) 존재
> - `completed_at` 필드 존재 (null 허용 — 진행 중 상태)
> - MAPPED 상태 TC에 `behavioral_check` (verdict/conditions/method) 필수
> - NOT_FOUND 상태 TC에 `reason` 필수
> - summary 정합성: mapped + not_found + provisioning_needed + provisioned + skipped + behavioral_mismatch + capture_planned == total_tcs
>   (behavioral_mismatch는 구조적 매칭 성공했으나 행위적 조건 미충족한 TC 카운트. 내부적으로 NOT_FOUND로 전환되나 summary 검증에서는 항목으로 포함됨)

> ℹ️ **behavioral_gate.py와의 계약**
> - 이 필드가 없어도 behavioral_gate.py는 해당 TC를 PASS 처리함 (차단 안 함)
> - 필드를 채우는 이유: 데이터 품질 보장 (매핑 완전성), Hook 강제가 아님
> - BLOCKED가 되려면 필드가 존재하고 `verdict != "PASS"` 이어야 함

```
파일: {ctx.ticket_folder}/{티켓}_데이터매핑.json

{
  "ticket": "PROJ-123",
  "sheet_version": "v2",
  "created_at": "2026-02-12",
  "completed_at": null,              // null = 매핑 진행 중 / ISO 타임스탬프 = 완료 (E-1: 부분 기록 구분)
  // ⚠️ Write 시 반드시 포함하여 단일 Write. 파일 생성 완료 전까지 null로 유지하고
  // Write 호출 직전에 now().isoformat()으로 설정. 2회 Write 금지.
  "organization_summary": {
    "primary": { "id": 1001, "name": "조직_A" },
    "additional": [{ "id": 1002, "name": "조직_B" }]
  },
  "mappings": {
    "TC-1.1": {
      "tc_name": "단일 항목 - 기본 케이스",
      "status": "MAPPED",
      "data": {
        "entity_code": "{entity_id_10}",
        "organization_id": 1001,
        "related_count": 1,
        "item_count": 1,
        "has_작업": true
      },
      "discovery_query": "SELECT ... FROM {entity_lifecycle} WHERE ...",
      "behavioral_check": { ... }  // schema: validate_data_mapping.py (verdict, conditions[], method)
    },
    "TC-4.1": {
      "tc_name": "작업 미할당 엔티티",
      "status": "NOT_FOUND",
      "reason": "모든 조직에서 작업_count=0인 데이터 없음",
      "suggestion": "API로 작업 없는 엔티티 생성 필요 (Provisioning 모드)"
    }
  },
  "summary": {
    "total_tcs": 15,
    "mapped": 11,
    "not_found": 3,
    "provisioning_needed": 1,
    "provisioned": 0,
    "behavioral_mismatch": 0,
    "skipped": 0,
    "capture_planned": 0,
    "coverage": "73%"
  }
}
```

> **completed_at 세팅**: 파일 Write 시 `completed_at`를 인라인으로 포함한다 (두 번 Write 금지).
> 단일 Write에서 completed_at = now().isoformat() 을 포함하여 원자적으로 완료 상태를 기록한다.
> ```
> # 단일 Write 패턴 (원자적 — 중단 시 null 고착 방지)
> mapping["completed_at"] = datetime.now().isoformat()  # Write 직전에 설정
> Write 데이터매핑.json  # completed_at 포함하여 단일 Write
> ```
> ※ 두 번 Write 금지: 첫 Write 후 중단 시 completed_at: null 영구 고착 → test-run Step 4 캐시 무효화 실패
>
> **Provisioning 후 completed_at 재갱신**:
> test-provisioning Step 4.5에서 데이터매핑.json을 업데이트할 때, completed_at을 now()로 재갱신해야 한다.
> (provisioning 이전 타임스탬프가 "완료" 시점으로 기록되지 않도록)
>
> test-run Step 4에서 매핑 파일 스킵 판정 시: `completed_at != null` 이어야 유효한 캐시로 인정.

### Step 6: 사용자 리포트

```
✅ 테스트 데이터 매핑 완료

매핑 결과: 11/15 TC (73%)
- MAPPED: 11개 TC (기존 데이터 발견)
- NOT_FOUND: 3개 TC (데이터 없음)
- PROVISIONING_NEEDED: 1개 TC (생성 필요)
- PROVISIONED: {summary.provisioned}건

조직 분포:
- 조직 1001: 5 TC
- 조직 1002: 3 TC
- 조직 1003: 3 TC

NOT_FOUND TC:
- TC-4.1: 작업 미할당 엔티티 → Provisioning 모드로 생성 가능
- TC-4.2: 빈 엔티티 → Provisioning 모드로 생성 가능
- TC-3.4: 극단적 비율 초과 → 데이터 부족

행위적 검증 결과:
- 구조적 매칭 후 행위적 검증 통과: N개 TC
- 행위적 조건 미충족으로 NOT_FOUND 전환: M개 TC
  - TC-X.X: {field}={actual} (required: {required}) → Provisioning 필요

생성된 파일:
- test/PROJ-123_기능명/PROJ-123_데이터매핑.json
```

---

## Provisioning 모드 (Integration)

`test-provisioning` 스킬과 연동하여 데이터를 생성합니다.

```
1. NOT_FOUND 발생
2. 사용자에게 Provisioning 제안
3. [승인 시] -> `test-provisioning` 스킬 호출
   - 입력: {티켓}_데이터매핑.json, Target TC
   - 출력: 업데이트된 데이터매핑.json
```

상세 로직은 `test-provisioning.md` 참조.

---

> ⚠️ Provisioning은 데이터 변경이 발생하므로 사용자 확인 후 실행. 상세 로직은 `test-provisioning.md` 참조.

---

## API 시퀀스 시뮬레이션 TC 데이터 매핑

`api_simulation` TC의 경우, Gate에서 추출한 API 시퀀스의 파라미터를 기반으로 데이터를 매핑한다.

- API 시퀀스의 첫 번째 API에 필요한 엔티티를 Discovery 대상으로 삼음
- 예: `GET /api/entity/v3/{code}/detail` → entity_code가 필요 → 기존 Discovery 로직과 동일
- 매핑 결과의 `channel`에 "API (시퀀스 시뮬레이션)" 표기
- `depends_on` 관계가 있는 API는 선행 API 응답에서 파라미터를 추출하므로 별도 매핑 불필요

---

## Capture Plan 모드 (향후 확장)

상태 전이 테스트에서 before/after 캡쳐 시점을 계획합니다:

```
1. TC의 상태 전이 분석 (before → action → after)
2. 캡쳐 포인트 정의:
   - before: 액션 실행 전 DB 스냅샷, UI 스크린샷
   - after: 액션 실행 후 DB 스냅샷, UI 스크린샷
3. 캡쳐 계획 파일 생성
```

---

## Output Format

### 매핑 파일

- `{ctx.ticket_folder}/{티켓}_데이터매핑.json`

### 상태값

| 상태                | 설명                                |
| ------------------- | ----------------------------------- |
| MAPPED              | DB에서 조건에 맞는 데이터 발견      |
| NOT_FOUND           | 어떤 워크플레이스에서도 데이터 없음 |
| BEHAVIORAL_MISMATCH | 구조적 매칭 성공, 행위적 조건 미충족 (NOT_FOUND로 전환됨) |
| SKIPPED             | behavioral_gate에 의해 실행 제외된 TC (구형 매핑 호환 또는 명시적 제외) |
| PROVISIONING_NEEDED | API로 생성 필요                     |
| PROVISIONED         | API로 생성 완료                     |
| CAPTURE_PLANNED     | 캡쳐 계획 수립 완료                 |

---

## Related Skills

- **test-run**: 테스트 실행 오케스트레이터 (Step 4에서 이 스킬 호출)
- **test-plan**: 테스트 계획 생성 (데이터 요구사항 포함)
- **test-provisioning**: NOT_FOUND 데이터 API 생성 (Worker)
