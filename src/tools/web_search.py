"""AgentForge Lite — 在线搜索工具（Tavily）

提供实时网络搜索能力，返回结构化结果。
Tavily 专为 AI Agent 设计，免费额度 1000次/月。

获取 API Key: https://app.tavily.com/
"""

from langchain_core.tools import tool

from src.core.config import TAVILY_API_KEY


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """在互联网上搜索实时信息。

    适用于需要最新数据、文档查询、事实核查等场景。

    Args:
        query: 搜索关键词
        max_results: 返回结果数量（默认5，最大10）

    Returns:
        搜索结果摘要
    """
    if not TAVILY_API_KEY:
        return "[ERROR] 未配置 TAVILY_API_KEY。请在 .env 中设置。获取: https://app.tavily.com/"

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query=query,
            max_results=min(max_results, 10),
            include_answer=True,
        )

        lines = []

        # Tavily 直接给出的答案摘要
        if response.get("answer"):
            lines.append(f"## 摘要\n{response['answer']}\n")

        # 各条搜索结果
        results = response.get("results", [])
        if results:
            lines.append("## 搜索结果")
            for i, r in enumerate(results, 1):
                title = r.get("title", "无标题")
                url = r.get("url", "")
                content = r.get("content", "")[:300]
                lines.append(f"\n### {i}. {title}")
                lines.append(f"URL: {url}")
                lines.append(f"{content}")

        if not lines:
            return f"[无搜索结果] query: {query}"

        return "\n".join(lines)

    except Exception as e:
        return f"[搜索错误] {type(e).__name__}: {e}"
