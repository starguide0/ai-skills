<!-- Phase 5.1: Regression Check (CUSTOM 모드만) -->
<!-- 입력: $SKILL_TMPDIR/arbiter.json, $ANALYZE_MD_PATH -->
<!-- 출력: Phase 5 출력에 Regression 섹션 추가 (감지 시) -->

## Phase 5.1: Regression Check — 이전 분석 결과와 비교

> **조건**: CUSTOM 모드(`$ANALYZE_MD_PATH` 존재)일 때만 실행. AUTO 모드는 건너뜀.
> **목적**: 이전 분석에서 CONFIRMED됐던 버그가 이번에 CLEARED됐다면 — 실제로 수정된 것인지, 분석이 잘못된 것인지 판별하여 **퇴행(Regression)**을 감지한다.

**입력:**
1. `$SKILL_TMPDIR/arbiter.json` (이번 분석 결과)
2. `$ANALYZE_MD_PATH` (이전 분석의 `## 알려진 취약 지점` 섹션)

**비교 로직:**

```
이전 analyze.md의 알려진 취약 지점 목록
  └→ 각 항목을 이번 arbiter.json confirmed_bugs/cleared_bugs와 대조

판정:
  A. 이전 CONFIRMED → 이번 CONFIRMED  : 미수정 지속 (정상)
  B. 이전 CONFIRMED → 이번 CLEARED    : ⚠ Regression 후보
       → skill_hash 변경 여부 확인
         hash 변경 있음: 수정 반영됐을 가능성 → "수정 확인 필요"
         hash 변경 없음: 분석 불일치 → "분석 퇴행 (False Negative 의심)"
  C. 이전 없음      → 이번 CONFIRMED  : 신규 발견 (정상)
```

**Phase 5 출력에 Regression 섹션 추가 (감지 시):**

```markdown
### ⚠ Regression 감지 (이전 분석 대비)
| ID | 이전 상태 | 이번 상태 | 판정 | 권고 |
|----|----------|----------|------|------|
| CR-001 | CONFIRMED | CLEARED | 분석 퇴행 의심 | 소스 직접 확인 후 Phase 6 판단 |
| LA-002 | CONFIRMED | CONFIRMED | 미수정 지속 | 수정 우선순위 재검토 |
```

> **Regression이 없으면** 이 섹션은 출력하지 않는다.

---
