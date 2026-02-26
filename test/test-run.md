---
name: test-run
description: "Single orchestrator that coordinates the entire test lifecycle: Gate (incl. server connectivity) → Plan → Data → Schedule → Execute (API + DB + UI) → Report. All test requests route through this skill."
version: 4.7.0
---

# Test Run Orchestrator

> **PreToolUse Hook 활성화됨**: ACTIVE TC에 STIMULUS 증거 없이 테스트 결과 파일을 Write하면 Hook이 DENY합니다. STIMULUS 미실행 시 반드시 INCOMPLETE로 표기하세요. (`validate_test_result.py`)

> ⚠️ **Hook DENY 메커니즘**
> - Hook deny = `exit(0)` + stdout에 `{"permissionDecision": "deny", ...}` JSON 출력
> - `exit(1)`은 Hook 자체 오류(파일 없음, 파싱 실패)에만 사용됨
> - DENY 발생 시 Claude Code가 도구 실행을 자동 차단 — LLM은 stderr/stdout 메시지를 읽고 원인 파악 후 수정

## Purpose

테스트의 전체 라이프사이클을 **단일 파이프라인**으로 조율합니다. 각 Step은 조건에 따라 자동 스킵되므로, "처음부터 끝까지" 또는 "실행만" 모두 이 스킬 하나로 처리됩니다.

> **원칙**: 오케스트레이터는 하나만 존재한다. 모든 테스트 요청은 이 스킬을 통한다.

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| 티켓 ID | 사용자 요청 | Y | Jira 티켓 식별자 (예: PROJ-123) |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| ctx.* | 전체 파이프라인 | 모든 컨텍스트 (test_baseline, sheet, data_mapping, execution_plan 등) |
| Confluence 보고서 | 사용자 | 최종 테스트 결과 문서 ({티켓}_Confluence_테스트결과_v{N}.{M}_{date}.md) |

# ctx 변수 타입 약속:
# - ctx.tc_spec      = tc_spec.json 절대 파일 경로 (string) — test-plan이 설정
# - ctx.tc_spec_data = tc_spec.json 파싱된 dict — 각 스킬이 Read 후 로컬 파싱

### CONSUMES (다른 스킬의 OUTPUT)
| 출처 스킬 | 사용 필드 | 사용 Step |
|-----------|----------|-----------|
| test-init | init_status | Step 0 |
| test-gate | test_baseline (mode, baseline_mode, analysis_mode, jira_digest, code_digest, comparison, test_scope, affected_services, test_types, server_connectivity, server_env_map, reason, **behavioral_contracts**) | Step 1 |
| test-plan | ctx.sheet, ctx.sheet_version, **ctx.tc_spec** | Step 3 |
| test-data | ctx.data_mapping | Step 4 |
| test-scheduler | ctx.execution_plan | Step 5 |
| test-reporter | Confluence 보고서 파일 | Step 6 |
| test-review-agent | {ticket}_review.json | Step 6.5 |
| test-evidence | 근거 규칙 (참조) | Step 5.3 |
| test-workspace-conventions | 경로 규칙 (참조) | Step 0 |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- Auto-skip 조건 판정 (Step 2, Step 4)
- Tiered Loop 실행 (Step 5.2)
- 서버 접속 끊김 처리 (Step 5.3)
- Partial Failure 복구 로직
- Manual Report 재생성

---

## ctx 복원 프로토콜 (Write-Through + Read-Through Cache)

> **원칙**: ctx는 L1 캐시(휘발성), 파일은 L2 스토리지(영구).
> 컨텍스트 압축으로 ctx가 유실될 수 있으므로, 매 Step 시작 시 필요한 ctx 필드를 확인하고 없으면 파일에서 복원한다.

### Write-Through (기존 — 변경 없음)

각 Step 완료 시 결과를 ctx에 저장하면서 **동시에** 파일에도 저장. 이미 모든 Step에서 수행 중.

### Read-Through Fallback (신규 — 각 Step 시작 시)

각 Step 시작 시 필요한 ctx 필드 존재를 확인한다:

1. ctx.{field} 존재 → 사용 (L1 히트)
2. ctx.{field} 없음 → 복원 맵의 파일에서 복원 (L2 폴백)
3. 파일도 없음 → ERROR: "선행 Step 미완료" → 파이프라인 중단

### 복원 맵 (ctx → 파일)

| ctx 필드 | 복원 파일 | 복원 방법 |
|----------|----------|----------|
| test_baseline | `{ctx.ticket_folder}/{ticket}_gate_*.json` | Glob → 타임스탬프 최신 → Read → JSON parse |
| sheet | `{ctx.ticket_folder}/{ticket}_테스트시트_v*.md` | Glob → 최고 v{N} 선택 |
| sheet_version | (sheet 파일명) | 파일명에서 `v{N}` 추출 |
| data_mapping | `{ctx.ticket_folder}/{ticket}_데이터매핑.json` | Read → JSON parse |
| execution_plan | `{ctx.ticket_folder}/{ticket}_execution_plan.json` | Read → JSON parse |
| partial_results | `{ctx.ticket_folder}/partial_results/*.json` | Glob → 경로 목록 |
| confluence_file | `{ctx.ticket_folder}/{ticket}_Confluence_테스트결과_v*.md` | Glob → 최신 버전 |
| behavioral_gate | `{ctx.ticket_folder}/{ticket}_behavioral_gate.json` | Read → JSON parse |
| tc_spec | `{ctx.ticket_folder}/{ticket}_tc_spec.json` | Glob → Read → JSON parse (ticket_folder 기준, CWD 독립) |
| report_result | `{ctx.ticket_folder}/partial_results/_summary.json` | Read → JSON parse |
| server_env_map | (ctx.test_baseline에서 파생) | test_baseline 복원 후 → `ctx.server_env_map = ctx.test_baseline.server_env_map` |
| auth_url | `test/_shared/환경/API_엔드포인트.md` | Read → AUTH_URL 값 추출 |

> **복원 범위**: ctx.ticket_folder 내부만 (IO Scope 유지).
> **ctx.ticket, ctx.ticket_folder**: 복원 불가 (최상위 컨텍스트). 없으면 사용자에게 재질문.
> **ctx.auth_body**: 파일 저장 금지 (보안). 컨텍스트 압축 후에는 `test/_shared/환경/계정.md`에서 loginId/password 재추출 후 `python3 -c "import json; print(json.dumps(...))"` 로 재생성.

---

## Workflow Overview

| Step | 이름 | 처리 방식 | 상세 |
|------|------|-----------|------|
| Step 0 | Init | 서브에이전트 | 워크스페이스 검증 + 스캐폴드 생성 |
| Step 1 | Verify (Gate) | Main (인터랙티브) | Jira vs 구현 비교, 사용자 의사결정, 서버 확인 |
| Step 2 | Sheet Check | Main | REUSE/REPLAN/NEW 판정 |
| Step 3 | Plan | 서브에이전트 | 테스트시트 생성/재생성 |
| Step 4 | Data | 서브에이전트 | TC별 데이터 매핑 |
| Step 5 | Execute | Main (인터랙티브) | 티어별 병렬 실행 + 실시간 피드백 |
| Step 6 | Report | 서브에이전트 | Confluence 보고서 생성 |
| Step 6.5 | Review | Main (인터랙티브) | 보고서 의미적 검증 (선택적) |
| Step 7 | Post | 서브에이전트 | 후처리 액션 (Confluence 업로드, Jira 코멘트) |

