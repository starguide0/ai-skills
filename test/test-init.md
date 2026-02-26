---
name: test-init
description: |
  Workspace initialization skill. Validates test folder structure, generates boilerplate/scaffold files,
  and checks readiness before test execution begins.
  Called automatically by test-run Step 0, or manually for new project setup.
version: 1.2.1
---

# Test Init — Workspace Initialization

## Purpose

프로젝트별 `test/` 폴더의 존재 유무, 필수 구조, 필수 파일의 유효성을 검증하고,
누락된 항목은 보일러플레이트 또는 스캐폴드로 자동 생성합니다.

> **호출 시점**: test-run의 Step 0에서 리소스 로딩 전에 실행됩니다.
> 단독으로도 호출 가능합니다 ("테스트 환경 초기화해줘").

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| project_root | 자동 감지 | N | 현재 작업 디렉토리 기준으로 프로젝트 루트 탐색 (.git, CLAUDE.md, build 파일 등) |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| init_status | test-run (Step 0.1) | READY\|CREATED\|NEEDS_INPUT\|NOT_READY |
| ctx.project_root | test-run, test-workspace-conventions | 감지된 프로젝트 루트 경로 |
| ctx.test_root | test-run, test-plan, test-data | {project_root}/test 경로 |
| ctx.ticket_folder | test-run (Step 0.1.5) | RESOLVE()에서 결정된 티켓별 폴더 경로 |

> ※ ctx.ticket_folder 설정 주체:
>    - 정상 파이프라인(test-run → test-init → test-gate → test-plan): test-run이 Step 0.1.5에서 최초 설정
>    - test-init standalone 실행: test-init이 Step 5 (Setup Wizard) 또는 Step 3에서 직접 설정
>    - 항상 $CLAUDE_PROJECT_DIR 기준 절대 경로

| created[] | 사용자 알림 | 새로 생성된 폴더/파일 목록 |
| scaffolded[] | 사용자 알림 | {TODO} 플레이스홀더를 포함하여 생성된 파일 목록 |
| protected[] | 사용자 알림 | 기존 내용이 보존된 파일 목록 (보호 규칙 적용) |
| auto_filled[] | 사용자 알림 | Setup Wizard가 자동 채움한 파일 목록 (Step 5) |
| integration_profile | test-run (Step 0.3) | 감지된 연동 프로필 (db, auth, web_ui, api, issue_tracker) |
| scaffold_manifest | INTERNAL | 프로파일 기반 조건부 생성 대상 (boilerplate, scaffold, skip) |
| ctx.pending_permissions | test-run (Step 0.3) | Setup Wizard 결과로 추가 필요한 권한 목록 |
| needs_input[] | 사용자 알림 | {TODO} 항목이 남아있는 파일 목록 (파일명 + TODO 개수) |
| errors[] | 사용자 알림 | 복구 불가능한 오류 목록 |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- 디렉토리 검증 로직 (필수 폴더 목록: test/, test/_shared/, test/_shared/환경/, test/_shared/도메인/, test/templates/, test/examples/)
- 프로젝트 프로파일 분석 로직 (Step 3: MCP 도구 스캔, 아키텍처 메타데이터 스캔, 기존 설정 스캔)
- 조건부 파일 생성 로직 (Step 4: scaffold_manifest 기반)
- 보일러플레이트 파일 생성 로직 (테스트_주의사항.md, README.md, 테스트시트_템플릿.md)
- 스캐폴드 파일 생성 로직 (URL.md, 실행_규칙.md, 계정.md, API_엔드포인트.md, permissions.json 등)
- {TODO} 플레이스홀더 패턴 검색 로직 ({TODO}, {TODO:...}, <!-- TODO -->)
- Step 5: Setup Wizard (NEEDS_SETUP 항목에 대한 사용자 대화형 설정)

---

## Trigger Examples

### 한글
- "테스트 환경 초기화해줘"
- "테스트 폴더 세팅해줘"
- "테스트 workspace 준비"

### 영어
- "Initialize test workspace"
- "Setup test environment"
- "Bootstrap test folder"

---

## Output

