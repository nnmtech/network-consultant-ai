import asyncio
import hashlib
import msgpack
import os
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, Dict, List
import structlog
from filelock import FileLock, Timeout

logger = structlog.get_logger()

class RobustCacheManager:
    def __init__(
        self,
        cache_dir: str = "/var/cache/network-ai",
        shards: int = 8,
        lock_timeout: int = 30,
        lock_retry_interval: float = 0.1,
        max_lock_attempts: int = 3,
    ):
        self.cache_dir = Path(cache_dir)
        self.shards = shards
        self.lock_timeout = lock_timeout
        self.lock_retry_interval = lock_retry_interval
        self.max_lock_attempts = max_lock_attempts
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir = self.cache_dir / ".locks"
        self.lock_dir.mkdir(exist_ok=True)
        
        self._stats = {
            "hits": 0,
            "misses": 0,
            "lock_timeouts": 0,
            "lock_recoveries": 0,
        }
        
        logger.info(
            "cache_init",
            cache_dir=str(self.cache_dir),
            shards=self.shards,
            lock_timeout=self.lock_timeout
        )
    
    def _generate_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        data = msgpack.packb(
            {"func": func_name, "args": args, "kwargs": kwargs},
            use_bin_type=True
        )
        return hashlib.blake2b(data, digest_size=16).hexdigest()
    
    def _get_shard_path(self, key: str) -> Path:
        shard_id = int(key[:2], 16) % self.shards
        shard_dir = self.cache_dir / f"shard_{shard_id}"
        shard_dir.mkdir(exist_ok=True)
        return shard_dir / f"{key}.cache"
    
    def _get_lock_path(self, key: str) -> Path:
        return self.lock_dir / f"{key}.lock"
    
    async def _is_lock_stale(self, lock_path: Path, max_age: int = 300) -> bool:
        if not lock_path.exists():
            return False
        
        try:
            age = time.time() - lock_path.stat().st_mtime
            return age > max_age
        except OSError:
            return False
    
    async def cleanup_stale_locks(self, max_age: int = 300):
        cleaned = 0
        for lock_file in self.lock_dir.glob("*.lock"):
            if await self._is_lock_stale(lock_file, max_age):
                try:
                    lock = FileLock(str(lock_file), timeout=0.1)
                    try:
                        lock.acquire(timeout=0.1)
                        lock_file.unlink(missing_ok=True)
                        lock.release()
                        cleaned += 1
                        self._stats["lock_recoveries"] += 1
                    except Timeout:
                        pass
                except Exception as e:
                    logger.warning(
                        "lock_cleanup_failed",
                        lock_file=str(lock_file),
                        error=str(e)
                    )
        
        if cleaned > 0:
            logger.info("stale_locks_cleaned", count=cleaned)
    
    async def get(self, key: str) -> Optional[Any]:
        cache_path = self._get_shard_path(key)
        lock_path = self._get_lock_path(key)
        
        if not cache_path.exists():
            self._stats["misses"] += 1
            return None
        
        lock = FileLock(str(lock_path), timeout=self.lock_timeout)
        
        try:
            lock.acquire(timeout=self.lock_timeout)
            try:
                with open(cache_path, "rb") as f:
                    data = msgpack.unpackb(f.read(), raw=False)
                
                if data["expires_at"] and time.time() > data["expires_at"]:
                    cache_path.unlink(missing_ok=True)
                    self._stats["misses"] += 1
                    return None
                
                self._stats["hits"] += 1
                return data["value"]
            finally:
                lock.release()
        except Timeout:
            self._stats["lock_timeouts"] += 1
            logger.warning("cache_get_timeout", key=key)
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
        tag: Optional[str] = None
    ):
        cache_path = self._get_shard_path(key)
        lock_path = self._get_lock_path(key)
        
        lock = FileLock(str(lock_path), timeout=self.lock_timeout)
        
        try:
            lock.acquire(timeout=self.lock_timeout)
            try:
                data = {
                    "value": value,
                    "expires_at": time.time() + expire if expire else None,
                    "tag": tag,
                    "created_at": time.time(),
                }
                
                with open(cache_path, "wb") as f:
                    f.write(msgpack.packb(data, use_bin_type=True))
            finally:
                lock.release()
        except Timeout:
            self._stats["lock_timeouts"] += 1
            logger.warning("cache_set_timeout", key=key)
    
    async def invalidate_tag(self, tag: str):
        removed = 0
        for shard_dir in self.cache_dir.glob("shard_*"):
            for cache_file in shard_dir.glob("*.cache"):
                try:
                    with open(cache_file, "rb") as f:
                        data = msgpack.unpackb(f.read(), raw=False)
                    
                    if data.get("tag") == tag:
                        cache_file.unlink(missing_ok=True)
                        removed += 1
                except Exception:
                    pass
        
        logger.info("tag_invalidated", tag=tag, removed=removed)
    
    async def clear_all(self):
        for shard_dir in self.cache_dir.glob("shard_*"):
            for cache_file in shard_dir.glob("*.cache"):
                cache_file.unlink(missing_ok=True)
        logger.info("cache_cleared")
    
    async def get_stats(self) -> Dict[str, Any]:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0
        
        return {
            **self._stats,
            "hit_rate": round(hit_rate, 3),
            "total_requests": total,
        }
    
    async def health_check(self) -> bool:
        try:
            test_key = "__health_check__"
            await self.set(test_key, {"status": "ok"}, expire=60)
            result = await self.get(test_key)
            return result is not None
        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            return False
    
    def memoize(
        self,
        expire: Optional[int] = None,
        tag: Optional[str] = None
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                key = self._generate_key(func.__name__, args, kwargs)
                
                cached = await self.get(key)
                if cached is not None:
                    return cached
                
                result = await func(*args, **kwargs)
                await self.set(key, result, expire=expire, tag=tag)
                
                return result
            return wrapper
        return decorator

robust_cache = RobustCacheManager(
    cache_dir=os.getenv("CACHE_DIR", "/var/cache/network-ai"),
    shards=int(os.getenv("CACHE_SHARDS", "8")),
    lock_timeout=int(os.getenv("CACHE_LOCK_TIMEOUT", "30")),
    lock_retry_interval=float(os.getenv("CACHE_LOCK_RETRY_INTERVAL", "0.1")),
    max_lock_attempts=int(os.getenv("CACHE_MAX_LOCK_ATTEMPTS", "3")),
)