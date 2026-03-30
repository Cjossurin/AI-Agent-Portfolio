# agents/ppc_agent.py
"""
PPC Campaign Agent
==================
AI-powered agent for researching, planning, and executing PPC advertising campaigns.

Features:
- Competitor & keyword research via Tavily API
- Platform selection recommendations (Google, Meta, LinkedIn, TikTok)
- Campaign plan generation with ad copy
- Automated execution via platform APIs OR manual export

Usage:
    ppc = PPCAgent(client_id="demo_client")
    research = await ppc.research_campaign(business_description="...", objectives=["leads"])
    plan = await ppc.generate_campaign_plan(research_id=research["id"])
    export = ppc.export_for_manual_upload(plan["id"])
"""

import os
import sys
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# Add utils to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))

load_dotenv()


class PPCAgent:
    """
    PPC Campaign Agent for researching, planning, and executing ad campaigns.
    """
    
    def __init__(self, client_id: str = "demo_client"):
        self.client_id = client_id
        self.claude_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        
        # Model selection (use Sonnet for quality ad copy)
        self.model = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
        
        # In-memory storage (replace with database in production)
        self.research_cache: Dict[str, Dict] = {}
        self.campaign_plans: Dict[str, Dict] = {}
        
        # Platform configurations
        self.supported_platforms = {
            "google": {
                "name": "Google Ads",
                "best_for": ["search intent", "high-volume traffic", "B2B & B2C"],
                "min_budget": 500,
                "api_available": bool(os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"))
            },
            "meta": {
                "name": "Meta Ads (Facebook/Instagram)",
                "best_for": ["visual products", "demographics targeting", "B2C"],
                "min_budget": 300,
                "api_available": bool(os.getenv("META_ACCESS_TOKEN"))
            },
            "linkedin": {
                "name": "LinkedIn Ads",
                "best_for": ["B2B", "professional audiences", "high-ticket services"],
                "min_budget": 1000,
                "api_available": bool(os.getenv("LINKEDIN_ACCESS_TOKEN"))
            },
            "tiktok": {
                "name": "TikTok Ads",
                "best_for": ["Gen Z", "viral content", "video-first brands"],
                "min_budget": 500,
                "api_available": False  # Future integration
            }
        }
        
        print("✅ PPC Agent initialized")
        print(f"🔍 Tavily API: {'Connected' if self.tavily_api_key else 'Not configured'}")
        print(f"📊 Supported platforms: {', '.join(self.supported_platforms.keys())}")
    
    # =========================================================================
    # RESEARCH PHASE
    # =========================================================================
    
    async def research_campaign(
        self,
        business_description: str,
        industry: str = "general",
        budget_range: str = "$500-2000/month",
        objectives: List[str] = None,
        target_location: str = "United States"
    ) -> Dict[str, Any]:
        """
        Conduct comprehensive PPC research for a new campaign.
        
        Args:
            business_description: What the business does
            industry: Business vertical
            budget_range: Monthly ad spend budget
            objectives: Campaign goals (leads, sales, awareness, traffic)
            target_location: Geographic targeting
        
        Returns:
            Research results including competitors, keywords, audiences, platform recommendations
        """
        objectives = objectives or ["leads"]
        research_id = str(uuid.uuid4())
        
        print(f"\n🔬 Starting PPC research for: {business_description[:50]}...")
        
        # 1. Competitor Research
        competitors = await self._research_competitors(business_description, industry)
        
        # 2. Keyword Research
        keywords = await self._research_keywords(business_description, industry)
        
        # 3. Audience Insights
        audiences = await self._research_audiences(business_description, industry, target_location)
        
        # 4. Platform Recommendations
        platform_recs = self._recommend_platforms(industry, budget_range, objectives)
        
        # Compile research results
        research = {
            "id": research_id,
            "client_id": self.client_id,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
            "input": {
                "business_description": business_description,
                "industry": industry,
                "budget_range": budget_range,
                "objectives": objectives,
                "target_location": target_location
            },
            "results": {
                "competitors": competitors,
                "keywords": keywords,
                "audiences": audiences,
                "platform_recommendations": platform_recs
            },
            "status": "completed"
        }
        
        # Cache results
        self.research_cache[research_id] = research
        
        print(f"✅ Research complete! ID: {research_id}")
        return research
    
    async def _research_competitors(self, business_description: str, industry: str) -> Dict:
        """Research competitor PPC strategies using Tavily."""
        print("  📊 Researching competitors...")
        
        if not self.tavily_api_key:
            # Fallback to Claude-only analysis
            return await self._claude_competitor_analysis(business_description, industry)
        
        try:
            # Use Tavily for web research
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=self.tavily_api_key)
            
            query = f"{industry} PPC advertising strategies competitors {business_description[:50]}"
            results = tavily.search(query, max_results=5)
            
            # Process with Claude for insights
            return await self._process_competitor_research(results, business_description)
        except Exception as e:
            print(f"  ⚠️ Tavily error: {e}, using Claude fallback")
            return await self._claude_competitor_analysis(business_description, industry)
    
    async def _claude_competitor_analysis(self, business_description: str, industry: str) -> Dict:
        """Use Claude to generate competitor insights without external APIs."""
        prompt = f"""Analyze the competitive PPC landscape for this business:

Business: {business_description}
Industry: {industry}

Provide a JSON response with:
{{
    "top_competitors": ["list of 3-5 likely competitors"],
    "common_keywords": ["keywords competitors likely bid on"],
    "ad_angles": ["common messaging angles in this industry"],
    "estimated_cpc_range": "$X - $Y",
    "competitive_intensity": "low/medium/high"
}}"""
        
        response = self.claude_client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text)
        except:
            return {"raw_analysis": response.content[0].text}
    
    async def _process_competitor_research(self, tavily_results: Dict, business_description: str) -> Dict:
        """Process Tavily research with Claude for actionable insights."""
        prompt = f"""Based on this research about PPC advertising in the market, provide competitor insights.

Research Results:
{json.dumps(tavily_results, indent=2)}

Business Context: {business_description}

Provide a JSON response with:
{{
    "top_competitors": ["identified competitors"],
    "competitor_strategies": ["what they're doing well"],
    "gaps_opportunities": ["underserved angles we can target"],
    "common_keywords": ["keywords to consider"],
    "ad_copy_themes": ["messaging themes that work"]
}}"""
        
        response = self.claude_client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text)
        except:
            return {"raw_analysis": response.content[0].text}
    
    async def _research_keywords(self, business_description: str, industry: str) -> Dict:
        """Research keyword opportunities."""
        print("  🔑 Researching keywords...")
        
        prompt = f"""Generate a comprehensive keyword list for PPC advertising.

Business: {business_description}
Industry: {industry}

Provide a JSON response with:
{{
    "high_intent_keywords": [
        {{"keyword": "example", "intent": "transactional", "estimated_volume": "high/medium/low", "competition": "high/medium/low"}}
    ],
    "long_tail_keywords": ["longer, specific keywords"],
    "negative_keywords": ["keywords to exclude"],
    "branded_keywords": ["brand-related terms"],
    "competitor_keywords": ["competitor brand terms to consider"]
}}"""
        
        response = self.claude_client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text)
        except:
            return {"raw_analysis": response.content[0].text}
    
    async def _research_audiences(self, business_description: str, industry: str, location: str) -> Dict:
        """Research target audience profiles."""
        print("  👥 Researching audiences...")
        
        prompt = f"""Define target audience profiles for PPC advertising.

Business: {business_description}
Industry: {industry}
Location: {location}

Provide a JSON response with:
{{
    "primary_audience": {{
        "demographics": {{"age": "range", "gender": "all/male/female", "income": "range"}},
        "interests": ["interest categories"],
        "behaviors": ["online behaviors"],
        "pain_points": ["problems they have"]
    }},
    "secondary_audiences": [
        {{"name": "segment name", "description": "who they are"}}
    ],
    "exclusions": ["audiences to exclude"],
    "lookalike_sources": ["best sources for lookalike audiences"]
}}"""
        
        response = self.claude_client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text)
        except:
            return {"raw_analysis": response.content[0].text}
    
    def _recommend_platforms(
        self, 
        industry: str, 
        budget_range: str, 
        objectives: List[str]
    ) -> List[Dict]:
        """Recommend advertising platforms based on business needs."""
        print("  📱 Analyzing platform fit...")
        
        # Parse budget
        try:
            budget_low = int(''.join(filter(str.isdigit, budget_range.split('-')[0])))
        except:
            budget_low = 500
        
        recommendations = []
        
        # Score each platform
        for platform_id, platform in self.supported_platforms.items():
            score = 0
            reasons = []
            
            # Budget fit
            if budget_low >= platform["min_budget"]:
                score += 2
                reasons.append(f"Budget meets minimum (${platform['min_budget']}/mo)")
            else:
                reasons.append(f"Budget below recommended minimum (${platform['min_budget']}/mo)")
            
            # Objective fit
            if "leads" in objectives and platform_id in ["google", "linkedin", "meta"]:
                score += 2
                reasons.append("Strong for lead generation")
            if "awareness" in objectives and platform_id in ["meta", "tiktok"]:
                score += 2
                reasons.append("Excellent for brand awareness")
            if "sales" in objectives and platform_id in ["google", "meta"]:
                score += 2
                reasons.append("Proven for direct sales")
            
            # Industry fit
            b2b_industries = ["technology", "consulting", "saas", "professional services"]
            b2c_industries = ["retail", "ecommerce", "food", "entertainment"]
            
            if industry.lower() in b2b_industries and platform_id == "linkedin":
                score += 3
                reasons.append("Ideal for B2B industries")
            if industry.lower() in b2c_industries and platform_id in ["meta", "tiktok"]:
                score += 2
                reasons.append("Strong for B2C")
            
            # Google is generally always relevant
            if platform_id == "google":
                score += 1
                reasons.append("Captures high-intent search traffic")
            
            recommendations.append({
                "platform": platform_id,
                "name": platform["name"],
                "score": score,
                "reasons": reasons,
                "api_available": platform["api_available"],
                "best_for": platform["best_for"]
            })
        
        # Sort by score
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations
    
    # =========================================================================
    # PLANNING PHASE
    # =========================================================================
    
    async def generate_campaign_plan(
        self,
        research_id: str,
        platforms: List[str] = None,
        execution_mode: str = "manual"  # "manual" or "automated"
    ) -> Dict[str, Any]:
        """
        Generate a complete campaign plan based on research.
        
        Args:
            research_id: ID of completed research
            platforms: Which platforms to generate plans for
            execution_mode: "manual" for export, "automated" for API execution
        
        Returns:
            Complete campaign plan with ad copy, targeting, and budget allocation
        """
        if research_id not in self.research_cache:
            raise ValueError(f"Research not found: {research_id}")
        
        research = self.research_cache[research_id]
        platforms = platforms or ["google", "meta"]
        
        print(f"\n📝 Generating campaign plan for: {', '.join(platforms)}")
        
        plan_id = str(uuid.uuid4())
        platform_plans = {}
        
        for platform in platforms:
            print(f"  📋 Building {platform} campaign...")
            platform_plans[platform] = await self._generate_platform_plan(
                platform, research, execution_mode
            )
        
        plan = {
            "id": plan_id,
            "research_id": research_id,
            "client_id": self.client_id,
            "created_at": datetime.now().isoformat(),
            "execution_mode": execution_mode,
            "platforms": platform_plans,
            "status": "pending_review"
        }
        
        self.campaign_plans[plan_id] = plan
        
        print(f"✅ Campaign plan generated! ID: {plan_id}")
        return plan
    
    async def _generate_platform_plan(
        self, 
        platform: str, 
        research: Dict, 
        execution_mode: str
    ) -> Dict:
        """Generate platform-specific campaign plan."""
        
        research_input = research["input"]
        research_results = research["results"]
        
        prompt = f"""Create a detailed {platform.upper()} advertising campaign plan.

BUSINESS CONTEXT:
{research_input['business_description']}
Industry: {research_input['industry']}
Budget: {research_input['budget_range']}
Objectives: {', '.join(research_input['objectives'])}
Location: {research_input['target_location']}

RESEARCH INSIGHTS:
Keywords: {json.dumps(research_results.get('keywords', {}), indent=2)[:1000]}
Audiences: {json.dumps(research_results.get('audiences', {}), indent=2)[:1000]}

Generate a complete campaign plan as JSON:
{{
    "campaign_name": "descriptive name",
    "campaign_objective": "platform-specific objective",
    "daily_budget": number,
    "bid_strategy": "strategy name",
    "ad_groups": [
        {{
            "name": "ad group name",
            "targeting": {{
                "keywords": ["for search campaigns"],
                "audiences": ["for display/social"],
                "demographics": {{}},
                "placements": ["optional"]
            }},
            "ads": [
                {{
                    "headline_1": "30 chars max",
                    "headline_2": "30 chars max",
                    "headline_3": "30 chars max",
                    "description_1": "90 chars max",
                    "description_2": "90 chars max",
                    "cta": "call to action",
                    "final_url": "landing page path"
                }}
            ]
        }}
    ],
    "negative_keywords": ["keywords to exclude"],
    "schedule": {{"days": "all/weekdays", "hours": "all/business"}},
    "tracking": ["conversion actions to track"]
}}

Create 2-3 ad groups with 2-3 ad variants each."""

        response = self.claude_client.messages.create(
            model=self.model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text)
        except:
            return {"raw_plan": response.content[0].text}
    
    # =========================================================================
    # EXPORT / EXECUTION PHASE
    # =========================================================================
    
    def export_for_manual_upload(
        self, 
        plan_id: str, 
        format: str = "json"
    ) -> Dict[str, str]:
        """
        Export campaign plan for manual upload to ad platforms.
        
        Args:
            plan_id: ID of the campaign plan
            format: "json" or "csv"
        
        Returns:
            Dictionary with export file contents for each platform
        """
        if plan_id not in self.campaign_plans:
            raise ValueError(f"Plan not found: {plan_id}")
        
        plan = self.campaign_plans[plan_id]
        exports = {}
        
        for platform, platform_plan in plan["platforms"].items():
            if format == "json":
                exports[f"{platform}_campaign.json"] = json.dumps(platform_plan, indent=2)
            elif format == "csv":
                exports[f"{platform}_campaign.csv"] = self._plan_to_csv(platform, platform_plan)
            
            # Always include ad copy as separate text file
            exports[f"{platform}_ad_copy.txt"] = self._extract_ad_copy(platform_plan)
        
        print(f"📦 Exported {len(exports)} files for manual upload")
        return exports
    
    def _plan_to_csv(self, platform: str, plan: Dict) -> str:
        """Convert plan to CSV format for bulk upload."""
        lines = ["Campaign,Ad Group,Headline 1,Headline 2,Headline 3,Description 1,Description 2,Final URL"]
        
        campaign_name = plan.get("campaign_name", "Campaign")
        for ad_group in plan.get("ad_groups", []):
            group_name = ad_group.get("name", "Ad Group")
            for ad in ad_group.get("ads", []):
                line = ",".join([
                    f'"{campaign_name}"',
                    f'"{group_name}"',
                    f'"{ad.get("headline_1", "")}"',
                    f'"{ad.get("headline_2", "")}"',
                    f'"{ad.get("headline_3", "")}"',
                    f'"{ad.get("description_1", "")}"',
                    f'"{ad.get("description_2", "")}"',
                    f'"{ad.get("final_url", "")}"'
                ])
                lines.append(line)
        
        return "\n".join(lines)
    
    def _extract_ad_copy(self, plan: Dict) -> str:
        """Extract all ad copy for easy review."""
        lines = ["=" * 60, "AD COPY EXPORT", "=" * 60, ""]
        
        for i, ad_group in enumerate(plan.get("ad_groups", []), 1):
            lines.append(f"\n📁 AD GROUP {i}: {ad_group.get('name', 'Untitled')}")
            lines.append("-" * 40)
            
            for j, ad in enumerate(ad_group.get("ads", []), 1):
                lines.append(f"\n  📝 Ad Variant {j}:")
                lines.append(f"     Headline 1: {ad.get('headline_1', '')}")
                lines.append(f"     Headline 2: {ad.get('headline_2', '')}")
                lines.append(f"     Headline 3: {ad.get('headline_3', '')}")
                lines.append(f"     Description 1: {ad.get('description_1', '')}")
                lines.append(f"     Description 2: {ad.get('description_2', '')}")
                lines.append(f"     CTA: {ad.get('cta', '')}")
                lines.append(f"     URL: {ad.get('final_url', '')}")
        
        return "\n".join(lines)
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_research(self, research_id: str) -> Optional[Dict]:
        """Retrieve cached research by ID."""
        return self.research_cache.get(research_id)
    
    def get_plan(self, plan_id: str) -> Optional[Dict]:
        """Retrieve campaign plan by ID."""
        return self.campaign_plans.get(plan_id)
    
    def list_research(self) -> List[Dict]:
        """List all cached research for this client."""
        return [
            r for r in self.research_cache.values() 
            if r["client_id"] == self.client_id
        ]
    
    def list_plans(self) -> List[Dict]:
        """List all campaign plans for this client."""
        return [
            p for p in self.campaign_plans.values() 
            if p["client_id"] == self.client_id
        ]


# =============================================================================
# CLI / Testing
# =============================================================================

async def main():
    """Test the PPC Agent."""
    import asyncio
    
    ppc = PPCAgent(client_id="demo_client")
    
    # Run research
    research = await ppc.research_campaign(
        business_description="AI consulting and automation services for small businesses in South Florida",
        industry="technology",
        budget_range="$1000-3000/month",
        objectives=["leads", "brand_awareness"],
        target_location="South Florida"
    )
    
    print("\n📊 Research Results:")
    print(json.dumps(research["results"]["platform_recommendations"], indent=2))
    
    # Generate plan
    plan = await ppc.generate_campaign_plan(
        research_id=research["id"],
        platforms=["google", "meta"],
        execution_mode="manual"
    )
    
    print("\n📋 Campaign Plan Preview:")
    for platform, platform_plan in plan["platforms"].items():
        print(f"\n{platform.upper()}:")
        print(f"  Campaign: {platform_plan.get('campaign_name', 'N/A')}")
        print(f"  Ad Groups: {len(platform_plan.get('ad_groups', []))}")
    
    # Export
    exports = ppc.export_for_manual_upload(plan["id"], format="json")
    print(f"\n📦 Generated {len(exports)} export files")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
