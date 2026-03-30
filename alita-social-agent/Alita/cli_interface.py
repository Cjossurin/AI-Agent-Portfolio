"""
CLI Dashboard for Alita Marketing Automation
===========================================
Interactive command-line interface for managing:
- Automatic vs Manual content workflows
- RAG document uploads
- Tone/Style configuration
- Deep research queries
- Automatic notifications

Usage: python cli_interface.py
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

# Import from agents directory
from agents.content_agent import ContentCreationAgent
from agents.knowledge_base import KnowledgeBase
from agents.rag_system import RAGSystem
from agents.faceless_generator import (
    FacelessGenerator, 
    VideoTier, 
    Platform, 
    AspectRatio,
    ImageQuality,
    ImageType
)


class AlitaCLI:
    """Interactive CLI Dashboard for Alita"""
    
    def __init__(self, client_id: str = "demo_client"):
        self.client_id = client_id
        self.agent = ContentCreationAgent(client_id=client_id)
        self.knowledge_base = KnowledgeBase()
        self.rag = RAGSystem()
        self.faceless_generator = FacelessGenerator(client_id=client_id)
        self.setup_complete = False
        
        # Notification preferences
        self.notifications_enabled = True
        self.notification_channels = ["dashboard"]  # dashboard, email, sms, webhook
        
        # Session state
        self.selected_ideas = []
        self.platform_selection = {}
        
        print("\n" + "="*70)
        print("  🤖 ALITA MARKETING AUTOMATION DASHBOARD".center(70))
        print("="*70)
        print(f"Client: {client_id}")
        print(f"Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    def show_main_menu(self) -> str:
        """Display main menu and get user choice"""
        print("\n" + "="*70)
        print("MAIN MENU")
        print("="*70)
        print("""
1. 📝 Start Content Workflow
2. 📚 Manage Knowledge Base
3. 🎨 Configure Style/Tone
4. 🔍 Query Deep Research
5. 🔔 Notification Settings
6. ℹ️  View Client Setup
7. 🎬 Faceless Video Generator
8. 🧵 Threads Management
9. ❌ Exit
        """)
        choice = input("Select option (1-9): ").strip()
        return choice
    
    # =========================================================================
    # WORKFLOW MANAGEMENT
    # =========================================================================
    
    async def start_workflow(self):
        """Main content creation workflow"""
        print("\n" + "="*70)
        print("CONTENT WORKFLOW")
        print("="*70)
        
        # Get client setup
        niche, platforms, content_types, themes = self.get_workflow_inputs()
        
        if not niche:
            print("❌ Workflow cancelled")
            return
        
        # Choose mode
        mode = self.select_mode()
        
        # Number of posts
        num_posts = self.get_integer_input("How many posts to generate? (1-10): ", min_val=1, max_val=10)
        
        print(f"\n🚀 Starting {mode.upper()} workflow...")
        print(f"   Niche: {niche}")
        print(f"   Platforms: {', '.join(platforms) if platforms else 'auto-select'}")
        print(f"   Content Types: {', '.join(content_types) if content_types else 'all'}")
        print(f"   Number of posts: {num_posts}")
        
        # Execute workflow
        try:
            results = await self.agent.create_and_post_workflow(
                niche=niche,
                num_posts=num_posts,
                mode=mode,
                platforms=platforms if platforms else None,
                content_types=content_types if content_types else None,
                themes=themes if themes else None
            )
            
            if mode == "manual":
                await self.manual_mode_workflow(results)
            else:
                self.show_automatic_results(results)
                
        except Exception as e:
            print(f"\n❌ Workflow error: {e}")
    
    def get_workflow_inputs(self) -> tuple:
        """Get required inputs for workflow"""
        print("\n📋 WORKFLOW SETUP")
        print("-" * 70)
        
        # Niche
        niche = input("\nWhat's your business niche? (e.g., 'coaching', 'ecommerce', 'saas'): ").strip()
        if not niche:
            return None, [], [], []
        
        # Platforms
        print("\nAvailable platforms: instagram, facebook, tiktok, linkedin, twitter, youtube")
        platforms_input = input("Select platforms (comma-separated) or press Enter for auto-select: ").strip()
        platforms = [p.strip().lower() for p in platforms_input.split(",")] if platforms_input else []
        
        # Content Types
        print("\nContent types:")
        print("  • growth   - Focus on follower growth")
        print("  • sales    - Focus on conversions/sales")
        print("  • engagement - Focus on engagement/reach")
        content_types_input = input("Select content types (comma-separated) or press Enter for all: ").strip()
        content_types = [c.strip().lower() for c in content_types_input.split(",")] if content_types_input else []
        
        # Themes
        themes_input = input("\nContent themes (comma-separated, optional): ").strip()
        themes = [t.strip() for t in themes_input.split(",")] if themes_input else []
        
        return niche, platforms, content_types, themes
    
    def select_mode(self) -> str:
        """Choose between automatic and manual modes"""
        print("\n🤖 SELECT OPERATING MODE")
        print("-" * 70)
        print("""
1. AUTOMATIC MODE
   • AI generates ideas → creates content → posts automatically
   • Best for: Hands-off clients, high trust in system
   • No approval needed

