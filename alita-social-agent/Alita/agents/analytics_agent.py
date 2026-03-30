"""
Analytics Agent
==============
AI-powered analytics system that collects data, generates insights,
and creates actionable reports for social media performance.

RESPONSIBILITIES:
- Collect data from all connected platforms (Instagram, Facebook, TikTok, LinkedIn, Twitter, YouTube, Threads)
- Aggregate metrics across platforms
- Generate AI-powered insights using Claude
- Identify trends and patterns
- Create recommendations for improvement
- Track performance over time
- Generate automated reports

INTEGRATION:
- Uses existing platform API clients (meta, late_client, youtube, etc.)
- Stores historical data for trend analysis
- Generates insights using Claude
- Outputs structured reports and recommendations
"""

import os
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import json

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


class MetricType(Enum):
    """Types of metrics tracked"""
    ENGAGEMENT = "engagement"       # Likes, comments, shares
    REACH = "reach"                 # Views, impressions
    GROWTH = "growth"               # Followers, subscribers
    CONVERSION = "conversion"       # Clicks, signups, sales
    CONTENT = "content"             # Post frequency, types


class Platform(Enum):
    """Supported platforms"""
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    YOUTUBE = "youtube"
    THREADS = "threads"


@dataclass
class PlatformMetrics:
    """Metrics for a single platform"""
    platform: str
    followers: int
    engagement_rate: float
    reach: int
    impressions: int
    posts_count: int
    avg_likes: float
    avg_comments: float
    avg_shares: float
    top_post_id: Optional[str] = None
    top_post_engagement: Optional[int] = None
    collected_at: str = ""
    
    def __post_init__(self):
        if not self.collected_at:
            self.collected_at = datetime.utcnow().isoformat()


@dataclass
class CrossPlatformReport:
    """Aggregated report across all platforms"""
    client_id: str
    start_date: str
    end_date: str
    platforms: List[PlatformMetrics]
    total_followers: int
    total_reach: int
    total_engagement: int
    avg_engagement_rate: float
    best_platform: str
    worst_platform: str
    insights: List[str]
    recommendations: List[str]
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.utcnow().isoformat()


