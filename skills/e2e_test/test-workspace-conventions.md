# Workspace Conventions

This skill uses project-relative conventions with a two-location architecture.

## Service Metadata Provider

Before metadata-driven analysis, resolve `ctx.service_metadata`.

- `ctx.service_metadata` describes how service metadata is obtained, not which skill produced it.
- Supported provider types: `file`, `cli`, `rag`, `mcp`
- Ask the user for provider information only when it is not already discoverable from project context.
- Preferred file location, when a file provider exists: `./.architecture/`
- Store and reuse a structure like:

```json
{
  "provider_type": "file|cli|rag|mcp",
  "location": "./.architecture/",
  "query_interface": "provider-specific query entrypoint",
  "capabilities": ["services", "dependencies", "db_schema", "data_contracts", "flows"],
  "freshness": "static|generated|live"
}
```

- If no service metadata provider exists, continue with source-direct analysis.

> ctx.service_metadata 없을 때 폴백 순서:
> 1. Glob(`{ticket_folder}/*_service_metadata.json`) → 최신 파일 사용
> 2. 파일도 없으면: 사용자에게 서비스 정보 요청 (provider name, base URL 최소 수집)

## Directory Architecture

```text
<project-root>/
  test/                              ← Test execution resources + output
    _shared/                         ← Shared env/domain knowledge (per project)
      test_concerns.md
      env/
        url.md                       ← Service URLs per environment
        execution_rules.md           ← LLM test execution rules
        accounts.md                  ← Test credentials per role
        api_endpoints.md             ← Service API list per project
        permissions.json             ← Claude Code permission mapping per project (DB tools, UI tools, etc.)
      domain/
        {domain_name}.md
      rule/                          ← Error prevention rules per project
        _caution_mcp_usage.md        ← Project MCP tool usage
        _caution_missing_tables.json ← Project DB table omission info
        _caution_common_errors.md    ← Project recurring error patterns
        _caution_error_candidates.json ← Project error candidates
        examples/                    ← Evidence writing examples per project
  # examples file location: test/examples/ (not test/_shared/rule/examples/)
  # Reference: test-evidence.md, _guidelines_test_evidence.md
    _post.md                         ← (Optional) Post-processing action definition after test completion
    templates/                       ← Test sheet/result templates
      README.md
      test_sheet_template.md
      test_result_template.md
      report_template.md
    examples/                        ← 작성 예시
    TICKET-123_FeatureName/          ← Per-ticket output folder (example)
      TICKET-123_test_sheet_v1.md
      TICKET-123_gate_{ts}.json
      TICKET-123_data_mapping.json      ← [SSOT] Structure signatures + sample file links
      TICKET-123_report_test_result.md
      samples/                     ← Input samples (Excel, etc.) accumulation folder
      partial_results/             ← [TEMP] Execution status (Reset on restart)

  $CLAUDE_PLUGIN_ROOT/skills/e2e_test/               ← Test skill definitions (범용 — 프로젝트 무관)
    rules/                           ← Claude 전용 범용 실행 규칙
      _guidelines_test_evidence.md   ← Pass/Fail 근거 작성 프레임워크 (범용)
      _report_format_rules.md        ← 보고서 출력 포맷 규칙 (범용)
      _test_permissions.json         ← 권한 범주 정의 (범용 구조, 프로젝트 config 참조)
```

---

## Ticket Folder Resolution (필수 — 프로그램화된 규칙)

> **원칙**: 모든 테스트 산출물은 반드시 `test/{ticket}_{feature}/` 폴더 안에서만 읽고 쓴다.
> 이 규칙은 test-run Step 0에서 **가장 먼저** 실행되며, 해석(resolution) 결과를 `ctx.ticket_folder`에 저장한다.
> 이후 모든 Step은 `ctx.ticket_folder`만 사용한다.

### Ticket Identity Principle (티켓 동일성 원칙)

> **1 Ticket = 1 Folder**: 티켓 ID가 같으면 반드시 같은 폴더를 사용한다.
> feature명(`_{feature}` 접미사)은 사람이 읽기 위한 라벨이며, 폴더 식별에 사용하지 않는다.

```
폴더 구조:  test/{ticket_id}_{feature}/
식별 키:         ^^^^^^^^^^^  ← 이것만 비교
라벨:                         ^^^^^^^^^  ← 무시 (표시용)

예시:
  "TICKET-123 테스트해줘"           → ticket_id = "TICKET-123" → test/TICKET-123_*/
  "TICKET-123_FeatureA 테스트"      → ticket_id = "TICKET-123" → test/TICKET-123_*/  (동일!)
  "TICKET-123 Description 테스트"  → ticket_id = "TICKET-123" → test/TICKET-123_*/  (동일!)
```

