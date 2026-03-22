"""AgentForge Lite — 配置模块"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# LLM (Qwen via OpenAI-compatible API)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-plus")

# 工作区
WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", "./workspace")).resolve()

# Token阈值（用于自动压缩，Phase 2）
TOKEN_THRESHOLD = int(os.getenv("TOKEN_THRESHOLD", "80000"))

# 技能目录
SKILLS_DIR = Path(os.getenv("SKILLS_DIR", "./src/skills")).resolve()

# 危险命令黑名单
DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "chmod -R 777 /",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
]

# Bash执行超时（秒）
BASH_TIMEOUT = 120

# Todo限制
TODO_MAX_ITEMS = 20
TODO_NAG_INTERVAL = 3  # 每隔N轮提醒

# 子Agent
SUBAGENT_MAX_ROUNDS = 10
