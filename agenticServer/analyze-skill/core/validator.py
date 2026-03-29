import re
from typing import List, Dict, Any

class StructuralValidator:
    """
    MD 프로토콜에 있던 결정론적/기계적 검증 규칙을 Python 로직으로 수행합니다.
    """

    @staticmethod
    def check_reserved_vars(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """시스템 예약 변수(TMPDIR) 사용 여부 검사"""
        errors = []
        for line in facts.get("reserved_var_risk", []):
            if "TMPDIR" in line and "SKILL_TMPDIR" not in line:
                errors.append({
                    "id": "VAL-TR",
                    "severity": "CRITICAL",
                    "description": "시스템 예약 변수 'TMPDIR' 사용이 감지되었습니다. 'SKILL_TMPDIR'을 사용해야 합니다.",
                    "evidence": line
                })
        return errors

    @staticmethod
    def check_branch_completeness(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """분기 조건의 타입 커버리지 검사 (SINGLE/PROMPT/HYBRID)"""
        errors = []
        branch_lines = "\n".join(facts.get("branch_conditions", []))
        
        # 스킬 타입이 복합적일 수 있는 경우 (예: HYBRID) 체크
        if facts.get("skill_type") == "HYBRID":
            missing = []
            if "SINGLE" not in branch_lines: missing.append("SINGLE")
            if "PROMPT" not in branch_lines: missing.append("PROMPT")
            
            for m in missing:
                errors.append({
                    "id": "VAL-BC",
                    "severity": "MEDIUM",
                    "description": f"HYBRID 타입 스킬에서 {m} 분기 처리가 누락되었을 가능성이 있습니다.",
                    "evidence": "branch_conditions 내 키워드 미발견"
                })
        return errors

    @staticmethod
    def validate_all(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """모든 기계적 검증 규칙을 실행합니다."""
        all_errors = []
        all_errors.extend(StructuralValidator.check_reserved_vars(facts))
        all_errors.extend(StructuralValidator.check_branch_completeness(facts))
        return all_errors
