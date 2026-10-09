# CodeAgent —— CLI 代码生成/补全 Agent

> 一个基于 **DeepSeek** 的代码生成 / 代码修改 Agent：它会自己决定去读哪些文件、搜哪些关键字，
> 信息够了再动手改代码。**每一次写盘前都会先给你看 diff，你点 `y` 才落盘，并且自动留备份与日志。**

[![tests](https://github.com/TheBland73/CodeAgent/workflows/tests/badge.svg)](https://github.com/TheBland73/CodeAgent/actions/workflows/test.yml)

作者：TheBland ｜ 语言：Python 3.9+ ｜ 交互方式：命令行（CLI）

---

## 目录

- [一、这个项目能做什么](#一这个项目能做什么)
- [二、环境准备](#二环境准备)
- [三、安装](#三安装)
- [四、配置 API Key](#四配置-api-key)
- [五、使用方法](#五使用方法)
- [六、命令与参数速查](#六命令与参数速查)
- [七、项目结构](#七项目结构)
- [八、工具清单](#八工具清单)
- [九、安全机制](#九安全机制)
- [十、测试](#十测试)
- [十一、常见问题排查](#十一常见问题排查)
- [十二、已知限制](#十二已知限制)
- [十三、后续可扩展方向](#十三后续可扩展方向)

---

## 一、这个项目能做什么

它把「代码补全」拆成两条路径，两条都真实可用：

### 路径 A：Agent 循环（会自主调查、自主决策）

```text
用户任务 → LLM 决策 → 调用工具（search_code / read_file）→ 结果回填 → LLM 再决策 → … → 修改文件
```

模型不是"一次生成就结束"，而是可以多步推理：先搜函数定义、再读文件确认、最后才动笔。
支持 5 个工具（2 个只读 + 3 个可写），一次任务最多 10 步、最多改 3 次，防止跑飞。

### 路径 B：FIM 直连补全（不走 Agent，一次调用出结果）

`/fim <文件> <行> <列>` 会把文件在光标处切成 **前文 / 后文**，交给 DeepSeek 的
FIM（fill-in-the-middle）接口补中间那段，再把候选代码插回文件。

两条路径共用同一套「确认 → 备份 → 写盘 → 记日志」的落地流程。

### 能力清单

| 能力 | 说明 |
|---|---|
| Agent 循环 | 多轮工具调用与结果回填（`core/agent.py`） |
| 工具集成 | 5 个工具，Function Calling 驱动（`core/tools.py`） |
| 上下文记忆 | 会话级 `messages` 数组，`/clear` 可重置（`core/cli.py`） |
| 错误处理 | 网络异常指数退避重试、工具异常转文本、空输出/非法 JSON 自动纠正 |
| 结果缓存 | FIM 与搜索结果带 TTL + 容量上限的内存缓存（`core/cache.py`） |
| 可审计 | 每次写盘留 `.bak` 备份 + `.agent_log/edit.log` JSONL 日志 |
| 人机确认 | 写盘前打印 diff，`y` 才执行（`core/ui.py`） |

---

## 二、环境准备

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.9 及以上 | 开发环境实测 3.12 / 3.13，CI 覆盖 3.11 / 3.12 / 3.13 |
| ripgrep (`rg`) | 任意较新版本 | **可选**：装上搜索更快更准，没装会自动改用内置搜索 |
| DeepSeek API Key | — | 在 <https://platform.deepseek.com/> 申请 |

安装 ripgrep（可选）：

```powershell
# Windows
winget install BurntSushi.ripgrep.MSVC
# macOS
brew install ripgrep
# Debian/Ubuntu
sudo apt install ripgrep
```

> **没装 `rg` 也能正常用**：`search_code` 会退回到内置的纯 Python 搜索，输出格式与 ripgrep 完全一致
> （`文件:行号:内容`），只是跳过 `.git`、`__pycache__`、`venv` 等目录以保速度。
> 想强制走内置搜索来验证这条路径，设置环境变量 `CODEAGENT_FORCE_PYTHON_SEARCH=1` 即可。

---

## 三、安装

```powershell
# 1) 进入项目目录
cd CodeAgent

# 2) 创建并激活虚拟环境
python -m venv venv2
.\venv2\Scripts\Activate.ps1        # Windows PowerShell
# source venv2/bin/activate          # macOS / Linux

# 3) 安装依赖（三种方式任选其一）
pip install -r requirements.txt      # 方式一：按锁定版本装运行依赖，最可复现
pip install -e .                     # 方式二：以可编辑包安装，会注册 codeagent 命令
pip install -e ".[dev]"              # 方式三：顺带装上 pytest，方便跑测试
```

方式二安装后会多出一个命令 `codeagent`，等价于 `python main.py`。

> 如果 `pip` 下载很慢或卡住，改用国内镜像（pytest 等小包也一起走镜像）：
>
> ```powershell
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> pip install -r requirements-dev.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

---

## 四、配置 API Key

项目从**项目根目录的 `.env`** 读取 Key（`core/config.py` 里写死了这个路径，不用管当前工作目录）。

```powershell
# 复制模板
Copy-Item .env.example .env

# 编辑 .env，填入你自己的 Key
# DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

`.env.example` 内容：

```ini
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
```

---

## 五、使用方法

### 5.1 启动

在项目根目录执行：

```powershell
.\venv2\Scripts\Activate.ps1
python main.py
```

看到欢迎面板即启动成功：

```text
╭──────────────────────────────╮
│ Code Agent by TheBland       │
│ 输入 /help 查看帮助，/exit 退出 │
╰──────────────────────────────╯

>
```

### 5.2 场景 1：Agent 自主调查后回答问题

```text
> core/tools.py 里 search_code 用哪个函数定位 ripgrep？在第几行？

  ── Step 1/10 ──────────────────────────
  · 思考耗时 2.31s
  → search_code({"query": "ripgrep"})
  ✓ search_code (12ms)
    core\tools.py:29:def _find_rg() -> Optional[str]:
  ── Step 2/10 ──────────────────────────
  · 无工具调用，输出最终答案

  ╭─ 总结 ─────────────────────────────╮
  │ 用 _find_rg()，定义在 core/tools.py:29 │
  ╰────────────────────────────────────╯
```

### 5.3 场景 2：补全一段没写完的代码（会先给你看 diff）

先准备一个待补全的文件 `demo.py`：

```python
def add(a, b):
    result = 
    return result
```

然后：

```text
> 补全 demo.py 第 2 行 result 的赋值

  ── Step 1/10 ──────────────────────────
  → read_file({"path": "demo.py"})
  ✓ read_file (3ms)
     1 | def add(a, b):
     2 |     result = 
     3 |     return result
  ── Step 2/10 ──────────────────────────
  → insert_at_cursor({"path": "demo.py", "line": 2, "col": 14, "text": "a + b"})

即将修改 demo.py
--- a/demo.py
+++ b/demo.py
@@ -1,3 +1,3 @@
 def add(a, b):
-    result = 
+    result = a + b
     return result
确认修改？ (y/n) y
  ✓ insert_at_cursor (5ms)
    [已插入] demo.py 第 2 行第 14 列（+1 -0）
    备份: demo.py.bak
```

**只有输入 `y` 才会写盘**；输入 `n` 或直接回车都会取消，文件一个字节都不动，但这次「拒绝」也会记进日志。

### 5.4 场景 3：FIM 直连补全（不经过 Agent 决策）

```text
> /fim demo.py 2 14
· FIM 补全中: demo.py (2:14)
即将修改 demo.py
--- a/demo.py ...
确认修改？ (y/n) y
```

等价于"把光标放在第 2 行第 14 列，让模型根据前文 `def add(a, b):\n    result = ` 和后文
`\n    return result` 补出中间那句"。

- 行号 / 列号都从 **1** 开始，列号表示"插到该行第几个字符之前"；
- 行号可以填 **行数+1**，表示追加到文件末尾；
- 首次调用会走网络，第二次相同的前文/后文/参数会**命中缓存**（终端会打印 `[缓存] FIM 命中 (prefix=…, suffix=…)`）。

### 5.5 场景 4：修改已有代码（精确替换）

```text
> 把 demo.py 里的 a - b 改成 a + b
```

模型会调用 `apply_edit`。它有一条硬规则：`old_code` 必须在文件中**唯一出现**——
出现 0 次会说"未找到"，出现多次会要求模型**带上更多上下文重试**，因此不会改错地方。

### 5.6 场景 5：从零创建新文件

```text
> 写一个解析 CSV 并统计每列空值数量的脚本 stats.py
```

模型确认文件不存在后调用 `write_file` 创建。若文件已存在，默认**拒绝覆盖**，必须显式带
`overwrite=true` 才允许（覆盖前照例备份）。

### 5.7 会话命令

```text
> /help      查看帮助
> /clear     清空对话历史（工具调用记录也会清掉，回到干净会话）
> /exit      退出（exit、quit 同样有效）
```

### 5.8 在代码里调用（二次开发）

```python
from core.agent import run_agent

answer = run_agent(
    user_task="core/tools.py 里 read_file 最多读多少行？",
    max_steps=8,      # 最多几步
    max_edits=3,      # 最多写盘几次
    verbose=True,
)
print(answer)
```

`run_agent(..., messages=history)` 传入同一个 `messages` 列表即可实现多轮会话。

---

## 六、命令与参数速查

### CLI 命令

| 命令 | 作用 |
|---|---|
| 任意自然语言 | 交给 Agent 处理（可读可写） |
| `/fim <文件> <行> <列>` | FIM 直连补全并插入 |
| `/clear` | 清空对话历史 |
| `/help` | 显示帮助 |
| `/exit`、`exit`、`quit` | 退出 |

### 关键参数

| 位置 | 参数 | 默认值 | 说明 |
|---|---|---|---|
| `run_agent` | `max_steps` | 10 | Agent 循环步数上限 |
| `run_agent` | `max_edits` | 3 | 单任务写盘次数上限 |
| `run_agent` | `temperature` | 0.3（CLI 用 0.2） | 采样温度 |
| `call_fim` | `max_tokens` | 128 | 补全长度上限 |
| `call_fim` | `temperature` | 0.2 | 补全温度 |
| `call_fim` | `use_cache` | `True` | 是否用 FIM 缓存 |
| `TTLCache` | `max_size` / `ttl` | FIM 128/600s，搜索 256/300s | 缓存容量与存活时间 |
| `_retry_call` | `max_retries` / `base_delay` | 3 / 1.0s | 重试次数与首次退避 |

---

## 七、项目结构

```text
CodeAgent/
├── main.py                 # 入口：调用 core.cli.main
├── conftest.py             # pytest 配置：路径、日志隔离、临时目录固定
├── pyproject.toml          # 打包与依赖声明、pytest 配置、codeagent 命令
├── requirements.txt        # 锁定版本的运行依赖清单（含间接依赖）
├── requirements-dev.txt    # 测试依赖（pytest）
├── .env.example            # API Key 配置模板
├── .gitignore              # 已忽略 .env / venv2 / .agent_log / *.bak / _pytest-tmp
├── .gitattributes          # 统一按 LF 入库，避免跨平台换行噪音
├── LICENSE                 # MIT
├── IncreaseDevelop.md      # 后续可扩展方向
├── README.md               # 本文档：安装、使用、工具与排查
├── Desgin.md               # 设计文档：架构、模块、取舍、局限
│
├── .github/workflows/
│   └── test.yml            # CI：6 个环境 × 有/无 ripgrep 两条路径
│
├── core/                   # 核心代码
│   ├── cli.py              # 交互式 REPL：会话、命令分发、/fim
│   ├── agent.py            # Agent 主循环 + 工具 Schema + 工具注册表
│   ├── tools.py            # 5 个工具的实现（diff/备份/日志都在这）
│   ├── llm.py              # DeepSeek 客户端、call_chat / call_fim、重试
│   ├── cache.py            # 带 TTL 与容量上限的内存缓存
│   ├── config.py           # 读取 .env，集中管理配置
│   ├── prompts.py          # FIM Prompt 模板（调试参考）
│   └── ui.py               # 终端 UI（rich 面板、diff 着色、y/n 确认）
│
├── test/                   # 自动化测试（会被 pytest 收集、被 CI 执行）
│   ├── test_unit_tools.py            # 离线单测：工具层
│   ├── test_unit_search_fallback.py  # 离线单测：无 ripgrep 时的内置搜索
│   ├── test_unit_agent.py            # 离线单测：Agent 循环（假 LLM）
│   ├── test_unit_cache_retry.py      # 离线单测：缓存与重试
│   └── test_unit_fim.py              # 离线单测：FIM 补全（桩掉接口）
│
└── scripts/manual/         # 人工观察用的脚本，不参与自动收集（见该目录 README）
    ├── test_tools.py / test_api.py / test_retry.py       # 只读或轻量
    ├── test_agent.py / test_fim.py / test_cache.py       # 真实调用 API
    ├── test_insert.py / test_apply_edit.py / test_diff.py # 会改文件，要 y/n 确认
    ├── test_confirm.py / test_log.py / check_insert.py
    └── sample.py / utils.py / README.md
```

> 运行时会自动生成这些文件，都已被 `.gitignore` 忽略：
> `.agent_log/edit.log`（写盘日志）、`*.bak`（备份）、`__pycache__/`。

---

## 八、工具清单

| 工具 | 读/写 | 参数 | 说明 |
|---|---|---|---|
| `search_code` | 只读 | `query`, `path`, `file_glob`, `max_results` | 优先用 ripgrep，没装则用内置搜索；返回 `文件:行号:内容`（`max_results` 为**单文件**上限） |
| `read_file` | 只读 | `path`, `start_line`, `end_line` | 返回**带行号**的内容，单次最多 500 行 |
| `insert_at_cursor` | 写 | `path`, `line`, `col`, `text` | 光标处插入（补全场景）；`line = 行数+1` 为追加到末尾 |
| `apply_edit` | 写 | `path`, `old_code`, `new_code` | 精确替换，要求 `old_code` 唯一匹配 |
| `write_file` | 写 | `path`, `content`, `overwrite` | 新建或覆盖（默认拒绝覆盖） |

工具 Schema 定义在 `core/agent.py`，实现与注册表分别在 `core/tools.py` 和 `TOOL_REGISTRY`。

---

## 九、安全机制

这是本项目与"让模型直接写文件"最大的区别，四道闸门：

1. **人机确认**：所有写操作先把 diff 打给你看，输 `y` 才继续；`n` / 回车 → 取消（`core/ui.py::ask_confirm`）。
2. **自动备份**：覆盖已有文件前先存 `xxx.py.bak`，随时可回滚（`core/tools.py::_make_backup`）。
3. **唯一匹配**：`apply_edit` 要求 `old_code` 唯一，避免"想改 A 结果改了 B"。
4. **默认不覆盖**：`write_file` 对已存在的文件默认拒绝，必须显式 `overwrite=True`。

额外还有：

- **步数与改数双上限**：`max_steps=10`、`max_edits=3`，避免模型反复改坏文件；
- **可审计日志**：每次尝试（含被拒绝的）都写进 `.agent_log/edit.log`，JSON Lines 格式，便于回溯；
- **错误不外抛**：工具异常统一转成 `[错误] …` 文本回传模型，Agent 不会因为一次工具失败就崩。

> ⚠️ 注意：确认机制保护的是 **写** 操作。`read_file` 可以读取本机任意路径的文件，
> 因此在不受信任的目录里跑、或让模型处理来路不明的文件时，请自行评估风险。
> 建议在专用项目目录内使用，不要让 Agent 在系统目录里工作。

---

## 十、测试

### 10.1 离线单元测试（推荐，不需要 API Key）

```powershell
.\venv2\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # 或：pip install -e ".[dev]"
python -m pytest                      # 配置见 pyproject.toml 的 [tool.pytest.ini_options]
```

预期输出（48 个用例全部通过，全程不联网、不消耗 token）：

```text
................................................                 [100%]
48 passed in 0.7s
```

覆盖内容：

- **工具层**：带行号读取、行内/行尾插入、`old_code` 不唯一与未找到、备份生成、默认拒绝覆盖；
- **搜索**：ripgrep 路径的命中与无结果；没装 `rg` 时内置搜索的命中、行号与 `文件:行号:内容` 格式、
  文件过滤（含 `!` 排除）、上下文行、单文件截断、非法正则与路径不存在的可读报错；
- **Agent 循环**：用假 LLM 响应验证多步调用、空输出纠正、非法 JSON 纠正、`max_steps` 与 `max_edits` 拦截、工具异常不外抛；
- **FIM 补全**：prefix/suffix 切分是否正确、多行补全的换行对齐、用户拒绝时不落盘、接口异常时的降级提示；
- **缓存与重试**：缓存命中/未命中、参数不同不串味、TTL 过期、容量淘汰，以及重试成功/耗尽/不可重试异常。

### 10.2 持续集成（GitHub Actions）

推送到 `main` 后会自动触发 [`.github/workflows/test.yml`](.github/workflows/test.yml)：

- 在 **6 个组合**上跑测试：`ubuntu-latest` / `windows-latest` × Python `3.11` / `3.12` / `3.13`；
- 每次跑**两遍**：先装好 ripgrep 跑一遍（验证搜索主路径），再设 `CODEAGENT_FORCE_PYTHON_SEARCH=1`
  跑一遍（验证没装 `rg` 的兜底路径）；
- 工作流本身**不需要 API Key**：全部用例都不发网络请求。

### 10.3 手动验证脚本（需要真实 API Key / 交互）

这些脚本演示真实行为，请单独运行，例如：

```powershell
python scripts\manual\test_tools.py      # 只读工具，不花钱
python scripts\manual\test_apply_edit.py # 各种边界用例
python scripts\manual\test_agent.py      # 让 Agent 真实回答一个问题
python scripts\manual\test_fim.py        # 直连 FIM 补全
```

> 命名约定：`test/test_unit_*.py` 是离线单测（会被 pytest 自动收集）；
> `scripts/manual/` 下的 `test_*.py` 是手动脚本，不参与自动收集，避免 pytest 一跑就发网络请求。
> 为什么 CI 的 Windows 机器也没装 `rg`？GitHub 的 runner 镜像默认不带 ripgrep（只有 macOS 自带），
> 所以工作流里显式 `apt-get install ripgrep` / `choco install ripgrep` 各装一次。

---

## 十一、常见问题排查

| 现象 | 原因与处理 |
|---|---|
| 启动即报 `DEEPSEEK_API_KEY 未设置` | 没建 `.env` 或没填 Key，见[第四节](#四配置-api-key) |
| `search_code` 结果比预期少 | 没装 `rg` 时走内置搜索，会跳过 `.git`、`__pycache__`、`venv` 等目录；想让结果更全就装上 ripgrep |
| `AuthenticationError 401` | Key 无效/已吊销（错误信息里会带 Key 尾号，如 `****19f4`），或复制时多了空格 |
| `RateLimitError` / 连接超时 | 会自动指数退避重试 3 次（终端打印 `[重试] 第 N 次失败`）；仍失败就降低调用频率 |
| 提示 `[已达最大步数 10，强制停止]` | 任务太大或模型绕圈，拆分任务，或调大 `run_agent(max_steps=…)` |
| 工具返回 `[已阻止] 本次任务已达到最多 3 次修改的上限` | 单任务写盘次数保护，重新发起一次任务即可 |
| `apply_edit` 报"不唯一" | 正常保护机制，在提示里给出更多上下文重试 |
| 中文乱码 | 终端编码问题，执行 `chcp 65001` 或设置 `$env:PYTHONIOENCODING="utf-8"` |
| 改了文件想回滚 | 用同目录下的 `xxx.py.bak`，或查 `.agent_log/edit.log` 的 `old` 字段 |

---

## 十二、已知限制

- 不是编辑器内联补全，没有 VS Code 插件，也没有大规模代码索引；
- 没有流式输出与多候选建议（`call_chat` 的 `stream=True` 目前只是占位，未实现）；
- 缓存是进程内内存缓存，退出即失效；没有做磁盘持久化；
- 上下文没有 token 预算管理，超长会话需要手动 `/clear`；会话历史也不会自动落盘；
- 只支持 DeepSeek（通过 OpenAI 兼容协议），换成别家需要改 `core/config.py` 的端点与模型名；
- 工具在本地直接读写文件，**没有做工作目录白名单**，请勿在重要目录里随意运行。

---

## 十三、后续可扩展方向

详见 [IncreaseDevelop.md](IncreaseDevelop.md)，优先级从高到低：

1. 只读/只写路径白名单，把 Agent 限制在指定项目目录内；
2. 上下文 token 预算与自动摘要（长会话不爆上下文）；
3. 流式输出 + 多候选补全，配合编辑器插件做内联补全；
4. 增加"跑测试验证改动"的工具，形成 改 → 验 → 修的闭环；
5. 会话持久化与 `--yes` 非交互模式（CI 里批量用）。

---

## 附：一句话总结

> 这是一个**真的会动手改代码、但绝不会偷偷改**的 CLI 代码 Agent：
> 它自己搜、自己读、自己判断，动手前把 diff 摊给你看，改完留备份和日志。
