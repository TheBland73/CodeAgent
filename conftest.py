"""
pytest 公共配置。

做四件事：
1. 注入一个占位 API Key：core.config 在导入时就会校验 DEEPSEEK_API_KEY，
   缺失直接抛 ValueError。CI 里没有 .env（也不会提交 .env），不注入的话
   3 个测试模块会在"收集阶段"就报错。占位 Key 只用于导入，测试全程不联网。
2. 把仓库根目录加入 sys.path，保证在任何工作目录下都能 import core；
3. 把写盘日志重定向到临时目录，避免跑一次测试就往仓库的 .agent_log/ 里塞
   一堆 pytest 临时路径的记录（日志是运行产物，不该由测试产生）；
4. 把 pytest 的 basetemp 钉在仓库内的临时目录：某些环境里子进程解析出的
   系统临时目录不可写，pytest 会退回"当前目录/pytest-of-<用户名>"，在项目里留垃圾。
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

# 必须在导入 core.* 之前注入：core.config 导入时就会读它
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-placeholder-not-a-real-key")

# 把仓库根目录（core/ 的父目录）加入 sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 所有测试产物集中在这里，已由 .gitignore 忽略
TEST_TMP = ROOT / "_pytest-tmp"
# 测试期间的写盘日志（在 basetemp 之外，避免被 pytest 每次清空）
TEST_LOG_DIR = TEST_TMP / ".agent-log"


def pytest_configure(config):
    """把 tmp_path 的根目录固定到仓库内，并清理上一轮的 basetemp。"""
    basetemp = TEST_TMP / "basetemp"
    if basetemp.exists():
        shutil.rmtree(basetemp, ignore_errors=True)
    config.option.basetemp = str(basetemp)


@pytest.fixture(autouse=True)
def _isolate_edit_log(monkeypatch):
    """所有测试统一把 core.tools 的写盘日志指向临时目录。"""
    TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.tools.LOG_DIR", TEST_LOG_DIR, raising=False)
    monkeypatch.setattr("core.tools.LOG_FILE", TEST_LOG_DIR / "edit.log", raising=False)
    yield
