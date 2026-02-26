---
name: test-scheduler
description: "Analyzes test scenarios to determine execution order and parallelism. Builds dependency graphs and creates execution batches."
version: 1.1.0
---

# Test Scheduler Skill

## Purpose

테스트시트를 분석하여 **병렬 실행 가능한 시나리오 그룹(Batch)** 을 구성합니다. 데이터 간섭(Data Interference)을 방지하고 실행 속도를 최적화합니다.

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| ctx.sheet | test-plan | Y | 테스트시트 절대 경로 — 시나리오 의존성 추출 |
| ctx.data_mapping | test-data | Y | 데이터매핑.json 절대 경로 — TC별 매핑 상태 |
| 행위적 조건 (in data_mapping) | test-data | N | 데이터매핑.json 내 TC별 behavioral_check — Pre-flight 검증에 사용 |
| {ticket}_tc_spec.json | test-plan | 조건부 | TC별 행위 조건 JSON — Pre-flight에서 db_check.sql 직접 실행 (마크다운 파싱 대체). 없으면 data_mapping의 behavioral_check 폴백 사용 |
| ctx.tc_spec | test-run (Step 3) | 조건부 | tc_spec.json 절대 경로. 없으면 Glob으로 복원 |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| test_execution_plan.json (DAG) | test-run (Step 5.1, 5.2) | 실행 계획 파일 ({ctx.ticket_folder}/{티켓}_execution_plan.json) |
| ctx.execution_plan | test-run (Step 5.2) | 실행 계획 파일 경로 (JSON 로드하여 사용) |
| execution_plan[].tier | test-run (Step 5.2) | Tiered Loop 레벨 (0부터 시작) |
| execution_plan[].parallel_tasks | test-run (Step 5.2) | 동일 Tier 내 병렬 실행 가능한 Task 목록 |
| execution_plan[].parallel_tasks[].id | test-run (Step 5.2) | Task 식별자 (예: PROV_A, RUN_TC_001) |
| execution_plan[].parallel_tasks[].type | test-run (Step 5.2) | PROVISION / TEST — 실행 타입 |
| execution_plan[].parallel_tasks[].depends_on | test-run (Step 5.2) | 이 Task가 의존하는 선행 Task ID 목록 |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- DAG(Directed Acyclic Graph) 알고리즘 (Node: 엔티티, Edge: 의존성)
- Tier 배정 로직 (진입 차수 0인 노드 → 현재 Tier, 노드 제거 → 다음 Tier)
- Batching 규칙 (동일 Tier 내 시나리오 그룹화)
- Atomic Sequence (엔티티 생성 내부 단계는 단일 Worker가 원자적 처리)
- Strict Join (depends_on 전체 SUCCESS 필요)
- Recursive Spawning (동일 엔티티 n개 생성 → n개 독립 노드)
- get_api_dependencies() 로직 (API 호출 체인 분석)
- Branch Independence (다른 Parent → 병렬 실행)

---

## ctx 복원 (Read-Through Fallback)

> 각 입력 필드가 ctx에 없으면 파일에서 복원한다:

| ctx 필드 | 복원 소스 | 복원 방법 |
|----------|-----------|-----------|
| sheet | `{ctx.ticket_folder}/{ticket}_테스트시트_v*.md` | Glob → 최고 버전 선택 |
| data_mapping | `{ctx.ticket_folder}/{ticket}_데이터매핑.json` | Read → JSON parse |
| server_env_map | ctx.test_baseline.server_env_map에서 파생 | test_baseline 복원 후 → ctx.server_env_map = ctx.test_baseline.server_env_map |

> - 파일도 없으면 → ERROR: "선행 Step(Plan/Data) 미완료" → 파이프라인 중단

---

## Logic Flow

0.  **Pre-flight 검증**: MAPPED TC의 behavioral_check 조건을 DB 재조회로 검증. stale 데이터 발견 시 사용자 선택.
1.  **의존성 추출**: 테스트시트 및 아키텍처 메타데이터에서 엔터티 간 생성 순서(Prerequisites) 파악
2.  **DAG 구성**: TC 간 의존성 분석으로 DAG 구성
3.  **Tier 배정**: DAG에서 병렬 실행 가능한 Tier 그룹 구성
4.  **Batching**: 동일 Tier 내 시나리오들을 Batch로 그룹화

