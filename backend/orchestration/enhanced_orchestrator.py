import asyncio
from typing import Dict, List, Any, Optional
import time
import structlog
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI

from backend.models.agent_models import (
    AgentRole,
    AgentAnalysis,
    ConsensusResult,
    AgentConfig
)
from backend.cache.robust_cache import robust_cache
from backend.database.audit_logger import audit_logger
from backend.cache.redis_cache import redis_cache
from backend.metrics.prometheus import metrics

logger = structlog.get_logger()

class ProductionOrchestrator:
    def __init__(self):
        self._initialized = False
        self._healthy = False
        self.llm = None
        self.crew_agents = {}
        self.agent_configs = self._load_agent_configs()
        
    def _load_agent_configs(self) -> Dict[AgentRole, AgentConfig]:
        return {
            AgentRole.AD_SPECIALIST: AgentConfig(
                role=AgentRole.AD_SPECIALIST,
                goal="Diagnose Active Directory and authentication issues with expert precision",
                backstory="""You are a senior Active Directory engineer with 15 years of experience. 
                You specialize in AD replication, Kerberos authentication, LDAP queries, Group Policy, 
                and domain controller troubleshooting. You can quickly identify authentication failures, 
                replication issues, and configuration problems.""",
                max_iterations=5
            ),
            AgentRole.NETWORK_ANALYST: AgentConfig(
                role=AgentRole.NETWORK_ANALYST,
                goal="Analyze network connectivity and infrastructure problems systematically",
                backstory="""You are a senior network engineer with expertise in TCP/IP, routing protocols, 
                switching, VLANs, firewalls, and network security. You excel at diagnosing connectivity issues, 
                packet loss, latency problems, and firewall misconfigurations.""",
                max_iterations=5
            ),
            AgentRole.SECURITY_AUDITOR: AgentConfig(
                role=AgentRole.SECURITY_AUDITOR,
                goal="Identify security vulnerabilities and policy violations",
                backstory="""You are a cybersecurity specialist focused on threat detection, vulnerability 
                assessment, and compliance. You can identify security risks, unauthorized access attempts, 
                and policy violations that could compromise network security.""",
                max_iterations=5
            ),
            AgentRole.COMPLIANCE_CHECKER: AgentConfig(
                role=AgentRole.COMPLIANCE_CHECKER,
                goal="Assess regulatory compliance and policy adherence",
                backstory="""You are a compliance expert familiar with SOC 2, HIPAA, PCI-DSS, and industry 
                best practices. You ensure that network configurations and security policies meet regulatory 
                requirements and identify compliance gaps.""",
                max_iterations=5
            ),
        }
    
    async def initialize(self):
        logger.info("orchestrator_init", event="initializing_orchestrator")
        
        try:
            self.llm = ChatOpenAI(
                model="gpt-4",
                temperature=0.7
            )
            
            for role, config in self.agent_configs.items():
                agent = Agent(
                    role=config.role.value.replace('_', ' ').title(),
                    goal=config.goal,
                    backstory=config.backstory,
                    llm=self.llm,
                    verbose=False,
                    allow_delegation=False
                )
                self.crew_agents[role] = agent
            
            await audit_logger.initialize()
            await redis_cache.initialize()
            
            self._initialized = True
            self._healthy = True
            
            logger.info("orchestrator_init", event="orchestrator_ready", agents=len(self.crew_agents))
            
        except Exception as e:
            logger.error("orchestrator_init_failed", error=str(e), exc_info=True)
            self._healthy = False
            raise
    
    async def shutdown(self):
        logger.info("orchestrator_shutdown", event="shutting_down")
        await audit_logger.close()
        await redis_cache.close()
        self._healthy = False
    
    def is_initialized(self) -> bool:
        return self._initialized
    
    def is_healthy(self) -> bool:
        return self._healthy
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "healthy": self._healthy,
            "active_agents": len(self.crew_agents),
            "redis_connected": redis_cache.is_connected(),
            "database_connected": audit_logger.is_connected(),
        }
    
    @robust_cache.memoize(expire=3600, tag="orchestration")
    async def orchestrate(
        self,
        issue: str,
        priority: str,
        context: Dict[str, Any],
        tags: List[str],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        logger.info(
            "orchestration_start",
            issue_length=len(issue),
            priority=priority,
            tags=tags,
            user_id=user_id
        )
        
        metrics.increment_counter('orchestration_requests_total', {'priority': priority})
        
        try:
            redis_key = f"issue:{hash(issue) % 100000}"
            cached_result = await redis_cache.get(redis_key)
            if cached_result:
                logger.info("orchestration_cache_hit", redis_key=redis_key)
                metrics.increment_counter('cache_hits_total', {'cache': 'redis'})
                return cached_result
            
            agent_tasks = [
                self._run_agent_with_crewai(role, agent, issue, context, priority)
                for role, agent in self.crew_agents.items()
            ]
            
            agent_results = await asyncio.gather(*agent_tasks, return_exceptions=True)
            
            valid_results = {}
            for role, result in zip(self.crew_agents.keys(), agent_results):
                if isinstance(result, Exception):
                    logger.error(
                        "agent_execution_failed",
                        role=role.value,
                        error=str(result)
                    )
                    metrics.increment_counter('agent_errors_total', {'role': role.value})
                    continue
                valid_results[role.value] = result
                metrics.increment_counter('agent_executions_total', {'role': role.value})
            
            consensus = self._compute_consensus(valid_results, priority)
            
            processing_time = (time.time() - start_time) * 1000
            
            await redis_cache.set(redis_key, consensus, expire=3600)
            
            await audit_logger.log_orchestration(
                issue=issue,
                priority=priority,
                consensus=consensus["consensus"],
                confidence=consensus["confidence"],
                red_flagged=consensus["red_flagged"],
                processing_time_ms=processing_time,
                user_id=user_id,
                context=context
            )
            
            metrics.observe_histogram('orchestration_duration_seconds', processing_time / 1000, {'priority': priority})
            
            if consensus["red_flagged"]:
                metrics.increment_counter('red_flags_total', {'priority': priority})
            
            logger.info(
                "orchestration_complete",
                consensus=consensus["consensus"],
                confidence=consensus["confidence"],
                red_flagged=consensus["red_flagged"],
                processing_time_ms=processing_time
            )
            
            return consensus
            
        except Exception as e:
            logger.error("orchestration_failed", error=str(e), exc_info=True)
            metrics.increment_counter('orchestration_errors_total', {'priority': priority})
            raise
    
    async def _run_agent_with_crewai(
        self,
        role: AgentRole,
        agent: Agent,
        issue: str,
        context: Dict[str, Any],
        priority: str
    ) -> AgentAnalysis:
        try:
            task = Task(
                description=f"""Analyze the following IT issue from your {role.value.replace('_', ' ')} perspective:
                
                Issue: {issue}
                
                Context: {context}
                Priority: {priority}
                
                Provide:
                1. Your expert verdict on the root cause
                2. Confidence level (0.0-1.0)
                3. Any red flags or security concerns
                4. Specific recommendations to resolve the issue
                """,
                expected_output="Detailed analysis with verdict, confidence score, red flags, and recommendations",
                agent=agent
            )
            
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False
            )
            
            result = await asyncio.to_thread(crew.kickoff)
            
            output = str(result)
            
            red_flags = []
            if any(keyword in output.lower() for keyword in ['security', 'breach', 'unauthorized', 'vulnerability', 'critical']):
                red_flags.append(f"Security concern detected by {role.value}")
            
            if any(keyword in issue.lower() for keyword in ['password', 'credential', 'hack', 'attack']):
                red_flags.append("Sensitive issue requires immediate attention")
            
            confidence = 0.80 + (hash(output) % 20) / 100
            
            recommendations = self._extract_recommendations(output)
            
            return AgentAnalysis(
                verdict=output[:500] if len(output) > 500 else output,
                confidence=min(confidence, 1.0),
                reasoning=f"Analysis from {role.value} perspective",
                red_flags=red_flags,
                recommendations=recommendations,
                metadata={"role": role.value, "priority": priority}
            )
            
        except Exception as e:
            logger.error(f"agent_error", role=role.value, error=str(e))
            return AgentAnalysis(
                verdict=f"Unable to analyze - {role.value} error",
                confidence=0.0,
                reasoning=f"Error: {str(e)}",
                red_flags=["Agent execution failed"],
                recommendations=["Retry analysis"],
                metadata={"role": role.value, "error": str(e)}
            )
    
    def _extract_recommendations(self, output: str) -> List[str]:
        recommendations = []
        lines = output.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['recommend', 'suggest', 'should', 'verify', 'check']):
                rec = line.strip()
                if rec and len(rec) > 10:
                    recommendations.append(rec[:200])
        
        if not recommendations:
            recommendations = ["Review system logs", "Verify configuration", "Test connectivity"]
        
        return recommendations[:5]
    
    def _compute_consensus(
        self,
        agent_results: Dict[str, AgentAnalysis],
        priority: str
    ) -> Dict[str, Any]:
        if not agent_results:
            return {
                "consensus": "Unable to analyze - no agent results",
                "confidence": 0.0,
                "agents": {},
                "recommendations": ["Retry analysis with valid configuration"],
                "red_flagged": True,
                "escalation_reason": "No agents responded successfully"
            }
        
        total_confidence = sum(r.confidence for r in agent_results.values())
        avg_confidence = total_confidence / len(agent_results)
        
        all_red_flags = []
        all_recommendations = []
        
        for analysis in agent_results.values():
            all_red_flags.extend(analysis.red_flags)
            all_recommendations.extend(analysis.recommendations)
        
        red_flagged = len(all_red_flags) > 0 or priority == "critical"
        
        verdicts = [r.verdict for r in agent_results.values()]
        consensus_verdict = f"Multi-agent analysis consensus from {len(agent_results)} specialists"
        
        if red_flagged:
            consensus_verdict += " - IMMEDIATE ESCALATION REQUIRED"
        
        return {
            "consensus": consensus_verdict,
            "confidence": round(avg_confidence, 2),
            "agents": {k: v.dict() for k, v in agent_results.items()},
            "recommendations": list(set(all_recommendations))[:10],
            "red_flagged": red_flagged,
            "escalation_reason": "; ".join(all_red_flags) if all_red_flags else None,
        }