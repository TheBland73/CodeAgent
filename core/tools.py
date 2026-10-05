"""
代码补全 Agent 的工具集。

当前提供两个工具：
    - search_code(query, path, ...): 用 ripgrep 搜索代码
    - read_file(path, ...): 读取文件内容
"""
#.\venv2\Scripts\Activate.ps1

import json
import difflib
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from core.cache import search_cache

# 日志目录
LOG_DIR = Path(".agent_log")
LOG_FILE = LOG_DIR / "edit.log"
# 日志里 old/new 的最大长度 （超出截断，防止单行爆长）
LOG_CONTENT_LIMIT = 2000

# ============================================================
# 工具 1: search_code
# ============================================================

def _find_rg() -> Optional[str]:
    """查找 ripgrep 可执行文件。"""
    return shutil.which("rg")


def search_code(
    query: str,
    path: str = ".",
    max_results: int = 30,
    file_glob: Optional[str] = None,
    context_lines: int = 0,
    use_cache: bool = True,
) -> str:
    """
    使用 ripgrep 在指定目录下搜索代码。

    Args:
        query: 搜索关键词（支持正则）
        path: 搜索目录或文件路径，默认当前目录
        max_results: 最多返回的结果条数
        file_glob: 文件过滤，如 "*.py" 或 "!*.json"
        context_lines: 上下文字行数，0 表示不显示

    Returns:
        格式化后的搜索结果字符串。每行格式：文件:行号:内容
        无结果或出错时返回可读的提示信息。
    """
    if use_cache:
        cached = search_cache.get(query, path, max_results, file_glob, context_lines)
        if cached is not None:
            print(f"[缓存] search_code 命中 (query={query!r})")
            return cached

    rg = _find_rg()
    if rg is None:
        return (
            "[错误] 未找到 ripgrep (rg)。\n"
            "请安装：\n"
            "  Windows: winget install BurntSushi.ripgrep.MSVC\n"
            "  macOS:   brew install ripgrep\n"
            "  Linux:   sudo apt install ripgrep"
        )

    cmd = [
        rg,
        "--line-number",          # 显示行号
        "--no-heading",           # 每行都带文件路径
        "--color=never",          # 关闭颜色，便于解析
        "--max-count", str(max_results),
    ]

    if context_lines > 0:
        cmd += ["--context", str(context_lines)]

    if file_glob:
        cmd += ["--glob", file_glob]

    cmd += [query, path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return f"[错误] 搜索超时（query={query!r}）。"
    except Exception as e:
        return f"[错误] 执行 ripgrep 失败: {type(e).__name__}: {e}"

    # rg 退出码：0=有匹配，1=无匹配，2=出错
    if result.returncode not in (0, 1):
        return f"[错误] ripgrep 返回码 {result.returncode}: {result.stderr.strip()}"

    # 统一计算最终结果
    if result.returncode == 1:
        final = f"[无结果] 未找到匹配 {query!r} 的内容。"
    else:
        lines = result.stdout.strip().splitlines()
        if len(lines) > max_results:
            lines = lines[:max_results]
            lines.append(f"...（已截断，最多显示 {max_results} 条）")
        final = "\n".join(lines) if lines else f"[无结果] 未找到匹配 {query!r} 的内容。"

    # 写缓存
    if use_cache:
        search_cache.set(final, query, path, max_results, file_glob, context_lines)

    return final

# ============================================================
# 工具 2: read_file
# ============================================================

def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_lines: int = 500,
) -> str:
    """
    读取文件内容。

    Args:
        path: 文件路径
        start_line: 起始行号（从 1 开始），None 表示从头
        end_line: 结束行号（含），None 表示到结尾
        max_lines: 单次最多读取的行数，防止文件过大撑爆上下文

    Returns:
        文件内容字符串，或错误提示。
    """
    p = Path(path)
    if not p.exists():
        return f"[错误] 文件不存在: {path}"
    if not p.is_file():
        return f"[错误] 不是文件: {path}"

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[错误] 读取失败: {type(e).__name__}: {e}"

    lines = content.splitlines()

    # 行号切片（1-based，含首含尾）
    s = (start_line - 1) if start_line and start_line > 0 else 0
    e = end_line if end_line and end_line > 0 else len(lines)
    e = min(e, len(lines))

    if s >= len(lines):
        return f"[错误] 起始行 {start_line} 超出文件范围（共 {len(lines)} 行）。"

    selected = lines[s:e]

    if len(selected) > max_lines:
        selected = selected[:max_lines]
        selected.append(f"...（已截断，仅显示前 {max_lines} 行）")

    # 带行号输出，便于模型理解位置
    numbered = [f"{s + i + 1:>4} | {line}" for i, line in enumerate(selected)]
    return "\n".join(numbered)