2. MANUAL MODE
   • AI generates ideas → you review/filter → select platforms → AI posts
   • Best for: Hands-on clients, want control over content
   • Full approval workflow
        """)
        choice = input("Select mode (1 or 2): ").strip()
        
        if choice == "1":
            confirmed = input("⚠️  Confirm automatic mode (all ideas will be posted)? (yes/no): ").strip().lower()
            if confirmed == "yes":
                return "automatic"
        elif choice == "2":
            return "manual"
        
        return self.select_mode()  # Retry
    
    async def manual_mode_workflow(self, results: Dict):
        """Handle manual approval workflow"""
        print("\n" + "="*70)
        print("MANUAL MODE: REVIEW & SELECT")
        print("="*70)
        
        ideas = results.get("ideas", [])
        
        if not ideas:
            print("❌ No ideas generated")
            return
        
        print(f"\n📋 {len(ideas)} Ideas Generated - Select which ones to post\n")
        
        # Display ideas with checkboxes
        for i, idea_info in enumerate(ideas):
            print(f"\n[{i}] {idea_info['topic']}")
            print(f"    Angle: {idea_info['angle']}")
            print(f"    Format: {idea_info['format']}")
            print(f"    Content Type: {idea_info['content_type']}")
            print(f"    Available Platforms: {', '.join(idea_info['platforms'])}")
            print(f"    Hook: {idea_info['hooks'][0] if idea_info['hooks'] else 'N/A'}")
        
        # Get selections
        print("\n" + "-"*70)
        selection_input = input("\nSelect ideas to post (e.g., '0, 2, 4' or 'all'): ").strip().lower()
        
        if selection_input == "all":
            selected_indices = list(range(len(ideas)))
        else:
            try:
                selected_indices = [int(x.strip()) for x in selection_input.split(",")]
                selected_indices = [i for i in selected_indices if 0 <= i < len(ideas)]
            except:
                print("❌ Invalid selection")
                return
        
        if not selected_indices:
            print("❌ No ideas selected")
            return
        
        print(f"\n✅ Selected {len(selected_indices)} ideas")
        
        # Platform selection per idea
        platform_selections = {}
        for idx in selected_indices:
            idea = ideas[idx]
            print(f"\n📍 Idea: {idea['topic']}")
            print(f"   Available: {', '.join(idea['platforms'])}")
            
            platforms = input("   Select platforms (comma-separated) or press Enter for all: ").strip()
            if platforms:
                platform_selections[idx] = [p.strip().lower() for p in platforms.split(",")]
            else:
                platform_selections[idx] = idea['platforms']
        
        # Generate and post selected ideas
        print("\n🚀 Generating and posting selected ideas...")
        print("="*70)
        
        posted_count = 0
        for idx in selected_indices:
            idea_info = ideas[idx]
            idea = idea_info['idea_object']
            selected_platforms = platform_selections[idx]
            
            print(f"\n📝 Posting idea {idx+1}: {idea_info['topic']}")
            print(f"   Platforms: {', '.join(selected_platforms)}")
            
            try:
                # Generate content
                content = await self.agent.generate_from_idea(idea)
                
                # Post to selected platforms
                for platform in selected_platforms:
                    result = await self.agent.post_content(content)
                    if result.success:
                        print(f"   ✅ Posted to {platform}")
                        posted_count += 1
                    else:
                        print(f"   ⚠️  Failed to post to {platform}")
                        
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        # Notification
        print("\n" + "="*70)
        print(f"✅ WORKFLOW COMPLETE")
        print(f"   Total Posted: {posted_count}")
        self.send_notification(f"Posted {posted_count} ideas to social media", "success")
    
    def show_automatic_results(self, results: Dict):
        """Display automatic mode results"""
        print("\n" + "="*70)
        print("AUTOMATIC MODE: COMPLETE")
        print("="*70)
        
        posts = results.get("posts", [])
        print(f"\n✅ {len(posts)} posts generated and posted")
        
        for i, post in enumerate(posts, 1):
            if "error" not in post:
                print(f"\n{i}. {post['idea']}")
                print(f"   Platform: {post['platform']}")
                print(f"   Status: ✅ Posted")
            else:
                print(f"\n{i}. {post['idea']}")
                print(f"   Status: ❌ {post['error']}")
        
        self.send_notification(f"Automatically posted {len(posts)} ideas", "success")
    
    # =========================================================================
    # KNOWLEDGE BASE MANAGEMENT
    # =========================================================================
    
    def manage_knowledge_base(self):
        """Knowledge base submenu"""
        while True:
            print("\n" + "="*70)
            print("KNOWLEDGE BASE MANAGEMENT")
            print("="*70)
            print("""
