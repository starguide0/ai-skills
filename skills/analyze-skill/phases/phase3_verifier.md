<!-- Phase 3: Verifier — Chain-of-Verification -->
<!-- 입력: $SKILL_TMPDIR/deliberated.json, $SKILL_TMPDIR/code_analyst_raw.json -->
<!-- 출력: $SKILL_TMPDIR/code_analyst.json, $SKILL_TMPDIR/prompt_verified.json -->

## Phase 3: Verifier — Chain-of-Verification (검증)

> **목적**: Phase 2.5의 병합된 버그 후보들이 환각인지 실제 사실인지 확정한다.
> **단일 Verifier가 deliberated.json을 처리** (중복 제거 완료 상태로 수신, 검증에만 집중).

**입력:**
1. `$SKILL_TMPDIR/deliberated.json` (Phase 2.5 출력 — `verification_tasks[]` 포함 가능)
2. `$SKILL_TMPDIR/code_analyst_raw.json`
3. HIGH/CRITICAL 가설(`hypotheses[]` 비어있지 않음) 검증 시: 해당 소스 파일 직접 읽기 허용

**지시:**
0. **verification_tasks 우선 실행**:
   `deliberated.json`의 `verification_tasks[]`가 존재하면 각 task의 `command`를 Bash로 실행한다.
   결과를 내부 `vt_results` 맵에 저장한다: `{bug_ref: {command, stdout, returncode}}`

   ```bash
   # 예시 — bug_ref: LA-001
   grep -rn 'ANALYZE_MD_PATH' phases/
   # stdout에 결과 있으면 → LA-001 hypothesis 반박 또는 확인 근거 확보
   ```
   ```
   # → vt_results["LA-001"] = {"command": "grep -rn ...", "stdout": "phases/phase2_experts.md:31: ...", "returncode": 0}
   ```

   - `verification_tasks[]`가 없거나 비어있으면 이 단계를 건너뛴다.
   - vt_results는 이후 Step A/B/C보다 **우선** 적용된다.
   - vt_results와 Verification Questions 결과가 충돌하면: **vt_results(bash 실행 결과)를 우선**한다.
   - 충돌 예시: vt_results의 grep이 패턴을 찾았지만(returncode=0, stdout 비어있지 않음) Verification Question이 'No'로 추론된 경우 → vt_results 우선으로 CLEARED 판정
   - 충돌 예시: vt_results의 grep이 아무것도 찾지 못했지만(stdout 비어있음) Verification Question이 'Yes'로 추론된 경우 → vt_results 우선으로 CONFIRMED 가능성 제거

1. `$SKILL_TMPDIR/deliberated.json`을 읽는다 (Phase 2.5 Group Deliberator 출력).
2. `$SKILL_TMPDIR/code_analyst_raw.json`을 읽는다.
3. **code_analyst_raw.json의 skipped = true인 경우**: bugs[] 비어있음을 확인하고 code_analyst.json에 그대로 전파.
4. 각 버그 후보마다 **사실 검증 우선 원칙**에 따라 아래 순서로 처리한다:

   **Step A — grep 검증 가능 여부 판단 (필수)**:
   버그의 Verification Questions를 보고 grep/bash로 답할 수 있는 질문인지 판단한다.

   | grep 검증 가능한 질문 유형 | 예시 |
   |--------------------------|------|
   | 특정 키/필드가 파일에 존재하는가? | `grep -n '"analyze_md_path"' phase1_grounding.py` |
   | 특정 함수/변수가 실제 호출되는가? | `grep -rn 'skill_purpose' scripts/` |
   | 특정 패턴이 어떤 파일에도 없는가? | `grep -rn 'ANALYZE_MD_PATH' phases/` |
   | 파일이 실제로 존재하는가? | Bash `ls` 또는 `test -f` |

   **Step B — grep 검증 가능하면: Bash 직접 실행 (LLM 추론 금지)**:
   ```bash
   # 예시: "analyze_md_path가 facts.json에 포함되는가?" 검증
   grep -n "analyze_md_path" "$SKILL_DIR/scripts/phase1_grounding.py"
   # 결과 있음 → Yes (해당 질문 PASS)
   # 결과 없음 → No  (해당 질문 FAIL → CONFIRMED)
   ```
   Bash 실행 결과를 `verdict_reason`에 명시한다. ("grep 결과: 3번째 줄에 존재" 등)

   **Step C — grep 불가한 질문만 LLM 추론**:
   설계 의도, 흐름 일관성 등 코드로 답할 수 없는 질문은 LLM이 파일을 읽어 판단한다.

   **Step D — HIGH/CRITICAL 가설 proactive 교차검증**:
   아래 조건을 모두 만족하는 버그에 한해 소스 파일을 직접 읽어 독립 교차검증한다:
   - severity = HIGH 또는 CRITICAL
   - `hypotheses[]`가 비어있지 않음
   - 아래 중 하나에 해당하면 불충분으로 판단한다:
     - vt_results가 없거나(verification_tasks 미제공) hypotheses 관련 command의 stdout이 비어있음
     - Step A에서 grep 검증 불가 판정되었고 Step C의 LLM 추론이 불확실함(CONFIRMED/CLEARED 확신 불가)

   절차:
   1. 해당 bug의 `file` 필드에서 소스 파일 경로를 확인한다.
   2. 해당 파일을 직접 Read한다 (bug의 `file` 필드는 `$SKILL_DIR` 기준 상대 경로 또는 파일명 — `$SKILL_DIR/{file}` 경로로 Read).
   3. `hypotheses`의 각 항목이 실제 코드에서 확인되는지 검증한다.
   4. 결과를 `verdict_reason`에 기록한다: `"직접 읽기: {파일명} line {N}: {근거}"`

   > LOW/MEDIUM 버그는 Step A/B/C로만 처리한다 (파일 읽기 비용 절감).

