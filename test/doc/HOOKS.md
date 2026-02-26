# Test Skill 훅 시스템 (Hooks)

> 최종 업데이트: 2026-02-22 | Test Skill v6.4

Claude Code 훅은 특정 도구 실행 이벤트에 자동으로 호출되는 Python 스크립트입니다.
Test Skill은 산출물 품질을 강제하기 위해 **5개 PreToolUse 훅**과 **2개 PostToolUse 훅**을 운영합니다.

---

## 1. 훅 시스템 개요

### 유형별 차이

| 유형 | 실행 시점 | 가능한 결과 | 역할 |
|------|----------|-----------|------|
| **PreToolUse** | 도구 실행 **전** | `deny` 차단 또는 허용 | 품질 게이트 |
| **PostToolUse** | 도구 실행 **후** | `message` 주입 또는 무시 | 정보 리마인드 |

### 실행 흐름

```
Claude 도구 호출 결정
        ↓
 PreToolUse 훅 병렬 실행
        ↓
 deny 응답 있으면 → 도구 실행 차단 + 이유 출력
 deny 없으면     → 도구 실행 허용
        ↓
 도구 실행
        ↓
 PostToolUse 훅 병렬 실행
        ↓
 message 있으면 → Claude 컨텍스트에 주의사항 주입
```

### 훅 I/O 형식

훅은 **stdin**으로 JSON 입력을 받고, **stdout**으로 결과를 출력합니다.

**stdin 입력:**
```json
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/path/to/file.md",
    "content": "..."
  },
  "tool_result": "..."
}
```

**PreToolUse deny 출력:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "위반 이유 상세 설명"
  }
}
```

**PostToolUse 메시지 출력:**
```json
{
  "hookSpecificOutput": {
    "message": "리마인드 메시지 내용"
  }
}
```

아무 출력 없이 `sys.exit(0)` → 허용/무시.

> ⚠️ **PreToolUse 훅 deny는 항상 exit(0)**
> Claude Code PreToolUse 훅은 차단 시 JSON `{"permissionDecision": "deny", ...}`를 stdout에 출력한 후 `exit(0)`을 호출한다.
> `exit(1)`은 훅 자체의 실행 오류(파일 없음, 파싱 실패 등)에만 사용된다.

---

## 2. 훅 설정 파일 (settings.local.json)

`.claude/settings.local.json`의 `hooks` 섹션에 등록됩니다:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/test/tools/훅이름.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [...]
  }
}
```

### matcher 동작 방식

| matcher 값 | 트리거 조건 |
|-----------|-----------|
| `"Write"` | Write 도구 호출 시 |
| `"Edit"` | Edit 도구 호출 시 |
| `"Bash"` | 모든 Bash 명령 실행 |
| `"mcp__postgres_outbound__query"` | 해당 MCP 도구 호출 시 |
| `"Task"` | Task(서브에이전트) 완료 시 |

**중요**: matcher가 사전 필터링하므로 훅 내부에서 `tool_name`은 matcher와 동일합니다.
`startswith()` 같은 추가 필터링이 필요하지 않습니다.

---

## 3. PreToolUse 훅 (차단 게이트)

모두 Write/Edit 도구에 적용되며, 파일 경로 패턴으로 대상 파일을 선택합니다.

### 3.1 validate_test_result.py

**대상**: `_테스트결과_` 포함 파일

**목적**: 테스트 결과 파일에 실제 실행 증거(STIMULUS)와 올바른 근거 포맷이 있는지 강제

**검증 항목:**

| 검사 | 조건 | deny 조건 |
|------|------|----------|
| STIMULUS 증거 (텍스트) | HTTP 메서드+URL, stimulus_executor 참조, HTTP 상태코드 | 텍스트 증거 없음 |
| STIMULUS 증거 (파일) | `partial_results/{TC_ID}_stimulus.json` 존재 | 텍스트는 있으나 파일 없음 |
| Pass TC 포맷 | 검증 결과 diff 테이블 (`\| 검증 항목 \|`) | 테이블 없음 |
| Fail TC 포맷 | `[Fail 근거]` 섹션 + 기대:/실제: 키워드 쌍 | 하나라도 없음 |

