from contextlib import asynccontextmanager
from typing import Optional
import time

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import ORJSONResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from backend.cache.robust_cache import robust_cache
from backend.orchestration.enhanced_orchestrator import ProductionOrchestrator
from backend.logging import configure_logging
from backend.auth.jwt_handler import verify_token
from backend.metrics.prometheus import metrics, CONTENT_TYPE_LATEST
from backend.api.admin_routes import router as admin_router
from backend.api.export_routes import router as export_router
from backend.api.versioning import router_v2
from backend.autonomous.health_monitor import health_monitor
from backend.autonomous.self_healing import self_healing_actions
from backend.autonomous.alert_manager import alert_manager
from backend.autonomous.rate_limiter import rate_limiter
from backend.autonomous.circuit_breaker import circuit_breaker_manager
from backend.autonomous.performance_optimizer import performance_optimizer
from backend.autonomous.anomaly_detector import anomaly_detector
from backend.autonomous.backup_manager import backup_manager
from backend.scheduler.task_scheduler import task_scheduler
from backend.tenancy.multi_tenant import multi_tenant_manager
from backend.audit.comprehensive_audit import comprehensive_audit
from backend.database.audit_logger import audit_logger
from backend.cache.redis_cache import redis_cache

configure_logging()
logger = structlog.get_logger()

security = HTTPBearer()
orchestrator = ProductionOrchestrator()

async def verify_auth_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    return payload

async def setup_autonomous_monitoring():
    health_monitor.register_component(
        "cache",
        check_func=robust_cache.health_check,
        heal_func=self_healing_actions.heal_cache_system
    )
    
    health_monitor.register_component(
        "database",
        check_func=lambda: audit_logger.is_connected(),
        heal_func=self_healing_actions.heal_database_connection
    )
    
    health_monitor.register_component(
        "redis",
        check_func=lambda: redis_cache.is_connected(),
        heal_func=self_healing_actions.heal_redis_connection
    )
    
    health_monitor.register_component(
        "orchestrator",
        check_func=lambda: orchestrator.is_healthy(),
        heal_func=None
    )
    
    await health_monitor.start()
    await performance_optimizer.start()
    await anomaly_detector.start()
    await backup_manager.start()
    await task_scheduler.start()
    
    logger.info("autonomous_systems_enabled")

@asynccontextmanager
async def robust_lifespan(app: FastAPI):
    logger.info("startup", event="application_starting", version="2.3.0")
    await robust_cache.cleanup_stale_locks()
    await orchestrator.initialize()
    await setup_autonomous_monitoring()
    yield
    logger.info("shutdown", event="application_stopping")
    await health_monitor.stop()
    await performance_optimizer.stop()
    await anomaly_detector.stop()
    await backup_manager.stop()
    await task_scheduler.stop()
    await orchestrator.shutdown()

