import os
import re
from typing import Optional, Dict, List
from config import PATHS

class PolicyInterpreter:
    """
    Expert/Phase protocols (.md)를 읽어 LLM에 주입할 최적화된 지침을 추출합니다.
    """

    def __init__(self):
        self.protocols_dir = PATHS["protocols"]

    def _read_file(self, filename: str) -> str:
        path = os.path.join(self.protocols_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Protocol not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def get_expert_protocol(self, expert_name: str, filter_intent: Optional[str] = None) -> str:
        """
        Expert 프로토콜에서 핵심 섹션만 추출합니다.
        """
        # CamelCase to snake_case (LogicAuditor -> logic_auditor)
        snake_name = re.sub(r'(?<!^)(?=[A-Z])', '_', expert_name).lower()
        filename = f"{snake_name}.md"
        content = self._read_file(filename)

        sections = self._parse_markdown_sections(content)
        
        # 필수 섹션 조합
        required = ["페르소나", "분석 포커스", "출력 스키마", "금지 목록"]
        distilled = []
        
        for title in required:
            if title in sections:
                body = sections[title]
                if title == "분석 포커스" and filter_intent:
                    body = self._filter_focus_items(body, filter_intent)
                
                distilled.append(f"## {title}\n{body}")

        return "\n\n".join(distilled)

    def _parse_markdown_sections(self, content: str) -> Dict[str, str]:
        """
        H2 (##) 헤더 기준으로 섹션을 분리합니다.
        """
        sections = {}
        current_title = None
        current_body = []

        for line in content.splitlines():
            match = re.match(r"^##\s+(.+)$", line)
            if match:
                if current_title:
                    sections[current_title] = "\n".join(current_body).strip()
                current_title = match.group(1).strip()
                current_body = []
            elif current_title:
                current_body.append(line)

        if current_title:
            sections[current_title] = "\n".join(current_body).strip()

        return sections

    def _filter_focus_items(self, focus_body: str, intent: str) -> str:
        """
        분석 포커스 내에서 특정 키워드(intent)와 관련된 항목만 남깁니다.
        """
        lines = focus_body.splitlines()
        filtered = []
        
        # 체크박스 항목 단위로 분리 (□ 로 시작하는 블록)
        current_block = []
        for line in lines:
            if line.strip().startswith("□"):
                if current_block:
                    # 블록 내에 intent 키워드가 있으면 결과에 포함
                    if any(intent.lower() in l.lower() for l in current_block):
                        filtered.extend(current_block)
                current_block = [line]
            elif current_block:
                current_block.append(line)

        # 마지막 블록 처리
        if current_block and any(intent.lower() in l.lower() for l in current_block):
            filtered.extend(current_block)

        return "\n".join(filtered) if filtered else focus_body

# Singleton instance
interpreter = PolicyInterpreter()
