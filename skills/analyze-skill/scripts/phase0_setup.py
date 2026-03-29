#!/usr/bin/env python3
"""
Phase 0: 환경 설정, 해시 계산, fingerprint 기반 schema drift 감지
출력: /tmp/analyze_{skill_name}_{ts}/phase0_result.json
"""
import sys, os, json, hashlib
from datetime import datetime
from pathlib import Path

# 공통 모듈 임포트 (같은 scripts/ 디렉토리)
sys.path.insert(0, str(Path(__file__).parent))
from structural import extract_structural_elements, compute_fingerprint

def compute_skill_hash(skill_dir: str) -> str:
    """모든 스킬 파일의 통합 해시"""
    files = sorted(Path(skill_dir).rglob("*"))
    files = [f for f in files if f.is_file() and "__pycache__" not in str(f)]
    h = hashlib.md5()
    for f in files:
        try:
            h.update(f.read_bytes())
        except OSError:
            pass
    return h.hexdigest()

def detect_schema_drift(skill_dir: str, schema_path: str) -> dict:
    """fingerprint 비교로 schema drift 감지"""
    new_structural = extract_structural_elements(skill_dir)
    new_fingerprint = compute_fingerprint(new_structural)

    if not Path(schema_path).exists():
        return {"status": "NO_SCHEMA", "new_fingerprint": new_fingerprint,
                "new_structural": new_structural}

    try:
        schema = json.loads(Path(schema_path).read_text())
    except json.JSONDecodeError:
        return {"status": "SCHEMA_PARSE_ERROR", "new_fingerprint": new_fingerprint,
                "new_structural": new_structural}
    prev_fingerprint = schema.get("_fingerprint", "")

    if new_fingerprint == prev_fingerprint:
        return {"status": "VALID", "fingerprint": new_fingerprint}

    prev = schema.get("_fingerprint_source", {})
    return {
        "status": "DRIFT_DETECTED",
        "prev_fingerprint": prev_fingerprint,
        "new_fingerprint": new_fingerprint,
        "new_structural": new_structural,
        "diff": {
            "added_files":   sorted(set(new_structural["produced_files"]) - set(prev.get("produced_files", []))),
            "removed_files": sorted(set(prev.get("produced_files", [])) - set(new_structural["produced_files"])),
            "added_fields":  sorted(set(new_structural["field_contracts"]) - set(prev.get("field_contracts", []))),
            "removed_fields":sorted(set(prev.get("field_contracts", [])) - set(new_structural["field_contracts"])),
        }
    }

def detect_skill_type(skill_dir: str) -> tuple:
    """
    scripts/ 디렉토리의 .py 파일은 스킬 내부 도구이므로 HYBRID 판정에 포함한다.
    analyze-skill은 scripts/*.py를 포함하므로 HYBRID 타입이 맞다 (의도적).
    """
    META = {"README.md", "readme.md", "SKILL.md"}
    py_files = [
        f for f in Path(skill_dir).rglob("*.py")
        if "__pycache__" not in str(f)
    ]
    md_files = [f for f in Path(skill_dir).rglob("*.md") if f.name not in META]
    if py_files:
        return "HYBRID", True
    elif len(md_files) >= 2:
        return "PROMPT", False
    return "SINGLE", False

def detect_platform() -> tuple:
    home = Path.home()
    if (home / ".claude").exists():
        return "claude-code", str(home / ".claude" / "skills" / "analyze-skill")
    elif (home / ".gemini").exists():
        return "gemini-cli", str(home / ".gemini" / "skills" / "analyze-skill")
    config = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
    return "generic", str(Path(config) / "skills" / "analyze-skill")

