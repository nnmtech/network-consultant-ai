import asyncio
import time
from typing import Dict, Any, List
import structlog
from datetime import datetime

logger = structlog.get_logger()

class HealthMonitor:
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.running = False
        self.task = None
        self.health_history: List[Dict[str, Any]] = []
        self.max_history = 100
        self.failure_count = 0
        self.consecutive_failures_threshold = 3
        self.components = {}
        
    async def start(self):
        if self.running:
            logger.warning("health_monitor_already_running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("health_monitor_started", interval=self.check_interval)
    
    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("health_monitor_stopped")
    
    def register_component(self, name: str, check_func, heal_func=None):
        self.components[name] = {
            "check": check_func,
            "heal": heal_func,
            "status": "unknown",
            "last_check": None,
            "failures": 0
        }
        logger.info("component_registered", component=name, has_healing=heal_func is not None)
    
    async def _monitor_loop(self):
        while self.running:
            try:
                await self._run_health_checks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_monitor_error", error=str(e), exc_info=True)
                await asyncio.sleep(self.check_interval)
    
    async def _run_health_checks(self):
        check_time = datetime.utcnow()
        results = {}
        all_healthy = True
        
        for name, component in self.components.items():
            try:
                is_healthy = await component["check"]()
                component["status"] = "healthy" if is_healthy else "unhealthy"
                component["last_check"] = check_time
                results[name] = is_healthy
                
                if not is_healthy:
                    all_healthy = False
                    component["failures"] += 1
                    
                    logger.warning(
                        "component_unhealthy",
                        component=name,
                        failures=component["failures"]
                    )
                    
                    if component["failures"] >= self.consecutive_failures_threshold:
                        await self._attempt_healing(name, component)
                else:
                    component["failures"] = 0
                    
            except Exception as e:
                logger.error(
                    "health_check_failed",
                    component=name,
                    error=str(e)
                )
                results[name] = False
                all_healthy = False
        
        self._record_health_check(check_time, results, all_healthy)
        
        if not all_healthy:
            self.failure_count += 1
        else:
            self.failure_count = 0
    
    async def _attempt_healing(self, name: str, component: Dict):
        if not component["heal"]:
            logger.warning(
                "no_healing_available",
                component=name,
                msg="Component has no healing function"
            )
            return
        
        try:
            logger.info("attempting_self_heal", component=name)
            
            success = await component["heal"]()
            
            if success:
                component["failures"] = 0
                component["status"] = "healed"
                logger.info(
                    "self_heal_successful",
                    component=name
                )
            else:
                logger.error(
                    "self_heal_failed",
                    component=name,
                    msg="Healing function returned False"
                )
                
        except Exception as e:
            logger.error(
                "self_heal_error",
                component=name,
                error=str(e),
                exc_info=True
            )
    
    def _record_health_check(self, check_time: datetime, results: Dict, all_healthy: bool):
        record = {
            "timestamp": check_time.isoformat(),
            "results": results,
            "all_healthy": all_healthy,
            "failure_count": self.failure_count
        }
        
        self.health_history.append(record)
        
        if len(self.health_history) > self.max_history:
            self.health_history.pop(0)
    
    def get_health_summary(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "check_interval": self.check_interval,
            "components": {
                name: {
                    "status": comp["status"],
                    "last_check": comp["last_check"].isoformat() if comp["last_check"] else None,
                    "failures": comp["failures"]
                }
                for name, comp in self.components.items()
            },
            "consecutive_failures": self.failure_count,
            "history_count": len(self.health_history)
        }
    
    def get_health_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.health_history[-limit:]

health_monitor = HealthMonitor(check_interval=30)