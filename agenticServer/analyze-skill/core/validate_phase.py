#!/usr/bin/env python3
"""
Phase 경계 JSON 정합성 검증
사용: python validate_phase.py <phase> <tmpdir>
  phase: phase2 | phase2_5 | phase3 | phase4

Phase 2  → 각 *_raw.json이 필수 필드를 갖는지 확인
Phase 2.5 → deliberated.json의 모든 ID가 raw.json에서 왔는지 확인
Phase 3  → deliberated.json의 모든 버그 ID가 prompt_verified.json에 존재하는지 확인
Phase 4  → prompt_verified.json의 CONFIRMED ID가 arbiter.json에 모두 존재하는지 확인
"""
from __future__ import annotations
import sys, json
from pathlib import Path


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def validate_phase2(tmpdir: str) -> list[str]:
    """각 *_raw.json이 필수 필드(analyst, bugs[])를 갖는지 확인"""
    errors = []
    expected = [
        "code_analyst_raw.json",
        "logic_auditor_raw.json",
        "contract_reviewer_raw.json",
        "interface_guard_raw.json",
        "context_guard_raw.json",
        "semantic_auditor_raw.json",
    ]
    for fname in expected:
        path = Path(tmpdir) / fname
        if not path.exists():
            errors.append(f"MISSING: {fname}")
            continue
        try:
            data = load(path)
        except json.JSONDecodeError as e:
            errors.append(f"INVALID_JSON: {fname} ({e})")
            continue
        if "bugs" not in data:
            errors.append(f"NO_BUGS_FIELD: {fname}")
        if fname != "code_analyst_raw.json" and "analyst" not in data:
            errors.append(f"NO_ANALYST_FIELD: {fname}")
    return errors


def validate_phase2_5(tmpdir: str) -> list[str]:
    """deliberated.json의 모든 ID가 *_raw.json 중 하나에서 온 것인지 확인"""
    errors = []
    del_path = Path(tmpdir) / "deliberated.json"
    if not del_path.exists():
        return ["MISSING: deliberated.json"]
    deliberated = load(del_path)

    raw_ids: set[str] = set()
    for fname in Path(tmpdir).glob("*_raw.json"):
        try:
            data = load(fname)
            for bug in data.get("bugs", []):
                if "id" in bug:
                    raw_ids.add(bug["id"])
        except (json.JSONDecodeError, KeyError):
            pass

    for bug in deliberated.get("bugs", []):
        bug_id = bug.get("id", "")
        if bug_id and bug_id not in raw_ids:
            errors.append(
                f"ORPHAN_ID in deliberated.json: '{bug_id}' — 어떤 *_raw.json에도 없음"
            )
    # verification_tasks 부재는 WARNING만 출력 — AUTO 모드 호환, 파이프라인 중단 안 함
    if "verification_tasks" not in deliberated:
        print("[WARNING] deliberated.json에 verification_tasks 없음 — Phase 3 proactive 검증 비활성화됨")
    return errors


def validate_phase3(tmpdir: str) -> list[str]:
    """deliberated.json의 모든 버그 ID가 prompt_verified.json에 존재하는지 확인 (CONFIRMED 또는 CLEARED 중 하나)"""
    errors = []
    del_path = Path(tmpdir) / "deliberated.json"
    ver_path = Path(tmpdir) / "prompt_verified.json"
    for p in [del_path, ver_path]:
        if not p.exists():
            return [f"MISSING: {p.name}"]

    deliberated = load(del_path)
    verified = load(ver_path)

    deliberated_ids = {b["id"] for b in deliberated.get("bugs", []) if "id" in b}
    verified_ids = {
        bid for b in verified.get("bugs", [])
        if (bid := b.get("id", b.get("ref", "")))
    }

    for mid in sorted(deliberated_ids - verified_ids):
        errors.append(
            f"DROPPED in Phase 3: '{mid}' — deliberated.json에 있지만 prompt_verified.json에 없음"
        )
    # CONFIRMED 버그에 confirmed_facts_inherited 필드 확인 (선택적 — WARNING만)
    for bug in verified.get("bugs", []):
        if bug.get("verdict") == "CONFIRMED" and "confirmed_facts_inherited" not in bug:
            print(
                f"[WARNING] prompt_verified.json '{bug.get('id', bug.get('ref', '?'))}': "
                "CONFIRMED이지만 confirmed_facts_inherited 없음 — 증거 체인 불완전"
            )

    # UNCERTAIN verdict 검증: clarifying_question 필드 필수
    uncertain_count = 0
    for bug in verified.get("bugs", []):
        if bug.get("verdict") == "UNCERTAIN":
            uncertain_count += 1
            bug_id = bug.get("id", bug.get("ref", "?"))
            if not bug.get("clarifying_question"):
                errors.append(
                    f"UNCERTAIN_NO_QUESTION: '{bug_id}' — "
                    "verdict=UNCERTAIN이지만 clarifying_question 없음"
                )
            if not bug.get("decision_impact"):
                errors.append(
                    f"UNCERTAIN_NO_IMPACT: '{bug_id}' — "
                    "verdict=UNCERTAIN이지만 decision_impact 없음"
                )

    if uncertain_count > 0:
        print(f"[INFO] Phase 3 UNCERTAIN: {uncertain_count}건 — Phase 5 HITL 필요")

    return errors


