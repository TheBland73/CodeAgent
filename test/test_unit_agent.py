"""
离线单元测试：Agent 循环（core/agent.py）。

用假的 LLM 响应替换真实 API 调用，验证循环控制逻辑：
    - 多步工具调用后能拿到最终答案
    - 空输出 / 非法 JSON 参数会被纠正后重试
    - max_steps 上限生效
    - max_edits 上限生效（写操作被拦截、只读工具放行）
    - execute_tool 永不抛异常

运行（项目根目录 CodeAgent/ 下）：
    python -m pytest -q
"""

from types import SimpleNamespace

import pytest

from core import agent as agent_mod


# ============================================================
# 伪造 LLM 响应
# ============================================================

class _StubCompletions:
    """按预设脚本依次返回响应；脚本用完后重复最后一条，避免死循环。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        idx = min(self.calls - 1, len(self.script) - 1)
        return self.script[idx]


class _StubClient:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=_StubCompletions(script))


def make_msg(content=None, tool_calls=None):
    """构造一个最小可用的 message 对象（用 dict 的形式传入，agent 用属性访问）。"""
    if tool_calls is None:
        calls = None
    else:
        calls = [
            SimpleNamespace(
                id=f"call_{i}",
                function=SimpleNamespace(name=name, arguments=arguments),
                model_dump=lambda i=i, name=name, arguments=arguments: {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                },
            )
            for i, (name, arguments) in enumerate(tool_calls)
        ]
    return SimpleNamespace(content=content, tool_calls=calls)


def make_response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def quiet_ui(monkeypatch):
    """关掉进度条式的 UI 输出，让测试输出干净。"""
    for name in (
        "print_step",
        "print_thinking",
        "print_tool_call",
        "print_tool_result",
        "print_no_tool_call",
        "print_correction",
    ):
        monkeypatch.setattr(agent_mod.ui, name, lambda *a, **k: None)


@pytest.fixture
def stub_llm(monkeypatch):
    """注入假客户端，返回一个可直接检查调用次数的 stub。"""
    def _install(script):
        stub = _StubClient(script)
        monkeypatch.setattr(agent_mod, "client", stub)
        return stub

    return _install


# ============================================================
# 测试
# ============================================================

def test_agent_returns_answer_without_tool_call(stub_llm, quiet_ui):
    stub = stub_llm([make_response(make_msg(content="直接回答"))])

    answer = agent_mod.run_agent("你好", verbose=False)

    assert answer == "直接回答"
    assert stub.chat.completions.calls == 1


def test_agent_executes_tool_then_answers(stub_llm, quiet_ui, monkeypatch):
    """第一步调用 read_file，第二步给出最终答案；messages 里应留下 tool 结果。"""
    seen = {}

    def fake_execute(name, arguments):
        seen["name"] = name
        seen["arguments"] = arguments
        return "[工具结果] 文件内容"

    monkeypatch.setattr(agent_mod, "execute_tool", fake_execute)

    stub_llm([
        make_response(make_msg(tool_calls=[("read_file", '{"path": "a.py"}')])),
        make_response(make_msg(content="读完了")),
    ])

    messages = None
    answer = agent_mod.run_agent("读一下 a.py", verbose=False, messages=messages)

    assert answer == "读完了"
    assert seen["name"] == "read_file"
    assert seen["arguments"] == '{"path": "a.py"}'


def test_agent_retries_after_empty_output(stub_llm, quiet_ui):
    """空输出应被纠正后重试，而不是直接返回空字符串。"""
    stub = stub_llm([
        make_response(make_msg(content=None, tool_calls=None)),
        make_response(make_msg(content="第二次成功了")),
    ])

    answer = agent_mod.run_agent("随便问点啥", verbose=False)

    assert answer == "第二次成功了"
    assert stub.chat.completions.calls == 2


def test_agent_stops_at_max_steps(stub_llm, quiet_ui, monkeypatch):
    """模型一直要求调用工具时，循环必须被 max_steps 截断。"""
    monkeypatch.setattr(agent_mod, "execute_tool", lambda name, arguments: "ok")

    stub = stub_llm([make_response(make_msg(tool_calls=[("read_file", '{"path": "a.py"}')]))])

    answer = agent_mod.run_agent("无限调用", verbose=False, max_steps=3)

    assert "最大步数 3" in answer
    assert stub.chat.completions.calls == 3


def test_max_edits_blocks_further_writes(stub_llm, quiet_ui, monkeypatch):
    """达到 max_edits 后，写操作被拦截；只读工具仍然放行。"""
    calls = []

    def fake_execute(name, arguments):
        calls.append(name)
        if name == "read_file":
            return "   1 | line"
        return "[已替换] a.py：1 处匹配（+1 -1）"

    monkeypatch.setattr(agent_mod, "execute_tool", fake_execute)

    stub_llm([
        make_response(make_msg(tool_calls=[("apply_edit", '{"path": "a.py"}')])),
        make_response(make_msg(tool_calls=[("apply_edit", '{"path": "b.py"}')])),
        make_response(make_msg(tool_calls=[("read_file", '{"path": "c.py"}')])),
        make_response(make_msg(content="收尾")),
    ])

    answer = agent_mod.run_agent("改文件", verbose=False, max_steps=6, max_edits=1)

    assert answer == "收尾"
    # apply_edit 只真正执行了一次，第二次被拦下；read_file 不受限制
    assert calls.count("apply_edit") == 1
    assert calls.count("read_file") == 1


def test_execute_tool_never_raises():
    assert "未知工具" in agent_mod.execute_tool("no_such_tool", "{}")
    assert "不是合法 JSON" in agent_mod.execute_tool("read_file", "{oops")
    # 参数不匹配也不应抛出
    assert "[错误]" in agent_mod.execute_tool("read_file", '{"wrong_arg": 1}')


def test_execute_tool_runs_real_read_file(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")

    out = agent_mod.execute_tool("read_file", '{"path": "%s"}' % str(f).replace("\\", "\\\\"))

    assert "x = 1" in out
