---
name: test-provisioning
description: "Handles the creation of test data via API calls when existing data is not found. Manages API dependency chains and falls back to source code analysis if metadata is missing."
---

# Test Provisioning Skill

## Purpose

`test-scheduler`로부터 할당받은 **엔터티 생성 단위 작업(Work Unit)**을 실행합니다.
특정 데이터(예: 주문 A)를 생성하기 위해 필요한 API 시퀀스를 자율적으로 탐색하거나 주입받아 완수하는 **Worker Subagent** 역할을 수행합니다.

---

## Interface Contract

### INPUT

| 필드                           | 출처                    | 필수 | 설명                                      |
| ------------------------------ | ----------------------- | ---- | ----------------------------------------- |
| Work unit                      | test-scheduler (Tier 0) | Y    | Entity creation work unit (sequence, target)     |
| data_mapping.json NOT_FOUND TC | test-data               | Y    | Data requirements (per-TC required entity info) |

### OUTPUT

| 필드                   | 소비자                    | 설명                                                                                              |
| ---------------------- | ------------------------- | ------------------------------------------------------------------------------------------------- |
| created_entity_ids     | test-data, test-scheduler | List of created entity IDs (e.g., order_id, container_id)                                         |
| updated_mapping_status | test-data                 | data_mapping.json update (status: NOT_FOUND → PROVISIONED or PROVISIONING_NEEDED → PROVISIONED) |

### INTERNAL (다른 스킬이 몰라도 되는 것)

- API 호출 순서 결정 로직 (ctx.service_metadata가 제공하는 api dependencies 또는 소스 코드 분석)
- 인증 처리 (로그인 API 호출, 토큰 확보)
- 엔터티 생성 체인 실행 (a → b → c, 이전 단계 output을 다음 단계 input으로 사용)
- Rollback/재시도 전략
- 환경 검증 (운영 환경 차단 로직)

## ctx 복원 (Read-Through Fallback)

| ctx 필드       | 복원 소스                                  | 복원 방법                                  |
| -------------- | ------------------------------------------ | ------------------------------------------ |
| ticket_folder  | gate\*.json 파일 경로                      | 복원 불가 시 ABORT                         |
| test_baseline  | `{ctx.ticket_folder}/{ticket}_gate_*.json` | Glob → 타임스탬프 최신 → Read → JSON parse |
| server_env_map | ctx.test_baseline.server_env_map           | test_baseline 복원 후 파생                 |
| data_mapping   | `{ticket_folder}/{ticket}_data_mapping.json` | Restore via Read tool                           |

> ⚠️ `server_env_map` 복원 실패 시 Step 3 운영 환경 차단 로직이 WARNING으로 격하됨 — 반드시 복원 확인 후 진행.

## Logic Flow

0.  **선행 조건**: `test-run.md` Step 4.3에서 사용자의 **고수준(High-level) 실행 승인**을 득한 후 진입.
1.  **작업 수취**: 특정 엔터티 생성 요청 수신
2.  **HitL 시퀀스 확보 (Contract Auto-Discovery)**:
    - `ctx.service_metadata` provider에서 api dependencies 조회
    - [Phase 1] 정의된 시퀀스가 없을 경우 소스 코드(Controller/DTO)를 분석하여 시퀀스 초안
    - [Phase 2] 사용자에게 초안 출력 후 승인(Y/N/Edit) 요청 (HitL Pause)
    - [Phase 3] 승인 시 `api-dependencies.json`에 영구 저장 후 실행. 거절 시 해당 건 N/T 처리 후 즉시 종료 (Fail-Fast)
3.  **원자적 실행 (Atomic Execution)**:
    - 시퀀스 내의 모든 단계를 중단 없이 실행 (a -> b -> c)
4.  **결과 보고**: 생성된 ID 및 결과를 메인 프로세스에 반환

## Trigger

- **Explicit**: "PROJ-456 데이터 생성해줘"
- **Implicit**: 실행 결과 발생 시 사용자 승인 후

## Execution Steps

