"""
Content Orchestrator - End-to-end content generation and posting workflow
Coordinates: Content Generation → (Optional Review) → Multi-Platform Posting

Workflow:
1. Accept content request (platform, topic, goal, etc.)
2. Generate content using Content Creation Agent
3. (Optional) Queue for human review/approval
4. Post to platforms using Posting Agent
5. Track results and handle failures
6. Comprehensive logging and monitoring
"""

import asyncio
import os
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path

# Import our agents
from agents.content_agent import ContentCreationAgent, ContentRequest, GeneratedContent
from agents.posting_agent import PostingAgent, ContentPost, PostingResult
from agents.client_profile_manager import ClientProfileManager, ClientProfile
from utils.image_generator import generate_image

# Setup logging
Path("logs").mkdir(exist_ok=True)  # Ensure logs directory exists first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/orchestrator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Status of content workflow."""
    GENERATING = "generating"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    POSTING = "posting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ContentWorkflow:
    """Complete workflow for generating and posting content."""
    workflow_id: str
    client_id: str
    platforms: List[str]  # Target platforms
    content_type: str  # Type of content (post, reel, article, etc.)
    topic: str
    goal: str  # views_engagement, follower_growth, conversions_sales
    client_voice: Optional[str] = None
    rag_context: Optional[str] = None
    require_review: bool = False  # If True, content waits for approval before posting
    media_urls: Optional[List[str]] = None
    scheduled_time: Optional[str] = None
    
    # Results
    generated_content: Optional[List[GeneratedContent]] = None
    posting_results: Optional[List[PostingResult]] = None
    status: str = "pending"
    error_log: List[str] = field(default_factory=list)  # Track all errors
    created_at: str = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class ContentOrchestrator:
    """
    Orchestrates the complete content generation and posting workflow.
    
    Features:
    - Generate content for multiple platforms simultaneously
    - Optional human review/approval step
    - Multi-platform posting with intelligent routing
    - Comprehensive tracking and error handling
    - Manual queue for failed posts
    
    Usage:
        orchestrator = ContentOrchestrator(client_id="client_123")
        workflow = await orchestrator.create_and_post_content(
            platforms=["twitter", "linkedin"],
            content_type="post",
            topic="AI automation",
            goal="views_engagement"
        )
    """
    
    def __init__(self, client_id: str):
        """
        Initialize orchestrator.
        
        Args:
            client_id: Client identifier for multi-client support
        """
        self.client_id = client_id
        
        # Load client profile for niche-specific settings
        self.profile_manager = ClientProfileManager()
        self.client_profile: Optional[ClientProfile] = self.profile_manager.get_client_profile(client_id)
        
        # Initialize agents
        self.content_agent = ContentCreationAgent(client_id=client_id)
        self.posting_agent = PostingAgent(client_id=client_id)
        
        # Track workflows
        self.workflows: Dict[str, ContentWorkflow] = {}
        self.workflow_counter = 0
        
        # Ensure logs directory exists
        Path("logs").mkdir(exist_ok=True)
        
        logger.info(f"Content Orchestrator initialized for client: {client_id}")
        if self.client_profile:
            niche_name = self.client_profile.niche.value if hasattr(self.client_profile.niche, 'value') else self.client_profile.niche
            logger.info(f"Client niche: {niche_name}, platforms: {self.client_profile.platforms}")
    
    def _generate_workflow_id(self) -> str:
        """Generate unique workflow ID."""
        self.workflow_counter += 1
        return f"workflow_{self.client_id}_{self.workflow_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    async def create_and_post_content(
        self,
        platforms: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        topic: Optional[str] = None,
        goal: str = "views_engagement",
        client_voice: Optional[str] = None,
        rag_context: Optional[str] = None,
        require_review: bool = False,
        media_urls: Optional[List[str]] = None,
        scheduled_time: Optional[str] = None
    ) -> ContentWorkflow:
        """
        Complete workflow: Generate content and post to platforms.
        Uses niche-specific settings as defaults.
        
        Args:
            platforms: List of target platforms (uses niche platforms if not provided)
            content_type: Type of content (post, reel, article, thread, etc.)
            topic: Content topic/subject (uses content pillars if not provided)
            goal: Content goal (views_engagement, follower_growth, conversions_sales)
            client_voice: Client's voice/style guidelines (uses niche tone if not provided)
            rag_context: Additional context from knowledge base
            require_review: If True, content waits for approval before posting
            media_urls: URLs to media files to include
            scheduled_time: ISO 8601 timestamp for scheduling
            
        Returns:
            ContentWorkflow with complete results
        """
        start_time = datetime.now()
        
        # Use niche-specific defaults
        if not platforms and self.client_profile:
            platforms = self.client_profile.platforms
        elif not platforms:
            platforms = ["instagram", "facebook"]
        
        if not content_type:
            content_type = "post"  # default
        
        if not topic and self.client_profile and self.client_profile.content_pillars:
            # Use first content pillar as default topic
            pillars = self.client_profile.content_pillars if isinstance(self.client_profile.content_pillars, list) else [self.client_profile.content_pillars]
            topic = pillars[0] if pillars else "general content"
        elif not topic:
            topic = "general content"
        
        if not client_voice and self.client_profile:
            client_voice = self.client_profile.tone
        
        logger.info(f"Starting workflow - Platforms: {platforms}, Topic: {topic}, Goal: {goal}")
        
        # Create workflow
        workflow = ContentWorkflow(
            workflow_id=self._generate_workflow_id(),
            client_id=self.client_id,
            platforms=platforms,
            content_type=content_type,
            topic=topic,
            goal=goal,
            client_voice=client_voice,
            rag_context=rag_context,
            require_review=require_review,
            media_urls=media_urls,
            scheduled_time=scheduled_time
        )
        
        self.workflows[workflow.workflow_id] = workflow
        
        print(f"\n{'='*80}")
        print(f"🎬 CONTENT WORKFLOW: {workflow.workflow_id}")
        print(f"{'='*80}")
        print(f"Client: {self.client_id}")
        print(f"Platforms: {', '.join(platforms)}")
        print(f"Content Type: {content_type}")
        print(f"Topic: {topic}")
        print(f"Goal: {goal}")
        print(f"Review Required: {require_review}")
        print(f"{'='*80}\n")
        
        # Step 1: Generate content for each platform
        workflow.status = WorkflowStatus.GENERATING.value
        logger.info(f"[{workflow.workflow_id}] Generating content for {len(platforms)} platforms")
        
        try:
            generated_content = await self._generate_content_for_platforms(workflow)
            workflow.generated_content = generated_content
            
            if not generated_content:
                error_msg = "Content generation failed - no content produced"
                workflow.status = WorkflowStatus.FAILED.value
                workflow.error_log.append(error_msg)
                logger.error(f"[{workflow.workflow_id}] {error_msg}")
                print("❌ Content generation failed!")
                return workflow
            
            logger.info(f"[{workflow.workflow_id}] Successfully generated {len(generated_content)} pieces of content")
        except Exception as e:
            error_msg = f"Content generation exception: {str(e)}"
            workflow.status = WorkflowStatus.FAILED.value
            workflow.error_log.append(error_msg)
            logger.error(f"[{workflow.workflow_id}] {error_msg}", exc_info=True)
            print(f"❌ Content generation error: {e}")
            return workflow
        
        # Step 2: Review (if required)
        if require_review:
            workflow.status = WorkflowStatus.PENDING_REVIEW.value
            logger.info(f"[{workflow.workflow_id}] Workflow pending review")
            print(f"\n⏸️  Content ready for review. Call approve_workflow('{workflow.workflow_id}') to continue.\n")
            return workflow
        
        # Step 3: Auto-approve and post
        logger.info(f"[{workflow.workflow_id}] Auto-approving and posting")
        workflow = await self.approve_and_post_workflow(workflow.workflow_id)
        
        # Calculate duration
        end_time = datetime.now()
        workflow.duration_seconds = (end_time - start_time).total_seconds()
        logger.info(f"[{workflow.workflow_id}] Workflow completed in {workflow.duration_seconds:.2f}s")
        
        return workflow
    
    def _map_content_type(self, platform: str, content_type: str) -> str:
        """Map generic content types to platform-specific ones."""
        platform = platform.lower()
        content_type = content_type.lower()
        
        # Platform-specific content type mappings
        mappings = {
            'tiktok': {
                'post': 'caption',  # TikTok uses "caption" not "post"
                'video': 'script',
            },
            'youtube': {
                'post': 'description',
                'video': 'script',
            },
            'pinterest': {
                'post': 'pin',
            },
        }
        
        if platform in mappings and content_type in mappings[platform]:
            return mappings[platform][content_type]
        return content_type
    
    async def _generate_content_for_platforms(self, workflow: ContentWorkflow) -> List[GeneratedContent]:
        """Generate content for all platforms in the workflow with error handling."""
        print(f"🤖 Generating content for {len(workflow.platforms)} platform(s)...\n")
        logger.info(f"[{workflow.workflow_id}] Starting content generation for platforms: {workflow.platforms}")
        
        generated_content = []
        errors = []
        
        for platform in workflow.platforms:
            try:
                # Map content type to platform-specific type
                mapped_content_type = self._map_content_type(platform, workflow.content_type)
                print(f"📝 Generating {platform} {mapped_content_type}...")
                logger.info(f"[{workflow.workflow_id}] Generating {platform} {mapped_content_type}")
                
                # Create content request
                request = ContentRequest(
                    content_type=mapped_content_type,
                    platform=platform,
                    topic=workflow.topic,
                    context=workflow.rag_context,
                    tone=workflow.client_voice,
                    include_hashtags=platform in ["instagram", "tiktok", "twitter"],
                    include_cta=True
                )
                
                # Generate content
                content_list = [await self.content_agent.generate_content(request, use_rag=True)]
                generated_content.extend(content_list)
                
                for content in content_list:
                    print(f"✅ Generated {platform} content ({len(content.content)} chars)")
                    print(f"   Preview: {content.content[:100]}...\n")
                    logger.info(f"[{workflow.workflow_id}] Successfully generated {platform} content")
            
            except Exception as e:
                error_msg = f"Failed to generate {platform} content: {str(e)}"
                print(f"❌ {error_msg}\n")
                errors.append(error_msg)
                workflow.error_log.append(error_msg)
                logger.error(f"[{workflow.workflow_id}] {error_msg}", exc_info=True)
        
        if errors:
            logger.warning(f"[{workflow.workflow_id}] Generation completed with {len(errors)} error(s)")
        
        return generated_content
    
    async def approve_and_post_workflow(self, workflow_id: str) -> ContentWorkflow:
        """
        Approve workflow and post content to all platforms.
        
        Args:
            workflow_id: The workflow ID to approve and post
            
        Returns:
            Updated ContentWorkflow with posting results
        """
        workflow = self.workflows.get(workflow_id)
        
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if not workflow.generated_content:
            raise ValueError(f"Workflow {workflow_id} has no generated content")
        
        print(f"\n{'='*80}")
        print(f"✅ APPROVING & POSTING: {workflow_id}")
        print(f"{'='*80}\n")
        
        workflow.status = WorkflowStatus.POSTING.value
        
        # Create post objects for each platform
        posts_to_publish = []
        
        for content in workflow.generated_content:
            # Auto-generate image for Instagram if no media provided
            media_urls = workflow.media_urls
            if content.platform.lower() == "instagram" and not media_urls:
                print(f"📸 Generating image for Instagram post...")
                image_path = f"temp/instagram_{workflow.workflow_id}_{content.platform}.jpg"
                try:
                    generate_image(content.content, image_path)
                    # Convert local path to file:// URL for posting agent
                    media_urls = [os.path.abspath(image_path)]
                    print(f"✅ Image generated: {image_path}")
                except Exception as e:
                    print(f"❌ Image generation failed: {e}")
                    media_urls = None
            
            post = ContentPost(
                content=content.content,
                platform=content.platform,
                content_type=workflow.content_type,
                client_id=self.client_id,
                media_urls=media_urls,
                scheduled_time=workflow.scheduled_time
            )
            posts_to_publish.append(post)
        
        # Post to all platforms
        posting_results = await self.posting_agent.post_to_multiple_platforms(posts_to_publish)
        workflow.posting_results = posting_results
        
        # Update workflow status
        all_successful = all(r.success for r in posting_results)
        any_manual = any(r.status == "manual_required" for r in posting_results)
        
        if all_successful:
            workflow.status = WorkflowStatus.COMPLETED.value
        elif any_manual:
            workflow.status = "completed_with_manual_queue"
        else:
            workflow.status = WorkflowStatus.FAILED.value
        
        workflow.completed_at = datetime.now().isoformat()
        
        print(f"\n{'='*80}")
        print(f"🏁 WORKFLOW COMPLETE: {workflow.status}")
        print(f"{'='*80}\n")
        
        return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[ContentWorkflow]:
        """Get workflow by ID."""
        return self.workflows.get(workflow_id)
    
    def get_all_workflows(self) -> List[ContentWorkflow]:
        """Get all workflows for this client."""
        return list(self.workflows.values())
    
    def get_pending_reviews(self) -> List[ContentWorkflow]:
        """Get all workflows pending review."""
        return [w for w in self.workflows.values() if w.status == WorkflowStatus.PENDING_REVIEW.value]
    
    def get_manual_queue(self) -> List[Dict]:
        """Get all items in manual posting queue."""
        return self.posting_agent.get_manual_queue()
    
    def get_workflow_stats(self) -> Dict:
        """
        Get comprehensive statistics about all workflows.
        
        Returns:
            Dictionary with workflow metrics
        """
        if not self.workflows:
            return {
                "total_workflows": 0,
                "completed": 0,
                "failed": 0,
                "pending_review": 0,
                "in_progress": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": 0.0
            }
        
        total = len(self.workflows)
        completed = sum(1 for w in self.workflows.values() if w.status == WorkflowStatus.COMPLETED.value)
        failed = sum(1 for w in self.workflows.values() if w.status == WorkflowStatus.FAILED.value)
        pending = sum(1 for w in self.workflows.values() if w.status == WorkflowStatus.PENDING_REVIEW.value)
        in_progress = sum(1 for w in self.workflows.values() if w.status in [WorkflowStatus.GENERATING.value, WorkflowStatus.POSTING.value])
        
        # Calculate average duration for completed workflows
        completed_with_duration = [w for w in self.workflows.values() if w.duration_seconds is not None]
        avg_duration = sum(w.duration_seconds for w in completed_with_duration) / len(completed_with_duration) if completed_with_duration else 0.0
        
        # Platform breakdown
        platform_counts = {}
        for workflow in self.workflows.values():
            for platform in workflow.platforms:
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        return {
            "total_workflows": total,
            "completed": completed,
            "failed": failed,
            "pending_review": pending,
            "in_progress": in_progress,
            "success_rate": (completed / total * 100) if total > 0 else 0.0,
            "avg_duration_seconds": avg_duration,
            "platform_breakdown": platform_counts
        }
    
    def export_workflow_log(self, workflow_id: str, filepath: Optional[str] = None) -> str:
        """
        Export a workflow's complete log to JSON file.
        
        Args:
            workflow_id: Workflow to export
            filepath: Optional custom filepath (defaults to logs/workflow_{id}.json)
            
        Returns:
            Path to exported file
        """
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if not filepath:
            filepath = f"logs/workflow_{workflow_id}.json"
        
        # Convert workflow to dict
        workflow_data = {
            "workflow_id": workflow.workflow_id,
            "client_id": workflow.client_id,
            "platforms": workflow.platforms,
            "content_type": workflow.content_type,
            "topic": workflow.topic,
            "goal": workflow.goal,
            "status": workflow.status,
            "created_at": workflow.created_at,
            "completed_at": workflow.completed_at,
            "duration_seconds": workflow.duration_seconds,
            "error_log": workflow.error_log,
            "generated_content": [
                {
                    "platform": c.platform,
                    "content": c.content,
                    "word_count": c.word_count,
                    "char_count": c.char_count
                } for c in workflow.generated_content
            ] if workflow.generated_content else [],
            "posting_results": [
                {
                    "platform": r.platform,
                    "success": r.success,
                    "status": r.status,
                    "post_id": r.post_id,
                    "error": r.error
                } for r in workflow.posting_results
            ] if workflow.posting_results else []
        }
        
        # Write to file
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(workflow_data, f, indent=2)
        
        logger.info(f"Exported workflow {workflow_id} to {filepath}")
        return filepath