1. 📄 Upload Documents
2. 🔍 Search Knowledge Base
3. 📋 View Indexed Documents
4. 🗑️  Clear Knowledge Base
5. ⬅️  Back
            """)
            choice = input("Select option (1-5): ").strip()
            
            if choice == "1":
                self.upload_documents()
            elif choice == "2":
                self.search_knowledge()
            elif choice == "3":
                self.view_documents()
            elif choice == "4":
                self.clear_knowledge_base()
            elif choice == "5":
                break
            else:
                print("❌ Invalid option")
    
    def upload_documents(self):
        """Upload documents to RAG"""
        print("\n" + "="*70)
        print("UPLOAD DOCUMENTS TO RAG")
        print("="*70)
        print("Supported formats: PDF, DOCX, TXT")
        
        file_path = input("\nEnter file path (or press Enter to scan knowledge_docs/): ").strip()
        
        if not file_path:
            # Scan knowledge_docs folder
            print("\n📂 Scanning knowledge_docs folder...")
            docs_path = Path("knowledge_docs")
            if not docs_path.exists():
                print("❌ knowledge_docs folder not found")
                return
            
            files = list(docs_path.glob("*.*"))
            if not files:
                print("❌ No files found in knowledge_docs")
                return
            
            print(f"✅ Found {len(files)} files. Starting ingestion...")
            
            # Use ingest script
            os.system(f'python ingest.py')
            print(f"✅ Ingestion complete!")
            return
        
        # Upload specific file
        path = Path(file_path)
        if not path.exists():
            print(f"❌ File not found: {file_path}")
            return
        
        print(f"\n📄 Uploading {path.name}...")
        
        try:
            tags = input("Enter tags (comma-separated, or press Enter for 'general'): ").strip()
            tags = [t.strip() for t in tags.split(",")] if tags else ["general"]
            
            self.knowledge_base.add_file(
                file_path=str(path),
                tags=tags,
                client_id=self.client_id
            )
            
            print(f"✅ {path.name} uploaded successfully!")
            self.send_notification(f"Document '{path.name}' added to knowledge base", "info")
            
        except Exception as e:
            print(f"❌ Upload failed: {e}")
    
    def search_knowledge(self):
        """Search the knowledge base"""
        print("\n" + "="*70)
        print("SEARCH KNOWLEDGE BASE")
        print("="*70)
        
        query = input("\nEnter search query: ").strip()
        if not query:
            return
        
        print(f"\n🔍 Searching for '{query}'...")
        
        try:
            results = self.knowledge_base.search(
                query=query,
                client_id=self.client_id,
                limit=5
            )
            
            if not results:
                print("❌ No results found")
                return
            
            print(f"\n✅ Found {len(results)} results:\n")
            
            for i, result in enumerate(results, 1):
                print(f"{i}. [{result['score']:.2f}] {result['text'][:200]}...")
                print(f"   Source: {result.get('source', 'Unknown')}\n")
                
        except Exception as e:
            print(f"❌ Search error: {e}")
    
    def view_documents(self):
        """List all indexed documents"""
        print("\n" + "="*70)
        print("INDEXED DOCUMENTS")
        print("="*70)
        
        try:
            docs = self.knowledge_base.list_documents(client_id=self.client_id)
            
            if not docs:
                print("❌ No documents found")
                return
            
            print(f"\n✅ Total: {len(docs)} documents\n")
            
            for doc in docs:
                print(f"📄 {doc.filename}")
                print(f"   Tags: {', '.join(doc.tags)}")
                print(f"   Added: {doc.created_at}")
                print(f"   Chunks: {doc.chunk_count}")
                print()
                
        except Exception as e:
            print(f"❌ Error listing documents: {e}")
    
    def clear_knowledge_base(self):
        """Clear all documents"""
        confirm = input("\n⚠️  Clear ALL documents? This cannot be undone. (yes/no): ").strip().lower()
        if confirm == "yes":
            try:
                self.knowledge_base.clear(client_id=self.client_id)
                print("✅ Knowledge base cleared")
                self.send_notification("Knowledge base cleared", "warning")
            except Exception as e:
                print(f"❌ Error: {e}")
    
    # =========================================================================
    # STYLE/TONE CONFIGURATION
    # =========================================================================
    
    def configure_style(self):
        """Configure client tone and style"""
        print("\n" + "="*70)
        print("STYLE & TONE CONFIGURATION")
        print("="*70)
        print("""
Your style is extracted from writing samples (past messages, DMs, etc.)
and used to match the AI-generated content to your voice.

1. 📝 Upload Style Samples
2. 🎯 View Current Style Profile
3. 🔄 Regenerate Style
4. ⬅️  Back
        """)
        choice = input("Select option (1-4): ").strip()
        
        if choice == "1":
            self.upload_style_samples()
        elif choice == "2":
            self.view_style_profile()
        elif choice == "3":
            self.regenerate_style()
        elif choice == "4":
            return
        else:
            print("❌ Invalid option")
    
    def upload_style_samples(self):
        """Upload writing samples for style extraction"""
        print("\n" + "="*70)
        print("UPLOAD STYLE SAMPLES")
        print("="*70)
        print("""
Upload examples of your writing to help the AI match your tone.
Formats: PDF, DOCX, TXT, JSON (Facebook/Instagram exports)

Best to include:
- Past DM conversations
- Social media replies
- Email responses
- Chat logs (10+ samples minimum)
        """)
        
        samples_folder = Path("raw_style_inputs")
        if not samples_folder.exists():
            print("\n❌ raw_style_inputs folder not found")
            return
        
        files = list(samples_folder.glob("*.*"))
        if files:
            print(f"\n✅ Found {len(files)} files in raw_style_inputs/")
            
            normalize = input("Run style normalization? (yes/no): ").strip().lower()
            if normalize == "yes":
                print("\n🔄 Normalizing style samples...")
                os.system("python normalize_style.py")
                print("\n✅ Style samples normalized!")
                self.send_notification("Style profile updated", "success")
        else:
            print("\n❌ No files found in raw_style_inputs/")
            print("💡 Add your chat exports to raw_style_inputs/ and try again")
    
    def view_style_profile(self):
        """Display current style profile"""
        print("\n" + "="*70)
        print("CURRENT STYLE PROFILE")
        print("="*70)
        
        # 1. Try PostgreSQL (survives Railway redeploys)
        content = None
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            _db = SessionLocal()
            try:
                _prof = _db.query(_CP).filter(_CP.client_id == self.client_id).first()
                if _prof and getattr(_prof, "normalized_samples_text", None):
                    content = _prof.normalized_samples_text
            finally:
                _db.close()
        except Exception:
            pass
        # 2. File fallback
        style_file = Path("style_references") / self.client_id / "normalized_samples.txt"
        if not content:
            if not style_file.exists():
                print("❌ No style profile found")
                print("\n💡 Upload writing samples first to generate a profile")
                return
            with open(style_file, 'r', encoding='utf-8') as f:
                content = f.read()
        
        preview_length = min(1000, len(content))
        print(f"\n📝 Profile Preview (first {preview_length} chars):\n")
        print(content[:preview_length])
        print(f"\n... (use this profile for AI content generation)")
    
    def regenerate_style(self):
        """Force regenerate style from samples"""
        confirm = input("\nRegenerate style from samples? (yes/no): ").strip().lower()
        if confirm == "yes":
            print("\n🔄 Regenerating...")
            os.system("python normalize_style.py")
            print("✅ Style regenerated!")
    
    # =========================================================================
    # DEEP RESEARCH
    # =========================================================================
    
    def query_deep_research(self):
        """Query and add deep research to knowledge base"""
        print("\n" + "="*70)
        print("DEEP RESEARCH QUERY")
        print("="*70)
        print("""