```json
{
  "status": "READY | CREATED | NEEDS_INPUT | NOT_READY",
  "project_root": "<detected project root>",
  "test_root": "<project_root>/test",
  "created": ["_shared/", "templates/", ...],
  "scaffolded": ["_shared/환경/URL.md", "_shared/환경/실행_규칙.md", ...],
  "protected": ["_shared/환경/ARGO_테스트_계정.md (기존 내용 보존)", ...],
  "auto_filled": ["permissions.json (DB 5개 자동)", "API_엔드포인트.md (서비스 7개 자동)", ...],
  "integration_profile": {
    "db": {"detected": true, "tools": 5, "config_status": "CONFIGURED"},
    "auth": {"detected": true, "needs_credentials": false},
    "web_ui": {"detected": true, "tools": 13, "config_status": "CONFIGURED"},
    "api": {"detected": true, "services": 7, "config_status": "CONFIGURED"},
    "issue_tracker": {"detected": true, "tools": 4, "config_status": "CONFIGURED"}
  },
  "scaffold_manifest": {
    "boilerplate": ["_shared/테스트_주의사항.md", ...],
    "scaffold": ["환경/URL.md", "환경/실행_규칙.md", "환경/permissions.json", ...],
    "skip": [{"file": "환경/API_엔드포인트.md", "reason": "서비스 미감지"}]
  },
  "needs_input": ["_shared/환경/계정.md (TODO 3건)", ...],
  "errors": []
}
```

### Status 정의

| Status | 의미 | 다음 행동 |
|--------|------|----------|
| **READY** | 모든 필수 항목 존재 + 유효 | 즉시 리소스 로딩 진행 |
| **CREATED** | 누락 항목을 생성함 (보일러플레이트) | 사용자에게 생성 내역 알림 후 진행 |
| **NEEDS_INPUT** | 스캐폴드 파일에 `{TODO}` 남아있음 | 사용자에게 입력 요청 후 재검증 |
| **NOT_READY** | 복구 불가능한 오류 | 사용자에게 수동 조치 요청 |

---

## Execution Steps

### Step 1: 프로젝트 루트 감지

```
1. 현재 작업 디렉토리 기준으로 프로젝트 루트 탐색
   - .git 존재 여부
   - CLAUDE.md 존재 여부
   - package.json / build.gradle / pom.xml 존재 여부

2. 프로젝트 루트 확정:
   - ctx.project_root = 감지된 루트
   - ctx.test_root = ctx.project_root + "/test"
```

### Step 2: 폴더 구조 검증 및 생성

```
필수 폴더 목록:
  test/
  test/_shared/
  test/_shared/환경/
  test/_shared/도메인/
  test/_shared/rule/
  test/templates/
  test/examples/

FOR each 필수 폴더:
  IF 존재하지 않음:
    → mkdir -p {폴더}
    → created[] 에 추가
```

### 2.1 티켓 폴더 검증 (ticket_id가 주어진 경우)

> 티켓 폴더는 test-init 단독 호출 시에는 생성하지 않는다.
> test-run의 Step 0.1.5 (Ticket Folder Resolution)에서 생성한다.
> test-init은 기존 티켓 폴더가 있을 경우 하위 구조만 검증한다.

```
IF ticket_id 제공됨 AND ctx.ticket_folder 존재:
  필수 하위 폴더:
    {ctx.ticket_folder}/partial_results/

  FOR each 필수 하위 폴더:
    IF 존재하지 않음:
      → mkdir -p {폴더}
      → created[] 에 추가
```

### Step 3: 프로젝트 프로파일 분석 (자동 — 판단 없음)

> **원칙**: 프로젝트 환경을 먼저 분석하여 어떤 스캐폴드가 필요한지 결정한 후,
> 필요한 파일만 생성한다. 불필요한 파일은 생성하지 않는다.

#### Phase A: Integration Detection (자동 — 판단 없음)

프로젝트 환경을 스캔하여 `integration_profile`을 생성한다.

