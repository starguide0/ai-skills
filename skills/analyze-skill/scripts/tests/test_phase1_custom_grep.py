#!/usr/bin/env python3
"""CG-012 fix: analyze.md 추가 정적 분析 명령 실행 테스트"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from phase1_grounding import execute_custom_greps

def test_bash_block_executed(tmp_path):
    """analyze.md의 bash 블록이 실제로 실행되어 결과가 반환되는지 확인"""
    skill_dir = str(tmp_path)
    (tmp_path / "SKILL.md").write_text("# Test\nsome_key: value\n")
    analyze_md = tmp_path / "analyze.md"
    analyze_md.write_text(
        "## 추가 정적 분析 명령 (Phase 1에서 실행)\n\n"
        "```bash\n"
        "grep -rn 'some_key' {스킬경로}/\n"
        "```\n"
    )
    results = execute_custom_greps(str(analyze_md), skill_dir)
    assert len(results) == 1
    assert results[0]["returncode"] == 0
    assert "some_key" in results[0]["stdout"]
    assert results[0]["command"] != ""

def test_no_analyze_md_returns_empty():
    """analyze.md 없으면 빈 리스트 반환"""
    results = execute_custom_greps("", "/nonexistent")
    assert results == []

def test_section_missing_returns_empty(tmp_path):
    """해당 섹션 없으면 빈 리스트 반환"""
    analyze_md = tmp_path / "analyze.md"
    analyze_md.write_text("# 다른 섹션\n내용 없음\n")
    results = execute_custom_greps(str(analyze_md), str(tmp_path))
    assert results == []

def test_failed_command_recorded(tmp_path):
    """실패한 명령도 returncode와 함께 기록됨"""
    analyze_md = tmp_path / "analyze.md"
    # analyze.md is in tmp_path but we search a separate subdirectory
    search_dir = tmp_path / "src"
    search_dir.mkdir()
    analyze_md.write_text(
        "## 추가 정적 분析 명령 (Phase 1에서 실행)\n\n"
        "```bash\n"
        f"grep -rn 'NONEXISTENT_PATTERN_XYZ' {search_dir}/\n"
        "```\n"
    )
    results = execute_custom_greps(str(analyze_md), str(tmp_path))
    assert len(results) == 1
    assert results[0]["returncode"] != 0
    assert results[0]["stdout"] == ""


def test_multiple_bash_blocks(tmp_path):
    """여러 bash 블록이 있으면 모두 실행됨"""
    (tmp_path / "a.txt").write_text("foo\n")
    (tmp_path / "b.txt").write_text("bar\n")
    analyze_md = tmp_path / "analyze.md"
    analyze_md.write_text(
        "## 추가 정적 분析 명령 (Phase 1에서 실행)\n\n"
        "```bash\n"
        "grep -rn 'foo' {스킬경로}/\n"
        "```\n\n"
        "```bash\n"
        "grep -rn 'bar' {스킬경로}/\n"
        "```\n"
    )
    results = execute_custom_greps(str(analyze_md), str(tmp_path))
    assert len(results) == 2
    assert results[0]["returncode"] == 0
    assert results[1]["returncode"] == 0


def test_empty_bash_block_skipped(tmp_path):
    """빈 bash 블록은 실행하지 않음"""
    analyze_md = tmp_path / "analyze.md"
    analyze_md.write_text(
        "## 추가 정적 분析 명령 (Phase 1에서 실행)\n\n"
        "```bash\n"
        "   \n"
        "```\n"
    )
    results = execute_custom_greps(str(analyze_md), str(tmp_path))
    assert results == []