5. **검증 규칙**:
   - 모든 질문이 'Yes' → CONFIRMED
   - 하나라도 'No' → CLEARED
   - 아래 조건 **모두** 충족 시 → **UNCERTAIN** (사용자 확인 필요):
     - severity = HIGH 또는 CRITICAL
     - vt_results가 없거나 관련 command의 stdout이 비어있음
     - Step D를 실행했으나 확정 불가이거나, `hypotheses[]`가 비어있어 Step D를 실행하지 않은 경우
     - `clarifying_question`과 `decision_impact`를 반드시 생성할 것
   - MEDIUM/LOW에서 확정 불가 → CLEARED로 처리 (HITL 비용 절감)
   - 역방향 질문("X가 없는가?")을 발견하면: "X가 있는가?"로 재해석 후 판정
   - grep 결과와 LLM 추론이 충돌하면: **grep 결과를 우선**한다
6. `found_in_analysts`, `analyst_count` 필드는 deliberated.json에서 그대로 승계한다.

**출력**:
- `$SKILL_TMPDIR/code_analyst.json`

```json
{
  "analyst": "CodeAnalyst",
  "bugs": [...],
  "skipped": true|false,
  "note": "SINGLE/PROMPT 타입 — Python 파일 없음",
  "json_output_keys": {},
  "json_input_keys": {},
  "glob_patterns_found": []
}
```

- `$SKILL_TMPDIR/prompt_verified.json`

```json
{
  "bugs": [
    {
      "id": "LA-001",
      "severity": "HIGH",
      "file": "SKILL.md",
      "section": "Phase 2",
      "analyst": "LogicAuditor",
      "description": "이슈 설명",
      "evidence": "근거",
      "verdict": "CONFIRMED|CLEARED",
      "verdict_reason": "검증 근거",
      "confirmed_facts_inherited": ["deliberated.json → bugs[i].confirmed_facts에서 동일 id의 항목을 상속"],
      "found_in_analysts": ["LogicAuditor", "ContractReviewer"],
      "analyst_count": 2
    },
    {
      "id": "LA-001",
      "severity": "HIGH",
      "file": "phase2_experts.md",
      "section": "Phase 2",
      "analyst": "LogicAuditor",
      "description": "이슈 설명",
      "evidence": "근거",
      "verdict": "UNCERTAIN",
      "verdict_reason": "grep 결과 없음 — ANALYZE_MD_PATH 관련 패턴 미발견. 파일 읽기로도 전달 여부 불명확.",
      "clarifying_question": "Phase 2 각 전문가 파견 시 ANALYZE_MD_PATH 값이 파견 지시에 명시적으로 포함되어 있나요?",
      "decision_impact": "YES → CLEARED / NO → CONFIRMED HIGH",
      "confirmed_facts_inherited": [],
      "found_in_analysts": ["LogicAuditor"],
      "analyst_count": 1
    }
  ],
  "file_naming_patterns": [],
  "ctx_fields_declared": [],
  "status_enums": {}
}
```

---
