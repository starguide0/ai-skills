<!-- Phase 4: Arbiter — 숙의 -->
<!-- 입력: $SKILL_TMPDIR/code_analyst.json, $SKILL_TMPDIR/prompt_verified.json -->
<!-- 출력: $SKILL_TMPDIR/arbiter.json -->

## Phase 4: Arbiter — 숙의 (앙상블 합성 + 충돌 분류)

> **Arbiter는 code_analyst.json과 prompt_verified.json만 기본 입력으로 받는다.**
> 충돌 해소를 위해 Type 1/3 충돌에 한해 소스 파일을 직접 읽거나 Bash grep을 실행할 수 있다.

**입력:**
1. `$SKILL_TMPDIR/code_analyst.json` (필수)
2. `$SKILL_TMPDIR/prompt_verified.json` (필수 — analyst_count 포함)
3. `$SKILL_TMPDIR/facts.json` — `facts.known_vulns` 참조용 (CUSTOM 모드)
4. 충돌 해소 필요 시에만 해당 소스 파일 직접 읽기 허용

> **CUSTOM 모드 known_vuln 분리 (Step 0 — 숙의 전 선처리)**:
> `facts.known_vulns`가 비어있지 않으면 아래를 실행한다:
> 1. `facts.json`에서 `known_vulns` 목록 로드 (`facts.known_vulns[].id`)
> 2. `prompt_verified.json`의 CONFIRMED 버그 중 `known_vuln_id` 필드가 있는 항목을 찾는다
> 3. 매칭된 항목: `confirmed_bugs`에 기록 시 `verdict_source: "known_vuln_reconfirmed"` 추가
> 4. 매칭 안 된 CONFIRMED 항목: 신규 버그 — 일반 처리
>
> 이렇게 하면 출력에서 **재확인 버그**와 **신규 버그**가 명확히 구분된다.

> **code_analyst.skipped = true인 경우 (SINGLE/PROMPT 타입):**
> - glob_patterns_found ↔ file_naming_patterns 교차 검증 건너뜀
> - json_output_keys ↔ json_input_keys 교차 검증 건너뜀
> - prompt_verified.json의 CONFIRMED 버그를 신뢰도와 함께 confirmed_bugs에 기록
>   (confidence = analyst_count / N, N=5)
> - confirmed_bugs에 `{"ref":"CODE-ANALYST-SKIPPED","verdict":"N/A","severity":"N/A","evidence":"SINGLE/PROMPT 타입 — CodeAnalyst 미실행"}` 기록

---

### 숙의 Step 1: 신뢰도 계산

```
confidence = analyst_count / N  (N=5, SINGLE/PROMPT 타입 전문가 수)
- confidence = 1.0  (5/5) → HIGH_CONFIDENCE  (즉시 수정 권장)
- confidence = 0.8  (4/5) → HIGH_CONFIDENCE  (즉시 수정 권장)
- confidence = 0.6  (3/5) → PROBABLE         (추가 검증 권장)
- confidence = 0.4  (2/5) → PROBABLE         (추가 검증 권장)
- confidence = 0.2  (1/5) → UNCERTAIN        (컨텍스트 의존 가능성)
```

CodeAnalyst 버그(HYBRID 타입)는 `confidence = 1.0`, `confidence_level = "HIGH_CONFIDENCE"`로 처리한다.
SINGLE/PROMPT 타입은 N=5 (LogicAuditor + ContractReviewer + InterfaceGuard + ContextGuard + SemanticAuditor).

> **UNCERTAIN 버그 (Phase 3에서 넘어온 경우)**:
> - confidence 계산은 동일하게 적용
> - UNCERTAIN 버그는 **Step 2 충돌 감지 전에** Arbiter 자체 결정론적 폴백을 먼저 시도한다:
>   1. `clarifying_question`을 보고 grep으로 답할 수 있는가?
>      - YES: bash 실행 → 결과로 CONFIRMED 또는 CLEARED 확정 → `verdict_source: "arbiter_resolved"` 기록 → 일반 확정 버그로 처리
>      - NO: escalations[]에 추가 (type: "UNCERTAIN_FROM_PHASE3")

---

### 숙의 Step 2: 충돌 감지 및 분류

```
Type 1: 사실 충돌 (Factual Contradiction)
  처리: → 즉시 결정론적 폴백 (Step 3)

Type 2: 컨텍스트 의존 (Context-Dependent)
  처리: → 조건 추출 후 조건부로 기록. 어느 쪽도 CLEARED 불가

Type 3: 인과 충돌 (Causal Cascade)
  처리: → 의존 그래프 작성, fix 순서 명시 (fix_order 필드)

Type 4: 결정 불가 (Undecidable / Spec Ambiguous)
  처리: → ESCALATE + 구조화된 최소 질문 생성 (Step 4)
```

