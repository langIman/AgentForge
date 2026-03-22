"""AgentForge Lite — 文件操作工具：read/write/edit + 路径沙箱"""

from pathlib import Path

from langchain_core.tools import tool

from src.core.config import WORKSPACE_ROOT


def _safe_path(file_path: str) -> Path:
    """将路径解析为绝对路径并验证在沙箱内。

    Raises:
        ValueError: 路径越出沙箱
    """
    resolved = Path(file_path).resolve()
    # 如果是相对路径，基于WORKSPACE_ROOT解析
    if not Path(file_path).is_absolute():
        resolved = (WORKSPACE_ROOT / file_path).resolve()
    # 沙箱检查
    if not str(resolved).startswith(str(WORKSPACE_ROOT)):
        raise ValueError(f"路径越出沙箱: {resolved}（沙箱: {WORKSPACE_ROOT}）")
    return resolved


@tool
def read_file(file_path: str, offset: int = 0, limit: int = 2000) -> str:
    """读取文件内容。

    Args:
        file_path: 文件路径（相对于workspace或绝对路径）
        offset: 起始行号（从0开始）
        limit: 读取行数上限

    Returns:
        带行号的文件内容
    """
    try:
        path = _safe_path(file_path)
    except ValueError as e:
        return f"[SANDBOX ERROR] {e}"

    if not path.exists():
        return f"[ERROR] 文件不存在: {path}"
    if not path.is_file():
        return f"[ERROR] 不是文件: {path}"

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = lines[offset : offset + limit]
        numbered = [f"{i + offset + 1:>6}\t{line}" for i, line in enumerate(selected)]
        result = "\n".join(numbered)
        if len(lines) > offset + limit:
            result += f"\n... (共{len(lines)}行，已显示{offset+1}-{offset+len(selected)})"
        return result if result else "[EMPTY FILE]"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """写入文件（覆盖已有内容）。

    Args:
        file_path: 文件路径
        content: 文件内容

    Returns:
        操作结果
    """
    try:
        path = _safe_path(file_path)
    except ValueError as e:
        return f"[SANDBOX ERROR] {e}"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"已写入 {path}（{len(content)} 字符）"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """精确替换文件中的字符串。

    Args:
        file_path: 文件路径
        old_string: 要替换的原文（必须在文件中唯一）
        new_string: 替换后的新文

    Returns:
        操作结果
    """
    try:
        path = _safe_path(file_path)
    except ValueError as e:
        return f"[SANDBOX ERROR] {e}"

    if not path.exists():
        return f"[ERROR] 文件不存在: {path}"

    try:
        text = path.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return f"[ERROR] 未找到要替换的字符串"
        if count > 1:
            return f"[ERROR] old_string 在文件中出现 {count} 次，需要唯一匹配。请提供更多上下文。"
        new_text = text.replace(old_string, new_string, 1)
        path.write_text(new_text, encoding="utf-8")
        return f"已替换 {path} 中的内容（1处）"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"
