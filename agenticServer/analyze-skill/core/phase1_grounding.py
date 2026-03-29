#!/usr/bin/env python3
"""
Phase 1: Grounding — grep 추출 + block_index 파싱 → facts.json
입력: phase0_result.json
출력: $SKILL_TMPDIR/facts.json
"""
from __future__ import annotations
import sys, json, re, shlex, subprocess
from pathlib import Path

# 공통 모듈 임포트 (run_grep 제거 — structural.py의 grep_oh/grep_n 사용)
sys.path.insert(0, str(Path(__file__).parent))
from structural import get_md_files, grep_oh, grep_n

def extract_skill_purpose(skill_dir: str) -> str:
    """대상 스킬의 목적을 결정론적으로 추출 (SKILL.md frontmatter description 우선, README.md fallback)"""
    skill_md = Path(skill_dir) / "SKILL.md"
    if skill_md.exists():
        m = re.search(r'^description:\s*(.+)', skill_md.read_text(), re.MULTILINE)
        if m:
            return m.group(1).strip()[:300]
    readme = Path(skill_dir) / "README.md"
    if readme.exists():
        for line in readme.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                return stripped[:300]
    return ""


def extract_common_facts(skill_dir: str) -> dict:
    """모든 타입 공통 grep 추출 — structural.py의 함수 재사용"""
    md_files = get_md_files(skill_dir)

    def freq(files: list[Path]) -> list[str]:
        """$SKILL_TMPDIR/*.json 파일 참조 빈도"""
        quoted = [shlex.quote(str(f)) for f in files]
        cmd = (
            f"grep -oh '$SKILL_TMPDIR/[a-zA-Z0-9_.-]*.json' {' '.join(quoted)} 2>/dev/null"
            " | sed 's|\\$SKILL_TMPDIR/||' | sort | uniq -c | sort -rn"
        )
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return r.stdout.strip().splitlines()

    return {
        "phase_output_files":   grep_oh(r'\$SKILL_TMPDIR/[a-zA-Z0-9_.-]*\.json', md_files),
        "phase_input_files":    grep_oh(r'"[a-zA-Z0-9_.-]*\.json"', md_files),
        "json_key_refs":        grep_oh(r'"[a-zA-Z_][a-zA-Z0-9_]*":', md_files),
        "branch_conditions":    grep_n(r'IF\|ELSE\|ELIF\|skipped\|code_analyst_needed', md_files),
        "mode_refs":            grep_n(r'CUSTOM\|AUTO', md_files),
        "reserved_var_risk":    grep_n(r'TMPDIR', md_files),
        "output_to_input_map":  freq(md_files),
        "analyze_md_path_refs": grep_n(r'ANALYZE_MD_PATH', md_files),
    }

def extract_known_vulns(analyze_md_path: str) -> list[dict]:
    """
    analyze.md의 '알려진 취약 지점' 섹션에서 항목을 파싱한다.
    반환: [{"id": "CR-002", "description": "...", "date": "2026-03-22"}]
    """
    if not analyze_md_path or not Path(analyze_md_path).exists():
        return []
    content = Path(analyze_md_path).read_text()
    section_match = re.search(
        r'##\s+알려진 취약 지점.*?\n(.*?)(?=\n##\s|\Z)',
        content, re.DOTALL
    )
    if not section_match:
        return []
    results = []
    for line in section_match.group(1).splitlines():
        # 형식: - **[CR-002] 설명**: 세부내용 — YYYY-MM-DD
        m = re.match(r'\s*-\s+\*\*\[([A-Z]+-\d+)\]\s*(.*?)\*\*[:\s]*(.*?)(?:\s*—\s*(\d{4}-\d{2}-\d{2}))?$', line)
        if m:
            results.append({
                "id": m.group(1),
                "short": m.group(2).strip(),
                "description": m.group(3).strip(),
                "date": m.group(4) or "",
            })
    return results


def execute_custom_greps(analyze_md_path: str, skill_dir: str) -> list[dict]:
    """
    analyze.md의 '추가 정적 분析 명령 (Phase 1에서 실행)' 섹션에서
    bash 블록을 추출해 실행하고 결과를 반환한다.

    반환 형식: [{"command": str, "stdout": str, "stderr": str, "returncode": int}]
    """
    if not analyze_md_path or not Path(analyze_md_path).exists():
        return []

    content = Path(analyze_md_path).read_text()

    # '추가 정적 분析 명령' 섹션 추출 (다음 ## 섹션 전까지)
    section_match = re.search(
        r'##\s+추가 정적 분析 명령.*?\n(.*?)(?=\n##\s|\Z)',
        content,
        re.DOTALL
    )
    if not section_match:
        return []

    section = section_match.group(1)

    # bash 코드 블록 추출
    bash_blocks = re.findall(r'```bash\n(.*?)```', section, re.DOTALL)
    if not bash_blocks:
        return []

    results = []
    for block in bash_blocks:
        cmd = block.strip().replace('{스킬경로}', skill_dir)
        if not cmd:  # skip empty blocks
            continue
        try:
            r = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=skill_dir,
                timeout=30,
            )
            results.append({
                "command": cmd,
                "stdout": r.stdout.strip(),
                "stderr": r.stderr.strip(),
                "returncode": r.returncode,
            })
        except subprocess.TimeoutExpired:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": "TIMEOUT after 30s",
                "returncode": -1,
            })
    return results


