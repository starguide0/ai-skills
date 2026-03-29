# Upgrade History

이 문서는 프로젝트의 주요 아키텍처 결정 사항, 버전 업데이트 내역, 및 업그레이드 가이드를 기록합니다.

---

## [3.0.1] - 2026-03-18

### Changed
- **Workspace Path Standardization**: 아키텍처 메타데이터 표준 경로를 대상 프로젝트 루트의 `.architecture/`로 재정렬했습니다. `refresh_architecture`와 `e2e_test`는 이 경로를 기준으로 동작합니다.
- **Provider Role Clarification**: `refresh_architecture`는 상위 consumer 스킬이 직접 의존해야 하는 대상이 아니라, service metadata를 생성하고 CLI 질의를 제공하는 provider implementation으로 재정의했습니다.

### Fixed
- **🔍 Precision Mapping**: 단어 경계(`\b`) 정규표현식을 도입하여 `user_id`와 같은 토큰이 다른 단어 내에서 오염되는 현상을 방지했습니다.
- **🛡️ Enhanced Verification**: `feature-index.json`과 실제 Flow 파일 간의 ID 일치 여부를 검증하는 로직을 강화하여 데이터 정합성을 확보했습니다.

## [3.0.0] - 2026-03-18

### Added
- **🧠 Behavioral Flow Extraction**: 진입점부터의 호출 체인 및 비즈니스 정책(분기)을 자동 요약하여 `flow-*.json`으로 추출하는 기능을 추가했습니다.
- **📖 Domain Glossary Loop**: 기술 용어를 비즈니스 용어로 매핑하고 사용자 피드백을 반영하는 `glossary` 관리 체계(`list`, `sync`)를 구축했습니다.
- **🔗 Horizontal Linkage Strategy**: 대규모 코드베이스에서의 기능 파편화를 방지하기 위해 `feature-index.json` 기반의 전역 색인 레이어를 도입했습니다.
- **📊 Mermaid Visualization**: 추출된 비즈니스 흐름을 시각화하기 위한 Mermaid 다이어그램 자동 생성 로직을 통합했습니다.
- **🛡️ Metadata Cross-Verification**: `verify` 명령어를 확장하여 Flow, Glossary, Skeleton 간의 참조 정합성 검증 로직을 추가했습니다.

---

## [2.3.3] - 2026-03-17

### Added
- **🌐 Universal Browser Intent**: 플랫폼 내장 도구(Subagent)와 Playwright CLI를 지능적으로 병합하여 고화질 레코딩 및 정교한 UI 조작 체계를 구축했습니다.
- **🖼️ Enhanced Visual Evidence**: 보고서 내 동영상(WebP) 및 스크린샷 자산 관리 규칙을 강화하여 배포 프로세스에 통합했습니다.

---

## [2.3.2] - 2026-03-17

### Added
- **Unified Architecture Path**: 당시 기준으로 `.architecture/` 폴더를 `.claude/architecture/`로 마이그레이션했습니다. 현재 표준은 다시 대상 프로젝트 루트의 `.architecture/`입니다.
- **Node.js-free Playwright Environment**: `playwright_utils`를 Python 기반으로 완전 전환하여 불필요한 의존성을 제거했습니다.
- **Enhanced Test Reporting**: 보고서 폴더 격리 및 자산 마이그레이션 로직을 통해 테스트 결과물의 영속성을 개선했습니다.

---

## [2.3.1] - 2026-03-16

### Changed
- **Multi-Platform Compatibility**: `SKILL.md`의 `allowed-tools`를 확장하여 Claude Code와 Gemini CLI 환경에서 도구 인식 오류를 해결했습니다.
- **Universal Tooling**: `Bash`, `Read`, `Write` 등 Claude 전용 도구 이름을 추가하여 플랫폼 간 호환성을 확보했습니다.

---

## [2.3.0] - 2026-03-16

### Added
- **Global Path Migration**: `e2e_test` 내의 모든 레거시 경로(`.claude/skills/`)를 최신 플러그인 규격(`skills/`)으로 일괄 마이그레이션했습니다.
- **Suite-wide Health Check**: 모든 스킬(`refresh_architecture`, `e2e_test`, `playwright_utils`)의 경로 정합성 및 도큐먼트 오류를 전수 점검하고 해결했습니다.

### Fixed
- **refresh-architecture 경로 오류**: `arch-manager.py` 및 관련 문서에서 legacy 파일명 참조 문제를 해결했습니다.

---

## [2.2.1] - 2026-03-15

### Fixed
- **Plugin Manifest 유효성 검사 오류 수정**: `plugin.json`에서 `commands` 및 `skills` 필드가 객체(`object`)가 아닌 문자열(`string`) 경로를 기대하는 규격을 준수하도록 수정했습니다.
- **불필요한 경로 제거**: 사용되지 않는 `commands/` 디렉토리에 대한 참조를 제거하였습니다.

---


### Changed
- **Skill-based Command Registration**: `/refresh-architecture` 명령의 노출 안정성을 위해 기존 `commands/` 폴더 기반에서 `skills/` 폴더 기반의 `SKILL.md` 구조로 마이그레이션했습니다.
- **플러그인 규격 강화**: `plugin.json`에 `skills` 디렉토리를 명시적으로 등록하여 Claude Code의 자동 감지 성능을 개선했습니다.

---


### Fixed
- **arch-manager.py 버그 수정**: `cmd_skeleton` 실행 시 발생하던 `NameError: name 'config' is not defined` 오류를 수정하고 전역 변수 초기화 로직을 보강했습니다.

### Changed
- **마켓플레이스 탐지 최적화**: Claude Marketplace의 `discover` 탭에서 탐지 효율을 높이기 위해 `marketplace.json` 및 `plugin.json`에 메타데이터(카테고리, 키워드)를 명시적으로 추가했습니다.

---

## [2.1.0] - 2026-03-13

### Changed
- **아키텍처 저장 구조 통합**: 기존의 `.metadata/` 폴더와 루트의 `configuration.json`을 단일 전용 폴더인 `.architecture/` 하위로 통합하였습니다.
    - 설정 파일: `./.architecture/configuration.json`
    - 메타데이터: `./.architecture/metadata/`
    - 상태 관리: `./.architecture/refresh-state.json`
- **Skill to Command 전환**: `refresh_architecture` 기술이 Claude Code의 슬래시 커맨드인 `/refresh`로 공식 전환되었습니다. 이제 AI의 판단에 맡기지 않고 명시적으로 호출하여 실행합니다.

### Fixed
- **경로 참조 버그**: `arch-manager.py query` 명령이 스킬 내부 폴더(`docs/`)를 바라보던 하드코딩 문제를 해결하였습니다. 이제 현재 프로젝트의 `.architecture/metadata/`를 정확히 참조합니다.

### Added
- **통합 슬래시 커맨드**: `/refresh` 커맨드가 추가되었습니다. (Phases 0-7 통합 프로세스 가이드 포함)

---

## [2.0.0] - 2026-03-10

### Added
- **Unified Skill Suite**: `e2e_test`, `refresh_architecture`, `playwright_utils`를 하나의 플러그인(`roy-skills`)으로 통합 관리하기 시작했습니다.
- **Single Versioning**: 개별 스킬 버전 대신 전체 플러그인의 단일 버전 정책을 도입했습니다.

---
*Created by Antigravity AI Architect*
