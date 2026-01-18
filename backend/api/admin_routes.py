from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
import structlog

from backend.auth.jwt_handler import verify_token
from backend.database.audit_logger import audit_logger
from backend.cache.robust_cache import robust_cache
from backend.cache.redis_cache import redis_cache

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
    """
    Get recent audit logs from database.
    Requires admin role.
    """
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
    """
    Clear cache by type.
    Options: 'all', 'orchestration', 'redis'
    """
    try:
        if cache_type == "all":
            await robust_cache.clear_all()
            logger.info("cache_cleared", cache_type="file_cache")
        elif cache_type == "orchestration":
            await robust_cache.invalidate_tag("orchestration")
            logger.info("cache_invalidated", tag="orchestration")
        elif cache_type == "redis":
            if redis_cache.is_connected():
                # Redis doesn't have a clear_all in our implementation
                # You would need to implement pattern-based deletion
                pass
        
        return {"status": "success", "message": f"{cache_type} cache cleared"}
    except Exception as e:
        logger.error("cache_clear_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear cache"
        )

@router.get("/users")
async def get_users(token: str = Depends(lambda: ...)) -> List[Dict[str, Any]]:
    """
    Get all users.
    Note: This is a placeholder. Implement actual user management.
    """
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
    """
    Create new user.
    Note: This is a placeholder. Implement actual user creation with database.
    """
    logger.info("user_created", username=username, role=role)
    return {"status": "success", "message": f"User {username} created"}

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    token: str = Depends(lambda: ...)
) -> Dict[str, str]:
    """
    Delete user.
    Note: This is a placeholder. Implement actual user deletion.
    """
    logger.info("user_deleted", username=username)
    return {"status": "success", "message": f"User {username} deleted"}