---

## Step 0: Init (Workspace 검증 + 리소스 로드)

### 0.1 Workspace 초기화 (test-init 호출)

리소스 로딩 전에 `test-init` 스킬을 먼저 호출하여 workspace를 검증합니다.

```
1. test-init 호출 → 폴더 구조 + 필수 파일 검증
2. 결과 판정:
   READY      → 즉시 리소스 로딩 진행 (0.2)
   CREATED    → 생성 내역 알림 후 리소스 로딩 진행
   NEEDS_INPUT → 사용자 입력 처리 후 재검증
   NOT_READY  → 파이프라인 중단, 수동 조치 요청
```

### 0.1.5 Ticket Folder Resolution (필수 — 리소스 로딩 전에 실행)

> 상세 알고리즘: `test-workspace-conventions.md` → "Ticket Folder Resolution" 참조
> **핵심 원칙**: 1 Ticket = 1 Folder — 티켓 ID가 같으면 feature명이 달라도 같은 폴더

```
0. 티켓 ID 정규화:
   - 입력에서 티켓 ID 패턴 추출: /([A-Z][A-Z0-9]*-\d+)/
   - "WO-55_할당해제NPE수정" → "WO-55" (feature명 제거)
   - "WO-55 부분취소 테스트" → "WO-55" (설명 제거)

1. RESOLVE(ticket_id) 호출:
   - Glob: $CLAUDE_PROJECT_DIR/test/{ticket_id}*/**  (절대 경로 필수 — CWD 리셋 시 상대 경로 실패)
   - ⚠️ Glob은 디렉토리 자체를 반환하지 않으므로 /** 패턴 필수
   - 필터링: _prefix, backup, examples 제외
   - 0개 → 사용자에게 기능명 질문 → 폴더 생성
   - 1개 → 자동 선택 (feature명 무관)
   - 2개+ → ⚠️ 원칙 위반 경고 + 사용자 선택
   - ASSERT 검증 (시작 경로, backup 미포함, 티켓 접두사)

2. 컨텍스트 설정:
   - ctx.ticket = normalized ticket_id (예: "WO-55")
   - ctx.ticket_folder = resolved folder path
   - 이후 모든 Step에서 ctx.ticket_folder 사용

3. IO Scope 활성화:
   - WRITE: ctx.ticket_folder/** 만 허용
   - READ: ctx.ticket_folder + _shared + templates + rules 만 허용
   - backup, 다른 티켓 폴더 접근 금지
```

### 0.2 _shared/ 로딩 원칙

> Main agent는 `_shared/` 파일을 직접 로드하지 않는다.
> 각 서브에이전트(Step 0, 3, 4, 6)가 `## _shared/ Dependencies` 선언에 따라 필요한 파일만 로드한다.
> Main이 직접 처리하는 Step(1, 5)은 해당 Step 진입 시 필요한 _shared/ 파일을 로드한다.

Step 1 진입 시 Main이 로드: `환경/URL.md`, `환경/API_엔드포인트.md`
Step 5 진입 시 Main이 로드: `환경/URL.md`, `환경/실행_규칙.md`, `환경/계정.md`, `환경/API_엔드포인트.md`, `rules/_guidelines_test_evidence.md`
Step 6 서브에이전트 로드: `rules/_confluence_output_rules.md`

### 0.3 Permission Scope 사전 검증

테스트 실행 중 반복적인 권한 허가 프롬프트를 방지하기 위해, 파이프라인 시작 전에 필요한 권한 범위를 검증합니다.

```
━━━ Phase A: 권한 목록 산출 ━━━

1. 권한 소스 로드:
   a) .claude/skills/test/rules/_test_permissions.json → 범용 권한 범주 (api_call, git_analysis 등)
   b) $CLAUDE_PROJECT_DIR/test/_shared/환경/permissions.json → 프로젝트별 도구 이름 (DB, UI, 이슈트래커)

2. 필수 권한 목록 산출:
   - always_required 범주: 직접 정의된 패턴 + FROM_PROJECT_CONFIG 해소
   - conditional 범주: ctx.test_types에 따라 필요한 것만 추가
   - 두 소스를 합산 → ctx.required_permissions (전체 필요 권한 목록)

━━━ Phase B: 현재 상태 확인 ━━━

3. .claude/settings.local.json 읽기 (Read tool):
   - permissions.allow 배열 추출
   - ctx.required_permissions와 대조
   - missing[] = 누락된 권한 목록

━━━ Phase C: 일괄 등록 (핵심) ━━━

4. 분기:
   IF missing 비어있음:
     → "[Step 0.3] ✅ 사전 권한 완료 — 모든 필수 권한 등록됨"
     → Phase D 스킵

   IF missing 존재:
     → 사용자에게 1회 승인 요청:

       "테스트 파이프라인 실행에 {N}개 권한이 추가로 필요합니다:

        [db_query]       mcp__postgres_{service}__query (3개)
        [issue_tracker]  mcp__atlassian__getJiraIssue (2개)
        [ui]             mcp__playwright__browser_* (5개)

        settings.local.json에 일괄 등록하시겠습니까?
        → 등록하면 이후 테스트 실행에서도 자동 승인됩니다.

        [1] 일괄 등록 (권장) — settings.local.json에 추가
        [2] 이번만 개별 허가 — 각 도구 호출 시마다 승인
        [3] 중단"

5. 사용자 선택 처리:

   [1] 일괄 등록:
     a) settings.local.json 읽기 (Read tool)
     b) permissions.allow에 missing[] 항목 추가
     c) 중복 제거 + 정렬
     d) settings.local.json 쓰기 (Edit tool — 기존 permissions.allow 교체)
     e) → "[Step 0.3] ✅ {N}개 권한 등록 완료"

   [2] 이번만 개별 허가:
     → "[Step 0.3] ⚠️ 개별 허가 모드 — 실행 중 권한 프롬프트가 발생합니다"
     → 파이프라인 계속 진행

   [3] 중단:
     → 파이프라인 종료

━━━ Phase D: 검증 ━━━

6. (일괄 등록한 경우) settings.local.json 재읽기로 등록 확인
   → 실패 시 에러 출력 + [2]로 폴백

━━━ 참조 ━━━

- 범용 범주: .claude/skills/test/rules/_test_permissions.json
- 프로젝트별 도구: $CLAUDE_PROJECT_DIR/test/_shared/환경/permissions.json
- 새 test_type 추가 시 양쪽 파일 모두 확인
- settings.local.json 수정은 반드시 사용자 승인 후에만 실행
```

### 0.4 STIMULUS 인증 준비

ACTIVE TC의 API 호출에 필요한 인증 정보를 준비합니다.

