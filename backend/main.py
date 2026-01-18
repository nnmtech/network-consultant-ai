from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

from backend.models.agent_models import OrchestrateRequest, OrchestrateResponse
from backend.orchestration.enhanced_orchestrator import ProductionOrchestrator
from backend.cache.robust_cache import robust_cache

logger = structlog.get_logger()
security = HTTPBearer()

REQUEST_COUNT = Counter('network_consultant_requests_total', 'Total requests')
REQUEST_LATENCY = Histogram('network_consultant_response_time_seconds', 'Response time')
AGENT_EXECUTIONS = Counter('network_consultant_agent_executions_total', 'Agent executions')
RED_FLAGS = Counter('network_consultant_red_flags_total', 'Red flags raised')

@asynccontextmanager
async def robust_lifespan(app: FastAPI):
    logger.info("startup", version="2.1.0", environment="production")
    await robust_cache.initialize()
    orchestrator = ProductionOrchestrator()
    app.state.orchestrator = orchestrator
    yield
    logger.info("shutdown", message="Graceful shutdown complete")

app = FastAPI(
    title="Network Consultant AI",
    version="2.1.0",
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

@app.post("/api/v1/orchestrate", response_model=OrchestrateResponse)
async def orchestrate_issue(
    request: OrchestrateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    REQUEST_COUNT.inc()
    start_time = time.time()
    
    try:
        orchestrator = app.state.orchestrator
        result = await orchestrator.orchestrate(request)
        
        AGENT_EXECUTIONS.inc(len(result.get("agents", {})))
        if result.get("red_flagged", False):
            RED_FLAGS.inc()
        
        REQUEST_LATENCY.observe(time.time() - start_time)
        
        return OrchestrateResponse(**result)
    except Exception as e:
        logger.error("orchestration_failed", error=str(e), issue=request.client_issue)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "2.1.0"
    }

@app.get("/health/live")
async def liveness_probe():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness_probe():
    try:
        stats = await robust_cache.get_stats()
        if stats:
            return {"status": "ready"}
        raise Exception("Cache not ready")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/health/startup")
async def startup_probe():
    return {"status": "started"}

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/system/status")
async def system_status():
    stats = await robust_cache.get_stats()
    return {
        "version": "2.1.0",
        "cache": stats,
        "uptime": time.time()
    }