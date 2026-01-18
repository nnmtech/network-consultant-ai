import asyncio
import time
from typing import Callable, Optional
from enum import Enum
import structlog

logger = structlog.get_logger()

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.opened_at: Optional[float] = None
        
        logger.info(
            "circuit_breaker_initialized",
            name=name,
            failure_threshold=failure_threshold,
            timeout=timeout
        )
    
    async def call(self, func: Callable, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.opened_at >= self.timeout:
                logger.info("circuit_breaker_half_open", name=self.name)
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                logger.warning("circuit_breaker_open", name=self.name)
                raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
            
        except self.expected_exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.success_threshold:
                logger.info("circuit_breaker_closed", name=self.name)
                self.state = CircuitState.CLOSED
                self.success_count = 0
    
    async def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(
            "circuit_breaker_failure",
            name=self.name,
            count=self.failure_count,
            threshold=self.failure_threshold
        )
        
        if self.failure_count >= self.failure_threshold:
            logger.error("circuit_breaker_opened", name=self.name)
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
    
    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure": self.last_failure_time
        }

class CircuitBreakerManager:
    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}
    
    def register(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60
    ) -> CircuitBreaker:
        breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            timeout=timeout
        )
        self.breakers[name] = breaker
        return breaker
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        return self.breakers.get(name)
    
    def get_all_states(self) -> dict:
        return {name: breaker.get_state() for name, breaker in self.breakers.items()}

circuit_breaker_manager = CircuitBreakerManager()

# Register common circuit breakers
circuit_breaker_manager.register("openai_api", failure_threshold=3, timeout=120)
circuit_breaker_manager.register("database", failure_threshold=5, timeout=60)
circuit_breaker_manager.register("redis", failure_threshold=3, timeout=30)