```
FUNCTION detect_integrations() → integration_profile:

  ━━━ A-1: MCP 도구 스캔 ━━━

  available_tools = ListMcpResourcesTool() 또는 도구 목록 확인
  # 사용 가능한 MCP 도구를 카테고리별로 분류

  detected = {
    db: [],         # mcp__postgres_*  패턴
    ui: [],         # mcp__playwright_*  패턴
    issue_tracker: [],  # mcp__atlassian_*  패턴
    event: []       # mcp__kafka_*  패턴 (있으면)
  }

  FOR each tool IN available_tools:
    IF tool.matches("mcp__postgres_*__query"):
      service_name = extract between "mcp__postgres_" and "__query"
      detected.db.append({tool: tool, service: service_name})
    IF tool.matches("mcp__playwright__*"):
      detected.ui.append({tool: tool})
    IF tool.matches("mcp__atlassian__*"):
      detected.issue_tracker.append({tool: tool})

  ━━━ A-2: 아키텍처 메타데이터 스캔 ━━━

  arch = {}
  IF exists(".claude/architecture/services.json"):
    arch.services = parse(services.json)  # 서비스 목록, 기술 스택
  IF exists(".claude/architecture/db-schemas/"):
    arch.databases = list(db-schemas/*.json)  # DB 스키마 파일 목록
  IF exists(".claude/architecture/api-dependencies.json"):
    arch.apis = parse(api-dependencies.json)  # API 관계

  ━━━ A-3: 기존 설정 스캔 ━━━

  existing_config = {}
  FOR each scaffold_file IN ["환경/계정.md", "환경/API_엔드포인트.md", "환경/permissions.json", ...]:
    file = find_matching_file(scaffold_file)  # 유사 파일명 포함
    IF file exists AND NOT is_todo_only(file):
      existing_config[scaffold_file] = "CONFIGURED"
    ELSE:
      existing_config[scaffold_file] = "NEEDS_SETUP"

  ━━━ A-4: integration_profile 생성 ━━━

  RETURN {
    db: {
      detected: len(detected.db) > 0,
      tools: detected.db,
      databases: arch.databases or [],
      config_status: existing_config["환경/permissions.json"]
    },
    auth: {
      detected: true,  # 모든 프로젝트에 인증 필요로 간주
      needs_credentials: existing_config["환경/계정.md"] == "NEEDS_SETUP"
    },
    web_ui: {
      detected: len(detected.ui) > 0,
      tools: detected.ui,
      config_status: existing_config["환경/permissions.json"]
    },
    api: {
      detected: len(arch.services) > 0 OR existing_config["환경/API_엔드포인트.md"] == "CONFIGURED",
      services: arch.services or [],
      config_status: existing_config["환경/API_엔드포인트.md"]
    },
    issue_tracker: {
      detected: len(detected.issue_tracker) > 0,
      tools: detected.issue_tracker,
      config_status: existing_config["환경/permissions.json"]
    },
    event: {
      detected: len(detected.event) > 0,
      tools: detected.event or [],
      config_status: "N/A"  # 이벤트 도구는 별도 설정 파일 없음
    }
  }
```

#### Phase B: Requirements Derivation (자동 — 판단 없음)

감지된 프로파일을 기반으로 어떤 파일을 생성할지 결정한다.

