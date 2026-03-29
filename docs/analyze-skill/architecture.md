---
title: analyze-skill 아키텍처 설계 문서
version: 4.0.0
date: 2026-03-20
status: implemented
---

# analyze-skill 아키텍처 설계

## 개요

analyze-skill은 다른 스킬의 품질을 체계적으로 분석하는 메타 스킬이다.
v4.0.0에서 MoT(Mixture of Thoughts) + Worker-C 숙의 프로토콜을 도입하여
LLM 비결정성으로 인한 Recall 문제를 해소했다.

---

## 핵심 설계 원칙

### 문제 진단: CoVe만으로는 재현성을 보장할 수 없다

v3.0.0까지는 CoVe(Chain-of-Verification)를 적용했으나 두 run의 결과가 수렴하지 않는 문제가 있었다.

```
CoVe가 해결하는 것:   Precision (발견된 버그가 진짜인가?) → False Positive 제거
CoVe가 해결 못하는 것: Recall (어떤 버그가 발견되어야 하는가?) → Coverage 보장 불가
```

두 run의 결과가 달랐던 근본 원인:
1. **Worker-B가 극도로 underspecified** → LLM 자유도가 너무 높아 run마다 다른 관점 탐색
2. **모드 차이** → B-002(자기참조 경로 버그)가 발동해 한 run은 AUTO, 다른 run은 CUSTOM 모드
3. **역방향 검증 질문** → "X가 없는가?" 형태 질문이 "모든 질문 Yes면 CONFIRMED" 규칙과 상충

### 해결: MoT는 Recall, CoVe는 Precision

```
MoT (Phase 2): Worker-B × N=3 독립 병렬 실행 → Coverage 확보
CoVe (Phase 3): 각 run 내 False Positive 제거 → Precision 확보
숙의 (Phase 4): 앙상블 합성 + 충돌 분류 → 신뢰도 계산 + 결정론적 해소
```

두 메커니즘은 레이어가 다르며 대체재가 아닌 보완재다.

---

## 파이프라인 구조 (v4.0.0)

```
Phase 0: 대상 파악 + TMPDIR 생성
Phase 1: 정적 분석 (Lead 직접) → facts.json
Phase 2: Worker-A (1x) + Worker-B × N=3 (MoT)
         → worker_a_raw.json
         → worker_b_1_raw.json / worker_b_2_raw.json / worker_b_3_raw.json
Phase 3: Worker-V (CoVe, 단일 에이전트 순차 처리)
         → worker_a.json
         → worker_b_verified.json (3개 run 병합 + found_in_runs + run_count)
Phase 4: Worker-C (MoT 숙의)
         → worker_c.json (신뢰도 + 충돌 분류 + fix_order + escalations)
Phase 5: 결과 통합 출력
Phase 6: analyze.md 생성/갱신 (사용자 확인)
```

---

## Worker-C 숙의 프로토콜

### Step 1: 신뢰도 계산

```
confidence = run_count / N  (N=3)

≥ 0.8 → HIGH_CONFIDENCE  (즉시 수정)
0.4~0.8 → PROBABLE       (추가 검증)
0.2~0.4 → UNCERTAIN      (컨텍스트 의존 가능성)
< 0.2  → NOISE           (스펙 모호 또는 환경 의존)
```

Worker-A 버그는 단일 run → confidence = 1.0 고정.

### Step 2: 충돌 분류 (Conflict Taxonomy)

| 유형 | 정의 | 처리 |
|------|------|------|
| **Type 1** 사실 충돌 | 같은 대상, 반대 사실 | 결정론적 폴백 (grep) |
| **Type 2** 컨텍스트 의존 | 둘 다 true, 조건 다름 | 조건부 기록, CLEARED 불가 |
| **Type 3** 인과 충돌 | 버그 A 수정 시 B의 전제 변경 | fix_order 의존 그래프 |
| **Type 4** 결정 불가 | 스펙 모호, N회 실행해도 수렴 안 함 | ESCALATE + 구조화 질문 |

### Step 3: 결정론적 폴백 체인

```
Type 1/3 충돌 감지
  └→ grep으로 답할 수 있는가?
       YES → Bash grep 실행 → 사실 확정
       NO  → Type 4 재분류 → ESCALATE
```

