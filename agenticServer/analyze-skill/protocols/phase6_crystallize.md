<!-- Phase 6: 지식 결정화 -->
<!-- 입력: $SKILL_TMPDIR/arbiter.json, $ANALYZE_MD_PATH -->
<!-- 출력: analyze.md 생성/갱신 제안 (사용자 확인 후) -->
<!-- 필수 변수: SKILL_TMPDIR, SKILL_DIR, SKILL_ANALYSIS_DIR -->
<!-- SKILL_ANALYSIS_DIR 획득: phase0_result.json의 skill_analysis_dir 필드 -->
<!-- python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['skill_analysis_dir'])" $SKILL_TMPDIR/phase0_result.json -->

## Phase 6: 지식 결정화 — analyze.md 생성/갱신 (사용자 확인)

> **목적**: 이번 분석에서 LLM 추론으로 어렵게 발견한 버그를 다음 실행에서는 bash/grep으로 기계적으로 잡을 수 있도록 analyze.md에 변환·저장한다.
> Phase 5 완료 후 실행한다. **사용자 확인 없이 파일을 수정하지 않는다.**

### Arbiter의 지식 결정화 임무

arbiter.json의 `inferred_as_deterministic` 항목을 기반으로:

1. **반복 발생 가능하고 정형화된 패턴** 선별 (CONFIRMED CRITICAL/HIGH 우선)
2. 해당 버그를 검출할 수 있는 최적의 **grep 또는 bash 명령** 생성
3. 다음 실행의 Phase 1에서 결정론적으로 확인할 수 있도록 analyze.md에 추가

### 코드 블록 의도 보정 기록 (SemanticAuditor 결과 반영)

SemanticAuditor의 `block_intent_inference` 항목 중 신뢰도 높은 추론을 analyze.md에 기록 제안:

```markdown
## 코드 블록 의도 보정
- SKILL.md line {N}: {lang} → intent: {executable|example|pseudo}
```

다음 분석 시 Phase 1 block_index 생성 시 자동 반영 (intent `unknown` 해소).
사용자 확인 후 추가하며, 수정 완료 항목은 사용자가 직접 삭제한다.

### skill_hash 갱신 (필수)

analyze.md 상단 frontmatter에 현재 `SKILL_HASH`를 기록한다:

```yaml
---
skill: {스킬명}
type: hybrid | prompt | single
version: 1.x
skill_hash: {SKILL_HASH}
skill_path: {SKILL_ABS_PATH}
---
```

---

### Case A: analyze.md 없음 (AUTO 모드) → 신규 생성 제안

```
analyze.md가 없습니다. 이번 분석 결과를 바탕으로 생성하시겠습니까?

저장 경로: $SKILL_ANALYSIS_DIR/{SKILL_NAME}/analyze.md
생성될 내용:
  - skill_hash: {SKILL_HASH}
  - 추가 정적 분석 명령 {N}개 (LLM 추론 → grep 결정론적 변환)
  - 알려진 취약 패턴 {M}개 (CONFIRMED CRITICAL/HIGH 버그 기반)

(N=0, M=0이면 저장할 내용이 없으므로 건너뜀)
[Y] 생성  [N] 건너뜀  [E] 내용 확인 후 결정
```

---

### Case HITL: 사용자 답변이 있는 경우 (UNCERTAIN 항목 확정)

> **진입 조건**:
> 1. `$SKILL_TMPDIR/hitl_answers.json`이 존재하고
> 2. `hitl_answers.json`의 `answers[]`가 비어있지 않은 경우에만 실행한다.
> `hitl_answers.json`이 없거나 `answers[]`가 비면 이 섹션 전체를 생략한다.
> (Phase 5에서 사용자가 모두 건너뛴 경우 `answers: []`로 기록됨)

`$SKILL_TMPDIR/hitl_answers.json`을 읽어 각 답변을 analyze.md에 반영한다.