```
FUNCTION derive_requirements(profile: integration_profile) → scaffold_manifest:

  manifest = {
    boilerplate: [],    # 항상 생성 (프로젝트 무관)
    scaffold: [],       # 조건부 생성 (프로파일 기반)
    skip: [],           # 명시적 건너뜀 (이유 포함)
  }

  ━━━ Boilerplate (항상 생성) ━━━
  manifest.boilerplate = [
    "test/_shared/테스트_주의사항.md",
    "test/templates/README.md",
    "test/templates/테스트시트_템플릿.md",
    "test/templates/테스트결과_템플릿.md",
    "test/templates/Confluence_테스트결과_템플릿.md"
  ]

  ━━━ Scaffold (조건부 생성) ━━━

  # 환경 파일 — 항상 필요 (기본)
  manifest.scaffold.append("환경/URL.md")        # 모든 프로젝트
  manifest.scaffold.append("환경/실행_규칙.md")   # 모든 프로젝트

  # 인증/계정 — 항상 필요 (기본)
  manifest.scaffold.append("환경/계정.md")

  # API 엔드포인트 — 서비스가 감지되면
  IF profile.api.detected:
    manifest.scaffold.append("환경/API_엔드포인트.md")
  ELSE:
    manifest.skip.append({file: "환경/API_엔드포인트.md", reason: "서비스 미감지"})

  # permissions.json — MCP 도구가 하나라도 감지되면
  IF profile.db.detected OR profile.web_ui.detected OR profile.issue_tracker.detected:
    manifest.scaffold.append("환경/permissions.json")
    # permissions.json 내 섹션도 조건부:
    manifest.permissions_sections = {
      db_tools: profile.db.detected,
      ui_tools: profile.web_ui.detected,
      issue_tracker_tools: profile.issue_tracker.detected,
      event_tools: profile.event.detected  # kafka 등
    }
  ELSE:
    manifest.skip.append({file: "환경/permissions.json", reason: "MCP 도구 미감지"})

  # MCP 사용 가이드 — DB MCP가 있으면
  IF profile.db.detected:
    manifest.scaffold.append("rule/_caution_mcp_usage.md")
  ELSE:
    manifest.skip.append({file: "rule/_caution_mcp_usage.md", reason: "DB MCP 미감지"})

  # 오류 패턴 — 항상 생성 (프로젝트 운영 중 축적)
  manifest.scaffold.append("rule/_caution_common_errors.md")
  manifest.scaffold.append("rule/_caution_missing_tables.json")
  manifest.scaffold.append("rule/_caution_error_candidates.json")

  RETURN manifest
```

#### Phase C: 분석 결과 출력

```
사용자에게 분석 결과를 출력한다 (판단이나 질문 없이 정보만 제공):

"━━━ 프로젝트 프로파일 분석 결과 ━━━

 감지 항목          상태     근거
 ──────────────────────────────────────
 DB (PostgreSQL)   ✅ 감지   mcp__postgres_* 5개
 Web UI            ✅ 감지   mcp__playwright_* 13개
 Issue Tracker     ✅ 감지   mcp__atlassian_* 4개
 Event (Kafka)     ❌ 미감지  mcp__kafka_* 없음
 API Services      ✅ 감지   architecture/services.json 7개
 Auth              ✅ 필요   기본 (모든 프로젝트)

 생성 대상:
   ✅ 보일러플레이트: 5개 (공통 파일)
   ✅ 스캐폴드: 7개 (조건 충족)
   ⏭️ 건너뜀: 1개 (조건 미충족)
     - 환경/Kafka_토픽.md → Event 도구 미감지"

integration_profile과 scaffold_manifest를 ctx에 저장
```

### Step 4: 조건부 파일 생성

> **Step 3에서 생성한 scaffold_manifest 기반으로 필요한 파일만 생성한다.**

#### 4.1 보일러플레이트 파일 생성

자동 생성 가능한 공통 파일. 내용이 프로젝트에 무관하게 동일합니다.

```
FOR each file IN manifest.boilerplate:
  IF NOT exists(file):
    → 표준 내용으로 생성
    → created[] 에 추가
  ELSE:
    → 건너뜀 (기존 파일 보존)
```

보일러플레이트 목록:
- `test/_shared/테스트_주의사항.md`
- `test/templates/README.md`
- `test/templates/테스트시트_템플릿.md`
- `test/templates/테스트결과_템플릿.md`
- `test/templates/Confluence_테스트결과_템플릿.md`

#### 4.2 스캐폴드 파일 생성 (조건부)

프로젝트별 설정이 필요한 파일. `{TODO}` 플레이스홀더로 생성됩니다.
**manifest.scaffold에 포함된 파일만 생성합니다.**

```
FOR each file IN manifest.scaffold:
  IF file 존재 (정확히 일치 또는 유사 파일명 매칭):
    IF PROTECTED (기존 내용 보호 규칙 적용):
      → 건너뜀 (기존 내용 보존)
      → protected[] 에 추가
    ELSE:
      → 유효성 검사 (Step 6)
  ELSE:
    → {TODO} 포함된 템플릿으로 생성
    → permissions.json의 경우 manifest.permissions_sections 기반으로 섹션 조건부 포함
    → scaffolded[] 에 추가
```

스캐폴드 목록 (조건부):

> **경로 기준**: 아래 경로는 workspace root (`$CLAUDE_PROJECT_DIR`) 기준 절대 경로입니다.

