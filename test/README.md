# Test Skill Suite — 사용 가이드

> **Version**: v6.4 | **Updated**: 2026-02-22

Jira 티켓 기반 E2E 테스트 오케스트레이션 스킬 스위트입니다.
테스트 계획(Plan) → 데이터 매핑(Data) → 실행(Execute) → 보고서(Report)를 단일 명령으로 자동 처리합니다.

**기술 문서:**
- [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) — 설계 철학, 아키텍처 다이어그램, 실행 모델, 파이프라인 상세
- [doc/HOOKS.md](doc/HOOKS.md) — 훅 시스템, PreToolUse/PostToolUse 훅 전체 명세

---

## 파이프라인 개요

| Step | 이름 | 역할 | Auto-Skip 조건 |
|------|------|------|---------------|
| **0** | Init | Workspace 검증 + 리소스 로드 | — |
| **1** | Verify (Gate) | Jira vs 구현 비교, 서버 접속 확인 | — |
| **2** | Sheet Check | 기존 시트 baseline 비교 | — |
| **3** | Plan | 테스트시트 생성 | mode = REUSE |
| **3.5** | Plan Review | 사용자 확인 후 Step 4 진행 | REUSE 시 스킵 |
| **4** | Data | TC별 데이터 매핑 | 매핑 존재 + 시트 버전 일치 |
| **5** | Execute | DAG 기반 병렬 실행 | — |
| **6** | Report | Confluence 보고서 생성 | — |
| **6.5** | Review | 보고서 의미적 검증 (선택) | TC 4개 이하 + Fail 없음 |
| **7** | Post | Confluence 업로드, Jira 코멘트 | `test/_post.md` 없음 |

---

## 사용 가이드

### 전체 테스트 (가장 일반적)

```
"PROJ-123 테스트 실행해줘"
"PROJ-123 E2E 테스트"
"PROJ-123 처음부터 끝까지 테스트"

→ test-run: Step 0~6 순차 실행 (필요한 Step만 자동 실행)
```

### 새 프로젝트 테스트 환경 초기화

```
"테스트 환경 초기화해줘"
"테스트 폴더 세팅해줘"

→ test-init: 폴더 구조 + 보일러플레이트 + 스캐폴드 생성
```

### 테스트 계획만 수립

```
"PROJ-123 테스트 계획 작성해줘"

→ test-plan: 단독 실행 (자체 Jira 조회 + 코드 분석)
```

### 테스트 데이터만 준비

```
"PROJ-123 테스트 데이터 찾아줘"

→ test-data: DB 크로스 워크플레이스 검색, 매핑 파일 생성
```

### 실패한 Batch만 재실행

```
"PROJ-123 Batch 2만 다시 실행해줘"

→ test-run: Step 5만 부분 실행, 기존 성공 결과 유지
```

### 보고서만 재생성

```
"PROJ-123 결과 리포트 다시 생성해줘"

→ test-reporter: partial_results/ 기반 재생성
```

### 강제 데이터 생성

```
"PROJ-123 데이터 강제로 생성해줘"

→ 기존 매핑 무시, API로 새 데이터 생성
```

### 테스트 후 Confluence/Jira 연동

```
"PROJ-123 테스트 끝나면 Confluence에 올려줘"
"PROJ-123 테스트 결과 Jira에 코멘트 달아줘"

→ test/_post.md에 액션 정의 → Step 7에서 자동 실행
```

**`test/_post.md` 설정 예시:**
```markdown
## confluence-upload
- source: confluence
- space: WMS
- parent: QA 테스트 결과
- title: [{ticket}] {summary} 테스트결과 {version}
- mode: create_or_update

## jira-comment
- condition: {result} == PASS
- content: |
    테스트 완료: {result} ({pass_count}/{total_count})
```

미설정 시: Step 7이 자동으로 스킵됩니다.

---

## Auto-Skip Logic

| Step | 스킵 조건 | 메시지 |
|------|----------|--------|
| Step 3 (Plan) | mode = REUSE | "기존 시트 v{N} 사용 (baseline 동일)" |
| Step 3.5 (Checkpoint) | mode = REUSE | "REUSE — Checkpoint 스킵" |
| Step 4 (Data) | 매핑 존재 + 시트 버전 일치 | "기존 데이터 매핑 사용 (시트 버전 일치)" |
| Step 5 (Execute) | — | 항상 실행 |
| Step 6 (Report) | — | 항상 실행 |
| Step 6.5 (Review) | TC ≤ 4개 AND Fail 0개 | "소규모 테스트 — Review 스킵" |
| Step 7 (Post) | `test/_post.md` 없음 | "[Step 7] ⏭️ _post.md 없음 — 후처리 스킵" |

---

## 버전 관리

### 테스트시트 버전 (Major)

| 조건 | 버전 | 예시 |
|------|------|------|
| 최초 생성 | v1 | `PROJ-123_테스트시트_v1_20260222.md` |
| baseline 변경 감지 | v{N+1} | `PROJ-123_테스트시트_v2_20260223.md` |
| baseline 동일 (REUSE) | 유지 | 기존 v2 그대로 사용 |

### 결과 리포트 버전 (Major.Minor)

| 조건 | 버전 | 예시 |
|------|------|------|
| 테스트시트 v{N} 기반 첫 실행 | v{N}.1 | `v2.1` |
| 동일 시트 기반 재실행 | v{N}.{M+1} | `v2.2` |

### 파일 명명 규칙

| 파일 유형 | 패턴 |
|-----------|------|
| 테스트시트 | `{티켓}_테스트시트_v{N}_{YYYY-MM-DD}.md` |
| 데이터매핑 | `{티켓}_데이터매핑.json` |
| 결과리포트 | `{티켓}_Confluence_테스트결과_v{N.M}_{YYYY-MM-DD}.md` |