def _make_diff(old: str, new: str, path: str, n: int = 3) ->str:
    """
    生成统一 diff 文本（格式同 git diff）。

    Args:
        old: 修改前的完整内容
        new: 修改后的完整内容
        path: 文件路径（用于 a/ b/ 头部）
        n: 上下文的行数

    Returns:
        diff 字符串；如果内容没变，返回空字符串
    """
    diff_lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=n,
    )
    diff = "".join(diff_lines)
    # 确保结尾有换行，便于拼接
    if diff and not diff.endswith("\n"):
        diff += "\n"
    return diff

def _diff_stats(diff: str) -> tuple:
    """从 diff 里统计 (新增行数, 删除行数)。"""
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return added, removed

def _make_backup(path: Path) -> Optional[Path]:
    """
    为文件创建备份（path + '.bak'）。
    已存在同名备份时覆盖，只保留最近一次。
    """
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, backup)
        return backup
    except Exception:
        return None

def _confirm_and_backup(
    path: Path,
    diff: str,
    skip_confirm: bool,
) -> tuple:
    """
    展示 diff、请求用户确认、按需备份。
    """
    from core import ui

    ui.print_edit_header(str(path))
    ui.print_diff(diff.rstrip())

    if skip_confirm:
        backup = _make_backup(path)
        return True, f"备份: {backup}" if backup else "（备份失败）"

    if not ui.ask_confirm():
        return False, "[已取消] 用户拒绝修改，文件未变"

    backup = _make_backup(path)
    return True, f"备份: {backup}" if backup else "（备份失败）"

def _truncate(text: str, limit: int = LOG_CONTENT_LIMIT) -> str:
    """超长内容截断，附加提示。"""
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(+{len(text) - limit} 字符)"