### RESOLVE(input) 알고리즘

```
FUNCTION resolve_ticket_folder(input: string) → string:

  ━━━ STEP 0: 티켓 ID 정규화 (Normalize) ━━━

  # 입력에서 티켓 ID 패턴만 추출 (설명, 구분자 등 제거)
  # 규칙: 하이픈(-) 뒤의 숫자가 끝나는 지점까지만 ID로 간주 (숫자 종결성 원칙)
  ticket_id = extract_ticket_pattern(input)
  # 정규식: /([A-Z]+-\d+)(?!\d)/  (대소문자 무시 검색 후 대문자 변환)
  #
  # 예시:
  #   "WO-55"                    → "WO-55"
  #   "WO-55_할당해제"            → "WO-55"
  #   "ABC-1234A_테스트"          → "ABC-1234" (A는 숫자가 아니므로 제외)
  #   "wo-55"                    → "WO-55"
  #
  # 매치 실패 → ERROR("유효한 티켓 ID를 찾을 수 없습니다: {input}")

  ━━━ STEP 1: 검색 (기존 폴더 재사용 우선) ━━━

  # 1. 티켓 ID로 시작하는 모든 폴더 검색
  candidates = Glob("test/{ticket_id}*", path=project_root, type=directory)
  
  # 2. 정확한 매칭 필터링 (ABC-123 검색 시 ABC-1234 제외)
  # 정규식: ^{ticket_id}(?!\d)
  valid = []
  FOR each path IN candidates:
    name = basename(path)
    IF regex_match(name, "^{ticket_id}(?!\d)"):
      valid.append(path)

  ━━━ STEP 2: 판정 및 생성 ━━━

  CASE len(valid) >= 1:
    # 가장 먼저 생성된 폴더 또는 가장 짧은 이름의 폴더를 대표 폴더로 선택
    # (이미 존재하면 무조건 재사용하여 1 Ticket = 1 Folder 유지)
    → RETURN valid[0]

  CASE len(valid) == 0:
    # 새 폴더 생성 시 사용자가 입력한 설명(feature)이 있다면 포함
    feature = extract_feature_suffix(input) # ticket_id 이후의 문자열
    IF feature:
      folder = "test/{ticket_id}_{feature}/"
    ELSE:
      folder = "test/{ticket_id}/"
      
    → mkdir -p folder
    → mkdir -p folder/partial_results
    → RETURN folder
```

### ctx.ticket_folder 사용 규칙

> 파일 선택 기준: 동일 패턴의 파일이 여러 개 존재할 때, 파일명의 YYYYMMDD_HHmmss 타임스탬프 문자열 기준으로 가장 최신 파일을 사용한다. (OS 파일 수정 시간이 아닌 파일명 기준)

```
설정 시점: test-run Step 0 (Folder Resolution)
사용 범위: Step 0 이후 모든 Step

사용 예시:
  게이트 결과 저장    → {ctx.ticket_folder}/{ticket}_gate_{timestamp}.json
  테스트시트 검색     → {ctx.ticket_folder}/{ticket}_test_sheet_v*.md
  데이터매핑 검색     → {ctx.ticket_folder}/{ticket}_data_mapping.json
  부분 결과 저장      → {ctx.ticket_folder}/partial_results/{TC_ID}.json
  테스트 결과 보고서  → {ctx.ticket_folder}/{ticket}_report_test_result_v{N}.{M}_{date}.md
  스크린샷            → {ctx.ticket_folder}/screenshots/{ticket}_SC_{TC}_{date}.png
```

---

## IO Scope Enforcement (필수 — 프로그램화된 규칙)

> **원칙**: 테스트 산출물의 읽기/쓰기는 명시적으로 허용된 경로에서만 수행한다.
> 아래 테이블에 없는 경로는 **접근 금지**이다.

### 허용 경로 (Allowlist)