- `test/_shared/환경/URL.md` (항상)
- `test/_shared/환경/실행_규칙.md` (항상)
- `test/_shared/환경/계정.md` (항상)
- `test/_shared/환경/API_엔드포인트.md` (profile.api.detected)
- `test/_shared/환경/permissions.json` (MCP 도구 감지 시)
- `test/_shared/rule/_caution_mcp_usage.md` (profile.db.detected)
- `test/_shared/rule/_caution_common_errors.md` (항상)
- `test/_shared/rule/_caution_missing_tables.json` (항상)
- `test/_shared/rule/_caution_error_candidates.json` (항상)

#### 4.3 기존 파일 보호 규칙 (Protection Rule)

> **핵심 원칙**: `test/_shared/환경/`과 `test/_shared/rule/`에 이미 유의미한 내용이 있는 파일은
> 절대 덮어쓰거나 내용을 축소하지 않습니다.

**보호 판정 기준**:

```
FOR each 스캐폴드 대상 디렉토리 (환경/, rule/):
  1. 해당 디렉토리의 모든 기존 파일을 수집
  2. 파일명 유사도 매칭 (프로젝트 접두사 허용):
     - 매칭 규칙 (순서대로 적용, 첫 매칭 시 중단):
       a. 정확히 일치: "테스트_계정.md" == "테스트_계정.md"
       b. 접두사 변형: 기존 파일명에서 프로젝트 접두사 제거 후 일치
          예: "ARGO_테스트_계정.md" → "테스트_계정.md" (접두사 "ARGO_" 제거)
       c. 부분 문자열: 스캐폴드 파일명이 기존 파일명의 substring
          예: "테스트_계정" ⊂ "ARGO_테스트_계정_v2.md"
     - 매칭 불가 시: 신규 파일로 간주 (스캐폴드 생성)
  3. 보호 여부 판정:
     IF 기존 파일이 존재하고:
       - 파일 크기 > 0 bytes AND
       - 내용이 {TODO} 플레이스홀더만으로 구성되지 않음
     THEN:
       → PROTECTED (기존 내용 보존, 스캐폴드 생성 건너뜀)
       → protected[] 에 추가
     ELSE:
       → 스캐폴드 생성 대상
```

**금지 행위**:
- 기존 파일의 내용을 요약/축소/삭제하는 행위
- 보안을 이유로 계정 정보 등의 기존 내용을 제거하는 행위
- 기존 파일명을 스캐폴드 정의 파일명으로 변경하는 행위

**허용 행위**:
- 기존 파일에 누락된 섹션을 **추가(append)** 하는 것 (기존 내용 유지 전제)
- 기존 파일의 {TODO} 항목을 사용자 입력으로 채우는 것

### Step 5: Setup Wizard (조건부 — NEEDS_SETUP 항목만 질문)

> **원칙**: "감지 가능한 것은 자동 채움, 감지 불가능한 것만 사용자에게 질문"
> Step 4에서 생성된 scaffold 파일의 {TODO}를 최대한 자동으로 채운다.
> 이미 CONFIGURED된 항목은 건너뛴다.

#### Phase A: 사전 요약

```
감지된 연동 목록을 사용자에게 표시:

"━━━ 설정 대상 확인 ━━━

 연동 유형        감지됨    MCP 도구              설정 상태
 ─────────────────────────────────────────────────────────
 DB (PostgreSQL)  ✅        mcp__postgres_* (5개)  ⚠️ NEEDS_SETUP
 Web UI           ✅        mcp__playwright_* (13개) ✅ CONFIGURED
 Issue Tracker    ✅        mcp__atlassian_* (4개)  ✅ CONFIGURED
 API              ✅        (arch 기반)             ⚠️ NEEDS_SETUP
 Auth             ✅        —                       ⚠️ NEEDS_SETUP

 ⚠️ 3개 항목의 설정이 필요합니다."

감지-권한 카테고리 매핑:

| Wizard 감지 항목 | permissions.json 카테고리 | 조건 |
|-----------------|------------------------|------|
| DB (PostgreSQL) | db_tools | profile.db.detected |
| Web UI | ui_tools | profile.web_ui.detected |
| Issue Tracker | issue_tracker_tools | profile.issue_tracker.detected |
| Event (Kafka) | event_tools | profile.event.detected |
| Auth | (계정.md) | 항상 필요 |
| API | (API_엔드포인트.md) | profile.api.detected |

AskUserQuestion:
  "설정이 필요한 항목을 지금 구성하시겠습니까?"
  [1] 전체 설정 (권장) — 모든 NEEDS_SETUP 항목을 순차 안내
  [2] 선택 설정 — 원하는 항목만 선택
  [3] 나중에 설정 — TODO 상태 유지, NEEDS_INPUT으로 반환

IF [3] → RETURN (Step 6으로 진행, TODO 유지)
IF [2] → 사용자가 선택한 항목만 아래 Case 실행
IF [1] → 모든 NEEDS_SETUP 항목에 대해 아래 Case 순차 실행
```