---

## Execution Steps

### Step 0.5: Pre-flight State Validation (실행 전 상태 검증)

> **목적**: 데이터 매핑 시점과 실행 시점 사이에 데이터 상태가 변경(stale)될 수 있으므로,
> 실행 직전에 행위적 조건을 재검증한다. 이 단계는 stale 데이터와 목적 부적합 데이터의 최종 안전망이다.
>
> **tc_spec.json 기반 검증**: `behavioral_condition.db_check.sql`을 직접 실행한다.
> 마크다운 파싱 없이 JSON 필드를 그대로 쿼리로 사용한다.

#### ctx 복원

```
IF ctx.tc_spec 없으면 → Glob `{ctx.ticket_folder}/{ticket}_tc_spec.json`  # ticket_folder 포함 (CWD 독립)
                  → 발견 시: Read → JSON parse → ctx.tc_spec 복원
파일도 없으면 → behavioral_check(data_mapping 내부) 기반 폴백
             → NOTE: REUSE 모드 또는 이전 버전 실행인 경우 정상

IF ctx.behavioral_gate 없으면 → Glob `{ctx.ticket_folder}/{ticket}_behavioral_gate.json`
                             → 발견 시: Read → JSON parse → ctx.behavioral_gate 복원 (B-2: 중복 SQL 실행 방지)
                             → 없으면: null (Pre-flight가 전체 실행)
```

#### 검증 실행

```
1. tc_spec.json 로드:
   IF ctx.tc_spec 존재:
     tc_spec_raw = Read(ctx.tc_spec)
     tc_spec_data = JSON.parse(tc_spec_raw)  # dict
   ELSE:
     tc_spec_data = null  # behavioral_check 폴백 사용

1.5 behavioral_gate.json 기존 결과 재사용 (B-2: 중복 SQL 실행 방지):
   IF ctx.behavioral_gate 존재:
     blocked_tcs = set()   # BLOCKED TC (SQL 재실행 스킵)
     FOR each result in ctx.behavioral_gate.results:
       IF result.gate == "BLOCKED":
         → execution_plan에서 tc_id BLOCKED 마킹 (SQL 재실행 없이 확정)
         blocked_tcs.add(result.tc_id)
       IF result.gate == "PASS" OR result.gate == "NEEDS_CONFIRMATION":
         # PASS/NEEDS_CONFIRMATION TC도 stale 체크 대상
         # (behavioral_gate 판정 이후 데이터 상태가 변경될 수 있으므로)
         IF result.gate == "NEEDS_CONFIRMATION":
           → 사용자 확인 목록에 추가
   ELSE:
     blocked_tcs = set()   # behavioral_gate.json 없음 → 모든 TC를 새로 검증

2. FOR each tc_id where data_mapping.status IN ["MAPPED", "PROVISIONED"] AND tc_id NOT IN blocked_tcs:
   # ※ blocked_tcs에 있는 TC는 이미 BLOCKED 확정 — SQL 재실행 스킵

   IF tc_spec_data.get("tcs", {}).get(tc_id, {}).get("behavioral_condition", {}).get("db_check") 존재:
     # ※ tc_spec.json 구조: {"tcs": {"TC-1": {"behavioral_condition": {...}}}}
     a. db_check.sql의 플레이스홀더를 data_mapping.mappings[tc_id].data로 치환
        예: '{data.container_code}' → 'TT0000000026496'

     b. 치환된 SQL 직접 실행 (MCP: db_check.db)

     c. db_check.assert 함수로 검증 (test-data Step 4.5-A와 동일 함수셋):
        - all_eq('VALUE')  → 모든 행의 값이 VALUE와 같은지
        - any_eq('VALUE')  → 하나 이상의 행이 VALUE인지
        - count_gte(N)     → 행 수가 N 이상인지
        - count_eq(N)      → 행 수가 정확히 N인지
        - is_null          → 값이 null인지
        - is_not_null      → 값이 null이 아닌지

     d. assert 실패 → stale_tcs에 추가
        { tc_id, field: db_check.sql, mapped_value: 기대값, current_value: 실제값 }

   ELSE IF data_mapping.mappings[tc_id].behavioral_check 존재 (폴백):
     → behavioral_check.conditions의 각 항목을 DB 재조회로 검증
     → 불일치 시 stale_tcs에 추가

   ELSE:
     → 검증 스킵 (behavioral_condition 없는 TC)

3. 검증 최적화:
   - 동일 tc_spec.db (MCP 도구)를 사용하는 쿼리는 배치로 병합 (WHERE IN)
   - Pre-flight는 Tier 0 실행 전 1회만 수행
```

