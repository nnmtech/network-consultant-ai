import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import msgpack
from filelock import FileLock, Timeout
import structlog
from functools import wraps

logger = structlog.get_logger()

class RobustCacheManager:
    def __init__(self):
        self.cache_dir = Path(os.getenv("CACHE_DIR", "/var/cache/network-ai"))
        self.shards = int(os.getenv("CACHE_SHARDS", 8))
        self.lock_timeout = int(os.getenv("CACHE_LOCK_TIMEOUT", 30))
        self.lock_retry_interval = float(os.getenv("CACHE_LOCK_RETRY_INTERVAL", 0.1))
        self.max_lock_attempts = int(os.getenv("CACHE_MAX_LOCK_ATTEMPTS", 3))
        
        self.lock_dir = self.cache_dir / ".locks"
        self.data_dir = self.cache_dir / ".data"
        self.tag_dir = self.cache_dir / ".tags"
        
        self._initialized = False
    
    async def initialize(self):
        """Initialize cache directories and clean stale locks"""
        if self._initialized:
            return
        
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.lock_dir.mkdir(exist_ok=True)
            self.data_dir.mkdir(exist_ok=True)
            self.tag_dir.mkdir(exist_ok=True)
            
            await self._cleanup_stale_locks()
            
            self._initialized = True
            logger.info("cache_initialized", cache_dir=str(self.cache_dir), shards=self.shards)
        except Exception as e:
            logger.error("cache_initialization_failed", error=str(e))
            raise
    
    async def _cleanup_stale_locks(self):
        """Clean up stale locks from crashed workers"""
        cleaned = 0
        for lock_file in self.lock_dir.glob("*.lock"):
            try:
                lock = FileLock(str(lock_file), timeout=0.1)
                if lock.acquire(blocking=False):
                    lock.release()
                    lock_file.unlink(missing_ok=True)
                    cleaned += 1
            except (Timeout, OSError):
                pass
        
        if cleaned > 0:
            logger.info("stale_locks_cleaned", count=cleaned)
    
    def _generate_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """Generate stable cache key using Blake2b + msgpack"""
        func_name = f"{func.__module__}.{func.__qualname__}"
        
        try:
            serialized = msgpack.packb((func_name, args, kwargs), use_bin_type=True)
        except Exception as e:
            logger.warning("serialization_fallback", error=str(e))
            serialized = str((func_name, args, kwargs)).encode()
        
        key_hash = hashlib.blake2b(serialized, digest_size=32).hexdigest()
        return key_hash
    
    def _get_shard_path(self, key: str) -> Path:
        """Determine shard directory for key"""
        shard_id = int(key[:4], 16) % self.shards
        shard_dir = self.data_dir / f"shard_{shard_id}"
        shard_dir.mkdir(exist_ok=True)
        return shard_dir / f"{key}.msgpack"
    
    def _get_lock_path(self, key: str) -> Path:
        """Get lock file path for key"""
        return self.lock_dir / f"{key}.lock"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with lock safety"""
        cache_file = self._get_shard_path(key)
        
        if not cache_file.exists():
            return None
        
        lock = FileLock(str(self._get_lock_path(key)), timeout=self.lock_timeout)
        
        try:
            with lock.acquire(timeout=self.lock_timeout):
                if not cache_file.exists():
                    return None
                
                with open(cache_file, "rb") as f:
                    data = msgpack.unpackb(f.read(), raw=False)
                
                if data["expire"] and time.time() > data["expire"]:
                    cache_file.unlink(missing_ok=True)
                    return None
                
                return data["value"]
        except Timeout:
            logger.warning("cache_get_timeout", key=key)
            return None
        except Exception as e:
            logger.error("cache_get_failed", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None, tag: Optional[str] = None):
        """Set value in cache with lock safety"""
        cache_file = self._get_shard_path(key)
        lock = FileLock(str(self._get_lock_path(key)), timeout=self.lock_timeout)
        
        try:
            with lock.acquire(timeout=self.lock_timeout):
                data = {
                    "value": value,
                    "expire": time.time() + expire if expire else None,
                    "tag": tag,
                    "created": time.time()
                }
                
                with open(cache_file, "wb") as f:
                    f.write(msgpack.packb(data, use_bin_type=True))
                
                if tag:
                    await self._add_to_tag(tag, key)
        except Timeout:
            logger.warning("cache_set_timeout", key=key)
        except Exception as e:
            logger.error("cache_set_failed", key=key, error=str(e))
    
    async def _add_to_tag(self, tag: str, key: str):
        """Add key to tag index"""
        tag_file = self.tag_dir / f"{tag}.tags"
        lock = FileLock(str(self.lock_dir / f"tag_{tag}.lock"), timeout=5)
        
        try:
            with lock.acquire(timeout=5):
                keys = set()
                if tag_file.exists():
                    with open(tag_file, "rb") as f:
                        keys = set(msgpack.unpackb(f.read(), raw=False))
                
                keys.add(key)
                
                with open(tag_file, "wb") as f:
                    f.write(msgpack.packb(list(keys), use_bin_type=True))
        except Exception as e:
            logger.error("tag_index_update_failed", tag=tag, error=str(e))
    
    async def invalidate_tag(self, tag: str):
        """Invalidate all cache entries with tag"""
        tag_file = self.tag_dir / f"{tag}.tags"
        
        if not tag_file.exists():
            return
        
        lock = FileLock(str(self.lock_dir / f"tag_{tag}.lock"), timeout=10)
        
        try:
            with lock.acquire(timeout=10):
                with open(tag_file, "rb") as f:
                    keys = msgpack.unpackb(f.read(), raw=False)
                
                for key in keys:
                    cache_file = self._get_shard_path(key)
                    cache_file.unlink(missing_ok=True)
                
                tag_file.unlink(missing_ok=True)
                
                logger.info("tag_invalidated", tag=tag, keys_removed=len(keys))
        except Exception as e:
            logger.error("tag_invalidation_failed", tag=tag, error=str(e))
    
    async def clear_all(self):
        """Clear entire cache"""
        import shutil
        try:
            shutil.rmtree(self.data_dir)
            shutil.rmtree(self.tag_dir)
            self.data_dir.mkdir(exist_ok=True)
            self.tag_dir.mkdir(exist_ok=True)
            logger.info("cache_cleared")
        except Exception as e:
            logger.error("cache_clear_failed", error=str(e))
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_files = sum(1 for _ in self.data_dir.rglob("*.msgpack"))
        total_size = sum(f.stat().st_size for f in self.data_dir.rglob("*.msgpack"))
        
        return {
            "total_entries": total_files,
            "total_size_bytes": total_size,
            "shards": self.shards,
            "cache_dir": str(self.cache_dir)
        }
    
    def memoize(self, expire: int = 3600, tag: Optional[str] = None):
        """Decorator for caching function results"""
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self._initialized:
                    await self.initialize()
                
                key = self._generate_key(func, args, kwargs)
                
                cached = await self.get(key)
                if cached is not None:
                    logger.debug("cache_hit", function=func.__name__, key=key[:12])
                    return cached
                
                logger.debug("cache_miss", function=func.__name__, key=key[:12])
                result = await func(*args, **kwargs)
                
                await self.set(key, result, expire=expire, tag=tag)
                
                return result
            
            return wrapper
        return decorator

robust_cache = RobustCacheManager()