def validate_phase4(tmpdir: str) -> list[str]:
    """prompt_verified.json의 CONFIRMED ID가 arbiter.json confirmed_bugs 또는 cleared_bugs에 모두 존재하는지 확인"""
    errors = []
    ver_path = Path(tmpdir) / "prompt_verified.json"
    arb_path = Path(tmpdir) / "arbiter.json"
    for p in [ver_path, arb_path]:
        if not p.exists():
            return [f"MISSING: {p.name}"]

    verified = load(ver_path)
    arbiter = load(arb_path)

    confirmed_ids = {
        b.get("id", b.get("ref", ""))
        for b in verified.get("bugs", [])
        if b.get("verdict") == "CONFIRMED"
    }
    arbiter_ids = (
        {b.get("ref", "") for b in arbiter.get("confirmed_bugs", [])} |
        {b.get("ref", "") for b in arbiter.get("cleared_bugs", [])} |
        {e.get("ref", "") for e in arbiter.get("escalations", [])}
    )

    for mid in sorted(confirmed_ids - arbiter_ids):
        errors.append(
            f"DROPPED in Phase 4: '{mid}' — Phase 3 CONFIRMED이지만 arbiter.json에 없음"
        )

    # UNCERTAIN ID 추적: Phase 3 UNCERTAIN이 arbiter.json에 모두 존재하는지 확인
    # (arbiter_ids는 confirmed_bugs + cleared_bugs + escalations를 모두 포함)
    uncertain_ids = {
        b.get("id", b.get("ref", ""))
        for b in verified.get("bugs", [])
        if b.get("verdict") == "UNCERTAIN"
    }
    for mid in sorted(uncertain_ids - arbiter_ids):
        errors.append(
            f"DROPPED_UNCERTAIN in Phase 4: '{mid}' — Phase 3 UNCERTAIN이지만 "
            "arbiter.json escalations[]에도 없고 confirmed/cleared_bugs에도 없음"
        )

    return errors


VALIDATORS = {
    "phase2":   validate_phase2,
    "phase2_5": validate_phase2_5,
    "phase3":   validate_phase3,
    "phase4":   validate_phase4,
}


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: validate_phase.py <phase2|phase2_5|phase3|phase4> <tmpdir>",
            file=sys.stderr,
        )
        sys.exit(1)

    phase, tmpdir = sys.argv[1], sys.argv[2]

    if phase not in VALIDATORS:
        print(f"Unknown phase: {phase}. Valid: {list(VALIDATORS)}", file=sys.stderr)
        sys.exit(1)

    errors = VALIDATORS[phase](tmpdir)

    if errors:
        print(f"[VALIDATION FAILED] {phase}:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        count_map = {
            "phase2":   "6개 raw.json",
            "phase2_5": "deliberated.json ID 추적",
            "phase3":   "Phase 2.5→3 ID 연속성 (CONFIRMED/CLEARED/UNCERTAIN 허용)",
            "phase4":   "Phase 3→4 CONFIRMED 추적",
        }
        print(f"[VALIDATION OK] {phase}: {count_map[phase]} 정합성 확인 완료")


if __name__ == "__main__":
    main()