### Step 1: 상태 목표 기반 API 시퀀스 결정 (Generic Provisioning)

동일한 엔티티(예: `order`)라도 TC가 요구하는 최종 상태(예: `CREATED`, `PICKING`, `RELEASED`)에 따라 필요한 API 호출 체인이 다릅니다.

```python
# 1. 목표 상태 분석 (TC 요구사항 기반)
# 단순 엔티티 종류가 아닌 "어떤 상태의 엔티티"가 필요한지 파악합니다.
target_entity = tc_requirement["entity"]
target_state = tc_requirement.get("required_state") # 예: "PICKING"

# 2. 메타데이터 기반 조회 (우선)
dependencies = load_from_service_metadata_provider(ctx.service_metadata, "api_dependencies")
# 엔티티와 특정 상태 조합으로 정의된 시퀀스가 있는지 확인 (예: "order_picking")
sequence_key = f"{target_entity}_{target_state}" if target_state else target_entity
sequence = dependencies.get(sequence_key) or dependencies.get(target_entity)

# 3. 메타데이터 없음 -> 동적 시퀀스 추론 (Generic Fallback)
if not sequence:
    # API 문서(OpenAPI), 컨트롤러/DTO 소스(Validation), DB 스키마(Entity 구조, FK, 제약조건) 및 상태 전이도(State Machine)를 모두 교차 분석하여 해당 상태에 도달하기 위한 API 호출 사슬 구성 (호출 순서 및 각 단계별 필수 데이터 페이로드 포함)
    draft_sequence = analyze_state_transition_api_chain(target_entity, target_state)
    
    # 파이프라인 일시 정지 후 사용자 컨펌 대기 (페이로드 데이터 포함)
    user_decision = prompt_user(
        f"목표 상태 '{target_state}'의 '{target_entity}' 생성 규칙이 없습니다. 다음 **API 호출 순서와 주입할 데이터(페이로드)**로 프로비저닝을 진행하시겠습니까?\n{draft_sequence}\n(Y/N/Edit): "
    )

    if user_decision == 'Y':
        save_to_json(draft_sequence, api_dependencies_path, key=sequence_key)
        sequence = draft_sequence
    elif user_decision == 'Edit':
        # 사용자가 수정한 시퀀스로 갱신
        sequence = apply_user_edit()
    else:
        # 맹목적 실행 방지 (Fail-Fast)
        mark_as_unprovisionable_and_abort()
```

### Step 2: 사전 조건 처리 (Login/Auth)

대부분의 API는 인증이 필요하므로, 테스트 계정으로 토큰을 먼저 확보합니다.

#### Auth 정보 수신 방법 (Worker 에이전트 필독)

이 스킬은 test-run의 Step 5.2에서 Worker로 호출됩니다. auth 정보는 다음 경로로 전달됩니다:

| auth 필드       | 전달 방식                                     | 복원 방법 (ctx 유실 시)                                                                                                  |
| --------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `ctx.auth_url`  | 오케스트레이터(test-run)가 ctx에 설정 후 전달 | `test/_shared/env/api_endpoints.md`에서 AUTH_URL 값 재추출                                                             |
| `ctx.auth_body` | 오케스트레이터(test-run)가 ctx에 설정 후 전달 | `test/_shared/env/accounts.md`에서 loginId/password 재추출 → `python3 -c "import json; print(json.dumps({...}))"` 로 재생성 |

> ⚠️ **보안 규칙**: `ctx.auth_body`는 파일에 저장하지 않는다. ctx에만 보관(휘발성).
> ⚠️ **ctx 유실 시**: ctx.auth_url 또는 ctx.auth_body가 없으면 위 복원 방법으로 재생성 후 진행.
> ⚠️ **auth 정보 없음**: 복원도 불가능하면 ABORT — 사용자에게 인증 정보 확인 요청.

```python
# ctx에서 auth 정보를 가져와 토큰을 발급받는다
# ctx.auth_url, ctx.auth_body 는 test-run Step 0.4에서 준비된 값을 사용
token = stimulus_executor(
    method="POST",
    url=ctx.auth_url,
    body=ctx.auth_body
)
headers = {"Authorization": f"Bearer {token}"}
```

