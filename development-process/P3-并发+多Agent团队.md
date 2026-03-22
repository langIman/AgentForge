# Phase 3：并发 + 多Agent团队 (s08-s10)

> 从单Agent跃迁为多Agent协作系统。Lead Agent可以spawn Worker、发消息、广播、审批计划、优雅关闭Worker，同时支持后台任务不阻塞对话。

---

## 做了什么

用一句话概括：**在P2单Agent基础上，加入了后台任务管理、多Worker团队、消息通信总线、协议状态机，形成完整的多Agent协作系统。**

---

## 新增文件清单

```
src/background/
├── __init__.py
└── manager.py              # BackgroundManager（后台任务）

src/team/
├── __init__.py
├── mailbox.py              # InMemoryMailbox（消息总线）+ 工厂工具
├── manager.py              # TeammateManager（团队管理）
├── protocols.py            # ProtocolTracker（协议FSM）
└── worker_graph.py         # Worker专用图构建

src/tools/
├── background.py           # background_run, check_background
├── team.py                 # spawn_teammate, list_teammates, send_message, read_inbox, broadcast
└── protocol.py             # shutdown_request, plan_approval

tests/
├── test_background.py      # 9个测试
├── test_team.py            # 15个测试
└── test_protocols.py       # 12个测试
```

## 修改的文件

```
src/core/state.py           # 新增5个P3字段
src/core/nodes.py           # pre_process注入后台通知+收件箱；system prompt加团队指令
src/cli.py                  # 新增9个工具、团队状态、'team'/'bg'命令
```

---

## 架构总览

```
┌─────────────┐
│  Lead Agent  │ ← 用户通过CLI交互
│  (主图)      │
│  21个工具    │
└─────┬───────┘
      │ spawn_teammate / send_message / broadcast
      │ shutdown_request / plan_approval
      ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Worker 1   │  │  Worker 2   │  │  Worker N   │
│  (独立图)   │  │  (独立图)   │  │  (独立图)   │
│  6个工具    │  │  6个工具    │  │  6个工具    │
└─────┬───────┘  └─────┬───────┘  └─────┬───────┘
      │                │                │
      └────────────────┼────────────────┘
                       ▼
              ┌─────────────────┐
              │  InMemoryMailbox │  ← 消息总线
              │  ProtocolTracker │  ← 协议FSM
              └─────────────────┘
```

---

## 逐模块说明

### 1. 后台任务管理器 (`src/background/manager.py`)

**解决的问题**：Agent执行 `pytest` 等耗时命令时，整个对话被阻塞。

**方案**：`BackgroundManager` 用线程执行命令，立即返回 task_id。

```
用户: "后台运行测试"
Agent调用: background_run("pytest tests/ -v")
  → BackgroundManager.run() 启动线程
  → 立即返回 task_id = "a1b2c3d4"
  → Agent继续对话，不阻塞

... 测试跑完 ...

下一轮对话:
  → pre_process() 调用 drain_notifications()
  → 发现 a1b2c3d4 完成
  → 注入 <bg_notifications> 到消息中
  → Agent看到通知，汇报结果
```

| 方法 | 作用 |
|------|------|
| `run(command, timeout)` | 启动后台线程，返回task_id |
| `drain_notifications()` | 取出所有已完成通知（非阻塞） |
| `get_status(task_id)` | 查询单个任务状态 |
| `list_tasks()` | 列出所有任务 |

**为什么用线程不用asyncio**：当前CLI是同步的（`agent.invoke()`），线程自然融入。接口与asyncio版完全一致，升级只需换实现。

---

### 2. 消息总线 (`src/team/mailbox.py`)

**解决的问题**：多个Agent之间如何通信？

**方案**：`InMemoryMailbox`——每个Agent一个收件箱，线程安全。

| 方法 | 语义 |
|------|------|
| `send(sender, to, content)` | 投递到目标收件箱 |
| `read_inbox(name)` | 取走并清空（消费语义） |
| `peek_inbox(name)` | 查看但不消费 |
| `broadcast(sender, content, teammates)` | 群发（排除自己） |
| `has_messages(name)` | 是否有未读 |

**消费语义**：`read_inbox` 取走后消息就没了。这避免了重复处理。

**工厂工具**：Worker不能直接操作mailbox（会暴露全局状态），所以用工厂函数创建绑定工具：