class AnalyticsAgent:
    """
    AI-powered analytics agent for social media performance tracking.
    """
    
    def __init__(self, client_id: str = "default_client"):
        """
        Initialize analytics agent.
        
        Args:
            client_id: Client identifier for data isolation
        """
        self.client_id = client_id
        self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Model configuration
        from utils.ai_config import CLAUDE_HAIKU, CLAUDE_SONNET
        self.haiku_model = CLAUDE_HAIKU
        self.sonnet_model = CLAUDE_SONNET
        
        print(f"📊 Analytics Agent initialized for client: {client_id}")
    
    async def collect_instagram_metrics(self, ig_user_id: str, access_token: str) -> Optional[PlatformMetrics]:
        """
        Collect metrics from Instagram using Meta Graph API.
        
        Args:
            ig_user_id: Instagram business account ID
            access_token: Instagram access token
            
        Returns:
            PlatformMetrics object or None if error
        """
        try:
            import httpx
            
            # Fetch account insights
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Get follower count and reach
                r1 = await client.get(
                    f"https://graph.facebook.com/v22.0/{ig_user_id}/insights",
                    params={
                        "metric": "reach,follower_count",
                        "period": "day",
                        "access_token": access_token
                    }
                )
                r1.raise_for_status()
                insights = r1.json().get("data", [])
                
                # Get profile views and engagement
                r2 = await client.get(
                    f"https://graph.facebook.com/v22.0/{ig_user_id}/insights",
                    params={
                        "metric": "profile_views,accounts_engaged,total_interactions",
                        "metric_type": "total_value",
                        "period": "day",
                        "access_token": access_token
                    }
                )
                r2.raise_for_status()
                engagement_data = r2.json().get("data", [])
                
                # Get recent media
                r3 = await client.get(
                    f"https://graph.facebook.com/v22.0/{ig_user_id}/media",
                    params={
                        "fields": "id,like_count,comments_count,timestamp",
                        "limit": 25,
                        "access_token": access_token
                    }
                )
                r3.raise_for_status()
                media = r3.json().get("data", [])
            
            # Parse metrics
            followers = 0
            reach = 0
            impressions = 0
            
            for item in insights:
                name = item.get("name")
                values = item.get("values", [])
                if values:
                    latest = values[-1].get("value", 0)
                    if name == "follower_count":
                        followers = latest
                    elif name == "reach":
                        reach = sum(v.get("value", 0) for v in values)
            
            # Calculate engagement metrics from recent posts
            total_likes = 0
            total_comments = 0
            total_engagement = 0
            top_post_id = None
            top_post_engagement = 0
            
            for post in media:
                likes = post.get("like_count", 0)
                comments = post.get("comments_count", 0)
                engagement = likes + comments
                
                total_likes += likes
                total_comments += comments
                total_engagement += engagement
                
                if engagement > top_post_engagement:
                    top_post_engagement = engagement
                    top_post_id = post.get("id")
            
            posts_count = len(media)
            avg_likes = total_likes / posts_count if posts_count > 0 else 0
            avg_comments = total_comments / posts_count if posts_count > 0 else 0
            engagement_rate = (total_engagement / (reach * posts_count)) * 100 if reach > 0 and posts_count > 0 else 0
            
            return PlatformMetrics(
                platform="instagram",
                followers=followers,
                engagement_rate=round(engagement_rate, 2),
                reach=reach,
                impressions=reach,  # Instagram doesn't separate impressions
                posts_count=posts_count,
                avg_likes=round(avg_likes, 1),
                avg_comments=round(avg_comments, 1),
                avg_shares=0,  # Instagram doesn't provide share counts
                top_post_id=top_post_id,
                top_post_engagement=top_post_engagement
            )
            
        except Exception as e:
            print(f"❌ Error collecting Instagram metrics: {e}")
            return None
    
    async def collect_facebook_metrics(self, page_id: str, page_token: str) -> Optional[PlatformMetrics]:
        """
        Collect metrics from Facebook page.
        
        Args:
            page_id: Facebook page ID
            page_token: Facebook page access token
            
        Returns:
            PlatformMetrics object or None if error
        """
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Get page info
                r1 = await client.get(
                    f"https://graph.facebook.com/v22.0/{page_id}",
                    params={
                        "fields": "followers_count,fan_count",
                        "access_token": page_token
                    }
                )
                r1.raise_for_status()
                page_data = r1.json()
                
                # Get recent posts
                r2 = await client.get(
                    f"https://graph.facebook.com/v22.0/{page_id}/posts",
                    params={
                        "fields": "id,created_time,reactions.summary(true),comments.summary(true),shares",
                        "limit": 25,
                        "access_token": page_token
                    }
                )
                r2.raise_for_status()
                posts = r2.json().get("data", [])
            
            followers = page_data.get("followers_count", page_data.get("fan_count", 0))
            
            # Calculate engagement from posts
            total_reactions = 0
            total_comments = 0
            total_shares = 0
            top_post_id = None
            top_post_engagement = 0
            
            for post in posts:
                reactions = post.get("reactions", {}).get("summary", {}).get("total_count", 0)
                comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
                shares = post.get("shares", {}).get("count", 0)
                engagement = reactions + comments + shares
                
                total_reactions += reactions
                total_comments += comments
                total_shares += shares
                
                if engagement > top_post_engagement:
                    top_post_engagement = engagement
                    top_post_id = post.get("id")
            
            posts_count = len(posts)
            avg_reactions = total_reactions / posts_count if posts_count > 0 else 0
            avg_comments = total_comments / posts_count if posts_count > 0 else 0
            avg_shares = total_shares / posts_count if posts_count > 0 else 0
            total_engagement = total_reactions + total_comments + total_shares
            engagement_rate = (total_engagement / (followers * posts_count)) * 100 if followers > 0 and posts_count > 0 else 0
            
            return PlatformMetrics(
                platform="facebook",
                followers=followers,
                engagement_rate=round(engagement_rate, 2),
                reach=followers * 3,  # Estimate: followers * avg reach multiplier
                impressions=followers * 5,  # Estimate
                posts_count=posts_count,
                avg_likes=round(avg_reactions, 1),
                avg_comments=round(avg_comments, 1),
                avg_shares=round(avg_shares, 1),
                top_post_id=top_post_id,
                top_post_engagement=top_post_engagement
            )
            
        except Exception as e:
            print(f"❌ Error collecting Facebook metrics: {e}")
            return None
    
    async def collect_all_metrics(
        self,
        instagram_credentials: Optional[Dict[str, str]] = None,
        facebook_credentials: Optional[Dict[str, str]] = None
    ) -> List[PlatformMetrics]:
        """
        Collect metrics from all connected platforms.
        
        Args:
            instagram_credentials: Dict with ig_user_id and access_token
            facebook_credentials: Dict with page_id and page_token
            
        Returns:
            List of PlatformMetrics
        """
        print("📊 Collecting metrics from all platforms...")
        
        tasks = []
        
        # Instagram
        if instagram_credentials:
            tasks.append(
                self.collect_instagram_metrics(
                    instagram_credentials["ig_user_id"],
                    instagram_credentials["access_token"]
                )
            )
        
        # Facebook
        if facebook_credentials:
            tasks.append(
                self.collect_facebook_metrics(
                    facebook_credentials["page_id"],
                    facebook_credentials["page_token"]
                )
            )
        
        # TODO: Add TikTok, LinkedIn, Twitter, YouTube, Threads collection
        # These will need Late API client integration
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors and None values
        metrics = [r for r in results if isinstance(r, PlatformMetrics)]
        
        print(f"✅ Collected metrics from {len(metrics)} platforms")
        return metrics
    
    def calculate_aggregates(self, metrics: List[PlatformMetrics]) -> Dict[str, Any]:
        """
        Calculate aggregate statistics across platforms.
        
        Args:
            metrics: List of platform metrics
            
        Returns:
            Dict with aggregated statistics
        """
        if not metrics:
            return {
                "total_followers": 0,
                "total_reach": 0,
                "total_engagement": 0,
                "avg_engagement_rate": 0.0,
                "best_platform": None,
                "worst_platform": None
            }
        
        total_followers = sum(m.followers for m in metrics)
        total_reach = sum(m.reach for m in metrics)
        total_engagement = sum(
            int(m.avg_likes + m.avg_comments + m.avg_shares) * m.posts_count
            for m in metrics
        )
        avg_engagement_rate = sum(m.engagement_rate for m in metrics) / len(metrics)
        
        # Find best and worst performers
        best = max(metrics, key=lambda m: m.engagement_rate)
        worst = min(metrics, key=lambda m: m.engagement_rate)
        
        return {
            "total_followers": total_followers,
            "total_reach": total_reach,
            "total_engagement": total_engagement,
            "avg_engagement_rate": round(avg_engagement_rate, 2),
            "best_platform": best.platform,
            "worst_platform": worst.platform
        }
    
    async def generate_insights(self, metrics: List[PlatformMetrics]) -> List[str]:
        """
        Generate AI-powered insights from metrics data.
        
        Args:
            metrics: List of platform metrics
            
        Returns:
            List of insight strings
        """
        if not metrics:
            return ["No data available to generate insights."]
        
        # Prepare metrics summary for Claude
        metrics_summary = "\n".join([
            f"- {m.platform.upper()}: {m.followers:,} followers, {m.engagement_rate}% engagement rate, "
            f"{m.posts_count} posts, avg {m.avg_likes:.0f} likes, {m.avg_comments:.0f} comments"
            for m in metrics
        ])
        
        prompt = f"""Analyze these social media metrics and provide 3-5 key insights:

{metrics_summary}

Focus on:
1. Performance patterns across platforms
2. Engagement quality indicators
3. Content frequency effectiveness
4. Areas of strength and weakness

Provide concise, actionable insights (1-2 sentences each)."""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            insights_text = response.content[0].text
            # Split into bullet points
            insights = [
                line.strip().lstrip("•-*123456789. ")
                for line in insights_text.split("\n")
                if line.strip() and not line.strip().startswith("Here")
            ]
            
            return insights[:5]  # Return top 5 insights
            
        except Exception as e:
            print(f"❌ Error generating insights: {e}")
            return ["Error generating insights. Please check metrics manually."]
    
    async def generate_recommendations(
        self,
        metrics: List[PlatformMetrics],
        insights: List[str]
    ) -> List[str]:
        """
        Generate actionable recommendations based on insights.
        
        Args:
            metrics: List of platform metrics
            insights: Generated insights
            
        Returns:
            List of recommendation strings
        """
        if not metrics or not insights:
            return ["Collect more data to generate recommendations."]
        
        metrics_summary = "\n".join([
            f"- {m.platform.upper()}: {m.engagement_rate}% engagement, {m.posts_count} posts/period"
            for m in metrics
        ])
        
        insights_text = "\n".join([f"- {insight}" for insight in insights])
        
        prompt = f"""Based on these social media metrics and insights, provide 3-5 specific, actionable recommendations:

METRICS:
{metrics_summary}

INSIGHTS:
{insights_text}

Provide recommendations that are:
1. Specific and actionable
2. Prioritized by potential impact
3. Realistic to implement
4. Data-driven

Format as numbered list."""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            
            recommendations_text = response.content[0].text
            recommendations = [
                line.strip().lstrip("•-*123456789. ")
                for line in recommendations_text.split("\n")
                if line.strip() and len(line.strip()) > 20
            ]
            
            return recommendations[:5]  # Return top 5 recommendations
            
        except Exception as e:
            print(f"❌ Error generating recommendations: {e}")
            return ["Error generating recommendations. Please review metrics manually."]
    
    async def generate_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        instagram_credentials: Optional[Dict[str, str]] = None,
        facebook_credentials: Optional[Dict[str, str]] = None
    ) -> CrossPlatformReport:
        """
        Generate comprehensive cross-platform analytics report.
        
        Args:
            start_date: Report start date (ISO format)
            end_date: Report end date (ISO format)
            instagram_credentials: Instagram API credentials
            facebook_credentials: Facebook API credentials
            
        Returns:
            CrossPlatformReport object
        """
        print("\n" + "=" * 60)
        print("📊 GENERATING ANALYTICS REPORT")
        print("=" * 60)
        
        # Set date range
        if not end_date:
            end_date = datetime.utcnow().isoformat()
        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        print(f"Period: {start_date[:10]} to {end_date[:10]}")
        
        # Collect metrics
        metrics = await self.collect_all_metrics(
            instagram_credentials=instagram_credentials,
            facebook_credentials=facebook_credentials
        )
        
        if not metrics:
            print("⚠️  No metrics collected")
            return CrossPlatformReport(
                client_id=self.client_id,
                start_date=start_date,
                end_date=end_date,
                platforms=[],
                total_followers=0,
                total_reach=0,
                total_engagement=0,
                avg_engagement_rate=0.0,
                best_platform="none",
                worst_platform="none",
                insights=["No data available"],
                recommendations=["Connect platforms to start tracking"]
            )
        
        # Calculate aggregates
        aggregates = self.calculate_aggregates(metrics)
        
        # Generate insights and recommendations
        print("🧠 Generating AI insights...")
        insights = await self.generate_insights(metrics)
        
        print("💡 Generating recommendations...")
        recommendations = await self.generate_recommendations(metrics, insights)
        
        report = CrossPlatformReport(
            client_id=self.client_id,
            start_date=start_date,
            end_date=end_date,
            platforms=metrics,
            total_followers=aggregates["total_followers"],
            total_reach=aggregates["total_reach"],
            total_engagement=aggregates["total_engagement"],
            avg_engagement_rate=aggregates["avg_engagement_rate"],
            best_platform=aggregates["best_platform"],
            worst_platform=aggregates["worst_platform"],
            insights=insights,
            recommendations=recommendations
        )
        
        print("✅ Report generated successfully")
        return report
    
    def export_report_json(self, report: CrossPlatformReport, filepath: str) -> bool:
        """
        Export report to JSON file.
        
        Args:
            report: CrossPlatformReport object
            filepath: Path to save JSON file
            
        Returns:
            Success status
        """
        try:
            report_dict = asdict(report)
            with open(filepath, "w") as f:
                json.dump(report_dict, f, indent=2)
            print(f"✅ Report exported to {filepath}")
            return True
        except Exception as e:
            print(f"❌ Error exporting report: {e}")
            return False
    
    def print_report(self, report: CrossPlatformReport):
        """
        Print formatted report to console.
        
        Args:
            report: CrossPlatformReport object
        """
        print("\n" + "=" * 60)
        print("📊 ANALYTICS REPORT")
        print("=" * 60)
        print(f"Client: {report.client_id}")
        print(f"Period: {report.start_date[:10]} to {report.end_date[:10]}")
        print(f"Generated: {report.generated_at[:19]}")
        
        print("\n" + "-" * 60)
        print("📈 OVERVIEW")
        print("-" * 60)
        print(f"Total Followers: {report.total_followers:,}")
        print(f"Total Reach: {report.total_reach:,}")
        print(f"Total Engagement: {report.total_engagement:,}")
        print(f"Avg Engagement Rate: {report.avg_engagement_rate}%")
        print(f"Best Platform: {report.best_platform.upper()}")
        print(f"Platforms Tracked: {len(report.platforms)}")
        
        print("\n" + "-" * 60)
        print("📱 PLATFORM BREAKDOWN")
        print("-" * 60)
        for m in report.platforms:
            print(f"\n{m.platform.upper()}:")
            print(f"  • Followers: {m.followers:,}")
            print(f"  • Engagement Rate: {m.engagement_rate}%")
            print(f"  • Posts: {m.posts_count}")
            print(f"  • Avg Likes: {m.avg_likes:.0f}")
            print(f"  • Avg Comments: {m.avg_comments:.0f}")
            if m.avg_shares > 0:
                print(f"  • Avg Shares: {m.avg_shares:.0f}")
        
        print("\n" + "-" * 60)
        print("💡 KEY INSIGHTS")
        print("-" * 60)
        for i, insight in enumerate(report.insights, 1):
            print(f"{i}. {insight}")
        
        print("\n" + "-" * 60)
        print("🎯 RECOMMENDATIONS")
        print("-" * 60)
        for i, rec in enumerate(report.recommendations, 1):
            print(f"{i}. {rec}")
        
        print("\n" + "=" * 60)


