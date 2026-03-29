# browser

이 스킬은 Playwright CLI를 활용한 성능 중심의 브라우저 조작과, 플랫폼 내장 도구를 활용한 고충실도(High-fidelity) 인터랙션을 통합적으로 가이드합니다.

## 🎭 실행 모드 (Execution Modes)

에이전트는 상황에 따라 아래 두 가지 모드 중 최적의 방법을 선택해야 합니다.

### 1. High-fidelity Interaction (Native-First)
- **의도**: 정교한 UI 조작, 동적 요소 대기, 작업 과정의 시각적 기록(Recording)이 필요한 경우.
- **도구 선택**: 현재 사용 중인 플랫폼(Antigravity, Claude Code 등)이 제공하는 **내장 브라우저 도구**(예: `browser_subagent`, `navigation_tool` 등)를 우선적으로 사용하십시오.
- **장점**: 고해상도 WebP 레코딩 및 세밀한 DOM 상태 분석 가능.

### 2. High-performance Execution (Playwright Fallback)
- **의도**: 단순 스크린샷 캡처, 대규모 반복 테스트, 미리 정의된 자동화 스크립트 실행.
- **도구 선택**: 제공되는 `playwright` CLI를 직접 호출합니다.
- **장점**: MCP나 서브에이전트 오버헤드가 없어 실행 속도가 매우 빠름.

## 주요 기능

### 1. 웹페이지 캡처 (Screenshot)
- **명령어**: `playwright screenshot <url> {ctx.ticket_folder}/screenshots/<filename>.png`
- **저장 위치**: 각 티켓별 폴더 내의 `screenshots/` 디렉토리에 저장됩니다.
- **보고서 영속성 (Report Persistence)**: 
    - 캡처된 이미지(PNG) 또는 레코딩(WebP)은 보고서 폴더의 `assets/`로 마이그레이션되어야 합니다.
    - 내장 도구가 생성한 영상 파일은 `{ticket}_assets/video_*.webp` 형식으로 저장하여 보고서에서 임베딩될 수 있도록 합니다.
- **후처리**: 위와 같이 보고서에 영구적으로 반영된 것이 확인된 임시 파일(저장소의 `screenshots/` 폴더 내 원본)만 `test-run` Step 8(Cleanup)에서 삭제됩니다.
- **설명**: 특정 URL에 접속하여 전체 화면 또는 특정 영역을 캡처합니다.

### 2. PDF 생성
- **명령어**: `playwright pdf <url> <output_path>`
- **설명**: 웹페이지를 PDF로 저장합니다.

### 3. 간단한 스크립트 실행
- **명령어**: `playwright test <script_path>`
- **설명**: 복잡한 인터랙션이 필요한 경우 미리 작성된 Playwright 스크립트를 실행합니다.

## 활용 팁
- `agent-browser`를 통해 파악된 셀렉터를 바탕으로 Playwright CLI를 직접 호출하여 클릭, 입력 등의 동작을 수행할 수 있습니다.
