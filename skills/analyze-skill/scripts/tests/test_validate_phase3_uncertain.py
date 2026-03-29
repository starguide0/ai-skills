#!/usr/bin/env python3
"""UNCERTAIN verdict가 validate_phase3()를 통과하는지 확인"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from validate_phase import validate_phase3

def _write(tmp_path, filename, data):
    p = tmp_path / filename
    p.write_text(json.dumps(data))
    return p

def test_uncertain_verdict_passes(tmp_path):
    """UNCERTAIN verdict는 validate_phase3 오류 없이 통과해야 함"""
    _write(tmp_path, "deliberated.json", {
        "bugs": [{"id": "LA-001"}],
        "verification_tasks": []
    })
    _write(tmp_path, "prompt_verified.json", {
        "bugs": [{
            "id": "LA-001",
            "verdict": "UNCERTAIN",
            "verdict_reason": "grep 결과 모호",
            "clarifying_question": "ANALYZE_MD_PATH가 전달되나요?",
            "decision_impact": "YES → CLEARED / NO → CONFIRMED"
        }]
    })
    errors = validate_phase3(str(tmp_path))
    assert errors == [], f"UNCERTAIN은 오류가 아님: {errors}"

def test_confirmed_and_uncertain_mixed(tmp_path):
    """CONFIRMED + UNCERTAIN 혼합도 통과해야 함"""
    _write(tmp_path, "deliberated.json", {
        "bugs": [{"id": "LA-001"}, {"id": "CG-001"}],
        "verification_tasks": []
    })
    _write(tmp_path, "prompt_verified.json", {
        "bugs": [
            {"id": "LA-001", "verdict": "CONFIRMED"},
            {"id": "CG-001", "verdict": "UNCERTAIN",
             "clarifying_question": "질문?", "decision_impact": "YES → CLEARED / NO → CONFIRMED"}
        ]
    })
    errors = validate_phase3(str(tmp_path))
    assert errors == []

def test_missing_clarifying_question_for_uncertain(tmp_path):
    """UNCERTAIN인데 clarifying_question 없으면 오류"""
    _write(tmp_path, "deliberated.json", {
        "bugs": [{"id": "LA-001"}],
        "verification_tasks": []
    })
    _write(tmp_path, "prompt_verified.json", {
        "bugs": [{"id": "LA-001", "verdict": "UNCERTAIN", "verdict_reason": "모호"}]
    })
    errors = validate_phase3(str(tmp_path))
    assert any("clarifying_question" in e for e in errors), f"오류 예상: {errors}"

def test_missing_decision_impact_for_uncertain(tmp_path):
    """UNCERTAIN인데 decision_impact 없으면 오류"""
    _write(tmp_path, "deliberated.json", {
        "bugs": [{"id": "LA-001"}],
        "verification_tasks": []
    })
    _write(tmp_path, "prompt_verified.json", {
        "bugs": [{
            "id": "LA-001",
            "verdict": "UNCERTAIN",
            "verdict_reason": "모호",
            "clarifying_question": "질문이 있음"
            # decision_impact 없음
        }]
    })
    errors = validate_phase3(str(tmp_path))
    assert any("decision_impact" in e for e in errors), f"오류 예상: {errors}"
