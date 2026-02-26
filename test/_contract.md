---
scope: skill-meta
not-skill-code: true
version: 1.0
---

# Test Skill 메타 계약

> ⚠️ **이 파일은 test 스킬의 메타 계약 파일이다.**
> test 스킬 실행 시 로드되지 않는다.
> test 스킬을 **수정하거나 분석할 때** 이 파일을 참조한다.

---

## 파일 분류 (File Scope)

test 스킬을 수정할 때 아래 분류를 기준으로 수정 대상 파일을 판단한다.

| 분류 | 파일/경로 | 수정 가능 | 설명 |
|------|-----------|----------|------|
| **스킬 진입점** | `SKILL.md` | ✅ | 스킬 정의 및 워크플로우 |
| **프롬프트 코드** | `test-run.md`, `test-gate.md`, `test-plan.md`, `test-data.md`, `test-scheduler.md`, `test-provisioning.md`, `test-reporter.md`, `test-evidence.md`, `test-init.md`, `test-workspace-conventions.md` | ✅ | LLM이 실행하는 프롬프트 |
| **Python 도구** | `tools/*.py` | ✅ | Hook 및 CLI 도구 (HYBRID 컴포넌트) |
| **런타임 규칙** | `rules/`, `templates/` | ✅ | 실행 시 로드되는 규칙/설정/템플릿 |
| **문서** | `doc/*.md` | ⛔ 읽기 전용 | 아키텍처 설명서. 코드 변경 후 별도 동기화 |
| **메타 파일** | `_contract.md`, `_analyze.md` | ⛔ 읽기 전용 | 스킬 코드 아님. 각각 수정 계약/분석 도구 담당자 관리 |

### 수정 요청 판단 원칙

- **테스트 스킬 기능 변경** → 프롬프트 코드 + Python 도구만 수정
- **`_analyze.md` 수정 요청** → analyze-skill 스킬 담당자 작업. 테스트 스킬 수정과 혼용 금지
- **`_contract.md` 수정 요청** → 파일 분류나 HYBRID 계약 자체가 바뀔 때만

---

## HYBRID 구조

test 스킬은 **Python 도구(tools/)** 와 **프롬프트(*.md)** 가 결합된 HYBRID 구조다.
한쪽을 수정하면 반드시 다른 쪽 영향 범위를 확인해야 한다.

```
프롬프트 (*.md)
  ↓ Bash 도구 호출
Python 도구 (tools/*.py)
  ↓ JSON 파일 출력
프롬프트 (*.md) 가 결과를 읽어 다음 단계 판단
```

---

## 핵심 데이터 흐름 (Python↔Prompt 계약)

| 생산자 | 출력 key | 소비자 | 기대 key | 상태 |
|--------|---------|--------|---------|------|
| `stimulus_executor.py` | `"response"` | `summarize_partial_results.py` | `"api_response"` (우선) / `"response"` (fallback) | ⚠️ `checks[tc_id]` 저장 시 fallback 없음 |
| `validate_test_sheet.py` | TC ID `[A-Za-z0-9.\-]+` | `summarize_partial_results.py` | natural sort | ✅ 일치 |
| `behavioral_gate.py` | `results[].gate` | `test-scheduler.md` Step 0.5 | `result.gate` | ⚠️ `is_tc_result_file()` 정규식 점(.) 미지원 (버그 H-1) |
| `summarize_partial_results.py` | `{pass, fail, nt, blocked, incomplete}` | `generate_mermaid_diagrams.py` | 동일 key | ✅ 일치 |
| `generate_mermaid_diagrams.py` | `_mermaid_drafts.json` | `generate_mermaid_urls.py` | `output_path.parent/partial_results/` | ⚠️ 암묵적 경로 가정 |

---

## 상태값 관리 규칙

`test-data.md`에서 status 값을 추가/삭제할 때 반드시 함께 수정할 위치:

| 수정 위치 | 이유 |
|-----------|------|
| `tools/validate_data_mapping.py` — `status_sum` 합산 | summary 검증 공식에 포함해야 함 |
| `tools/validate_data_mapping.py` — entry 레벨 검증 분기 | 상태별 필수 필드 검증 |
| `test-scheduler.md` Step 0.5 필터 조건 | 실행 대상 status 목록 |
| `doc/HOOKS.md` 예시 JSON | 문서 동기화 (읽기 전용이므로 마지막에 별도 업데이트) |

---

## 수정 시 체크리스트

### Python 도구 수정 시

- [ ] 출력 JSON의 key 이름 변경 → 해당 key를 읽는 프롬프트/Python 파일 전체 확인 (위 데이터 흐름 표 참조)
- [ ] 정규식 패턴 변경 → `validate_test_sheet.py`, `validate_test_result.py`, `behavioral_gate.py` 세 파일 패턴 일치 여부 확인
- [ ] Hook exit code 변경 → `doc/HOOKS.md` 규칙과 일치하는지 확인 (deny = exit(0), 에러 = exit(1))

### 프롬프트 수정 시

- [ ] 새 status 값 추가 → 위 "상태값 관리 규칙" 표의 4개 위치 동시 수정
- [ ] ctx 필드 추가 → 해당 스킬 파일의 ctx 복원 섹션에 복원 경로 추가
- [ ] Interface Contract (INPUT/OUTPUT 표) 변경 → 해당 필드를 소비하는 스킬의 INPUT 표도 확인
