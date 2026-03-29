#!/usr/bin/env python3
"""
공통 모듈: structural element 추출 (phase0_setup.py + phase1_grounding.py 공유)
- shlex.quote()로 경로 안전 처리
- 두 스크립트가 동일 로직으로 fingerprint 일관성 보장
"""
from __future__ import annotations
import shlex, subprocess, hashlib, json
from pathlib import Path

def get_md_files(skill_dir: str) -> list[Path]:
    """메타 파일 제외 .md 파일 목록 (결정론적 정렬)"""
    META = {"README.md", "readme.md", "SKILL.md"}
    return sorted(
        f for f in Path(skill_dir).rglob("*.md")
        if f.name not in META
    )

def grep_oh(pattern: str, files: list[Path]) -> list[str]:
    """macOS BSD grep 호환, 경로 안전 처리 (shlex.quote)"""
    if not files:
        return []
    quoted = [shlex.quote(str(f)) for f in files]
    cmd = f"grep -oh {shlex.quote(pattern)} {' '.join(quoted)} 2>/dev/null | sort -u"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return sorted(set(r.stdout.strip().splitlines()))

def grep_n(pattern: str, files: list[Path]) -> list[str]:
    """라인 번호 포함 grep (경로 안전 처리)"""
    if not files:
        return []
    quoted = [shlex.quote(str(f)) for f in files]
    cmd = f"grep -n {shlex.quote(pattern)} {' '.join(quoted)} 2>/dev/null"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip().splitlines()

def extract_structural_elements(skill_dir: str) -> dict:
    """
    구조적 요소 추출 — fingerprint 계산에 사용.
    phase0_setup.py와 phase1_grounding.py가 동일 함수를 호출하여
    fingerprint 불일치 방지.
    """
    md_files = get_md_files(skill_dir)
    produced = grep_oh(r'\$SKILL_TMPDIR/[a-zA-Z0-9_.-]*\.json', md_files)
    consumed = grep_oh(r'"[a-zA-Z0-9_.-]*\.json"', md_files)
    fields   = grep_oh(r'"[a-zA-Z_][a-zA-Z0-9_]*":', md_files)
    return {
        "produced_files": produced,
        "consumed_files": consumed,
        "field_contracts": fields[:50],
    }

def compute_fingerprint(structural: dict) -> str:
    canonical = json.dumps(structural, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(canonical.encode()).hexdigest()
