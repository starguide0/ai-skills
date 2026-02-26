---
name: test-post
description: "Reads project-level _post.md and executes post-test actions (Confluence upload, Jira comment, etc.) after report generation."
version: 1.0.0
---

# Test Post-Processing Skill

## Purpose

테스트 완료 후 프로젝트별로 정의된 후처리 액션을 실행합니다. `test/_post.md` 파일이 존재하면 해당 내용을 파싱하여 자동 실행합니다.

---

## Interface Contract

### INPUT
| 필드 | 출처 | 필수 | 설명 |
|------|------|------|------|
| test/_post.md | 프로젝트 설정 | N | 후처리 액션 정의 파일 (없으면 Step 7 스킵) |
| ctx.ticket | test-run | Y | 티켓 ID |
| ctx.ticket_folder | test-run | Y | 티켓 폴더 경로 |
| ctx.test_baseline | test-gate | Y | 테스트 기준 정보 (summary, branch 등) |
| ctx.report_result | test-reporter | Y | 최종 결과 (pass_count, fail_count, total_count, result) |
| ctx.confluence_file | test-reporter | Y | Confluence 결과 파일 경로 |
| ctx.result_file | test-reporter | Y | 테스트결과 파일 경로 |
| ctx.sheet_file | test-plan | Y | 테스트시트 파일 경로 |

### OUTPUT
| 필드 | 소비자 | 설명 |
|------|--------|------|
| post_actions_result | 사용자 | 각 액션별 실행 결과 (성공/실패/스킵) |

---

## ctx 복원 (Read-Through Fallback)

> 각 입력 필드가 ctx에 없으면 파일에서 복원한다:
> - ctx.ticket, ctx.ticket_folder → 복원 불가 (최상위 컨텍스트). 없으면 사용자에게 재질문.
> - ctx.test_baseline 없으면 → Glob `{ticket}_gate_*.json` → 최신 → JSON parse
> - ctx.report_result 없으면 → Read `partial_results/_summary.json` → JSON parse
> - ctx.confluence_file 없으면 → Glob `{ticket}_Confluence_테스트결과_v*.md` → 최신 버전
> - ctx.result_file 없으면 → Glob `{ticket}_테스트결과_v*.md` → 최신 버전
> - ctx.sheet_file 없으면 → Glob `{ticket}_테스트시트_v*.md` → 최고 버전
> - 파일도 없으면 → ERROR: "선행 Step 미완료" → 해당 변수 사용 액션 스킵

---

## `_post.md` 파일 형식

### 위치

`test/_post.md` (프로젝트 루트의 test/ 직하)

### 사용 가능한 변수

액션 정의에서 `{변수명}` 형태로 사용합니다. 런타임에 실제 값으로 치환됩니다.

| 변수 | 설명 | 예시 |
|------|------|------|
| `{ticket}` | 티켓 ID | WO-55 |
| `{summary}` | Jira 티켓 요약 | 작업자 할당해제 NPE 수정 |
| `{version}` | 테스트결과 버전 | v1.1 |
| `{sheet_version}` | 테스트시트 버전 | v1 |
| `{date}` | 실행 일자 | 2026-02-20 |
| `{result}` | 전체 결과 | PASS 또는 FAIL |
| `{pass_count}` | PASS TC 수 | 4 |
| `{fail_count}` | FAIL TC 수 | 0 |
| `{total_count}` | 전체 TC 수 | 4 |
| `{ticket_folder}` | 티켓 폴더 절대 경로 | /Users/roy/workspace/test/WO-55_할당해제NPE수정 |
| `{confluence_file}` | Confluence 파일 절대 경로 | .../WO-55_Confluence_테스트결과_v1.1_2026-02-20.md |
| `{result_file}` | 테스트결과 파일 절대 경로 | .../WO-55_테스트결과_v1.1_2026-02-20.md |
| `{sheet_file}` | 테스트시트 파일 절대 경로 | .../WO-55_테스트시트_v1_2026-02-20.md |
| `{branch}` | 변경 브랜치명 | feature/WO-55-job-inprogress-npe |

### 액션 블록 형식

각 액션은 `## action-type` 헤더로 시작하며, 하위에 key-value 속성을 정의합니다.

```markdown
## {action-type}
- key: value
- key: value
```

### 조건부 실행

각 액션 블록에 `condition` 속성을 추가하여 조건부 실행이 가능합니다.

```markdown
## confluence-upload
- condition: {result} == PASS
- ...
```

