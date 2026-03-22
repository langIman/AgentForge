"""AgentForge Lite — 技能系统：两层注入"""

from pathlib import Path

from langchain_core.tools import tool

from src.core.config import SKILLS_DIR


class SkillLoader:
    """技能加载器 — 两层注入。

    Layer 1: get_descriptions() → 简短描述注入system prompt（~100 tok/技能）
    Layer 2: get_content(name) → 完整SKILL.md作为tool_result（~2000 tok）
    """

    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self.skills_dir = skills_dir
        self._cache: dict[str, str] = {}

    def _discover(self) -> list[str]:
        """发现所有可用技能（含SKILL.md的子目录）"""
        if not self.skills_dir.exists():
            return []
        return [
            d.name
            for d in sorted(self.skills_dir.iterdir())
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    def get_descriptions(self) -> str:
        """Layer 1: 获取所有技能的简短描述（用于system prompt）"""
        skills = self._discover()
        if not skills:
            return ""
        lines = []
        for name in skills:
            skill_file = self.skills_dir / name / "SKILL.md"
            content = skill_file.read_text(encoding="utf-8")
            # 取第一行非空行作为描述
            first_line = ""
            for line in content.splitlines():
                stripped = line.strip().lstrip("#").strip()
                if stripped:
                    first_line = stripped
                    break
            lines.append(f"- **{name}**: {first_line}")
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        """Layer 2: 获取技能完整内容"""
        if name in self._cache:
            return self._cache[name]

        skill_file = self.skills_dir / name / "SKILL.md"
        if not skill_file.exists():
            return f"[ERROR] 技能 '{name}' 不存在。可用技能: {', '.join(self._discover())}"

        content = skill_file.read_text(encoding="utf-8")
        self._cache[name] = content
        return content


# 全局单例
skill_loader = SkillLoader()


@tool
def load_skill(name: str) -> str:
    """加载指定技能的完整内容。

    Args:
        name: 技能名称（如 code-review, agent-builder）

    Returns:
        技能的完整SKILL.md内容
    """
    return skill_loader.get_content(name)
