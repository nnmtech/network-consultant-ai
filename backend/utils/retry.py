import asyncio
import functools
from typing import Callable, Optional, Type, Tuple
import structlog

logger = structlog.get_logger()

def async_retry(
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            "retry_exhausted",
                            func=func.__name__,
                            attempts=attempt,
                            error=str(e)
                        )
                        raise
                    
                    wait_time = backoff_base ** (attempt - 1)
                    logger.warning(
                        "retry_attempt",
                        func=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        wait_seconds=wait_time,
                        error=str(e)
                    )
                    
                    if on_retry:
                        await on_retry(attempt, e)
                    
                    await asyncio.sleep(wait_time)
            
            raise last_exception
        
        return wrapper
    return decorator