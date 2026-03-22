"""AgentForge Lite — Bash工具：Shell执行 + 危险命令过滤 + 超时"""

import asyncio
import subprocess

from langchain_core.tools import tool

from src.core.config import BASH_TIMEOUT, DANGEROUS_COMMANDS, WORKSPACE_ROOT


def _is_dangerous(command: str) -> bool:
    """检查命令是否包含危险模式"""
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return True
    return False


@tool
def bash(command: str) -> str:
    """在shell中执行命令。

    Args:
        command: 要执行的shell命令

    Returns:
        命令的stdout和stderr输出（截断至50000字符）
    """
    if _is_dangerous(command):
        return f"[BLOCKED] 危险命令被拦截: {command}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=BASH_TIMEOUT,
            cwd=str(WORKSPACE_ROOT),
        )
        output = result.stdout + result.stderr
        if not output.strip():
            output = f"[exit code: {result.returncode}]"
        return output[:50_000]
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] 命令超时（{BASH_TIMEOUT}秒）: {command}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"
