"""AgentForge Lite — CLI主入口（REPL）

Phase 2: 加入SqliteSaver checkpointer、数据库初始化、新工具、会话恢复。
"""

import asyncio
import sys
import uuid

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

from src.core.config import MODEL_NAME, OPENAI_API_BASE, OPENAI_API_KEY, WORKSPACE_ROOT
from src.core.graph import build_graph
from src.core.nodes import make_nodes
from src.core.state import AgentState
from src.storage.database import init_db
from src.tools.bash import bash
from src.tools.compact import compact
from src.tools.file_ops import edit_file, read_file, write_file
from src.tools.skill import load_skill, skill_loader
from src.tools.subagent import spawn_subagent
from src.tools.task import task_create, task_get, task_list, task_update
from src.tools.todo import todo_manager, todo_write


def create_agent(checkpointer=None):
    """构建主Agent图

    Phase 2: 新增5个工具（compact + task CRUD），加入checkpointer。
    """
    tools = [
        # P1 工具
        bash, read_file, write_file, edit_file,
        todo_write, spawn_subagent, load_skill,
        # P2 工具
        compact, task_create, task_update, task_list, task_get,
    ]
    model = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
    ).bind_tools(tools)
    nodes = make_nodes(model, skill_loader)
    graph = build_graph(AgentState, nodes, tools, checkpointer=checkpointer)
    return graph


def main():
    """CLI REPL主循环"""
    # 初始化数据库（Task/Transcript表）
    asyncio.run(init_db())

    # 确保workspace目录存在
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    # SqliteSaver — 会话持久化，退出重启后可恢复
    with SqliteSaver.from_conn_string("agentforge_checkpoints.db") as checkpointer:
        agent = create_agent(checkpointer=checkpointer)

        # 会话ID：支持恢复已有会话
        session_id = None
        if len(sys.argv) > 1 and sys.argv[1].startswith("--session="):
            session_id = sys.argv[1].split("=", 1)[1]
            print(f"[恢复会话: {session_id}]")
        if not session_id:
            session_id = uuid.uuid4().hex[:8]

        config = {"configurable": {"thread_id": session_id}}

        print("=" * 60)
        print("  AgentForge Lite — Phase 2")
        print(f"  Model: {MODEL_NAME}")
        print(f"  Workspace: {WORKSPACE_ROOT}")
        print(f"  Session: {session_id}")
        print("  输入 'quit'/'exit' 退出 | 'todos' 查看待办 | 'tasks' 查看任务")
        print("=" * 60)
        print()

        while True:
            try:
                user_input = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                print(f"再见！（会话ID: {session_id}，可通过 --session={session_id} 恢复）")
                break
            if user_input.lower() == "todos":
                print(todo_manager.render())
                continue
            if user_input.lower() == "tasks":
                result = task_list.invoke({"status": None})
                print(result)
                continue

            try:
                result = agent.invoke(
                    {
                        "messages": [HumanMessage(content=user_input)],
                        "session_id": session_id,
                        "todos": todo_manager.get_items(),
                        "rounds_since_todo": 0,
                        "token_count": 0,
                        "compressed": False,
                        "tasks_snapshot": "",
                    },
                    config,
                )
                # 提取最终AI回复
                last_ai = None
                for msg in reversed(result["messages"]):
                    if hasattr(msg, "content") and msg.content and msg.type == "ai":
                        if not msg.tool_calls:
                            last_ai = msg.content
                            break
                if last_ai:
                    print(f"\nAgent> {last_ai}\n")
                else:
                    print("\n[Agent执行完毕，无文本输出]\n")
            except KeyboardInterrupt:
                print("\n[中断当前执行]\n")
            except Exception as e:
                print(f"\n[ERROR] {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