```
1. 인증 정보 소스 로드:
   - test/_shared/환경/계정.md 에서 loginId, password 추출
   - test/_shared/환경/API_엔드포인트.md 에서 AUTH_URL 확인

2. 인라인 인증 JSON 생성 (파일 저장 금지):
   - ⚠️ 비밀번호에 특수문자(!, @, # 등)가 포함될 수 있음
     → 반드시 Python json.dumps()로 JSON 문자열 생성 (echo/printf 금지)
   - 인증 JSON은 ctx.auth_body에 문자열로 보관, 파일로 저장하지 않음
   - 예시:
     ctx.auth_body = '{"loginId":"testuser","password":"P@ss!","forceLogin":true}'

3. 인증 검증 (선택적):
   - stimulus_executor.py --auth-login으로 토큰 발급 테스트
   - 실패 시 사용자에게 알림 → 계정 정보 확인 요청

4. 컨텍스트 저장:
   - ctx.auth_url = AUTH_URL
   - ctx.auth_body = 인증 JSON 문자열 (파일 경로가 아님)

⚠️ 보안 규칙:
   - 인증 정보(loginId, password)를 partial_results/ 또는 기타 파일에 저장 금지
   - 토큰은 ctx에만 보관 (휘발성 — 세션 종료 시 자동 소멸)

⚠️ 컨텍스트 압축 후 복구:
   - ctx.auth_url: test/_shared/환경/API_엔드포인트.md에서 재추출
   - ctx.auth_body: test/_shared/환경/계정.md에서 loginId/password 재추출 →
     python3 -c "import json; print(json.dumps({'loginId':'...','password':'...'}))"
   - 복구 후 0.4 재실행 (Step 0.4부터 재시작)
```

### 0.5 $CLAUDE_PROJECT_DIR 환경변수 설정 (필수 — 모든 Python 도구 호출 전)

> **목적**: 모든 Python 도구 경로가 `$CLAUDE_PROJECT_DIR/.claude/skills/test/tools/`를 기준으로 구성된다.
> 이 환경변수가 미설정이면 모든 STIMULUS/VERDICT/COMPARE 도구 호출이 실패한다.

```
# CLAUDE_PROJECT_DIR 설정 및 검증 (non-git 환경 지원)
CLAUDE_PROJECT_DIR=$(python3 -c "
import subprocess, os, sys

# 1차: git rev-parse
try:
    result = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                           capture_output=True, text=True, timeout=5)
    if result.returncode == 0 and result.stdout.strip():
        print(result.stdout.strip())
        sys.exit(0)
except Exception:
    pass

# 2차: CLAUDE.md 탐색 (현재 디렉토리부터 상위로)
cwd = os.getcwd()
for _ in range(10):
    if os.path.exists(os.path.join(cwd, 'CLAUDE.md')):
        print(cwd)
        sys.exit(0)
    parent = os.path.dirname(cwd)
    if parent == cwd:
        break
    cwd = parent

# 3차: 현재 디렉토리
print(os.getcwd())
")
export CLAUDE_PROJECT_DIR

# 검증: tools/ 디렉토리 존재 확인
if [ ! -d "$CLAUDE_PROJECT_DIR/.claude/skills/test/tools" ]; then
  echo "❌ tools/ 디렉토리 미발견: $CLAUDE_PROJECT_DIR/.claude/skills/test/tools"
  echo "⚠️ 수동 설정 필요: export CLAUDE_PROJECT_DIR=/Users/roy/workspace"
fi
ctx.CLAUDE_PROJECT_DIR = $CLAUDE_PROJECT_DIR  # 이후 모든 Python 도구 호출에서 사용
```

---

## Step 1: Verify (test-gate v4.1 호출)

> Gate 내부 동작의 상세는 `test-gate.md` 참조. 여기서는 오케스트레이터 관점의 입출력만 기술한다.

```
1. test-gate 스킬 호출
   - 입력: 티켓 ID, 브랜치명
   - Gate가 수행하는 것: 분석 모드 선택(Q0), 참조 데이터 확인, Jira vs 구현 비교,
     사용자 의사결정, 서비스 탐색, 범위 판단, 서버 접속 확인
   - 출력: test_baseline (아래 참조)

2. Gate 차단 조건 (파이프라인 즉시 종료):
   - BE API 서버 접속 실패 (DB만으로 대체 불가)
   - 사용자가 "중단" 선택
   - Jira/코드 변경 모두 없음

3. Gate 통과 시 → test_baseline을 ctx에 저장:
   - ctx.test_baseline (mode, baseline_mode, jira_digest, code_digest, comparison)
   - ctx.test_scope, ctx.analysis_mode
   - ctx.affected_services (탐색된 서비스 목록 + 유형: BE_API/FE_WEB/FE_APP)
   - ctx.test_types (api_test, db_verify, web_ui_capture, mobile_api_simulation, event_verify)
   - ctx.server_env_map (수정 서비스별 환경 맵)
   - ctx.behavioral_contracts = test_baseline.behavioral_contracts (Plan이 tc_spec.json 생성에 사용)

4. Gate 결과 파일 저장 (다음 실행 참조용):
   - 파일: {ctx.ticket_folder}/{티켓}_gate_{YYYYMMDD_HHmmss}.json
   - 내용: test_baseline 전체 (mode, baseline_mode, analysis_mode, jira_digest,
     code_digest, comparison, test_scope, affected_services, test_types,
     server_connectivity, server_env_map, reason,
     **behavioral_contracts** — Plan의 tc_spec.json 생성에 사용)
   - ⚠️ sheet_version 미포함 — Plan 출력물이므로 gate.json에 기록하지 않음
   - 용도: 다음 Gate 실행 시 Q0(이전 analysis_mode), 1.8(영향도 비교)에서 참조
```

---

## Step 2: Sheet Check (시트 버전 판정)

> **ctx 복원**: ctx.test_baseline 없으면 → `{ticket}_gate_*.json` 최신 파일에서 복원

```
# 검색 범위: ctx.ticket_folder 내부만 (IO Scope Enforcement)

1. test_baseline.mode 확인:

   CASE "REUSE":
     → "[Step 2] 기존 시트 v{N} 사용 (baseline 동일)"
     → ctx.sheet = 기존 시트
     → ctx.sheet_version = ctx.sheet 파일명에서 v숫자 패턴 추출 ("v" prefix 유지)
       # 예: "TICKET-123_테스트시트_v1.2.md" → ctx.sheet_version = "v1.2" ("v" 포함)
       # 파일명에서 추출 실패 시 → ctx.sheet_version = "unknown"
       # ※ tc_spec.json의 sheet_version 필드도 동일 포맷 ("v" 포함)이어야 함
     → tc_spec.json 존재 확인: Glob {ctx.ticket_folder}/{ticket}_tc_spec.json
       IF 없음 → "[Step 2] ⚠️ tc_spec.json 미발견 — Step 5 VERDICT는 마크다운 폴백 모드로 실행"
       IF 발견:
         tc_spec_sheet_ver = tc_spec.json["sheet_version"]
         IF tc_spec_sheet_ver != ctx.sheet_version:
           WARNING: "tc_spec.json 버전 불일치 (tc_spec={tc_spec_sheet_ver}, 현재={ctx.sheet_version}) — 마크다운 폴백 모드로 전환"
           → tc_spec.json 사용 안 함
         ELSE:
           ctx.tc_spec = {tc_spec.json 절대 경로}
     → Step 3 스킵

   CASE "REPLAN":
     → "[Step 2] baseline 변경 감지 → 기존 시트 기반 증분 수정 (v{N+1})"
     → ctx.previous_sheet = 기존 시트 경로 (Step 3에서 참조용으로 전달)
     → Step 3 진행

   CASE "NEW":
     → "[Step 2] 시트 없음 → 신규 생성"
     → Step 3 진행
```

---

## Step 3: Plan (test-plan 호출)

> **처리 방식**: 서브에이전트 dispatch → test-plan.md 로드 → 완료 시 ctx.sheet, ctx.sheet_version 반환

