"""
CLI tool for generating content across platforms using the prompt library.
Usage: python generate_content.py --platform facebook --type post --topic "AI for business" --goal follower_growth
"""

import asyncio
import argparse
import sys
from content_orchestrator import ContentOrchestrator


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate social media content using the prompt library',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate a Facebook growth post
  python generate_content.py --platform facebook --type post --topic "AI for business growth" --goal follower_growth
  
  # Generate an Instagram awareness story
  python generate_content.py --platform instagram --type story --topic "Behind the scenes" --goal brand_awareness
  
  # Generate a TikTok video script with custom voice
  python generate_content.py --platform tiktok --type video --topic "Quick tips" --goal engagement --voice "Fun, energetic, Gen-Z friendly"
  
  # Generate for multiple platforms
  python generate_content.py --platform facebook instagram --type post --topic "Product launch" --goal conversion
        """
    )
    
    parser.add_argument(
        '--platform', '-p',
        nargs='+',
        required=True,
        choices=['facebook', 'instagram', 'tiktok', 'twitter', 'linkedin', 'youtube'],
        help='Target platform(s) for content generation'
    )
    
    parser.add_argument(
        '--type', '-t',
        required=True,
        choices=['post', 'story', 'reel', 'video', 'carousel', 'ad'],
        help='Type of content to generate'
    )
    
    parser.add_argument(
        '--topic',
        required=True,
        help='Topic or subject for the content'
    )
    
    parser.add_argument(
        '--goal', '-g',
        required=True,
        choices=['engagement', 'follower_growth', 'brand_awareness', 'conversion', 'traffic'],
        help='Marketing goal for the content'
    )
    
    parser.add_argument(
        '--voice', '-v',
        default='Professional, friendly, authentic',
        help='Brand voice/tone for the content (default: "Professional, friendly, authentic")'
    )
    
    parser.add_argument(
        '--client',
        default='default_client',
        help='Client ID for tracking (default: "default_client")'
    )
    
    parser.add_argument(
        '--auto-post',
        action='store_true',
        help='Automatically post without review (use with caution!)'
    )
    
    parser.add_argument(
        '--no-review',
        action='store_true',
        help='Skip review step (same as --auto-post)'
    )
    
    return parser.parse_args()


async def main():
    """Main execution function."""
    args = parse_arguments()
    
    # Map CLI goal names to template goal names
    goal_mapping = {
        'engagement': 'views_engagement',
        'follower_growth': 'follower_growth',
        'brand_awareness': 'follower_growth',  # Maps to growth-focused templates
        'conversion': 'conversions_sales',
        'traffic': 'conversions_sales',
    }
    template_goal = goal_mapping.get(args.goal, 'views_engagement')
    
    # Determine if review is required
    require_review = not (args.auto_post or args.no_review)
    
    print("\n" + "="*80)
    print("CONTENT GENERATION REQUEST")
    print("="*80)
    print(f"Platform(s): {', '.join(args.platform)}")
    print(f"Content Type: {args.type}")
    print(f"Topic: {args.topic}")
    print(f"Goal: {args.goal}")
    print(f"Voice: {args.voice}")
    print(f"Review Required: {'Yes' if require_review else 'No'}")
    print("="*80 + "\n")
    
    # Initialize orchestrator
    orchestrator = ContentOrchestrator(client_id=args.client)
    
    # Generate content
    print("🔄 Generating content using prompt library...\n")
    
    try:
        workflow = await orchestrator.create_and_post_content(
            platforms=args.platform,
            content_type=args.type,
            topic=args.topic,
            goal=template_goal,
            client_voice=args.voice,
            require_review=require_review
        )
        
        # Display generated content
        print("\n" + "="*80)
        print("✅ GENERATED CONTENT")
        print("="*80)
        
        for i, content in enumerate(workflow.generated_content, 1):
            print(f"\n📱 Platform: {content.platform.upper()}")
            print("-"*80)
            print(content.content)
            print("-"*80)
        
        # Handle review/posting
        if require_review:
            print("\n" + "="*80)
            print("REVIEW & APPROVAL")
            print("="*80)
            print("\nPlease review the content above.")
            
            # === SCENE 3 SCREENCAST: HUMAN APPROVAL REQUIREMENT START ===
            response = input("\nDo you want to post this content? (yes/no): ").strip().lower()
            # === SCENE 3 SCREENCAST: HUMAN APPROVAL REQUIREMENT END ===
            
            if response in ['yes', 'y']:
                print("\n🚀 Posting content...\n")
                workflow = await orchestrator.approve_and_post_workflow(workflow.workflow_id)
                print(f"✅ Content posted successfully! Workflow status: {workflow.status}")
            else:
                print("\n❌ Content not posted. Workflow saved for later review.")
                print(f"Workflow ID: {workflow.workflow_id}")
        else:
            print("\n✅ Content generated and posted automatically (review was disabled)")
            print(f"Workflow status: {workflow.status}")
        
        print("\n" + "="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error generating content: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
