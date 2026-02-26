# Workspace Conventions

This skill uses project-relative conventions with a two-location architecture.

## Directory Architecture

```text
<project-root>/
  test/                              ← 테스트 실행 리소스 + 출력
    _shared/                         ← 공유 환경/도메인 지식 (프로젝트별)
      테스트_주의사항.md
      환경/
        URL.md                       ← 환경별 서비스 URL
        실행_규칙.md                  ← LLM 테스트 실행 규칙
        계정.md                       ← 역할별 테스트 계정 정보
        API_엔드포인트.md            ← 프로젝트별 서비스 API 목록
        permissions.json             ← 프로젝트별 Claude Code 권한 매핑 (DB 도구, UI 도구 등)
      도메인/
        {도메인명}.md
      rule/                          ← 프로젝트별 에러 방지 규칙
        _caution_mcp_usage.md        ← 프로젝트 MCP 도구 사용법
        _caution_missing_tables.json ← 프로젝트 DB 테이블 누락 정보
        _caution_common_errors.md    ← 프로젝트 반복 오류 패턴
        _caution_error_candidates.json ← 프로젝트 에러 후보
        examples/                    ← 프로젝트별 근거 작성 예시
  # examples 파일 위치: test/examples/ (test/_shared/rule/examples/ 아님)
  # 참조: test-evidence.md, _guidelines_test_evidence.md
    _post.md                         ← (선택) 테스트 완료 후 처리 액션 정의
    templates/                       ← 테스트시트/결과 템플릿
      README.md
      테스트시트_템플릿.md
      테스트결과_템플릿.md
      Confluence_테스트결과_템플릿.md
    examples/                        ← 작성 예시
    ARG-33725_컨테이너SKU그룹화/     ← 티켓별 출력 폴더 (예시)
      ARG-33725_테스트시트_v1.md
      ARG-33725_gate_20260214_153000.json
      ARG-33725_데이터매핑.json
      ARG-33725_Confluence_테스트결과_v1.0.md
      partial_results/

  .claude/skills/test/               ← Test skill definitions (범용 — 프로젝트 무관)
    rules/                           ← Claude 전용 범용 실행 규칙
      _guidelines_test_evidence.md   ← Pass/Fail 근거 작성 프레임워크 (범용)
      _confluence_output_rules.md    ← Confluence 출력 포맷 규칙 (범용)
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
  "WO-55 테스트해줘"           → ticket_id = "WO-55" → test/WO-55_*/
  "WO-55_할당해제NPE수정 테스트" → ticket_id = "WO-55" → test/WO-55_*/  (동일!)
  "WO-55 부분취소 테스트"       → ticket_id = "WO-55" → test/WO-55_*/  (동일!)
```

### RESOLVE(input) 알고리즘

```
FUNCTION resolve_ticket_folder(input: string) → string:

  ━━━ STEP 0: 티켓 ID 정규화 (Normalize) ━━━

  # 입력에서 티켓 ID 패턴만 추출 (feature명, 설명 등 제거)
  ticket_id = extract_ticket_pattern(input)
  # 정규식: /([A-Z][A-Z0-9]*-\d+)/  (첫 번째 매치)
  #
  # 예시:
  #   "WO-55"                    → "WO-55"
  #   "WO-55_할당해제NPE수정"     → "WO-55"
  #   "ARG-33725_컨테이너SKU"    → "ARG-33725"
  #   "wo-55"                    → "WO-55"  (대문자 정규화)
  #
  # 매치 실패 → ERROR("유효한 티켓 ID를 찾을 수 없습니다: {input}")

  ━━━ STEP 1: 검색 (ticket_id만으로 검색) ━━━

  candidates = Glob("test/{ticket_id}*/**", path=project_root)
  # 예: ticket_id="WO-55" → Glob("test/WO-55*/**")
  # → 내부 파일들을 반환하므로, 경로에서 "test/{폴더명}/" 부분을 추출하여 중복 제거
  # ⚠️ Glob은 디렉토리 자체를 반환하지 않으므로 /** 로 내부 파일을 탐색 후 폴더명 추출

  ━━━ STEP 2: 필터링 (자동 — 판단 없음) ━━━

  valid = []
  FOR each candidate IN candidates:
    name = basename(candidate)
    IF name.startsWith("_"):          SKIP  # 규칙 영역
    IF name == "backup":              SKIP  # 백업 영역
    IF name == "examples":            SKIP  # 예시 영역
    IF name contains "backup" OR candidate contains "/backup/":  SKIP  # 백업 관련
    IF NOT name.startsWith(ticket_id + "_") AND name != ticket_id: SKIP  # 다른 티켓 (WO-54로 WO-540 오매칭 방지)
    ELSE: valid.append(candidate)

  ━━━ STEP 3: 판정 (분기 — 조건별 고정 행동) ━━━

  CASE len(valid) == 1:
    → RETURN valid[0]

  CASE len(valid) == 0:
    → feature_name = AskUserQuestion(
        "테스트 폴더를 생성합니다. 기능명을 입력해주세요.",
        header="기능명",
        options=[
          {label: "직접 입력", description: "예: 컨테이너SKU그룹화"}
        ]
      )

    # 입력 검증 (필수)
    → IF feature_name contains any of ["/", "..", "*", "\\", ":", " "]:
        → ERROR("기능명에 특수문자 사용 불가: {feature_name}")
        → 재입력 요청 (AskUserQuestion 재호출)

    → folder = "test/{ticket_id}_{feature_name}/"
    → mkdir -p folder
    → mkdir -p folder/partial_results
    → RETURN folder

  CASE len(valid) > 1:
    # ⚠️ 이상 상태: 1 Ticket = 1 Folder 원칙 위반
    # 사용자에게 경고 + 선택 요청
    → selected = AskUserQuestion(
        "⚠️ 동일 티켓({ticket_id})의 폴더가 {len(valid)}개 있습니다. "
        "1 Ticket = 1 Folder 원칙에 따라 하나만 사용해야 합니다. "
        "사용할 폴더를 선택해주세요.",
        header="폴더 선택",
        options=valid.map(v → {label: basename(v), description: v})
      )
    → RETURN selected

  ━━━ STEP 4: 검증 (assertion — 실패 시 중단) ━━━

  ASSERT result.startsWith("test/")
  ASSERT NOT result.startsWith("test/_")
  ASSERT NOT result.contains("backup")
  ASSERT basename(result).startsWith(ticket_id)
  # 하나라도 실패 → ERROR("Ticket folder validation failed"), 파이프라인 중단
```

