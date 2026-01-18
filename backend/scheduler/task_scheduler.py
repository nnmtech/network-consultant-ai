import asyncio
from typing import Callable, Dict, List, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

class ScheduledTask:
    def __init__(
        self,
        name: str,
        func: Callable,
        interval_seconds: Optional[int] = None,
        cron_expression: Optional[str] = None,
        enabled: bool = True
    ):
        self.name = name
        self.func = func
        self.interval_seconds = interval_seconds
        self.cron_expression = cron_expression
        self.enabled = enabled
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count = 0
        self.error_count = 0
        
    async def execute(self):
        if not self.enabled:
            return
        
        try:
            logger.info("scheduled_task_starting", task=self.name)
            
            if asyncio.iscoroutinefunction(self.func):
                await self.func()
            else:
                self.func()
            
            self.last_run = datetime.utcnow()
            self.run_count += 1
            
            logger.info(
                "scheduled_task_completed",
                task=self.name,
                run_count=self.run_count
            )
            
        except Exception as e:
            self.error_count += 1
            logger.error(
                "scheduled_task_failed",
                task=self.name,
                error=str(e),
                exc_info=True
            )

class TaskScheduler:
    """
    Schedule recurring tasks (cron-like functionality).
    """
    
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.scheduler_task = None
    
    async def start(self):
        if self.running:
            return
        
        self.running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("task_scheduler_started", tasks=len(self.tasks))
    
    async def stop(self):
        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
        logger.info("task_scheduler_stopped")
    
    def register_task(
        self,
        name: str,
        func: Callable,
        interval_seconds: int,
        enabled: bool = True
    ):
        task = ScheduledTask(
            name=name,
            func=func,
            interval_seconds=interval_seconds,
            enabled=enabled
        )
        
        self.tasks[name] = task
        logger.info(
            "task_registered",
            name=name,
            interval=interval_seconds
        )
    
    def enable_task(self, name: str):
        if name in self.tasks:
            self.tasks[name].enabled = True
            logger.info("task_enabled", name=name)
    
    def disable_task(self, name: str):
        if name in self.tasks:
            self.tasks[name].enabled = False
            logger.info("task_disabled", name=name)
    
    def remove_task(self, name: str):
        if name in self.tasks:
            del self.tasks[name]
            logger.info("task_removed", name=name)
    
    async def _scheduler_loop(self):
        while self.running:
            try:
                for task in self.tasks.values():
                    if not task.enabled:
                        continue
                    
                    should_run = False
                    
                    if task.last_run is None:
                        should_run = True
                    elif task.interval_seconds:
                        elapsed = (datetime.utcnow() - task.last_run).total_seconds()
                        if elapsed >= task.interval_seconds:
                            should_run = True
                    
                    if should_run:
                        asyncio.create_task(task.execute())
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_loop_error", error=str(e))
                await asyncio.sleep(10)
    
    def get_task_status(self) -> List[Dict]:
        return [
            {
                "name": task.name,
                "enabled": task.enabled,
                "interval_seconds": task.interval_seconds,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "run_count": task.run_count,
                "error_count": task.error_count
            }
            for task in self.tasks.values()
        ]

task_scheduler = TaskScheduler()

# Register default tasks
async def cleanup_old_cache():
    from backend.cache.robust_cache import robust_cache
    await robust_cache.cleanup_stale_locks(max_age=3600)
    logger.info("scheduled_cache_cleanup_completed")

async def generate_daily_report():
    logger.info("scheduled_daily_report_generation")
    # Implement daily summary report generation

task_scheduler.register_task("cache_cleanup", cleanup_old_cache, interval_seconds=3600)
task_scheduler.register_task("daily_report", generate_daily_report, interval_seconds=86400)