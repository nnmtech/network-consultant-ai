import asyncio
import json
import time
from typing import Dict, List, Optional
import structlog
from pathlib import Path

logger = structlog.get_logger()

class RequestRecorder:
    """
    Records requests for debugging and replay.
    """
    
    def __init__(self, storage_dir: str = "./request_logs"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.recordings: List[Dict] = []
        self.max_recordings = 1000
        self.recording_enabled = True
        
    def record_request(
        self,
        endpoint: str,
        method: str,
        headers: Dict,
        body: Optional[Dict],
        response: Optional[Dict],
        status_code: int,
        duration_ms: int
    ):
        if not self.recording_enabled:
            return
        
        recording = {
            "timestamp": time.time(),
            "endpoint": endpoint,
            "method": method,
            "headers": dict(headers),
            "body": body,
            "response": response,
            "status_code": status_code,
            "duration_ms": duration_ms
        }
        
        self.recordings.append(recording)
        
        if len(self.recordings) > self.max_recordings:
            self.recordings.pop(0)
    
    async def save_recordings(self, filename: Optional[str] = None):
        if not filename:
            filename = f"recordings_{int(time.time())}.json"
        
        filepath = self.storage_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.recordings, f, indent=2)
            
            logger.info(
                "recordings_saved",
                filename=filename,
                count=len(self.recordings)
            )
            
        except Exception as e:
            logger.error("save_recordings_failed", error=str(e))
    
    async def replay_requests(
        self,
        filename: str,
        client_func: callable,
        filter_endpoint: Optional[str] = None
    ) -> List[Dict]:
        filepath = self.storage_dir / filename
        
        try:
            with open(filepath, 'r') as f:
                recordings = json.load(f)
            
            results = []
            
            for recording in recordings:
                if filter_endpoint and recording["endpoint"] != filter_endpoint:
                    continue
                
                logger.info(
                    "replaying_request",
                    endpoint=recording["endpoint"],
                    method=recording["method"]
                )
                
                start = time.time()
                
                try:
                    response = await client_func(
                        recording["endpoint"],
                        recording["method"],
                        recording["body"]
                    )
                    
                    duration_ms = int((time.time() - start) * 1000)
                    
                    results.append({
                        "original": recording,
                        "replay_response": response,
                        "replay_duration_ms": duration_ms,
                        "duration_diff_ms": duration_ms - recording["duration_ms"]
                    })
                    
                except Exception as e:
                    logger.error("replay_failed", error=str(e))
                    results.append({
                        "original": recording,
                        "replay_error": str(e)
                    })
            
            logger.info("replay_completed", total=len(results))
            return results
            
        except Exception as e:
            logger.error("replay_error", error=str(e))
            return []
    
    def get_recordings(self, limit: int = 100) -> List[Dict]:
        return self.recordings[-limit:]
    
    def clear_recordings(self):
        self.recordings.clear()
        logger.info("recordings_cleared")

request_recorder = RequestRecorder()