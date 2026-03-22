# Agent Builder — Agent构建技能

## 触发条件
当用户要求创建新Agent、设计Agent架构、或配置Agent工具集时加载此技能。

## 构建流程

1. **需求分析**：明确Agent的目标、工具集、约束
2. **设计State**：确定需要的状态字段
3. **选择工具**：从可用工具中选择合适的子集
4. **配置节点**：定制 pre_process / agent / post_process
5. **测试验证**：构建后进行基本对话测试

## Agent架构模板

```python
from src.core.state import AgentState
from src.core.graph import build_graph

# 1. 定义专用State（可选扩展AgentState）
class MyAgentState(AgentState):
    custom_field: str

# 2. 选择工具集
tools = [bash, read_file, write_file, edit_file]

# 3. 创建节点
nodes = make_nodes(model)  # 或自定义

# 4. 构建图
graph = build_graph(MyAgentState, nodes, tools)
```

## 最佳实践

- **工具最小化**：只给Agent需要的工具，减少出错空间
- **System Prompt**：清晰定义Agent角色和边界
- **轮次限制**：设置合理的最大交互轮次
- **输出格式**：明确期望的输出格式
- **错误处理**：预设常见错误的恢复策略

## 常见Agent类型

| 类型 | 工具集 | 特点 |
|------|--------|------|
| 探索型 | read_file, bash | 只读，用于信息收集 |
| 编码型 | 全套file工具 + bash | 可修改代码 |
| 审查型 | read_file | 只读，输出报告 |
| 编排型 | spawn_subagent, todo_write | 分解任务、协调子Agent |
