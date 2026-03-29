<!-- Phase 5: 결과 통합 출력 -->
<!-- 입력: $SKILL_TMPDIR/code_analyst.json, $SKILL_TMPDIR/prompt_verified.json, $SKILL_TMPDIR/arbiter.json -->
<!-- 출력: 마크다운 테이블 렌더링 -->

## Phase 5: 결과 통합 출력

> **[조건부 출력 규칙]**
> - `arbiter.json`의 `confirmed_bugs[]`가 비어있으면 "Python 이슈" 및 "프롬프트 이슈" 섹션 전체를 생략하고 HITL 섹션부터 출력한다.
> - `arbiter.json`의 `escalations[]`에 `UNCERTAIN_FROM_PHASE3` 타입이 없으면 HITL 섹션을 생략한다.

code_analyst.json, prompt_verified.json, arbiter.json을 읽어 다음 형식으로 출력:

```markdown
## {스킬명} 분석 결과 (CUSTOM|AUTO 모드 — HYBRID|PROMPT|SINGLE)

### Python 이슈 (CodeAnalyst)
| 심각도 | ID | 이슈 | 파일:라인 | 코드 |
|--------|-----|------|-----------|------|
| CRITICAL | CA-001 | glob 패턴 불일치 | behavioral_gate.py:32 | `glob.glob(...)` |

### 프롬프트 이슈 (페르소나 MoT)
| 심각도 | ID | 분석가 | 이슈 | 신뢰도 | 파일:섹션 |
|--------|-----|-------|------|--------|-----------|
| HIGH | CR-001 | ContractReviewer | ENCODED 계산 불일치 | 2/3 PROBABLE | SKILL.md:Phase 0 |

### 숙의 결과 (Arbiter)
| 대상 ID | 신뢰도 | 결과 | 근거 요약 |
|---------|--------|------|-----------|
| CA-001 | - | ✅ CONFIRMED | grep 직접 확인 |
| CR-001 | 2/3 PROBABLE | ✅ CONFIRMED | sed vs tr 불일치 확정 |
| LA-003 | 1/3 UNCERTAIN | ⚠ ESCALATE | 스펙 모호 |

### 충돌 해소 현황
| 충돌 | 유형 | 해소 방법 |
|------|------|---------|
| CR-001 ↔ IG-002 | Type 3 (인과) | CR-001 선행 수정 필요 |

### 수정 순서 의존성
1. 먼저: CR-001 (이유: ENCODED 수정이 선행)
2. 이후: IG-001

### 불확실 항목 — 사용자 확인 필요 (HITL)

> 아래 항목은 자동 검증으로 확정하지 못했습니다.
> 각 질문에 YES/NO로 답하면 버그 여부가 확정되고 analyze.md에 자동 반영됩니다.

| ID | 심각도 | 유형 | 질문 | YES 시 | NO 시 |
|----|--------|------|------|--------|-------|
| LA-001 | HIGH | Phase3 검증불가 | Phase 2 파견 시 ANALYZE_MD_PATH가 명시적으로 포함되나요? | CLEARED | CONFIRMED |
| LA-003 | MEDIUM | 스펙 모호 | 캐시 hit 시 analyze.md를 직접 렌더링하나요? | CLEARED | CONFIRMED |

**답변 방법**: 각 ID에 대해 `YES` 또는 `NO`로 답해주세요.

### 총평
| 등급 | 건수 | 설명 |
|------|------|------|
| CRITICAL | N | 즉시 수정 — Silent failure 포함 |
| HIGH     | N | 다음 배포 전 수정 |
| MEDIUM   | N | 개선 권장 |
| LOW      | N | 선택적 개선 |
| UNCERTAIN | N | 사용자 확인 필요 — 위 HITL 섹션 참조 |
```

**Phase 5 → Phase 6 핸드오프**: 사용자가 HITL 섹션의 각 ID에 YES/NO로 답하면,
Phase 5 완료 직후 `$SKILL_TMPDIR/hitl_answers.json`을 생성한다 (Phase 6이 이 파일을 소비):

```json
{
  "answers": [
    {"ref": "LA-001", "answer": "YES", "resolved_verdict": "CLEARED"},
    {"ref": "CG-003", "answer": "NO",  "resolved_verdict": "CONFIRMED"}
  ],
  "skipped": ["LA-003"]
}
```
답변하지 않은 항목은 `skipped[]`에 ref만 기록한다. HITL 항목이 없거나 모두 건너뛰면 `answers: []`.

---
