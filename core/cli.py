# main.py
"""
代码助手 Agent CLI（会话式）
"""

from core import ui
from core.agent import run_agent
from core.tools import fim_assist


SYSTEM_PROMPT = """你是一个代码助手 Agent。

可用工具:
- read_file: 读取文件内容（带行号）
- search_code: 搜索代码，查找相关函数或引用
- insert_at_cursor: 在指定行列插入代码（用于补全已有文件）
- apply_edit: 精确替换一段文本（用于修改已有文件，old_code 必须唯一）
- write_file: 创建新文件或覆盖已有文件（用于从零写代码）

工作流程:
1. 如果目标文件已存在，先 read_file 读取确认内容。
2. 如果是"写一个新函数/新脚本"且文件不存在，直接用 write_file 创建。
3. 如果任务涉及项目里的其他函数/类型，用 search_code 确认。
4. 信息足够后，调用相应工具修改文件。
5. 完成后用一两句话总结你做了什么。

规则:
- 补全已有代码用 insert_at_cursor，修改已有代码用 apply_edit，
  从零创建新文件用 write_file。
- 不要用 write_file 覆盖已经存在的文件（除非用户明确要求覆盖）。
- 一次任务最多修改 3 次。
- 最终回答不要再贴完整代码，只说明修改位置和内容。
- 用中文回答。
"""


HELP_TEXT = """
可用命令:
  /exit, exit, quit         退出会话
  /clear                    清空对话历史
  /help                     显示本帮助
  /fim <文件> <行> <列>      在指定光标位置做一次 FIM 补全（不走 Agent 循环）

使用方式:
  直接输入任务描述，例如:
    补全 sample.py 里 add 函数的 result 赋值
    把 sample.py 里的 a - b 改成 a + b

  FIM 直连补全（模型只看光标前文/后文，不调用工具），例如:
    /fim test/sample.py 2 14
"""


def new_session() -> list:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def handle_fim(args: list) -> None:
    """处理 /fim <文件> <行> <列> 直连补全命令。"""
    if len(args) != 3:
        ui.print_error("用法: /fim <文件> <行> <列>，例如 /fim test/sample.py 2 14")
        return

    path, line_str, col_str = args
    if not line_str.isdigit() or not col_str.isdigit():
        ui.print_error("行号和列号必须是正整数。")
        return

    ui.console.print(f"[dim]· FIM 补全中: {path} ({line_str}:{col_str})[/dim]")
    # fim_assist 内部自带 diff 展示与人机确认
    result = fim_assist(path, line=int(line_str), col=int(col_str))
    if result.startswith("[错误]") or result.startswith("[已取消]") or result.startswith("[无补全]"):
        ui.print_error(result.strip())
    else:
        ui.print_summary(result)


def main():
    ui.print_welcome()

    messages = new_session()

    while True:
        try:
            task = ui.prompt_input().strip()
        except (EOFError, KeyboardInterrupt):
            ui.console.print("\n[dim]再见。[/dim]")
            break

        if not task:
            continue

        if task in ("/exit", "exit", "quit"):
            ui.console.print("[dim]再见。[/dim]")
            break
        if task == "/help":
            ui.print_help(HELP_TEXT)
            continue
        if task == "/clear":
            messages = new_session()
            ui.print_cleared()
            continue
        if task == "/fim" or task.startswith("/fim "):
            handle_fim(task.split()[1:])
            continue

        try:
            summary = run_agent(
                user_task=task,
                system_prompt=SYSTEM_PROMPT,
                max_steps=10,
                max_edits=3,
                temperature=0.2,
                verbose=True,
                messages=messages,
            )
        except Exception as e:
            ui.print_error(f"Agent 失败: {type(e).__name__}: {e}")
            continue

        ui.print_summary(summary)


if __name__ == "__main__":
    main()