---

## 증거 체계 (Evidence System)

모든 TC는 검증 가능한 증거를 포함해야 합니다.

### 근거 수준 (Level of Evidence)

| Level | 설명 | 필수 사용 케이스 |
|-------|------|----------------|
| **1** | 기본 (기대 vs 실제) | 단순 조회 |
| **2** | 표준 (+ 검증 쿼리/API 응답) | 일반 CRUD |
| **3** | 상세 (+ 사이드이펙트 확인) | 비즈니스 로직 |
| **4** | 전문가 (+ 원인 분석, 재현 조건, 개발자 액션) | **모든 Fail (필수!)** |

### Pass 근거 (Level 2-3)

필수: 기대값 vs 실제값 + 검증 쿼리/API 응답 + 사이드이펙트 확인

### Fail 근거 (Level 4 필수!)

필수: 기대값 vs 실제값(불일치) + 실패 지점 + **근본 원인 분석**(코드 위치) + **재현 조건** + **개발자 액션**(수정 제안) + 증거 자료

### 자가 점검 3가지 질문

1. **투명성**: 내 근거를 보고 누구나 같은 결론에 도달하는가?
2. **재현성**: 개발자가 내 증거로 직접 검증할 수 있는가?
3. **실행성**: Fail 시, 개발자가 즉시 수정 작업에 착수할 수 있는가?

---

## Troubleshooting & Recovery

### Partial Failure (부분 실패)

```
증상: partial_results/ 에 일부 시나리오 결과 누락
조치: "PROJ-456 Batch 2만 다시 실행해줘"
→ 실패한 배치만 재실행, 기존 성공 결과 유지
```

### Gate 중단 후 재실행

```
증상: Step 1에서 "중단" 선택 후 Jira/코드 수정
조치: 재실행 시 Step 0부터 시작
→ 이전 시트/매핑은 Step 2/4에서 자동 판정
```

### Report 생성 실패

```
증상: 에이전트 오류로 최종 보고서 생성 중단
조치: "PROJ-456 결과 리포트 다시 생성해줘"
→ test-reporter가 partial_results/ 기반으로 재생성
```

### NEEDS_INPUT (최초 설정)

```
증상: test-init이 스캐폴드에서 {TODO} 발견
선택:
  [1] 지금 입력 → 각 {TODO} 항목에 대해 순차 질문
  [2] 나중에 입력 → 파일 위치 안내 후 종료
  [3] 기존 파일 참조 → 경로 지정하여 자동 채움
```

### 메타데이터 없음 (SOURCE_DIRECT)

```
증상: Gate Step 1.0에서 .claude/architecture/ 가 없어 SOURCE_DIRECT 판정
선택:
  [1] 이대로 진행 → 소스코드 직접 분석 (정확도 저하 감수)
  [2] 참조 데이터 경로 변경 → 사용자가 기존 메타데이터 위치 입력
  [3] SOURCE_DIRECT로 확정
```

---

## 최근 변경사항 (v6.4)

### Step 3.5 — Plan Review Checkpoint (신규)

테스트시트 생성 완료 후, 데이터 매핑으로 넘어가기 전에 **사용자 확인 단계**가 추가되었습니다.

- TC 개수, 시나리오 목록, 데이터 요구사항 요약을 제시
- 승인 → Step 4 진행 / 수정 요청 → 재생성 / 중단 → 파이프라인 종료
- REUSE 시 자동 스킵 (기존 시트 그대로 사용)

**효과**: 불필요한 Data/Execute 실행 방지, 테스트시트 품질 사전 확인

### Step 6.5 — Review Agent (신규)

최종 보고서에 대해 `test-review-agent`(Worker)가 **의미적 검증**을 수행합니다.

- 커버리지, 근거 품질, 논리 일관성, 누락 TC 자동 검출
- NEEDS_REVISION + critical 이슈 → 사용자 보고 후 수정 여부 확인
- 소규모 테스트(TC ≤ 4개, Fail 0개)는 자동 스킵

**효과**: AI가 AI 결과물을 리뷰하여 보고서 품질 일관성 향상

### 훅 시스템 — remind_caution.py (신규)

DB 쿼리 또는 API 호출 실행 직후, `_caution_common_errors.md`에서 관련 주의사항을 자동으로 리마인드합니다.

- MCP PostgreSQL 5개 DB 쿼리 후 자동 실행
- Bash로 stimulus_executor / curl 실행 후 자동 실행
- 상세: [doc/HOOKS.md](doc/HOOKS.md) 참조

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| **v6.4** | **2026-02-22** | **Step 3.5 Checkpoint, Step 6.5 Review 신규. remind_caution.py 훅 추가. README/ARCHITECTURE/HOOKS 문서 분리** |
| v6.3 | 2026-02-21 | 상태 관리 확장: Write-Through + Read-Through Cache 패턴 문서화 |
| v6.2 | 2026-02-20 | 메타데이터 토큰 예산 추가 |
| v6.1 | 2026-02-20 | 실행 모델 및 설계 개념 섹션 추가 |
| v6.0 | 2026-02-20 | Step 7 (Post) 추가, test-reporter v3.0 반영 |
| v5.1 | 2026-02-14 | Gate v4.1, test-run v4.2 반영 |
| v5.0 | 2026-02-14 | Gate v4.0 (서비스 탐색, 서버 접속, 모바일 시뮬레이션) |
| v4.0 | 2026-02-13 | README 전면 재작성 (설계서 + 사용 가이드 통합) |
| v3.0 | 2026-02-13 | 단일 오케스트레이터 통합, Jira-First Gate 도입 |