**YES 답변 (CLEARED 확정):**
```
[추가] 추가 정적 분析 명령 — 다음 분析에서 자동 확인
  + # [{버그 설명} 검증 — YES 확정({날짜})]
  + {clarifying_question의 핵심 패턴을 grep 명령으로 변환}
```
예시:
```
  + # [ANALYZE_MD_PATH 전달 여부 검증 — YES 확정(2026-03-22)]
  + grep -rn 'ANALYZE_MD_PATH' phases/phase2_experts.md
```

**NO 답변 (CONFIRMED 확정):**
```
[추가] 알려진 취약 지점
  + - **{버그 설명}**: {evidence} — HITL 확정({날짜})
```
예시:
```
  + - **ANALYZE_MD_PATH 미전달**: Phase 2 파견 시 CUSTOM 모드 값 누락 — HITL 확정(2026-03-22)
```

**답변 없음 (사용자가 건너뜀):**
- UNCERTAIN 상태 유지 → analyze.md에 기록하지 않음
- 다음 분析 시 동일 질문 재발생 가능

사용자 확인 메시지 형식:
```
HITL 답변 반영 ({N}건):

[YES → CLEARED] LA-001: 추가 정적 분析 명령에 grep 추가
[NO → CONFIRMED] CG-003: 알려진 취약 지점에 추가

위 내용을 analyze.md에 반영할까요?
[Y] 적용  [S] 항목별 선택  [N] 건너뜀
```

---

### Case B: analyze.md 있음 (CUSTOM 모드) → 갱신 제안

```
analyze.md 갱신 제안 ({N}개 항목):

[갱신] skill_hash
  ~ skill_hash: {이전 해시} → {SKILL_HASH}

[추가] 추가 정적 분석 명령
  + # [ENCODED 계산 검증]
  + echo '/a/b/c' | tr '/' '__'   # 단일 언더스코어 확인용

[추가] 알려진 취약 패턴
  + - **TMPDIR 시스템 변수 충돌**: Phase 0에서 TMPDIR 사용 시 시스템 오염 (2026-03-21)

각 항목을 개별 승인하시겠습니까? [Y] 전체 적용  [S] 항목별 선택  [N] 건너뜀
```

---

### 공통: analyze.md 수정 규칙

- 저장/수정 경로: `$SKILL_ANALYSIS_DIR/{SKILL_NAME}/analyze.md`
  - `$SKILL_ANALYSIS_DIR`은 Phase 0 step 3에서 config.yml 로드 후 설정됨 (= SKILL_SELF_DIR)
  - 서브디렉토리는 Phase 0 step 4에서 `mkdir -p "$ANALYZE_MD_DIR"`으로 이미 생성됨
- 기존 내용은 절대 삭제하지 않는다 (추가만)
- `알려진 취약 패턴` 섹션의 수정 완료 항목은 사용자가 직접 삭제한다
- `version` frontmatter를 patch 단위로 올린다 (예: 1.1 → 1.2)
- `skill_hash`는 매 분석마다 갱신한다

### 공통: 임시 파일 삭제 (필수)

Phase 6 처리(생성/갱신/건너뜀) 완료 후 SKILL_TMPDIR을 삭제한다:

```bash
rm -rf "$SKILL_TMPDIR"
echo "임시 파일 삭제 완료: $SKILL_TMPDIR"
```

삭제 실패 시 경로를 사용자에게 알리고 수동 삭제를 안내한다.

---

## Schema Drift 갱신 (Phase 0에서 DRIFT_DETECTED인 경우)

phase0_result.json의 schema_drift.status == "DRIFT_DETECTED"이면:

1. diff 내용 표시:
   - 추가된 파일: {diff.added_files}
   - 제거된 파일: {diff.removed_files}
   - 추가된 필드: {diff.added_fields}

2. LLM 판단: "이 변경이 Phase 간 계약에 영향을 주는가?"
   - 예: phase_output_files 추가 → 소비 Phase 확인 필요 → schema files 섹션 갱신 제안
   - 아니오: _fingerprint + _skill_hash만 갱신

3. 사용자 확인 후 state.schema.json 갱신:
   - _skill_hash: {new_skill_hash}
   - _fingerprint: {new_fingerprint}
   - _fingerprint_source: {new_structural}
   - files 섹션: 변경 항목만 업데이트
