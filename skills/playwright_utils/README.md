# playwright_utils

Playwright CLI를 통합 관리하고, MCP 의존성 없이 고속 브라우저 자동화를 지원하는 유틸리티 스택입니다.

## 주요 기능
- **자동 설치**: `npx playwright --version` 체크 및 부족 시 자동 설치 (`npm install` + `playwright install --with-deps`)
- **CLI-First 실행**: 가벼운 CLI 명령어를 통해 브라우저를 제어하고 분석합니다.
- **환경 독립성**: 프로젝트 로컬 환경에 최적화된 브라우저 구동을 보장합니다.

## 사용법
- `setup.md`: Playwright 환경 준비 (설치 및 업데이트)
- `browser.md`: 공통 브라우저 조작 (Screenshot, Navigation 등)
