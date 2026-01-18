from typing import Dict, Optional, List
import structlog
from datetime import datetime

logger = structlog.get_logger()

class Tenant:
    def __init__(
        self,
        tenant_id: str,
        name: str,
        plan: str = "free",
        max_requests_per_day: int = 100,
        features: Optional[List[str]] = None
    ):
        self.tenant_id = tenant_id
        self.name = name
        self.plan = plan
        self.max_requests_per_day = max_requests_per_day
        self.features = features or []
        self.created_at = datetime.utcnow()
        self.active = True
        self.request_count_today = 0
        self.total_requests = 0

class MultiTenantManager:
    """
    Manage multiple tenants with separate quotas and features.
    """
    
    def __init__(self):
        self.tenants: Dict[str, Tenant] = {}
        self.plans = {
            "free": {
                "max_requests_per_day": 100,
                "max_file_size_mb": 10,
                "features": ["basic_analysis"]
            },
            "pro": {
                "max_requests_per_day": 1000,
                "max_file_size_mb": 100,
                "features": ["basic_analysis", "advanced_analysis", "priority_support", "export_all_formats"]
            },
            "enterprise": {
                "max_requests_per_day": 10000,
                "max_file_size_mb": 1000,
                "features": ["basic_analysis", "advanced_analysis", "priority_support", "export_all_formats", "custom_agents", "dedicated_support"]
            }
        }
    
    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        plan: str = "free"
    ) -> Tenant:
        if tenant_id in self.tenants:
            raise ValueError(f"Tenant {tenant_id} already exists")
        
        plan_config = self.plans.get(plan, self.plans["free"])
        
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            plan=plan,
            max_requests_per_day=plan_config["max_requests_per_day"],
            features=plan_config["features"]
        )
        
        self.tenants[tenant_id] = tenant
        logger.info("tenant_created", tenant_id=tenant_id, name=name, plan=plan)
        
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return self.tenants.get(tenant_id)
    
    def check_quota(self, tenant_id: str) -> tuple[bool, Optional[str]]:
        tenant = self.get_tenant(tenant_id)
        
        if not tenant:
            return False, "Tenant not found"
        
        if not tenant.active:
            return False, "Tenant account is inactive"
        
        if tenant.request_count_today >= tenant.max_requests_per_day:
            return False, f"Daily quota exceeded ({tenant.max_requests_per_day} requests)"
        
        return True, None
    
    def increment_usage(self, tenant_id: str):
        tenant = self.get_tenant(tenant_id)
        if tenant:
            tenant.request_count_today += 1
            tenant.total_requests += 1
    
    def has_feature(self, tenant_id: str, feature: str) -> bool:
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        return feature in tenant.features
    
    def reset_daily_quotas(self):
        for tenant in self.tenants.values():
            tenant.request_count_today = 0
        logger.info("daily_quotas_reset", tenant_count=len(self.tenants))
    
    def get_tenant_stats(self, tenant_id: str) -> Optional[Dict]:
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return None
        
        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "plan": tenant.plan,
            "active": tenant.active,
            "requests_today": tenant.request_count_today,
            "requests_remaining_today": tenant.max_requests_per_day - tenant.request_count_today,
            "total_requests": tenant.total_requests,
            "features": tenant.features
        }

multi_tenant_manager = MultiTenantManager()

# Create default tenant
multi_tenant_manager.create_tenant("default", "Default Tenant", "enterprise")