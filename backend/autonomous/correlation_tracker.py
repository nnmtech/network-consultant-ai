import asyncio
import time
import uuid
from typing import Dict, List, Optional
import structlog
from contextvars import ContextVar
from collections import defaultdict

logger = structlog.get_logger()

# Context variable for request correlation
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

class CorrelationTracker:
    """
    Tracks request flow across services and components.
    Enables distributed tracing for debugging.
    """
    
    def __init__(self):
        self.traces: Dict[str, Dict] = {}
        self.max_traces = 10000
        self.span_data: Dict[str, List[Dict]] = defaultdict(list)
        
    def start_trace(self, correlation_id: Optional[str] = None) -> str:
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        correlation_id_var.set(correlation_id)
        
        self.traces[correlation_id] = {
            "correlation_id": correlation_id,
            "started_at": time.time(),
            "completed_at": None,
            "status": "in_progress",
            "spans": []
        }
        
        logger.info("trace_started", correlation_id=correlation_id)
        return correlation_id
    
    def add_span(self, name: str, metadata: Dict = None):
        correlation_id = correlation_id_var.get()
        
        if not correlation_id or correlation_id not in self.traces:
            return
        
        span = {
            "name": name,
            "started_at": time.time(),
            "metadata": metadata or {}
        }
        
        self.traces[correlation_id]["spans"].append(span)
        self.span_data[correlation_id].append(span)
    
    def end_span(self, name: str):
        correlation_id = correlation_id_var.get()
        
        if not correlation_id or correlation_id not in self.traces:
            return
        
        spans = self.traces[correlation_id]["spans"]
        for span in reversed(spans):
            if span["name"] == name and "completed_at" not in span:
                span["completed_at"] = time.time()
                span["duration_ms"] = int((span["completed_at"] - span["started_at"]) * 1000)
                break
    
    def end_trace(self, status: str = "success"):
        correlation_id = correlation_id_var.get()
        
        if not correlation_id or correlation_id not in self.traces:
            return
        
        trace = self.traces[correlation_id]
        trace["completed_at"] = time.time()
        trace["status"] = status
        trace["total_duration_ms"] = int((trace["completed_at"] - trace["started_at"]) * 1000)
        
        logger.info(
            "trace_completed",
            correlation_id=correlation_id,
            duration_ms=trace["total_duration_ms"],
            status=status,
            spans_count=len(trace["spans"])
        )
        
        if len(self.traces) > self.max_traces:
            oldest = min(self.traces.keys(), key=lambda k: self.traces[k]["started_at"])
            del self.traces[oldest]
            if oldest in self.span_data:
                del self.span_data[oldest]
    
    def get_trace(self, correlation_id: str) -> Optional[Dict]:
        return self.traces.get(correlation_id)
    
    def get_recent_traces(self, limit: int = 50) -> List[Dict]:
        sorted_traces = sorted(
            self.traces.values(),
            key=lambda t: t["started_at"],
            reverse=True
        )
        return sorted_traces[:limit]
    
    def get_slow_traces(self, threshold_ms: int = 5000, limit: int = 20) -> List[Dict]:
        slow_traces = [
            t for t in self.traces.values()
            if t.get("total_duration_ms", 0) > threshold_ms
        ]
        return sorted(slow_traces, key=lambda t: t["total_duration_ms"], reverse=True)[:limit]

correlation_tracker = CorrelationTracker()