지원 조건:
- `{변수} == 값` — 같으면 실행
- `{변수} != 값` — 다르면 실행
- `always` — 항상 실행 (기본값, condition 생략 시)

---

## 지원 액션 유형

### 1. `confluence-upload`

Confluence 페이지를 생성하거나 업데이트합니다.

```markdown
## confluence-upload
- source: confluence
- space: QA
- parent: 테스트 결과 모음
- title: [{ticket}] {summary} 테스트결과 {version}
- mode: create_or_update
```

| 속성 | 필수 | 설명 |
|------|------|------|
| source | Y | 업로드할 파일 유형: `confluence` (Confluence 포맷), `result` (테스트결과), `sheet` (테스트시트) |
| space | Y | Confluence Space Key |
| parent | N | 부모 페이지 제목 (없으면 Space 루트에 생성) |
| title | Y | 페이지 제목 (변수 치환 가능) |
| mode | N | `create` (새로 생성), `update` (기존 업데이트), `create_or_update` (기본값) |
| condition | N | 실행 조건 (기본: always) |

**실행 로직**:
1. source에 해당하는 파일 경로 resolve (`confluence` → ctx.confluence_file 등)
2. 파일 내용 읽기
3. Confluence API로 Space 조회 → parent 페이지 검색
4. mode에 따라 생성 또는 업데이트
5. 결과 URL 출력

### 2. `jira-comment`

Jira 티켓에 코멘트를 추가합니다.

```markdown
## jira-comment
- content: |
    테스트 완료: {result} ({pass_count}/{total_count})
    시트: {sheet_version}, 결과: {version}
- condition: always
```

| 속성 | 필수 | 설명 |
|------|------|------|
| content | Y | 코멘트 내용 (변수 치환 가능, 여러 줄 가능) |
| condition | N | 실행 조건 (기본: always) |

**실행 로직**:
1. content의 변수 치환
2. Jira API로 코멘트 추가 (addCommentToJiraIssue)
3. 결과 출력

### 3. `custom`

사용자 정의 액션 (향후 확장용). 현재는 메시지 출력만 지원.

```markdown
## custom
- name: 슬랙 알림 메모
- message: "{ticket} 테스트 완료 — 수동으로 슬랙에 공유 필요"
```

---

## Logic Flow

```
1. _post.md 존재 확인
   - Glob: test/_post.md
   - 없으면 → "[Step 7] ⏭️ _post.md 없음 — 후처리 스킵"
   - 있으면 → 파일 읽기

2. 액션 블록 파싱
   - ## 헤더로 액션 분리
   - 각 액션의 key-value 속성 추출
   - 변수 치환 ({ticket} → 실제 값)

3. 조건 평가
   - 각 액션의 condition 평가
   - 조건 불충족 → 해당 액션 스킵 + 로그

4. 순차 실행
   - 정의된 순서대로 액션 실행
   - 각 액션 결과를 사용자에게 실시간 표시

5. 사용자 확인
   - 각 액션 실행 전 사용자 확인 요청 (선택적)
   - 실패 시 다음 액션은 계속 진행 (독립적)

6. 결과 요약 출력
   ━━━ Post-Processing 결과 ━━━
   [✅] confluence-upload: 페이지 생성 완료 (URL)
   [✅] jira-comment: 코멘트 추가 완료
   [⏭️] custom: 조건 불충족으로 스킵
```

## 사용자 확인 정책

| 액션 유형 | 확인 필요 여부 | 이유 |
|----------|--------------|------|
| confluence-upload | **Y** (최초 실행 시) | 외부 시스템 변경, 되돌리기 어려움 |
| jira-comment | **Y** (최초 실행 시) | 외부 시스템 변경 |
| custom | N | 메시지 출력만 |

> 사용자가 한 번 승인하면 동일 세션 내에서는 재확인 불필요.
> 단, `_post.md` 파일이 변경된 경우 다시 확인 요청.

---

## Error Handling

| 오류 유형 | 처리 |
|----------|------|
| _post.md 파싱 실패 | 에러 출력 + 전체 Step 7 스킵 |
| Confluence Space 미발견 | 해당 액션 FAIL + 다음 액션 계속 |
| Jira 코멘트 실패 | 해당 액션 FAIL + 다음 액션 계속 |
| 변수 치환 실패 | 미치환 변수를 `{변수명}` 그대로 유지 + 경고 |

---

## Related Skills

| 스킬 | 관계 |
|------|------|
| **test-run** | Step 7에서 이 스킬을 호출 |
| **test-reporter** | Step 6 결과를 입력으로 받음 |
