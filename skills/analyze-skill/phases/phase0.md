<!-- Phase 0: 타입 감지 + 모드 결정 -->
<!-- 입력: Python scripts/phase0_setup.py 실행 결과 (phase0_result.json) -->
<!-- 출력: 캐시hit이면 재분석 여부 사용자 확인 후 진행, 아니면 Phase 1 실행 -->

## Phase 0: 대상 스킬 파악 + 해시 계산 + 임시 디렉토리 생성

```
1. 스킬 디렉토리 탐색:
   Glob "{스킬경로}/**"
   → 파일 목록 수집

2. 타입 감지:
   스킬 디렉토리 내 파일 목록에서 아래 메타 파일을 제외한다:
     - README.md, readme.md

   IF .py 파일 존재 → HYBRID  (code_analyst_needed = true)
   ELIF 스킬 디렉토리 내 .md 파일 (메타 파일 제외) 2개 이상 → PROMPT  (code_analyst_needed = false)
   ELSE → SINGLE  (code_analyst_needed = false)

   → echo "타입: {TYPE}, CodeAnalyst 필요: {code_analyst_needed}"

3. config.yml 로드 또는 초기화 (Bash):

   `SKILL_SELF_DIR`은 analyze-skill 스킬 자신이 위치한 디렉토리다.
   (스킬 실행 컨텍스트의 "Base directory for this skill" 값)
   이 디렉토리가 곧 `SKILL_ANALYSIS_DIR`(분석 결과 저장 루트)이다.

   ```bash
   # analyze-skill 스킬 자신의 디렉토리 (LLM이 컨텍스트에서 파악)
   SKILL_SELF_DIR="{Base directory for this skill}"  # 예: ~/.claude/skills/analyze-skill
   CONFIG_FILE="$SKILL_SELF_DIR/config.yml"

   if [ -f "$CONFIG_FILE" ]; then
     # 기존 config 로드
     PLATFORM=$(grep "^platform:" "$CONFIG_FILE" | awk '{print $2}')
     SKILL_ANALYSIS_DIR="$SKILL_SELF_DIR"
     echo "config 로드: $CONFIG_FILE (platform=$PLATFORM)"
   else
     # 첫 실행 — 플랫폼 감지 후 config.yml 생성
     if   [ -n "$CLAUDECODE" ] || [ -d "$HOME/.claude" ]; then
       PLATFORM="claude-code"
     elif [ -n "$GEMINI_HOME" ] || [ -d "$HOME/.gemini" ]; then
       PLATFORM="gemini-cli"
     elif [ -n "$OPENAI_AGENT" ] || [ -d "$HOME/.codex" ]; then
       PLATFORM="codex"
     else
       PLATFORM="generic"
     fi

     SKILL_ANALYSIS_DIR="$SKILL_SELF_DIR"

     cat > "$CONFIG_FILE" <<EOF
platform: ${PLATFORM}
skill_self_dir: ${SKILL_SELF_DIR}
EOF
     echo "config 초기화 완료: $CONFIG_FILE (platform=$PLATFORM)"
   fi
   ```

4. analyze.md 확인:
   경로 형식: `{SKILL_ANALYSIS_DIR}/{스킬명}/analyze.md`
   스킬명별 서브디렉토리를 생성하므로 path hash가 필요 없다.

   ```bash
   SKILL_ABS_PATH=$(realpath "{스킬경로}")
   SKILL_NAME=$(basename "$SKILL_ABS_PATH")
   ANALYZE_MD_DIR="${SKILL_ANALYSIS_DIR}/${SKILL_NAME}"
   ANALYZE_MD_PATH="${ANALYZE_MD_DIR}/analyze.md"
   mkdir -p "$ANALYZE_MD_DIR"
   ```

   IF "$ANALYZE_MD_PATH" 존재 → CUSTOM 모드 (각 Phase에 병합)
   ELSE → AUTO 모드

   예시:
     SKILL_ABS_PATH: /Users/roy/project/skills/skills/test-run
     SKILL_NAME: test-run
     SKILL_SELF_DIR: ~/.claude/skills/analyze-skill
     ANALYZE_MD_PATH: ~/.claude/skills/analyze-skill/test-run/analyze.md

   ※ analyze.md frontmatter에 skill_path 필드를 기록하여 경로를 명시한다.

5. 소스 해시 계산 + 캐시 hit 판정 (Bash):

   ```bash
   # OS별 단일 해시값 생성 (macOS: md5, Linux: md5sum)
   if command -v md5sum >/dev/null 2>&1; then
     SKILL_HASH=$(find "{스킬경로}" -type f | sort | xargs md5sum | md5sum | cut -d' ' -f1)
   else
     SKILL_HASH=$(find "{스킬경로}" -type f | sort | xargs md5 | md5 | awk '{print $NF}')
   fi

   PREV_HASH=""
   if [ -f "$ANALYZE_MD_PATH" ]; then
     PREV_HASH=$(grep "^skill_hash:" "$ANALYZE_MD_PATH" | head -1 | awk '{print $2}')
   fi

   if [ "$SKILL_HASH" = "$PREV_HASH" ] && [ -n "$PREV_HASH" ]; then
     echo "캐시 hit — 스킬이 변경되지 않았습니다. (hash: $SKILL_HASH)"
     echo ""
     echo "이전 분석 결과가 있습니다. 어떻게 할까요?"
     echo "  [Y] 재분석 — 새 분석 실행 (Phase 1부터 진행)"
     echo "  [N] 기존 결과 표시 — 이전 분석 결과를 Phase 5 형식으로 렌더링 후 종료"
     # IF 사용자가 Y 선택 → cache_hit 무시, 캐시 miss와 동일하게 Phase 1부터 진행
     # IF 사용자가 N 선택 (또는 기본값) →
     #   analyze.md의 "알려진 취약 지점" 섹션을 읽어 아래 형식으로 직접 렌더링 후 종료
     #   (tmpdir 없으므로 phase5_output.md 형식 불가 — analyze.md에서 직접 읽는다):
     #
     #   ## {스킬명} 이전 분석 결과 (캐시 hit — {날짜})
     #   ### 알려진 취약 지점
     #   {analyze.md "알려진 취약 지점" 섹션 그대로 출력}
     #   → 이 결과는 마지막 분析(hash: $PREV_HASH) 시점 기준입니다.
   else
     echo "캐시 miss — 새 분석 시작. 현재 해시: $SKILL_HASH"
   fi
   ```

6. 임시 디렉토리 생성 (Bash):
   TS=$(date +%Y%m%d%H%M%S)
   SKILL_TMPDIR="/tmp/analyze_{스킬명}_${TS}"
   mkdir -p "$SKILL_TMPDIR"
   echo "임시 디렉토리: $SKILL_TMPDIR"

   ※ 주의: TMPDIR은 macOS/Linux 시스템 예약 환경변수이므로 반드시 SKILL_TMPDIR을 사용한다.
```
