import asyncio
import time
from typing import Dict, Optional
import structlog
from collections import defaultdict, deque

logger = structlog.get_logger()

class RateLimiter:
    def __init__(self):
        self.requests: Dict[str, deque] = defaultdict(deque)
        self.limits = {
            "default": {"requests": 100, "window": 60},
            "orchestrate": {"requests": 10, "window": 60},
            "admin": {"requests": 200, "window": 60}
        }
        self.blocked_until: Dict[str, float] = {}
    
    async def check_rate_limit(
        self,
        identifier: str,
        endpoint_type: str = "default"
    ) -> tuple[bool, Optional[str]]:
        current_time = time.time()
        
        if identifier in self.blocked_until:
            if current_time < self.blocked_until[identifier]:
                remaining = int(self.blocked_until[identifier] - current_time)
                return False, f"Rate limit exceeded. Try again in {remaining}s"
            else:
                del self.blocked_until[identifier]
        
        limit_config = self.limits.get(endpoint_type, self.limits["default"])
        max_requests = limit_config["requests"]
        window = limit_config["window"]
        
        request_queue = self.requests[identifier]
        
        while request_queue and request_queue[0] < current_time - window:
            request_queue.popleft()
        
        if len(request_queue) >= max_requests:
            self.blocked_until[identifier] = current_time + window
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                endpoint=endpoint_type,
                requests=len(request_queue)
            )
            return False, f"Rate limit exceeded: {max_requests} requests per {window}s"
        
        request_queue.append(current_time)
        return True, None
    
    def get_usage(self, identifier: str) -> Dict:
        current_time = time.time()
        request_queue = self.requests.get(identifier, deque())
        
        recent_requests = sum(1 for t in request_queue if t > current_time - 60)
        
        return {
            "requests_last_minute": recent_requests,
            "blocked": identifier in self.blocked_until,
            "blocked_until": self.blocked_until.get(identifier)
        }

rate_limiter = RateLimiter()