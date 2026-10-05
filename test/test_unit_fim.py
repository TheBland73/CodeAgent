"""
离线单元测试：FIM 补全工具（core/tools.py 的 fim_assist）。

核心思路：fim_assist 内部是"延迟导入" call_fim 的，所以只要在测试里
把 core.llm.call_fim 换成一个假函数，就能在不联网、不花 token 的前提下
验证「光标切分 → 补全 → 写盘」这条链路。

运行（项目根目录 CodeAgent/ 下）：
    python -m pytest -q
"""

import pytest

from core import llm as llm_mod
from core import ui as ui_mod
from core.tools import fim_assist


@pytest.fixture
def fake_fim(monkeypatch):
    """把 core.llm.call_fim 换成可控的桩，并记录收到的 prefix/suffix。"""
    captured = {}

    def _install(completion):
        def _fake_call_fim(prefix, suffix, model=None, max_tokens=128,
                           temperature=0.2, use_cache=True):
            captured["prefix"] = prefix
            captured["suffix"] = suffix
            captured["max_tokens"] = max_tokens
            return completion

        monkeypatch.setattr(llm_mod, "call_fim", _fake_call_fim)
        return captured

    return _install


def test_fim_assist_splits_prefix_and_suffix(tmp_path, fake_fim):
    f = tmp_path / "a.py"
    f.write_text("def add(a, b):\n    result = \n    return result\n", encoding="utf-8")

    captured = fake_fim("a + b")
    out = fim_assist(str(f), line=2, col=14, skip_confirm=True)

    assert captured["prefix"] == "def add(a, b):\n    result = "
    assert captured["suffix"] == "\n    return result\n"
    assert "[FIM 补全]" in out
    assert f.read_text(encoding="utf-8") == "def add(a, b):\n    result = a + b\n    return result\n"


def test_fim_assist_multiline_completion_keeps_structure(tmp_path, fake_fim):
    """补全自带缩进时，不能再补一个换行，否则会多出空行。"""
    f = tmp_path / "a.py"
    f.write_text("def f():\n\n    return x + y\n", encoding="utf-8")

    fake_fim("    x = 1\n    y = 2")
    fim_assist(str(f), line=2, col=1, skip_confirm=True)

    assert f.read_text(encoding="utf-8") == "def f():\n    x = 1\n    y = 2\n    return x + y\n"


def test_fim_assist_adds_newline_when_cursor_has_trailing_text(tmp_path, fake_fim):
    """光标后面还接着同一行的代码时，多行补全必须以换行收尾。"""
    f = tmp_path / "a.py"
    f.write_text("value = x + y\n", encoding="utf-8")

    fake_fim("a\nb")
    fim_assist(str(f), line=1, col=9, skip_confirm=True)

    assert f.read_text(encoding="utf-8") == "value = a\nb\nx + y\n"


def test_fim_assist_at_eof_uses_whole_file_as_prefix(tmp_path, fake_fim):
    f = tmp_path / "a.py"
    f.write_text("a = 1\n", encoding="utf-8")

    captured = fake_fim("b = 2\n")
    fim_assist(str(f), line=2, col=1, skip_confirm=True)

    assert captured["prefix"] == "a = 1\n"
    assert captured["suffix"] == ""
    assert f.read_text(encoding="utf-8") == "a = 1\nb = 2\n"


def test_fim_assist_empty_completion_changes_nothing(tmp_path, fake_fim):
    f = tmp_path / "a.py"
    original = "a = 1\n"
    f.write_text(original, encoding="utf-8")

    fake_fim("")
    out = fim_assist(str(f), line=2, col=1, skip_confirm=True)

    assert "[无补全]" in out
    assert f.read_text(encoding="utf-8") == original


def test_fim_assist_rejects_bad_position(tmp_path, fake_fim):
    f = tmp_path / "a.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")

    fake_fim("never used")
    assert "[错误] 行号" in fim_assist(str(f), line=99, col=1, skip_confirm=True)
    assert "[错误] 列号" in fim_assist(str(f), line=1, col=99, skip_confirm=True)
    assert "[错误] 文件不存在" in fim_assist(str(tmp_path / "nope.py"), line=1, col=1)
    assert f.read_text(encoding="utf-8") == "a = 1\nb = 2\n"


def test_fim_assist_reports_api_failure(tmp_path, monkeypatch):
    f = tmp_path / "a.py"
    f.write_text("a = 1\n", encoding="utf-8")

    def _boom(**kwargs):
        raise RuntimeError("网络不可用")

    monkeypatch.setattr(llm_mod, "call_fim", _boom)
    out = fim_assist(str(f), line=2, col=1, skip_confirm=True)

    assert "[错误] FIM 补全失败" in out
    assert f.read_text(encoding="utf-8") == "a = 1\n"


def test_fim_assist_user_rejection_keeps_file(tmp_path, fake_fim, monkeypatch):
    f = tmp_path / "a.py"
    original = "a = 1\n"
    f.write_text(original, encoding="utf-8")

    fake_fim("b = 2\n")
    monkeypatch.setattr(ui_mod, "ask_confirm", lambda: False)

    out = fim_assist(str(f), line=2, col=1, skip_confirm=False)

    assert "[已取消]" in out
    assert f.read_text(encoding="utf-8") == original
