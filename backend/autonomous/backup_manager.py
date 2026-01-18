import asyncio
import json
import os
import time
from typing import Dict, List, Optional
import structlog
from pathlib import Path
import gzip
import shutil

logger = structlog.get_logger()

class BackupManager:
    """
    Automated backup and restore for configuration and state.
    """
    
    def __init__(self, backup_dir: str = "./backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.running = False
        self.task = None
        self.backup_interval = 3600  # 1 hour
        self.max_backups = 24  # Keep 24 hours of backups
        
    async def start(self):
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._backup_loop())
        logger.info("backup_manager_started", interval=self.backup_interval)
    
    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("backup_manager_stopped")
    
    async def _backup_loop(self):
        while self.running:
            try:
                await self.create_backup()
                await self._cleanup_old_backups()
                await asyncio.sleep(self.backup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("backup_loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(self.backup_interval)
    
    async def create_backup(self, backup_name: Optional[str] = None) -> str:
        if not backup_name:
            backup_name = f"backup_{int(time.time())}"
        
        backup_path = self.backup_dir / f"{backup_name}.json.gz"
        
        try:
            backup_data = await self._collect_backup_data()
            
            with gzip.open(backup_path, 'wt', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2)
            
            logger.info(
                "backup_created",
                backup_name=backup_name,
                size_bytes=backup_path.stat().st_size
            )
            
            return str(backup_path)
            
        except Exception as e:
            logger.error("backup_creation_failed", error=str(e), exc_info=True)
            raise
    
    async def _collect_backup_data(self) -> Dict:
        from backend.cache.robust_cache import robust_cache
        from backend.autonomous.health_monitor import health_monitor
        from backend.autonomous.alert_manager import alert_manager
        
        return {
            "timestamp": time.time(),
            "version": "2.1.0",
            "cache_stats": await robust_cache.get_stats(),
            "health_summary": health_monitor.get_health_summary(),
            "health_history": health_monitor.get_health_history(limit=100),
            "alerts": alert_manager.get_all_alerts(limit=500),
            "alert_summary": alert_manager.get_alert_summary()
        }
    
    async def restore_backup(self, backup_path: str) -> bool:
        try:
            with gzip.open(backup_path, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            logger.info(
                "backup_restored",
                timestamp=backup_data.get("timestamp"),
                version=backup_data.get("version")
            )
            
            return True
            
        except Exception as e:
            logger.error("backup_restore_failed", error=str(e), exc_info=True)
            return False
    
    async def _cleanup_old_backups(self):
        backups = sorted(self.backup_dir.glob("backup_*.json.gz"))
        
        if len(backups) > self.max_backups:
            for old_backup in backups[:-self.max_backups]:
                old_backup.unlink()
                logger.info("old_backup_deleted", backup=old_backup.name)
    
    def list_backups(self) -> List[Dict]:
        backups = []
        for backup_file in sorted(self.backup_dir.glob("backup_*.json.gz"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "name": backup_file.name,
                "path": str(backup_file),
                "size_bytes": stat.st_size,
                "created_at": stat.st_mtime
            })
        return backups

backup_manager = BackupManager()