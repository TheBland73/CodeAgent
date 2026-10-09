# CodeAgent 设计文档

> 配套文档：[README.md](README.md)（项目说明与使用方法）
> 文件名沿用作业提交要求中的写法 `Desgin.md`。

---

## 目录

- [1. 项目目标与范围](#1-项目目标与范围)
- [2. 整体架构](#2-整体架构)
- [3. 模块设计](#3-模块设计)
- [4. Agent 循环设计](#4-agent-循环设计)
- [5. 工具系统设计](#5-工具系统设计)
- [6. LLM 接入与 FIM 补全](#6-llm-接入与-fim-补全)
- [7. 可靠性与错误处理](#7-可靠性与错误处理)
- [8. 缓存设计](#8-缓存设计)
- [9. 安全设计（写盘四道闸门）](#9-安全设计写盘四道闸门)
- [10. 数据结构与对外接口](#10-数据结构与对外接口)
- [11. 关键设计取舍](#11-关键设计取舍)
- [12. 测试设计](#12-测试设计)
- [13. 局限与演进路线](#13-局限与演进路线)

---

## 1. 项目目标与范围

### 1.1 目标

做一个**简单但完整**的代码助手 Agent，把 Agent 开发的四大基础能力跑通并可演示：

1. **LLM 调用**：封装 chat（对话/工具调用）与 FIM（中间填充补全）两类接口；
2. **Prompt 设计**：System Prompt 约束行为边界、FIM Prompt 描述光标上下文；
3. **工具集成**：模型通过 Function Calling 自主选择并调用本地工具；
4. **Agent 循环**：多步「决策 → 调用工具 → 回填结果 → 再决策」，并带步数/改数上限。

在此之上补一件工程上真正重要的事：**模型可以改文件，但不能偷偷改文件**。
因此写入路径统一收敛为「展示 diff → 人工确认 → 备份 → 写盘 → 记日志」。

### 1.2 范围内（In Scope）

- CLI 交互（会话式 REPL，支持多轮上下文记忆）；
- 5 个注册给模型的工具：2 个只读（`search_code` / `read_file`）+ 3 个可写（`insert_at_cursor` / `apply_edit` / `write_file`）；
- FIM 直连补全命令 `/fim`，底层是第 6 个工具函数 `fim_assist`（**不注册给模型**，见 5.3）；
- 重试、降级、缓存、日志；
- 离线单元测试 + 手动验证脚本。

### 1.3 范围外（Out of Scope）

- 编辑器内联补全、VS Code 插件、IDE 集成；
- 大规模代码索引 / 向量检索；
- 流式输出与多候选建议；
- 沙箱隔离与工作目录白名单（**已知风险，见第 13 节**）；
- 多 Agent 协作、任务规划器（Plan-and-Execute）。

### 1.4 设计原则

| 原则 | 落地方式 |
|---|---|
| 错误不外抛 | 工具层所有异常转成 `[错误] …` 文本，回传给模型自行调整 |
| 写操作可回滚 | 覆盖前自动 `*.bak`，全过程写 JSONL 日志 |
| 决策与执行分离 | 模型只负责"想"，本地代码负责"做"，工具白名单由注册表决定 |
| 分层解耦 | LLM / 工具 / 循环 / UI / 配置各成模块，可分别替换与测试 |
| 默认安全 | 覆盖默认拒绝、替换要求唯一匹配、写盘默认需要人工确认 |

---

## 2. 整体架构

### 2.1 分层视图

```text
┌──────────────────────────────────────────────────────────┐
│  表现层  core/ui.py        rich 面板 / diff 着色 / y-n 确认  │
│          core/cli.py       会话 REPL、命令分发（含 /fim）     │
├──────────────────────────────────────────────────────────┤
│  编排层  core/agent.py     Agent 主循环、工具 Schema、注册表  │
├──────────────────────────────────────────────────────────┤
│  能力层  core/tools.py     search_code / read_file          │
│                            insert_at_cursor / apply_edit     │
│                            write_file / fim_assist           │
│          core/llm.py       call_chat / call_fim / _retry_call│
├──────────────────────────────────────────────────────────┤
│  基础层  core/cache.py     TTLCache（FIM 缓存、搜索缓存）      │
│          core/config.py    .env 读取与配置校验                │
│          core/prompts.py   FIM Prompt 模板                   │
└──────────────────────────────────────────────────────────┘
                            ↓
              本地文件系统 / ripgrep / DeepSeek API
```

依赖方向自上而下单向：`ui ← cli → agent → tools → llm → config`。
`ui` 与 `tools` 之间没有硬依赖——`tools.py` 只在需要确认时才 `from core import ui`
（函数内延迟导入），使工具层可以在无终端环境下被测试。

### 2.2 运行时序（两条路径）

**路径 A：Agent 循环（写入型任务）**

```text
用户输入任务
   │
   ▼
cli.main() 读取一行 → run_agent(task, messages)
   │
   ├─ messages.append({"role":"user", …})
   │
   ▼  ┌─────────────────── for step in 1..max_steps ───────────────────┐
      │ 1. _retry_call(client.chat.completions.create(tools=SCHEMA))   │
      │ 2. 空输出？        → 追加上下文提示，continue（不计为最终答案）  │
      │ 3. 参数非法 JSON？ → 追加上下文提示，continue                  │
      │ 4. 无 tool_calls？ → return msg.content（结束）                │
      │ 5. 写工具且 edits_done >= max_edits？ → 返回 [已阻止]，不执行   │
      │ 6. execute_tool(name, arguments) → 追加 role="tool" 消息       │
      └────────────────────────────────────────────────────────────────┘
   │
   ▼
cli 打印总结面板；messages 留在内存供下一轮复用（上下文记忆）
```

**路径 B：FIM 直连补全（`/fim 文件 行 列`）**

```text
handle_fim(args) → fim_assist(path, line, col)
    │
    ├─ 读文件，按 (line, col) 切成 prefix / suffix
    ├─ call_fim(prefix, suffix, max_tokens)   ← 命中缓存则直接返回
    ├─ 拼回全文 → _make_diff() 生成 unified diff
    └─ _write_with_confirm()：打印 diff → y/n → 备份 → 写盘 → 写日志
```

两条路径共用第 9 节的写入流程，因此安全语义完全一致。

### 2.3 关键设计模式

| 模式 | 位置 | 作用 |
|---|---|---|
| ReAct 式循环 | `core/agent.py::run_agent` | 推理与行动交替，直到模型不再要工具 |
| 注册表（Registry） | `core/agent.py::TOOL_REGISTRY` | 名字 → 函数映射，工具白名单即"能力边界" |
| 策略注入（Strategy） | `run_agent(system_prompt=…)` | 补全 Agent 与代码助手 Agent 共用同一循环 |
| 门面（Facade） | `core/llm.py::call_chat / call_fim` | 屏蔽 OpenAI SDK 细节，统一重试 |
| 装饰器式重试 | `core/llm.py::_retry_call` | 传 lambda，只对可重试异常退避 |
| 模板方法 | `core/tools.py::_write_with_confirm` | 固定"确认→备份→写盘→日志"骨架，五个工具复用 |
| 单例 | `core/config.py::settings`、`core/cache.py` 模块级缓存 | 配置与缓存全局共享 |

---

## 3. 模块设计

### 3.1 `main.py`（6 行）

唯一职责是入口：`from core.cli import main`，`__main__` 时调用。
保持极薄，方便换入口（未来接 Web 界面时只需换这一层）。

### 3.2 `core/config.py`

- 用 `Path(__file__).resolve().parent.parent / ".env"` **显式定位**项目根目录的 `.env`，
  因此不管从哪个工作目录启动，配置都能读到；
- `Settings` 类集中声明 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEFAULT_MODEL`；
- **启动即校验**：Key 为空直接 `raise ValueError`，避免带着空 Key 发出必然 401 的请求，
  把"配置错误"和"网络错误"区分开。

### 3.3 `core/llm.py`

三个职责：

1. **客户端构造**：`client`（`https://api.deepseek.com`）用于 chat/工具调用；
   `fim_client`（`https://api.deepseek.com/beta`）用于 FIM 补全——这是 DeepSeek 的 Beta 端点要求。
2. **能力封装**：
   - `call_chat(messages, model, stream, temperature) -> str`
   - `call_fim(prefix, suffix, model, max_tokens, temperature, use_cache) -> str`
3. **重试**：`_retry_call(fn, max_retries=3, base_delay=1.0)`，
   只捕获 `APIConnectionError / APITimeoutError / RateLimitError / InternalServerError`
   四类"重试有意义"的异常，退避为 `base_delay * 2^(attempt-1)`（1s → 2s → 4s）。

> 设计取舍：把可重试异常定义成模块级元组 `RETRYABLE_EXCEPTIONS`，
> 测试里可以直接替换成假异常，无需真的制造网络故障。

### 3.4 `core/cache.py`

`TTLCache`：字典 + `(value, timestamp)` 二元组，key 由所有影响结果的参数
`json.dumps(sort_keys=True)` 后取 sha256 前 16 位生成。

- `get()` 命中时校验 TTL，过期即删并记一次 miss；
- `set()` 超容量时按**写入时间**淘汰最早的一条（FIFO）；
- `stats()` 暴露 `hits / misses / size / hit_rate`，便于观察缓存效果。

两个模块级单例：

| 实例 | 容量 | TTL | 缓存 key |
|---|---|---|---|
| `fim_cache` | 128 | 600s | `(model, prefix, suffix, max_tokens, temperature)` |
| `search_cache` | 256 | 300s | `(query, path, max_results, file_glob, context_lines)` |

> **踩过的坑（已在代码注释中记录）**：最初曾只按 `prefix` 做 FIM 缓存键，
> 结果"同一个前缀、不同后缀"会命中同一条缓存，返回完全错误的补全。
> 现在 key 覆盖全部影响输出的参数，`test_unit_cache_retry.py::test_cache_key_includes_all_arguments` 专门守着这条。

### 3.5 `core/prompts.py`

只用 9 行做两件事：定义 FIM 的原始模板 `<｜fim▁begin｜>…<｜fim▁hole｜>…<｜fim▁end｜>`，
并提供 `build_fim_prompt(prefix, suffix)` 供调试/日志打印。
真实调用不需要手动拼模板——SDK 的 `prompt` / `suffix` 参数会由服务端组装。

### 3.6 `core/ui.py`

所有终端输出收口在这里（`rich` 的 `Console` / `Panel` / `Rule` / `Text`）：

- 会话级：`print_welcome` / `print_help` / `print_cleared` / `prompt_input`；
- 步骤级：`print_step` / `print_thinking` / `print_tool_call` / `print_tool_result` / `print_correction`；
- 结果级：`print_summary` / `print_error`；
- 写入级：`print_edit_header` / `print_diff`（逐行着色：`+` 绿、`-` 红、`@@` 青）/ `ask_confirm`。

好处：换主题、改语言、或未来换成 Web 输出，只动这一个文件。
`ask_confirm()` 对 `EOFError / KeyboardInterrupt` 一律返回 `False`（**默认不写盘**）。

### 3.7 `core/cli.py`

- `SYSTEM_PROMPT`：CLI 每次启动时生成会话兜底 System Prompt（约束"最多改 3 次"、"不要覆盖已存在文件"、"最终回答不要贴完整代码"、用中文回答），
  在 `core/cli.py::new_session()` 里放进 `messages[0]`；`core/agent.py::DEFAULT_SYSTEM_PROMPT` 是 `run_agent` 的直接调用者（如二次开发、脚本）不传 `system_prompt` 时的默认值，两者用途不同、不重复维护同一份文案；
- `HELP_TEXT`：面向用户的命令说明；
- `new_session()`：构造全新的 messages（`/clear` 复用同一函数）；
- `handle_fim(args)`：解析 `/fim 文件 行 列`，做参数校验后交给 `fim_assist`；
- `main()`：REPL 主循环。捕获 `EOFError / KeyboardInterrupt` 优雅退出；
  对 `run_agent` 整体包一层 `try/except`，**单轮失败不会终止会话**。

### 3.8 `core/agent.py`

见第 4、5 节。

---

## 4. Agent 循环设计

### 4.1 循环骨架

```python
for step in range(1, max_steps + 1):
    response = _retry_call(lambda: client.chat.completions.create(
        model=settings.DEFAULT_MODEL, messages=messages,
        tools=TOOLS_SCHEMA, temperature=temperature))

    msg = response.choices[0].message

    if not msg.content and not msg.tool_calls:      # 纠错 1：空输出
        messages += [assistant(""), user("上一次回复是空的，请继续…")]
        continue

    if msg.tool_calls and 有非法 JSON 参数:           # 纠错 2：参数格式
        messages += [assistant(content), user("参数不是合法 JSON，请重新调用…")]
        continue

    messages.append(assistant_msg)                   # 回填 assistant（含 tool_calls）
    if not msg.tool_calls:
        return msg.content or ""                     # 终止条件：模型不再要工具

    for tc in msg.tool_calls:                        # 执行工具并回填结果
        result = execute_tool(tc.function.name, tc.function.arguments)
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

return f"[已达最大步数 {max_steps}，强制停止]"
```

### 4.2 终止条件

| 条件 | 结果 |
|---|---|
| 模型返回纯文本、无 `tool_calls` | 正常结束，返回该文本 |
| 达到 `max_steps` | 返回 `[已达最大步数 N，强制停止]`，避免死循环与费用失控 |
| 达到 `max_edits` 后模型仍要写 | 写操作被替换为 `[已阻止] …` 文本，引导模型收尾 |

### 4.3 两道纠错

模型偶尔会"摆烂"（返回空）或给出坏 JSON。与其让循环直接抛异常，不如**把错误当成一次对话**：

- **空输出**：追加一条 user 消息点明问题，`continue` 让模型重来；
- **非法 JSON 参数**：先 `json.loads` 预检，找出坏掉的调用名，追加 user 消息要求重发。

这样做的好处：纠错本身也占用 `max_steps` 配额，不会无限重试；
且终端会打印 `⚠` 提示，便于观察模型行为。

### 4.4 上下文记忆

`messages` 是整个循环唯一的"记忆载体"：

- `run_agent(messages=None)` → 新建 `[system]`；
- `run_agent(messages=history)` → **就地追加**，实现多轮会话；
- 工具调用与结果都留在 `messages` 里，所以模型能记住"上一轮我看过哪个文件"；
- `/clear` 只是把 `messages` 换成一个新的 `[system]`。

> 取舍：`messages` 只存内存、不落盘，也没有 token 预算控制。
> 长会话会持续增长，需要用户主动 `/clear`。见第 13 节演进路线。

### 4.5 可观测性

每一步都打印：`Step i/max_steps`、思考耗时、每个工具调用的名字与参数预览、
每个工具结果的前 200 字符与耗时（毫秒）。既能当作演示画面，也是排查"模型为什么乱调工具"的主要手段。

辅助函数 `_preview(text, limit)` 负责截断，防止把超长文件内容打到终端。
`print_messages()` 保留为调试用（默认不调用）。

---

## 5. 工具系统设计

### 5.1 Schema 与实现的分离

- `TOOLS_SCHEMA`（`core/agent.py`）：给**模型**看的 JSON Schema，
  每个工具的 `description` 都写清楚了"什么时候用、参数什么含义、有什么坑"；
- `TOOL_REGISTRY`（`core/agent.py`）：给**程序**用的名字→函数映射；
- 实现在 `core/tools.py`。

这样"模型能调用的工具集合"是一个显式的白名单字典，加工具只需改两处（Schema + 注册表）。

### 5.2 统一执行入口

```python
def execute_tool(name: str, arguments: str) -> str:
    if name not in TOOL_REGISTRY:  return f"[错误] 未知工具: {name}"
    try:    args = json.loads(arguments)
    except json.JSONDecodeError as e:  return f"[错误] 参数不是合法 JSON: {e}"
    try:    return TOOL_REGISTRY[name](**args)
    except TypeError as e:  return f"[错误] 参数不匹配: {e}"
    except Exception as e:  return f"[错误] 工具 {name} 执行失败: {type(e).__name__}: {e}"
```

**保证：永不抛异常，永远返回字符串。** 这样循环不会因为某个工具炸掉而整体失败，
模型还能读到错误信息并自行纠正（例如把 `read_file("no_such.py")` 换成先 `search_code`）。

### 5.3 各工具实现要点

| 工具 | 要点 |
|---|---|
| `search_code` | 两条路径：① 用 `_find_rg()`（`shutil.which("rg")`）定位 ripgrep，命令带 `--line-number --no-heading --color=never --max-count`，超时 30s，退出码 0/1 都算正常（1=无匹配），结果同时按 `--max-count` 与 `max_results` 双层截断并标注"…（已截断）"；② **找不到 rg 时退化为内置纯 Python 搜索** `_python_search()`，输出格式与 rg 路径完全一致（`文件:行号:内容`，上下文行用 `-` 分隔），遍历时跳过 `.git`/`__pycache__`/`venv` 等目录，非法正则与路径不存在都返回可读错误。两条路径的结果共用同一份缓存语义 |
| `read_file` | 输出 `"%4d \| %s"` 形式**带行号**文本，模型才能准确说出"第几行"；支持 `start_line/end_line` 切片与 `max_lines=500` 上限，防止撑爆上下文；返回的错误信息都带上"共 N 行"这类可操作信息 |
| `insert_at_cursor` | 1-based 行列；行号允许取 `逻辑行数+1` 表示追加到文件末尾；插入时把行尾的 `\n`/`\r\n` 单独切出来，避免把插入内容拼到换行符后面；列号越界给出"该行长度为 L，有效列号 1..L+1" |
| `apply_edit` | `old_code` 用 `content.count()` 检查唯一性：0 次→未找到，>1 次→拒绝并建议扩大上下文；通过后才 `replace(..., 1)` |
| `write_file` | 已存在且 `overwrite=False` → 直接拒绝（默认安全）；新建时自动 `mkdir(parents=True)`；覆盖时读旧内容用于生成 diff |
| `fim_assist` | 把文件在光标处切成 prefix/suffix → 调 FIM → 拼回 → 走同一套确认流程；**不注册给模型**，只由 `/fim` 命令调用，避免模型用它绕过 Schema 约束 |

### 5.4 行号口径的一致性（一个真实修复）

`read_file` 展示给模型的行号来自 `content.splitlines()`（**逻辑行号**，末尾换行符不算一行），
而 `insert_at_cursor` 早期用 `content.splitlines(keepends=True)` 做边界判断。

对于以换行结尾的常见文件，后者会多算一行，直接后果是：
**模型想"在文件末尾追加一行"时，会收到"行号超出范围"的莫名错误**。

修复方式：统一按 `logical_count = len(content.splitlines())` 判定，并允许
`line == logical_count + 1` 走"追加到文件末尾"分支；`fim_assist` 采用同一口径。
回归测试见 `test/test_unit_tools.py::test_insert_at_cursor_can_append_at_eof`。

### 5.5 写操作的模板方法

```python
def _write_with_confirm(p, diff, skip_confirm) -> (bool, str):
    ui.print_edit_header(str(p))
    ui.print_diff(diff.rstrip())
    if skip_confirm:                      # 自动化/测试路径
        backup = _make_backup(p);  return True, f"备份: {backup}"
    if not ui.ask_confirm():              # 人工确认路径
        return False, "[已取消] 用户拒绝修改，文件未变"
    backup = _make_backup(p)
    return True, f"备份: {backup}" if backup else "（备份失败）"
```

三个写工具与 `fim_assist` 都调用它，因此"确认、备份、取消语义"只有一份实现。
`skip_confirm=True` 是给测试与自动化留的后门，CLI 永远不会传它。

---

## 6. LLM 接入与 FIM 补全

### 6.1 两类接口的差异

| | `call_chat` | `call_fim` |
|---|---|---|
| 端点 | `https://api.deepseek.com` | `https://api.deepseek.com/beta` |
| 输入 | `messages` 数组 | `prefix` + `suffix` 字符串 |
| 用途 | 工具调用/多步推理/回答 | 光标处补全中间代码 |
| 默认温度 | 1.0（CLI 传 0.2） | 0.2 |
| 缓存 | 无（对话天然不重复） | 有，key 含全部参数 |

### 6.2 为什么 FIM 要用 Beta 端点

DeepSeek 的 fill-in-the-middle 能力挂在 Beta 路径上，因此单独构造了 `fim_client`。
两个 client 共用同一个 API Key 与重试装饰器，改动局限在 `core/llm.py` 内部。

### 6.3 Prompt 设计

- **Agent 的 System Prompt**（`core/agent.py::DEFAULT_SYSTEM_PROMPT`）强调三件事：
  先说清工具能干什么、再规定"信息够就直接回答，不要再调工具"、最后划红线"不要编造工具结果里没有的内容"；
- **CLI 的 System Prompt**（`core/cli.py::SYSTEM_PROMPT`）额外给出**工具选择策略**：
  补全用 `insert_at_cursor`、修改用 `apply_edit`、新建用 `write_file`，
  并明确"最多改 3 次""最终回答不要贴完整代码"。这条"最多改 3 次"已由 `max_edits` 在代码层**真正强制**，
  Prompt 与实现保持一致，而不是只写在提示里。

---

## 7. 可靠性与错误处理

按"故障发生的位置"分四层处理：

| 层次 | 故障 | 处理策略 |
|---|---|---|
| 网络/服务端 | 连接失败、超时、限流、5xx | `_retry_call` 指数退避重试 3 次；最终失败则抛出，由 CLI 捕获并打印，会话继续 |
| 模型输出 | 空回复、`tool_calls` 参数非法 JSON | 追加纠错消息让模型重来（占步数配额，不会无限） |
| 工具执行 | 文件不存在、参数不匹配、超时、编码错误 | `execute_tool` 捕获全部异常→`[错误] …` 文本回传给模型 |
| 业务边界 | 行号/列号越界、`old_code` 不唯一、目标已存在、用户拒绝 | 返回**可操作**的拒绝理由（含"共 N 行""出现 M 次""有效范围 1..L+1"），让模型能自己改对 |

其他兜底：

- **日志失败不影响主流程**：`_log_edit` 整体包在 `try/except` 里，写日志失败静默忽略；
- **备份失败不阻塞写入**：`_make_backup` 失败返回 `None`，结果里明确写"（备份失败）"，用户可见；
- **配置错误早暴露**：缺 Key 直接启动失败，而不是发一次注定 401 的请求；
- **双上限防跑飞**：`max_steps=10` + `max_edits=3`；
- **Claude/Ctrl+C 安全退出**：`ask_confirm` 遇到中断按"拒绝"处理。

---

## 8. 缓存设计

### 8.1 为什么需要

两类操作天然重复：

- FIM 补全：同一个光标位置反复触发（用户来回试、编辑器触发多次）；
- 搜索：模型在同一个任务里反复搜同一个关键字。

### 8.2 设计要点

- **key 必须覆盖全部影响输出的参数**：FIM 是 `(model, prefix, suffix, max_tokens, temperature)`。
  这是本项目唯一一次真实"缓存正确性"事故的修复结果（见 3.4 节）；
- **TTL**：FIM 600s、搜索 300s。搜索 TTL 更短，因为文件可能被改了；
- **容量上限 + FIFO 淘汰**：避免长时间驻留导致内存无界增长；
- **命中可观测**：`search_code` / `call_fim` 命中时打印 `[缓存] …`，`stats()` 给出命中率；
- **可关闭**：`use_cache=False` 可绕过缓存，排查"是不是缓存把结果搞旧了"。

### 8.3 已知取舍

进程内内存缓存，退出即失效；没有跨进程共享，也没有基于文件 mtime 的失效策略。
对单机 CLI 场景够用。

---

## 9. 安全设计（写盘四道闸门）

模型能写文件是这类 Agent 的核心价值，也是最大风险。设计上按"纵深防御"处理：

```text
        ┌── 闸门 1：人工确认 ─────────────────────────────┐
模型提议 │  core/ui.py::ask_confirm()                      │
  写操作 │  先打印 diff，输 y 才继续；n / 回车 / Ctrl+C → 拒绝 │
        └─────────────────────────────────────────────────┘
        ┌── 闸门 2：自动备份 ─────────────────────────────┐
        │  core/tools.py::_make_backup() → 同目录 *.bak    │
        └─────────────────────────────────────────────────┘
        ┌── 闸门 3：唯一匹配 ─────────────────────────────┐
        │  apply_edit 要求 old_code 在文件中恰好出现 1 次   │
        └─────────────────────────────────────────────────┘
        ┌── 闸门 4：默认不覆盖 ───────────────────────────┐
        │  write_file 对已存在文件默认拒绝，需显式 overwrite │
        └─────────────────────────────────────────────────┘
```

补充机制：

- **改数上限**：`max_edits=3`，达到后写操作被替换为 `[已阻止] …`，模型只能收尾；
- **审计日志**：`.agent_log/edit.log`，JSON Lines，每条记录
  `ts / tool / file / old / new / result / backup`。
  `result` 取值 `success` / `rejected` / `write_error: …`——**被拒绝的尝试同样留痕**；
  单条 old/new 超过 2000 字符会被截断并标注 `...(+N 字符)`，防止单行爆长；
- **路径校验**：所有文件操作先判 `exists()` 与 `is_file()`，把"目录当文件写"这类错误挡在前面。

### 9.1 已知安全边界（务必知晓）

| 风险 | 现状 | 建议 |
|---|---|---|
| 工作目录白名单 | ❌ 未实现，工具可读写任意路径 | 只在专用项目目录内运行；不要把 Agent 指向系统目录 |
| `read_file` 的信息泄漏 | ❌ 无路径限制 | 不要在含密钥的目录里让模型自由探索 |
| 命令注入 | ✅ `search_code` 用 `subprocess.run([...])` 列表传参，不经过 shell | — |
| Key 泄漏 | ⚠️ `.env` 已 gitignore；若 Key 曾出现在聊天/截图里应吊销重发 | 见 README 第十一节 |

---

## 10. 数据结构与对外接口

### 10.1 messages（唯一的会话状态）

```python
{"role": "system",    "content": "..."}                        # 会话开始时一条
{"role": "user",      "content": "用户任务 / 纠错提示"}
{"role": "assistant", "content": "...", "tool_calls": [...]}    # 有工具调用时带 tool_calls
{"role": "tool",      "tool_call_id": "call_x", "content": "工具返回的字符串"}
```

### 10.2 关键函数签名

```python
# core/agent.py
def execute_tool(name: str, arguments: str) -> str
def run_agent(user_task: str,
              system_prompt: str = DEFAULT_SYSTEM_PROMPT,
              max_steps: int = 10,
              max_edits: int = 3,
              temperature: float = 0.3,
              verbose: bool = True,
              messages: list = None) -> str

# core/tools.py
def search_code(query: str, path: str = ".", max_results: int = 30,
                file_glob: Optional[str] = None, context_lines: int = 0,
                use_cache: bool = True) -> str
def read_file(path: str, start_line: Optional[int] = None,
              end_line: Optional[int] = None, max_lines: int = 500) -> str
def insert_at_cursor(path: str, line: int, col: int, text: str,
                     skip_confirm: bool = False) -> str
def apply_edit(path: str, old_code: str, new_code: str,
               skip_confirm: bool = False) -> str
def write_file(path: str, content: str, overwrite: bool = False,
               skip_confirm: bool = False) -> str
def fim_assist(path: str, line: int, col: int, max_tokens: int = 128,
               skip_confirm: bool = False) -> str

# core/llm.py
def call_chat(messages: list, model: str = None, stream: bool = False,
              temperature: float = 1.0) -> str
def call_fim(prefix: str, suffix: str, model: str = None, max_tokens: int = 128,
             temperature: float = 0.2, use_cache: bool = True) -> str
def _retry_call(fn, max_retries: int = 3, base_delay: float = 1.0)

# core/cache.py
class TTLCache:
    def __init__(self, max_size: int = 128, ttl: float = 600.0)
    def get(self, *args) -> Optional[Any]
    def set(self, value: Any, *args) -> None
    def stats(self) -> dict
    def clear(self) -> None
```

### 10.3 回调约定

所有工具**统一返回 `str`**，不返回结构化对象。原因是返回值会直接作为 `role="tool"` 的
`content` 送给模型，字符串是唯一无损的公共格式；状态靠前缀表达：

| 前缀 | 含义 |
|---|---|
| `[错误] …` | 执行失败（含原因与建议） |
| `[已取消] …` | 用户拒绝，文件未变 |
| `[已插入] / [已替换] / [已新建] / [已覆盖] / [已追加] / [FIM 补全]` | 写盘成功 |
| `[已阻止] …` | 达到 `max_edits`，未执行 |
| `[无结果] / [无补全]` | 正常但无内容 |

这个前缀约定同时被程序使用：`run_agent` 靠 `result.startswith("[已")` 判断一次写操作是否真正生效，
再累加 `edits_done`。

---

## 11. 关键设计取舍

| 决策 | 备选方案 | 为什么这么选 |
|---|---|---|
| 用原生 OpenAI SDK，不上 LangChain/AutoGen | 主流 Agent 框架 | 循环逻辑只有几十行，自己写反而**每一步都可控、可测、可演示**；框架会把 Agent 循环变成黑盒，不利于展示"我理解 Agent 是怎么跑的" |
| 工具结果统一用字符串 | 结构化 JSON | 与 `role="tool"` 消息格式天然契合；模型对带前缀的文本提示理解更稳 |
| 精确替换用"唯一匹配"而非行号 | 直接按行号改 | 行号会因前一次插入而漂移；唯一匹配虽要求模型给更多上下文，但**改错地方的概率极低** |
| 写盘必须人工确认 | 全自动写入 | 课程作业与真实使用场景都更看重"可控"；`skip_confirm` 保留给自动化 |
| 内存缓存而非磁盘缓存 | 落盘缓存 | CLI 单次会话生命周期短，落盘收益低、维护成本高（失效策略复杂） |
| FIM 不注册成模型工具 | 让模型自己调 FIM | FIM 是"一次调用出结果"的直连能力，让模型去调会绕开 Schema 约束与列号校验；改为 `/fim` 显式命令，语义清晰 |
| `messages` 只存内存不落盘 | 会话持久化 | 避免隐私/密钥写进磁盘；代价是退出即失去上下文（已在限制中说明） |
| 错误以文本回传而非抛出 | 抛异常中断 | Agent 的价值在于"能自己纠错再试"，抛出会让一次小失误毁掉整个任务 |

---

## 12. 测试设计

### 12.1 测试分层

测试分两层，**自动收集只跑离线的那一层**（配置见 `pyproject.toml` 的 `[tool.pytest.ini_options]`）：

| 层次 | 文件 | 是否联网 | 内容 |
|---|---|---|---|
| 离线单元测试 | `test/test_unit_tools.py` | 否 | 带行号读取、行内/末尾插入、越界拒绝、`old_code` 唯一性、备份生成、默认拒绝覆盖 |
| 离线单元测试 | `test/test_unit_agent.py` | 否 | 用**假 LLM 响应**驱动循环：多步调用、空输出纠正、`max_steps` 截断、`max_edits` 拦截写操作（只读放行）、`execute_tool` 永不抛异常 |
| 离线单元测试 | `test/test_unit_cache_retry.py` | 否 | 缓存命中/未命中、参数不同不串味、TTL 过期、容量淘汰、重试成功/耗尽/不可重试异常不重试 |
| 离线单元测试 | `test/test_unit_fim.py` | 否 | 把 `core.llm.call_fim` 换成桩：prefix/suffix 切分是否正确、多行补全的换行对齐、空补全不改文件、位置越界拒绝、接口异常降级、用户拒绝时不落盘 |
| 离线单元测试 | `test/test_unit_search_fallback.py` | 否 | 把 `core.tools._find_rg` 桩成 `None`，强制走内置搜索：命中与 `文件:行号:内容` 格式、行号正确、跳过 `__pycache__` 等目录、`*.txt` 包含过滤与 `!*.txt` 排除过滤、上下文行用 `-`、单文件截断、非法正则与路径不存在的可读报错、单文件路径搜索 |
| 手动验证脚本 | `scripts/manual/*.py` | 是 / 需交互 | 直连 API 的真实演示（`test_api.py`、`test_fim.py`、`test_cache.py`）、工具边界用例（`test_apply_edit.py`、`test_insert.py`、`test_diff.py`）、确认与日志（`test_confirm.py`、`test_log.py`） |

当前规模：**48 个用例，全部离线，单次运行不到 1 秒**（实测 `python -m pytest -q` → `48 passed`；
分布：工具层 13、搜索兜底 12、Agent 循环 7、缓存与重试 8、FIM 补全 8）。

关键测试技巧：

- **假 LLM**：`_StubClient` 直接替换 `core.agent.client`，用脚本化响应驱动循环，
  从而在不发请求的前提下验证所有分支（含异常分支）；
- **时间伪造**：TTL 测试里把 `core.cache.time.time` 换成 `lambda: real() + 11`，
  不必真的 `sleep` 10 分钟；
- **能力伪造**：搜索兜底测试把 `core.tools._find_rg` 换成 `lambda: None`，
  不依赖本机是否装了 ripgrep，也不靠改 `PATH`；
- **不污染仓库**：所有文件操作都在 pytest 的 `tmp_path` 里进行；
- **命名隔离**：离线测试统一叫 `test_unit_*.py`，手动脚本叫 `test_*.py`，
  前者被自动收集，后者不会被误跑（否则 `pytest` 一执行就会打网络请求）。

`conftest.py` 承担四件事：

1. 把仓库根目录加入 `sys.path`，因此在任何工作目录下执行 `python -m pytest` 都能正确 `import core`；
2. **在 `import core.*` 之前注入占位 API Key**，见 12.3；
3. 把 `core.tools` 的写盘日志重定向到 `_pytest-tmp/.agent-log/`，测试不会在仓库的
   `.agent_log/` 里留下记录（日志是运行产物，不该由测试产生）；
4. 把 pytest 的 `basetemp` 钉在仓库内的 `_pytest-tmp/basetemp`。某些环境下子进程解析出的
   系统临时目录不可写，pytest 会退回"当前目录/pytest-of-<用户名>"，在项目里留下一堆垃圾。
   （`basetemp` 不是 `pyproject.toml` 的合法选项，所以只能写在 `pytest_configure` 钩子里。）

### 12.2 持续集成

`.github/workflows/test.yml` 在每次 push / PR 到 main 时运行，矩阵为
`ubuntu-latest` / `windows-latest` × Python `3.11` / `3.12` / `3.13`，共 6 个 job，各自独立的"干净机器"：

1. 先 `apt-get install ripgrep`（Linux）或 `choco install ripgrep`（Windows）把 ripgrep 装上，
   跑一遍 `python -m pytest -q` —— 验证**搜索主路径**；
2. 再设 `CODEAGENT_FORCE_PYTHON_SEARCH=1` 跑第二遍 —— 验证**没有 ripgrep 时的兜底路径**。

两条都设 `PYTHONIOENCODING=utf-8`，避免 Windows runner 上中文输出被本地编码干扰。
CI 全程**不注入真实 API Key**：所有用例都不发网络请求。
真正需要 Key 的只有 `core/config.py` 在导入时的"存在性校验"，
所以由 `conftest.py` 补一个假值（`sk-test-placeholder-not-a-real-key`）让它通过，见 12.3。
这个工作流的意义在于，它把"在我机器上能跑"变成"在一台什么都不装的机器上也能跑"——
最初的两次失败正好各暴露了一个隐藏依赖：第一次是 GitHub runner 默认不带 ripgrep
（只有 macOS 自带），暴露出 `search_code` 对系统命令的硬依赖，才有了兜底实现；
第二次是本地工作区里躺着一个 `.env` 掩盖了"导入即抛异常"的问题，才有了占位 Key。

### 12.3 为什么需要占位 API Key

`core/config.py` 在**模块导入时**就校验 `DEEPSEEK_API_KEY`，没有就直接抛 `ValueError`。
这是"尽早失败"的设计——用户漏配 `.env` 时立刻得到明确提示，而不是等到第一次请求才报 401。
但它在 CI 里撞出一个问题：**仓库里没有 `.env`**（本来就被 `.gitignore` 排除），
于是 `core.llm → core.config` 这条导入链一碰就炸，
`test_unit_agent.py` / `test_unit_cache_retry.py` / `test_unit_fim.py`
在**收集阶段**就报错，整轮 pytest 以退出码 2 中断。

本机之所以一直绿，纯粹因为工作区里躺着一个有效的 `.env`——
**测试结果依赖了"跑测试的机器上恰好有什么文件"，这是最隐蔽的一类环境依赖。**

解决办法是在 `conftest.py` 里、`import core.*` **之前**注入占位值：

```python
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-placeholder-not-a-real-key")
```

三个设计要点：

- **用 `setdefault` 而不是直接赋值**：本地有真实 `.env` 时不会被覆盖，开发时仍能用真 Key 跑；
- **只能是占位值**：任何真实 Key 都不许进版本库，自然也不许进 CI；
- **它只骗过"存在性校验"**：所有用例都不发请求，所以假 Key 不会导致任何网络失败。

配套的边界要划清：**离线测试不需要真实 Key；`python main.py` 与 `/fim` 必须配真 Key。**
把假 Key 换成真 Key 的步骤见 README 第四节。

---

## 13. 局限与演进路线

### 13.1 当前局限

1. **无路径白名单**：工具可读写任意本地路径，是第一优先级的安全缺口；
2. **无 token 预算**：会话变长后可能超出模型上下文，只能靠 `/clear`；
3. **无流式输出**：`call_chat(stream=True)` 只是占位（会返回一句提示），长回答要等完整返回；
4. **缓存不落盘**：进程重启即失效；
5. **单轮改数偏少**：`max_edits=3` 对"大改造"任务可能不够，需要用户重发任务；
6. **无并发**：工具串行执行；模型一次给多个工具调用时也是一个一个跑；
7. **FIM 补全无语法校验**：补出来的代码语法是否正确、缩进风格是否匹配，目前完全依赖模型输出质量；
8. **内置搜索不如 ripgrep**：兜底路径没有正则引擎优化、没有 `.gitignore` 感知，
   大仓库下明显更慢，只适合中小项目（装上 `rg` 即走主路径）。

### 13.2 演进路线（与 `IncreaseDevelop.md` 对齐）

| 优先级 | 事项 | 预期改动位置 |
|---|---|---|
| P0 | 工作目录白名单 / `--root` 参数 | `core/tools.py` 增加路径校验装饰器 |
| P0 | 改动后自动跑语法检查（`ast.parse` 或 `compileall`），失败则不落盘 | `core/tools.py::_write_with_confirm` 前置校验 |
| P1 | token 预算与自动摘要（超阈值时压缩最早的对话） | `core/agent.py::run_agent` |
| P1 | 流式输出 + 多候选补全 | `core/llm.py`、`core/ui.py` |
| P1 | `--yes` 非交互模式，便于脚本/CI 批量使用 | `core/cli.py`、`core/tools.py` |
| P2 | 会话持久化（可选、且不落 Key） | `core/cli.py` |
| P2 | 增加"跑测试"工具，形成 改 → 验 → 修 闭环 | `core/tools.py` + `TOOLS_SCHEMA` |
| P3 | VS Code 插件 / 编辑器内联补全、大规模索引 | 新增独立模块（当前架构已把 UI 与核心解耦，可平滑接入） |
