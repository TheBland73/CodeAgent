"""
search_code 的内置搜索兜底路径（没有安装 ripgrep 时）。

不访问网络，也不依赖本机是否装了 rg：
用 monkeypatch 把 core.tools._find_rg 的返回值改成 None，强制走兜底分支。

运行：python -m pytest test/test_unit_search_fallback.py -q
"""

import pytest

from core.tools import search_code


@pytest.fixture
def no_rg(monkeypatch):
    """模拟一台没装 ripgrep 的机器。"""
    monkeypatch.setattr("core.tools._find_rg", lambda: None)


@pytest.fixture
def project(tmp_path):
    """造一个小项目：两个源文件 + 一个应被跳过的缓存目录。"""
    (tmp_path / "main.py").write_text(
        "def format_date(d):\n    return d\n", encoding="utf-8"
    )
    (tmp_path / "helper.py").write_text(
        "def format_date(d, fmt):\n    return fmt\n", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("format_date 在这里也出现\n", encoding="utf-8")
    junk = tmp_path / "__pycache__"
    junk.mkdir()
    (junk / "cached.py").write_text("format_date 不该被搜到\n", encoding="utf-8")
    return tmp_path


def test_fallback_finds_keyword_without_rg(no_rg, project):
    out = search_code("format_date", path=str(project), use_cache=False)

    assert "format_date" in out
    assert "没有 ripgrep" not in out          # 不再返回错误
    assert "[错误]" not in out


def test_fallback_output_is_file_line_content(no_rg, project):
    out = search_code("format_date", path=str(project), use_cache=False)

    lines = [ln for ln in out.splitlines() if "format_date" in ln]
    assert lines, "至少应有一行命中"
    for ln in lines:
        head, _, content = ln.partition(":")
        line_no, _, text = content.partition(":")
        assert head.endswith(".py") or head.endswith(".txt")
        assert line_no.isdigit()
        assert "format_date" in text


def test_fallback_reports_line_numbers(no_rg, project):
    out = search_code(r"^\s*return d", path=str(project), use_cache=False)

    assert "main.py:2:    return d" in out


def test_fallback_skips_junk_dirs(no_rg, project):
    out = search_code("不该被搜到", path=str(project), use_cache=False)

    assert "__pycache__" not in out
    assert "[无结果]" in out


def test_fallback_respects_file_glob(no_rg, project):
    out = search_code("format_date", path=str(project), file_glob="*.txt", use_cache=False)

    assert "notes.txt" in out
    assert "main.py" not in out


def test_fallback_supports_negative_glob(no_rg, project):
    out = search_code("format_date", path=str(project), file_glob="!*.txt", use_cache=False)

    assert "notes.txt" not in out
    assert "main.py" in out


def test_fallback_no_result_is_readable(no_rg, project):
    out = search_code("zzz_not_exist_xxx", path=str(project), use_cache=False)

    assert "[无结果]" in out


def test_fallback_truncates_per_file(no_rg, tmp_path):
    (tmp_path / "many.py").write_text("hit\n" * 50, encoding="utf-8")

    out = search_code("hit", path=str(tmp_path), max_results=5, use_cache=False)

    assert out.count("many.py:") == 5
    assert "已截断" in out


def test_fallback_invalid_regex_is_readable(no_rg, project):
    out = search_code("([unclosed", path=str(project), use_cache=False)

    assert "[错误]" in out
    assert "正则" in out


def test_fallback_missing_path_is_readable(no_rg, tmp_path):
    out = search_code("x", path=str(tmp_path / "nope"), use_cache=False)

    assert "[错误]" in out
    assert "路径不存在" in out


def test_fallback_context_lines_use_dash(no_rg, project):
    out = search_code("format_date", path=str(project), context_lines=1, use_cache=False)

    lines = out.splitlines()
    # 命中行用 ':' 分隔
    assert "main.py:1:def format_date(d):" in lines
    # 上下文行（非命中行）用 '-' 分隔，与 ripgrep 的 --context 输出一致
    assert "main.py:2-    return d" in lines


def test_fallback_single_file_path(no_rg, project):
    out = search_code("format_date", path=str(project / "main.py"), use_cache=False)

    assert "main.py:1:def format_date(d):" in out