---

### 숙의 Step 3: 결정론적 폴백 체인 (Type 1/3 의무 적용)

```
충돌 감지
  └→ "grep으로 답할 수 있는가?"
       YES → Bash grep 직접 실행 → 사실 확정 → 판정
       NO  → Type 4로 재분류 → Step 4 (ESCALATE)
```

---

### 숙의 Step 4: ESCALATE 질문 생성 (Type 4 / UNCERTAIN_FROM_PHASE3)

> Type 4 충돌(결정 불가)과 Step 1에서 해소되지 못한 UNCERTAIN_FROM_PHASE3 모두 이 섹션의 스키마로 escalations[]에 기록한다.

```json
{
  "ref": "LA-003",
  "conflict": "CLEARED(LogicAuditor) vs CONFIRMED(ContractReviewer)",
  "undecidable_because": "스펙 모호",
  "clarifying_question": "질문 내용",
  "decision_impact": "YES → CLEARED / NO → CONFIRMED"
}
```

```json
{
  "ref": "LA-001",
  "type": "UNCERTAIN_FROM_PHASE3",
  "undecidable_because": "Phase 3 grep/파일읽기로도 확정 불가",
  "clarifying_question": "Phase 2 각 전문가 파견 시 ANALYZE_MD_PATH가 명시적으로 전달되나요?",
  "decision_impact": "YES → CLEARED / NO → CONFIRMED HIGH",
  "severity": "HIGH"
}
```

---

### 숙의 Step 5: fix_order 의존 그래프

```json
{
  "must_fix_first": "CR-002",
  "before": "IG-001",
  "reason": "ENCODED 수정이 선행되어야 ANALYZE_MD_PATH 전달이 의미 있음"
}
```

---

**출력**: `$SKILL_TMPDIR/arbiter.json`에 저장:

```json
{
  "_schema": {
    "confirmed_bugs[].ref": "원본 분석가 ID (예: LA-001). CODE-ANALYST-SKIPPED는 CodeAnalyst 미실행 표시",
    "confirmed_bugs[].severity": "CRITICAL | HIGH | MEDIUM | LOW",
    "confirmed_bugs[].verdict": "CONFIRMED | N/A",
    "confirmed_bugs[].confidence": "analyst_count / N (0.0~1.0)",
    "confirmed_bugs[].confidence_level": "HIGH_CONFIDENCE | PROBABLE | UNCERTAIN",
    "cleared_bugs[].ref": "CLEARED 판정된 버그 ID",
    "new_bugs[]": "Arbiter가 숙의 중 직접 발견한 신규 버그",
    "conflicts[].type": "Type1(사실충돌) | Type2(컨텍스트의존) | Type3(인과충돌) | Type4(결정불가)",
    "fix_order[]": "Type3 충돌 해소를 위한 수정 순서 의존 그래프",
    "escalations[]": "Type4(결정불가-스펙모호) | UNCERTAIN_FROM_PHASE3(Phase3 검증 불가) — 설계자 확인이 필요한 항목",
    "escalations[].type": "Type4(결정불가-스펙모호) | UNCERTAIN_FROM_PHASE3(Phase3 검증 불가)",
    "inferred_as_deterministic[]": "이번 LLM 추론으로 발견한 패턴 → 다음 실행에서 grep으로 변환 후보"
  },
  "confirmed_bugs": [
    {
      "ref": "LA-001",
      "severity": "HIGH",
      "verdict": "CONFIRMED",
      "confidence": 0.67,
      "confidence_level": "PROBABLE",
      "analyst": "LogicAuditor",
      "evidence": "근거 기술"
    },
    {
      "ref": "CODE-ANALYST-SKIPPED",
      "verdict": "N/A",
      "severity": "N/A",
      "evidence": "SINGLE/PROMPT 타입 — CodeAnalyst 미실행"
    }
  ],
  "cleared_bugs": [],
  "new_bugs": [],
  "conflicts": [],
  "fix_order": [],
  "escalations": [],
  "inferred_as_deterministic": [
    {
      "type": "bash_command_behavior | file_naming_pattern | status_enum | ctx_field | exit_code_rule | other",
      "description": "분석가가 LLM 추론으로 발견했지만 grep/bash로 결정론적으로 추출 가능한 패턴",
      "grep_command": "grep -rho '...' {SKILL_DIR}/... 2>/dev/null | sort -u",
      "facts_field": "facts.json에 추가할 필드명",
      "phase6_target": "추가 정적 분석 명령 | 알려진 취약 패턴"
    }
  ]
}
```

---