```
1. test-plan 스킬 호출
   - 입력: ctx.test_baseline (jira_digest, code_digest, test_scope, baseline_mode, **behavioral_contracts**)
     # ※ behavioral_contracts 필수 전달 — Plan이 tc_spec.json 생성 시 사용 (미전달 시 소스코드 재분석 fallback)
   - test-plan은 jira_data를 재조회하지 않고 Gate에서 전달받은 데이터 사용

2. 출력:
   - {티켓}_테스트시트_v{N}_{날짜}.md (마크다운 — 사람이 읽는 문서)
   - {티켓}_tc_spec.json — TC별 행위 조건·기대값·데이터 요구사항 구조화 JSON (기계 계약)
     (상세 스키마: test-plan.md Step 4.3-C 참조)
   - Section 0: Test Baseline (jira_digest + code_digest + 비교 결과)
   - Section 1~: 기존 테스트시트 구조

3. 컨텍스트 업데이트:
   - ctx.sheet = 생성된 시트
   - ctx.sheet_version = "v{N}"
   - ctx.tc_spec = {티켓}_tc_spec.json 절대 경로
```

---

## Step 3.5: Plan Review Checkpoint (NEW 또는 REPLAN 시)

> **원칙**: 테스트시트 생성/수정 후, 사용자가 시트를 검토할 기회를 보장한다.
> REUSE 모드에서는 기존 시트를 그대로 사용하므로 이 Checkpoint를 스킵한다.

```
━━━ 진입 조건 ━━━

IF test_baseline.mode == "REUSE":
  → "[Step 3.5] ⏭️ 기존 시트 재사용 — Checkpoint 스킵"
  → Step 4 진행

IF test_baseline.mode == "NEW" OR "REPLAN":
  → Checkpoint 실행 (아래)

━━━ 사용자에게 제시할 요약 ━━━

테스트시트에서 다음 정보를 추출하여 요약 테이블로 제시:

1. TC 현황:
   - ACTIVE TC 수 / OBSERVATION TC 수 / 총 TC 수
   - 시나리오별 TC 개수

2. 시나리오 목록 (1줄 요약):
   | # | 시나리오 | TC 수 | 유형 |
   |---|----------|-------|------|
   | 1 | {시나리오명} | {N}개 | ACTIVE/OBSERVATION |
   | ... | ... | ... | ... |

3. 예상 데이터 요구사항:
   - 필요한 데이터 종류 (EO, OB, Shipment 등)
   - 특수 조건 (특정 상태, 특정 이벤트 등)

4. STIMULUS 명세 현황:
   - STIMULUS 명세 있음: {N}개 TC
   - STIMULUS 명세 없음 (실행 시 추론 필요): {M}개 TC

━━━ 사용자 선택 ━━━

AskUserQuestion으로 3가지 선택지 제시:

  [1] 승인 → Step 4 진행
  [2] 수정 요청 → 사용자 피드백 반영 후 test-plan 재호출 → Step 3.5 재실행
  [3] 중단 → 파이프라인 중단 (시트는 이미 파일로 저장됨, 추후 REUSE 가능)

━━━ 수정 요청 처리 ━━━

사용자가 [2]를 선택한 경우:
  1. 사용자의 피드백 내용을 수집
  2. test-plan을 피드백 반영 모드로 재호출
  3. 시트 재생성 후 ctx.sheet, ctx.sheet_version 업데이트
  4. Step 3.5 재실행 (요약 재제시 → 재확인)
  - 최대 3회 반복 후 자동으로 Step 4 진행 (무한루프 방지)
  - **루프 카운터 영구화 (컨텍스트 압축 대비)**:
    - Step 3.5 진입 시: ctx.plan_review_count 없으면 → Read `{ctx.ticket_folder}/{ticket}_plan_review_count.json` → count 복원 (없으면 0)
    - 사용자가 [2] 선택 시: count += 1 → 즉시 `{ticket}_plan_review_count.json` Write (`{"count": N}`)
    - count >= 3 → "[Step 3.5] ⏩ 수정 한도 초과 — Step 4 자동 진행"
    - Step 4 진행 확정 시: `{ticket}_plan_review_count.json` 삭제 (정리)
```

---

## Step 4: Data (test-data 호출)

> **처리 방식**: 서브에이전트 dispatch → test-data.md 로드 → 완료 시 ctx.data_mapping 반환

> **ctx 복원**: ctx.sheet 없으면 → `{ticket}_테스트시트_v*.md` 최고 버전에서 복원, ctx.sheet_version 없으면 → 파일명에서 `v{N}` 추출

```
1. 데이터 매핑 파일 존재 확인
   - Glob: {ctx.ticket_folder}/{티켓}_데이터매핑.json

2. 조건부 스킵:
   IF 매핑 파일 존재 AND 매핑.sheet_version == ctx.sheet_version AND 매핑.completed_at != null
     → "[Step 4] 기존 데이터 매핑 사용 (시트 버전 일치 + 매핑 완료 확인)"
     # ※ completed_at: null이면 이전 실행이 중단된 불완전 매핑 → 재실행 필수
     → Step 4 스킵
   ELSE
     → test-data 스킬 호출

3. test-data 결과 확인:
   - MAPPED: 정상
   - NOT_FOUND: 사용자에게 알림
     → "N개 TC의 데이터를 찾을 수 없습니다."
     → [1] 계속 진행 (NOT_FOUND TC는 N/T 처리)
     → [2] Provisioning 모드로 데이터 생성
     → [3] 중단 (사용자가 데이터 준비 후 재실행)

4. 컨텍스트 업데이트:
   - ctx.data_mapping = 매핑 결과
```

---

## Step 5: Schedule + Execute

> **ctx 복원**: ctx.sheet 없으면 → 테스트시트 파일에서 복원, ctx.data_mapping 없으면 → `{ticket}_데이터매핑.json`에서 복원

### 5.0.0 tc_spec.json 로드 (Step 5 전체에서 사용)
<!-- 5.0.1(Pre-flight) 실행 전 선행 단계 — 3단계 번호는 "5.0 블록의 첫 단계" 의미 -->

> **목적**: ctx.tc_spec은 파일 경로(string)이다. Step 5.2.1 VERDICT에서 딕셔너리로 접근하려면
> 명시적으로 Read + JSON parse가 필요하다. 이 단계를 스킵하면 tc_spec[tc_id] 접근이 실패한다.

```
IF ctx.tc_spec 존재 (파일 경로 string):
  1. Read: {ctx.tc_spec} 파일 읽기
  2. JSON parse → ctx.tc_spec_data = parsed dict
  3. 이후 VERDICT 등에서 ctx.tc_spec_data[tc_id]로 접근
ELSE IF Glob {ctx.ticket_folder}/{ticket}_tc_spec.json 발견:
  1. Read → JSON parse → ctx.tc_spec_data
ELSE:
  → ctx.tc_spec_data = null  # VERDICT fallback 모드 (마크다운 파싱)
```

### Step 5.0.0 완료 후 Step 5.0.1 진행

### ⭐ 5.0.1 Pre-Execution Behavioral Gate (필수)

> **원칙**: 데이터 매핑 파일의 behavioral_check를 기계적으로 검증하여, 행위적 조건이 미충족된 TC를 실행 전에 차단한다.

```bash
python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/behavioral_gate.py \
  --mapping {ctx.ticket_folder}/{ticket}_데이터매핑.json \
  --output {ctx.ticket_folder}/{ticket}_behavioral_gate.json
```
- 출력: `{gate_passed, results[{tc_id, gate: PASS|BLOCKED|NEEDS_CONFIRMATION, reason}], summary}`
- `BLOCKED` TC → 실행 금지, `NEEDS_CONFIRMATION` TC → 사용자 확인 후 실행
- Hook 모드로도 동작: `partial_results/TC-*.json` 작성 시 behavioral_check.verdict 자동 검증

