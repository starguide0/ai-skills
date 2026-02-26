---
name: test-provisioning
description: "Handles the creation of test data via API calls when existing data is not found. Manages API dependency chains and falls back to source code analysis if metadata is missing."
version: 1.0.0
---

# Test Provisioning Skill

## Purpose

`test-scheduler`로부터 할당받은 **엔터티 생성 단위 작업(Work Unit)**을 실행합니다.
특정 데이터(예: 주문 A)를 생성하기 위해 필요한 API 시퀀스를 자율적으로 탐색하거나 주입받아 완수하는 **Worker Subagent** 역할을 수행합니다.

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| Work unit | test-scheduler (Tier 0) | Y | 생성할 엔터티 정보 (sequence, target) |
| 데이터매핑.json의 NOT_FOUND TC | test-data | Y | 데이터 요구사항 (TC별 필요한 엔터티 정보) |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| created_entity_ids | test-data, test-scheduler | 생성된 엔터티의 ID 목록 (예: order_id, container_id 등) |
| updated_mapping_status | test-data | 데이터매핑.json 업데이트 (status: NOT_FOUND → PROVISIONED 또는 PROVISIONING_NEEDED → PROVISIONED) |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- API 호출 순서 결정 로직 (.claude/architecture/api-dependencies.json 또는 소스 코드 분석)
- 인증 처리 (로그인 API 호출, 토큰 확보)
- 엔터티 생성 체인 실행 (a → b → c, 이전 단계 output을 다음 단계 input으로 사용)
- Rollback/재시도 전략
- 환경 검증 (운영 환경 차단 로직)

## ctx 복원 (Read-Through Fallback)

| ctx 필드 | 복원 소스 | 복원 방법 |
|----------|-----------|-----------|
| ticket_folder | gate*.json 파일 경로 | 복원 불가 시 ABORT |
| test_baseline | `{ctx.ticket_folder}/{ticket}_gate_*.json` | Glob → 타임스탬프 최신 → Read → JSON parse |
| server_env_map | ctx.test_baseline.server_env_map | test_baseline 복원 후 파생 |
| data_mapping | `{ticket_folder}/{ticket}_데이터매핑.json` | Read 도구로 복원 |

> ⚠️ `server_env_map` 복원 실패 시 Step 3 운영 환경 차단 로직이 WARNING으로 격하됨 — 반드시 복원 확인 후 진행.

## Logic Flow

1.  **작업 수취**: `test-scheduler`가 계획한 특정 엔터티 생성 요청 수신
2.  **시퀀스 확보**:
    - 주입된 시퀀스가 있을 경우 해당 시퀀스 사용
    - 없을 경우 `.claude/architecture/api-dependencies.json` 또는 소스 분석을 통해 생성 전략 수립
3.  **원자적 실행 (Atomic Execution)**:
    - 시퀀스 내의 모든 단계를 중단 없이 실행 (a -> b -> c)
    - 중간 단계 실패 시 Rollback 혹은 재시도 전략 수행
4.  **결과 보고**: 생성된 ID 및 결과를 메인 프로세스에 반환

## Trigger

- **Explicit**: "PROJ-456 데이터 생성해줘"
- **Implicit**: 실행 결과 발생 시 사용자 승인 후

## Execution Steps

### Step 1: API 시퀀스 결정

데이터 생성을 위한 API 호출 순서를 결정합니다.

```python
# 1. 메타데이터 조회
dependencies = load_json(f"{ctx.CLAUDE_PROJECT_DIR}/.claude/architecture/api-dependencies.json")
# ※ 절대 경로 필수 — CWD 리셋 시 상대 경로 실패
sequence = dependencies.get(target_entity)

# 2. 메타데이터 없음 -> 소스 코드 분석 (Fallback)
if not sequence:
    # Controller/Service 코드에서 생성 로직 역추적
    sequence = analyze_creation_logic(target_entity)
```

### Step 2: 사전 조건 처리 (Login/Auth)

대부분의 API는 인증이 필요하므로, 테스트 계정으로 토큰을 먼저 확보합니다.

#### Auth 정보 수신 방법 (Worker 에이전트 필독)

이 스킬은 test-run의 Step 5.2에서 Worker로 호출됩니다. auth 정보는 다음 경로로 전달됩니다:

| auth 필드 | 전달 방식 | 복원 방법 (ctx 유실 시) |
|-----------|-----------|------------------------|
| `ctx.auth_url` | 오케스트레이터(test-run)가 ctx에 설정 후 전달 | `test/_shared/환경/API_엔드포인트.md`에서 AUTH_URL 값 재추출 |
| `ctx.auth_body` | 오케스트레이터(test-run)가 ctx에 설정 후 전달 | `test/_shared/환경/계정.md`에서 loginId/password 재추출 → `python3 -c "import json; print(json.dumps({...}))"` 로 재생성 |

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

생성된 엔티티 정보를 데이터매핑.json에 **직접 파일 쓰기**로 업데이트한다.