| 경로 | 접근 | 용도 | 로드 시점 |
|------|------|------|----------|
| `test/_shared/env/**` | READ ONLY | Env, accounts, domain knowledge | Loaded by each subagent per dependencies |
| `test/_post.md` | READ ONLY | Post-processing action defs | Step 7 |
| `test/templates/**` | READ ONLY | Sheet/Result templates | Step 0 (scaffold), Step 3 (test sheet gen) |
| `test/examples/**` | READ ONLY | Reference examples | As needed |
| `$CLAUDE_PLUGIN_ROOT/skills/e2e_test/rules/**` | READ ONLY | Generic execution rules | Step 5 (_guidelines_test_evidence.md), Step 6 (_report_format_rules.md) |
| `{ctx.ticket_folder}/**` | READ + WRITE | Test artifacts | After Step 0 |

### 금지 경로 (Denylist)

| 패턴 | 금지 사유 |
|------|----------|
| `test/backup/**` | 아카이브 영역 — 현재 테스트와 무관 |
| `test/{other_ticket}*/` | 다른 티켓의 산출물 — 교차 오염 방지 |
| `test/_shared/**` (WRITE) | 공유 리소스 수정 금지 |
| `test/templates/**` (WRITE) | 템플릿 수정 금지 |
| `{project_root}/**` (WRITE, test/ 외부) | 테스트 폴더 외부 쓰기 금지 |

### 경로 검증 함수

> WRITE는 ctx.ticket_folder 안에서만, READ는 위 Allowlist 경로에서만 허용. 위반 시 즉시 오류.

---

## `_`-Prefixed Rules

- **Folders** starting with `_` are rule/config zones. Never write test outputs into them.
- **Files** starting with `_` are mandatory docs that must be loaded before execution.


## Runtime Preflight (서브에이전트별 로드)

> **원칙**: Main agent는 _shared/ 파일을 직접 로드하지 않는다.
> 각 서브에이전트가 자신의 `## _shared/ Dependencies` 선언에 따라 필요한 파일만 로드한다.

| Step | 처리 방식 | 로드하는 _shared/ 파일 |
|------|-----------|----------------------|
| Step 0 (Init) | Subagent | env/permissions.json |
| Step 1 (Gate) | Main (Interactive) | env/url.md, env/api_endpoints.md |
| Step 3 (Plan) | Subagent | test_concerns.md, domain/{related}.md |
| Step 4 (Data) | Subagent | test_concerns.md, env/url.md, env/api_endpoints.md, rule/_caution_*.md/.json |
| Step 5 (Execute) | Main (Interactive) | env/url.md, env/execution_rules.md, env/accounts.md, env/api_endpoints.md |
| Step 6 (Report) | 서브에이전트 | rules/_report_format_rules.md  (Main이 Step 6 진입 시 로드, reporter subagent 상속) |

> `rules/` 범용 파일도 동일 원칙: _guidelines_test_evidence.md → Step 5만, _report_format_rules.md → Step 6만.

> `_caution_common_errors.md`는 test-data.md(Step 1) 진입 시점에 로드된다.
> test-init.md, test-plan.md, test-gate.md는 이 파일을 로드하지 않는다.

---


## Output Conventions

> **전제**: 아래 모든 경로는 `{ctx.ticket_folder}/` 하위이다.

- 티켓 폴더: `test/{ticket}_{feature}/`
- 게이트 결과: `{ticket}_gate_{YYYYMMDD_HHmmss}.json`
- 테스트시트: `{ticket}_test_sheet_v{N}_{YYYY-MM-DD}.md`
- 데이터매핑: `{ticket}_data_mapping.json` ← 구조 시그니처 포함
- 샘플 폴더: `samples/` ← 모든 버전의 샘플 누적
- TC 계약 명세: `{ticket}_tc_spec.json`
- Mermaid URL 맵: `.mermaid_urls_{ticket}.json`
- 결과 리포트: `{ticket}_report_test_result_v{N}.{M}_{YYYY-MM-DD}.md`
- 부분 결과: `partial_results/{TC_ID}.json`
- 스크린샷: `screenshots/{ticket}_SC_{TC}_{date}.png`

## Write-Through 원자적 쓰기 규칙

서브에이전트 크래시로 인한 불완전 파일 생성을 방지한다:

```
임시 파일로 쓰고 완료 후 rename (OS의 atomic rename 보장):
  1. write({ticket}_data_mapping.json.tmp)   ← Writing
  2. rename(→ {ticket}_data_mapping.json)    ← Atomic replace

파일이 .tmp 없이 존재하면 항상 완전한 상태임이 보장됨.
```

적용 대상: gate.json, test_sheet.md, data_mapping.json, execution_plan.json, partial_results/*.json
