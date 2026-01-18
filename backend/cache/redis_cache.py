import asyncio
from typing import Any, Optional
import json
import os
import structlog

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = structlog.get_logger()

class RedisCache:
    def __init__(self):
        self.client = None
        self._connected = False
    
    async def initialize(self):
        if not REDIS_AVAILABLE:
            logger.warning("redis_unavailable", msg="redis package not installed")
            return
        
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            
            self.client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            
            await self.client.ping()
            self._connected = True
            
            logger.info("redis_init", event="redis_connected")
            
        except Exception as e:
            logger.warning("redis_init_failed", error=str(e))
            self._connected = False
    
    async def get(self, key: str) -> Optional[Any]:
        if not self._connected or not self.client:
            return None
        
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("redis_get_failed", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, expire: int = 3600):
        if not self._connected or not self.client:
            return
        
        try:
            await self.client.setex(
                key,
                expire,
                json.dumps(value)
            )
        except Exception as e:
            logger.error("redis_set_failed", key=key, error=str(e))
    
    async def delete(self, key: str):
        if not self._connected or not self.client:
            return
        
        try:
            await self.client.delete(key)
        except Exception as e:
            logger.error("redis_delete_failed", key=key, error=str(e))
    
    async def close(self):
        if self.client:
            await self.client.close()
            self._connected = False
            logger.info("redis_closed")
    
    def is_connected(self) -> bool:
        return self._connected

redis_cache = RedisCache()