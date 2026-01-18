from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from enum import Enum

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class OrchestrateRequest(BaseModel):
    client_issue: str = Field(..., min_length=10, max_length=5000)
    priority: Priority = Priority.MEDIUM
    client_context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    tags: Optional[List[str]] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_issue": "Users cannot authenticate to network shares",
                "priority": "high",
                "client_context": {
                    "environment": "Active Directory",
                    "users_affected": 45,
                    "location": "Atlanta HQ"
                },
                "tags": ["authentication", "ad", "urgent"]
            }
        }

class AgentVerdict(BaseModel):
    verdict: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None

class OrchestrateResponse(BaseModel):
    status: str
    consensus: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    agents: Dict[str, AgentVerdict]
    recommendations: List[str]
    red_flagged: bool
    processing_time_ms: float
    request_id: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "consensus": "AD replication issue between DC01 and DC02",
                "confidence": 0.94,
                "agents": {
                    "ad_specialist": {
                        "verdict": "AD replication",
                        "confidence": 0.96
                    }
                },
                "recommendations": [
                    "Check AD replication status",
                    "Verify DNS resolution"
                ],
                "red_flagged": False,
                "processing_time_ms": 2345,
                "request_id": "req_abc123"
            }
        }

class AgentConfig(BaseModel):
    role: str
    goal: str
    backstory: str
    allow_delegation: bool = False
    verbose: bool = False

class TaskConfig(BaseModel):
    description: str
    expected_output: str
    agent: str