**예외 (검증 스킵):**
- `[관찰]` 태그 포함 → OBSERVATION TC (자동화 불가)
- `INCOMPLETE` 텍스트 포함 → 정직한 미완료 허용

**STIMULUS 텍스트 인식 패턴:**
```
[✅] 3. STIMULUS              ← 7-step 체크리스트 형식
POST https://api.../endpoint  ← HTTP 메서드 + URL
→ HTTP 200                    ← 응답 상태코드
stimulus_executor 참조         ← 실행 도구 언급
```

---

### 3.2 validate_test_sheet.py

**대상**: `_테스트시트_` 포함 파일

**목적**: 테스트시트가 표준 섹션 구조와 TC 형식을 준수하는지 강제

**검증 항목:**

| 검사 | deny 조건 |
|------|----------|
| `## 0. Test Baseline` 섹션 | 없으면 deny |
| `### 0.1` ~ `### 0.7` 하위 섹션 | 하나라도 없으면 deny |
| 각 TC의 `선정 이유` 필드 | 없거나 빈 값이면 deny |
| 각 TC의 `행위적 조건` 필드 | 존재하지 않으면 deny |
| N/A 행위적 조건 적합성 | 도출 트리에 ②③ 레이어가 있으면 N/A 불가 |
| 기대값 도출 트리 | `├─①` 또는 `④ 기대결과` 패턴 없으면 deny |
| ACTIVE TC STIMULUS 블록 | `━━━ STIMULUS ━━━` 없으면 deny |

> ⚠️ **ACTIVE 마커 테이블 없으면 전체 TC가 ACTIVE 간주**
> `| TC-xxx | ... | ACTIVE |` 패턴의 마커 테이블이 단 하나도 없으면,
> 파일 내 모든 TC를 ACTIVE로 간주하여 STIMULUS 블록을 요구한다.

---

### 3.3 validate_data_mapping.py

**대상**: `_데이터매핑.json` 포함 파일

**목적**: 데이터 매핑 파일의 스키마 유효성과 수치 정합성 강제

**검증 항목:**

| 검사 | deny 조건 |
|------|----------|
| JSON 파싱 | 유효하지 않은 JSON |
| 최상위 필수 필드 | `sheet_version`, `created_at`, `mappings` 중 하나라도 없음 |
| `mappings` 타입 | dict가 아닌 경우 |
| MAPPED TC | `behavioral_check` + `verdict`, `conditions`, `method` 없음 |
| NOT_FOUND TC | `reason` 필드 없음 |
| summary 정합성 | `mapped + not_found + provisioning_needed + provisioned + skipped + behavioral_mismatch == total_tcs` |

**정상 데이터매핑.json 구조:**
```json
{
  "sheet_version": "v1",
  "created_at": "2026-02-22",
  "mappings": {
    "TC-1.1": {
      "status": "MAPPED",
      "data": { "entity_code": "ENT-00001" },
      "behavioral_check": {
        "verdict": "PASS",
        "conditions": ["outbound_order.state = READY"],
        "method": "DB 직접 조회"
      }
    },
    "TC-1.2": {
      "status": "NOT_FOUND",
      "reason": "해당 상태의 주문이 존재하지 않음"
    }
  },
  "summary": {
    "total_tcs": 2,
    "mapped": 1,
    "not_found": 1,
    "provisioning_needed": 0,
    "provisioned": 0
  }
}
```

---

### 3.4 behavioral_gate.py (Dual-Mode)

**대상**: `partial_results/TC-*.json` 파일

**목적**: TC 결과 저장 전, 테스트 데이터의 사전조건(behavioral_check)이 PASS인지 확인

이 훅은 **Hook Mode**(훅으로 자동 실행)와 **CLI Mode**(수동 실행) 두 가지로 동작합니다.

#### Hook Mode

```
TC-N.json 저장 시도
        ↓
partial_results/ 부모 디렉터리에서 *_데이터매핑.json 탐색
        ↓
해당 TC의 behavioral_check.verdict 확인
        ↓
PASS → 저장 허용
비PASS → deny + "데이터 매핑의 behavioral_check를 수정하세요" 출력
```

`behavioral_check` 필드가 없는 TC(구형 매핑 호환)는 통과합니다.

