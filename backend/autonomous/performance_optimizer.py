import asyncio
import time
from typing import Dict, List
import structlog
from collections import deque
import statistics

logger = structlog.get_logger()

class PerformanceOptimizer:
    def __init__(self):
        self.metrics: Dict[str, deque] = {}
        self.window_size = 100
        self.running = False
        self.task = None
        self.optimization_interval = 300
        
    async def start(self):
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._optimization_loop())
        logger.info("performance_optimizer_started")
    
    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("performance_optimizer_stopped")
    
    def record_metric(self, metric_name: str, value: float):
        if metric_name not in self.metrics:
            self.metrics[metric_name] = deque(maxlen=self.window_size)
        
        self.metrics[metric_name].append({
            "value": value,
            "timestamp": time.time()
        })
    
    async def _optimization_loop(self):
        while self.running:
            try:
                await self._analyze_and_optimize()
                await asyncio.sleep(self.optimization_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("optimization_error", error=str(e))
                await asyncio.sleep(self.optimization_interval)
    
    async def _analyze_and_optimize(self):
        analysis = self.analyze_performance()
        
        for metric_name, stats in analysis.items():
            if "response_time" in metric_name and stats["mean"] > 5000:
                logger.warning(
                    "slow_performance_detected",
                    metric=metric_name,
                    mean_ms=stats["mean"],
                    p95_ms=stats["p95"]
                )
                await self._optimize_cache_strategy()
            
            if "cache_hit_rate" in metric_name and stats["mean"] < 0.7:
                logger.warning(
                    "low_cache_hit_rate",
                    metric=metric_name,
                    rate=stats["mean"]
                )
                await self._increase_cache_ttl()
    
    async def _optimize_cache_strategy(self):
        logger.info("optimizing_cache_strategy")
        from backend.cache.robust_cache import robust_cache
        await robust_cache.cleanup_stale_locks()
    
    async def _increase_cache_ttl(self):
        logger.info("cache_ttl_optimization_suggested")
    
    def analyze_performance(self) -> Dict:
        analysis = {}
        
        for metric_name, data_points in self.metrics.items():
            if not data_points:
                continue
            
            values = [p["value"] for p in data_points]
            
            if len(values) < 2:
                continue
            
            analysis[metric_name] = {
                "count": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0,
                "min": min(values),
                "max": max(values),
                "p95": self._percentile(values, 95),
                "p99": self._percentile(values, 99)
            }
        
        return analysis
    
    def _percentile(self, values: List[float], percentile: int) -> float:
        sorted_values = sorted(values)
        index = int(len(sorted_values) * (percentile / 100))
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def get_metrics_summary(self) -> Dict:
        return {
            "tracked_metrics": list(self.metrics.keys()),
            "total_data_points": sum(len(d) for d in self.metrics.values()),
            "optimization_interval": self.optimization_interval,
            "running": self.running
        }

performance_optimizer = PerformanceOptimizer()