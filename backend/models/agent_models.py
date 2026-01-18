from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class AgentRole(str, Enum):
    AD_SPECIALIST = "ad_specialist"
    NETWORK_ANALYST = "network_analyst"
    SECURITY_AUDITOR = "security_auditor"
    COMPLIANCE_CHECKER = "compliance_checker"
    DOCUMENTATION_AGENT = "documentation_agent"

class AgentAnalysis(BaseModel):
    verdict: str = Field(..., description="Agent's analysis verdict")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    reasoning: Optional[str] = Field(None, description="Detailed reasoning")
    red_flags: List[str] = Field(default_factory=list, description="Identified red flags")
    recommendations: List[str] = Field(default_factory=list, description="Action recommendations")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

class ConsensusResult(BaseModel):
    consensus: str = Field(..., description="Final consensus verdict")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")
    agents: Dict[str, AgentAnalysis] = Field(..., description="Individual agent results")
    recommendations: List[str] = Field(..., description="Combined recommendations")
    red_flagged: bool = Field(default=False, description="Whether issue requires escalation")
    escalation_reason: Optional[str] = Field(None, description="Reason for escalation")

class AgentConfig(BaseModel):
    role: AgentRole
    goal: str
    backstory: str
    tools: List[str] = Field(default_factory=list)
    allow_delegation: bool = False
    verbose: bool = False
    max_iterations: int = 5
    max_execution_time: Optional[int] = None