> ℹ️ **behavioral_gate.py 판정 규칙**
> - `behavioral_check` 필드 **없음** → PASS (BLOCKED 아님) — 구형 매핑 파일 호환
> - BLOCKED = `behavioral_check.verdict != "PASS"` 이면서 필드가 존재하는 경우만
> - 매핑 파일 자체가 없으면 → 전체 PASS (graceful)

> **Pre-flight 중복 검증 방지 (B-2)**: behavioral_gate.py 결과는 `{ticket}_behavioral_gate.json`에 저장된다.
> - behavioral_gate.py: 데이터매핑 시점의 behavioral_check 스냅샷 재평가 (빠름)
> - test-scheduler Pre-flight: 실행 직전 db_check.sql 직접 실행으로 stale 데이터 감지 (신선)
> - **충돌 해결 원칙**: 두 검증 중 하나라도 BLOCKED 판정 시 → BLOCKED 확정 (보수적 판정)
> - Pre-flight는 behavioral_gate.json의 BLOCKED TC에 대해 SQL 재실행을 스킵한다 (이미 차단됨)

### 5.1 Scheduling (test-scheduler 호출)

```
1. test-scheduler 스킬 호출
   - 입력: ctx.sheet, ctx.data_mapping
   - 출력: test_execution_plan.json (Tier 기반 DAG)

2. 실행 계획 검증:
   - 모든 TC가 데이터에 매핑되었는지 확인
   - NOT_FOUND TC는 N/T로 마킹
   - BLOCKED TC 마킹 (두 소스 합산 — 보수적 판정):
     IF ctx.behavioral_gate 존재:
       FOR each result in behavioral_gate.results:
         IF result.gate == "BLOCKED" → result.tc_id BLOCKED 마킹
     FOR each tc_id where data_mapping[tc_id].behavioral_check.verdict == "FAIL" → BLOCKED 마킹
     # ※ 두 신호 중 하나라도 BLOCKED이면 BLOCKED 확정 (OR 조건)
```

### 5.2 Execution (Tiered Loop)

```
1. test_execution_plan.json 로드

2. FOR each Tier (0 to N):
   - 현재 Tier의 parallel_tasks 동시 실행

   - Task Type별 처리:
     PROVISION: test-provisioning Worker 호출
     TEST: TC Execution Protocol(5.2.1)에 따라 실행

   - Strict Sync: 현재 Tier 모든 Task 완료 후 다음 Tier 진행
   - 각 Task 결과 → partial_results/ 에 저장
   # partial_results/ 경로: {ctx.ticket_folder}/partial_results/

   - **Tier 0 PROVISION 완료 시 병합 트리거 (C-7)**:
     IF 현재 Tier == 0 AND Tier에 PROVISION 타입 Task가 있었음:
       → test-provisioning Step 4.5 실행 (오케스트레이터가 직접):
         FOR each {tc_id}_provisioning.json in partial_results/:
           a. Read 최신 {ticket}_데이터매핑.json
           b. mappings[tc_id] 업데이트 (status=PROVISIONED, data, provisioned_at)
           c. Write 데이터매핑.json (Read-Modify-Write 직렬화)
         데이터매핑.json의 completed_at = now() 로 갱신

3. 실행 결과 수집:
   - ctx.partial_results = 수집된 결과 파일들

4. partial_results 파일 형식 (test-reporter와의 계약):
   파일: partial_results/{TC_ID}.json
   {
     "tc_id": "TC-1.1",
     "tc_type": "ACTIVE | OBSERVATION",  // TC 유형 (test-plan 4-A 참조)
     "status": "PASS | FAIL | N/T | BLOCKED | INCOMPLETE",
     "checklist": {                       // 체크리스트 (5.2.1 참조, 필수)
       "data": "...",
       "before": { ... },
       "stimulus": { ... },
       "wait": "...",
       "after": { ... },
       "compare": "...",
       "verdict": "..."
     },
     "api_response": { ... },           // api_test 결과
     "db_before": { ... },              // db_verify 사전 스냅샷
     "db_after": { ... },               // db_verify 사후 스냅샷
     "db_changes": [ ... ],             // db_verify 변경 행 목록
     "screenshots": ["path/to/..."],    // web_ui_capture 스크린샷 경로
     "mobile_api_results": [ ... ],     // mobile_api_simulation API 시퀀스 결과
     "event_results": { ... },          // event_verify 토픽 매칭 결과
     "checkpoints": [ ... ],            // e2e TC 구간별 검증 결과 (5.2.2 CHECKPOINT)
     "evidence": { "level": 2, "text": "..." },  // 근거 (test-evidence 규칙 준수)
     "error": null                      // 오류 시 에러 메시지
   }
   - 미해당 필드는 null 또는 생략
   - test-reporter는 이 형식을 기준으로 병합
```

### ⭐ 5.2.1 TC Execution Protocol — 체크리스트 (필수 — 스킵 불가)

> **원칙**: 모든 TC는 아래 체크리스트를 사용자에게 **실시간으로 표시**하며 순차 진행한다.
> 체크되지 않은 항목이 있으면 다음 항목으로 진행할 수 없다.
> 이 프로토콜은 "DB 조회만으로 PASS 판정"을 구조적으로 방지한다.

#### 체크리스트 (7단계)

```
━━━ TC-{id}: {TC 제목} ━━━

[ ] 1. DATA      — 테스트 입력 데이터 ID 확보 + 기록
[ ] 2. BEFORE    — 실행 전 상태 스냅샷 (DB 조회 or 화면 캡처)
[ ] 3. STIMULUS  — 실제 API 호출 or 화면 조작 (request/response 기록)
[ ] 4. WAIT      — 비동기 처리 대기 (해당 시, 없으면 자동 체크)
[ ] 5. AFTER     — 실행 후 상태 확인 (DB 재조회 or 화면 캡처)
[ ] 6. COMPARE   — Before vs After 변화 분석
[ ] 7. VERDICT   — PASS/FAIL 판정 + 근거
```

#### 실행 규칙