LLM이 판단하는 영역을 최소화하고, 판단이 어려울수록 결정론적 방법(grep)
또는 구조화된 출력(질문)으로 위임한다.

### Step 4: ESCALATE 구조화 질문 (Type 4)

단순 플래그가 아닌 최소 질문으로 출력:

```json
{
  "clarifying_question": "Phase 0 타입 감지 시 analyze.md를 명시적으로 제외하지 않은 것이 의도된 설계인가?",
  "decision_impact": "YES → CLEARED / NO → CONFIRMED + 제외 목록 수정 필요"
}
```

**"수렴 실패 자체가 신호"**: N회 실행해도 판정이 갈리면 스펙 모호성을 의미한다.
숙의의 올바른 종료점은 모든 충돌 해소가 아니라 **해소 가능한 것과 불가능한 것의 분리**다.

---

## 패러다임 분류

현재 구조는 GoT(Graph of Thoughts)와 유사해 보이나 GoT가 아니다.

| GoT 특성 | analyze-skill |
|---------|-------------|
| Thought vertices + edges | ✅ |
| Aggregation 연산 | ✅ Worker-V |
| **동적 그래프 구성** | ❌ 실행 전 구조 고정 |
| **사이클/피드백 루프** | ❌ Phase 4 → Phase 2 재귀 없음 |
| **조건부 분기 확장** | ❌ ESCALATE가 새 Worker-B 트리거 안 함 |

**정확한 분류: MoA (Mixture of Agents) + 정적 검증 파이프라인**

GoT화를 위해서는 Worker-C의 low-confidence/ESCALATE 결과가
타겟 프롬프트로 Worker-B를 재파견하고 그래프 노드를 동적으로 추가하는
피드백 루프가 필요하다. 현재는 사람에게 위임(ESCALATE)으로 루프를 닫는다.

---

## v3.0.0 → v4.0.0 변경 내역

### 버그 수정

| ID | 심각도 | 내용 |
|----|--------|------|
| B-001 | HIGH | Worker-A 섹션 내 출력 파일명 충돌 (`worker_a.json` → `worker_a_raw.json`) |
| B-002 | HIGH | ANALYZE_MD_PATH 자기참조 중복 경로 생성 → 자기참조 감지 분기 추가 |
| B-003 | MEDIUM | 타입 감지에서 analyze.md 암묵적 제외 → 명시적 제외 목록 추가 |
| B-004/B-005 | MEDIUM | Worker-B 명세 극도 부족 → 체크리스트 + 출력 스키마 전면 추가 |
| C-001 | MEDIUM | 역방향 검증 질문("X가 없는가?") → "사실이면 Yes" 형태 강제 규칙 추가 |

### 아키텍처 개선

| 항목 | 변경 |
|------|------|
| Worker-B 실행 | 1회 → N=3회 병렬 (MoT) |
| Phase 3 출력 | `worker_b.json` → `worker_b_verified.json` (run_count, found_in_runs 포함) |
| Phase 4 Worker-C | 단순 교차 검증 → MoT 숙의 (5단계 프로토콜) |
| worker_c.json 스키마 | `confirmed/cleared/new_bugs` → + `conflicts`, `fix_order`, `escalations`, `confidence` |
| Phase 5 출력 | 버그 목록 → + 신뢰도 컬럼, 충돌 해소 현황, 수정 순서, ESCALATE 테이블 |

---

## 실행 메커니즘 주의사항

SKILL.md는 Workers를 역할로 기술하지만 실제로는 모두 Agent tool 호출(subagent)이다.

**MoT 독립성 보장 요건:**
- Worker-B × 3: 반드시 독립 subagent 호출 (서로의 결과 격리)
- Worker-V: 단일 subagent 허용 (검증 단계 — 발견이 아님)
  단, cross-run 참조 금지: run-1 검증 완료 후 run-2 검증 원칙

**Worker-V 독립성 한계:**
단일 Worker-V가 3개 raw 파일을 동시에 수신하면 confirmation bias 가능성이 있다.
완전한 독립을 원하면 Worker-V × 3 병렬 실행 + Worker-C merge 구조로 전환 필요
(비용 증가와 독립성 사이의 트레이드오프).