#### CLI Mode

전체 매핑 파일을 일괄 검사하여 결과를 JSON으로 출력합니다:

```bash
python3 behavioral_gate.py \
  --mapping ARG-XXXXX_데이터매핑.json \
  --output ARG-XXXXX_behavioral_gate.json
```

출력 예시:
```json
{
  "gate_passed": false,
  "results": [
    { "tc_id": "TC-1.1", "gate": "PASS", "reason": "behavioral_check.verdict=PASS" },
    { "tc_id": "TC-2.1", "gate": "BLOCKED", "reason": "behavioral_check.verdict=FAIL: 상태 불일치" }
  ],
  "summary": { "pass": 1, "blocked": 1, "needs_confirmation": 0 }
}
```

---

## 4. PostToolUse 훅 (정보 제공)

deny가 아닌 메시지 주입만 수행합니다. 실행 흐름을 차단하지 않습니다.

### 4.1 remind_caution.py (A-1 신규)

**트리거:**
- Bash 실행 후 → `stimulus_executor` 또는 `curl` 명령 포함 시
- MCP PostgreSQL 도구 후 → 5개 DB 전체 (outbound/inbound/inventory/job/metadata)

**목적**: DB 쿼리나 API 호출 직후, 자주 발생하는 관련 실수를 `_caution_common_errors.md`에서 자동 검색하여 리마인드

**배경**: Step 0에서 caution 파일을 1회 로드하지만, 긴 파이프라인 실행 중 컨텍스트 윈도우에서 밀려날 수 있음. PostToolUse 훅으로 실행 직후 관련 부분만 재주입.

**동작 흐름:**

```
MCP postgres 도구 실행
        ↓
SQL 내용 분석 → 키워드 추출
  JOIN 있음     → join, inner_join / left_join
  IS NULL 있음  → null, is_null
  state/status  → state, enum
  timestamp     → timestamp
  LIMIT 없음    → limit
  서비스명      → cross_service, {service}
        ↓
_caution_common_errors.md의 <!-- keywords: ... --> 태그와 매칭
        ↓
관련 섹션 제목 리스트 → 리마인드 메시지 출력
```

**caution 파일 키워드 태그 형식:**
```markdown
<!-- keywords: mcp_postgres, join, null -->
## 패턴 1: INNER JOIN 누락 시 데이터 누락
...

<!-- keywords: state, enum -->
## 패턴 5: 상태(state) 컬럼 비교 시 ENUM 타입 주의
...
```

**출력 예시:**
```
[Caution Remind] 관련 주의사항 (cross_service, join, mcp_postgres, null, query):
  - 패턴 1: INNER JOIN 누락 시 데이터 누락
  - 패턴 5: 상태(state) 컬럼 비교 시 ENUM 타입 주의
상세 내용: .claude/skills/test/_rules/_caution_common_errors.md 참조
```

---

### 4.2 agent_report_validator.py

**트리거**: Task 도구 완료 후 (서브에이전트 반환)

**목적**: Worker 에이전트가 `harness-agent-report-v1` 스키마로 보고서를 반환했을 때 구조 검증

**동작**: Task 결과에서 `"$schema": "harness-agent-report-v1"` 포함 JSON 추출 시도 → 없으면 무시

**검증 항목:**

| 필드 누락 시 | 경고 메시지 |
|------------|-----------|
| `task_summary` | "작업 요약(task_summary)이 누락되었습니다" |
| `findings` | "구체적 발견사항(findings)을 보고하지 않았습니다" |
| `decisions` | "판단 근거(decisions)가 누락되었습니다" |
| `verification.result == "fail"` | "Worker 검증이 실패(fail)했습니다 — 확인 필요" |
| `verification.result == "partial"` | "Worker 검증이 부분적(partial)입니다" |

**보고서 스키마:**
```json
{
  "$schema": "harness-agent-report-v1",
  "agent_role": "implementer | reviewer | tester | researcher",
  "task_summary": "무엇을 했는가 (1줄)",
  "findings": [
    { "type": "change | issue | observation", "description": "..." }
  ],
  "decisions": [
    { "decision": "판단 내용", "reason": "이유" }
  ],
  "verification": {
    "method": "어떻게 검증했는가",
    "result": "pass | fail | partial",
    "evidence": "증거"
  }
}
```

