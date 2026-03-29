---
name: refresh-semantics
description: 아키텍처 및 도메인 시맨틱 분석 (Phase 3~7) 스킬. refresh-architecture의 하위 작업입니다.
---

# 아키텍처 시맨틱 분석 (Phase 3~7)

$ARGUMENTS

> **호출 방식:**
> - `/refresh-architecture target: db-semantics` → 자동으로 이 스킬 호출 (Phase 1~2 완료 후)
> - `/refresh-semantics` → 독립 실행 (기존 메타데이터 기반, `.architecture/` 사용)
> - `/refresh-semantics service: task-service` → 특정 서비스만
>
> **전제 조건:** `db-schemas/{service}.json` 등에 Phase 1~2 구조 정보가 있어야 함.

---

## 핵심 원칙

1. 의미는 코드 전체(FE~BE~데이터~Git)에서 드러난다 — Entity 한 곳이 아님
2. 참조를 세지 말고, 참조에서 **의미를 추출**하고 가중치 투표하라
3. 코드가 말하는 것 vs 데이터가 말하는 것이 다르면 — 그 차이가 버그

---

## 설정값 참조

> Phase 3-7의 가중치, ref 레벨, confidence 임계값, null 해석 테이블 등 모든 설정값:
> `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py semantics-config`
>
> 저장 구조 스키마 + 축약 키 범례:
> `python3 $CLAUDE_PROJECT_DIR/skills/refresh_architecture/scripts/arch-manager.py schema-template`

---

## 3-Tier 실행 전략

| Tier | 범위 | 깊이 | 시간 |
|------|------|------|------|
| T1 (Skeleton) | 전체 컬럼 | 참조 횟수만 | ~5분 |
| T2 (Summary) | Critical/High 테이블 | 의미 1줄 + confidence + lifecycle | ~20분 |
| T3 (Deep) | 이상 컬럼만 | full references + conflict 분석 | 컬럼당 ~30초 |

- T1에서 refCount 0~1인 컬럼은 DEAD/ISOLATED 태깅만 하고 T2 스킵

---

## Phase 3: 소스 코드 참조 분석

**참조마다 추출할 것:** WHERE (파일:라인:레이어), WHAT (의미 추론), WEIGHT (명시성 기반 가중치)

**분석 레이어** (축약 — 상세는 `semantics-config` 참조):
- **3.1 Backend**: Entity → writer/reader/lifecycle/stateMachine/validation 추출
- **3.2 Frontend**: React → uiLabel, formatting, conditionalRender, filterColumn 추출
- **3.3 Test**: assertion 기대값, given/when/then 흐름에서 의미 힌트
- **3.4 Security**: 마스킹/암호화 → securityLevel, 감사 로그 → auditTarget
- **3.5 External**: 외부 시스템 ID → externalSource, 배치 → batchUsage

**집계 절차:**
1. 참조점별 의미를 의미 그룹별로 합산
2. dominant 의미 (최고 가중합) 선정
3. generic 의미는 specific 의미에 흡수 (예: '이벤트 연결' → '판매채널 재고 예약 이벤트')
4. 크로스 컬럼 상호작용 (toMap 복합키, 조건결합, 파생계산) 탐지

---

## Phase 4: 런타임 데이터 분석

- **MCP 접속 가능 시만 실행.** 불가 시 SKIP.
- distinctValues, uniqueRatio, nullRate, lengthPattern 쿼리 (SQL은 `semantics-config` 참조)
- **핵심 불일치 패턴 4가지:**
  1. enum 불일치: 코드 enum N개 vs DB DISTINCT M개
  2. 유니크 가정: 코드 toMap() vs DB uniqueRatio < 1.0
  3. NOT NULL 가정: 코드 null체크 없음 vs DB NULL 존재
  4. 길이 제한: @Column(length=N) vs DB max(length) > N

---

## Phase 5: Git 히스토리 분석

같은 컬럼의 사용 패턴이 시간에 따라 변하면 → semanticEvolution 기록.
구 코드가 구 의미 가정 중이면 버그. (git 명령어는 `semantics-config` 참조)

---

## Phase 6: 관계 그래프 생성

explicitFK, implicitFK, coAccess, stateMachine → db-graph.json (전체 서비스 통합)

---

## Phase 7: 가중치 투표 + Confidence

| Confidence | 기준 |
|------------|------|
| HIGH | 가중합 상위 70%+, 3+ 소스 일관, 불일치 없음 |
| MEDIUM | 50~70%, 2소스, 경미한 불일치 |
| LOW | 50% 미만, 1소스, 불일치 존재 |
| CONFLICT | 2+ 소스 모순 → knownIssue 자동 기록 |

**자동 보강**: data-contracts.json에 Writer/Reader, CONFLICT, 불일치, DEAD, semanticEvolution 자동 기록.

---

## Phase 7.5: Behavioral Flow & Policy Extraction

단일 엔티티 분석을 넘어, 실제 비즈니스 유스케이스의 흐름을 추출합니다.

1. **Entry Point Identification**: 컨트롤러, 서비스 진입점 탐색.
2. **Call Chain Tracing**: 핵심 비즈니스 로직의 호출 경로 추적.
3. **Policy Summarization**: `if/else`, `switch` 등 복잡한 분기 조건을 "비즈니스 정책"으로 요약.
5. **Feature Mapping**: `feature-index.json`을 통해 서비스 간 기능 연결 고리를 매핑하여 횡적 연관성을 완성합니다.
6. **Output**: `flow-{service}.json` 생성 (Mermaid 다이어그램 포함).

---

## Phase 9: Horizontal Linkage & Global Indexing

수만 개의 파일로 구성된 대규모 프로젝트에서 기능의 파편화를 방지하기 위한 전략입니다.

1. **Skeleton (Anchors)**: 물리적 구조를 통해 기능의 시작점과 끝점을 고정합니다.
2. **Glossary (Identity)**: 서로 다른 파일에서 쓰이는 용어들을 비즈니스 관점에서 통합하여 같은 기능임을 인식합니다.
3. **Graph (Pathways)**: DB와 API 관계를 통해 기능이 흐르는 통로를 정의합니다.
4. **Global Index**: `.architecture/metadata/feature-index.json`에 모든 서비스의 기능을 통합 관리하여, LLM이 필요할 때 연관 서비스의 Flow를 즉시 찾아볼 수 있게 합니다.

---

## 예시: event_id 분석 흐름

```
T1 (5분): grep -c "eventId\|event_id" → 5회 → refLevel: LOW
T2 (2분): 5개 참조점에서 WHERE/WHAT/WEIGHT 추출 →
    "판매채널 재고 예약 이벤트 ID" (3.3) dominant
    nullSemantics: "일반재고"
    → db-schemas에 1줄 기록
T3 (온디맨드, 30초): /analyze에서 event_id 조사 시
    → full references + crossColumnInteraction 출력
```