### Step 3: API 체인 실행

#### 환경 안전 검증 (Step 3 최우선 실행)

1. ctx.server_env_map에서 현재 환경 확인:

   # 환경 안전 검증: 모든 서비스의 env 확인

   FOR each service, config in ctx.server_env_map.items():
   IF config.get("env") in ("production", "prod"):
   ERROR: "🚫 운영 환경 프로비저닝 차단 — {service}.env={config['env']}"
   → 즉시 중단 (사용자에게 ERROR 출력 후 파이프라인 종료)

2. ctx.server_env_map이 없거나 비어있거나 env 필드 확인 불가:
   WARNING: "환경 정보 없음 — 프로비저닝 진행 전 사용자 확인 필요"
   → 사용자에게 현재 환경 확인 요청 후 진행

```python
# 예: 주문 생성 (Order -> Job -> Container)
context = {}
for step in sequence:
    # 이전 단계의 output을 입력으로 사용
    payload = build_payload(step, context)
    response = call_api(step.method, step.url, payload, headers)

    # 결과 저장 (ID 등)
    context[step.output_key] = response[step.output_key]
```

### Step 4: 매핑 파일 업데이트

생성된 엔티티 정보를 data_mapping.json에 **직접 파일 쓰기**로 업데이트한다.

> **partial_results/ 디렉토리 생성 (병렬 Task 시작 전 오케스트레이터가 1회 실행)**:
>
> ```
> IF NOT EXISTS {ctx.ticket_folder}/partial_results/:
>   mkdir -p {ctx.ticket_folder}/partial_results/
> ```
>
> 각 Provisioning Task가 아닌 오케스트레이터가 생성 (병렬 mkdir 경쟁 조건 방지)

```python
# 1. 기존 매핑 파일 로드 (ctx.ticket_folder 기준 — IO Scope 준수)
mapping_path = f"{ctx.ticket_folder}/{ticket}_data_mapping.json"
mapping = load_json(mapping_path)

# 2. 자신의 TC 결과를 임시 파일에 먼저 저장 (병렬 Write 충돌 방지)
temp_path = f"{ctx.ticket_folder}/partial_results/{tc_id}_provisioning.json"
temp_result = {"tc_id": tc_id, "status": "PROVISIONED", "data": context, "provisioned_at": timestamp}
save_json(temp_result, temp_path)
```

> **병렬 Provisioning 순차 Write 프로토콜 (F-2)**:
> data_mapping.json은 단일 파일이므로 동시 Write 시 마지막 Write가 이전 결과를 덮어쓸 수 있다.
>
> **처리 방식 (2단계 Write)**:
>
> 1. **각 Provisioning Task**: 자신의 결과를 `{ctx.ticket_folder}/partial_results/{tc_id}_provisioning.json`에만 저장 (충돌 없음)
> 2. **오케스트레이터 (모든 Task 완료 후)**: 임시 파일들을 순차 병합:
>    ```
>    FOR each {tc_id}_provisioning.json (완료된 순서로):
>      a. Read 최신 data_mapping.json        ← 이전 병합 결과 반영
>      b. mapping.mappings[tc_id] 업데이트 ← 해당 TC만 수정
>      c. Write data_mapping.json             ← 원자적 갱신
>    ```
>    → Read-Modify-Write 경쟁 조건 방지 (직렬화 보장)

### Worker 실패 처리

1. 타임아웃 후 `{tc_id}_provisioning.json` 미존재 → Worker 실패 → `status: PROVISIONING_NEEDED` (재시도 가능)
2. 결과 파일에 `"status"` 필드 없음 → 불완전 쓰기 → 삭제 후 재시도
3. 최대 재시도 2회. 이후 → `tc_id`를 `BLOCKED`로 마킹, 실행 제외

### Step 4.5: 오케스트레이터 병합 (병렬 실행 완료 후)

