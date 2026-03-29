import os
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.structural import get_md_files, grep_oh, grep_n
from core.validator import StructuralValidator

class GroundingEngine:
    """
    소스코드 및 문서에서 분석에 필요한 결정론적 팩트를 추출합니다.
    (기존 phase1_grounding.py 로직의 함수화 버전)
    """

    def __init__(self, skill_dir: str):
        self.skill_dir = Path(skill_dir)
        if not self.skill_dir.exists():
            raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

    def extract_all_facts(self, analyze_md_path: Optional[str] = None) -> Dict[str, Any]:
        """모든 팩트를 추출하여 딕셔너리로 반환합니다."""
        facts = self.extract_common_facts()
        facts["skill_purpose"] = self.extract_skill_purpose()
        facts["block_index"] = self.build_block_index(analyze_md_path)
        
        # analyze.md가 있을 경우 추가 정보 추출
        if analyze_md_path and os.path.exists(analyze_md_path):
            facts["custom_grep_results"] = self.execute_custom_greps(analyze_md_path)
            facts["known_vulns"] = self.extract_known_vulns(analyze_md_path)
        else:
            facts["custom_grep_results"] = []
            facts["known_vulns"] = []

        # 기계적 검증 수행 (Auto-Detected Errors)
        facts["auto_detected_errors"] = StructuralValidator.validate_all(facts)

        # 메타 정보 추가
        facts.update({
            "skill_dir": str(self.skill_dir),
            "files": [f.name for f in self.skill_dir.rglob("*.md")],
        })

        # 전문가 뷰 생성
        facts["_expert_views"] = self.build_expert_views(facts)
        return facts

    def extract_skill_purpose(self) -> str:
        skill_md = self.skill_dir / "SKILL.md"
        if skill_md.exists():
            m = re.search(r'^description:\s*(.+)', skill_md.read_text(), re.MULTILINE)
            if m:
                return m.group(1).strip()[:300]
        return ""

    def extract_common_facts(self) -> Dict[str, Any]:
        md_files = get_md_files(str(self.skill_dir))
        return {
            "phase_output_files":   grep_oh(r'\$SKILL_TMPDIR/[a-zA-Z0-9_.-]*\.json', md_files),
            "phase_input_files":    grep_oh(r'"[a-zA-Z0-9_.-]*\.json"', md_files),
            "json_key_refs":        grep_oh(r'"[a-zA-Z_][a-zA-Z0-9_]*":', md_files),
            "branch_conditions":    grep_n(r'IF\|ELSE\|ELIF\|skipped\|code_analyst_needed', md_files),
            "mode_refs":            grep_n(r'CUSTOM\|AUTO', md_files),
            "reserved_var_risk":    grep_n(r'TMPDIR', md_files),
        }

    def build_block_index(self, analyze_md_path: Optional[str] = None) -> List[Dict[str, Any]]:
        META_FILES = {"README.md", "readme.md", "SKILL.md"}
        SHELL_LANGS = {'bash', 'sh', 'zsh'}
        DATA_LANGS  = {'json', 'yaml', 'yml', 'toml'}
        CODE_LANGS  = {'py', 'python', 'ts', 'typescript', 'js', 'javascript',
                       'tsx', 'jsx', 'go', 'rust', 'java', 'kotlin', 'swift',
                       'cpp', 'c', 'cs', 'rb', 'php'}

        intent_map = {}
        if analyze_md_path and Path(analyze_md_path).exists():
            for line in Path(analyze_md_path).read_text().splitlines():
                m = re.match(r'-\s+`?(\S+?)`?\s+line\s+(\d+):\s+.+?\s+→\s+intent:\s+(\w+)', line)
                if m:
                    intent_map[f"{m.group(1)}:{m.group(2)}"] = m.group(3)

        block_index = []
        md_files = sorted(
            f for f in self.skill_dir.rglob("*.md")
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
                    m = re.match(r'^```(\w*)', line)
                    if m:
                        in_block = True
                        block_lang = m.group(1).lower()
                        block_start = i
                else:
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

        return block_index

    def build_expert_views(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        block_index = facts.get("block_index", [])
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
                "block_index": block_index,
            },
            "SemanticAuditor": {
                **custom_ctx,
                "block_index": [b for b in block_index if b["type"] in ("PSEUDO", "CODE")],
            },
        }

    def execute_custom_greps(self, analyze_md_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(analyze_md_path): return []
        content = Path(analyze_md_path).read_text()
        section_match = re.search(r'##\s+추가 정적 분析 명령.*?\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
        if not section_match: return []
        
        bash_blocks = re.findall(r'```bash\n(.*?)```', section_match.group(1), re.DOTALL)
        results = []
        for block in bash_blocks:
            cmd = block.strip().replace('{스킬경로}', str(self.skill_dir))
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(self.skill_dir), timeout=30)
                results.append({"command": cmd, "stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "returncode": r.returncode})
            except Exception as e:
                results.append({"command": cmd, "error": str(e)})
        return results

    def extract_known_vulns(self, analyze_md_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(analyze_md_path): return []
        content = Path(analyze_md_path).read_text()
        section_match = re.search(r'##\s+알려진 취약 지점.*?\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
        if not section_match: return []
        
        results = []
        for line in section_match.group(1).splitlines():
            m = re.match(r'\s*-\s+\*\*\[([A-Z]+-\d+)\]\s*(.*?)\*\*[:\s]*(.*?)(?:\s*—\s*(\d{4}-\d{2}-\d{2}))?$', line)
            if m:
                results.append({"id": m.group(1), "short": m.group(2).strip(), "description": m.group(3).strip(), "date": m.group(4) or ""})
        return results
