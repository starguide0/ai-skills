---
name: analyze-skill
description: 스킬의 품질을 체계적으로 검사한다. - **CUSTOM 모드**: `$SKILL_ANALYSIS_DIR/{스킬명}/analyze.md`가 있으면 해당 프로토콜을 각 Phase에 병합 (`SKILL_ANALYSIS_DIR`은 Phase 0에서 플랫폼 자동 감지 후 설정) - **AUTO 모드**: `analyze.md` 없으면 범용 체크리스트로 동작 - 타입 자동 감지: HYBRID (Python + Prompt) / PROMPT (Prompt only) / SINGLE
---

# Analyze Skill

스킬의 품질을 체계적으로 검사한다.

- **CUSTOM 모드**: `$SKILL_ANALYSIS_DIR/{스킬명}/analyze.md`가 있으면 해당 프로토콜을 각 Phase에 병합
- **AUTO 모드**: `analyze.md` 없으면 범용 체크리스트로 동작
- 타입 자동 감지: HYBRID (Python + Prompt) / PROMPT (Prompt only) / SINGLE

---

## 사용법

```bash
/analyze-skill [스킬경로]        ← 특정 스킬 분석
/analyze-skill                   ← 모든 스킬 전체 검사
```

---

## 실행 흐름

1. **Phase 0 (Python)**: `scripts/phase0_setup.py {skill_dir}` 실행
   → `phase0_result.json` 생성
   → `cache_hit`이면 기존 analyze.md 렌더링 후 종료
   → `schema_drift` 감지 시 사용자에게 알림
   → 상세 지시: `phases/phase0.md` 참조

2. **Phase 1 (Python)**: `scripts/phase1_grounding.py {tmpdir}/phase0_result.json` 실행
   → `facts.json` + 전문가 뷰 슬라이싱 완료 (결정론적 grep)
   → block_index 생성 (intent는 CUSTOM 모드에서 analyze.md 보정값 반영, 나머지는 unknown)

3. **Phase 1.5 (LLM)**: `phases/phase1_5_enrichment.md` 참조
   → facts.json의 intent=unknown 블록들을 .md 파일 전체 읽기로 분류
   → facts.json block_index.intent 갱신 (in-place 덮어쓰기)
   → intent=unknown 블록이 없으면 즉시 스킵

4. **Phase 2 (LLM)**: `phases/phase2_experts.md` 참조
   → 각 전문가에게 `facts._expert_views[전문가명]` + `facts.skill_purpose` + `facts.skill_type` 전달
   → SINGLE/PROMPT: CodeAnalyst 스킵
   → 완료 후 즉시 검증:

   ```bash
   python scripts/validate_phase.py phase2 "$SKILL_TMPDIR"
   ```

5. **Phase 2.5 (LLM)**: `phases/phase2_experts.md` Phase 2.5 섹션 참조
   → 완료 후 즉시 검증:

   ```bash
   python scripts/validate_phase.py phase2_5 "$SKILL_TMPDIR"
   ```

6. **Phase 3 (LLM)**: `phases/phase3_verifier.md` 참조
   → 완료 후 즉시 검증:

   ```bash
   python scripts/validate_phase.py phase3 "$SKILL_TMPDIR"
   ```

7. **Phase 4 (LLM)**: `phases/phase4_arbiter.md` 참조
   → **책임자 주도 끝장토론 (Adversarial MoT)**
   → 2:2 전문가 그룹(도메인별) 간의 비판적 분석 및 반박 루프 실행
   → 책임자(Lead)의 전역 취합 및 정제 (Global Aggregator)
   → 완료 후 즉시 검증:

   ```bash
   python scripts/validate_phase.py phase4 "$SKILL_TMPDIR"
   ```

8. **Phase 5 (LLM)**: `phases/phase5_output.md` 참조
   → 분析 결과 마크다운 렌더링 + HITL 질문 출력
   → escalations 있으면 사용자 답변 수집 후 `$SKILL_TMPDIR/hitl_answers.json` 생성

9. **Phase 5.1 (LLM, 선택)**: `phases/phase5_1_regression.md` 참조
   → HITL 답변 반영 후 회귀 검증 실행 (선택적)

10. **Phase 6 (LLM)**: `phases/phase6_crystallize.md` 참조
    → analyze.md 갱신 (skill_hash 포함) + SKILL_TMPDIR 삭제

---

## Severity Rubric (전 분석가 공통)

| 등급 | 정의 | 예시 |
| :--- | :--- | :--- |
| **CRITICAL** | 기능 완전 무력화 또는 Silent failure | glob 패턴 불일치로 파일 영구 탐지 실패 |
| **HIGH** | 데이터 오염, 집계 오류, 계약 파괴 | 상태 키 잘못 매핑으로 집계 틀림 |
| **MEDIUM** | 계약 불명확, 엣지 케이스 미처리, 일관성 결여 | 합산 공식에 상태값 누락 가능성 |
| **LOW** | 코드 품질, 가독성, DRY 위반 | 중복 헬퍼 함수 |

---

## 전체 스킬 검사

