# 手动验证脚本

这个目录存放开发过程中用来**人工观察行为**的脚本。它们不是自动化测试，**不会被 CI 执行**，
正式测试请见 [`test/`](../../test)。放在这里的目的是：保留"每一步都实际跑过、眼睛看过输出"的证据，
同时让仓库根目录和测试目录保持干净。

## 为什么和 `test/` 分开

| | `test/test_unit_*.py` | `scripts/manual/*.py` |
|---|---|---|
| 运行方式 | `python -m pytest` | `python scripts/manual/xxx.py` |
| 是否联网 | **否**，全部用假客户端 | **部分是**，直接请求 DeepSeek API |
| 是否需要 API Key | 否 | **需要**（`core/llm.py` 走真实客户端） |
| 是否有副作用 | 否（在临时目录里操作） | **有**：写文件、生成 `*.bak`、写 `.agent_log/edit.log` |
| 部分脚本 | — | 会在**当前目录**打印 diff 并**等待你输入 y/n 确认** |

## 运行前提

1. 已完成项目安装（见根目录 [`README.md`](../../README.md) 的"安装"一节）
2. 仓库根目录存在 `.env` 且已填**有效**的 `DEEPSEEK_API_KEY`
3. 在**仓库根目录**执行（脚本按相对路径找 `core/`）：

```powershell
# Windows PowerShell
.\venv2\Scripts\python.exe scripts\manual\test_insert.py

# 或先激活虚拟环境
.\venv2\Scripts\Activate.ps1
python scripts\manual\test_insert.py
```

## 脚本清单

### 只读 / 无副作用

| 脚本 | 验证内容 |
|---|---|
| [`test_tools.py`](test_tools.py) | 工具层冒烟：`search_code` / `read_file` / `insert_at_cursor` / `apply_edit` / `write_file` 的返回值格式与错误分支 |
| [`check_insert.py`](check_insert.py) | `insert_at_cursor` 行号边界（**历史上发现"无法追加到文件末尾"的那个 bug 就是靠它暴露的**） |
| [`test_retry.py`](test_retry.py) | `_retry_call` 的指数退避：成功、重试耗尽、不可重试异常三种路径 |
| [`utils.py`](utils.py) | 辅助函数 `round_to_two` |

### 需要有效 API Key

| 脚本 | 验证内容 |
|---|---|
| [`test_api.py`](test_api.py) | 最小连通性：`call_chat` 能否拿到回复；Key / base_url / 模型名是否可用 |
| [`test_agent.py`](test_agent.py) | 完整 Agent 循环：多步工具调用后能否给出最终答复 |
| [`test_fim.py`](test_fim.py) | FIM 补全端点（走 `https://api.deepseek.com/beta`）：prefix/suffix 拼接是否被正确补全 |

### 有副作用：会写文件、会等待确认

> ⚠️ 以下脚本会在当前目录创建临时文件与 `*.bak` 备份，并向 `.agent_log/edit.log` 追加记录。
> 运行前请确认所在目录不是重要目录，运行后自行清理产生的文件。

| 脚本 | 验证内容 |
|---|---|
| [`test_insert.py`](test_insert.py) | `insert_at_cursor` 的交互确认流程（diff 展示 + y/n） |
| [`test_apply_edit.py`](test_apply_edit.py) | `apply_edit` 唯一匹配、备份生成、diff 统计 |
| [`test_diff.py`](test_diff.py) | diff 渲染：新增/删除/上下文行的着色与 `+N -M` 统计 |
| [`test_confirm.py`](test_confirm.py) | 确认环节的"拒绝"分支 —— 拒绝后**文件不应被修改**（但也**不应留下半成品**） |
| [`test_log.py`](test_log.py) | `.agent_log/edit.log` 的 JSONL 结构：字段完整性、内容截断、`rejected` 也要留痕 |
| [`test_cache.py`](test_cache.py) | 两级缓存：`fim_cache`（TTL 600s）与 `search_cache`（TTL 300s）的命中率统计 |

### 数据文件

| 文件 | 用途 |
|---|---|
| [`sample.py`](sample.py) | 供上述脚本改写的示例源码 |
| [`test_insert_sample.py`](test_insert_sample.py) | `insert_at_cursor` 的目标文件（脚本会往里插入代码） |

## 提示

- 这些脚本是**开发过程中的手工观察工具**，输出以人眼判读为主，不做断言。若要做回归防护，
  请把发现的问题沉淀成 `test/test_unit_*.py` 里的一条断言 —— 这正是本项目 48 条离线用例的来源。
- 跑完脚本后如果 `git status` 出现 `*.bak` 或临时文件，直接删掉即可；`.gitignore` 已忽略
  `*.bak` 与 `.agent_log/`，它们不会误入版本库。
