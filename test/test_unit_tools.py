"""
离线单元测试：工具层（core/tools.py）。

设计目标：
    - 不访问网络、不调用 LLM；
    - 全部在 tmp_path 里操作，不污染仓库；
    - 写操作统一用 skip_confirm=True 走自动化路径。

运行（项目根目录 CodeAgent/ 下）：
    python -m pytest -q
"""

import pytest

from core.tools import (
    LOG_FILE,
    apply_edit,
    insert_at_cursor,
    read_file,
    search_code,
    write_file,
)


# ============================================================
# read_file
# ============================================================

def test_read_file_returns_numbered_lines(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")

    out = read_file(str(f))

    assert "   1 | a = 1" in out
    assert "   2 | b = 2" in out


def test_read_file_respects_line_range(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8")

    out = read_file(str(f), start_line=3, end_line=4)

    assert "line3" in out and "line4" in out
    assert "line1" not in out and "line5" not in out


def test_read_file_errors(tmp_path):
    assert "[错误] 文件不存在" in read_file(str(tmp_path / "nope.py"))
    assert "[错误] 不是文件" in read_file(str(tmp_path))


# ============================================================
# insert_at_cursor
# ============================================================

def test_insert_at_cursor_inline(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def add(a, b):\n    result = \n    return result\n", encoding="utf-8")

    out = insert_at_cursor(str(f), line=2, col=14, text="a + b", skip_confirm=True)

    assert "[已插入]" in out
    assert "result = a + b" in f.read_text(encoding="utf-8")


def test_insert_at_cursor_can_append_at_eof(tmp_path):
    """回归测试：文件以换行符结尾时，line = 逻辑行数+1 应表示追加到末尾。"""
    f = tmp_path / "a.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")

    out = insert_at_cursor(str(f), line=3, col=1, text="c = 3\n", skip_confirm=True)

    assert "[已追加]" in out
    assert f.read_text(encoding="utf-8") == "a = 1\nb = 2\nc = 3\n"


def test_insert_at_cursor_rejects_bad_position(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")

    assert "[错误] 行号" in insert_at_cursor(str(f), line=99, col=1, text="x")
    assert "[错误] 列号" in insert_at_cursor(str(f), line=1, col=99, text="x")
    # 越界调用不能改动文件
    assert f.read_text(encoding="utf-8") == "a = 1\nb = 2\n"


# ============================================================
# apply_edit
# ============================================================

DUPLICATE_SNIPPET = """def add(a, b):
    result = a - b
    return result


def sub(a, b):
    result = a - b
    return result
"""


def test_apply_edit_unique_match(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def mul(a, b):\n    return a * b\n", encoding="utf-8")

    out = apply_edit(
        str(f),
        old_code="    return a * b\n",
        new_code="    return a * b * 2\n",
        skip_confirm=True,
    )

    assert "[已替换]" in out
    assert "a * b * 2" in f.read_text(encoding="utf-8")


def test_apply_edit_rejects_non_unique_match(tmp_path):
    f = tmp_path / "a.py"
    f.write_text(DUPLICATE_SNIPPET, encoding="utf-8")

    out = apply_edit(
        str(f),
        old_code="    result = a - b\n",
        new_code="    result = a + b\n",
        skip_confirm=True,
    )

    assert "不唯一" in out
    assert f.read_text(encoding="utf-8") == DUPLICATE_SNIPPET


def test_apply_edit_rejects_missing_and_empty_old_code(tmp_path):
    f = tmp_path / "a.py"
    f.write_text(DUPLICATE_SNIPPET, encoding="utf-8")

    assert "未找到" in apply_edit(str(f), old_code="print('x')\n", new_code="y", skip_confirm=True)
    assert "不能为空" in apply_edit(str(f), old_code="", new_code="y", skip_confirm=True)


def test_apply_edit_makes_backup(tmp_path):
    f = tmp_path / "a.py"
    original = "def mul(a, b):\n    return a * b\n"
    f.write_text(original, encoding="utf-8")

    apply_edit(str(f), old_code="a * b", new_code="a * b * 2", skip_confirm=True)

    backup = f.with_suffix(f.suffix + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original


# ============================================================
# write_file
# ============================================================

def test_write_file_creates_and_refuses_overwrite(tmp_path):
    f = tmp_path / "new.py"

    out = write_file(str(f), "x = 1\n", skip_confirm=True)
    assert "[已新建]" in out
    assert f.read_text(encoding="utf-8") == "x = 1\n"

    # 默认不允许覆盖
    out = write_file(str(f), "x = 2\n", skip_confirm=True)
    assert "文件已存在" in out
    assert f.read_text(encoding="utf-8") == "x = 1\n"

    # 显式 overwrite=True 才允许
    out = write_file(str(f), "x = 2\n", overwrite=True, skip_confirm=True)
    assert "[已覆盖]" in out
    assert f.read_text(encoding="utf-8") == "x = 2\n"


# ============================================================
# search_code（只读，不依赖 LLM）
# ============================================================

def test_search_code_finds_keyword(tmp_path):
    (tmp_path / "m.py").write_text("def format_date(d):\n    return d\n", encoding="utf-8")

    out = search_code("format_date", path=str(tmp_path), file_glob="*.py")

    assert "format_date" in out
    assert "m.py" in out


def test_search_code_no_result_is_readable(tmp_path):
    out = search_code("zzz_not_exist_xxx", path=str(tmp_path))

    assert "[无结果]" in out or "[错误]" in out  # 无 rg 时降级为可读错误，不抛异常