### ctx.ticket_folder 사용 규칙

```
설정 시점: test-run Step 0 (Folder Resolution)
사용 범위: Step 0 이후 모든 Step

사용 예시:
  게이트 결과 저장    → {ctx.ticket_folder}/{ticket}_gate_{timestamp}.json
  테스트시트 검색     → {ctx.ticket_folder}/{ticket}_테스트시트_v*.md
  데이터매핑 검색     → {ctx.ticket_folder}/{ticket}_데이터매핑.json
  부분 결과 저장      → {ctx.ticket_folder}/partial_results/{TC_ID}.json
  Confluence 보고서   → {ctx.ticket_folder}/{ticket}_Confluence_테스트결과_v{N.M}_{date}.md
  스크린샷            → {ctx.ticket_folder}/screenshots/{ticket}_SC_{TC}_{date}.png
```

---

## IO Scope Enforcement (필수 — 프로그램화된 규칙)

> **원칙**: 테스트 산출물의 읽기/쓰기는 명시적으로 허용된 경로에서만 수행한다.
> 아래 테이블에 없는 경로는 **접근 금지**이다.

### 허용 경로 (Allowlist)

| 경로 | 접근 | 용도 | 로드 시점 |
|------|------|------|----------|
| `test/_shared/**` | READ ONLY | 환경, 계정, 도메인 지식 | 각 서브에이전트가 자신의 Dependencies 선언에 따라 로드 |
| `test/_post.md` | READ ONLY | 후처리 액션 정의 | Step 7 |
| `test/templates/**` | READ ONLY | 시트/결과 템플릿 | Step 0 (scaffold), Step 3 (테스트시트 생성) |
| `test/examples/**` | READ ONLY | 작성 예시 참조 | 필요 시 |
| `.claude/skills/test/rules/**` | READ ONLY | 범용 실행 규칙 | Step 5 (_guidelines_test_evidence.md), Step 6 (_confluence_output_rules.md) |
| `{ctx.ticket_folder}/**` | READ + WRITE | 테스트 산출물 | Step 0 이후 |

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
| Step 0 (Init) | 서브에이전트 | 환경/permissions.json |
| Step 1 (Gate) | Main (인터랙티브) | 환경/URL.md, 환경/API_엔드포인트.md |
| Step 3 (Plan) | 서브에이전트 | 테스트_주의사항.md, 도메인/{관련}.md |
| Step 4 (Data) | 서브에이전트 | 테스트_주의사항.md, 환경/URL.md, 환경/API_엔드포인트.md, rule/_caution_*.md/.json |
| Step 5 (Execute) | Main (인터랙티브) | 환경/URL.md, 환경/실행_규칙.md, 환경/계정.md, 환경/API_엔드포인트.md |
| Step 6 (Report) | 서브에이전트 | rules/_confluence_output_rules.md  (Main이 Step 6 진입 시 로드, reporter subagent 상속) |

> `rules/` 범용 파일도 동일 원칙: _guidelines_test_evidence.md → Step 5만, _confluence_output_rules.md → Step 6만.

---


## Output Conventions

> **전제**: 아래 모든 경로는 `{ctx.ticket_folder}/` 하위이다.

- 티켓 폴더: `test/{ticket}_{feature}/`
- 게이트 결과: `{ticket}_gate_{YYYYMMDD_HHmmss}.json` <!-- YYYYMMDD_HHmmss: 동일 티켓에서 여러 게이트 실행 시 구분 목적 (타임스탬프 포함) -->
- 테스트시트: `{ticket}_테스트시트_v{N}_{YYYY-MM-DD}.md`
- 데이터매핑: `{ticket}_데이터매핑.json`
- TC 계약 명세: `{ticket}_tc_spec.json` — TC별 행위 조건·기대값·데이터 요구사항 (test-plan Step 4.3-C)
- Mermaid URL 맵: `.mermaid_urls_{ticket}.json` — generate_mermaid_urls.py 출력물, reporter Step 2에서 생성 ({ctx.ticket_folder}/ 에 저장)
- 결과 리포트: `{ticket}_Confluence_테스트결과_v{N.M}_{YYYY-MM-DD}.md`
- 부분 결과: `partial_results/{TC_ID}.json`
- 스크린샷: `screenshots/{ticket}_SC_{TC}_{date}.png`

## Write-Through 원자적 쓰기 규칙

서브에이전트 크래시로 인한 불완전 파일 생성을 방지한다:

```
임시 파일로 쓰고 완료 후 rename (OS의 atomic rename 보장):
  1. write({ticket}_데이터매핑.json.tmp)   ← 쓰기 중
  2. rename(→ {ticket}_데이터매핑.json)    ← 원자적 교체

파일이 .tmp 없이 존재하면 항상 완전한 상태임이 보장됨.
```

적용 대상: gate.json, 테스트시트.md, 데이터매핑.json, execution_plan.json, partial_results/*.json
