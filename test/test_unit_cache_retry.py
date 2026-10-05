"""
离线单元测试：缓存与重试（core/cache.py、core/llm.py）。

不访问网络：ttl 用 monkeypatch 控制时间，重试用假的失败函数。

运行（项目根目录 CodeAgent/ 下）：
    python -m pytest -q
"""

import time

import pytest

from core.cache import TTLCache
from core.llm import _retry_call


# ============================================================
# TTLCache
# ============================================================

def test_cache_hit_and_miss():
    cache = TTLCache(max_size=8, ttl=60)

    assert cache.get("k") is None          # 未写入 → miss
    cache.set("v", "k")
    assert cache.get("k") == "v"           # 命中
    assert cache.stats()["hits"] == 1
    assert cache.stats()["misses"] == 1


def test_cache_key_includes_all_arguments():
    """回归测试：prefix 相同但 suffix/参数不同，绝不能命中同一条缓存。"""
    cache = TTLCache(max_size=8, ttl=60)

    cache.set("补全A", "prefix", "suffix-A", 128, 0.2)

    assert cache.get("prefix", "suffix-A", 128, 0.2) == "补全A"
    assert cache.get("prefix", "suffix-B", 128, 0.2) is None
    assert cache.get("prefix", "suffix-A", 64, 0.2) is None
    assert cache.get("prefix", "suffix-A", 128, 0.9) is None


def test_cache_expires_after_ttl():
    cache = TTLCache(max_size=8, ttl=10)
    cache.set("v", "k")

    # 伪造"已经过了 11 秒"
    real_time = time.time
    try:
        time.time = lambda: real_time() + 11
        assert cache.get("k") is None
    finally:
        time.time = real_time


def test_cache_evicts_when_full():
    cache = TTLCache(max_size=2, ttl=60)
    cache.set("v1", "k1")
    time.sleep(0.01)
    cache.set("v2", "k2")
    time.sleep(0.01)
    cache.set("v3", "k3")   # 超容量 → 淘汰最早写入的 k1

    assert cache.get("k1") is None
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"
    assert cache.stats()["size"] == 2


def test_cache_clear():
    cache = TTLCache(max_size=8, ttl=60)
    cache.set("v", "k")
    cache.get("k")

    cache.clear()

    assert cache.stats() == {"hits": 0, "misses": 0, "size": 0, "hit_rate": "0.0%"}


# ============================================================
# _retry_call
# ============================================================

class _FlakyError(Exception):
    pass


def test_retry_eventually_succeeds(monkeypatch):
    monkeypatch.setattr("core.llm.RETRYABLE_EXCEPTIONS", (_FlakyError,))
    monkeypatch.setattr("core.llm.time.sleep", lambda s: None)   # 不真的等待

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _FlakyError("网络抖动")
        return "success"

    assert _retry_call(flaky, max_retries=3, base_delay=0.01) == "success"
    assert attempts["n"] == 3


def test_retry_raises_after_exhausting(monkeypatch):
    monkeypatch.setattr("core.llm.RETRYABLE_EXCEPTIONS", (_FlakyError,))
    monkeypatch.setattr("core.llm.time.sleep", lambda s: None)

    attempts = {"n": 0}

    def always_fail():
        attempts["n"] += 1
        raise _FlakyError("一直失败")

    with pytest.raises(_FlakyError):
        _retry_call(always_fail, max_retries=3, base_delay=0.01)

    assert attempts["n"] == 3


def test_non_retryable_error_is_not_retried(monkeypatch):
    monkeypatch.setattr("core.llm.time.sleep", lambda s: None)

    attempts = {"n": 0}

    def bad_request():
        attempts["n"] += 1
        raise ValueError("参数错误不该重试")

    with pytest.raises(ValueError):
        _retry_call(bad_request, max_retries=3, base_delay=0.01)

    assert attempts["n"] == 1
