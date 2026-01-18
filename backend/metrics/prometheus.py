from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import structlog

logger = structlog.get_logger()

class PrometheusMetrics:
    def __init__(self):
        self.orchestration_requests = Counter(
            'orchestration_requests_total',
            'Total orchestration requests',
            ['priority']
        )
        
        self.orchestration_duration = Histogram(
            'orchestration_duration_seconds',
            'Orchestration processing time',
            ['priority'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )
        
        self.agent_executions = Counter(
            'agent_executions_total',
            'Total agent executions',
            ['role']
        )
        
        self.agent_errors = Counter(
            'agent_errors_total',
            'Total agent errors',
            ['role']
        )
        
        self.cache_hits = Counter(
            'cache_hits_total',
            'Total cache hits',
            ['cache']
        )
        
        self.cache_misses = Counter(
            'cache_misses_total',
            'Total cache misses',
            ['cache']
        )
        
        self.red_flags = Counter(
            'red_flags_total',
            'Total red flags raised',
            ['priority']
        )
        
        self.orchestration_errors = Counter(
            'orchestration_errors_total',
            'Total orchestration errors',
            ['priority']
        )
        
        self.active_orchestrations = Gauge(
            'active_orchestrations',
            'Current active orchestrations'
        )
        
        logger.info("prometheus_metrics_initialized")
    
    def increment_counter(self, metric_name: str, labels: dict):
        try:
            counter = getattr(self, metric_name.replace('_total', ''), None)
            if counter:
                counter.labels(**labels).inc()
        except Exception as e:
            logger.error("metric_increment_failed", metric=metric_name, error=str(e))
    
    def observe_histogram(self, metric_name: str, value: float, labels: dict):
        try:
            histogram = getattr(self, metric_name.replace('_seconds', ''), None)
            if histogram:
                histogram.labels(**labels).observe(value)
        except Exception as e:
            logger.error("metric_observe_failed", metric=metric_name, error=str(e))
    
    def set_gauge(self, metric_name: str, value: float):
        try:
            gauge = getattr(self, metric_name, None)
            if gauge:
                gauge.set(value)
        except Exception as e:
            logger.error("metric_set_failed", metric=metric_name, error=str(e))
    
    def generate_metrics(self):
        return generate_latest()

metrics = PrometheusMetrics()