#### Phase B: 항목별 설정 (NEEDS_SETUP만)

```
━━━ B-1: DB 연동 설정 ━━━

IF profile.db.config_status == "NEEDS_SETUP":

  IF profile.db.detected:
    # MCP 도구가 이미 있음 — 자동 채움 가능
    "DB 연동: MCP PostgreSQL 도구 {N}개 감지됨"
    감지된 도구 목록 표시:
      mcp__postgres_outbound__query → wms_outbound
      mcp__postgres_job__query → wms_job
      ...

    AskUserQuestion:
      "감지된 MCP DB 도구로 permissions.json을 구성할까요?"
      [1] 자동 구성 (권장) — 감지된 도구 기반으로 자동 채움
      [2] 수동 입력 — 직접 도구명/DB명 입력
      [3] 건너뛰기

    IF [1]:
      → permissions.json의 db_tools 섹션 자동 채움
      → _caution_mcp_usage.md의 MCP 도구 → DB 매핑 테이블 자동 채움
      → auto_filled[] 에 추가

  ELSE:
    # MCP 도구 없음 — 연결 방법 문의
    AskUserQuestion:
      "DB 접근 방법을 선택해주세요"
      [1] MCP PostgreSQL 서버 추가 설정 — .mcp.json 또는 설정 안내
      [2] 직접 연결 (connection string) — 수동 설정
      [3] DB 검증 사용 안함

    IF [1]:
      → MCP 서버 설정 가이드 출력 (서비스별 연결 정보 입력 안내)
    IF [2]:
      → connection string 입력 요청
    IF [3]:
      → db_tools를 빈 배열로 설정

━━━ B-2: 인증/계정 설정 ━━━

IF profile.auth.needs_credentials:

  AskUserQuestion:
    "테스트 계정 정보를 설정하시겠습니까?"
    [1] 지금 입력 (권장) — 역할별 계정 정보 순차 입력
    [2] 기존 파일에서 가져오기 — 파일 경로 지정
    [3] 나중에 입력

  IF [1]:
    # 프로젝트 아키텍처 기반으로 필요 역할 추정
    # arch.services는 services.json의 서비스 목록 (list of service objects)
    # 모바일 서비스 감지: type이 "FE_APP"이거나 서비스명에 "mobile", "app"이 포함된 경우
    has_mobile = any(
      s.get("type") == "FE_APP" or 
      any(kw in s.get("name","").lower() for kw in ["mobile", "app", "wms-app"])
      for s in (arch.services or [])
    )
    has_web = any(
      s.get("type") == "FE_WEB" or
      any(kw in s.get("name","").lower() for kw in ["web", "frontend", "front"])
      for s in (arch.services or [])
    )
    IF has_mobile:
      suggested_roles = ["QA 테스터", "모바일 작업자"]
    ELIF has_web:
      suggested_roles = ["QA 테스터", "관리자"]
    ELSE:
      suggested_roles = ["QA 테스터"]

    FOR each role IN suggested_roles:
      AskUserQuestion: "{role} 계정의 아이디를 입력해주세요"
      AskUserQuestion: "{role} 계정의 비밀번호를 입력해주세요"
      AskUserQuestion: "인증 API 엔드포인트를 입력해주세요 (예: https://api.example.com/auth/login)"
    → 계정.md 업데이트
    → auto_filled[] 에 추가

  IF [2]:
    → 파일 경로 입력 → 내용 파싱 → 계정.md 자동 채움

━━━ B-3: API 엔드포인트 설정 ━━━

IF profile.api.config_status == "NEEDS_SETUP":

  IF arch.services exists:
    # 아키텍처에서 서비스 목록 자동 추출
    "서비스 {N}개 감지됨 (architecture/services.json 기반)"
    서비스 목록 표시

    AskUserQuestion:
      "감지된 서비스 목록으로 API 엔드포인트 파일을 구성할까요?"
      [1] 자동 구성 (권장) — 서비스명 기반 URL 패턴 생성
      [2] 수동 입력 — 직접 서비스/URL 입력
      [3] 건너뛰기

    IF [1]:
      → 서비스별 Base URL 테이블 자동 생성
      → URL 패턴은 "{service}-api.{domain}" 형태로 추정
      → 사용자에게 도메인 입력 요청 (예: argoport.co)
      → API_엔드포인트.md 업데이트

  ELSE:
    → 수동 입력 안내

━━━ B-4: Web UI 설정 ━━━

IF profile.web_ui.detected AND profile.web_ui.config_status == "NEEDS_SETUP":

  "Web UI 테스트: Playwright MCP 도구 {N}개 감지됨"

  AskUserQuestion:
    "Web UI 테스트를 활성화할까요?"
    [1] 활성화 (권장) — Playwright 도구를 permissions.json에 등록
    [2] 비활성화 — Web UI 캡처 사용 안함

  IF [1]:
    → permissions.json의 ui_tools 섹션에 감지된 도구 추가
    → settings_template에도 추가
    → 사용자에게 Web UI URL 입력 요청 (예: https://deploy-test.wms.argoport.co)

━━━ B-5: Issue Tracker 설정 ━━━

IF profile.issue_tracker.detected AND profile.issue_tracker.config_status == "NEEDS_SETUP":

  "Issue Tracker: Atlassian MCP 도구 {N}개 감지됨"

  AskUserQuestion:
    "Jira/Confluence 연동을 활성화할까요?"
    [1] 활성화 (권장) — Atlassian 도구를 permissions.json에 등록
    [2] 비활성화 — Jira 수동 확인

  IF [1]:
    → permissions.json의 issue_tracker_tools 섹션에 감지된 도구 추가
```