#### Stale 데이터 감지 시 처리

```
IF stale_tcs가 비어있지 않음:
  1. WARNING 출력:
     "⚠️ Pre-flight 검증 실패: {N}개 TC의 데이터 상태 변경 감지"
     - TC-X: {db_check.sql 요약} 실패 — 기대: {assert}, 실제: {current_value}

  2. 사용자 선택지:
     a) 실행 계속 (현재 상태로 진행, FAIL 가능성 인지)
     b) 해당 TC 스킵 (N/T 처리)
     c) 재매핑 (test-data Step 4 재실행)
     d) Provisioning (새 데이터 생성)

  3. 사용자 선택에 따라 execution_plan 수정

#### NEEDS_CONFIRMATION 사용자 확인 처리

```
IF 사용자 확인 목록에 NEEDS_CONFIRMATION TC 존재:
  사용자에게 확인 요청:
  "다음 TC는 behavioral_check 없이 매핑되었습니다. 데이터 적합성을 직접 확인해주세요:
   {NEEDS_CONFIRMATION TC 목록 + reason}"

  사용자 응답에 따라:
  a) "확인됨 — 진행" → execution_plan에 해당 TC 포함 (PASS로 간주)
  b) "스킵" → execution_plan에서 해당 TC 제외 (N/T 처리)
  c) "재매핑" → test-data Step 4 재실행 후 scheduler 재시작
```

IF 검증 실패 TC가 전체의 50% 이상:
  → 전체 재매핑 제안
```

### Step 1: 의존성 트리 생성

시나리오별 required_data를 기반으로 엔터티 간 선후 관계를 파악하여 DAG를 구성한다.
엔터티 생성 전제조건(Prerequisites)은 get_api_dependencies()로 탐색한다.

### Step 2: Tier 기반 스케줄링

진입 차수(In-degree)가 0인 노드를 현재 Tier에 배정하고, 처리 후 제거하며 다음 Tier로 이동한다.
순환 의존성 감지 시 CycleDetectedError 발생 후 사용자에게 의존성 그래프 출력 및 중단.

### Step 3: Tier 배정

> Logic Flow 참조. 진입 차수(In-degree) 0인 노드를 현재 Tier에 배정 후 제거하며 반복.
> 순환 의존성 감지 시 CycleDetectedError 발생 → 사용자에게 의존성 그래프 출력 후 중단.

### Step 4: Batching

> Logic Flow 참조. 동일 Tier 내 시나리오를 Batch로 그룹화.
> 결과를 `execution_plan[].parallel_tasks`로 구성하여 OUTPUT 산출.

---

## Rules for Parallelism

1.  **Branch Independence**: 서로 다른 Parent를 가진 브랜치들은 항상 병렬로 실행합니다.
2.  **Atomic Sequence**: 엔터티 하나를 만드는 내부 단계(a-b-c)는 하나의 Worker(Subagent)가 원자적으로 처리합니다.
3.  **Strict Join**: `depends_on`에 명시된 모든 Task가 `SUCCESS`여야 다음 Tier를 시작합니다.
4.  **Recursive Spawning**: 동일 엔터티 n개 생성 요청 시, n개의 독립 노드를 생성하여 병렬 처리 효율을 높입니다.
