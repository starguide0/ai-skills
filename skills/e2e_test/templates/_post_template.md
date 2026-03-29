# Test Post-Processing Actions

이 문서에서 테스트 완료 후 수행할 후처리 액션(보고서 발행, 이슈 코멘트 등)을 정의합니다.
`## action-type` 헤더 아래에 설정을 작성하며, `{변수}`는 런타임에 실제 값으로 치환됩니다.

---

## publish-report

- condition: {result} == PASS
- provider: report
- space: QA
- parent: 테스트 결과 모음
- title: [{ticket}] {summary} 테스트결과 {version}
- mode: create_or_update

---

## update-issue-comment

- condition: always
- provider: issue
- content: |
  테스트 완료: {result} ({pass_count}/{total_count})
  시트 버전: {sheet_version}
  결과 버전: {version}
  보고서: {report_file}

---

## custom

- name: 완료 알림
- message: "{ticket} 테스트 후처리가 완료되었습니다."