# Example usage and testing
async def example_workflow():
    """Example of complete content generation and posting workflow."""
    
    # Initialize orchestrator
    orchestrator = ContentOrchestrator(client_id="demo_client")
    
    print("\n" + "="*80)
    print("EXAMPLE 1: Generate and post immediately (no review)")
    print("="*80)
    
    # Example 1: Auto-post to Twitter and LinkedIn
    workflow1 = await orchestrator.create_and_post_content(
        platforms=["twitter", "linkedin"],
        content_type="post",
        topic="5 ways AI is transforming small business operations",
        goal="views_engagement",
        client_voice="Professional but friendly. Use data and examples. Keep it actionable.",
        rag_context="AI tools are helping small businesses automate tasks, reduce costs, and scale faster. Key areas: customer service automation, content creation, data analysis, inventory management, and marketing automation.",
        require_review=False  # Post immediately
    )
    
    print("\n" + "="*80)
    print("EXAMPLE 2: Generate with review required")
    print("="*80)
    
    # Example 2: Generate content but wait for approval
    workflow2 = await orchestrator.create_and_post_content(
        platforms=["instagram", "tiktok"],
        content_type="reel",
        topic="Quick AI automation tip for entrepreneurs",
        goal="follower_growth",
        client_voice="Energetic, casual, use emojis. Keep it short and punchy.",
        rag_context="Use ChatGPT to draft email responses in 30 seconds instead of 10 minutes.",
        require_review=True,  # Wait for approval
        media_urls=["https://example.com/video-123.mp4"]
    )
    
    # Show generated content for review
    print("\n📋 CONTENT READY FOR REVIEW:")
    for content in workflow2.generated_content:
        print(f"\n{content.platform.upper()}:")
        print(f"{content.content}\n")
    
    # Simulate approval
    print("✅ Approving workflow...\n")
    workflow2 = await orchestrator.approve_and_post_workflow(workflow2.workflow_id)
    
    # Check manual queue
    manual_queue = orchestrator.get_manual_queue()
    if manual_queue:
        print(f"\n📋 MANUAL POSTING QUEUE ({len(manual_queue)} items):")
        for item in manual_queue:
            print(f"   • {item['platform'].upper()} {item['content_type']}")
            print(f"     Content: {item['content'][:60]}...")
            print(f"     Queued: {item['queued_at']}\n")
    
    # Show all workflows
    all_workflows = orchestrator.get_all_workflows()
    print(f"\n📊 TOTAL WORKFLOWS: {len(all_workflows)}")
    for wf in all_workflows:
        print(f"   • {wf.workflow_id}: {wf.status}")


if __name__ == "__main__":
    asyncio.run(example_workflow())
