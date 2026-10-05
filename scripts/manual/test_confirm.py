# test_confirm.py
from pathlib import Path
from unittest.mock import patch
from core.tools import apply_edit

TEST_FILE = Path("test_confirm_sample.py")

INITIAL = """def add(a, b):
    result = a - b
    return result
"""


def setup():
    TEST_FILE.write_text(INITIAL, encoding="utf-8")
    # 清理旧备份
    bak = TEST_FILE.with_suffix(TEST_FILE.suffix + ".bak")
    if bak.exists():
        bak.unlink()


def run(label, user_input):
    print(f"\n{'=' * 60}")
    print(f"[{label}]")
    print(f"{'=' * 60}")
    setup()

    with patch("builtins.input", return_value=user_input):
        result = apply_edit(
            str(TEST_FILE),
            old_code="    result = a - b\n",
            new_code="    result = a + b\n",
        )
    print(f"返回: {result}")
    print(f"文件内容:\n{TEST_FILE.read_text(encoding='utf-8')}")

    bak = TEST_FILE.with_suffix(TEST_FILE.suffix + ".bak")
    print(f"备份存在: {bak.exists()}")


if __name__ == "__main__":
    run("用户输入 y —— 应确认并备份", "y")
    run("用户输入 n —— 应取消且无备份", "n")
    run("用户输入空 —— 应取消", "")
    run("用户输入 Y（大写）—— 应确认", "Y")