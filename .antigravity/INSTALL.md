# Installing Skills for Antigravity

Antigravity (Gemini Advanced Agentic Coding) 환경에 `ai-skills`를 설치하여 에이전트의 역량을 확장합니다.

## 🤖 에이전트 지시사항 (Agent Instructions)

이 문서를 읽고 있는 Antigravity 에이전트는 다음 단계를 수행하여 설치를 완료하십시오.

### 1. 사용자의 설치 의도 확인
사용자에게 다음 두 가지 옵션 중 하나를 선택하도록 요청하십시오. (별도의 요구가 없으면 **옵션 B**를 권장하십시오.)

*   **[옵션 A: 글로벌 설치]**: 모든 프로젝트에서 스킬 사용 가능 (주의: 토큰 사용량 증가 및 컨텍스트 오염 위험)
*   **[옵션 B: 워크스페이스 격리]**: 현재 프로젝트에서만 스킬 사용 (권장: 안전하고 효율적인 토큰 관리)

### 2. 설치 실행 (Execution)
사용자의 선택에 따라 다음 명령어를 순차적으로 실행하십시오.

#### [Option A: Global Installation]
```bash
# Antigravity 글로벌 플러그인 디렉토리 생성 및 심볼릭 링크 연결
mkdir -p ~/.gemini/antigravity/plugins
ln -s "$(pwd)" ~/.gemini/antigravity/plugins/ai-skills
```

#### [Option B: Workspace Isolation]
```bash
# 현재 작업 디렉토리에 에이전트 스킬 매핑
mkdir -p .agents
ln -s "$(pwd)/skills" .agents/skills
```

### 3. 완료 보고
설치가 완료되면 연동된 경로를 사용자에게 보고하고, 에이전트가 새로운 스킬을 즉시 활용할 수 있는 상태임을 알리십시오.