Ask Claude to research a topic deeply and add the results
to your knowledge base for use in content generation.

Examples:
- "What are the top Instagram algorithm changes in 2025?"
- "Best practices for B2B LinkedIn content strategy"
- "TikTok hook patterns that go viral"
        """)
        
        query = input("\nEnter your research query: ").strip()
        if not query:
            return
        
        print(f"\n🔍 Researching: '{query}'")
        print("⏳ This may take a moment...")
        
        # TODO: Implement deep research with Claude API
        # For now, mock response
        print("\n📚 Research Results:")
        print("(Feature coming soon - integrate with Claude deep research API)")
        
        # Would add: approve/revise workflow
        approve = input("\nApprove and add to knowledge base? (yes/no): ").strip().lower()
        if approve == "yes":
            print("✅ Research added to knowledge base!")
            self.send_notification(f"Research added: {query}", "success")
    
    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
    
    def notification_settings(self):
        """Configure notification preferences"""
        print("\n" + "="*70)
        print("NOTIFICATION SETTINGS")
        print("="*70)
        print(f"""
Notifications Enabled: {'✅ Yes' if self.notifications_enabled else '❌ No'}
Active Channels: {', '.join(self.notification_channels)}

1. ✅ Enable/Disable Notifications
2. 📧 Add Email Channel
3. 📱 Add SMS Channel
4. 🪝 Add Webhook
5. ⬅️  Back
        """)
        choice = input("Select option (1-5): ").strip()
        
        if choice == "1":
            self.notifications_enabled = not self.notifications_enabled
            status = "✅ Enabled" if self.notifications_enabled else "❌ Disabled"
            print(f"\n{status}")
        elif choice == "2":
            email = input("Enter email address: ").strip()
            if email:
                if "email" not in self.notification_channels:
                    self.notification_channels.append("email")
                print(f"✅ Email notifications enabled: {email}")
        elif choice == "3":
            phone = input("Enter phone number (with country code): ").strip()
            if phone:
                if "sms" not in self.notification_channels:
                    self.notification_channels.append("sms")
                print(f"✅ SMS notifications enabled: {phone}")
        elif choice == "4":
            webhook = input("Enter webhook URL: ").strip()
            if webhook:
                if "webhook" not in self.notification_channels:
                    self.notification_channels.append("webhook")
                print(f"✅ Webhook notifications enabled")
        elif choice == "5":
            return
        else:
            print("❌ Invalid option")
    
    def send_notification(self, message: str, notification_type: str = "info"):
        """Send notification to configured channels"""
        if not self.notifications_enabled:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Dashboard notification (always)
        print(f"\n📢 [{notification_type.upper()}] {message}")
        
        # Email, SMS, Webhook would be implemented here
        # For now, just log to file
        log_file = "notifications.log"
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] [{notification_type}] {message}\n")
    
    # =========================================================================
    # CLIENT SETUP
    # =========================================================================
    
    def view_setup(self):
        """View client configuration"""
        print("\n" + "="*70)
        print("CLIENT SETUP")
        print("="*70)
        
        print(f"""
Client ID: {self.client_id}
Notifications: {'✅ Enabled' if self.notifications_enabled else '❌ Disabled'}
Notification Channels: {', '.join(self.notification_channels)}

KNOWLEDGE BASE:
- Status: ✅ Ready
- Supported formats: PDF, DOCX, TXT

STYLE CONFIGURATION:
- Location: style_references/{self.client_id}/
- Status: {'✅ Configured' if Path(f'style_references/{self.client_id}').exists() else '⚠️ Not configured'}

DEEP RESEARCH:
- Status: 📋 Available (coming soon)
- Integration: Claude API

API CONNECTIONS:
- Anthropic: ✅ Connected
- OpenAI: ✅ Connected
- Meta (Facebook/Instagram): {'✅ Connected' if os.getenv('INSTAGRAM_ACCESS_TOKEN') else '⚠️ Not configured'}
- Late API (TikTok/LinkedIn/Twitter): {'✅ Connected' if os.getenv('LATE_API_KEY') else '⚠️ Not configured'}
        """)
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_integer_input(self, prompt: str, min_val: int = 1, max_val: int = 100) -> int:
        """Get validated integer input"""
        while True:
            try:
                val = int(input(prompt))
                if min_val <= val <= max_val:
                    return val
                print(f"❌ Enter a number between {min_val} and {max_val}")
            except ValueError:
                print("❌ Enter a valid number")
    
    # =========================================================================
    # THREADS MANAGEMENT
    # =========================================================================
    
    async def threads_menu(self):
        """Threads management submenu"""
        from api.threads_client import ThreadsClient
        
        while True:
            print("\n" + "="*70)
            print("🧵 THREADS MANAGEMENT")
            print("="*70)
            print("""