#### Phase C: Auto-Configure (자동 — 판단 없음)

```
FUNCTION apply_configuration(wizard_results):

  ━━━ C-1: Scaffold 파일 업데이트 ━━━

  FOR each result IN wizard_results WHERE action != "SKIP":
    target_file = resolve scaffold file path
    Read(target_file)
    Replace {TODO} placeholders with wizard_results values
    Write(target_file)
    auto_filled[] 에 추가

  ━━━ C-2: settings.local.json 연동 제안 ━━━

  IF permissions.json가 업데이트됨:
    new_permissions = permissions.json의 settings_template.permissions_allow
    current_settings = Read(".claude/settings.local.json")

    missing = new_permissions - current_settings.permissions.allow
    IF missing 존재:
      "permissions.json 기반으로 settings.local.json에 {N}개 권한을 추가할 수 있습니다."
      # test-run Step 0.3 (Permission Scope 사전 검증)에서 처리하도록 위임
      → ctx.pending_permissions = missing

  ━━━ C-3: 결과 요약 ━━━

  "━━━ Setup Wizard 완료 ━━━
   ✅ 자동 구성: {auto_filled 목록}
   ⏭️ 건너뜀: {skipped 목록}
   ⚠️ 수동 필요: {remaining_todos 목록}"
```

---

### Step 6: 파일 유효성 검증

```
FOR each 기존 파일 + 새로 생성된 스캐폴드 파일:
  1. 빈 파일 검사 (0 bytes)
  2. {TODO} 플레이스홀더 검색
     - 패턴: {TODO}, {TODO:...}, <!-- TODO -->

  IF {TODO} 발견:
    → needs_input[] 에 추가
    → "{파일명} (TODO {N}건)" 형식으로 기록
```

### Step 7: 판정 및 출력