def build_block_index(skill_dir: str, analyze_md_path: str) -> list[dict]:
    """
    코드 블록 분류 + block_index 생성

    중첩 백틱 처리 규칙:
    - 블록 내부에서 ``` 로 시작하는 줄이 나오면:
        - 언어 태그가 있으면 (```python) → 중첩 시작으로 간주하지 않고 무시
        - 언어 태그가 없으면 (``` 만) → 닫힘 처리
    - 이 규칙으로 마크다운 예시 블록 내 중첩 펜스를 안전하게 처리
    """
    META_FILES = {"README.md", "readme.md", "SKILL.md"}
    SHELL_LANGS = {'bash', 'sh', 'zsh'}
    DATA_LANGS  = {'json', 'yaml', 'yml', 'toml'}
    CODE_LANGS  = {'py', 'python', 'ts', 'typescript', 'js', 'javascript',
                   'tsx', 'jsx', 'go', 'rust', 'java', 'kotlin', 'swift',
                   'cpp', 'c', 'cs', 'rb', 'php'}

    intent_map = {}
    if analyze_md_path and Path(analyze_md_path).exists():
        for line in Path(analyze_md_path).read_text().splitlines():
            # CG-015 fix: \w+ → [^\s→]+ to handle "(no lang)" format
            # also strip backticks from filename
            m = re.match(r'-\s+`?(\S+?)`?\s+line\s+(\d+):\s+.+?\s+→\s+intent:\s+(\w+)', line)
            if m:
                intent_map[f"{m.group(1)}:{m.group(2)}"] = m.group(3)

    block_index = []
    md_files = sorted(
        f for f in Path(skill_dir).rglob("*.md")
        if f.name not in META_FILES
    )

    for md_file in md_files:
        lines = md_file.read_text().splitlines(keepends=True)
        in_block = False
        block_lang = None
        block_start = 0
        current_section = 'top'
        block_num = 0

        for i, line in enumerate(lines, 1):
            h = re.match(r'^(#{1,3})\s+(.+)', line)
            if h:
                current_section = h.group(2).strip()

            if not in_block:
                # 블록 시작: ``` 로 시작하는 줄
                m = re.match(r'^```(\w*)', line)
                if m:
                    in_block = True
                    block_lang = m.group(1).lower()
                    block_start = i
            else:
                # 블록 내부:
                # ``` 만 있는 줄 → 닫힘
                # ```lang 으로 시작하는 줄 → 중첩 시작 무시 (닫힘 처리하지 않음)
                close_only = re.match(r'^```\s*$', line)
                if close_only:
                    block_num += 1
                    lang = block_lang or ''
                    if lang in SHELL_LANGS:   btype = 'SHELL'
                    elif lang in DATA_LANGS:  btype = 'DATA'
                    elif lang in CODE_LANGS:  btype = 'CODE'
                    else:                     btype = 'PSEUDO'

                    block_lines = lines[block_start:i-1]
                    summary = next((l.strip()[:80] for l in block_lines if l.strip()), '')
                    intent  = intent_map.get(f"{md_file.name}:{block_start + 1}", 'unknown')

                    block_index.append({
                        'file': md_file.name, 'block_number': block_num,
                        'type': btype, 'lang': lang, 'intent': intent,
                        'section': current_section,
                        'line_start': block_start + 1, 'line_end': i - 1,
                        'summary': summary,
                    })
                    in_block = False
                    block_lang = None
                # else: ```lang → 중첩 펜스, 무시하고 계속

    return block_index