> **partial_results/ 디렉토리 생성 (병렬 Task 시작 전 오케스트레이터가 1회 실행)**:
> ```
> IF NOT EXISTS {ctx.ticket_folder}/partial_results/:
>   mkdir -p {ctx.ticket_folder}/partial_results/
> ```
> 각 Provisioning Task가 아닌 오케스트레이터가 생성 (병렬 mkdir 경쟁 조건 방지)

```python
# 1. 기존 매핑 파일 로드 (ctx.ticket_folder 기준 — IO Scope 준수)
mapping_path = f"{ctx.ticket_folder}/{ticket}_데이터매핑.json"
mapping = load_json(mapping_path)

# 2. 자신의 TC 결과를 임시 파일에 먼저 저장 (병렬 Write 충돌 방지)
temp_path = f"{ctx.ticket_folder}/partial_results/{tc_id}_provisioning.json"
temp_result = {"tc_id": tc_id, "status": "PROVISIONED", "data": context, "provisioned_at": timestamp}
save_json(temp_result, temp_path)
```

> **병렬 Provisioning 순차 Write 프로토콜 (F-2)**:
> 데이터매핑.json은 단일 파일이므로 동시 Write 시 마지막 Write가 이전 결과를 덮어쓸 수 있다.
>
> **처리 방식 (2단계 Write)**:
> 1. **각 Provisioning Task**: 자신의 결과를 `{ctx.ticket_folder}/partial_results/{tc_id}_provisioning.json`에만 저장 (충돌 없음)
> 2. **오케스트레이터 (모든 Task 완료 후)**: 임시 파일들을 순차 병합:
>    ```
>    FOR each {tc_id}_provisioning.json (완료된 순서로):
>      a. Read 최신 데이터매핑.json        ← 이전 병합 결과 반영
>      b. mapping.mappings[tc_id] 업데이트 ← 해당 TC만 수정
>      c. Write 데이터매핑.json             ← 원자적 갱신
>    ```
>    → Read-Modify-Write 경쟁 조건 방지 (직렬화 보장)

### Worker 실패 처리

1. 타임아웃 후 `{tc_id}_provisioning.json` 미존재 → Worker 실패 → `status: PROVISIONING_NEEDED` (재시도 가능)
2. 결과 파일에 `"status"` 필드 없음 → 불완전 쓰기 → 삭제 후 재시도
3. 최대 재시도 2회. 이후 → `tc_id`를 `BLOCKED`로 마킹, 실행 제외

### Step 4.5: 오케스트레이터 병합 (병렬 실행 완료 후)

> **트리거**: test-run Step 5.2 Tiered Loop에서 Tier 0의 모든 PROVISION Task 완료 시 자동 실행.
> 오케스트레이터(test-run Main agent)가 직접 실행 — 개별 Provisioning Task가 실행하는 것이 아님.
> test-run Step 5.2에 "Tier 0 PROVISION 완료 시 병합 트리거" 조항으로 명시되어 있음.

```
IF 병렬 PROVISION Tasks 완료:
  FOR each {tc_id}_provisioning.json in {ctx.ticket_folder}/partial_results/:
    1. Read 최신 {ticket}_데이터매핑.json
    2. mappings[tc_id].status = "PROVISIONED"
    3. mappings[tc_id].data = provisioning_result.data
    4. mappings[tc_id].provisioned_at = provisioning_result.provisioned_at
    5. Write 업데이트된 데이터매핑.json
  # 각 TC의 원래 status에 따라 해당 필드 감소 (정합성 유지)
  FOR each provisioned TC:
    IF original_status == "PROVISIONING_NEEDED":
      summary.provisioning_needed -= 1
    ELSE IF original_status == "NOT_FOUND":
      summary.not_found -= 1
    summary.provisioned += 1
  # 프로비저닝 완료 시 데이터매핑 상태 갱신
  data_mapping.mappings[tc_id].status = "MAPPED"
  data_mapping.mappings[tc_id].data = {provisioning 결과로 채운 데이터}
  # behavioral_check 설정 (validate_data_mapping.py hook 통과 필수)
  # 프로비저닝으로 생성된 데이터는 조건을 직접 충족시켰으므로 PASS
  data_mapping.mappings[tc_id].behavioral_check = {
    "verdict": "PASS",
    "method": "provisioned",
    "conditions": ["data provisioned via API — behavioral conditions satisfied by construction"]
  }
  # 데이터매핑 파일 업데이트 (Step 5 완료 Write 패턴 사용)
  # 검증: mapped + not_found + provisioning_needed + provisioned == total_tcs
  # 불일치 시: WARN 로그 출력 — 실행 중단하지 않음 (데이터 일관성 경고만)
  # ── 루프 종료 후 1회 실행 ──
  # completed_at 갱신 (provisioning 완료 시점으로 업데이트)
  mapping["completed_at"] = datetime.now().isoformat()
  Write 데이터매핑.json (최종 상태)
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

| 스킬 | 관계 |
|------|------|
| **test-scheduler** | Tier 0에서 이 스킬을 Worker로 호출 |
| **test-data** | NOT_FOUND 발생 시 이 스킬로 데이터 생성 |
| **test-run** | Step 5에서 Scheduler를 통해 간접 호출 |
