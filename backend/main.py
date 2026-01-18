from contextlib import asynccontextmanager
from typing import Optional
import time

from fastapi import FastAPI, HTTPException, Depends, status
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

@asynccontextmanager
async def robust_lifespan(app: FastAPI):
    logger.info("startup", event="application_starting", version="2.1.0")
    await robust_cache.cleanup_stale_locks()
    await orchestrator.initialize()
    yield
    logger.info("shutdown", event="application_stopping")
    await orchestrator.shutdown()

app = FastAPI(
    title="Network Consultant AI",
    version="2.1.0",
    description="Enterprise-grade AI agent system for network consulting",
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

@app.post("/api/v1/orchestrate", response_model=OrchestrateResponse)
async def orchestrate_issue(
    request: OrchestrateRequest,
    auth_payload: dict = Depends(verify_auth_token)
):
    start = time.time()
    request_id = f"req_{int(start * 1000)}"
    
    user_id = auth_payload.get("sub")
    
    logger.info(
        "orchestration_request",
        request_id=request_id,
        issue=request.client_issue[:100],
        priority=request.priority,
        user_id=user_id
    )
    
    try:
        result = await orchestrator.orchestrate(
            issue=request.client_issue,
            priority=request.priority,
            context=request.client_context.dict() if request.client_context else {},
            tags=request.tags,
            user_id=user_id
        )
        
        processing_time = int((time.time() - start) * 1000)
        
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
    }
    
    return HealthResponse(
        status="healthy" if all(v == "healthy" for v in components.values()) else "degraded",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        components=components,
        uptime_seconds=int(time.time() - start_time),
        version="2.1.0"
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
    return {
        "version": "2.1.0",
        "environment": "production",
        "uptime_seconds": int(time.time() - start_time),
        "cache_stats": await robust_cache.get_stats(),
        "orchestrator_status": orchestrator.get_status(),
    }

app.mount("/", StaticFiles(directory="static", html=True), name="static")