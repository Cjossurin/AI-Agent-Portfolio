"""
Alita Agents Package
====================
Contains all AI agents for the content automation system.
"""

from .engagement_agent import EngagementAgent
from .ppc_agent import PPCAgent
from .rag_system import RAGSystem
from .marketing_intelligence_agent import (
    MarketingIntelligenceAgent,
    ContentIdea,
    ContentStrategy,
    ContentFormat,
    ContentGoal,
    Priority,
    generate_ideas,
    generate_strategy
)

__all__ = [
    # Agents
    "EngagementAgent",
    "PPCAgent", 
    "RAGSystem",
    "MarketingIntelligenceAgent",
    
    # Data classes
    "ContentIdea",
    "ContentStrategy",
    
    # Enums
    "ContentFormat",
    "ContentGoal",
    "Priority",
    
    # Convenience functions
    "generate_ideas",
    "generate_strategy",
]
