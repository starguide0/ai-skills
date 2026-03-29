from mcp.server.fastmcp import FastMCP
import os
import json
from policy_interpreter import interpreter
from core.grounding import GroundingEngine
from config import PATHS

# Initialize FastMCP server
mcp = FastMCP("AnalyzeSkill")

@mcp.tool()
def get_server_info() -> str:
    """Returns basic information about the Analyze-Skill AgenticServer."""
    return "Analyze-Skill AgenticServer v1.0.0 is running with GroundingEngine & PolicyInterpreter."

@mcp.tool()
def get_rules(expert_name: str, intent: str = "") -> str:
    """
    특정 전문가(Expert)의 분석 규칙을 프로토콜에서 추출하여 반환합니다.
    - expert_name: LogicAuditor, SemanticAuditor 등
    - intent: 특정 분석 의도 (예: IF_BRANCH, SKIP_CONDITION)
    """
    try:
        return interpreter.get_expert_protocol(expert_name, intent)
    except Exception as e:
        return f"Error retrieving rules: {str(e)}"

@mcp.tool()
def extract_facts(skill_dir: str, analyze_md_path: str = "") -> str:
    """
    소스코드 및 문서에서 분석에 필요한 결정론적 팩트를 추출합니다.
    - skill_dir: 대상 스킬의 절대 경로
    - analyze_md_path: 분석 대상 analyze.md 파일의 경로 (있을 경우)
    """
    try:
        engine = GroundingEngine(skill_dir)
        facts = engine.extract_all_facts(analyze_md_path)
        return json.dumps(facts, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error extracting facts: {str(e)}"

if __name__ == "__main__":
    mcp.run()