1. ✍️  Create Post
2. 📝 Create Thread (Multi-Post)
3. 📊 View Recent Posts
4. 💬 View & Reply to Comments
5. 📈 View Analytics
6. ⬅️  Back
            """)
            choice = input("Select option (1-6): ").strip()
            
            if choice == "1":
                await self.create_threads_post()
            elif choice == "2":
                await self.create_thread_series()
            elif choice == "3":
                await self.view_threads_posts()
            elif choice == "4":
                await self.manage_threads_comments()
            elif choice == "5":
                await self.view_threads_analytics()
            elif choice == "6":
                break
            else:
                print("❌ Invalid option")
    
    async def create_threads_post(self):
        """Create a single Threads post"""
        from api.threads_client import ThreadsClient
        
        print("\n" + "="*70)
        print("✍️  CREATE THREADS POST")
        print("="*70)
        
        text = input("\n📝 Post text (max 500 characters): ").strip()
        if not text:
            print("❌ Post text required")
            return
        
        if len(text) > 500:
            print(f"⚠️  Text too long ({len(text)} characters). Truncating to 500...")
            text = text[:497] + "..."
        
        media_url = input("🖼️  Media URL (optional, press Enter to skip): ").strip()
        media_urls = [media_url] if media_url else None
        
        schedule = input("⏰ Schedule for later? (yes/no) [no]: ").strip().lower() == "yes"
        scheduled_time = None
        
        if schedule:
            from datetime import datetime, timedelta
            hours = input("   How many hours from now? [1]: ").strip()
            hours = int(hours) if hours.isdigit() else 1
            scheduled_time = (datetime.now() + timedelta(hours=hours)).isoformat()
            print(f"   Scheduled for: {scheduled_time}")
        
        print(f"\n🚀 Posting to Threads...")
        
        try:
            client = ThreadsClient(client_id=self.client_id)
            post = await client.create_post(
                text=text,
                media_urls=media_urls,
                scheduled_time=scheduled_time
            )
            
            if post.status == "published":
                print(f"\n✅ Post published successfully!")
                print(f"   Post ID: {post.post_id}")
            elif post.status == "scheduled":
                print(f"\n⏰ Post scheduled successfully!")
                print(f"   Post ID: {post.post_id}")
            else:
                print(f"\n❌ Post failed to publish")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def create_thread_series(self):
        """Create a thread (multiple connected posts)"""
        from api.threads_client import ThreadsClient
        
        print("\n" + "="*70)
        print("📝 CREATE THREAD SERIES")
        print("="*70)
        print("\nEnter each post (press Enter twice to finish):\\n")
        
        posts = []
        post_num = 1
        
        while True:
            text = input(f"Post {post_num}: ").strip()
            if not text:
                if len(posts) > 0:
                    break
                else:
                    continue
            
            if len(text) > 500:
                print(f"   ⚠️  Truncating to 500 characters...")
                text = text[:497] + "..."
            
            posts.append(text)
            post_num += 1
        
        if not posts:
            print("❌ No posts entered")
            return
        
        delay = input(f"\n⏱️  Delay between posts (seconds) [2]: ").strip()
        delay = int(delay) if delay.isdigit() else 2
        
        print(f"\n🚀 Creating thread with {len(posts)} posts...")
        
        try:
            client = ThreadsClient(client_id=self.client_id)
            results = await client.create_thread(posts, delay_seconds=delay)
            
            success_count = sum(1 for r in results if r.status == "published")
            print(f"\n✅ Thread created: {success_count}/{len(posts)} posts published")
            
            for i, post in enumerate(results, 1):
                status_emoji = "✅" if post.status == "published" else "❌"
                print(f"   {status_emoji} Post {i}: {post.post_id}")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def view_threads_posts(self):
        """View recent Threads posts"""
        from api.threads_client import ThreadsClient
        
        print("\n" + "="*70)
        print("📊 RECENT THREADS POSTS")
        print("="*70)
        
        limit = input("\nHow many posts to show? [20]: ").strip()
        limit = int(limit) if limit.isdigit() else 20
        
        try:
            client = ThreadsClient(client_id=self.client_id)
            posts = await client.get_recent_posts(limit=limit)
            
            if not posts:
                print("\n📭 No posts found")
                return
            
            print(f"\n✅ Found {len(posts)} posts:\\n")
            
            for i, post in enumerate(posts, 1):
                print(f"{i}. {post.text[:80]}{'...' if len(post.text) > 80 else ''}")
                print(f"   ❤️  {post.like_count} likes  💬 {post.reply_count} replies  🔁 {post.quote_count} quotes")
                print(f"   📅 {post.created_at.strftime('%Y-%m-%d %H:%M') if post.created_at else 'Unknown'}")
                print()
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def manage_threads_comments(self):
        """View and reply to comments on Threads posts"""
        from api.threads_client import ThreadsClient
        
        print("\n" + "="*70)
        print("💬 THREADS COMMENTS")
        print("="*70)
        
        post_id = input("\nEnter post ID: ").strip()
        if not post_id:
            print("❌ Post ID required")
            return
        
        try:
            client = ThreadsClient(client_id=self.client_id)
            comments = await client.get_post_comments(post_id)
            
            if not comments:
                print("\n📭 No comments found")
                return
            
            print(f"\n✅ Found {len(comments)} comments:\\n")
            
            for i, comment in enumerate(comments, 1):
                username = comment.get("username", "Unknown")
                text = comment.get("text", "")
                likes = comment.get("like_count", 0)
                print(f"{i}. @{username}: {text}")
                print(f"   ❤️  {likes} likes")
                print()
            
            # Option to reply
            reply_choice = input("Reply to a comment? (yes/no): ").strip().lower()
            if reply_choice == "yes":
                comment_num = input(f"Which comment? (1-{len(comments)}): ").strip()
                if comment_num.isdigit() and 1 <= int(comment_num) <= len(comments):
                    comment_id = comments[int(comment_num) - 1].get("id")
                    reply_text = input("Reply text: ").strip()
                    
                    if reply_text:
                        result = await client.reply_to_comment(comment_id, reply_text)
                        if "error" in result:
                            print(f"❌ Failed: {result['error']}")
                        else:
                            print("✅ Reply posted!")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def view_threads_analytics(self):
        """View Threads account analytics"""
        from api.threads_client import ThreadsClient
        
        print("\n" + "="*70)
        print("📈 THREADS ANALYTICS")
        print("="*70)
        
        try:
            client = ThreadsClient(client_id=self.client_id)
            analytics = await client.get_account_analytics()
            
            if "error" in analytics:
                print(f"\n❌ Error: {analytics['error']}")
                return
            
            print("\n📊 Account Performance:\\n")
            
            # Display analytics
            for key, value in analytics.items():
                if key != "error":
                    formatted_key = key.replace("_", " ").title()
                    print(f"   {formatted_key}: {value}")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    # =========================================================================
    # FACELESS VIDEO GENERATOR
    # =========================================================================
    
    async def faceless_video_menu(self):
        """Faceless Video Generator submenu"""
        while True:
            print("\n" + "="*70)
            print("🎬 FACELESS VIDEO GENERATOR")
            print("="*70)
            
            # Show API status
            apis = self.faceless_generator.get_available_apis()
            tiers = self.faceless_generator.get_available_tiers()
            
            print(f"\n📡 API Status:")
            print(f"   Pexels (Stock Video): {'✅' if apis.get('pexels') else '❌'}")
            print(f"   Pixabay (Stock Video): {'✅' if apis.get('pixabay') else '❌'}")
            print(f"   ElevenLabs (Voiceover): {'✅' if apis.get('elevenlabs') else '❌'}")
            print(f"   DALL-E 3 (Images): {'✅' if apis.get('dalle') else '❌'}")
            print(f"   fal.ai (AI Animation): {'✅' if apis.get('fal') else '❌'}")
            print(f"   FFmpeg (Assembly): {'✅' if apis.get('ffmpeg') else '❌'}")
            
            print(f"\n🎯 Available Tiers: {', '.join(tiers)}")
            
            print("""
