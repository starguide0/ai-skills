<!-- Phase 2: 독립 전문가 파견 (MoT) + Phase 2.5: Group Deliberator -->
<!-- 입력: $SKILL_TMPDIR/facts.json (facts._expert_views[전문가명] 참조) -->
<!-- 출력: $SKILL_TMPDIR/*_raw.json, $SKILL_TMPDIR/deliberated.json -->

## Phase 2: 독립 전문가 파견 (MoT)

> **독립 전문가 MoT**: 각 전문가는 서로 다른 시각을 담당한다. 그룹 경계 없이 독립적으로 분석하고, 동일 버그가 여러 전문가에서 발견되면 Phase 2.5에서 병합한다.
> 각 전문가는 자신의 영역에 집중하되, **facts.json + block_index의 사실 위에서만 해석을 추가한다. .md 원문을 직접 읽지 않는다** (SemanticAuditor는 분석 대상 .md 파일 전체 읽기 허용).

> **CodeAnalyst 스킵 조건**: `code_analyst_needed = false` (SINGLE/PROMPT 타입)이면
> CodeAnalyst를 파견하지 않고 아래 Bash 명령으로 빈 결과 파일을 즉시 생성한다:
>
> ```bash
> echo '{"bugs":[],"json_output_keys":{},"json_input_keys":{},"glob_patterns_found":[],"skipped":true,"note":"SINGLE/PROMPT 타입 — Python 파일 없음"}' \
>   > "$SKILL_TMPDIR/code_analyst_raw.json"
> ```

> **타입별 병렬 실행 구성:**
> - HYBRID 타입: CodeAnalyst + LogicAuditor + ContractReviewer + InterfaceGuard + ContextGuard + SemanticAuditor = 총 6개 동시 파견
> - SINGLE/PROMPT 타입: LogicAuditor + ContractReviewer + InterfaceGuard + ContextGuard + SemanticAuditor = 5개 병렬 파견
>
> **전역 컨텍스트 주입 (필수)**: 모든 전문가 파견 시 아래 네 항목을 파견 지시 본문 **맨 위**에 반드시 포함시킨다.
> ```
> SKILL_TMPDIR={SKILL_TMPDIR 실제값}
> SKILL_DIR={SKILL_DIR 실제값}
> [분析 대상 스킬 컨텍스트]
> skill_purpose: {facts.skill_purpose}   ← 이 스킬이 무엇을 하는 도구인가
> skill_type:    {facts.skill_type}       ← HYBRID | PROMPT | SINGLE
> ```
> 이 컨텍스트 없이는 전문가들이 "버그인가 의도적 설계인가"를 맥락 없이 판단하게 된다.
>
> **CUSTOM 모드 추가 검사 (analyze.md 직접 읽기 금지)**:
> CUSTOM 모드 추가 정적 분析 명령은 Phase 1에서 이미 실행되어 `facts._expert_views[전문가명].custom_grep_results`에 저장됨.
> 각 전문가는 analyze.md를 직접 읽지 말고 **`custom_grep_results`의 결과를 사용**한다.
> - `custom_grep_results[i].stdout` 이 비어있으면 → 해당 패턴 없음 (버그 가능성 있음)
> - `custom_grep_results[i].returncode == 0` 이면 → 패턴 발견됨 (정상 또는 known_vuln 재확인)
>
> **알려진 취약 지점 처리**: `facts._expert_views[전문가명].known_vulns`에 이전 분析에서 확인된 취약점 목록이 있음.
> 이 목록에 있는 버그를 발견한 경우 `"known_vuln_id": "CR-002"` 필드를 버그 보고에 추가한다.
> Arbiter가 신규 버그와 재확인 버그를 구분하는 데 사용하므로 반드시 표시할 것.
>
> **플랫폼 파견 메커니즘**: 각 전문가는 독립 subagent로 병렬 파견한다.
> Claude Code는 Agent/Task tool, Gemini CLI는 activate_skill, 기타 플랫폼은 동등한 subagent 메커니즘을 사용한다.
> 병렬 subagent를 지원하지 않는 환경에서는 순차 실행으로 대체한다 (결과 동일, 속도 저하).

> **사실/가설 분리 원칙 (전 전문가 필수)**:
> 각 버그 보고 시 반드시 아래를 구분한다:
> - `confirmed_facts`: 직접 읽은 코드/grep 결과로 확인된 사실 (라인 번호, 실제 텍스트 인용)
> - `hypotheses`: 패턴/추론으로 의심되지만 코드 확인이 필요한 것
> - `verification_needed`: hypotheses를 확인할 수 있는 구체적 grep 명령 (hypothesis 없으면 `[]`)
>
> **LLM 편향 방지**: "이것이 버그다"고 확신하기 전에 `confirmed_facts`에 실제 코드 근거를 먼저 나열하라.
> 근거가 없으면 `hypotheses`에만 기록하고 `verification_needed`를 반드시 채운다.

---

### [CodeAnalyst] Python 코드 버그 탐지

**지시:**
facts.json을 읽고, .py 파일들을 분석하여 의심스러운 지점을 찾는다.
각 이슈마다 **Verification Questions**를 포함한다.

**입력:**
1. `$SKILL_TMPDIR/facts.json` (필수 — 분석의 사실적 기반)
2. 스킬 디렉토리의 모든 .py 파일 (누락 금지)
3. ARCHITECTURE.md, HOOKS.md (있으면)
4. CUSTOM 모드인 경우 `facts.custom_grep_results` 및 `facts.known_vulns` 사용 (analyze.md 직접 읽기 금지)

**분석 지시:**

facts.json에서 추출된 패턴/exit code/JSON 참조는 확정된 사실이다.
**facts.json에 이미 있는 데이터를 재탐색하는 것은 금지한다.**

```
□ Python 버전 호환성
  - facts.modern_type_hints 목록 기준 확인
  - from __future__ import annotations 없으면 → MEDIUM

□ 정렬 버그
  - 문자열로 숫자 ID 정렬 → CRITICAL (예: "TC-10" < "TC-2")

□ JSON 스키마 일관성
  - facts.json_outputs의 각 호출 → 실제 출력 키를 파일에서 직접 확인
  - 소비자 코드가 기대하는 키와 대조 → 불일치 = HIGH

□ glob 패턴 ↔ 파일명 규칙
  - facts.glob_patterns의 각 패턴을 ARCHITECTURE.md의 파일명 규칙과 대조
  - 불일치 = CRITICAL

□ exit code (facts.exit_codes 기준)
  - HOOKS.md 규칙과 대조 → 불일치 = HIGH

□ 예외 처리 누락 (json.loads without try/except)
□ 암묵적 경로 가정 (CWD 의존 상대경로)
□ 중복 함수 (DRY 위반) → LOW
□ 빈 데이터 엣지 케이스
□ Edit Hook false-deny
```

**Verification Questions 작성 규칙**: 반드시 "사실이면 Yes" 형태. "X가 없는가?" 금지.

**출력**: `$SKILL_TMPDIR/code_analyst_raw.json`에 저장:

```json
{
  "analyst": "CodeAnalyst",
  "bugs": [
    {
      "id": "CA-001",
      "severity": "CRITICAL",
      "file": "tools/behavioral_gate.py",
      "line": 32,
      "code_excerpt": "glob.glob(...)",
      "description": "이슈 설명",
      "evidence": "근거",
      "confirmed_facts": [
        "직접 읽은 코드에서 확인된 사실 (라인 번호 포함)"
      ],
      "hypotheses": [
        "추론된 문제 — 코드 확인 필요"
      ],
      "verification_needed": [
        "grep -n 'pattern' file.py"
      ],
      "verification_questions": [
        "사실이면 Yes: line 32에 해당 패턴이 있는가?",
        "사실이면 Yes: ARCHITECTURE.md에 영문 파일명이 명시되어 있는가?"
      ]
    }
  ],
  "json_output_keys": {"tools/foo.py": ["key_a", "key_b"]},
  "json_input_keys": {"tools/bar.py": ["key_a", "key_b"]},
  "glob_patterns_found": [{"file": "tools/foo.py", "line": 32, "pattern": "*.json"}]
}
```

---

### [LogicAuditor] 실행 흐름 / 분기 완결성 분석

**페르소나**: 당신은 **LogicAuditor**다. 실행 흐름, 예외 처리, 분기 완결성, 스킵 조건 전파에 집중하는 전문가다.

**검증 질문 작성 규칙**: 반드시 "사실이면 Yes" 형태. "X가 없는가?" 금지.

**입력:**
1. `$SKILL_TMPDIR/facts.json` (필수 — facts.branch_conditions, facts.mode_refs, facts.block_index 우선 참조)
2. CUSTOM 모드인 경우 `facts._expert_views[전문가명].custom_grep_results` 및 `known_vulns` 사용 (analyze.md 직접 읽기 금지)
3. ※ .md 원문 직접 읽기 금지 — block_index의 section/summary/line 정보로 맥락 파악

**분석 포커스:**
```
□ 각 이슈 보고 시:
  - block_index/facts.json에서 직접 확인 가능한 것 → confirmed_facts
  - 패턴으로 의심되나 원문 없이 확신 불가한 것 → hypotheses
  - facts.json-only 전문가는 verification_needed에 "grep -n '패턴' 파일명" 형식으로 반드시 기록

□ 분기 조건 완결성
  - IF/ELSE 분기가 SINGLE/PROMPT/HYBRID 세 타입 모두를 커버하는가?
  - facts.branch_conditions 기준으로 확인
  - 누락 케이스 = MEDIUM

□ 스킵 조건 전파
  - code_analyst_needed = false 시 스킵이 Phase 3~4까지 올바르게 전파되는가?
  - code_analyst.skipped 필드가 각 Phase에서 참조되는가?
  - 누락 = HIGH

□ CUSTOM/AUTO 모드 대칭성
  - CUSTOM 모드 전용 지시가 각 분석가 섹션 모두에 명시되어 있는가?
  - 누락 = MEDIUM

□ 예외 케이스 처리
  - 빈 입력, 파일 없음, 스킵 조건 등이 명세되어 있는가?
  - 누락 = MEDIUM

□ 임시 디렉토리 변수명 안전성
  - SKILL_TMPDIR (비예약 변수명)을 사용하는가?
  - TMPDIR(시스템 예약 변수) 사용 시 → CRITICAL
```

**출력**: `$SKILL_TMPDIR/logic_auditor_raw.json`에 저장:

```json
{
  "_schema": {
    "analyst": "출력한 분석가 이름 (고정값: LogicAuditor)",
    "bugs[].id": "LA-{N} 형식. N은 이 분석가 내 순번",
    "bugs[].severity": "CRITICAL | HIGH | MEDIUM | LOW — Severity Rubric 기준 엄수",
    "bugs[].file": "분석 대상 파일명 (경로 제외)",
    "bugs[].section": "버그가 위치한 Phase/섹션명 (예: Phase 2, 숙의 Step 3)",
    "bugs[].description": "버그 설명 — 원인과 영향을 1~2문장으로 서술",
    "bugs[].evidence": "SKILL.md에서 직접 인용한 구절 — 추측 금지",
    "bugs[].block_ref": "연관된 block_index 항목 (없으면 null)",
    "bugs[].verification_questions": "반드시 '사실이면 Yes' 형태. 역방향('X가 없는가?') 금지"
  },
  "analyst": "LogicAuditor",
  "bugs": [
    {
      "id": "LA-001",
      "severity": "HIGH",
      "file": "SKILL.md",
      "section": "Phase X",
      "description": "이슈 설명",
      "evidence": "SKILL.md에서 직접 인용한 구절",
      "confirmed_facts": [
        "block_index/facts.json에서 직접 확인된 사실"
      ],
      "hypotheses": [
        "추론된 문제 — 원문 없이 확신 불가"
      ],
      "verification_needed": [
        "grep -n 'pattern' phases/file.md"
      ],
      "block_ref": {
        "block_number": 3,
        "type": "PSEUDO",
        "intent": "unknown",
        "summary": "IF 분기 조건 나열"
      },
      "verification_questions": ["사실이면 Yes: [질문 내용]"]
    }
  ],
  "file_naming_patterns": [],
  "ctx_fields_declared": [],
  "status_enums": {}
}
```

---

### [ContractReviewer] 명세 ↔ 구현 간극 분석

**페르소나**: 당신은 **ContractReviewer**다. 프롬프트 지침과 실제 구현 사이의 간극을 찾는 전문가다. "명세는 X를 요구하는데 실제 구현이 Y다"를 탐지한다.

**검증 질문 작성 규칙**: 반드시 "사실이면 Yes" 형태. "X가 없는가?" 금지.

**입력:**
1. `$SKILL_TMPDIR/facts.json` (필수 — facts.json_key_refs, facts.block_index 우선 참조)
2. CUSTOM 모드인 경우 `facts._expert_views[전문가명].custom_grep_results` 및 `known_vulns` 사용 (analyze.md 직접 읽기 금지)
3. ※ .md 원문 직접 읽기 금지 — block_index의 section/summary/line 정보로 맥락 파악

**분석 포커스:**
```
□ 각 이슈 보고 시:
  - block_index/facts.json에서 직접 확인 가능한 것 → confirmed_facts
  - 패턴으로 의심되나 원문 없이 확신 불가한 것 → hypotheses
  - facts.json-only 전문가는 verification_needed에 "grep -n '패턴' 파일명" 형식으로 반드시 기록

□ 분석가 출력 스키마 ↔ 소비자 기대 스키마 일치
  - CodeAnalyst/LogicAuditor/ContractReviewer/InterfaceGuard 출력 필드명
    == Verifier/Arbiter가 참조하는 필드명인가?
  - facts.json_key_refs 기준으로 교차 확인
  - 불일치 = HIGH

□ ENCODED 계산 명세 vs 실제 bash 명령 일치
  - 명세 텍스트의 치환 규칙 == bash 명령의 실제 동작인가?
  - sed 's|/|__|g' 대신 tr 같은 비동등 명령 사용 시 → CRITICAL

□ Phase 출력 파일명 명세 vs 실제 저장 경로 일치
  - 파이프라인 구조 다이어그램의 파일명 == 각 분석가 지시의 저장 경로인가?
  - 불일치 = HIGH

□ 문서 내 상호 참조 일관성
  - 섹션 A에서 언급된 개념이 섹션 B에서 다르게 정의되지 않는가?
  - 불일치 = HIGH

□ analyze.md ENCODED 경로 예시 일치
  - 경로 계산 예시가 실제 bash 명령 결과와 일치하는가?
  - 불일치 = HIGH
```

**출력**: `$SKILL_TMPDIR/contract_reviewer_raw.json`에 저장 (analyst: "ContractReviewer" 포함, bugs[] 구조는 confirmed_facts/hypotheses/verification_needed 필드 포함).

---

### [InterfaceGuard] Phase 간 입출력 정합성 분석

**페르소나**: 당신은 **InterfaceGuard**다. Phase 간 입출력 파일명, JSON 키값의 정합성, 외부 스펙 준수를 검사하는 전문가다. "Phase N이 출력한 파일을 Phase N+1이 올바르게 읽는가"를 탐지한다.

**검증 질문 작성 규칙**: 반드시 "사실이면 Yes" 형태. "X가 없는가?" 금지.

**입력:**
1. `$SKILL_TMPDIR/facts.json` (필수 — facts.phase_output_files, facts.phase_input_files, facts.block_index 우선 참조)
2. CUSTOM 모드인 경우 `facts._expert_views[전문가명].custom_grep_results` 및 `known_vulns` 사용 (analyze.md 직접 읽기 금지)
3. ※ .md 원문 직접 읽기 금지 — block_index의 section/summary/line 정보로 맥락 파악

**분석 포커스:**
```
□ 각 이슈 보고 시:
  - block_index/facts.json에서 직접 확인 가능한 것 → confirmed_facts
  - 패턴으로 의심되나 원문 없이 확신 불가한 것 → hypotheses
  - facts.json-only 전문가는 verification_needed에 "grep -n '패턴' 파일명" 형식으로 반드시 기록

□ Phase 간 출력→입력 파일명 일치
  - Phase N의 출력 파일명 == Phase N+1의 입력 파일명인가?
  - facts.phase_output_files와 facts.phase_input_files 교차 대조
  - 불일치 = HIGH

□ code_analyst.json 스키마 명세 완결성
  - code_analyst.json의 JSON 스키마(skipped 필드 포함)가 Phase 3에 정의되어 있는가?
  - prompt_verified.json 스키마와 동등한 수준으로 기술되어 있는가?
  - 미정의 = HIGH

□ ANALYZE_MD_PATH 분석가 전달 메커니즘
  - Phase 2 분석가 파견 지시에 ANALYZE_MD_PATH 값이 명시적으로 전달되는가?
  - 미전달 시 CUSTOM 모드 추가 검사 불가 → HIGH

□ 전체 스킬 검사 SKILL_TMPDIR 삭제
  - 전체 스킬 검사 모드에서 각 스킬의 SKILL_TMPDIR 삭제 시점이 명세되어 있는가?
  - 누락 = MEDIUM

□ analyze.md skill_hash 갱신 지시
  - Phase 6에서 analyze.md에 현재 SKILL_HASH를 기록하는 지시가 있는가?
  - 누락 시 캐시 hit 판정 불가 → HIGH
```

**출력**: `$SKILL_TMPDIR/interface_guard_raw.json`에 저장 (analyst: "InterfaceGuard" 포함, bugs[] 구조는 confirmed_facts/hypotheses/verification_needed 필드 포함).

---

### [ContextGuard] 앞뒤 맥락 일관성 분석

**페르소나**: 당신은 **ContextGuard**다. block_index를 기반으로 섹션 간, Phase 간 개념 정의의 앞뒤 일관성을 검사하는 전문가다. "섹션 A에서 정의된 개념이 섹션 B에서 다르게 사용되는가"를 탐지한다.

**검증 질문 작성 규칙**: 반드시 "사실이면 Yes" 형태. "X가 없는가?" 금지.

**입력:**
1. `$SKILL_TMPDIR/facts.json` (필수 — facts.block_index, facts.mode_refs, facts.json_key_refs 우선 참조)
2. CUSTOM 모드인 경우 `facts._expert_views[전문가명].custom_grep_results` 및 `known_vulns` 사용 (analyze.md 직접 읽기 금지)
3. ※ .md 원문 직접 읽기 금지 — block_index의 section/type/summary/line 정보로 맥락 파악

**분석 포커스:**
```
□ 각 이슈 보고 시:
  - block_index/facts.json에서 직접 확인 가능한 것 → confirmed_facts
  - 패턴으로 의심되나 원문 없이 확신 불가한 것 → hypotheses
  - facts.json-only 전문가는 verification_needed에 "grep -n '패턴' 파일명" 형식으로 반드시 기록

□ 섹션 간 용어 일관성
  - 동일 개념이 다른 섹션에서 다른 이름으로 사용되는가?
  - block_index의 section 필드와 summary에서 용어 불일치 탐지
  - 불일치 = MEDIUM

□ 파이프라인 다이어그램 ↔ 각 Phase 섹션 일치
  - 다이어그램에 나열된 출력 파일명 == 각 Phase 섹션의 실제 출력 파일명인가?
  - block_index의 DATA 블록에서 파일명 추출 후 대조
  - 불일치 = HIGH

□ CUSTOM/AUTO 모드 분기의 앞뒤 대칭
  - Phase 0에서 CUSTOM 모드 조건이 설정되면 이후 모든 Phase에서 동등하게 언급되는가?
  - facts.mode_refs 기준 Phase별 언급 여부 확인
  - 누락 Phase = MEDIUM

□ 캐시 hit 경로의 완결성
  - 캐시 hit 발생 시 렌더링 소스(analyze.md)와 출력 형식이 명세되어 있는가?
  - 미명세 = HIGH
```

**출력**: `$SKILL_TMPDIR/context_guard_raw.json`에 저장 (analyst: "ContextGuard" 포함, bugs[] 구조는 confirmed_facts/hypotheses/verification_needed 필드 포함).

---

### [SemanticAuditor] PSEUDO + CODE 블록 의미론 분석

**페르소나**: 당신은 **SemanticAuditor**다. PSEUDO 블록(의사코드)과 CODE 블록(프로그래밍 코드)을 **전체 문서 맥락과 함께** 해석하는 전문가다. SHELL/DATA 블록은 Phase 1이 이미 처리했으므로 분석하지 않는다.
코드 블록을 주변 맥락과 분리해서 분석하면 오탐이 발생한다. block_index는 **타입 안내 지도**로만 사용하고, 반드시 해당 .md 파일 전체를 Read하여 맥락을 파악한 뒤 분석한다.

**검증 질문 작성 규칙**: 반드시 "사실이면 Yes" 형태. "X가 없는가?" 금지.

```
□ SemanticAuditor 사실/가설 분리 특이사항:
  - .md 파일 전체를 읽으므로 confirmed_facts는 반드시 실제 라인 번호와 텍스트 인용 포함
  - hypotheses는 "맥락적 추론"에 한정 (코드로 확인된 것은 confirmed_facts로 기록)
  - verification_needed는 읽지 않은 파일이 있을 경우에만 기재
```

**입력:**
1. `$SKILL_TMPDIR/facts.json` (필수 — facts.block_index에서 type="PSEUDO"|"CODE" 블록 위치 파악)
2. 분석 대상 .md 파일 **전체** Read (`skill_dir` + `file` 경로 조합, 블록 범위 제한 없음)
3. CUSTOM 모드인 경우 `ANALYZE_MD_PATH`의 추가 검사항목 (파견 시 경로 명시 전달됨)

**분석 포커스:**
```
[PSEUDO 블록]
□ IF/ELSE 분기 완결성
  - 모든 분기가 명시적 처리 경로를 갖는가?
  - ELIF 없이 암묵적 fall-through가 있는가?
  - 누락 케이스 = MEDIUM

□ 조건 나열의 상호 배타성
  - 조건 A와 B가 동시에 참일 수 있는가?
  - 중복 조건 = MEDIUM

□ 의사코드 → 실제 구현 추적 가능성
  - PSEUDO 블록의 의도가 인근 SHELL/DATA 블록에서 구현되는가?
  - block_index의 섹션/라인 범위로 인근 블록 확인
  - 구현 누락 = HIGH

□ 스킵 조건 전파 완결성
  - PSEUDO 블록에 스킵 조건이 있으면 이후 Phase PSEUDO 블록에서도 전파 처리되는가?
  - 전파 누락 = HIGH

[CODE 블록]
□ 코드 의도 검증 (Phase 1.5 결과 재검토)
  - Phase 1.5에서 부여된 intent가 전체 맥락과 일치하는지 확인
  - 잘못 분류된 블록은 block_intent_inference에 보정값 기록
    (Phase 6에서 analyze.md 보정 후보 — 다음 분석 시 Phase 1에 반영됨)
  - intent=unknown이 남아있는 블록도 이 시점에 추론하여 기록

□ 코드와 섹션 설명 일치
  - 이 코드가 해당 섹션의 설명 의도와 일치하는가?
  - 불일치 = MEDIUM

□ 동일 섹션 내 코드 블록 간 일관성
  - 같은 섹션의 여러 CODE 블록에서 변수명/파일명/로직이 일치하는가?
  - 불일치 = MEDIUM

□ 코드 완결성 (intent 고려)
  - intent=executable인 경우: 실제 실행 가능한 완전한 코드인가?
  - intent=example인 경우: 오류가 있어도 의도적 생략일 수 있음 — 맥락 판단
```

**출력**: `$SKILL_TMPDIR/semantic_auditor_raw.json`에 저장:

```json
{
  "analyst": "SemanticAuditor",
  "bugs": [
    {
      "id": "SA-001",
      "severity": "MEDIUM",
      "file": "SKILL.md",
      "section": "Phase 2",
      "description": "이슈 설명",
      "evidence": "근거",
      "confirmed_facts": [
        "SKILL.md line 42에서 직접 읽음: '...' — 실제 텍스트 인용"
      ],
      "hypotheses": [
        "맥락적 추론: 이 블록의 의도가 주변 설명과 불일치할 가능성"
      ],
      "verification_needed": [],
      "block_ref": {
        "block_number": 7,
        "type": "PSEUDO",
        "intent": "unknown",
        "summary": "IF 분기 조건"
      },
      "verification_questions": ["사실이면 Yes: [질문 내용]"]
    }
  ],
  "block_intent_inference": [
    {
      "file": "SKILL.md",
      "line_start": 280,
      "lang": "bash",
      "inferred_intent": "pseudo",
      "reason": "IF 조건 나열 구조 — 실제 bash 실행 불가"
    }
  ]
}
```

---

## Phase 2.5: Group Deliberator — 동일 버그 병합

> **목적**: 그룹 경계 없이 전체 전문가 결과에서 동일한 버그를 다른 표현으로 발견한 항목을 병합한다. Phase 3 Verifier의 중복 검증 비용을 절감한다.

**입력:** 전체 전문가 *_raw.json 파일 (code_analyst_raw.json 포함)

**병합 기준:**
```
동일 버그 판정 방법:
  각 버그 쌍에 대해 다음 질문에 LLM이 Yes/No로 판단한다:
    "두 버그가 동일한 결함을 설명하는가?
     (같은 파일 + 같은 섹션/라인 범위 ±5 이내이고,
      표현은 달라도 동일한 근본 원인을 가리키는가?)"

  Yes → 동일 버그로 병합
  No  → 독립 버그로 유지

  severity가 두 등급 이상 차이나면 → 동일 버그로 병합하더라도 반드시 주석 남김

병합 처리:
  - found_in_analysts: 발견한 전문가 이름 목록
  - analyst_count: 발견 전문가 수
  - description: 가장 구체적인 설명 채택
  - severity: 가장 높은 등급 채택
  - id: 첫 번째 발견 전문가의 ID 유지
```

**verification_tasks 생성 (병합 완료 후):**
```
모든 버그의 verification_needed[]를 수집한다.
verification_needed가 빈 배열([])인 버그는 건너뛴다.
중복 명령은 제거한다 — 같은 command가 여러 버그에 있으면 가장 높은 severity의 bug_ref를 사용한다.
HIGH/CRITICAL 버그는 우선순위 HIGH로 표시한다.
LOW/MEDIUM 버그는 우선순위 MEDIUM으로 표시한다.
```

**출력**: `$SKILL_TMPDIR/deliberated.json`에 저장:

```json
{
  "bugs": [
    {
      "id": "LA-001",
      "severity": "HIGH",
      "file": "SKILL.md",
      "section": "Phase 0",
      "description": "병합된 이슈 설명 (가장 구체적)",
      "evidence": "근거",
      "confirmed_facts": ["병합 대상 버그 중 가장 구체적인 confirmed_facts 상속"],
      "hypotheses": ["병합 대상 버그의 hypotheses 통합"],
      "verification_needed": ["병합 대상 버그의 verification_needed 수집 (중복 제거)"],
      "found_in_analysts": ["LogicAuditor", "ContextGuard"],
      "analyst_count": 2,
      "block_ref": {
        "block_number": 3,
        "type": "SHELL",
        "intent": "executable",
        "summary": "SKILL_HASH 계산 — OS 분기"
      },
      "verification_questions": ["사실이면 Yes: [질문 내용]"]
    }
  ],
  "merge_log": [
    {
      "merged_ids": ["LA-001", "CG-002"],
      "reason": "동일 파일 + 동일 섹션 + severity 동일"
    }
  ],
  "verification_tasks": [
    {
      "bug_ref": "LA-001",
      "severity": "HIGH",
      "command": "grep -rn 'ANALYZE_MD_PATH' phases/",
      "purpose": "ANALYZE_MD_PATH 전달 여부 확인",
      "priority": "HIGH"
    }
  ]
}
```

---