```python
# 为worker1创建专属工具（sender自动绑定为worker1）
send_tool = make_send_tool("worker1", mailbox)
read_tool = make_read_inbox_tool("worker1", mailbox)
```

---

### 3. 协议FSM (`src/team/protocols.py`)

**解决的问题**：Agent之间的交互需要结构化，不能只靠自然语言。

**方案**：`ProtocolTracker`——每个请求有唯一ID，经过严格的状态流转。

```
创建请求 → pending → approved / rejected
                  （不可逆，不可重复处理）
```

**支持的协议类型**：

| 协议 | 场景 | 流程 |
|------|------|------|
| `shutdown` | Lead要求Worker退出 | Lead创建→发邮件→Worker读到→完成当前工作→退出 |
| `plan_approval` | Lead提计划给Worker | Lead创建→发计划→Worker审阅→approve/reject |

**为什么需要FSM而不是直接发消息**：
- **可追踪**：每个请求有ID，能查状态
- **不可重复处理**：防止Worker重复响应
- **结构化**：不依赖自然语言解析

---

### 4. Worker专用图 (`src/team/worker_graph.py`)

Worker与Lead共用 `build_graph()` 的图拓扑，但节点逻辑不同：

| 节点 | Lead | Worker |
|------|------|--------|
| pre_process | micro_compact + auto_compact + bg通知 + 收件箱 | micro_compact + 收件箱 + shutdown检测 |
| agent | 通用system prompt | 身份prompt（"你是worker1，角色：..."） |
| post_process | Nag机制 | 无（Worker不需要todo提醒） |

**工具集对比**：

| Lead（21个） | Worker（6个） |
|-------------|--------------|
| bash, read_file, write_file, edit_file | bash, read_file, write_file, edit_file |
| todo_write, spawn_subagent, load_skill | |
| compact, task_create/update/list/get | |
| background_run, check_background | |
| spawn_teammate, list_teammates, broadcast | |
| send_message, read_inbox | send_message, read_inbox |
| shutdown_request, plan_approval | |

Worker的 send_message / read_inbox 是通过工厂函数创建的**绑定版**，sender自动设为自己的名字。

---

### 5. 团队管理器 (`src/team/manager.py`)

**TeammateManager** 管理Worker的完整生命周期：

```
spawn(name, role, prompt)
  → 创建Worker专用工具集（绑定mailbox）
  → 创建Worker专用model（bind_tools）
  → 构建Worker专用图（build_worker_graph）
  → 启动独立线程执行 graph.invoke()
  → Worker完成后自动向Lead发送完成通知
```

**Worker线程的异常处理**：
- 正常完成：向Lead发送 `[任务完成] + 最后输出`
- 异常退出：向Lead发送 `[Worker异常] + 错误信息`
- 无论如何：状态设为 "idle"

---

### 6. 九个新工具 (`src/tools/`)

#### background.py（所有角色）

| 工具 | 功能 |
|------|------|
| `background_run(command, timeout)` | 启动后台命令 |
| `check_background(task_id)` | 查询后台任务状态 |

#### team.py（Lead角色）

| 工具 | 功能 |
|------|------|
| `spawn_teammate(name, role, prompt)` | 生成Worker |
| `list_teammates()` | 列出团队成员和状态 |
| `send_message(to, content)` | 向Worker发消息 |
| `read_inbox()` | 读取Lead收件箱 |
| `broadcast(content)` | 群发给所有Worker |

#### protocol.py（Lead角色）

| 工具 | 功能 |
|------|------|
| `shutdown_request(target, reason)` | 请求Worker优雅退出 |
| `plan_approval(target, plan)` | 向Worker发送计划请求审批 |

---

### 7. 节点更新 (`src/core/nodes.py`)

**pre_process新增两段注入逻辑**（在压缩之后）：

```python
# Phase 3: 注入后台任务通知
if bg_manager:
    notifications = bg_manager.drain_notifications()
    if notifications:
        → 注入 <bg_notifications>...</bg_notifications>

# Phase 3: 注入Lead收件箱消息
if mailbox:
    inbox = mailbox.read_inbox(agent_name)
    if inbox:
        → 注入 <inbox>...</inbox>
```

**system prompt新增团队管理指令**：当 `has_team=True` 时，提示Agent可以使用团队管理工具。

