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
cd ~/project/skills/test

# 3. HTTP 요청을 위한 필수 라이브러리(requests) 설치
pip3 install requests
# (필요에 따라 가상 환경(venv) 구성 후 활용할 수도 있습니다)
```

### 2. 스킬 연동 (Plugin 방식)

의존성 설치가 끝난 후, 사용하는 클라이언트 툴에 맞춰 연동합니다.

#### 방법 A: Superpowers 기반 설치 (가장 권장)

[obra/superpowers](https://github.com/obra/superpowers) 프레임워크가 적용된 환경(Claude Code, Cursor 등)을 사용 중이라면, 로컬 워크스페이스의 스킬 디렉토리에 이 저장소를 직접 클론하여 연동할 수 있습니다.

1. 터미널을 열고 워크스페이스(프로젝트 루트)에서 다음 명령어를 실행하여 스킬을 다운로드합니다.
   ```bash
   # Claude Code / Cursor 등 Superpowers가 바라보는 스킬 폴더 생성 및 클론
   mkdir -p .claude/skills
   git clone https://github.com/starguide0/ai-skills.git .claude/skills/test
   ```
2. 설치 후, 해당 폴더로 이동하여 내장 Python 스크립트 실행에 필요한 필수 라이브러리가 설치되었는지 점검합니다.
   ```bash
   cd .claude/skills/test
   pip3 install requests
   ```
3. (선택사항) 만약 당신의 환경이 아직 `superpowers` 런타임 자체를 가지고 있지 않다면, [공식 가이드](https://github.com/obra/superpowers)를 참고하여 Claude Code의 경우 `/plugin install`, Cursor의 경우 `/plugin-add` 명령어로 먼저 상위 프레임워크를 연동해 주십시오.

#### 방법 B: Claude MCP(Model Context Protocol) 수동 연동

#### 방법 B: Workspace 직접 배치 (Legacy)

Claude가 프로젝트 디렉토리를 로드할 때 직접 컨텍스트로 읽어들이도록 워크스페이스 내부에 폴더를 연결합니다.

```bash
ln -s ~/project/skills/test ~/workspace/.claude/skills/test
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

> "테스트 결과 보고서를 만들어줘."

- 시스템은 `test-report.md` 규칙을 참조하여 `result.md` 형식의 최종 테스트 요약 보고서를 생성합니다.

---

## ⚠️ 주의 사항 (Rules & Common Errors)

이 스킬을 수정하거나 개선할 때는 `rules/_caution_common_errors.md` 파일을 반드시 숙지해야 합니다.

- **보안**: 비밀번호나 인증 토큰 등 민감 정보가 포함된 `auth_body` 데이터를 절대 파일(예: `partial_results/`)에 하드코딩하여 저장하면 안 됩니다.
- **명령어 검증 (Zero-Trust)**: 스킬 내에서 파이썬이나 쉘 스크립트를 실행할 때는 반드시 그 결과를 확인(Exit code 및 STDOUT 확인)해야 하며, LLM이 결과를 임의로 예측(환각/Hallucination)하여 응답해서는 안 됩니다.
- **Python 의존성**: 복잡한 논리 판단은 LLM 프롬프트가 아닌 가급적 `tools/` 내부의 Python 스크립트에 수학적/절차적 로직으로 위임해야 안전합니다.
