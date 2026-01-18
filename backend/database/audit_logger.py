import asyncio
from typing import Dict, Any, Optional
import asyncpg
import os
import time
import structlog

logger = structlog.get_logger()

class AuditLogger:
    def __init__(self):
        self.pool = None
        self._connected = False
    
    async def initialize(self):
        try:
            db_url = os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/network_ai"
            )
            
            self.pool = await asyncpg.create_pool(
                db_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            
            await self._create_tables()
            
            self._connected = True
            logger.info("audit_logger_init", event="database_connected")
            
        except Exception as e:
            logger.warning("audit_logger_init_failed", error=str(e))
            self._connected = False
    
    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orchestration_audit (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    issue TEXT NOT NULL,
                    priority VARCHAR(20),
                    consensus TEXT,
                    confidence FLOAT,
                    red_flagged BOOLEAN,
                    processing_time_ms INTEGER,
                    user_id VARCHAR(100),
                    context JSONB,
                    request_id VARCHAR(100)
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orchestration_timestamp 
                ON orchestration_audit(timestamp DESC)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orchestration_red_flagged 
                ON orchestration_audit(red_flagged) WHERE red_flagged = true
            """)
    
    async def log_orchestration(
        self,
        issue: str,
        priority: str,
        consensus: str,
        confidence: float,
        red_flagged: bool,
        processing_time_ms: int,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        if not self._connected or not self.pool:
            logger.warning("audit_log_skipped", reason="database_not_connected")
            return
        
        try:
            request_id = f"req_{int(time.time() * 1000)}"
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO orchestration_audit 
                    (issue, priority, consensus, confidence, red_flagged, 
                     processing_time_ms, user_id, context, request_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, issue, priority, consensus, confidence, red_flagged,
                     processing_time_ms, user_id, context, request_id)
            
            logger.info(
                "audit_logged",
                request_id=request_id,
                red_flagged=red_flagged
            )
            
        except Exception as e:
            logger.error("audit_log_failed", error=str(e))
    
    async def get_recent_audits(self, limit: int = 100) -> list:
        if not self._connected or not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM orchestration_audit 
                    ORDER BY timestamp DESC 
                    LIMIT $1
                """, limit)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("audit_fetch_failed", error=str(e))
            return []
    
    async def close(self):
        if self.pool:
            await self.pool.close()
            self._connected = False
            logger.info("audit_logger_closed")
    
    def is_connected(self) -> bool:
        return self._connected

audit_logger = AuditLogger()