# Test rules/ 폴더 가이드

> 테스트 스킬 실행 시 참조하는 **범용** 가이드라인 (프로젝트 무관)
>
> ⚠️ 프로젝트별 DB 오류 패턴, 주의사항은 `test/_shared/rule/`에 있음 (여기가 아님)

## 폴더 구조

```
$CLAUDE_PLUGIN_ROOT/skills/e2e_test/rules/
├── README.md                          # 이 파일
├── _guidelines_test_evidence.md      # Pass/Fail 근거 작성 가이드라인 (Step 5 로드)
├── _report_format_rules.md           # 보고서 출력 포맷 규칙 (Step 6 로드)
├── _test_permissions.json            # 권한 범주 정의 (범용 구조, 프로젝트 config 참조)
├── _test_sheet_rules.json            # 테스트시트 구조 검증 JSON 스키마 (validate_test_sheet.py)
├── _wiki_output_rules.json           # 리포트 출력 구조 검증 JSON 스키마 (validate_report_structure.py)
├── _data_mapping_rules.json          # 데이터매핑 구조 검증 JSON 스키마 (validate_data_mapping.py)
└── _caution_common_errors.md         # 반복 발생 오류 패턴 (범용 — 프로젝트 무관)
```

---

## 파일 목록 및 용도

| 파일 | 용도 | 로드 시점 |
|------|------|-----------|
| `_guidelines_test_evidence.md` | Pass/Fail 근거 작성 규칙, Level 1-4, 템플릿 | **Step 5 (Execute)** — 모든 TC 결과 작성 시 필수 |
| `_report_format_rules.md` | 보고서 리포트 출력 포맷 규칙 | **Step 6 (Report)** — 리포트 생성 시 필수 |
| `_test_permissions.json` | 권한 범주 정의 (범용 구조, Step 0.3 Permission 검증 시 참조) | Step 0 |
| `_test_sheet_rules.json` | 테스트시트 구조 검증 JSON 스키마 | Hook (validate_test_sheet.py) |
| `_wiki_output_rules.json` | 리포트 출력 구조 검증 JSON 스키마 | Hook (validate_report_structure.py) |
| `_data_mapping_rules.json` | 데이터매핑 구조 검증 JSON 스키마 | Hook (validate_data_mapping.py) |
| `_caution_common_errors.md` | 반복 발생 오류 패턴 (범용 — 프로젝트 무관) | Step 4 (Data) |

---

## 메타데이터 우선순위

```
1순위: ctx.service_metadata provider가 제공하는 공식 DB schema 메타데이터
2순위: test/_shared/rule/_caution_missing_tables.json  (Architecture에 누락된 테이블 임시 캐시)
3순위: 실시간 스키마 조회                         (information_schema 쿼리)
```

---

**중요**: `rules/`는 범용 가이드라인만 포함합니다. 프로젝트별 DB 오류 패턴(`_caution_*.md/.json`)은 `test/_shared/rule/`에 위치합니다.
