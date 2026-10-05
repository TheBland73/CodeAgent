# test_diff.py
from pathlib import Path
from core.tools import apply_edit, insert_at_cursor

TEST_FILE = Path("test_diff_sample.py")

INITIAL = """def add(a, b):
    result = 
    return result


def mul(a, b):
    return a * b
"""


def setup():
    TEST_FILE.write_text(INITIAL, encoding="utf-8")


def run(label, fn):
    print(f"\n{'=' * 60}")
    print(f"[{label}]")
    print(f"{'=' * 60}")
    setup()
    print(fn())


if __name__ == "__main__":
    run("apply_edit - 单行替换", lambda: apply_edit(
        str(TEST_FILE),
        old_code="    result = a - b\n",
        new_code="    result = a + b\n",
    ))

    run("apply_edit - 多行替换", lambda: apply_edit(
        str(TEST_FILE),
        old_code="def mul(a, b):\n    return a * b\n",
        new_code="def mul(a, b):\n    return a * b * 2\n",
    ))

    run("apply_edit - 删除", lambda: apply_edit(
        str(TEST_FILE),
        old_code="\n\ndef mul(a, b):\n    return a * b\n",
        new_code="\n",
    ))

    run("insert_at_cursor - 行内插入", lambda: insert_at_cursor(
        str(TEST_FILE),
        line=2,
        col=14,
        text="a + b",
    ))

    run("insert_at_cursor - 行首插入", lambda: insert_at_cursor(
        str(TEST_FILE),
        line=1,
        col=1,
        text="# 这是新注释\n",
    ))