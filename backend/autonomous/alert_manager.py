import asyncio
from typing import List, Dict, Any, Callable
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

class Alert:
    def __init__(self, severity: str, component: str, message: str, metadata: Dict = None):
        self.severity = severity
        self.component = component
        self.message = message
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()
        self.resolved = False
        self.resolved_at = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "component": self.component,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }

class AlertManager:
    def __init__(self):
        self.alerts: List[Alert] = []
        self.max_alerts = 1000
        self.notification_handlers: List[Callable] = []
        self.alert_cooldown: Dict[str, datetime] = {}
        self.cooldown_period = timedelta(minutes=5)
        
    def register_handler(self, handler: Callable):
        self.notification_handlers.append(handler)
        logger.info("alert_handler_registered", handler=handler.__name__)
    
    async def raise_alert(
        self,
        severity: str,
        component: str,
        message: str,
        metadata: Dict = None
    ):
        alert_key = f"{component}:{severity}:{message}"
        
        if alert_key in self.alert_cooldown:
            last_alert = self.alert_cooldown[alert_key]
            if datetime.utcnow() - last_alert < self.cooldown_period:
                logger.debug(
                    "alert_suppressed",
                    component=component,
                    reason="cooldown_active"
                )
                return
        
        alert = Alert(severity, component, message, metadata)
        self.alerts.append(alert)
        self.alert_cooldown[alert_key] = datetime.utcnow()
        
        if len(self.alerts) > self.max_alerts:
            self.alerts.pop(0)
        
        logger.warning(
            "alert_raised",
            severity=severity,
            component=component,
            message=message,
            metadata=metadata
        )
        
        await self._notify_handlers(alert)
    
    async def _notify_handlers(self, alert: Alert):
        for handler in self.notification_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(
                    "alert_handler_failed",
                    handler=handler.__name__,
                    error=str(e)
                )
    
    def resolve_alerts(self, component: str):
        resolved_count = 0
        for alert in self.alerts:
            if alert.component == component and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.utcnow()
                resolved_count += 1
        
        if resolved_count > 0:
            logger.info(
                "alerts_resolved",
                component=component,
                count=resolved_count
            )
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        return [alert.to_dict() for alert in self.alerts if not alert.resolved]
    
    def get_all_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [alert.to_dict() for alert in self.alerts[-limit:]]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        active = [a for a in self.alerts if not a.resolved]
        
        by_severity = {
            "critical": 0,
            "warning": 0,
            "info": 0
        }
        
        for alert in active:
            severity = alert.severity.lower()
            if severity in by_severity:
                by_severity[severity] += 1
        
        return {
            "total_alerts": len(self.alerts),
            "active_alerts": len(active),
            "resolved_alerts": len(self.alerts) - len(active),
            "by_severity": by_severity
        }

alert_manager = AlertManager()

# Example notification handler
async def log_alert_handler(alert: Alert):
    logger.info(
        "alert_notification",
        severity=alert.severity,
        component=alert.component,
        message=alert.message
    )

# Register default handler
alert_manager.register_handler(log_alert_handler)