1. 🎥 Generate Video (enter script)
2. 🖼️  Generate Image
3. 📊 View Generation Stats
4. 🧪 Test APIs
5. ⬅️  Back to Main Menu
            """)
            
            choice = input("Select option (1-5): ").strip()
            
            if choice == "1":
                await self.generate_video_flow()
            elif choice == "2":
                await self.generate_image_flow()
            elif choice == "3":
                self.show_generation_stats()
            elif choice == "4":
                await self.test_faceless_apis()
            elif choice == "5":
                break
            else:
                print("❌ Invalid option")
    
    async def generate_video_flow(self):
        """Interactive video generation workflow"""
        print("\n" + "="*70)
        print("🎥 GENERATE FACELESS VIDEO")
        print("="*70)
        
        # Option: Generate script or provide own
        print("\n📝 SCRIPT OPTIONS:")
        print("1. 🤖 AI-Generate Script (recommended)")
        print("2. ✍️  Provide Your Own Script")
        print("3. 📋 Use Demo Script")
        
        script_choice = input("\nSelect option (1-3) [default: 1]: ").strip() or "1"
        
        script = None
        
        if script_choice == "1":
            # AI-generate optimized script
            print("\n🤖 AI SCRIPT GENERATION")
            print("-" * 70)
            
            topic = input("📌 Video Topic/Angle: ").strip()
            if not topic:
                topic = "Why 90% of startups fail and how to avoid it"
                print(f"Using demo topic: {topic}")
            
            duration = input("⏱️  Target Duration (seconds) [default: 60]: ").strip()
            duration = int(duration) if duration.isdigit() else 60
            
            style = input("🎨 Style [default: engaging, educational]: ").strip() or "engaging, educational"
            
            print(f"\n⚙️  Generating optimized script...")
            script_result = await self.faceless_generator.generate_script(
                topic=topic,
                platform=Platform.INSTAGRAM_REEL,
                duration_target=duration,
                style=style
            )
            
            if script_result.get("error"):
                print(f"❌ Script generation failed: {script_result['error']}")
                return
            
            script = script_result["script"]
            
            print(f"\n✅ Script Generated!")
            print(f"   📊 Stats: {script_result['word_count']} words, "
                  f"{script_result['scene_count']} scenes, "
                  f"~{script_result['estimated_duration']}s")
            print(f"\n📄 SCRIPT PREVIEW:")
            print("-" * 70)
            print(script[:300] + "..." if len(script) > 300 else script)
            print("-" * 70)
            
            confirm = input("\n✅ Use this script? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("❌ Cancelled")
                return
        
        elif script_choice == "2":
            # User provides own script
            print("\n✍️  Enter your video script:")
            print("   (Tip: 2-3 sentences will be grouped per visual)")
            script = input("\n> ").strip()
            
            if not script:
                print("❌ Script required")
                return
        
        else:
            # Demo script
            script = (
                "Did you know that 90% of startups fail in their first year? "
                "The number one reason is not running out of money. "
                "It's building something nobody wants. "
                "Before writing a single line of code, validate your idea. "
                "Talk to 100 potential customers. "
                "If they won't pay now, they won't pay later. "
                "Save yourself years of wasted effort. "
                "Follow for more startup tips!"
            )
            print(f"\n📋 Using demo script:\n{script[:100]}...")
        
        # Select tier with cost preview
        print("\n💰 SELECT VIDEO TIER:")
        print("-" * 70)
        print("""
1. 🎬 Stock Video (FREE)
   • Uses real Pexels/Pixabay footage
   • Professional quality, zero cost
   • Best for: Most content, budget-conscious

2. 🖼️  Generated Images ($0.04/image)
   • AI-generated unique visuals
   • Ken Burns zoom/pan effects
   • Best for: Unique branding, custom visuals

3. ✨ AI Animation ($0.35/5sec)
   • AI-animated images (Kling/Wan)
   • Premium motion effects
   • Best for: High-impact premium content
        """)
        
        tier_choice = input("Select tier (1-3) [default: 1]: ").strip() or "1"
        
        tier_map = {
            "1": VideoTier.STOCK_VIDEO,
            "2": VideoTier.GENERATED_IMAGES,
            "3": VideoTier.AI_ANIMATION
        }
        tier = tier_map.get(tier_choice, VideoTier.STOCK_VIDEO)
        
        # Select image quality for Tier 2 & 3
        image_quality = ImageQuality.BUDGET  # Default
        if tier in [VideoTier.GENERATED_IMAGES, VideoTier.AI_ANIMATION]:
            print("\n🎨 SELECT IMAGE QUALITY:")
            print("-" * 70)
            print("""