```
0. 스킬 루트 결정:
   인자 없이 실행 시:
     SKILLS_ROOT = 현재 작업 디렉토리 (CWD)
   인자로 경로가 주어진 경우 해당 경로를 SKILLS_ROOT로 사용

1. Glob "$SKILLS_ROOT/*" → 스킬 디렉토리 목록
   (analyze-skill 자신은 목록에서 제외)
2. 각 스킬에 대해 Phase 0 → 1 → 1.5 → 2 → 2.5~6 순서로 반복
   Phase 6은 각 스킬 분석 직후 건너뜀
   → 전체 분석 완료 후 한 번에 갱신 제안 (사용자 확인 부담 최소화)
   → 단, 각 스킬의 SKILL_TMPDIR은 Phase 6 일괄 갱신 완료 후 삭제
     (Phase 6에서 arbiter.json 참조 + SKILL_HASH 기록이 필요하므로 미리 삭제 금지)
   → Phase 6 일괄 갱신 시 각 스킬의 analyze.md에 해당 SKILL_HASH를 기록해야 함 (캐시 hit 동작 전제)
   → 모든 스킬 Phase 6 완료 후 각 SKILL_TMPDIR을 일괄 삭제
3. 전체 요약 테이블 출력

| 스킬명 | CRITICAL | HIGH | MEDIUM | LOW |
| :--- | :--- | :--- | :--- | :--- |
```

---

## 에이전트 등급 및 토큰 최적화

`analyze-skill`은 역할의 중요도에 따라 에이전트 등급을 추상화하여 관리하며, 런타임에 플랫폼(Claude/Gemini)에 맞는 실제 모델로 해소(Resolve)합니다. 프롬프트 내에 특정 모델명을 직접 쓰지 않고 **등급 변수**를 사용함으로써 유지보수성과 이식성을 극대화합니다.

### 등급 변수 정의 ($GRADE_X)
- **`$GRADE_A`**: 최고 수준의 성능 (추론 중심). 예: Sonnet 3.5, Gemini 1.5 Pro.
- **`$GRADE_B`**: 균형 잡힌 속도와 성능. 예: Haiku 3, Gemini 1.5 Flash.
- **`$GRADE_C`**: 최경량, 대량 데이터 분류 전용. 예: Gemini 1.5 Flash-8b.

### 변수 해소 (Variable Resolution) 워크플로우

변수 해소는 **"스크립트가 데이터를 준비하고, 에이전트(LLM)가 가이드를 읽어 데이터를 찾아내는"** 지시 이행(Instruction Following) 프로세스로 동작합니다.

1.  **준비 (Phase 0 Script)**: 실행 환경을 감지하여 `facts.json`에 `model_map`을 생성합니다.
    - 플랫폼이 `claude-code`면 `$GRADE_A`를 `claude-3-5-sonnet-latest`로 매핑.
    - 미지원 플랫폼이면 `config.json`의 `default` 설정을 사용.
2.  **인지 (Agent)**: 에이전트(나)는 현재 단계의 `Phase MD` 가이드와 `facts.json` 데이터를 동시에 읽습니다.
3.  **대조 및 실행 (Action)**:
    - 가이드에 "이 작업에는 **`$GRADE_A`**를 사용하세요"라는 지침을 확인합니다.
    - 에이전트는 `facts.json`의 `model_map`에서 `$GRADE_A`에 해당하는 실제 모델명을 조회합니다.
    - 조회된 모델명으로 subagent를 호출(`activate_skill` 등)하여 실제 작업을 수행합니다.

### 설정 및 커스텀 (config.json)
`SKILL_ANALYSIS_DIR/config.json`에서 각 등급 변수(`GRADE_A~C`)에 할당될 플랫폼별 모델명과 각 역할(`Expert`, `Arbiter` 등)이 어떤 등급을 사용할지 정의할 수 있습니다.

---

## analyze.md 작성 가이드 (스킬 개발자용)

> analyze.md는 `{SKILL_SELF_DIR}/{분석대상스킬명}/analyze.md` 경로에 보관됩니다.
> `SKILL_SELF_DIR`은 analyze-skill 스킬 자신이 위치한 디렉토리이며,
> Phase 0에서 config.yml을 통해 로드됩니다 (첫 실행 시 자동 생성).
>
> 플랫폼별 예시:
> - Claude Code: `~/.claude/skills/analyze-skill/{분석대상스킬명}/analyze.md`
> - Gemini CLI: `~/.gemini/skills/analyze-skill/{분석대상스킬명}/analyze.md`
>
> **가장 쉬운 방법**: `/analyze-skill [스킬경로]`를 한 번 실행한 뒤 Phase 6에서 자동 생성 제안을 수락하면 됩니다.

```markdown
---
skill: {스킬명}
type: hybrid | prompt | single
version: 1.0
skill_hash: {최초 분석 시 자동 기록}
skill_path: {스킬 절대경로}
---

# {스킬명} Analyze Protocol

## 폴더 구조
{스킬 고유 폴더 구조 설명}

## 아키텍처 개요
{핵심 데이터 흐름}

## 추가 정적 분석 명령 (Phase 1에서 실행)

```bash
grep -rn "{확인할 패턴}" {스킬경로}/
```

## 추가 검사항목 (분석가 기본 체크리스트에 합산)

{스킬 고유 검증 항목}

## 알려진 취약 지점

> 과거 분석에서 확정된 버그 패턴. 수정 완료 시 삭제.

- **{취약점}**: {설명 + 발견 날짜}

## 코드 블록 의도 보정

> SemanticAuditor가 추론한 블록 실행 의도. 다음 분석 시 Phase 1 block_index에 자동 반영.
> 형식: `- {파일명} line {N}: {lang} → intent: {executable|example|pseudo}`

- {예시: SKILL.md line 163: bash → intent: executable}

```markdown
- {예시: SKILL.md line 163: bash → intent: executable}
```
