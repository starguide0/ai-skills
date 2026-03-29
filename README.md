# Skills Repository

이 저장소는 `superpowers` 패턴의 AI 에이전트 전용 기술(Skills) 모음입니다.
LLM 기반의 개발 도구(Claude Code, Cursor)에서 **플러그인 형태**로 직접 연동(Marketplace Plugin)하여 사용할 수 있습니다.

## 🚀 설치 및 사용 방법 (Installation)

이 저장소의 스킬은 Claude Code 외에도 다양한 에이전트 환경(Cursor, Codex, OpenCode 등)에서 활용할 수 있습니다.
사용하시는 환경에 맞춰 아래 가이드 중 하나를 선택해 주세요.

### 1. Claude Code (via Plugin Marketplace)
Claude Code에서는 먼저 마켓플레이스를 추가한 후, 개별 플러그인을 설치합니다:

```bash
# 1) 마켓플레이스 등록 (원격 저장소 또는 로컬 경로 ./ 지정)
/plugin marketplace add https://github.com/starguide0/ai-skills

# 2) 통합 스킬 플러그인 설치 (e2e_test, refresh_architecture 동시 설치)
/plugin install roy-skills@roy-skills-marketplace
```



#### ✅ 플러그인 관리 명령어
설치가 완료되면 다음 명령어로 관리할 수 있습니다:
```bash
# 로드된 스킬 목록 조회
/plugin list

# 플러그인 업데이트 (저장소 구조 통합됨에 따라 roy-skills 로 일괄 업데이트)
/plugin update 플러그인이름
# 예: /plugin update roy-skills
```

### 2. Cursor
Cursor Agent Chat에서 다음 명령어를 입력해 설치합니다:
```bash
/plugin-add starguide0/ai-skills
```

### 3. Codex
Codex에게 다음 명령을 내려 설치 문서를 읽고 자동으로 구성하게 합니다:
```bash
Fetch and follow instructions from https://raw.githubusercontent.com/starguide0/ai-skills/refs/heads/main/.codex/INSTALL.md
```

### 4. OpenCode
OpenCode에게 다음 명령을 내려 설치 문서를 읽고 자동으로 구성하게 합니다:
```bash
Fetch and follow instructions from https://raw.githubusercontent.com/starguide0/ai-skills/refs/heads/main/.opencode/INSTALL.md
```

### 5. Antigravity (Gemini Advanced Agentic Coding)
Antigravity에게 다음 명령을 내려 설치 문서를 읽고 자동으로 구성하게 합니다:

```bash
Fetch and follow instructions from https://raw.githubusercontent.com/starguide0/ai-skills/refs/heads/main/.antigravity/INSTALL.md
```

또는 로컬에서 바로 다음을 실행하게 하십시오:
```bash
Please analyze and execute installation instructions from .antigravity/INSTALL.md
```

> **[잠재적 위험(Risk) 및 주의점]**
> - 글로벌 설치와 워크스페이스 격리 설치 중 선택할 수 있습니다.
> - 시스템의 컨텍스트 폴루션(Context Pollution)을 피해야 하는 상황이라면 **반드시 에이전트에게 옵션 B(격리 설치)를 요청**하십시오.


---

## 확장 방법

1. `skills/` 디렉토리 아래에 새로운 기능의 폴더를 생성합니다.
2. 폴더 내부에 `SKILL.md` 파일을 작성하고 상단에 YAML 프론트매터(`name`, `description`, `version`)를 추가합니다.

## 📦 버전 관리 및 배포 자동화 (CI/CD)

각 플러그인의 버전 분리 및 관리를 위해 GitHub Actions 기반의 자동 배포 시스템이 구축되어 있습니다. 
새로운 버전을 릴리스하려면, 터미널에서 다음 규칙에 따라 Git Tag를 생성 후 푸시하세요:

```bash
# 형식: v<major.minor.patch>
$ git tag v2.3.3
$ git push origin v2.3.3
```

Action 봇이 감지하여 아래 3개 문서의 버전 속성을 자동으로 최신화하고 커밋해줍니다.
- `{plugin_name}/SKILL.md`
- `{plugin_name}/.claude-plugin/plugin.json` (및 `.cursor-plugin/`)
- 루트 `.claude-plugin/marketplace.json`

## 포함된 스킬

- **e2e_test**: 자동화된 테스트 계획 및 실행 (워크플로우 포함)
- **refresh_architecture**: 프로젝트 아키텍처 메타데이터 자동 갱신 및 탐색
- **playwright_utils**: 고속 브라우저 자동화 및 Playwright 관리
