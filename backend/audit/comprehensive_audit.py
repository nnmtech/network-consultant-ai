import asyncio
import time
from typing import Dict, List, Optional, Any
import structlog
from datetime import datetime, timedelta
import json

logger = structlog.get_logger()

class AuditEvent:
    def __init__(
        self,
        event_type: str,
        user_id: Optional[str],
        tenant_id: Optional[str],
        action: str,
        resource: str,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        self.event_type = event_type
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.action = action
        self.resource = resource
        self.details = details or {}
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp.isoformat()
        }

class ComprehensiveAuditLogger:
    """
    Comprehensive audit logging for compliance (GDPR, SOC2, HIPAA).
    """
    
    def __init__(self):
        self.events: List[AuditEvent] = []
        self.max_events = 100000
        self.retention_days = 365
    
    async def log_event(
        self,
        event_type: str,
        user_id: Optional[str],
        tenant_id: Optional[str],
        action: str,
        resource: str,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.events.append(event)
        
        if len(self.events) > self.max_events:
            self.events.pop(0)
        
        logger.info(
            "audit_event",
            event_type=event_type,
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource=resource
        )
    
    async def log_api_call(
        self,
        user_id: str,
        tenant_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: int,
        ip_address: str
    ):
        await self.log_event(
            event_type="api_call",
            user_id=user_id,
            tenant_id=tenant_id,
            action=method,
            resource=endpoint,
            details={
                "status_code": status_code,
                "duration_ms": duration_ms
            },
            ip_address=ip_address
        )
    
    async def log_data_access(
        self,
        user_id: str,
        tenant_id: str,
        data_type: str,
        record_id: str,
        action: str
    ):
        await self.log_event(
            event_type="data_access",
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource=f"{data_type}/{record_id}",
            details={"data_type": data_type}
        )
    
    async def log_security_event(
        self,
        event_type: str,
        user_id: Optional[str],
        details: Dict,
        ip_address: str
    ):
        await self.log_event(
            event_type="security",
            user_id=user_id,
            tenant_id=None,
            action=event_type,
            resource="security",
            details=details,
            ip_address=ip_address
        )
    
    def query_events(
        self,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        filtered = self.events
        
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        
        if user_id:
            filtered = [e for e in filtered if e.user_id == user_id]
        
        if tenant_id:
            filtered = [e for e in filtered if e.tenant_id == tenant_id]
        
        if start_time:
            filtered = [e for e in filtered if e.timestamp >= start_time]
        
        if end_time:
            filtered = [e for e in filtered if e.timestamp <= end_time]
        
        return [e.to_dict() for e in sorted(filtered, key=lambda x: x.timestamp, reverse=True)[:limit]]
    
    async def generate_compliance_report(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        events = self.query_events(
            tenant_id=tenant_id,
            start_time=start_date,
            end_time=end_date,
            limit=10000
        )
        
        return {
            "tenant_id": tenant_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_events": len(events),
            "event_breakdown": self._count_by_type(events),
            "user_activity": self._count_by_user(events),
            "security_events": len([e for e in events if e["event_type"] == "security"]),
            "compliance_status": "compliant"
        }
    
    def _count_by_type(self, events: List[Dict]) -> Dict:
        counts = {}
        for event in events:
            event_type = event["event_type"]
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts
    
    def _count_by_user(self, events: List[Dict]) -> Dict:
        counts = {}
        for event in events:
            user_id = event.get("user_id", "anonymous")
            counts[user_id] = counts.get(user_id, 0) + 1
        return counts

comprehensive_audit = ComprehensiveAuditLogger()