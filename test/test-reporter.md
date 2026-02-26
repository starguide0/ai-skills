---
name: test-reporter
description: "Aggregates partial test results from multiple batches and generates the final Confluence-compatible report."
version: 4.1.0
---

# Test Reporter Skill

## Purpose

분산 실행된 부분 결과(`partial_results/*.json`)를 수집하여 **단일 결과 문서**로 병합합니다. 문서 표준(Template Compliance)을 강제합니다.

---

## _shared/ Dependencies

이 스킬이 로드하는 `_shared/` 파일 목록:
- (없음 — 결과 파일만 읽는다.)
- `rules/_confluence_output_rules.md` → test-run Step 6 진입 시 Main 오케스트레이터가 로드. 본 subagent는 ctx에서 상속받아 사용.

> **test-evidence 규칙**: 근거 형식(Level 1-4)은 Step 5 실행 시(validate_test_result.py hook)에
> 이미 강제됨. reporter는 기작성된 근거를 그대로 보고서에 통합한다.
> reporter가 evidence guidelines를 별도 로드할 필요 없음 (Step 5 write time enforcement).

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| ctx.partial_results | test-run (Step 5) | Y | 분산 실행된 TC별 부분 결과 파일 모음 (partial_results/*.json) |
| ctx.sheet | test-plan | Y | 테스트시트 파일 경로 ({ticket}_테스트시트_v{N}_{date}.md) |
| ctx.test_baseline | test-gate | Y | Gate 통과 시 생성된 기준 객체 (jira_digest, code_digest, test_types 등) |
| ctx.tc_spec | test-plan | 조건부 | {ticket}_tc_spec.json 절대 경로 — TC별 기대값 도출 트리 자동 생성에 사용. 없으면 LLM CoT 추론 |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| Confluence 테스트결과 파일 | 사용자 | {ticket}_Confluence_테스트결과_v{N}.{M}_{YYYY-MM-DD}.md |
| template_compliance_check | test-run (검증용) | 필수 섹션 포함 여부 체크 결과 |

### INTERNAL (다른 스킬이 몰라도 되는 것)
- Confluence 마크다운 호환 규칙 (_confluence_output_rules.md 기반)
- 테스트 유형별 결과 병합 규칙 (API 테스트, DB Before/After, UI 캡쳐, 모바일 시뮬레이션, 이벤트 검증)
- 템플릿 검증 로직 (용어 정의, API 필드 안내, 테스트 흐름, 사전 조건 DB 검증, 근거 작성 규칙, TC 선정 이유, TC 상세, 전체 결과 요약)
- 섹션 자동 복구 로직 (누락 시 자동 생성 시도)
- Pass/Fail/N·T/BLOCKED 통계 계산
- 시나리오 ID 순서 정렬 로직

## ctx 복원 (Read-Through Fallback)

> 각 입력 필드가 ctx에 없으면 파일에서 복원한다:
> - ctx.partial_results 없으면 → Glob `{ctx.ticket_folder}/partial_results/*.json` → 경로 목록으로 복원
> - ctx.sheet 없으면 → Glob `{ctx.ticket_folder}/{ticket}_테스트시트_v*.md` → 최고 버전 선택
> - ctx.test_baseline 없으면 → Glob `{ctx.ticket_folder}/{ticket}_gate_*.json` → 타임스탬프 최신 → JSON parse
> - ctx.tc_spec 없으면 → Glob `{ctx.ticket_folder}/{ticket}_tc_spec.json` → JSON parse (도출 트리 생성용, 없어도 계속)
> - 파일도 없으면 → ERROR: "선행 Step 미완료" → 파이프라인 중단

---

## Logic Flow

1.  **요약 생성 (Python)**: partial_results/ 전체를 단일 요약 JSON으로 집계
    ```bash
    python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/summarize_partial_results.py \
      --dir {ctx.ticket_folder}/partial_results/ \
      --output {ctx.ticket_folder}/partial_results/_summary.json
    ```
    → `_summary.json` 1개만 Read하면 전체 TC 현황 파악 가능 (개별 JSON Read 불필요)

2.  **Mermaid 초안 생성 (Python)**: _summary.json에서 다이어그램 골격 생성
    > **생성 시점**: reporter Step 2에서 생성 (test-run Step 5 종료 후).
    > _confluence_output_rules.md의 "Step 5 후반 사전 생성" 지침과 다름 — reporter Step 2가 권위 있는 생성 시점.
    ```bash
    python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/generate_mermaid_diagrams.py \
      --summary {ctx.ticket_folder}/partial_results/_summary.json \
      --output {ctx.ticket_folder}/partial_results/_mermaid_drafts.json
    ```
    → pie chart(완성), sequence/state(골격) 생성. before_after는 null (LLM 직접 작성)

    **Step 2-b: URL 생성 (다이어그램 생성 직후)**
    ```bash
    python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/generate_mermaid_urls.py \
      --ticket {ticket} --output {ctx.ticket_folder}/.mermaid_urls_{ticket}.json
    ```
    → 생성된 다이어그램 각각의 렌더링 URL을 JSON으로 저장 (문서 삽입용)

3.  **LLM 검토/보강**: `_summary.json` + `_mermaid_drafts.json` 2개 Read + (있으면) `{ticket}_tc_spec.json` Read
    - Mermaid 골격을 검토하고 Note/Kafka 이벤트/내부 흐름 등 보강
    - Before/After flowchart는 LLM이 직접 작성 (코드 이해 필요)
    - TC별 자연어 근거, 의미 해석, FAIL 원인 분석
    - **기대값 도출 트리 생성 (D-3)**:
      IF ctx.tc_spec 존재:
        FOR each tc_id in tcs:
          tc_spec[tc_id].expected.fields 와 static_fields에서 ASCII 트리 자동 생성:
          ```
          ① Source:    {source_db}.{source_table}.{source_column}
          ② Transform: {aggregation}({source_column}) → {path}
                       {extra_join이 있으면: + JOIN {extra_join}}
          ③ Filter:    WHERE {source_where}
          ④ Outcome:   기대값 = {computed_value} (실행 시 동적 계산)
          ```
        # static_fields (고정값 필드) 처리:
        # static_fields는 full 4단계 트리 대신 1줄 형식 사용:
        # "④ 기대결과: {value} (고정값 — 도출 불필요)"
        # 예: "④ 기대결과: 200 (HTTP Status — 고정값)"
        # fields[]에 있는 formula 필드만 4단계 트리로 출력한다.
      ELSE (tc_spec.json 없는 CoT 폴백):
        동일한 4단계 ASCII 트리 형식을 유지하되, 소스를 코드 분석으로 대체:
        ```
        ① Source:    {테스트시트 기대결과 셀 또는 TC 사전조건에서 데이터 출처 추론}
        ② Transform: {코드 분석 (Gate code_digest) 기반 — 어떤 로직이 이 값을 생성하는가}
        ③ Filter:    {TC 조건 (behavioral_condition) 기반 — 어떤 상태여야 이 값이 반환되는가}
        ④ Outcome:   기대값 = {_summary.json.checks의 expected 값}
        ```
        ※ tc_spec.json 없어도 동일한 4단계 트리 형식 필수 — Template Compliance Check 통과 요건
        NOTE: tc_spec.json 있으면 정확도 및 자동화 수준 대폭 향상

4.  **유형별 결과 통합**: 아래 테스트 유형별 결과 병합 규칙 적용

5.  **문서 생성**: `_confluence_output_rules.md` 기반으로 마크다운 생성

6.  **구조 검증 (Python)**: 생성된 Confluence 문서의 필수 섹션 검사
    ```bash
    python3 $CLAUDE_PROJECT_DIR/.claude/skills/test/tools/validate_report_structure.py \
      --file {ctx.ticket_folder}/{ticket}_Confluence_테스트결과_v{N}.{M}_{YYYY-MM-DD}.md \
      --output {ctx.ticket_folder}/partial_results/_validation.json
    ```
    → FAIL 항목만 LLM이 수정 (17개 체크 중 PASS는 무시)

    > ⚠️ **결과 확인 필수 — exit code 믿지 말 것**
    > `validate_report_structure.py`는 FAIL 항목이 있어도 항상 `exit(0)` 반환 (CLI 전용 도구).
    > exit code가 아닌 반드시 `--output` 으로 지정한 `_validation.json`을 Read하여 확인:
    > - `"result": "fail"` 항목 → 해당 섹션을 보고서에서 직접 수정
    > - `"result": "pass"` 항목 → 무시
    > 이 파일을 읽지 않으면 구조적으로 불완전한 보고서가 그대로 제출될 수 있음.

7.  **보관**: 부분 결과 파일 유지 (디버깅용)

## Template Compliance Check

생성된 문서는 다음 항목을 반드시 포함해야 합니다:

*   [ ] 용어 정의 (Tables)
*   [ ] API 응답 필드 안내
*   [ ] 코드 수정 요약 (Code Change Summary)
*   [ ] 테스트 흐름 (Mermaid)
*   [ ] 사전 조건 DB 검증
*   [ ] 근거 작성 규칙
*   [ ] TC 선정 이유 (각 TC 제목 아래 `> **선정 이유**: ...` blockquote)
*   [ ] TC 상세 (Pass/Fail Evidence)
*   [ ] TC 기대값 도출 트리 (각 TC의 "사전 조건 확인" 블록에 ASCII 트리 포함 — Source/Transform/Filter/Outcome 레이어)
*   [ ] TC 검증 diff 테이블 (Pass TC의 상세확인내용을 | # | 검증 항목 | 기대 | 실제 | 판정 | 테이블로 통일)
*   [ ] 전체 결과 요약 (Summary)

## 코드 수정 요약 (Code Change Summary)

테스트 결과 문서에 **수정된 코드의 변경 내용과 전후 효과**를 포함한다. 리뷰어가 "무엇이 변경되었고 → 어떤 효과가 있고 → 어떻게 검증했는지"를 한 문서에서 파악할 수 있도록 한다.

### 필수 구성 요소

1. **변경 파일별 Before/After 코드**
   - 파일 경로 + 라인 번호
   - 수정 전 코드 (코드블록)
   - 수정 전 문제점 설명 (blockquote)
   - 수정 후 코드 (코드블록)
   - 수정 후 효과 설명 (blockquote)

2. **수정 전후 효과 요약 테이블**
   - 시나리오별 수정 전 동작 → 수정 후 동작 → 검증 TC 매핑
   - 각 행이 어떤 TC로 검증되었는지 명시

### 데이터 소스
- `ctx.test_baseline.code_digest` — 변경 파일 및 구현 사항
- `ctx.test_baseline.jira_digest` — Jira 요구사항 (수정 이유)
- Gate 분석 시 수집한 코드 diff 정보

### Confluence 포맷 주의
- 코드 스니펫은 **테이블 밖** 독립 코드블록으로 작성
- 효과 설명은 `> → ✅ 해석` blockquote 형식

## 테스트 유형별 결과 병합

partial_results에 포함될 수 있는 테스트 유형별 결과를 올바르게 병합한다:

| 유형 | partial_results 필드 | 보고서 반영 |
|------|---------------------|------------|
| API 테스트 | api_response | 실제 응답 JSON + 검증 해석 blockquote |
| DB Before/After | db_before, db_after, changes | 변경 행 비교 + 사이드이펙트 검증 |
| UI 캡쳐 | screenshots[] | `![TC번호](screenshots/...)` 이미지 삽입 |
| 모바일 시뮬레이션 | mobile_api_results[] | API 시퀀스별 요청/응답 + "모바일 시뮬레이션" 태그 |
| 이벤트 검증 | event_results | 토픽 발행/소비 매칭 결과 |
| 구간별 Trace | checkpoints[] | e2e TC 구간별 STIMULUS+CHECK 결과 요약 테이블 |

## 문서 간소화 3원칙

> **목표**: 정보 밀도를 높이면서 문서 길이를 줄인다. FAIL TC는 축약하지 않는다.

### 원칙 1: 트리가 기대값을 설명한다 → 상세확인에서 재설명 금지

- 도출 트리(사전 조건 확인)가 이미 기대값의 근거를 제공하므로,
  상세확인내용에서 "기대: X" 항목을 별도로 설명하지 않는다.
- 상세확인내용은 **검증 diff 테이블** 1개로 통일한다:

```markdown
**검증 결과** (도출 트리 ④와 대조):

| # | 검증 항목 | 기대 | 실제 | 판정 |
|---|----------|------|------|------|
| 1 | groups 수 | 4 | 4 | ✅ |
| 2 | 각 SKU qty | 1 | 1 | ✅ |

> → ✅ {종합 해석 1줄}
```

### 원칙 2: API 응답은 검증 필드만 발췌

- JSON 전체 덤프 금지. 검증 대상 필드만 발췌하여 표시.
- 생략된 필드는 "API 응답 필드 안내" 섹션에서 일괄 안내.
- 발췌 시 `(검증 대상 필드만 발췌)` 명시.

### 원칙 3: 동일 데이터는 1회만 기술 → 이후 TC는 참조

- 같은 컨테이너/엔티티를 여러 TC에서 사용하는 경우:
  - 첫 TC: 도출 트리 + API 응답 + 검증 테이블 (전체 기술)
  - 이후 TC: `> **데이터**: TC-{N}과 동일 ({Entity ID}) — 도출 트리 및 API 응답은 TC-{N} 참조`
  - 이후 TC에서는 **추가 검증 포인트만** 기술
- 종합 검증 쿼리가 있으면 "사전 조건 DB 검증 (종합)"에서 1회만 기술, 각 TC에서 참조

## 이전 버전 비교 금지 (No Cross-Version Comparison)

테스트 결과 문서는 **해당 실행의 사실(fact)만** 기록한다. 이전 테스트 결과와의 비교를 포함하지 않는다.

**금지 항목**:
- "v{N-1} 대비 변경 사항" 섹션
- TC별 "이전 결과: FAIL → 현재: PASS" 형태의 비교
- "이전 버전에서는..." 등의 비교 문구
- 통과율 변화 추이 (예: "92.9% → 100%")

**이유**: 결과 문서는 결과론적 사실만 담아야 한다. 이전 버전과의 비교가 필요하면 사용자가 별도로 비교를 요청한다.

**허용 항목**:
- 결함 보고서의 Root Cause 설명 (코드 분석 결과)
- 데이터 상태 변경 사실 기록 (예: "DB 상태가 X이므로 테스트 조건 미충족" — 이전 테스트 결과 언급 없이)

---

## Error Handling

*   **Missing Partial Results**: 해당 시나리오를 `N·T` (Not Tested) 처리하고 사유 명시
*   **Template Violation**: 누락된 섹션이 있을 경우 자동 복구 시도 또는 경고 출력
*   **BLOCKED TC** (서버 접속 끊김): `⚠️ BLOCKED` 상태로 표시, 사유 명시

---

## Related Skills

| 스킬 | 관계 |
|------|------|
| **test-run** | Step 6에서 이 스킬을 호출하여 최종 보고서 생성 |
| **test-evidence** | Pass/Fail 근거 작성 규칙 참조 |
| **test-plan** | 테스트시트 구조를 보고서에 반영 |
| **_confluence_output_rules.md** | 문서 구조 + Mermaid 변환 + 체크리스트 |