---

## 5. 현재 등록된 전체 훅 (settings.local.json)

```
PreToolUse:
  Write  → validate_test_result.py   (10s)  ← 결과 파일 STIMULUS + 포맷 검증
         → validate_test_sheet.py    (10s)  ← 시트 구조 검증
         → validate_data_mapping.py  (10s)  ← 데이터매핑 JSON 검증
         → behavioral_gate.py        (10s)  ← TC 사전조건 검증
         → quality_gate.py           ( 5s)  ← 보안/임포트 검증 (dev-harness)

  Edit   → (위와 동일 5개)

PostToolUse:
  Bash                          → remind_caution.py       (5s)  ← API 호출 후 리마인드
  mcp__postgres_outbound__query → remind_caution.py       (5s)  ← DB 쿼리 후 리마인드
  mcp__postgres_inbound__query  → remind_caution.py       (5s)
  mcp__postgres_inventory__query→ remind_caution.py       (5s)
  mcp__postgres_job__query      → remind_caution.py       (5s)
  mcp__postgres_metadata__query → remind_caution.py       (5s)
  Task                          → agent_report_validator.py (5s) ← Worker 보고서 검증 (dev-harness)
```

---

## 6. 훅 동작 검증 방법

### 직접 테스트 (stdin 주입)

```bash
# validate_test_sheet.py 테스트 — Section 0 없는 빈 파일로 deny 발생 확인
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/WO-99_테스트시트_v1.md","content":"# 빈 파일"}}' | \
  python3 .claude/skills/test/tools/validate_test_sheet.py

# validate_data_mapping.py 테스트 — 필수 필드 누락으로 deny 발생 확인
echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/WO-99_데이터매핑.json","content":"{}"}}' | \
  python3 .claude/skills/test/tools/validate_data_mapping.py

# remind_caution.py 테스트 — MCP 도구 시뮬레이션
echo '{"tool_name":"mcp__postgres_outbound__query","tool_input":{"sql":"SELECT a.id, b.name FROM outbound_order a JOIN outbound_batch b ON a.id = b.id WHERE a.state IS NULL"}}' | \
  python3 .claude/skills/test/tools/remind_caution.py
```

### behavioral_gate.py CLI 모드 테스트

```bash
python3 .claude/skills/test/tools/behavioral_gate.py \
  --mapping test/WO-55_작업자할당/WO-55_데이터매핑.json
```

---

## 7. 훅 추가/수정 방법

### 새 PreToolUse 훅 추가

1. `.claude/skills/test/tools/새_훅.py` 작성:
   ```python
   #!/usr/bin/env python3
   import json, sys

   def main():
       raw = sys.stdin.read()
       try:
           hook_input = json.loads(raw)
       except json.JSONDecodeError:
           sys.exit(0)

       tool_input = hook_input.get("tool_input", {})
       file_path = tool_input.get("file_path", "")

       # 대상 파일 필터링
       if "_대상패턴_" not in file_path:
           sys.exit(0)

       # 검증 로직
       violation = False  # 실제 검증 구현

       if violation:
           output = {"hookSpecificOutput": {
               "hookEventName": "PreToolUse",
               "permissionDecision": "deny",
               "permissionDecisionReason": "위반 이유"
           }}
           print(json.dumps(output, ensure_ascii=False))
       sys.exit(0)

   if __name__ == "__main__":
       main()
   ```

2. `.claude/settings.local.json`에 등록:
   ```json
   {
     "matcher": "Write",
     "hooks": [
       {
         "type": "command",
         "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/test/tools/새_훅.py\"",
         "timeout": 10
       }
     ]
   }
   ```

### remind_caution.py 주의사항 추가

`.claude/skills/test/_rules/_caution_common_errors.md`에 키워드 태그 추가:
```markdown
<!-- keywords: 새키워드, 추가키워드 -->
## 새 주의사항 제목
내용 설명...
```

키워드는 소문자, 쉼표 구분. `_caution_common_errors.md`를 수정하는 것만으로
remind_caution.py가 자동으로 인식합니다 (재시작 불필요).
