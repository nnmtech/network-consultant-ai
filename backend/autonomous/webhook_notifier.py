import asyncio
import aiohttp
from typing import List, Dict, Optional
import structlog
import json

logger = structlog.get_logger()

class WebhookNotifier:
    """
    Send notifications to external webhooks (Slack, Teams, Discord, custom).
    """
    
    def __init__(self):
        self.webhooks: Dict[str, str] = {}
        self.retry_attempts = 3
        self.retry_delay = 5
        
    def register_webhook(self, name: str, url: str):
        self.webhooks[name] = url
        logger.info("webhook_registered", name=name)
    
    async def send_notification(
        self,
        event_type: str,
        title: str,
        message: str,
        severity: str = "info",
        metadata: Optional[Dict] = None
    ):
        payload = {
            "event_type": event_type,
            "title": title,
            "message": message,
            "severity": severity,
            "metadata": metadata or {},
            "timestamp": asyncio.get_event_loop().time()
        }
        
        for name, url in self.webhooks.items():
            asyncio.create_task(self._send_to_webhook(name, url, payload))
    
    async def _send_to_webhook(self, name: str, url: str, payload: Dict):
        for attempt in range(self.retry_attempts):
            try:
                formatted_payload = self._format_payload(url, payload)
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=formatted_payload,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status < 300:
                            logger.info(
                                "webhook_notification_sent",
                                webhook=name,
                                status=response.status
                            )
                            return
                        else:
                            logger.warning(
                                "webhook_notification_failed",
                                webhook=name,
                                status=response.status,
                                attempt=attempt + 1
                            )
                            
            except Exception as e:
                logger.error(
                    "webhook_error",
                    webhook=name,
                    error=str(e),
                    attempt=attempt + 1
                )
            
            if attempt < self.retry_attempts - 1:
                await asyncio.sleep(self.retry_delay)
    
    def _format_payload(self, url: str, payload: Dict) -> Dict:
        if "slack.com" in url:
            return self._format_slack(payload)
        elif "discord.com" in url:
            return self._format_discord(payload)
        else:
            return payload
    
    def _format_slack(self, payload: Dict) -> Dict:
        color_map = {
            "critical": "danger",
            "warning": "warning",
            "info": "good"
        }
        
        return {
            "text": payload["title"],
            "attachments": [{
                "color": color_map.get(payload["severity"], "good"),
                "text": payload["message"],
                "fields": [
                    {"title": "Event Type", "value": payload["event_type"], "short": True},
                    {"title": "Severity", "value": payload["severity"], "short": True}
                ]
            }]
        }
    
    def _format_discord(self, payload: Dict) -> Dict:
        color_map = {
            "critical": 15158332,  # Red
            "warning": 16776960,   # Yellow
            "info": 3447003        # Blue
        }
        
        return {
            "embeds": [{
                "title": payload["title"],
                "description": payload["message"],
                "color": color_map.get(payload["severity"], 3447003),
                "fields": [
                    {"name": "Event Type", "value": payload["event_type"], "inline": True},
                    {"name": "Severity", "value": payload["severity"], "inline": True}
                ]
            }]
        }

webhook_notifier = WebhookNotifier()