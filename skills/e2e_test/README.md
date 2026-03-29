# Claude Test Skill

이 저장소는 Claude 환경에서 동작하는 **API 테스트 및 자동화 오케스트레이션 스킬(Test Skill)**을 제공합니다.
사용자가 테스트 계획을 수립하고, 데이터를 준비하며, 테스트를 실행하고, 최종 결과 리포트를 생성하는 전체 라이프사이클을 관리합니다.

## 핵심 아키텍처 (Hybrid Approach)

이 스킬은 **프롬프트(LLM의 추론/계획 능력)**와 **Python 스크립트(결정론적 실행 및 연산)**가 결합된 하이브리드 구조를 사용합니다.

- **프롬프트 (`*.md`)**: 테스트 시나리오 설계, 컨텍스트 이해, 오케스트레이션, 예외 상황 판단, 리포팅
- **Python 스크립트 (`tools/*.py`)**: HTTP API 실제 호출, 데이터 파싱, 응답 값의 수학적/논리적 검증(Verdict Calculator), 디스크 I/O

---

## 🚀 설치 (Installation & Configuration)

이 스킬은 내부적으로 Python 3 스크립트를 사용하여 HTTP 요청 및 결과 검증 로직을 시뮬레이션합니다.
원활한 동작을 위해 **먼저 Python 환경을 설정한 뒤**, Claude 앱(또는 워크스페이스)에 플러그인을 마운트해야 합니다.

### 1. Python 의존성 설치 (필수작업)

시스템에 Python 3.8 이상이 설치되어 있어야 합니다.

```bash
# 1. 저장소 클론
git clone https://github.com/starguide0/ai-skills.git ~/project/skills

# 2. test 스킬 디렉토리로 이동
cd ~/project/skills/e2e_test

# 3. HTTP 요청 및 결과 검증을 위한 필수 라이브러리 설치
pip3 install requests jsonschema
# (필요에 따라 가상 환경(venv) 구성 후 활용할 수도 있습니다)
```

### 2. 스킬 연동

Python 의존성 설치가 끝난 후, 원하시는 구동 환경에 맞춰 연동을 진행합니다.

#### 환경 1: Claude Code
Claude Code에서는 마켓플레이스를 등록하여 설치하거나 수동으로 클론할 수 있습니다:
**옵션 A: 플러그인 명령어를 통한 마켓플레이스 사용**
```bash
# 1) 마켓플레이스 환경 추가
/plugin marketplace add https://github.com/starguide0/ai-skills

# 2) 플러그인 설치 (단일 구조로 통합된 roy-skills 팩키지로 설치)
/plugin install roy-skills@roy-skills-marketplace
# 업데이트 시: /plugin update roy-skills
```
**옵션 B: 기반 폴더 수동 클론 (Legacy 방식)**
```bash
mkdir -p .claude/skills
git clone https://github.com/starguide0/ai-skills.git .claude/skills/e2e_test
```
*(선택사항) 만약 당신의 환경이 아직 `superpowers` 런타임 자체를 가지고 있지 않다면, 공식 가이드를 따라 마켓플레이스를 먼저 추가(`/plugin marketplace add obra/superpowers-marketplace`)한 뒤 연동(`/plugin install superpowers@superpowers-marketplace`)해 주십시오.*

#### 환경 2: Cursor
프롬프트나 Cursor Agent Chat을 통해 설치를 진행합니다:
```bash
/plugin-add starguide0/ai-skills
```

#### 환경 3: Codex
LLM 본체에 아래 명령을 지시하여 설치 가이드를 읽고 자동으로 구성하게 합니다:
```bash
Fetch and follow instructions from https://raw.githubusercontent.com/starguide0/ai-skills/refs/heads/main/.codex/INSTALL.md
```

#### 환경 4: OpenCode
LLM 본체에 아래 명령을 지시하여 설치 가이드를 읽고 자동으로 구성하게 합니다:
```bash
Fetch and follow instructions from https://raw.githubusercontent.com/starguide0/ai-skills/refs/heads/main/.opencode/INSTALL.md
```

#### 환경 5: Workspace 직접 배치 (로컬 개발용 Legacy)
Claude가 프로젝트 디렉토리를 로드할 때 스킬을 직접 컨텍스트로 읽어들이도록 심볼릭 링크를 연결합니다.
```bash
ln -s ~/project/skills/e2e_test ~/workspace/.claude/skills/e2e_test
```

---

## 🛠 사용 방법 (Usage)

이 스킬은 사용자가 자연어로 테스트 관련 지시를 내리면 자동으로 작동합니다. 내부적으로 `test-run.md`라는 오케스트레이터가 파이프라인을 관장합니다.

### 1. 테스트 계획 수립

> "회원가입 API와 로그인 API에 대한 테스트 시나리오를 작성해줘."