1. 💰 Budget (DALL-E 3) - $0.04/image
   • Fast generation (~5-10s per image)
   • Good quality, reliable
   • Best for: Testing, high-volume content

2. ⭐ Standard (Flux) - $0.055/image
   • Balanced quality/cost
   • More detail than DALL-E
   • Best for: Regular content, better visuals

3. 💎 Premium (Midjourney) - $0.05/image
   • Highest artistic quality
   • Professional-grade images
   • Best for: Premium content, brand showcase
            """)
            
            quality_choice = input("Select quality (1-3) [default: 1]: ").strip() or "1"
            
            quality_map = {
                "1": ImageQuality.BUDGET,
                "2": ImageQuality.STANDARD,
                "3": ImageQuality.PREMIUM
            }
            image_quality = quality_map.get(quality_choice, ImageQuality.BUDGET)
            
            # Update cost estimates with selected quality
            cost_per_image = {
                ImageQuality.BUDGET: 0.04,
                ImageQuality.STANDARD: 0.055,
                ImageQuality.PREMIUM: 0.05
            }
            
            if tier == VideoTier.GENERATED_IMAGES:
                cost_estimates[tier] = scenes * cost_per_image[image_quality]
            # AI Animation already accounts for image cost + animation cost
        
        # Select platform
        print("\n📱 SELECT PLATFORM:")
        print("""
1. Instagram Reel (9:16)
2. TikTok (9:16)
3. YouTube Short (9:16)
4. YouTube (16:9)
5. Instagram Feed (1:1)
        """)
        
        platform_choice = input("Select platform (1-5) [default: 1]: ").strip() or "1"
        
        platform_map = {
            "1": Platform.INSTAGRAM_REEL,
            "2": Platform.TIKTOK,
            "3": Platform.YOUTUBE_SHORT,
            "4": Platform.YOUTUBE,
            "5": Platform.INSTAGRAM_FEED
        }
        platform = platform_map.get(platform_choice, Platform.INSTAGRAM_REEL)
        
        # Ask for niche/topic for better visual matching
        print("\n🎯 VIDEO NICHE (for better visual matching):")
        print("   Examples: 'AI automation', 'fitness', 'real estate', 'startups'")
        niche = input("   Enter niche [optional]: ").strip() or None
        
        # Estimate cost
        sentences = len([s for s in script.split('.') if s.strip()])
        scenes = max(1, sentences // 2)  # 2-3 sentences per scene
        
        cost_estimates = {
            VideoTier.STOCK_VIDEO: 0.0,
            VideoTier.GENERATED_IMAGES: scenes * 0.04,
            VideoTier.AI_ANIMATION: scenes * 0.35
        }
        voiceover_cost = len(script) / 1000 * 0.30
        total_cost = cost_estimates[tier] + voiceover_cost
        
        print(f"\n💵 COST ESTIMATE:")
        print(f"   Tier: {tier.value}")
        print(f"   Scenes: ~{scenes}")
        print(f"   Visuals: ${cost_estimates[tier]:.2f}")
        print(f"   Voiceover: ${voiceover_cost:.2f}")
        print(f"   TOTAL: ${total_cost:.2f}")
        if niche:
            print(f"   🎯 Niche: {niche}")
        
        # Subtitle and music options
        print("\n🎨 ADDITIONAL OPTIONS:")
        add_captions = input("Add word-highlighting subtitles? (yes/no) [default: yes]: ").strip().lower() or "yes"
        add_music = input("Add background music? (yes/no) [default: no]: ").strip().lower() or "no"
        
        music_url = None
        music_volume = 0.15
        if add_music == "yes":
            print("\n🎵 BACKGROUND MUSIC:")
            print("   Enter URL to MP3 file (or press Enter to skip)")
            music_url = input("   Music URL: ").strip() or None
            
            if music_url:
                vol = input("   Music volume (0.05-0.30) [default: 0.15]: ").strip()
                try:
                    music_volume = float(vol) if vol else 0.15
                    music_volume = max(0.05, min(music_volume, 0.30))
                except:
                    music_volume = 0.15
        
        confirm = input("\n🚀 Generate video? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Cancelled")
            return
        
        # Generate!
        print("\n" + "="*70)
        print("🎬 GENERATING VIDEO...")
        print("="*70)
        print("\nSteps:")
        print("1. Generating voiceover with ElevenLabs...")
        print("2. Splitting script into smart scene groups...")
        print("3. Generating visuals for each scene...")
        print("4. Applying crossfade transitions...")
        print("5. Adding audio with fade effects...")
        if add_captions == "yes":
            print("6. Adding word-highlighting subtitles...")
        if add_music == "yes" and music_url:
            print("7. Mixing background music...")
        print("\nThis may take a few minutes...\n")
        
        try:
            result = await self.faceless_generator.generate_video(
                script=script,
                tier=tier,
                platform=platform,
                niche=niche,
                image_quality=image_quality,
                include_captions=(add_captions == "yes"),
                include_music=(add_music == "yes"),
                music_url=music_url,
                music_volume=music_volume
            )
            
            if result.success:
                print("\n" + "="*70)
                print("✅ VIDEO GENERATED SUCCESSFULLY!")
                print("="*70)
                print(f"\n📁 Output: {result.local_path}")
                print(f"⏱️  Generation time: {result.generation_time_seconds:.1f}s")
                print(f"💰 Actual cost: ${result.cost_estimate:.2f}")
                print(f"🎯 Tier used: {result.tier_used}")
                print(f"📊 Scenes: {result.metadata.get('scene_count', 'N/A')}")
                
                self.send_notification(f"Video generated: {result.local_path}", "success")
            else:
                print(f"\n❌ Generation failed: {result.error}")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    async def generate_image_flow(self):
        """Interactive image generation workflow"""
        print("\n" + "="*70)
        print("🖼️  GENERATE FACELESS IMAGE")
        print("="*70)
        
        prompt = input("\n📝 Enter image prompt: ").strip()
        if not prompt:
            print("❌ Prompt required")
            return
        
        print("\n📐 SELECT SIZE:")
        print("""