```
FOR each TC in execution_plan:

  ━━━ Phase 1: 유형 판별 ━━━

  tc_type = TC 제목에서 유형 판별
    IF TC 제목이 "[관찰]"로 시작 → OBSERVATION
    ELSE → ACTIVE

  ━━━ Phase 2: 체크리스트 실행 (사용자에게 실시간 표시) ━━━

  출력: "━━━ TC-{id}: {제목} ━━━"

  [Step 1: DATA]
    - 테스트시트의 사전조건 + data_mapping에서 입력 데이터 확보
    - 데이터 ID를 기록 (예: "EO0000000129500")
    - 데이터 없으면 → status = N/T, 체크리스트 중단
    - 출력: "[✅] 1. DATA — {데이터 ID}"

  [Step 2: BEFORE]
    - 테스트시트의 BEFORE 명세에 따라 사전 상태 조회
    - DB 쿼리 결과 또는 화면 스크린샷 기록
    # DB 쿼리 결과를 파일로 저장 (compare_db_snapshots.py 입력용)
    Write: {ctx.ticket_folder}/partial_results/{TC_ID}_before.json
    - 출력: "[✅] 2. BEFORE — {핵심 상태 요약}"

  [Step 3: STIMULUS] ★ 핵심 ★
    IF tc_type == ACTIVE:
      - ★ 필수 도구: stimulus_executor.py ★
      - ACTIVE TC의 STIMULUS는 반드시 stimulus_executor.py를 통해 실행한다.
      - 호출 형식:
        python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/stimulus_executor.py \
          --method {METHOD} \
          --url "{FULL_URL}" \
          --header "Content-Type: application/json" \
          --body '{BODY_JSON}' \
          --tc-id {TC_ID} \
          --auth-url "{AUTH_URL}" \
          --auth-body "${ctx.auth_body}" \
          --output {ctx.ticket_folder}/partial_results/{TC_ID}_stimulus.json
      - AUTH_URL과 인증 정보는 Step 0.4에서 준비된 ctx.auth_body를 인라인으로 전달한다.
      - ❌ 인증 정보를 파일로 저장하여 --auth-body-file로 전달 금지
      - 출력 JSON의 response 섹션을 증거로 사용한다.

      > ⚠️ **validate_test_result.py Hook 통과 조건 (2가지 모두 필요)**
      > 1. partial_results/{TC_ID}.json 내 텍스트 증거 (HTTP 메서드+URL 또는 stimulus_executor 참조)
      > 2. `{ctx.ticket_folder}/partial_results/{TC_ID}_stimulus.json` 파일이 디스크에 실제 존재
      > → 텍스트 증거만 있고 파일 없으면 Hook이 DENY — stimulus_executor.py `--output` 파라미터가 이 파일을 생성함
      - request 전체 (method, URL, headers, body) 기록
      - response 전체 (status code, body) 기록
      - 출력: "[✅] 3. STIMULUS — {method} {endpoint} → HTTP {status}"
      - ❌ curl이나 직접 API 호출 금지 — 반드시 stimulus_executor.py 경유
      - ❌ stimulus_executor.py 없이 ACTIVE TC를 PASS 판정 금지

      ❌ STIMULUS 실행 실패 또는 미실행 시:
        → status = INCOMPLETE (PASS/FAIL 판정 불가)
        → 출력: "[❌] 3. STIMULUS — 미실행: {사유}"
        → 사용자에게 알림 후 다음 TC로 이동

    IF tc_type == OBSERVATION:
      - STIMULUS 생략
      - 출력: "[⏭️] 3. STIMULUS — 생략 (관찰 TC)"

  [Step 4: WAIT]
    - 비동기 처리가 필요하면 대기 (Kafka 이벤트 처리 등)
    - 불필요하면 즉시 체크
    - 출력: "[✅] 4. WAIT — {N}초 대기" 또는 "[✅] 4. WAIT — 불필요"

  [Step 5: AFTER]
    - BEFORE과 동일한 대상을 재조회
    - DB 쿼리 결과 또는 화면 스크린샷 기록
    # DB 쿼리 결과를 파일로 저장 (compare_db_snapshots.py 입력용)
    Write: {ctx.ticket_folder}/partial_results/{TC_ID}_after.json
    - 출력: "[✅] 5. AFTER — {핵심 상태 요약}"

  [Step 6: COMPARE]
    - ★ Python 도구 사용 (BEFORE + AFTER 모두 존재 시):
      python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/compare_db_snapshots.py \
        --before {ctx.ticket_folder}/partial_results/{TC_ID}_before.json \
        --after {ctx.ticket_folder}/partial_results/{TC_ID}_after.json \
        --output {ctx.ticket_folder}/partial_results/{TC_ID}_diff.json
    - diff.json의 changed/unchanged/added/removed를 읽고 변화 의미를 해석
    - BEFORE이 없는 TC는 Python 도구 스킵 → AFTER 단독으로 비교 분석
    - 출력: "[✅] 6. COMPARE — {변화 요약}"

  [Step 7: VERDICT]
    ━━━ 기대값 도출 (tc_spec.json 우선) ━━━

    IF ctx.tc_spec_data 존재 AND tc_spec_data[tc_id] 존재:
      a) static_fields 수집 (고정값 — 계산 불필요):
         # static_fields는 plain dict {"path": value} 형식 (tc_spec.json 스키마 기준)
         expected_json = ctx.tc_spec_data[tc_id].expected.static_fields  # dict 그대로 사용
         예: {"http_status": 200, "inUse": false}

      b) formula fields 계산 (DB 실측값으로 기대값 산출):
         FOR each field in ctx.tc_spec_data[tc_id].expected.fields:
           # identifier_column/identifier_field null 체크
           IF field.source_column is null OR field.aggregation is null:
             WARNING: "source_column 또는 aggregation 없음 — formula 기대값 계산 불가, 폴백"
             CONTINUE
           
           id_col = ctx.tc_spec_data[tc_id].data_requirement.get("identifier_column")
           id_field = ctx.tc_spec_data[tc_id].data_requirement.get("identifier_field")
           IF id_col is null OR id_field is null:
             WARNING: "identifier_column 또는 identifier_field null — formula SQL 생성 불가, 기대값 폴백"
             CONTINUE
           id_val = data_mapping.data.get(id_field)
           IF id_val is null:
             WARNING: "data_mapping에 identifier_field "{id_field}" 없음 — formula SQL 생성 불가"
             CONTINUE

           # aggregation이 null이면 단순 조회
           IF field.aggregation == null:
             source_sql = """
               SELECT {field.source_column}
               FROM {field.source_table}
               {field.extra_join 있으면 JOIN 절 추가}
               WHERE {field.source_where}
                 AND {ctx.tc_spec_data[tc_id].data_requirement.identifier_column} = '{data_mapping.data[ctx.tc_spec_data[tc_id].data_requirement.identifier_field]}'
                 # identifier_column: tc_spec.data_requirement.identifier_column (예: "container_code", "outbound_order_id")
                 # identifier_field:  tc_spec.data_requirement.identifier_field   (예: data_mapping.data 내 키명)
               LIMIT 1
             """
           ELSE:
             source_sql = """
               SELECT {field.aggregation}({field.source_column}) AS computed
               FROM {field.source_table}
               {field.extra_join 있으면 JOIN 절 추가}
               WHERE {field.source_where}
                 AND {ctx.tc_spec_data[tc_id].data_requirement.identifier_column} = '{data_mapping.data[ctx.tc_spec_data[tc_id].data_requirement.identifier_field]}'
                 # identifier_column: tc_spec.data_requirement.identifier_column (예: "container_code", "outbound_order_id")
                 # identifier_field:  tc_spec.data_requirement.identifier_field   (예: data_mapping.data 내 키명)
             """
           result = MCP 쿼리 실행 (db: field.source_db)
           computed_value = result.computed 또는 result[0][field.source_column]
           expected_json[field.path] = computed_value
           # 예: expected_json["total_qty"] = 3  ← DB에서 실측
           # 예: expected_json["groups_count"] = 10  ← COUNT(*) 결과

         ❌ 테스트시트 기대결과 셀의 수동 입력 숫자를 그대로 사용 금지
         ✅ 항상 실제 데이터 기준으로 기대값을 동적 계산

    ELSE (tc_spec.json 없는 폴백):
      → 테스트시트 기대결과 셀에서 직접 파싱
      → WARNING: "tc_spec.json 없음 — 기대값 수동 파싱 (정확도 저하 경고)"

    ━━━ 기계적 비교 실행 ━━━

    # ⚠️ expected_json 구성 주의:
    # tc_spec.expected.fields[] 배열은 기대값을 "계산하는 공식"이지 expected_json 자체가 아님.
    # verdict_calculator.py에 전달되는 --expected는 반드시 평탄한(flat) key-value dict여야 함.
    # 예: {"http_status": 200, "groups_count": 3} — fields[] 배열을 그대로 전달 금지

    - ★ verdict_calculator.py 실행:
      python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/verdict_calculator.py \
        --expected '{위 단계에서 도출한 expected_json}' \
        --actual-file {ctx.ticket_folder}/partial_results/{TC_ID}_stimulus.json \
        --tc-id {TC_ID} \
        --output {ctx.ticket_folder}/partial_results/{TC_ID}_verdict.json
    - verdict_calculator.py가 http_status, *_count, total_qty, all_*, non_null 등을 기계적으로 비교
    - 도구 출력의 verdict 필드를 기준으로 PASS/FAIL 판정 (LLM이 JSON 수동 계산하지 않음)
    - 근거 기록 (test-evidence 규칙 준수)
    - 출력: "[✅] 7. VERDICT — {PASS|FAIL} ({근거 요약})"

  ━━━ Phase 3: Validation Gate (자동 — Hook이 강제) ━━━

  validate_test_result.py Hook이 자동 실행:
  - ACTIVE TC에 STIMULUS 증거 없으면 → Write/Edit deny
  - Pass TC에 검증 diff 테이블 없으면 → deny
  - Fail TC에 [Fail 근거] 또는 기대:/실제: 누락 시 → deny

  IF test_types.db_verify == true:
    ASSERT checklist.before IS NOT NULL
      → 실패 시: status = INCOMPLETE, "BEFORE 스냅샷 누락"
    ASSERT checklist.after IS NOT NULL
      → 실패 시: status = INCOMPLETE, "AFTER 스냅샷 누락"

  IF 모든 ASSERT 통과:
    → status = checklist.verdict (PASS 또는 FAIL)
  ELSE:
    → status = INCOMPLETE
    → 사용자에게 알림: "TC-{id}: 체크리스트 미완료 — {누락 항목}"

  ━━━ Phase 4: 결과 저장 ━━━

  partial_results/{TC_ID}.json에 체크리스트 포함하여 저장
```


