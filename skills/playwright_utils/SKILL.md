---
name: playwright_utils
description: Playwright CLI management and high-speed browser automation utility.
allowed-tools:
  - run_command, Bash
  - list_dir, Glob
  - view_file, Read
  - write_to_file, Write
  - Edit
  - Grep
---

# Playwright Utils Skill

이 스킬은 Playwright CLI를 관리하고 MCP 오버헤드 없이 고속 브라우저 자동화 기능을 제공합니다.

## 주요 기능

1. **자동화된 환경 구축 (`setup.md`)**
   - Playwright CLI 설치 여부 확인 및 자동 설치 (`pip3 install playwright` + `playwright install`)
2. **고속 브라우저 제어 (`browser.md`)**
   - 스크린샷 캡처, 페이지 탐색, PDF 생성 등 CLI 기반 브라우저 조작

## 사용 규칙

- 모든 브라우저 자동화 실행 전 `setup`을 호출하여 환경을 보장하십시오.
- `agent-browser`와 연동하여 분석된 셀렉터를 Playwright CLI 명령어로 실행하십시오.
