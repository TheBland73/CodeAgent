"""
代码补全 Agent 的核心循环。

流程:
    user 任务 → LLM 决策 → (可选) 执行工具 → 回填结果 → LLM 再决策 → ... → 最终回答
"""

import json
import time
from core import ui
from core.config import settings
from core.llm import client
from core import tools
from core.llm import _retry_call


# ============================================================
# 工具 Schema（告诉模型有哪些工具可用）
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "使用 ripgrep 在代码库中搜索关键词或正则表达式。"
                "返回格式为 '文件路径:行号:内容'。适合用来查找函数定义、变量使用位置。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或正则表达式",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索的目录或文件路径，默认为当前目录",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "文件类型过滤，如 '*.py'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回多少条结果，默认 30",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取文件内容，返回带行号的文本。"
                "可以指定起止行号只读取一部分，避免文件过大。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从 1 开始），可选",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（含），可选",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_at_cursor",
            "description": (
                "在文件的指定行列插入代码。用于【补全】场景。"
                "line 是行号（从 1 开始），col 是列号（从 1 开始，"
                "表示插入到该行第 col 个字符之前，可等于行长度+1 表示行尾）。"
                "工具会展示 diff 并请求用户确认，确认后写入并自动备份。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "line": {"type": "integer", "description": "行号（1-based）"},
                    "col": {"type": "integer", "description": "列号（1-based）"},
                    "text": {"type": "string", "description": "要插入的代码"},
                },
                "required": ["path", "line", "col", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_edit",
            "description": (
                "精确替换文件中的一段代码。用于【修改】场景。"
                "old_code 必须在文件中唯一出现（0 次或多次都会被拒绝），"
                "建议包含前后几行以确保唯一。"
                "工具会展示 diff 并请求用户确认，确认后写入并自动备份。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_code": {
                        "type": "string",
                        "description": "要被替换的原文（必须唯一匹配，包含缩进）",
                    },
                    "new_code": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old_code", "new_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "创建新文件，或覆盖已有文件。用于【从零生成新代码】场景。"
                "如果文件已存在且 overwrite 为 False，会被拒绝。"
                "工具会展示 diff 并请求用户确认，确认后写入，覆盖时自动备份。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "文件已存在时是否允许覆盖，默认 False",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]


# ============================================================
# 工具注册表：名字 → 实际函数
# ============================================================

TOOL_REGISTRY = {
    "search_code": tools.search_code,
    "read_file": tools.read_file,
    "insert_at_cursor": tools.insert_at_cursor,
    "apply_edit": tools.apply_edit,
    "write_file": tools.write_file,
}


def execute_tool(name: str, arguments: str) -> str:
    """执行一个工具调用，返回字符串结果（永不抛异常）。"""
    if name not in TOOL_REGISTRY:
        return f"[错误] 未知工具: {name}"

    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError as e:
        return f"[错误] 参数不是合法 JSON: {e}"

    try:
        return TOOL_REGISTRY[name](**args)
    except TypeError as e:
        return f"[错误] 参数不匹配: {e}"
    except Exception as e:
        return f"[错误] 工具 {name} 执行失败: {type(e).__name__}: {e}"


# ============================================================
# 调试打印
# ============================================================

def _preview(text: str, limit: int = 200) -> str:
    """截断长文本用于打印。"""
    if text is None:
        return "<None>"
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... (+{len(text) - limit} 字符)"

# 不调用
def print_messages(messages: list) -> None:
    """打印当前 messages 的摘要，方便观察循环。"""
    print("\n" + "-" * 60)
    print(f"当前 messages 数量: {len(messages)}")
    for i, m in enumerate(messages):
        role = m.get("role", "?")
        content = _preview(m.get("content"), 120)
        extra = ""
        if m.get("tool_calls"):
            names = [tc["function"]["name"] for tc in m["tool_calls"]]
            extra = f" [tool_calls: {names}]"
        if m.get("tool_call_id"):
            extra = f" [tool_call_id: {m['tool_call_id']}]"
        print(f"  [{i}] {role}{extra}: {content}")
    print("-" * 60)


# ============================================================
# Agent 主循环
# ============================================================

DEFAULT_SYSTEM_PROMPT = """你是一个代码补全 Agent。

你可以使用以下工具来调查代码库：
- search_code: 搜索代码，找到定义、引用、使用位置
- read_file: 读取文件内容

工作方式：
1. 先分析用户的任务，判断需要哪些信息。
2. 如果需要查看代码，调用工具；一次可以调用多个。
3. 拿到结果后继续判断，直到你有足够信息。
4. 信息足够时，直接给出最终答案，不要再调用工具。

回答要求：
- 如果任务是补全代码，直接给出补全的代码片段（不要 markdown 代码块以外的解释）。
- 如果任务是回答问题，简洁准确地回答。
- 不要编造没有在工具结果中看到的内容。
"""

# 会真正改动磁盘的工具（只读工具不受修改次数限制）
WRITE_TOOL_NAMES = {"insert_at_cursor", "apply_edit", "write_file", "fim_assist"}


def run_agent(
    user_task: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_steps: int = 10,
    max_edits: int = 3,
    temperature: float = 0.3,
    verbose: bool = True,
    messages: list = None,
) -> str:
    """
    运行 Agent 循环。

    Args:
        user_task: 用户任务描述
        system_prompt: 系统提示词
        max_steps: 最多循环步数，防止无限调用
        max_edits: 单次任务内最多执行多少次写操作（insert_at_cursor /
                   apply_edit / write_file / fim_assist），防止模型反复改坏文件；
                   只读工具（search_code / read_file）不计入
        temperature: 采样温度
        verbose: 是否打印每一步的调试信息
        messages: 已有的对话历史。传入时会就地追加，实现多轮会话；
                  None 时新建一个以 system_prompt 开头的会话

    Returns:
        模型最终回答的文本
    """
    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt},
        ]
    messages.append({"role": "user", "content": user_task})

    edits_done = 0  # 本任务内已成功执行的写操作次数

    for step in range(1, max_steps + 1):
        step_start = time.time()
        if verbose:
            ui.print_step(step, max_steps)

        response = _retry_call(lambda: client.chat.completions.create(
            model=settings.DEFAULT_MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            temperature=temperature,
        ))

        msg = response.choices[0].message

        if verbose:
            elapsed = time.time() - step_start
            ui.print_thinking(elapsed)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args_short = _preview(tc.function.arguments, 100)
                    ui.print_tool_call(tc.function.name, args_short)
            else:
                ui.print_no_tool_call()

        # --- 纠错 1: 空输出 ---
        if not msg.content and not msg.tool_calls:
            messages.append({"role": "assistant", "content": ""})
            messages.append({
                "role": "user",
                "content": "你的上一次回复是空的。请继续：要么调用工具获取信息，要么直接给出最终答案。",
            })
            if verbose:
                ui.print_correction("空输出，已提示模型重试")
            continue

        # --- 纠错 2: 无效 JSON 参数 ---
        if msg.tool_calls:
            bad = []
            for tc in msg.tool_calls:
                try:
                    json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    bad.append(tc.function.name)

            if bad:
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({
                    "role": "user",
                    "content": (
                        f"你之前的工具调用参数不是合法 JSON（{', '.join(bad)}）。"
                        "请重新调用，确保 arguments 是一个合法的 JSON 对象。"
                    ),
                })
                if verbose:
                    ui.print_correction(f"无效 JSON 参数: {bad}，已提示模型重试")
                continue

        # 1) 追加 assistant 消息
        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        messages.append(assistant_msg)

        # 2) 没有工具调用 → 结束
        if not msg.tool_calls:
            return msg.content or ""

        # 3) 逐个执行工具
        for tc in msg.tool_calls:
            name = tc.function.name
            arguments = tc.function.arguments
            t0 = time.time()

            # 修改次数上限：超过后不再执行写操作，把结果回传给模型让它收尾
            if name in WRITE_TOOL_NAMES and edits_done >= max_edits:
                result = (
                    f"[已阻止] 本次任务已达到最多 {max_edits} 次修改的上限，"
                    "该写操作未执行。请基于已有信息直接给出最终总结。"
                )
                tool_elapsed = 0.0
            else:
                result = execute_tool(name, arguments)
                tool_elapsed = time.time() - t0
                if name in WRITE_TOOL_NAMES and result.startswith("[已"):
                    edits_done += 1

            if verbose:
                ui.print_tool_result(name, _preview(result, 200), tool_elapsed * 1000)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return f"[已达最大步数 {max_steps}，强制停止]"