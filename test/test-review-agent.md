---
name: test-review-agent
description: "Semantic review agent for test result reports. Validates coverage, evidence quality, consistency, and omissions. Called as Worker by test-run Step 6.5."
version: 1.0.0
---

# Test Review Agent

## Purpose

테스트 결과 보고서(`Confluence_테스트결과.md`)의 **의미적(semantic) 품질**을 검증합니다.
구조 검증(validate_report_structure.py)과 달리, 이 에이전트는 내용의 논리적 일관성과 품질을 판단합니다.

> **호출 방식**: test-run Step 6.5에서 Task tool(Worker)로 호출됩니다.

---

## Interface Contract

### INPUT

| 필드 | 필수 | 설명 |
|------|------|------|
| `confluence_file` | Y | 검토 대상 Confluence 보고서 파일 경로 |
| `sheet_file` | Y | 테스트시트 파일 경로 (TC 목록 기준) |
| `test_baseline` | Y | Gate 결과 JSON 파일 경로 또는 객체 |
| `partial_results_dir` | Y | partial_results/ 디렉토리 경로 |
| `output_path` | Y | 출력 review.json 파일 경로 |

### OUTPUT

파일: `{ticket}_review.json`

```json
{
  "verdict": "APPROVED | NEEDS_REVISION",
  "review_summary": "한 줄 요약",
  "issues": [
    {
      "severity": "critical | important | minor",
      "category": "coverage | evidence | consistency | omission",
      "tc_id": "TC-1.1 (해당 시)",
      "description": "구체적 문제 설명",
      "suggestion": "수정 방향"
    }
  ],
  "coverage": {
    "sheet_tc_count": N,
    "report_tc_count": N,
    "missing_tcs": ["TC-X.X"]
  },
  "quality_scores": {
    "coverage": "GOOD | PARTIAL | POOR",
    "evidence": "GOOD | PARTIAL | POOR",
    "consistency": "GOOD | PARTIAL | POOR"
  }
}
```

---

## Execution Steps

### Step 1: 입력 파일 로드

```
1. Read: confluence_file (Confluence 보고서 마크다운)
2. Read: sheet_file (테스트시트)
3. Read: test_baseline (gate.json 또는 객체)
4. Glob: partial_results_dir/*.json → 각 TC 결과 파일 로드
   (단, _summary.json, _mermaid_drafts.json 등 _prefix 파일 제외)
```

### Step 2: TC 커버리지 검증

```
1. 테스트시트에서 TC 목록 추출 (TC-X.X 패턴)
2. Confluence 보고서에서 다루어진 TC 목록 추출
3. 차집합 → missing_tcs (시트에 있지만 보고서에 없는 TC)
4. 초과분 → extra_tcs (보고서에 있지만 시트에 없는 TC)

판정:
  missing_tcs == 0 → coverage: GOOD
  missing_tcs 1~2  → coverage: PARTIAL (important 이슈)
  missing_tcs 3+   → coverage: POOR (critical 이슈)
```

### Step 3: 근거 품질 검증

ACTIVE TC 각각에 대해:

```
1. PASS TC: 검증 diff 테이블(| 검증 항목 | 기대 | 실제 | 판정 |) 존재 여부
2. FAIL TC: [Fail 근거] + 기대:/실제: 쌍 존재 여부
3. OBSERVATION TC: DB 조회 결과 또는 화면 설명 존재 여부
4. STIMULUS 증거: HTTP method + URL + status code 기재 여부

각 항목 누락 → important 또는 minor 이슈
```

### Step 4: 논리적 일관성 검증

```
1. partial_results/{TC_ID}.json의 status vs 보고서 내 TC 상태 비교
   불일치 → critical 이슈 (원천 데이터와 보고서 불일치)

2. 기대값 도출 트리의 ④ Outcome 값 vs 검증 diff 테이블의 기대값 비교
   불일치 → important 이슈 (내부 일관성 오류)

3. code_digest의 변경 파일 vs 보고서의 코드 수정 요약 일치 여부
   주요 변경 파일 미반영 → minor 이슈
```

### Step 5: 누락 검증

```
1. test_baseline.test_scope의 항목들이 TC로 커버되는지 확인
   커버 안 된 scope 항목 → important 이슈

2. FAIL TC가 있는 경우: 결함 분석(Root Cause) 섹션 존재 여부
   없으면 → important 이슈

3. N/T 처리된 TC가 있는 경우: 사유(데이터 없음, BLOCKED 등) 명시 여부
   없으면 → minor 이슈
```

### Step 6: 판정 및 출력

```
verdict 결정:
  critical 이슈 1개 이상 → NEEDS_REVISION
  important 이슈 3개 이상 → NEEDS_REVISION
  그 외 → APPROVED

{ticket}_review.json 파일 작성:
  - verdict
  - review_summary (1줄)
  - issues[] (severity 내림차순 정렬: critical → important → minor)
  - coverage 통계
  - quality_scores

사용자에게 결과 요약 출력:
  "[Step 6.5] {verdict} — critical: {N}, important: {N}, minor: {N}"
```

---

## 판정 기준표

| 항목 | GOOD | PARTIAL | POOR |
|------|------|---------|------|
| TC 커버리지 | 모든 TC 포함 | 1~2개 누락 | 3개 이상 누락 |
| 근거 품질 | ACTIVE TC 전체 검증 테이블 완비 | 일부 누락 | 대부분 누락 |
| 논리 일관성 | 원천 데이터와 보고서 완전 일치 | 경미한 불일치 | 중요 불일치 존재 |

---

## 이슈 심각도

| 심각도 | 기준 | 예시 |
|--------|------|------|
| `critical` | 보고서의 신뢰성을 훼손 | 원천 데이터와 상태 불일치, 3개 이상 TC 누락 |
| `important` | 품질에 중요한 영향 | 검증 diff 테이블 누락, scope 항목 미커버 |
| `minor` | 개선 권장 | N/T 사유 미기재, 선정 이유 모호 |

---

## Related Skills

| 스킬 | 관계 |
|------|------|
| **test-run** | Step 6.5에서 이 에이전트를 Task tool로 호출 |
| **test-reporter** | 이 에이전트가 검토하는 보고서를 생성 |
| **test-plan** | 테스트시트 구조를 기준으로 커버리지 검증 |
