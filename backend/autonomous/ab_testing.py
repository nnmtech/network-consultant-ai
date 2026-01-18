import asyncio
import time
import random
from typing import Dict, List, Optional, Callable, Any
import structlog
from collections import defaultdict

logger = structlog.get_logger()

class ABTest:
    def __init__(
        self,
        name: str,
        variants: Dict[str, Callable],
        traffic_split: Optional[Dict[str, float]] = None
    ):
        self.name = name
        self.variants = variants
        self.traffic_split = traffic_split or {k: 1.0/len(variants) for k in variants.keys()}
        self.results: Dict[str, Dict] = defaultdict(lambda: {
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "total_duration_ms": 0,
            "avg_duration_ms": 0
        })
        self.enabled = True
        
    def select_variant(self, user_id: Optional[str] = None) -> tuple[str, Callable]:
        if user_id:
            random.seed(hash(user_id))
        
        rand = random.random()
        cumulative = 0.0
        
        for variant_name, split_pct in self.traffic_split.items():
            cumulative += split_pct
            if rand <= cumulative:
                return variant_name, self.variants[variant_name]
        
        first_variant = list(self.variants.keys())[0]
        return first_variant, self.variants[first_variant]
    
    async def execute(self, user_id: Optional[str] = None, *args, **kwargs) -> Any:
        if not self.enabled:
            default_variant = list(self.variants.keys())[0]
            return await self.variants[default_variant](*args, **kwargs)
        
        variant_name, variant_func = self.select_variant(user_id)
        
        start = time.time()
        success = False
        result = None
        
        try:
            if asyncio.iscoroutinefunction(variant_func):
                result = await variant_func(*args, **kwargs)
            else:
                result = variant_func(*args, **kwargs)
            success = True
            
        except Exception as e:
            logger.error(
                "ab_test_variant_failed",
                test=self.name,
                variant=variant_name,
                error=str(e)
            )
            raise
        
        finally:
            duration_ms = int((time.time() - start) * 1000)
            self._record_result(variant_name, success, duration_ms)
        
        return result
    
    def _record_result(self, variant_name: str, success: bool, duration_ms: int):
        stats = self.results[variant_name]
        stats["calls"] += 1
        
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1
        
        stats["total_duration_ms"] += duration_ms
        stats["avg_duration_ms"] = stats["total_duration_ms"] // stats["calls"]
    
    def get_results(self) -> Dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "variants": dict(self.results)
        }

class ABTestManager:
    def __init__(self):
        self.tests: Dict[str, ABTest] = {}
    
    def create_test(
        self,
        name: str,
        variants: Dict[str, Callable],
        traffic_split: Optional[Dict[str, float]] = None
    ) -> ABTest:
        test = ABTest(name, variants, traffic_split)
        self.tests[name] = test
        logger.info("ab_test_created", name=name, variants=list(variants.keys()))
        return test
    
    def get_test(self, name: str) -> Optional[ABTest]:
        return self.tests.get(name)
    
    def get_all_results(self) -> Dict[str, Dict]:
        return {name: test.get_results() for name, test in self.tests.items()}

ab_test_manager = ABTestManager()