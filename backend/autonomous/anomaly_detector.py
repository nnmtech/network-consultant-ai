import asyncio
import time
from typing import Dict, List, Optional
import structlog
from collections import deque
import statistics

logger = structlog.get_logger()

class AnomalyDetector:
    def __init__(self):
        self.baseline: Dict[str, Dict] = {}
        self.recent_values: Dict[str, deque] = {}
        self.anomalies: List[Dict] = []
        self.max_anomalies = 500
        self.baseline_window = 100
        self.running = False
        self.task = None
        
    async def start(self):
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._detection_loop())
        logger.info("anomaly_detector_started")
    
    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("anomaly_detector_stopped")
    
    def record_value(self, metric_name: str, value: float):
        if metric_name not in self.recent_values:
            self.recent_values[metric_name] = deque(maxlen=self.baseline_window)
        
        self.recent_values[metric_name].append(value)
        
        if len(self.recent_values[metric_name]) >= 20:
            self._update_baseline(metric_name)
            self._check_for_anomaly(metric_name, value)
    
    def _update_baseline(self, metric_name: str):
        values = list(self.recent_values[metric_name])
        
        if len(values) < 10:
            return
        
        self.baseline[metric_name] = {
            "mean": statistics.mean(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "min": min(values),
            "max": max(values),
            "updated_at": time.time()
        }
    
    def _check_for_anomaly(self, metric_name: str, value: float):
        if metric_name not in self.baseline:
            return
        
        baseline = self.baseline[metric_name]
        mean = baseline["mean"]
        stdev = baseline["stdev"]
        
        if stdev == 0:
            return
        
        z_score = abs((value - mean) / stdev)
        
        if z_score > 3:
            anomaly = {
                "metric": metric_name,
                "value": value,
                "expected_mean": mean,
                "z_score": z_score,
                "timestamp": time.time(),
                "severity": "high" if z_score > 4 else "medium"
            }
            
            self.anomalies.append(anomaly)
            
            if len(self.anomalies) > self.max_anomalies:
                self.anomalies.pop(0)
            
            logger.warning(
                "anomaly_detected",
                metric=metric_name,
                value=value,
                expected=mean,
                z_score=round(z_score, 2),
                severity=anomaly["severity"]
            )
            
            from backend.autonomous.alert_manager import alert_manager
            asyncio.create_task(
                alert_manager.raise_alert(
                    severity=anomaly["severity"],
                    component="performance",
                    message=f"Anomaly in {metric_name}: {value:.2f} (expected ~{mean:.2f})",
                    metadata=anomaly
                )
            )
    
    async def _detection_loop(self):
        while self.running:
            try:
                await asyncio.sleep(60)
                self._cleanup_old_anomalies()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("anomaly_detection_error", error=str(e))
    
    def _cleanup_old_anomalies(self):
        current_time = time.time()
        cutoff_time = current_time - 3600
        
        self.anomalies = [
            a for a in self.anomalies
            if a["timestamp"] > cutoff_time
        ]
    
    def get_recent_anomalies(self, limit: int = 50) -> List[Dict]:
        return self.anomalies[-limit:]
    
    def get_baseline_summary(self) -> Dict:
        return {
            metric: {
                "mean": round(data["mean"], 2),
                "stdev": round(data["stdev"], 2),
                "range": [round(data["min"], 2), round(data["max"], 2)]
            }
            for metric, data in self.baseline.items()
        }
    
    def get_summary(self) -> Dict:
        return {
            "tracked_metrics": list(self.baseline.keys()),
            "total_anomalies": len(self.anomalies),
            "recent_anomalies": len([a for a in self.anomalies if time.time() - a["timestamp"] < 3600]),
            "running": self.running
        }

anomaly_detector = AnomalyDetector()