### 5.2.2 CHECKPOINT 프로토콜 (e2e TC — 선택적)

> 테스트시트에 "데이터 흐름 구간" (test-plan Step 4.4)이 정의된 TC에만 적용.
> 단일 API 호출 TC는 기존 5.2.1 BEFORE/AFTER로 충분하다.
> 이 프로토콜은 e2e 테스트에서 "어느 구간에서 실패했는가"를 특정할 수 있게 한다.

#### 확장 체크리스트 (e2e TC)

기존 체크리스트의 STIMULUS(Step 3)를 구간별로 확장한다:

```
━━━ TC-{id}: {e2e TC 제목} ━━━

[ ] 1. DATA      — 테스트 입력 데이터 확보
[ ] 2. BEFORE    — 전체 구간의 초기 상태 스냅샷

[ ] 3-① STIMULUS — 구간① {트리거 API} → HTTP {status}
[ ] 3-① CHECK    — 구간① 결과: {검증 대상} = {실제값} (기대: {기대값})
[ ] 3-② STIMULUS — 구간② {트리거 API} → HTTP {status}
[ ] 3-② CHECK    — 구간② 결과: {검증 대상} = {실제값} (기대: {기대값})
...
[ ] 3-N STIMULUS — 구간N {최종 트리거}
[ ] 3-N CHECK    — 구간N 결과: {검증 대상} = {실제값}

[ ] 4. WAIT      — 비동기 처리 대기
[ ] 5. AFTER     — 최종 상태 확인
[ ] 6. COMPARE   — 전체 구간 변화 요약 (구간별 성공/실패 식별)
[ ] 7. VERDICT   — PASS/FAIL + 실패 구간 지정
```

#### 실행 규칙

```
- 각 구간의 CHECK가 기대값과 불일치 시:
  → 해당 구간을 ❌ 표시하고, 후속 구간은 실행 중단 또는 계속 (TC 성격에 따라)
  → VERDICT에 "구간 ②에서 실패" 형태로 실패 지점 명시

- partial_results 파일에 checkpoints 필드 추가:
  "checkpoints": [
    { "segment": "①", "trigger": "POST /picking/start", "expected": "state=IN_PROGRESS", "actual": "state=IN_PROGRESS", "pass": true },
    { "segment": "②", "trigger": "POST /picking/complete", "expected": "qty=5", "actual": "qty=0", "pass": false }
  ]
```


### 5.3 테스트 유형별 실행 (ctx.test_types 기반)

각 TC 실행 시, Gate에서 결정된 `ctx.test_types`에 따라 검증 항목이 달라진다.

| test_type | 조건 | 실행 내용 |
|-----------|------|----------|
| `api_test` | 항상 true | ctx.server_env_map으로 HTTP 요청 → 응답 검증 |
| `db_verify` | Repository/Entity 변경 시 | API 호출 전 SELECT 스냅샷 → API 호출 후 재조회 → Before/After 비교 (변경행 + 사이드이펙트 감지). 대상: ctx.test_types.db_verify_tables |
| `web_ui_capture` | FE_WEB 변경 시 | Playwright로 대상 화면 스크린샷 → `screenshots/` 저장 |
| `mobile_api_simulation` | FE_APP 변경 시 | Gate에서 추출한 ctx.test_types.mobile_api_sequences의 API 체인을 순서대로 BE 서버에 호출. TC "채널"은 "API (모바일 시뮬레이션)" |
| `event_verify` | Kafka 변경 시 | 토픽 발행/소비 매칭 확인 |

**모바일 API 시뮬레이션 상세**:
- Gate가 모바일 소스코드에서 추출한 API 호출 시퀀스를 사용
- 각 시퀀스의 `api_sequence`를 `order` 순으로 실행
- `depends_on` 이 있으면 선행 API 응답에서 파라미터 추출
- 기대 결과는 BE API 응답 기준으로 검증

**실행 중 서버 접속 끊김**:
- Connection refused/timeout 발생 시 해당 TC를 BLOCKED 처리
- 나머지 TC 실행 중단, 현재까지 결과를 partial_results에 저장
- 사용자에게 알림 후 Step 6으로 이동

---

## Step 6: Report (test-reporter 호출)

> **처리 방식**: 서브에이전트 dispatch → test-reporter.md + rules/_confluence_output_rules.md 로드 → 완료 시 confluence_file 반환

> **ctx 복원**: ctx.partial_results 없으면 → Glob `partial_results/*.json` → 경로 목록, ctx.sheet 없으면 → 테스트시트 파일에서 복원, ctx.test_baseline 없으면 → gate 파일에서 복원

```
1. test-reporter 스킬 호출
   - 입력: ctx.partial_results, ctx.sheet, ctx.test_baseline, ctx.tc_spec (조건부 — 있으면 전달)
   - 출력: {티켓}_Confluence_테스트결과_v{N}_{날짜}.md

2. Template Compliance 검증:
   - 필수 섹션 포함 여부 자동 검사
   - 누락 시 자동 복구 또는 경고

3. 최종 요약 출력:
   ✅ 테스트 완료
   - 시트: {티켓}_테스트시트_v{N}.md
   - 결과: {티켓}_Confluence_테스트결과_v{N}.md
   - Pass: X개 / Fail: Y개 / N/T: Z개
   - 주요 이슈: (있을 경우 하이라이트)

# ctx.report_result 설정 (Step 6.5 자동 트리거 판정에 사용)
Read: {ctx.ticket_folder}/partial_results/_summary.json
→ JSON parse → ctx.report_result (Step 6.5에서 stats.total, stats.fail 참조용)
```