app = FastAPI(
    title="Network Consultant AI",
    version="2.3.0",
    description="Enterprise AI with multi-tenancy, scheduled tasks, email notifications, and comprehensive audit",
    lifespan=robust_lifespan,
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(export_router)
app.include_router(router_v2)

class ClientContext(BaseModel):
    environment: str
    users_affected: Optional[int] = None
    location: Optional[str] = None

class OrchestrateRequest(BaseModel):
    client_issue: str = Field(..., min_length=10, max_length=2000)
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    client_context: Optional[ClientContext] = None
    tags: list[str] = Field(default_factory=list)

class OrchestrateResponse(BaseModel):
    status: str
    consensus: str
    confidence: float
    agents: dict
    recommendations: list[str]
    red_flagged: bool
    processing_time_ms: int
    request_id: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    components: dict
    uptime_seconds: int
    version: str

start_time = time.time()

@app.middleware("http")
async def comprehensive_audit_middleware(request: Request, call_next):
    start = time.time()
    
    response = await call_next(request)
    
    duration_ms = int((time.time() - start) * 1000)
    
    # Log API call to audit trail
    user_id = "anonymous"
    tenant_id = "default"
    
    await comprehensive_audit.log_api_call(
        user_id=user_id,
        tenant_id=tenant_id,
        endpoint=request.url.path,
        method=request.method,
        status_code=response.status_code,
        duration_ms=duration_ms,
        ip_address=request.client.host
    )
    
    return response

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    path = request.url.path
    
    endpoint_type = "default"
    if "/orchestrate" in path:
        endpoint_type = "orchestrate"
    elif "/admin" in path:
        endpoint_type = "admin"
    
    allowed, message = await rate_limiter.check_rate_limit(client_ip, endpoint_type)
    
    if not allowed:
        return ORJSONResponse(
            status_code=429,
            content={"detail": message}
        )
    
    response = await call_next(request)
    return response

@app.post("/api/v1/orchestrate", response_model=OrchestrateResponse)
async def orchestrate_issue(
    request: OrchestrateRequest,
    auth_payload: dict = Depends(verify_auth_token)
):
    start = time.time()
    request_id = f"req_{int(start * 1000)}"
    
    user_id = auth_payload.get("sub")
    tenant_id = auth_payload.get("tenant_id", "default")
    
    # Check tenant quota
    allowed, quota_message = multi_tenant_manager.check_quota(tenant_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=quota_message)
    
    logger.info(
        "orchestration_request",
        request_id=request_id,
        issue=request.client_issue[:100],
        priority=request.priority,
        user_id=user_id,
        tenant_id=tenant_id
    )
    
    try:
        breaker = circuit_breaker_manager.get("openai_api")
        if breaker:
            result = await breaker.call(
                orchestrator.orchestrate,
                issue=request.client_issue,
                priority=request.priority,
                context=request.client_context.dict() if request.client_context else {},
                tags=request.tags,
                user_id=user_id
            )
        else:
            result = await orchestrator.orchestrate(
                issue=request.client_issue,
                priority=request.priority,
                context=request.client_context.dict() if request.client_context else {},
                tags=request.tags,
                user_id=user_id
            )
        
        processing_time = int((time.time() - start) * 1000)
        
        # Increment tenant usage
        multi_tenant_manager.increment_usage(tenant_id)
        
        performance_optimizer.record_metric("orchestration_response_time", processing_time)
        anomaly_detector.record_value("orchestration_response_time", processing_time)
        
        response = OrchestrateResponse(
            status="success",
            consensus=result["consensus"],
            confidence=result["confidence"],
            agents=result["agents"],
            recommendations=result["recommendations"],
            red_flagged=result["red_flagged"],
            processing_time_ms=processing_time,
            request_id=request_id
        )
        
        logger.info(
            "orchestration_complete",
            request_id=request_id,
            processing_time_ms=processing_time,
            consensus=result["consensus"],
            confidence=result["confidence"]
        )
        
        return response
        
    except Exception as e:
        logger.error(
            "orchestration_failed",
            request_id=request_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Orchestration failed: {str(e)}"
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    components = {
        "cache": "healthy" if await robust_cache.health_check() else "unhealthy",
        "orchestrator": "healthy" if orchestrator.is_healthy() else "unhealthy",
        "lock_system": "healthy",
        "autonomous_monitor": "healthy" if health_monitor.running else "stopped",
        "performance_optimizer": "healthy" if performance_optimizer.running else "stopped",
        "anomaly_detector": "healthy" if anomaly_detector.running else "stopped",
        "backup_manager": "healthy" if backup_manager.running else "stopped",
        "task_scheduler": "healthy" if task_scheduler.running else "stopped"
    }
    
    return HealthResponse(
        status="healthy" if all(v == "healthy" for v in components.values()) else "degraded",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        components=components,
        uptime_seconds=int(time.time() - start_time),
        version="2.3.0"
    )

@app.get("/health/live")
async def liveness_probe():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness_probe():
    if not orchestrator.is_healthy():
        raise HTTPException(status_code=503, detail="Orchestrator not ready")
    return {"status": "ready"}

@app.get("/health/startup")
async def startup_probe():
    if not orchestrator.is_initialized():
        raise HTTPException(status_code=503, detail="Still initializing")
    return {"status": "started"}

@app.get("/metrics")
async def metrics_endpoint():
    return Response(
        content=metrics.generate_metrics(),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/system/status")
async def system_status(auth_payload: dict = Depends(verify_auth_token)):
    cache_stats = await robust_cache.get_stats()
    tenant_id = auth_payload.get("tenant_id", "default")
    
    anomaly_detector.record_value("cache_hit_rate", cache_stats.get("hit_rate", 0))
    
    return {
        "version": "2.3.0",
        "environment": "production",
        "uptime_seconds": int(time.time() - start_time),
        "cache_stats": cache_stats,
        "orchestrator_status": orchestrator.get_status(),
        "autonomous_health": health_monitor.get_health_summary(),
        "alerts": alert_manager.get_alert_summary(),
        "circuit_breakers": circuit_breaker_manager.get_all_states(),
        "performance": performance_optimizer.get_metrics_summary(),
        "anomalies": anomaly_detector.get_summary(),
        "scheduled_tasks": task_scheduler.get_task_status(),
        "tenant_stats": multi_tenant_manager.get_tenant_stats(tenant_id)
    }

@app.get("/api/v1/autonomous/health-history")
async def get_health_history(limit: int = 20):
    return health_monitor.get_health_history(limit=limit)

@app.get("/api/v1/autonomous/alerts")
async def get_alerts(active_only: bool = True):
    if active_only:
        return alert_manager.get_active_alerts()
    return alert_manager.get_all_alerts()

@app.get("/api/v1/autonomous/anomalies")
async def get_anomalies(limit: int = 50):
    return anomaly_detector.get_recent_anomalies(limit=limit)

@app.get("/api/v1/autonomous/performance")
async def get_performance():
    return performance_optimizer.analyze_performance()

app.mount("/", StaticFiles(directory="static", html=True), name="static")