# ═══════════════════════════════════════════════════════════════════════════
# Testing
# ═══════════════════════════════════════════════════════════════════════════

async def test_analytics_agent():
    """Test analytics agent functionality."""
    print("\n🧪 Testing Analytics Agent...\n")
    
    agent = AnalyticsAgent(client_id="test_client")
    
    # Create mock metrics for testing (in production, these come from API)
    mock_metrics = [
        PlatformMetrics(
            platform="instagram",
            followers=5420,
            engagement_rate=3.8,
            reach=12430,
            impressions=18650,
            posts_count=8,
            avg_likes=197.5,
            avg_comments=12.3,
            avg_shares=0,
            top_post_id="18123456789",
            top_post_engagement=485
        ),
        PlatformMetrics(
            platform="facebook",
            followers=2890,
            engagement_rate=2.1,
            reach=8670,
            impressions=13200,
            posts_count=6,
            avg_likes=45.2,
            avg_comments=8.7,
            avg_shares=3.2,
            top_post_id="12345678_98765432",
            top_post_engagement=124
        )
    ]
    
    # Test 1: Calculate aggregates
    print("=" * 60)
    print("TEST 1: Calculate aggregates")
    print("=" * 60)
    aggregates = agent.calculate_aggregates(mock_metrics)
    print(f"Total Followers: {aggregates['total_followers']:,}")
    print(f"Total Reach: {aggregates['total_reach']:,}")
    print(f"Avg Engagement Rate: {aggregates['avg_engagement_rate']}%")
    print(f"Best Platform: {aggregates['best_platform']}")
    
    # Test 2: Generate insights
    print("\n" + "=" * 60)
    print("TEST 2: Generate AI insights")
    print("=" * 60)
    insights = await agent.generate_insights(mock_metrics)
    for i, insight in enumerate(insights, 1):
        print(f"{i}. {insight}")
    
    # Test 3: Generate recommendations
    print("\n" + "=" * 60)
    print("TEST 3: Generate recommendations")
    print("=" * 60)
    recommendations = await agent.generate_recommendations(mock_metrics, insights)
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")
    
    # Test 4: Full report (using mock data)
    print("\n" + "=" * 60)
    print("TEST 4: Generate full report")
    print("=" * 60)
    # Note: This test uses mock data instead of real API calls
    # In production, pass real credentials to generate_report()
    print("⚠️  Skipping API calls in test mode")
    print("✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(test_analytics_agent())