- 시스템은 `test-plan.md` 규칙을 참조하여 테스트 케이스 명세서(TCD)를 작성합니다.

### 2. 테스트 환경 및 데이터 준비

> "테스트 실행을 위한 환경 변수와 더미 데이터를 준비해라."

- 시스템은 `test-provisioning.md` 규칙을 참조하여 사전 조건(Pre-condition), API 인증 토큰 추출 로직 등을 설정합니다.

### 3. 테스트 실행 (Execution)

> "작성된 테스트 케이스를 실행해줘."

- 시스템은 `stimulus_executor.py`를 통해 실제 타겟 서버로 HTTP API 요청을 전송합니다.
- 요청 결과는 `partial_results/` 디렉토리에 저장됩니다.

### 4. 결과 검증 (Verification)

> "테스트 실행 결과를 검증해줘."

- 시스템은 `verdict_calculator.py`를 호출하여 실제 응답값(Actual)과 예상값(Expected)을 결정론적(Deterministic)으로 비교 분석하여 PASS/FAIL을 판정합니다. (LLM의 환각을 방지하고 코드 레벨에서 정밀 검증 수행)

### 5. 결과 리포팅
116: 
117: > "테스트 결과 보고서를 만들어줘."
118: 
119: - 시스템은 `test-report.md` 규칙을 참조하여 `result.md` 형식의 최종 테스트 요약 보고서를 생성합니다.
120: 
121: ---
122: 
123: ## 📦 Repository & 서비스 관리
124: 
125: 이 스킬은 테스트 대상 서비스의 소스 코드를 탐색하고 관리하기 위해 **Repository Registry** 시스템을 사용합니다.
126: 
127: ### 1. Repository Registry (`repo-registry.json`)
128: 
129: `test/_shared/repo-registry.json` 파일은 프로젝트에서 사용하는 모든 서비스의 Git URL과 상태 정보를 관리합니다.
130: - `test-init` 실행 시 자동으로 스캐폴딩됩니다.
131: - 로컬에 없는 서비스도 Git URL만 등록되어 있으면 원격 조회를 통해 분석할 수 있습니다.
132: 
133: ### 2. 원격 서비스 탐색 (Remote Reconnaissance)
134: 
135: `test-gate` 단계에서 시스템은 다음과 같이 서비스를 탐색합니다:
136: 1. **Local Scan**: 작업 폴더 내의 하위 디렉토리를 스캔하여 `.git` 정보를 확인합니다.
137: 2. **Remote Scan**: 로컬에서 찾지 못한 서비스는 `repo-registry.json`의 원격 URL을 통해 브랜치 존재 여부 및 변경 이력을 확인합니다.
138: 
139: ### 3. 유효성 검증 및 제어 (Skip/Abort)
140: 
141: 서비스 접근에 문제가 발생할 경우(예: 권한 오류, 잘못된 URL), 시스템은 무조건 중단하지 않고 사용자에게 선택권을 제공합니다:
142: - **[Skip]**: 해당 서비스를 테스트 대상에서 제외하고 나머지 프로세스 진행
143: - **[Abort]**: 전체 파이프라인 즉시 중단
144: 
145: ---
146: 
147: ## 📁 티켓 관리 및 폴더 규칙
148: 
149: 이 스킬은 **'1 Ticket = 1 Folder'** 원칙을 고수합니다.
150: 
151: - **정밀한 티켓 추출**: 정규표현식 `([A-Z]+-\d+)(?!\d)`을 사용하여 티켓 ID를 정확하게 추출합니다 (예: `ABC-1234A`에서 `ABC-1234`만 추출).
152: - **폴더 재사용**: 동일한 티켓 ID로 작업할 경우, 폴더명 내의 기능 설명이 다르더라도 기존 티켓 폴더를 찾아 재사용함으로써 데이터 산재를 방지합니다.
153: 
154: ---
155: 
156: ## ⚠️ 주의 사항 (Rules & Common Errors)

이 스킬을 수정하거나 개선할 때는 `rules/_caution_common_errors.md` 파일을 반드시 숙지해야 합니다.

- **보안**: 비밀번호나 인증 토큰 등 민감 정보가 포함된 `auth_body` 데이터를 절대 파일(예: `partial_results/`)에 하드코딩하여 저장하면 안 됩니다.
- **명령어 검증 (Zero-Trust)**: 스킬 내에서 파이썬이나 쉘 스크립트를 실행할 때는 반드시 그 결과를 확인(Exit code 및 STDOUT 확인)해야 하며, LLM이 결과를 임의로 예측(환각/Hallucination)하여 응답해서는 안 됩니다.
- **Python 의존성**: 복잡한 논리 판단은 LLM 프롬프트가 아닌 가급적 `tools/` 내부의 Python 스크립트에 수학적/절차적 로직으로 위임해야 안전합니다.
