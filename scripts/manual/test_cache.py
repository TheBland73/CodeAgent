# test_cache.py
from core.cache import fim_cache, search_cache
from core.llm import call_fim
from core.tools import search_code


def test_fim_cache():
    print("\n=== 测试 1: FIM 缓存 ===")
    prefix = "def add(a, b):\n    result = "
    suffix = "\n    return result"

    # 第一次：应该走网络
    r1 = call_fim(prefix=prefix, suffix=suffix)
    # 第二次：应该命中缓存
    r2 = call_fim(prefix=prefix, suffix=suffix)

    print(f"第一次结果: {r1!r}")
    print(f"第二次结果: {r2!r}")
    print(f"结果一致: {r1 == r2}")
    print(f"缓存统计: {fim_cache.stats()}")


def test_search_cache():
    print("\n=== 测试 2: 搜索缓存 ===")
    r1 = search_code("def ", path="core", file_glob="*.py", max_results=10)
    r2 = search_code("def ", path="core", file_glob="*.py", max_results=10)
    print(f"结果一致: {r1 == r2}")
    print(f"缓存统计: {search_cache.stats()}")


def test_cache_invalidation():
    """验证不同 suffix 不会被错误命中。"""
    print("\n=== 测试 3: 不同 suffix 不混淆 ===")
    prefix = "x = "
    r1 = call_fim(prefix=prefix, suffix="\nprint(x)")
    r2 = call_fim(prefix=prefix, suffix="\nreturn x")
    print(f"prefix 相同，suffix 不同 → 命中: {r1 == r2}（应该是 False 或内容相关，但绝不能是同一个缓存）")


if __name__ == "__main__":
    test_fim_cache()
    test_search_cache()
    test_cache_invalidation()