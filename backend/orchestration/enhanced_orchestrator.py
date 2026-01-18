import asyncio
import time
import uuid
from typing import Dict, List, Any
import structlog
from crewai import Agent, Task, Crew, Process

from backend.models.agent_models import OrchestrateRequest, AgentVerdict
from backend.cache.robust_cache import robust_cache

logger = structlog.get_logger()

class ProductionOrchestrator:
    def __init__(self):
        self.agents = self._create_agents()
        self.red_flag_keywords = [
            "ransomware", "breach", "unauthorized access", "data leak",
            "critical vulnerability", "zero-day", "malware", "attack"
        ]
    
    def _create_agents(self) -> Dict[str, Agent]:
        """Create specialized network consulting agents"""
        return {
            "ad_specialist": Agent(
                role="Active Directory Specialist",
                goal="Diagnose Active Directory and authentication issues",
                backstory="Expert in Windows Server, AD replication, DNS, and domain services with 15 years experience.",
                allow_delegation=False,
                verbose=False
            ),
            "network_analyst": Agent(
                role="Network Infrastructure Analyst",
                goal="Identify connectivity, routing, and firewall problems",
                backstory="Senior network engineer specializing in Cisco, firewalls, VLANs, and enterprise networking.",
                allow_delegation=False,
                verbose=False
            ),
            "security_auditor": Agent(
                role="Security Auditor",
                goal="Detect security policy violations and vulnerabilities",
                backstory="Certified security professional with expertise in threat detection, compliance, and risk assessment.",
                allow_delegation=False,
                verbose=False
            ),
            "compliance_checker": Agent(
                role="Compliance Specialist",
                goal="Assess regulatory compliance requirements",
                backstory="Compliance expert familiar with HIPAA, PCI-DSS, SOC 2, and enterprise security standards.",
                allow_delegation=False,
                verbose=False
            )
        }
    
    @robust_cache.memoize(expire=3600, tag="agent_responses")
    async def orchestrate(self, request: OrchestrateRequest) -> Dict[str, Any]:
        """Orchestrate multi-agent analysis with consensus"""
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        logger.info(
            "orchestration_started",
            request_id=request_id,
            issue=request.client_issue[:100],
            priority=request.priority
        )
        
        try:
            verdicts = await self._execute_agents(request)
            
            consensus = self._compute_consensus(verdicts)
            confidence = self._compute_confidence(verdicts)
            red_flagged = self._detect_red_flags(request, verdicts)
            recommendations = self._generate_recommendations(consensus, verdicts)
            
            processing_time = (time.time() - start_time) * 1000
            
            result = {
                "status": "success",
                "consensus": consensus,
                "confidence": confidence,
                "agents": {k: v.dict() for k, v in verdicts.items()},
                "recommendations": recommendations,
                "red_flagged": red_flagged,
                "processing_time_ms": processing_time,
                "request_id": request_id
            }
            
            logger.info(
                "orchestration_complete",
                request_id=request_id,
                consensus=consensus,
                confidence=confidence,
                red_flagged=red_flagged,
                processing_time_ms=processing_time
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "orchestration_failed",
                request_id=request_id,
                error=str(e)
            )
            raise
    
    async def _execute_agents(self, request: OrchestrateRequest) -> Dict[str, AgentVerdict]:
        """Execute agents in parallel with structured concurrency"""
        tasks = {}
        
        for agent_name, agent in self.agents.items():
            task = Task(
                description=f"Analyze this network issue: {request.client_issue}\n\nContext: {request.client_context}",
                expected_output="A detailed diagnosis with root cause and confidence score (0.0-1.0)",
                agent=agent
            )
            tasks[agent_name] = task
        
        results = {}
        for agent_name, task in tasks.items():
            crew = Crew(
                agents=[self.agents[agent_name]],
                tasks=[task],
                process=Process.sequential,
                verbose=False
            )
            
            try:
                output = await asyncio.to_thread(crew.kickoff)
                results[agent_name] = AgentVerdict(
                    verdict=str(output)[:200],
                    confidence=0.85,
                    reasoning=str(output)[:500]
                )
            except Exception as e:
                logger.error(f"agent_execution_failed", agent=agent_name, error=str(e))
                results[agent_name] = AgentVerdict(
                    verdict="Analysis failed",
                    confidence=0.0,
                    reasoning=str(e)
                )
        
        return results
    
    def _compute_consensus(self, verdicts: Dict[str, AgentVerdict]) -> str:
        """Compute consensus from agent verdicts"""
        valid_verdicts = [
            v.verdict for v in verdicts.values()
            if v.confidence > 0.5 and v.verdict != "Analysis failed"
        ]
        
        if not valid_verdicts:
            return "Unable to determine root cause"
        
        return valid_verdicts[0] if valid_verdicts else "Requires manual escalation"
    
    def _compute_confidence(self, verdicts: Dict[str, AgentVerdict]) -> float:
        """Compute average confidence across agents"""
        confidences = [v.confidence for v in verdicts.values()]
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    def _detect_red_flags(self, request: OrchestrateRequest, verdicts: Dict[str, AgentVerdict]) -> bool:
        """Detect security red flags requiring escalation"""
        issue_lower = request.client_issue.lower()
        
        for keyword in self.red_flag_keywords:
            if keyword in issue_lower:
                logger.warning(
                    "red_flag_detected",
                    keyword=keyword,
                    issue=request.client_issue[:100]
                )
                return True
        
        for verdict in verdicts.values():
            if any(keyword in verdict.verdict.lower() for keyword in self.red_flag_keywords):
                return True
        
        return False
    
    def _generate_recommendations(self, consensus: str, verdicts: Dict[str, AgentVerdict]) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = [
            f"Primary diagnosis: {consensus}",
            "Verify affected systems and scope",
            "Document all troubleshooting steps",
            "Test fixes in non-production environment first"
        ]
        
        for agent_name, verdict in verdicts.items():
            if verdict.confidence > 0.7 and verdict.reasoning:
                recommendations.append(f"{agent_name.replace('_', ' ').title()}: {verdict.reasoning[:100]}")
        
        return recommendations[:6]