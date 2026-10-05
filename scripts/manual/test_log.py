# test_log.py
import json
from pathlib import Path
from unittest.mock import patch
from core.tools import apply_edit, LOG_FILE

TEST_FILE = Path("test_log_sample.py")

INITIAL = """def add(a, b):
    result = a - b
    return result
"""


def setup():
    TEST_FILE.write_text(INITIAL, encoding="utf-8")
    # 清空日志，方便看清本次产生的条目
    if LOG_FILE.exists():
        LOG_FILE.unlink()


def show_log():
    print("\n--- 日志内容 ---")
    if not LOG_FILE.exists():
        print("(无日志)")
        return
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    setup()

    # 1) 成功修改
    print("=" * 60)
    print("[1] 成功修改")
    print("=" * 60)
    with patch("builtins.input", return_value="y"):
        result = apply_edit(
            str(TEST_FILE),
            old_code="    result = a - b\n",
            new_code="    result = a + b\n",
        )
    print(result)

    # 2) 拒绝修改（应当也记一条 rejected）
    print("\n" + "=" * 60)
    print("[2] 拒绝修改")
    print("=" * 60)
    with patch("builtins.input", return_value="n"):
        result = apply_edit(
            str(TEST_FILE),
            old_code="    result = a + b\n",
            new_code="    result = a * b\n",
        )
    print(result)

    show_log()