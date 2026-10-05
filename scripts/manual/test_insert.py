# test_insert.py
from pathlib import Path
from core.tools import insert_at_cursor

TEST_FILE = Path("test_insert_sample.py")

INITIAL = """def add(a, b):
    result = 
    return result
"""


def setup():
    TEST_FILE.write_text(INITIAL, encoding="utf-8")


def show(title):
    print(f"\n--- {title} ---")
    print(repr(TEST_FILE.read_text(encoding="utf-8")))
    print(TEST_FILE.read_text(encoding="utf-8"))


def case(name, **kwargs):
    print(f"\n{'=' * 50}")
    print(f"[{name}]")
    setup()
    result = insert_at_cursor(**kwargs)
    print(result)
    show(name)


if __name__ == "__main__":
    # 1. 行内插入：在第 2 行第 14 列（"result = " 之后）
    case("行内插入", path=str(TEST_FILE), line=2, col=14, text="a + b")

    # 2. 行首插入：在第 1 行第 1 列
    case("行首插入", path=str(TEST_FILE), line=1, col=1, text="# comment\n")

    # 3. 行尾插入：第 2 行行尾（col = 行长度 + 1）
    case("行尾插入", path=str(TEST_FILE), line=2, col=len("    result = ") + 1, text="  # 计算")

    # 4. 多行插入
    case("多行插入", path=str(TEST_FILE), line=2, col=1, text="    # 步骤 1\n    # 步骤 2\n")

    # 5. 列号超范围
    case("列号超范围", path=str(TEST_FILE), line=2, col=999, text="x")

    # 6. 行号超范围
    case("行号超范围", path=str(TEST_FILE), line=99, col=1, text="x")

    # 7. 文件不存在
    print(f"\n{'=' * 50}")
    print("[文件不存在]")
    print(insert_at_cursor("no_such_file.py", line=1, col=1, text="x"))