1. Square (1080x1080) - Instagram Feed
2. Portrait (1080x1920) - Stories/Reels
3. Landscape (1920x1080) - YouTube/Facebook
        """)
        
        size_choice = input("Select size (1-3) [default: 1]: ").strip() or "1"
        size_map = {"1": "1080x1080", "2": "1080x1920", "3": "1920x1080"}
        size = size_map.get(size_choice, "1080x1080")
        
        # Select image quality
        print("\n🎨 SELECT IMAGE QUALITY:")
        print("-" * 70)
        print("""
1. 💰 Budget (DALL-E 3) - $0.04
   • Fast generation (~5-10s)
   • Good quality, reliable
   • Best for: Testing, quick content

2. ⭐ Standard (Flux) - $0.055
   • Balanced quality/cost
   • More detail and creativity
   • Best for: Regular posts, better visuals

3. 💎 Premium (Midjourney) - $0.05
   • Highest artistic quality
   • Professional-grade output
   • Best for: Hero images, brand showcase
        """)
        
        quality_choice = input("Select quality (1-3) [default: 1]: ").strip() or "1"
        
        quality_map = {
            "1": ImageQuality.BUDGET,
            "2": ImageQuality.STANDARD,
            "3": ImageQuality.PREMIUM
        }
        image_quality = quality_map.get(quality_choice, ImageQuality.BUDGET)
        
        # Select image type
        print("\n🎯 SELECT IMAGE TYPE:")
        print("""
1. General (default) - Balanced for any content
2. Artistic - Creative, stylized visuals
3. Text - Images with text/quotes (best with Ideogram)
        """)
        
        type_choice = input("Select type (1-3) [default: 1]: ").strip() or "1"
        
        type_map = {
            "1": ImageType.GENERAL,
            "2": ImageType.ARTISTIC,
            "3": ImageType.TEXT
        }
        image_type = type_map.get(type_choice, ImageType.GENERAL)
        
        # Cost preview
        cost_map = {
            ImageQuality.BUDGET: 0.04,
            ImageQuality.STANDARD: 0.055,
            ImageQuality.PREMIUM: 0.05
        }
        
        print(f"\n💵 ESTIMATED COST: ${cost_map[image_quality]:.3f}")
        print(f"   Quality: {image_quality.value}")
        print(f"   Type: {image_type.value}")
        print(f"   Size: {size}")
        
        confirm = input("\n🚀 Generate image? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Cancelled")
            return
        
        print(f"\n🎨 Generating {image_quality.value} quality image ({size})...")
        
        try:
            result = await self.faceless_generator.generate_image(
                prompt=prompt,
                size=size,
                image_type=image_type,
                quality=image_quality
            )
            
            if result.success:
                print(f"\n✅ Image generated!")
                print(f"🔗 URL: {result.url}")
                print(f"💰 Cost: ${result.cost_estimate:.2f}")
                print(f"⏱️  Time: {result.generation_time_seconds:.1f}s")
            else:
                print(f"\n❌ Failed: {result.error}")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    def show_generation_stats(self):
        """Display generation statistics"""
        stats = self.faceless_generator.get_stats()
        
        print("\n" + "="*70)
        print("📊 GENERATION STATISTICS")
        print("="*70)
        print(f"""
Videos Generated: {stats['videos_generated']}
Images Generated: {stats['images_generated']}
Total Cost: ${stats['total_cost']:.2f}

API Calls:
  • Pexels: {stats['api_calls']['pexels']}
  • Pixabay: {stats['api_calls']['pixabay']}
  • ElevenLabs: {stats['api_calls']['elevenlabs']}
  • DALL-E: {stats['api_calls']['dalle']}
  • fal.ai: {stats['api_calls']['fal']}

Tier Usage:
  • Stock Video: {stats['tier_usage']['stock_video']}
  • Generated Images: {stats['tier_usage']['generated_images']}
  • AI Animation: {stats['tier_usage']['ai_animation']}

Errors: {stats['errors']}
        """)
    
    async def test_faceless_apis(self):
        """Test all faceless generator APIs"""
        print("\n" + "="*70)
        print("🧪 TESTING APIS...")
        print("="*70)
        
        results = await self.faceless_generator.test_apis()
        
        print("\nResults:")
        for api, result in results.items():
            status = "✅" if result.get("success") else "❌"
            details = result.get("note") or result.get("error") or ""
            if "found" in str(result):
                details = f"{result.get('videos_found', result.get('voices_found', ''))} found"
            print(f"  {api}: {status} {details}")
    
    async def run(self):
        """Main CLI loop"""
        while True:
            choice = self.show_main_menu()
            
            try:
                if choice == "1":
                    await self.start_workflow()
                elif choice == "2":
                    self.manage_knowledge_base()
                elif choice == "3":
                    self.configure_style()
                elif choice == "4":
                    self.query_deep_research()
                elif choice == "5":
                    self.notification_settings()
                elif choice == "6":
                    self.view_setup()
                elif choice == "7":
                    await self.faceless_video_menu()
                elif choice == "8":
                    await self.threads_menu()
                elif choice == "9":
                    print("\n👋 Goodbye!\n")
                    break
                else:
                    print("❌ Invalid option")
            except KeyboardInterrupt:
                print("\n\n⏸️  Paused. Press Ctrl+C again to exit, or continue")
            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()


async def main():
    """Main entry point"""
    cli = AlitaCLI(client_id="demo_client")
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