> **Task 실패/타임아웃 처리:**
> - 각 Worker Task는 최대 5분 대기
> - 타임아웃 시: 해당 TC를 `PROVISIONING_FAILED` 상태로 마킹하고 계속 진행
> - 부분 결과 파일(`{tc_id}_provisioning_partial.json`) 정리 책임: **오케스트레이터(Lead)**
> - 전체 실패율 > 50% 시 사용자에게 중단 여부 확인

> **트리거**: test-run Step 5.2 Tiered Loop에서 Tier 0의 모든 PROVISION Task 완료 시 자동 실행.
> 오케스트레이터(test-run Main agent)가 직접 실행 — 개별 Provisioning Task가 실행하는 것이 아님.
> test-run Step 5.2에 "Tier 0 PROVISION 완료 시 병합 트리거" 조항으로 명시되어 있음.

```
IF 병렬 PROVISION Tasks 완료:
  FOR each {tc_id}_provisioning.json in {ctx.ticket_folder}/partial_results/:
    1. Read 최신 {ticket}_data_mapping.json
    2. mappings[tc_id].data = provisioning_result.data
    3. mappings[tc_id].provisioned_at = provisioning_result.provisioned_at
    4. [사후 검증] tc_spec.json의 behavioral_condition.db_check.sql 실행 (오케스트레이터 직접 수행)
       - 통과 시: mappings[tc_id].status = "MAPPED", behavioral_check.verdict = "PASS", method = "provisioned_and_verified"
       - 실패 시: mappings[tc_id].status = "BLOCKED", behavioral_check.verdict = "FAIL", conditions = ["검증 실패 로그"]
    5. Write data_mapping.json (Read-Modify-Write 직렬화)

  # 각 TC의 원래 status에 따라 해당 필드 감소 (정합성 유지)
  FOR each provisioned TC (status == "MAPPED" or "BLOCKED"):
    IF original_status == "PROVISIONING_NEEDED":
      summary.provisioning_needed -= 1
    ELSE IF original_status == "NOT_FOUND":
      summary.not_found -= 1

    IF status == "MAPPED":
      summary.mapped += 1
      summary.provisioned += 1   # Provisioning 경로로 완료된 TC 추적
    ELSE:
      summary.blocked += 1

  # 데이터매핑 파일 업데이트 완료
  # 검증: mapped + not_found + provisioning_needed + provisioned + skipped + behavioral_mismatch + capture_planned + blocked == total_tcs
  # 불일치 시: WARN 로그 출력 — 실행 중단하지 않음 (데이터 일관성 경고만)

  # ── 루프 종료 후 1회 실행 ──
  mapping["completed_at"] = datetime.now().isoformat()
  Write data_mapping.json (최종 상태)
```

## Configuration (api-dependencies.json)

- 이 파일이 없으면 소스 코드 분석 모드로 작동합니다.
- 자주 사용하는 엔터티 생성 패턴(예: 주요 데이터 생성 체인)은 이 파일에 정의하는 것을 권장합니다.
- 권한 문제로 파일 생성 실패 시, 수동 생성 필요.

```json
{
  "order": [
    { "action": "login", "output": "token" },
    {
      "action": "create_order_master",
      "input": ["token"],
      "output": "order_id"
    },
    { "action": "approve_order", "input": ["token", "order_id"] }
  ]
}
```

## Safety Rules

1.  **No Direct DB Insert**: 반드시 애플리케이션 API를 경유할 것.
2.  **User Confirmation**: 대량 데이터 생성이나 파괴적 작업 전 사용자 승인 필수.
3.  **Environment Check**: 운영(Production) 환경에서는 실행 불가 (코드 레벨 차단).

---

## Related Skills

| 스킬               | 관계                                    |
| ------------------ | --------------------------------------- |
| **test-scheduler** | Tier 0에서 이 스킬을 Worker로 호출      |
| **test-data**      | NOT_FOUND 발생 시 이 스킬로 데이터 생성 |
| **test-run**       | Step 5에서 Scheduler를 통해 간접 호출   |