```
IF errors 존재:
  status = "NOT_READY"
ELIF needs_input 존재:
  status = "NEEDS_INPUT"
ELIF created 또는 scaffolded 존재:
  status = "CREATED"
ELSE:
  status = "READY"

결과를 사용자에게 출력:

┌─ Test Init 결과 ──────────────────────────────┐
│ Status: {status}                               │
│ Project: {project_root}                        │
│ Test Root: {test_root}                         │
│                                                │
│ ✅ 존재: _shared/, templates/, ...             │
│ 📁 생성: _shared/도메인/ (새로 생성)            │
│ 🔒 보호: 환경/ARGO_테스트_계정.md (기존 보존)   │
│ 📝 스캐폴드: 환경/계정.md (TODO 3건)           │
│ ⚠️ 입력 필요: 환경/URL.md, 환경/실행_규칙.md   │
└────────────────────────────────────────────────┘
```

---

## Scaffold Templates

> **템플릿 파일 위치**: `$CLAUDE_PROJECT_DIR/.claude/skills/test/templates/_shared/`
> 템플릿 파일이 없을 경우 보일러플레이트 내용으로 직접 생성
> 스캐폴드 생성 시 해당 디렉토리의 `.template` 파일들을 `test/_shared/`로 복사한다.
> 파일명에서 `.template` 확장자를 제거하고 복사. 예: `환경/URL.md.template` → `환경/URL.md`

### 복사 대상 목록

| 템플릿 파일 | 생성되는 파일 | 비고 |
|------------|------------|------|
| `환경/URL.md.template` | `환경/URL.md` | 환경 URL (구: 테스트_환경_공통.md 前半) |
| `환경/실행_규칙.md.template` | `환경/실행_규칙.md` | 실행 규칙 (구: 테스트_환경_공통.md 後半) |
| `환경/계정.md.template` | `환경/계정.md` | 테스트 계정 |
| `환경/API_엔드포인트.md.template` | `환경/API_엔드포인트.md` | API 목록 |
| `환경/permissions.json.template` | `환경/permissions.json` | 권한 매핑 |
| `도메인/{domain}.md.template` | `도메인/{domain}.md` | 감지된 도메인명으로 치환 |
| `rule/_caution_mcp_usage.md.template` | `rule/_caution_mcp_usage.md` | MCP 사용 가이드 |
| `rule/_caution_common_errors.md.template` | `rule/_caution_common_errors.md` | 반복 오류 패턴 |
| `rule/_caution_missing_tables.json.template` | `rule/_caution_missing_tables.json` | 누락 테이블 |
| `rule/_caution_error_candidates.json.template` | `rule/_caution_error_candidates.json` | 오류 후보 |
| `README.md.template` | `README.md` | 파일 구조 지도 |


---

## NEEDS_INPUT 처리

> **Step 5 (Setup Wizard)가 먼저 실행된 후에도 남아있는 {TODO}만 여기서 처리한다.**
> Wizard가 자동 채움한 항목은 이미 해결됨. 여기서는 Wizard에서 "나중에 설정"을 선택했거나,
> Wizard가 채울 수 없는 프로젝트 고유 정보만 다룬다.

status가 `NEEDS_INPUT`일 때의 사용자 인터랙션:

```
1. auto_filled 항목 제외하고 남은 {TODO} 목록 제시:
   "Setup Wizard가 {M}개 항목을 자동 구성했습니다."
   "다음 {N}개 항목에 추가 입력이 필요합니다:"
   - test/_shared/환경/계정.md (TODO 2건: PW)
   - test/_shared/rule/_caution_common_errors.md (TODO 4건: 오류 패턴)

2. 사용자 선택:
   [1] 지금 입력 → 각 {TODO} 항목에 대해 순차적으로 질문
   [2] 나중에 입력 → 파일 위치 안내 후 NEEDS_INPUT 상태로 반환
   [3] 기존 환경 파일 참조 → 경로 입력받아 자동 채움 시도

3. "지금 입력" 선택 시:
   AskUserQuestion으로 각 항목을 질문하여 파일 업데이트
   → 완료 후 재검증 → status 갱신

4. 판정:
   남은 {TODO}가 필수 파일 (환경/계정, API) → NEEDS_INPUT 유지
   남은 {TODO}가 선택 파일 (rule/오류패턴) → CREATED로 격상 (진행 가능)
```