---

## Step 6.5: Review (선택적 — test-review-agent 호출)

> **ctx 복원**: ctx.confluence_file 없으면 → Glob `{ticket}_Confluence_테스트결과_v*.md` 최신 파일에서 복원, ctx.sheet 없으면 → 테스트시트 파일에서 복원

```
━━━ 트리거 조건 ━━━

이 Step은 선택적이다. 다음 조건에서 실행:
  - 사용자가 명시적으로 리뷰 요청한 경우
  - TC 개수가 5개 이상인 경우 (자동 트리거)
    # 출처: ctx.report_result.stats.total (Step 6에서 생성된 partial_results/_summary.json)
    # 복원: Glob {ctx.ticket_folder}/partial_results/_summary.json → Read → stats.total 필드
  - Fail TC가 1개 이상인 경우 (자동 트리거)
    # 출처: ctx.report_result.stats.fail (partial_results/_summary.json의 stats.fail 필드)

스킵 조건:
  - TC 개수 4개 이하 AND Fail 0개 → "[Step 6.5] ⏭️ 소규모 테스트 — Review 스킵"

━━━ 실행 ━━━

1. test-review-agent를 Worker(Task tool)로 호출:
   - confluence_file: ctx.confluence_file
   - sheet_file: ctx.sheet 파일 경로
   - test_baseline: ctx.test_baseline (또는 gate 파일 경로)
   - partial_results_dir: {ctx.ticket_folder}/partial_results/
   - output_path: {ctx.ticket_folder}/{ticket}_review.json

2. Worker 결과 수신 후 처리:

   IF verdict == "APPROVED":
     → "[Step 6.5] ✅ Review 통과 — 보고서 품질 확인됨"
     → Step 7 진행

   IF verdict == "NEEDS_REVISION":
     → 이슈 목록을 심각도별로 분류하여 사용자에게 보고

     IF critical 이슈 존재:
       → 사용자에게 이슈 리스트 제시 + 수정 여부 질문
       → [1] 수정 후 재리뷰 → 이슈 수정 → Step 6 재실행 → Step 6.5 재실행
            ※ 루프 카운터: ctx.report_review_count (파일: {ticket}_report_review_count.json)
            ※ 최대 3회 → "[Step 6.5] ⏩ 재리뷰 한도 초과 — Step 7 자동 진행"
       → [2] 이슈 인지하고 계속 진행 → Step 7
       → [3] 중단

     IF important/minor만 존재:
       → 이슈 리스트 제시 (정보 제공)
       → "[Step 6.5] ⚠️ Review 완료 — {N}개 개선사항 발견 (important: {X}, minor: {Y})"
       → Step 7 자동 진행

━━━ 출력 ━━━

- {ticket}_review.json: 리뷰 상세 결과
- 사용자에게 리뷰 요약 제시
```

---

## Step 7: Post (test-post 호출 — 선택적)

> **ctx 복원**: ctx.test_baseline, ctx.report_result, ctx.confluence_file, ctx.result_file, ctx.sheet_file 모두 없으면 각각 대응 파일에서 복원 (상세는 test-post.md 참조)

> 상세는 `test-post.md` 참조. 여기서는 오케스트레이터 관점의 입출력만 기술한다.

```
1. _post.md 존재 확인:
   - Glob: $CLAUDE_PROJECT_DIR/test/_post.md
   - 없으면 → "[Step 7] ⏭️ _post.md 없음 — 후처리 스킵" → 파이프라인 종료
   - 있으면 → test-post 스킬 호출

2. test-post 스킬 호출:
   - 입력: ctx 전체 (ticket, ticket_folder, test_baseline, report_result 등)
   - _post.md 파싱 → 액션 블록 추출 → 변수 치환 → 조건 평가

3. 사용자 확인:
   - 외부 시스템 변경 액션 (Confluence, Jira 등)은 사용자 확인 후 실행
   - 확인 거부 시 해당 액션 스킵 (다음 액션은 계속 진행)

4. 액션 순차 실행:
   - confluence-upload: Confluence 페이지 생성/업데이트
   - jira-comment: Jira 티켓에 코멘트 추가
   - custom: 사용자 정의 메시지 출력

5. 결과 출력:
   ━━━ Post-Processing 결과 ━━━
   [✅] confluence-upload: 페이지 생성 완료 (URL)
   [✅] jira-comment: 코멘트 추가 완료
```

---

## Auto-Skip Logic

각 Step은 조건에 따라 자동으로 스킵됩니다:

| Step | 스킵 조건 | 메시지 |
|------|----------|--------|
| Step 3 (Plan) | mode = REUSE | "기존 시트 v{N} 사용" |
| Step 3.5 (Checkpoint) | mode = REUSE | "기존 시트 재사용 — Checkpoint 스킵" |
| Step 4 (Data) | 매핑 존재 + 버전 일치 | "기존 데이터 매핑 사용" |
| Step 5 (Execute) | — | 항상 실행 |
| Step 6 (Report) | — | 항상 실행 |
| Step 6.5 (Review) | TC 4개 이하 AND Fail 0개 | "소규모 테스트 — Review 스킵" |
| Step 7 (Post) | test/_post.md 없음 | "_post.md 없음 — 후처리 스킵" |

---

## Error Handling & Recovery

### Partial Failure (부분 실패)

```
- 특정 Tier/Batch만 실패한 경우
- 실패한 Task만 재실행 가능
- Trigger: "PROJ-456 Batch 2만 다시 실행해줘"
- partial_results/ 에 기존 성공 결과 유지
```

### Gate 중단 후 재실행

```
- 사용자가 Step 1에서 "중단" 선택 후 Jira/코드 수정
- 재실행 시 Step 0부터 다시 시작
- 이전 실행의 시트/매핑은 Step 2/4에서 자동 판정
```

### Manual Report 재생성

```
- partial_results/ 는 있지만 최종 보고서 생성 실패 시
- Trigger: "PROJ-456 결과 리포트 다시 생성해줘"
- Step 6만 단독 실행 (test-reporter 직접 호출)
```

---

## Related Skills

| 스킬 | 호출 Step | 역할 |
|------|----------|------|
| **test-init** | Step 0 | Workspace 검증, 폴더/파일 초기화 |
| **test-gate** | Step 1 | Jira vs 구현 비교, baseline 결정 |
| **test-plan** | Step 3 | 테스트시트 생성 (jira_digest + code_digest 포함) |
| **test-data** | Step 4 | TC별 데이터 매핑 |
| **test-provisioning** | Step 5 | API 기반 데이터 생성 (Worker) |
| **test-scheduler** | Step 5 | DAG 기반 실행 계획 수립 |
| **test-reporter** | Step 6 | 결과 집계 및 보고서 생성 |
| **test-review-agent** | Step 6.5 | 보고서 의미적 검증 (커버리지, 근거 품질, 일관성, 누락) |
| **test-post** | Step 7 | 후처리 액션 (Confluence 업로드, Jira 코멘트 등) |
| **test-evidence** | 참조 | Pass/Fail 근거 작성 가이드 |
