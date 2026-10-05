# core/cache.py
"""
带 TTL 和容量上限的内存缓存。

用于:
    - FIM 补全结果缓存（key = prefix + suffix + 参数）
    - 搜索结果缓存（key = query + 路径 + 过滤条件）
"""

import hashlib
import json
import time
from typing import Any, Optional


class TTLCache:
    """简单的 TTL + 容量上限内存缓存。"""

    def __init__(self, max_size: int = 128, ttl: float = 600.0):
        self._store: dict = {}
        self._max_size = max_size
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _key(self, *args) -> str:
        raw = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get(self, *args) -> Optional[Any]:
        k = self._key(*args)
        entry = self._store.get(k)
        if entry is None:
            self._misses += 1
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._store[k]
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, value: Any, *args) -> None:
        k = self._key(*args)
        if len(self._store) >= self._max_size:
            # FIFO 淘汰：删掉最早写入的一条
            oldest = min(self._store.items(), key=lambda kv: kv[1][1])
            del self._store[oldest[0]]
        self._store[k] = (value, time.time())

    def stats(self) -> dict:
        total = self._hits + self._misses
        rate = (self._hits / total * 100) if total else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "hit_rate": f"{rate:.1f}%",
        }

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0


# 模块级单例
fim_cache = TTLCache(max_size=128, ttl=600.0)
search_cache = TTLCache(max_size=256, ttl=300.0)