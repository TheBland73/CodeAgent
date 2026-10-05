# test_tools.py
"""
单独测试 tools.py 中的工具函数。
不涉及 LLM，不涉及 Agent 循环。
"""

from core.tools import search_code, read_file


def test_search_code():
    print("=" * 60)
    print("测试 1: search_code('def ', path='core', file_glob='*.py')")
    print("=" * 60)
    result = search_code("def ", path="core", file_glob="*.py", max_results=10)
    print(result)
    print()


def test_search_code_no_result():
    print("=" * 60)
    print("测试 2: search_code('zzz_not_exist_xxx')")
    print("=" * 60)
    result = search_code("zzz_not_exist_xxx", path="core")
    print(result)
    print()


def test_read_file_full():
    print("=" * 60)
    print("测试 3: read_file('core/config.py')")
    print("=" * 60)
    result = read_file("core/config.py")
    print(result)
    print()


def test_read_file_range():
    print("=" * 60)
    print("测试 4: read_file('core/tools.py', start_line=1, end_line=10)")
    print("=" * 60)
    result = read_file("core/tools.py", start_line=1, end_line=10)
    print(result)
    print()


def test_read_file_not_found():
    print("=" * 60)
    print("测试 5: read_file('no_such_file.py')")
    print("=" * 60)
    result = read_file("no_such_file.py")
    print(result)
    print()


if __name__ == "__main__":
    test_search_code()
    test_search_code_no_result()
    test_read_file_full()
    test_read_file_range()
    test_read_file_not_found()