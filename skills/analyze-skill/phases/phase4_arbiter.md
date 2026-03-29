# Phase 4: Arbiter — 숙의 (책임자 주도 끝장토론)

<!-- Phase 4: Arbiter — 숙의 (책임자 주도 끝장토론 모델) -->
<!-- 입력: $SKILL_TMPDIR/code_analyst.json, $SKILL_TMPDIR/prompt_verified.json -->
<!-- 출력: $SKILL_TMPDIR/arbiter.json -->

> **상태**: v4.1.0 전략 개편 적용 (단일 에이전트 판단 → 책임자 주도 도메인별 2:2 끝장토론)
> **목표**: 오탐 제거, 설계적 타당성 검증, 합의된 결과와 양보 불가 쟁점의 명확한 분리

> **에이전트 등급**: `Arbiter` / `ServiceLead` ( **$GRADE_A** )
> - `facts.model_map.GRADE_A` 변수에 할당된 모델을 사용하여 호출하십시오.

---

## Step 4.1: 책임자(Lead)의 기준 수립 및 1차 필터링

- **역할**: 서비스/스킬 책임자 (Service/Skill Lead)
- **입력**: `facts.json` (skill_purpose, skill_type), `prompt_verified.json`
- **동작**:
    1. 분석 대상 스킬의 핵심 가치와 설계 원칙을 재확인합니다.
    2. `prompt_verified.json`의 모든 버그 후보를 훑어보며, 스킬의 범위를 벗어나거나(Out of Scope) 지나치게 지엽적인 의견을 1차적으로 필터링합니다.
    3. 토론 그룹 구성을 확정합니다 (예: Logic & Flow 그룹, Interface & Contract 그룹).

---

## Step 4.2: 도메인별 전문가 그룹 끝장토론 (Multiple 2:2 Groups)

- **구성**: 도메인별로 **제시자(Proposers) 2명**과 **비판자(Critics) 2명**을 배치합니다.
- **토론 프로토콜 (끝장토론)**:
    1. **제시(Round 1)**: Proposers가 버그 후보의 근거(`evidence`, `verdict_reason`)를 바탕으로 결함임을 주장합니다.
    2. **공격(Round 1)**: Critics가 해당 결함이 "의도된 설계"이거나 "환경적 제약"일 가능성을 제기하며 비판합니다.
    3. **방어 및 분석(Round 2)**: Proposers가 비판 내용을 코드/사실 기반으로 재반박하거나, 비판을 수용하여 severity를 조정합니다.
    4. **수렴(Round 3)**: 합의가 가능한 항목은 'AGREED'로, 끝까지 이견이 갈리는 항목은 'DEADLOCK'으로 분류합니다.
- **기록**: 각 버그 항목에 `debate_status`("AGREED" | "DEADLOCK")를 기록합니다.

---

## Step 4.3: 책임자의 전역 취합 및 정제 (Global Aggregator)

- **역할**: 서비스/스킬 책임자 (Service/Skill Lead)
- **동작**:
    1. **중복 제거**: 서로 다른 도메인 그룹에서 보고된 동일 현상을 하나로 병합합니다 (가장 논리가 강한 쪽 채택).
    2. **전역 정합성 검토**: 특정 그룹의 수정 제안이 다른 도메인의 스펙을 침해하지 않는지 최종 조율합니다.
    3. **신뢰도 재산출**: 합의된 강도에 따라 `confidence`를 보정합니다. (AGREED=1.0, DEADLOCK=0.5 미만)
    4. **최종 변별**: `confirmed_bugs`, `cleared_bugs`, `escalations`를 확정합니다.

---

## Step 4.4: 결정론적 폴백 및 ESCALATE (Type 4)

- **Type 1/3 충돌**: 토론 중 사실 관계(Type 1)나 인과 관계(Type 3)가 쟁점이 될 경우, 즉시 **Bash grep**을 실행하여 사실을 확정합니다.
- **Type 4 (결정 불가/DEADLOCK)**: 토론 후에도 해결되지 않은 쟁점은 `escalations`에 추가하여 사용자에게 질문합니다.

---

**출력**: `$SKILL_TMPDIR/arbiter.json`

```json
{
  "_schema": {
    "confirmed_bugs[].debate_status": "AGREED | CONCEDED",
    "escalations[].type": "DEADLOCK | UNCERTAIN",
    "meta.debate_rounds": "토론 횟수 (기본 3)",
    "meta.lead_summary": "책임자의 전체 분석 요약"
  },
  "meta": {
    "debate_rounds": 3,
    "lead_summary": "전체적인 분석 결과 및 주요 쟁점 정리"
  },
  "confirmed_bugs": [
    {
      "ref": "LA-001",
      "severity": "HIGH",
      "verdict": "CONFIRMED",
      "debate_status": "AGREED",
      "confidence": 1.0,
      "evidence": "..."
    }
  ],
  "cleared_bugs": [],
  "new_bugs": [],
  "conflicts": [],
  "fix_order": [],
  "escalations": [
    {
      "ref": "SA-003",
      "type": "DEADLOCK",
      "conflict": "제시자(Logic) vs 비판자(Semantic)",
      "undecidable_because": "설계 의도의 모호성",
      "clarifying_question": "이 부분의 설계가 의도된 것인가요?",
      "decision_impact": "YES -> CLEARED / NO -> CONFIRMED"
    }
  ]
}
```