def build_expert_views(facts: dict) -> dict:
    """전문가별 입력 뷰 슬라이싱"""
    block_index = facts.get("block_index", [])
    # CUSTOM 모드 공통 컨텍스트 — Workers가 analyze.md를 직접 읽지 않아도 되도록
    custom_ctx = {
        "custom_grep_results": facts.get("custom_grep_results", []),
        "known_vulns": facts.get("known_vulns", []),
    }

    return {
        "LogicAuditor": {
            **custom_ctx,
            "branch_conditions": facts.get("branch_conditions", []),
            "mode_refs": facts.get("mode_refs", []),
            "block_index": [b for b in block_index if b["type"] == "PSEUDO"],
        },
        "ContractReviewer": {
            **custom_ctx,
            "json_key_refs": facts.get("json_key_refs", []),
            "phase_output_files": facts.get("phase_output_files", []),
            "phase_input_files": facts.get("phase_input_files", []),
            "block_index": [b for b in block_index if b["type"] == "DATA"],
        },
        "InterfaceGuard": {
            **custom_ctx,
            "phase_output_files": facts.get("phase_output_files", []),
            "phase_input_files": facts.get("phase_input_files", []),
            "output_to_input_map": facts.get("output_to_input_map", []),
            "block_index": block_index,
        },
        "ContextGuard": {
            **custom_ctx,
            "mode_refs": facts.get("mode_refs", []),
            "json_key_refs": facts.get("json_key_refs", []),
            "block_index": [
                {k: v for k, v in b.items() if k in
                 ("file", "block_number", "type", "section", "line_start", "line_end", "summary")}
                for b in block_index
            ],
        },
        "SemanticAuditor": {
            **custom_ctx,
            "block_index": [b for b in block_index if b["type"] in ("PSEUDO", "CODE")],
        },
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: phase1_grounding.py <phase0_result.json>", file=sys.stderr)
        sys.exit(1)

    phase0 = json.loads(Path(sys.argv[1]).read_text())
    skill_dir     = phase0["skill_dir"]
    skill_tmpdir  = phase0["skill_tmpdir"]
    skill_type    = phase0["skill_type"]
    skill_hash    = phase0["skill_hash"]
    mode          = phase0["mode"]
    analyze_md_path = phase0["analyze_md_path"]

    # 공통 grep 추출
    facts = extract_common_facts(skill_dir)

    # 스킬 목적 추출 (Context Re-Injection 용)
    facts["skill_purpose"] = extract_skill_purpose(skill_dir)

    # block_index 생성
    facts["block_index"] = build_block_index(skill_dir, analyze_md_path)

    # analyze.md 추가 정적 분析 명령 실행 — Phase 2 Workers가 재실행하지 않도록 여기서 처리
    custom_grep_results = execute_custom_greps(analyze_md_path, skill_dir)
    facts["custom_grep_results"] = custom_grep_results
    if custom_grep_results:
        print(f"  custom_grep_results: {len(custom_grep_results)}개 명령 실행됨")

    # analyze.md 알려진 취약 지점 파싱 — Arbiter가 재확인 vs 신규 버그를 구분하는 데 사용
    known_vulns = extract_known_vulns(analyze_md_path)
    facts["known_vulns"] = known_vulns
    if known_vulns:
        print(f"  known_vulns: {len(known_vulns)}개 로드됨 ({', '.join(v['id'] for v in known_vulns)})")

    # 메타 정보
    facts.update({
        "skill_dir": skill_dir,
        "skill_type": skill_type,
        "mode": mode,
        "skill_hash": skill_hash,
        "analyze_md_path": analyze_md_path,
        "files": [f.name for f in Path(skill_dir).rglob("*.md")],
    })

    # 전문가 뷰 슬라이싱
    facts["_expert_views"] = build_expert_views(facts)

    # HYBRID 추가 추출
    if skill_type == "HYBRID":
        py_files = [f for f in Path(skill_dir).rglob("*.py")
                    if "__pycache__" not in str(f)]
        if py_files:
            quoted_py = " ".join(shlex.quote(str(f)) for f in py_files)

            def gpy(pattern: str) -> list[str]:
                r = subprocess.run(
                    f"grep -rn {shlex.quote(pattern)} {quoted_py} 2>/dev/null"
                    " | grep -v __pycache__",
                    shell=True, capture_output=True, text=True
                )
                return r.stdout.strip().splitlines()

            facts.update({
                "glob_patterns":  gpy(r'glob\.'),
                "exit_codes":     gpy(r'sys\.exit'),
                "json_file_refs": gpy(r'\.json"'),
                "json_outputs":   gpy(r'json\.dump'),
            })

            # CR-013: Python 스크립트 출력 JSON 파일명도 phase_output_files에 추가
            # (예: phase0_result.json은 .md에 $SKILL_TMPDIR 참조 없어 grep 누락)
            py_json_lines = gpy(r'"[a-zA-Z0-9_.-]*\.json"')
            py_output_names: set[str] = set()
            for line in py_json_lines:
                m = re.search(r'"([a-zA-Z0-9_.-]+\.json)"', line)
                if m:
                    py_output_names.add(m.group(1))
            existing = set(facts["phase_output_files"])
            facts["phase_output_files"] += sorted(py_output_names - existing)

    # 저장
    out_path = Path(skill_tmpdir) / "facts.json"
    out_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2))

    # 요약 출력
    block_types: dict[str, int] = {}
    for b in facts["block_index"]:
        block_types[b["type"]] = block_types.get(b["type"], 0) + 1

    print(f"facts.json 생성 완료: {out_path}")
    print(f"  block_index: {len(facts['block_index'])}개 — {block_types}")
    print(f"  phase_output_files: {len(facts['phase_output_files'])}개")
    print(f"  branch_conditions: {len(facts['branch_conditions'])}개")
    print(f"  expert_views: {list(facts['_expert_views'].keys())}")

if __name__ == "__main__":
    main()