**向后兼容**：bg_manager和mailbox都是可选参数，P1/P2代码传None即可。

---

### 8. State扩展

```python
class AgentState(TypedDict):
    # Phase 1 (不变)
    messages, session_id, todos, rounds_since_todo
    # Phase 2 (不变)
    token_count, compressed, tasks_snapshot
    # Phase 3 (新增)
    bg_notifications: list[str]    # 后台任务通知
    inbox_messages: list[dict]     # 收件箱消息
    agent_name: str                # Agent名称（lead / worker名）
    agent_role: str                # 角色描述
    team_name: str                 # 团队名称
```

---

## 关键设计决策

### 为什么用线程而不是asyncio？

当前CLI是同步的（`agent.invoke()` + `input()`）。asyncio需要整个调用链都是async，改动太大。线程自然融入sync代码，且接口与async版完全一致：

```python
# 线程版                        # asyncio版（未来升级）
bg_manager.run(cmd)             await bg_manager.run(cmd)
bg_manager.drain_notifications() await bg_manager.drain_notifications()
```

方法签名相同，替换实现不影响调用方。

### 为什么Worker在独立线程里跑完整图？

每个Worker需要独立的消息历史和工具绑定。放在线程里意味着：
- Worker的 `graph.invoke()` 完全独立
- Worker的状态（messages）不会污染Lead
- 多个Worker真正并行执行

### 为什么Worker只有6个工具？

**最小权限原则**。Worker不能：
- 管理其他Worker（只有Lead能spawn/shutdown）
- 操作todo/task系统（由Lead统筹）
- 加载技能（由Lead决定策略）
- 启动后台任务（避免嵌套复杂度）

Worker只能：做事（bash/file）+ 通信（send/read）。

### 消息注入为什么在pre_process而不是post_process？

pre_process在agent（LLM调用）之前执行。注入在这里意味着LLM能在当前轮次就看到新消息和通知。如果放在post_process，要等到下一轮才能看到。

---

## 典型交互流程

### 后台任务

```
You> 在后台运行测试，同时帮我review代码
Agent> [调用 background_run("pytest tests/ -v")]
       后台任务 a1b2c3d4 已启动。我来review代码...
       [执行代码审查...]

... 数轮后，测试跑完 ...

Agent> (pre_process注入通知)
       收到后台通知：测试全部通过（94 passed）。
       代码审查结果如下：...
```

### 多Agent协作

```
You> 帮我重构认证模块，分两个人做：一个改后端，一个改前端
Agent> [调用 spawn_teammate("backend", "后端开发", "重构认证API...")]
       [调用 spawn_teammate("frontend", "前端开发", "更新登录页面...")]

       已创建2个Worker。

... Worker在后台独立执行 ...

Agent> (pre_process注入inbox)
       收到 backend 的消息：[任务完成] API重构完毕，新增了JWT验证。
       收到 frontend 的消息：[任务完成] 登录页面已更新。

       两个任务都完成了！
```

### 协议交互

```
You> 让backend先停下来
Agent> [调用 shutdown_request("backend", "需要先review代码")]
       已发送关闭请求给 backend。

... backend完成当前工作，汇报后退出 ...
```

---

## 测试覆盖

94个测试全部通过，P3新增36个：

| 测试文件 | 数量 | 覆盖内容 |
|----------|------|----------|
| `test_background.py` | 9 | 非阻塞执行、通知队列、超时、状态查询 |
| `test_team.py` | 15 | 消息收发、消费语义、广播、工厂工具、团队管理、重复spawn |
| `test_protocols.py` | 12 | 创建/批准/拒绝、重复处理拦截、按目标过滤、FSM状态流转、时间戳 |

---

## P3验证清单

- [x] `background_run("sleep 2 && echo done")` 立即返回，不阻塞
- [x] 后台完成后通知注入下一轮对话（pre_process drain）
- [x] spawn_teammate成功，Worker在独立线程执行
- [x] send_message/read_inbox正常通信
- [x] broadcast群发正确（排除自己）
- [x] shutdown_request创建协议+发送邮件
- [x] 协议FSM状态转换正确（pending→approved/rejected，不可重复）
- [x] Worker工厂工具正确绑定agent名称
- [x] 94个测试全部通过
