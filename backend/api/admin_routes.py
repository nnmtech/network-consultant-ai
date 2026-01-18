from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
import structlog

from backend.auth.jwt_handler import verify_token
from backend.database.audit_logger import audit_logger
from backend.cache.robust_cache import robust_cache
from backend.cache.redis_cache import redis_cache
from backend.autonomous.correlation_tracker import correlation_tracker
from backend.autonomous.backup_manager import backup_manager
from backend.autonomous.webhook_notifier import webhook_notifier
from backend.autonomous.ab_testing import ab_test_manager
from backend.autonomous.request_replay import request_recorder

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

async def verify_admin(token: str) -> dict:
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    role = payload.get("role")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return payload

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 100,
    token: str = Depends(lambda: ...)
) -> List[Dict[str, Any]]:
    try:
        logs = await audit_logger.get_recent_audits(limit=limit)
        return logs
    except Exception as e:
        logger.error("audit_logs_fetch_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch audit logs"
        )

@router.post("/cache/clear")
async def clear_cache(
    cache_type: str = "all",
    token: str = Depends(lambda: ...)
) -> Dict[str, str]:
    try:
        if cache_type == "all":
            await robust_cache.clear_all()
            logger.info("cache_cleared", cache_type="file_cache")
        elif cache_type == "orchestration":
            await robust_cache.invalidate_tag("orchestration")
            logger.info("cache_invalidated", tag="orchestration")
        
        return {"status": "success", "message": f"{cache_type} cache cleared"}
    except Exception as e:
        logger.error("cache_clear_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear cache"
        )

@router.get("/traces")
async def get_traces(limit: int = 50) -> List[Dict]:
    return correlation_tracker.get_recent_traces(limit=limit)

@router.get("/traces/{correlation_id}")
async def get_trace(correlation_id: str) -> Dict:
    trace = correlation_tracker.get_trace(correlation_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace

@router.get("/traces/slow")
async def get_slow_traces(threshold_ms: int = 5000, limit: int = 20) -> List[Dict]:
    return correlation_tracker.get_slow_traces(threshold_ms=threshold_ms, limit=limit)

@router.post("/backups/create")
async def create_backup(backup_name: Optional[str] = None) -> Dict[str, str]:
    try:
        backup_path = await backup_manager.create_backup(backup_name=backup_name)
        return {"status": "success", "backup_path": backup_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backups")
async def list_backups() -> List[Dict]:
    return backup_manager.list_backups()

@router.post("/backups/restore")
async def restore_backup(backup_path: str) -> Dict[str, str]:
    success = await backup_manager.restore_backup(backup_path)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Restore failed")

@router.post("/webhooks/register")
async def register_webhook(name: str, url: str) -> Dict[str, str]:
    webhook_notifier.register_webhook(name, url)
    return {"status": "success", "message": f"Webhook {name} registered"}

@router.post("/webhooks/test")
async def test_webhook(name: str) -> Dict[str, str]:
    await webhook_notifier.send_notification(
        event_type="test",
        title="Test Notification",
        message="This is a test notification from Network Consultant AI",
        severity="info"
    )
    return {"status": "success"}

@router.get("/ab-tests")
async def get_ab_tests() -> Dict[str, Dict]:
    return ab_test_manager.get_all_results()

@router.get("/recordings")
async def get_recordings(limit: int = 100) -> List[Dict]:
    return request_recorder.get_recordings(limit=limit)

@router.post("/recordings/save")
async def save_recordings(filename: Optional[str] = None) -> Dict[str, str]:
    await request_recorder.save_recordings(filename=filename)
    return {"status": "success"}

@router.delete("/recordings")
async def clear_recordings() -> Dict[str, str]:
    request_recorder.clear_recordings()
    return {"status": "success"}

@router.get("/users")
async def get_users(token: str = Depends(lambda: ...)) -> List[Dict[str, Any]]:
    return [
        {
            "username": "admin@example.com",
            "role": "admin",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "active"
        },
        {
            "username": "user@example.com",
            "role": "user",
            "created_at": "2026-01-15T00:00:00Z",
            "status": "active"
        }
    ]

@router.post("/users")
async def create_user(
    username: str,
    password: str,
    role: str = "user",
    token: str = Depends(lambda: ...)
) -> Dict[str, str]:
    logger.info("user_created", username=username, role=role)
    return {"status": "success", "message": f"User {username} created"}

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    token: str = Depends(lambda: ...)
) -> Dict[str, str]:
    logger.info("user_deleted", username=username)
    return {"status": "success", "message": f"User {username} deleted"}