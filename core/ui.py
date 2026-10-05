# core/ui.py
"""
终端 UI 层。

所有面向用户的输出都通过这里的函数，方便统一风格和后续换主题。
"""

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text


console = Console()

# 颜色约定
C_BRAND = "cyan"
C_SUCCESS = "green"
C_ERROR = "red"
C_WARN = "yellow"
C_DIM = "dim"
C_TOOL = "magenta"


# ============================================================
# 会话级
# ============================================================

def print_welcome():
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Code Agent by TheBland[/bold cyan]\n"
        "[dim]输入 /help 查看帮助，/exit 退出[/dim]",
        border_style=C_BRAND,
        padding=(0, 2),
    ))
    console.print()


def print_help(text: str):
    console.print(Panel(
        text.strip(),
        title="帮助",
        title_align="left",
        border_style=C_BRAND,
        padding=(0, 2),
    ))


def print_cleared():
    console.print("[dim]· 对话历史已清空[/dim]")


def prompt_input() -> str:
    """主循环的输入提示符。"""
    return console.input("[bold cyan]> [/bold cyan]")


# ============================================================
# Agent 步骤
# ============================================================

def print_step(step: int, max_steps: int):
    console.print()
    console.print(Rule(
        f"[bold {C_BRAND}]Step {step}/{max_steps}[/bold {C_BRAND}]",
        style=C_DIM,
        align="left",
    ))


def print_thinking(elapsed: float):
    console.print(f"  [dim]·[/dim] 思考耗时 [bold]{elapsed:.2f}s[/bold]")


def print_tool_call(name: str, args_preview: str):
    console.print(
        f"  [bold {C_TOOL}]→[/bold {C_TOOL}] "
        f"[bold]{name}[/bold]"
        f"[dim]({args_preview})[/dim]"
    )


def print_tool_result(name: str, result_preview: str, elapsed_ms: float):
    console.print(
        f"  [bold {C_SUCCESS}]✓[/bold {C_SUCCESS}] "
        f"{name} [dim]({elapsed_ms:.0f}ms)[/dim]"
    )
    for line in result_preview.splitlines() or [""]:
        console.print(f"    {line}", style="dim", markup=False)

def print_no_tool_call():
    console.print(f"  [dim]·[/dim] 无工具调用，输出最终答案")


def print_correction(msg: str):
    console.print(f"  [bold {C_WARN}]⚠[/bold {C_WARN}] {msg}")


def print_error(msg: str):
    console.print(f"  [bold {C_ERROR}]✗[/bold {C_ERROR}] {msg}")


# ============================================================
# 结果展示
# ============================================================

def print_summary(text: str):
    console.print()
    console.print(Panel(
        text.strip(),
        title="[bold]总结[/bold]",
        title_align="left",
        border_style=C_SUCCESS,
        padding=(0, 2),
    ))


def print_diff(diff: str):
    """给 diff 逐行着色。"""
    text = Text()
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            text.append(line + "\n", style="bold")
        elif line.startswith("@@"):
            text.append(line + "\n", style=C_BRAND)
        elif line.startswith("+"):
            text.append(line + "\n", style=C_SUCCESS)
        elif line.startswith("-"):
            text.append(line + "\n", style=C_ERROR)
        else:
            text.append(line + "\n", style=C_DIM)
    console.print(text, end="")


def print_edit_header(path: str):
    console.print()
    console.print(f"[bold]即将修改[/bold] [cyan]{path}[/cyan]")


def ask_confirm() -> bool:
    """带颜色的 y/n 确认。"""
    try:
        answer = console.input(
            f"[bold {C_WARN}]确认修改？[/bold {C_WARN}] [dim](y/n)[/dim] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    return answer in ("y", "yes")