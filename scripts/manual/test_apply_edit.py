# test_apply_edit.py
from pathlib import Path
from core.tools import apply_edit

TEST_FILE = Path("test_edit_sample.py")

INITIAL = """def add(a, b):
    result = a - b
    return result


def sub(a, b):
    result = a - b
    return result


def mul(a, b):
    return a * b
"""


def setup():
    TEST_FILE.write_text(INITIAL, encoding="utf-8")


def show(title):
    print(f"\n--- {title} ---")
    print(TEST_FILE.read_text(encoding="utf-8"))


def case(name, **kwargs):
    print(f"\n{'=' * 50}")
    print(f"[{name}]")
    setup()
    result = apply_edit(**kwargs)
    print(result)
    show(name)


if __name__ == "__main__":
    # 1. 成功替换：old_code 唯一
    case(
        "成功替换（唯一匹配）",
        path=str(TEST_FILE),
        old_code="    return a * b\n",
        new_code="    return a * b * 1\n",
    )

    # 2. 不唯一：old_code 出现多次
    case(
        "不唯一（出现多次）",
        path=str(TEST_FILE),
        old_code="    result = a - b\n",
        new_code="    result = a + b\n",
    )

    # 3. 未找到：old_code 不存在
    case(
        "未找到",
        path=str(TEST_FILE),
        old_code="print('hello')\n",
        new_code="print('world')\n",
    )

    # 4. 唯一：带上更多上下文后可以唯一匹配
    case(
        "加长上下文后唯一",
        path=str(TEST_FILE),
        old_code=(
            "def add(a, b):\n"
            "    result = a - b\n"
            "    return result\n"
        ),
        new_code=(
            "def add(a, b):\n"
            "    result = a + b\n"
            "    return result\n"
        ),
    )

    # 5. 多行替换成单行
    case(
        "多行替换成单行",
        path=str(TEST_FILE),
        old_code=(
            "def mul(a, b):\n"
            "    return a * b\n"
        ),
        new_code="def mul(a, b): return a * b\n",
    )

    # 6. 删除：new_code 为空
    case(
        "删除一段代码",
        path=str(TEST_FILE),
        old_code="\n\ndef mul(a, b):\n    return a * b\n",
        new_code="\n",
    )

    # 7. 空 old_code
    print(f"\n{'=' * 50}")
    print("[空 old_code]")
    setup()
    print(apply_edit(str(TEST_FILE), old_code="", new_code="x"))

    # 8. 文件不存在
    print(f"\n{'=' * 50}")
    print("[文件不存在]")
    print(apply_edit("no_such_file.py", old_code="x", new_code="y"))