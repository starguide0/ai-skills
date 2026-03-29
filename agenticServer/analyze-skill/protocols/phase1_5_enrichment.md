<!-- Phase 1.5: Block Intent Enrichment (LLM) -->
<!-- 입력: $SKILL_TMPDIR/facts.json (block_index에 intent=unknown 포함) -->
<!-- 출력: $SKILL_TMPDIR/facts.json (block_index.intent 갱신, in-place 덮어쓰기) -->

## Phase 1.5: Block Intent Enrichment

> **목적**: Phase 1에서 결정론적 grep으로 생성된 block_index는 타입(SHELL/DATA/CODE/PSEUDO)은 정확하지만 `intent`가 모두 `unknown`이다. 이 Phase에서 LLM이 각 .md 파일을 전체 읽어 각 블록의 실행 의도를 분류한다. 이후 전문가들이 일관된 기준으로 분석할 수 있도록 facts.json을 갱신한다.

> **실행 조건**: block_index에 `intent=unknown`인 블록이 1개 이상 있을 때만 실행한다. 모두 이미 알려진 경우 스킵.

---

### 실행 흐름

```
1. facts.json 로드:
   Read "$SKILL_TMPDIR/facts.json"
   → block_index 전체 확인
   → intent=unknown인 블록 목록 추출

2. 미지 블록이 없으면 즉시 종료:
   IF (intent=unknown 블록 수 == 0) → Phase 1.5 스킵, Phase 2로 진행

3. 파일별 그룹화:
   intent=unknown 블록을 file 기준으로 그룹화
   각 파일에 대해 한 번만 Read 수행 (파일당 1회 Read 원칙)

4. 파일별 intent 분류:
   각 파일에 대해:
     a. 파일 전체 Read (skill_dir + "/" + file)
     b. 해당 파일의 unknown 블록들에 대해 intent 분류 (아래 기준 적용)
     c. 결과를 임시 맵에 저장: key = "file:line_start", value = intent

5. facts.json block_index 갱신:
   intent=unknown인 모든 블록의 intent를 분류 결과로 교체
   갱신된 facts.json을 "$SKILL_TMPDIR/facts.json"에 덮어쓰기

5.5. 갱신 검증:
   갱신된 facts.json을 재로드하여 intent=unknown인 블록이 0개인지 확인한다.
   IF unknown 블록 수 > 0:
     → "경고: {N}개 블록의 intent 갱신 실패 — 알려진 intent만 적용된 상태로 계속 진행"을 출력하고 진행한다.
     → 전체 중단하지 않는다 (부분 갱신 상태로도 Phase 2 분析 가능).

6. 요약 출력:
   갱신된 블록 수와 intent 분포 출력
   예: "Phase 1.5 완료: 12개 블록 갱신 — {executable:5, example:4, pseudo:2, schema:1}"
```

---

### Intent 분류 기준

각 블록에 대해 **전체 파일 맥락**을 고려하여 4가지 중 하나를 선택한다:

| Intent | 정의 | 판별 신호 |
|--------|------|-----------|
| `executable` | 실제로 실행되어야 하는 코드 | 명령어 형식, 변수 치환($VAR), 출력 파일 생성, 단계 지시 내 포함 |
| `example` | 예시/참고용 코드 (실행 불필요) | "예시:", "예:", "형식:", 예제 블록, 출력 형식 설명 |
| `pseudo` | 의사코드 또는 흐름 설명 | IF/ELIF/ELSE 나열, 번호 매긴 절차, 자연어 혼합, bash 문법 오류 허용 |
| `schema` | 데이터 구조 명세 (JSON/YAML 샘플 등) | JSON 예시 객체, 필드 설명용 구조체, "출력 형식", "입력 형식" |

**모호한 경우 판단 규칙**:
- SHELL 타입 블록이 섹션 지시 내에 있고 `$VAR` 치환 포함 → `executable`
- SHELL 타입이지만 자연어 설명 안에 인용된 경우 → `example`
- PSEUDO 타입은 대부분 `pseudo`이나, 단순 번호 절차면 `executable` 가능
- DATA 타입(JSON) 블록이 출력 형식 설명이면 → `schema`

**확신이 없을 때**: `example`로 분류 (오탐 최소화)

---

### 출력 형식 (facts.json 갱신)

block_index의 각 항목에서 `intent` 필드만 교체한다:

```json
{
  "file": "phase0.md",
  "block_number": 2,
  "type": "SHELL",
  "lang": "bash",
  "intent": "executable",
  "section": "Phase 0: 대상 스킬 파악",
  "line_start": 29,
  "line_end": 58,
  "summary": "CONFIG_FILE 로드 또는 초기화"
}
```

변경 후 `$SKILL_TMPDIR/facts.json`을 덮어쓰기 저장한다.

**`_expert_views` 동기화 필수**: `_expert_views`는 Phase 1에서 block_index를 슬라이싱한 독립 복사본이므로,
block_index를 갱신해도 `_expert_views` 내부의 intent는 자동 반영되지 않는다.
다음 방법으로 동기화한다:

```
갱신된 intent_map (key="file:line_start", value=intent)을 이용하여
facts._expert_views 내의 모든 block entry의 intent도 동일하게 교체한다.
```

동기화 완료 후 검증:
- facts.json을 재로드하여 `_expert_views` 내 intent=unknown 블록 수를 확인한다.
- block_index의 unknown 수와 _expert_views의 unknown 수가 일치하면 정상.
- 불일치 시 "경고: _expert_views 동기화 불완전 ({N}개 미동기화)" 출력 후 계속 진행.

---

### Phase 1.5 완료 후 Phase 2 전환

Phase 1.5 결과를 요약 출력 후 즉시 Phase 2로 진행한다.
전문가 파견 시 "Phase 1.5에서 block intent 갱신 완료"를 파견 지시에 명시한다.