def _log_edit(
    tool: str,
    path: Path,
    old_content: str,
    new_content: str,
    result: str,
    backup: Optional[str] = None,
) -> None:
    """
    追加一条修改日志到 .agent_logs/edit.log（JSON Lines）。
    日志写入失败不影响主流程。
    """
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "file": str(path),
        "old": _truncate(old_content),
        "new": _truncate(new_content),
        "result": result,
    }
    if backup:
        record["backup"] = backup

    try:
        LOG_DIR.mkdir(exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # 日志失败不应影响功能
        pass

def _write_with_confirm(
    p: Path,
    old_content: str,
    new_content: str,
    diff: str,
    tool: str,
    skip_confirm: bool,
) -> str:
    """
    统一的写入流程：确认 → 写入 → 日志。

    Returns:
        给用户看的消息。用户拒绝时返回取消消息。
    """
    # 1) 确认 + 备份
    proceed, msg = _confirm_and_backup(p, diff, skip_confirm)
    if not proceed:
        _log_edit(tool, p, old_content, new_content, "rejected")
        return msg

    # 2) 写入
    try:
        p.write_text(new_content, encoding="utf-8")
    except Exception as e:
        err = f"[错误] 写入失败: {type(e).__name__}: {e}"
        _log_edit(tool, p, old_content, new_content, f"write_error: {e}")
        return err

    # 3) 日志
    backup_path = msg.split(": ", 1)[1] if msg.startswith("备份") else None
    _log_edit(tool, p, old_content, new_content, "success", backup=backup_path)

    return msg

def insert_at_cursor(
    path: str,
    line: int,
    col: int,
    text: str,
    skip_confirm: bool = False,
) -> str:
    """
    在文件的指定行列插入文本。用于代码补全。

    Args:
        path: 文件路径
        line: 行号（从 1 开始，等于行数+1 时表示追加到文件末尾）
        col: 列号（从 1 开始，表示插入到该行第 col 个字符之前）
        text: 要插入的文本（可包含换行）

    Returns:
        操作结果摘要
    """
    p = Path(path)
    if not p.exists():
        return f"[错误] 文件不存在: {path}"
    if not p.is_file():
        return f"[错误] 不是文件: {path}"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"[错误] 读取失败: {type(e).__name__}: {e}"

    lines = content.splitlines(keepends=True)
    # 注意：read_file 展示给模型的行号是"逻辑行号"（末尾换行符不算一行）。
    # 这里按同样的口径计算，避免模型照着 read_file 的行号调用时错位。
    logical_count = len(content.splitlines())
    if line < 1 or line > logical_count + 1:
        return (
            f"[错误] 行号 {line} 超出范围。"
            f"文件共 {logical_count} 行，有效行号 1-{logical_count + 1}"
            f"（{logical_count + 1} 表示追加到文件末尾）。"
        )

    if line == logical_count + 1:
        # 追加到文件末尾：保留原有结尾，直接拼接
        new_content = content + text
        diff = _make_diff(content, new_content, path)
        added, removed = _diff_stats(diff)
        msg = _write_with_confirm(
            p, content, new_content, diff, "insert_at_cursor", skip_confirm
        )
        if msg.startswith("[已取消]") or msg.startswith("[错误]"):
            return msg
        return (
            f"[已追加] {path} 文件末尾（+{added} -{removed}）\n"
            f"{msg}\n"
            f"{diff}"
        )

    target = lines[line - 1]
    # 行尾可能带 \n 或 \r\n，计算"可见长度"时排除换行符
    visible = target.rstrip("\r\n")
    newline_suffix = target[len(visible):]

    if col < 1 or col > len(visible) + 1:
        return (
            f"[错误] 列号 {col} 超出范围。"
            f"第 {line} 行长度为 {len(visible)}，有效列号 1-{len(visible) + 1}"
        )

    pos = col - 1
    # 把插入内容拼回该行：前缀 + text + 后缀 + 原换行符
    lines[line - 1] = visible[:pos] + text + visible[pos:] + newline_suffix

    new_content = "".join(lines)

    diff = _make_diff(content, new_content, path)
    added, removed = _diff_stats(diff)

    msg = _write_with_confirm(p, content, new_content, diff, "insert_at_cursor", skip_confirm)
    if msg.startswith("[已取消]") or msg.startswith("[错误]"):
        return msg

    return (
        f"[已插入] {path} 第 {line} 行第 {col} 列"
        f"（+{added} -{removed}）\n"
        f"{msg}\n"
        f"{diff}"
    )

def apply_edit(
    path: str,
    old_code: str,
    new_code: str,
    skip_confirm: bool = False,
) -> str:
    """
    精确替换文件中的一段代码。

    要求 old_code 在文件中唯一出现：
        - 0 次 → 拒绝，提示未找到
        - 多次 → 拒绝，提示不唯一，建议扩大上下文

    写入前会展示 diff 并请求用户确认（可通过 skip_confirm=True 跳过）。
    """
    p = Path(path)
    if not p.exists():
        return f"[错误] 文件不存在: {path}"
    if not p.is_file():
        return f"[错误] 不是文件: {path}"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"[错误] 读取失败: {type(e).__name__}: {e}"

    if not old_code:
        return "[错误] old_code 不能为空。"

    count = content.count(old_code)
    if count == 0:
        return f"[错误] 未找到 old_code 在 {path} 中的匹配内容。"
    if count > 1:
        return (
            f"[错误] old_code 在 {path} 中出现 {count} 次，不唯一。"
            "请提供更长的上下文（包含前后几行）以确保唯一匹配。"
        )

    new_content = content.replace(old_code, new_code, 1)

    diff = _make_diff(content, new_content, path)
    added, removed = _diff_stats(diff)

    msg = _write_with_confirm(p, content, new_content, diff, "apply_edit", skip_confirm)
    if msg.startswith("[已取消]") or msg.startswith("[错误]"):
        return msg

    return (
        f"[已替换] {path}：1 处匹配（+{added} -{removed}）\n"
        f"{msg}\n"
        f"{diff}"
    )

def write_file(
    path: str,
    content: str,
    overwrite: bool = False,
    skip_confirm: bool = False,
) -> str:
    """
    创建新文件或覆盖已有文件。

    Args:
        path: 文件路径
        content: 要写入的完整内容
        overwrite: 已有文件时是否允许覆盖。False 时拒绝，防止误删。
        skip_confirm: 跳过用户确认（用于自动化测试）

    Returns:
        操作结果摘要
    """
    p = Path(path)

    if p.exists():
        if not p.is_file():
            return f"[错误] 路径已存在且不是文件: {path}"
        if not overwrite:
            return (
                f"[错误] 文件已存在: {path}。"
                "如需覆盖请显式设置 overwrite=True。"
            )
        # 覆盖：读旧内容用于 diff
        try:
            old_content = p.read_text(encoding="utf-8")
        except Exception as e:
            return f"[错误] 读取旧文件失败: {type(e).__name__}: {e}"
    else:
        # 新建：确保父目录存在
        if p.parent and not p.parent.exists():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return f"[错误] 创建目录失败: {type(e).__name__}: {e}"
        old_content = ""

    new_content = content

    # 生成 diff（新建时 old 为空，全部显示为 +）
    diff = _make_diff(old_content, new_content, path)
    added, removed = _diff_stats(diff)

    # 确认 + 写入 + 日志（复用统一编排，但走 overwrite 分支的特殊逻辑）
    from core import ui

    action = "覆盖" if p.exists() else "新建"
    ui.print_edit_header(f"{path}（{action}）")
    ui.print_diff(diff.rstrip())

    if not skip_confirm:
        if not ui.ask_confirm():
            _log_edit("write_file", p, old_content, new_content, "rejected")
            return "[已取消] 用户拒绝修改，文件未变"

    # 备份：仅覆盖已有文件时
    backup_msg = "（新建文件，无需备份）"
    if p.exists():
        backup = _make_backup(p)
        backup_msg = f"备份: {backup}" if backup else "（备份失败）"

    try:
        p.write_text(new_content, encoding="utf-8")
    except Exception as e:
        err = f"[错误] 写入失败: {type(e).__name__}: {e}"
        _log_edit("write_file", p, old_content, new_content, f"write_error: {e}")
        return err

    backup_path = None
    if backup_msg.startswith("备份"):
        backup_path = backup_msg.split(": ", 1)[1]
    _log_edit("write_file", p, old_content, new_content, "success", backup=backup_path)

    return (
        f"[已{action}] {path}（+{added} -{removed}）\n"
        f"{backup_msg}\n"
        f"{diff}"
    )


def fim_assist(
    path: str,
    line: int,
    col: int,
    max_tokens: int = 128,
    skip_confirm: bool = False,
) -> str:
    """
    在指定光标位置做一次 FIM 补全，并把候选代码插入文件。

    与 insert_at_cursor 的区别：补全内容不是由模型"显式给出"，
    而是由 DeepSeek FIM（fill-in-the-middle）接口根据光标前文/后文生成。

    Args:
        path: 文件路径
        line: 光标所在行（从 1 开始，等于行数+1 表示文件末尾）
        col: 光标所在列（从 1 开始）
        max_tokens: 生成的 token 上限
        skip_confirm: 跳过用户确认（自动化测试用）

    Returns:
        操作结果摘要（含候选代码与 diff）
    """
    # 延迟导入，避免 core.tools → core.llm → core.config 在 import 期强耦合
    from core.llm import call_fim

    p = Path(path)
    if not p.exists():
        return f"[错误] 文件不存在: {path}"
    if not p.is_file():
        return f"[错误] 不是文件: {path}"

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"[错误] 读取失败: {type(e).__name__}: {e}"

    inner = content.splitlines(keepends=True)
    logical_count = len(content.splitlines())

    if line < 1 or line > logical_count + 1:
        return (
            f"[错误] 行号 {line} 超出范围。"
            f"文件共 {logical_count} 行，有效行号 1-{logical_count + 1}。"
        )

    # 1) 把文件在光标处切成 prefix / suffix
    if line == logical_count + 1:
        prefix, suffix = content, ""
    else:
        target = inner[line - 1]
        visible = target.rstrip("\r\n")
        newline_suffix = target[len(visible):]
        if col < 1 or col > len(visible) + 1:
            return (
                f"[错误] 列号 {col} 超出范围。"
                f"第 {line} 行长度为 {len(visible)}，有效列号 1-{len(visible) + 1}"
            )
        offset = col - 1
        prefix = "".join(inner[:line - 1]) + visible[:offset]
        suffix = visible[offset:] + newline_suffix + "".join(inner[line:])

    # 2) 调用 FIM 端点
    try:
        completion = call_fim(prefix=prefix, suffix=suffix, max_tokens=max_tokens)
    except Exception as e:
        return f"[错误] FIM 补全失败: {type(e).__name__}: {e}"

    if not completion:
        return "[无补全] 模型没有返回内容，文件未修改。"

    # 3) 多行补全收尾对齐：只有当光标后面还接着同一行的文本时，才需要补一个换行，
    #    否则会把后面的代码顶到自己那一行、多出一个空行。
    if "\n" in completion and suffix and not completion.endswith("\n") and suffix[0] != "\n":
        completion += "\n"

    # 4) 确认 + 写入 + 日志（复用统一写入流程）
    new_content = prefix + completion + suffix
    diff = _make_diff(content, new_content, path)
    added, removed = _diff_stats(diff)

    msg = _write_with_confirm(
        p, content, new_content, diff, "fim_assist", skip_confirm
    )
    if msg.startswith("[已取消]") or msg.startswith("[错误]"):
        return msg

    return (
        f"[FIM 补全] {path} 第 {line} 行第 {col} 列（+{added} -{removed}）\n"
        f"候选代码:\n{completion}\n"
        f"{msg}\n"
        f"{diff}"
    )