def main():
    if len(sys.argv) < 2:
        print("Usage: phase0_setup.py <skill_dir>", file=sys.stderr)
        sys.exit(1)

    skill_dir  = str(Path(sys.argv[1]).resolve())
    skill_name = Path(skill_dir).name
    ts         = datetime.now().strftime("%Y%m%d%H%M%S")
    skill_tmpdir = f"/tmp/analyze_{skill_name}_{ts}"
    Path(skill_tmpdir).mkdir(parents=True, exist_ok=True)

    platform, skill_analysis_dir = detect_platform()
    Path(skill_analysis_dir).mkdir(parents=True, exist_ok=True)

    analyze_md_dir  = Path(skill_analysis_dir) / skill_name
    analyze_md_dir.mkdir(parents=True, exist_ok=True)
    analyze_md_path = str(analyze_md_dir / "analyze.md")
    mode            = "CUSTOM" if Path(analyze_md_path).exists() else "AUTO"
    skill_hash      = compute_skill_hash(skill_dir)

    prev_hash = ""
    if Path(analyze_md_path).exists():
        for line in Path(analyze_md_path).read_text().splitlines():
            if line.startswith("skill_hash:"):
                prev_hash = line.split(":", 1)[1].strip()
                break

    schema_path  = str(Path(skill_dir) / "state.schema.json")
    drift_result = detect_schema_drift(skill_dir, schema_path)
    skill_type, code_analyst_needed = detect_skill_type(skill_dir)

    # Agent Grading & Model Optimization
    config_path = Path(skill_analysis_dir) / "config.json"
    default_config = {
        "grades": {
            "A": {"claude": "claude-3-5-sonnet-latest", "gemini": "gemini-1.5-pro"},
            "B": {"claude": "claude-3-haiku-20240307",  "gemini": "gemini-1.5-flash"},
            "C": {"claude": "claude-3-haiku-20240307",  "gemini": "gemini-1.5-flash-8b"}
        },
        "assignments": {
            "Arbiter": "A", "ServiceLead": "A", "Expert": "B",
            "Verifier": "B", "Enricher": "C", "Crystallizer": "C"
        }
    }

    if not config_path.exists():
        config_path.write_text(json.dumps(default_config, ensure_ascii=False, indent=2))
        config = default_config
    else:
        try:
            config = json.loads(config_path.read_text())
        except Exception:
            config = default_config

    # Resolving models for the current platform
    model_settings = {}
    model_map = {}
    platform_key = "claude" if platform == "claude-code" else "gemini" if platform == "gemini-cli" else platform
    grades = config.get("grades", default_config["grades"])
    assignments = config.get("assignments", default_config["assignments"])
    
    # 1. Global Grade Map (GRADE_A, GRADE_B, GRADE_C)
    for g_key, p_models in grades.items():
        var_name = f"GRADE_{g_key}"
        # Priority: Exact match -> "default" -> fallback hardcoded
        model_name = p_models.get(platform_key) or p_models.get("default")
        if not model_name:
            # Absolute fallback if config is broken
            fallback_map = {"A": "claude-3-5-sonnet-latest", "B": "gemini-1.5-flash", "C": "gemini-1.5-flash-8b"}
            model_name = fallback_map.get(g_key, "unknown")
        model_map[var_name] = model_name

    # 2. Role-to-Model Assignment
    for role, grade in assignments.items():
        model_name = model_map.get(f"GRADE_{grade}", "unknown")
        model_settings[role] = {
            "grade": grade,
            "model": model_name
        }

    result = {
        "skill_dir": skill_dir, "skill_name": skill_name,
        "skill_tmpdir": skill_tmpdir, "platform": platform,
        "skill_analysis_dir": skill_analysis_dir,
        "analyze_md_path": analyze_md_path,
        "mode": mode, "skill_hash": skill_hash,
        "cache_hit": (skill_hash == prev_hash and bool(prev_hash)),
        "skill_type": skill_type,
        "code_analyst_needed": code_analyst_needed,
        "schema_drift": drift_result,
        "model_settings": model_settings,
        "model_map": model_map,
    }

    out = Path(skill_tmpdir) / "phase0_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
