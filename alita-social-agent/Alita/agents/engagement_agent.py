# agents/engagement_agent.py
import os
import sys
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv
from agents.rag_system import RAGSystem
from agents.voice_matching_system import VoiceMatchingSystem
from utils.file_reader import load_texts_from_folder
from utils.guardrails import validate_message
from conversation_memory import conversation_memory

load_dotenv()

class EngagementAgent:
    def __init__(self, client_id: str = "demo_client", use_voice_matching: bool = True):
        self.claude_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.rag = RAGSystem()
        self.client_id = client_id
        
        # Initialize Voice Matching System
        self.use_voice_matching = use_voice_matching
        if use_voice_matching:
            self.voice_system = VoiceMatchingSystem()
            self.style_context = self._load_voice_profile(client_id)
        else:
            self.voice_system = None
            self.style_context = self._load_style_references(client_id)

        # Load tone/style preferences (humor, conversation mode, platform adjustments)
        self.tone_prefs = self._load_tone_prefs(client_id)
        
        # Load Claude model configuration from central ai_config
        from utils.ai_config import CLAUDE_HAIKU, CLAUDE_SONNET
        self.haiku_model = CLAUDE_HAIKU
        self.sonnet_model = CLAUDE_SONNET
        self.default_model = os.getenv("CLAUDE_DEFAULT_MODEL", "haiku")
        self._tier = "pro"  # default; callers may override via set_tier()
        
        print("✅ Engagement Agent ready")
        print(f"🤖 Default model: {self.haiku_model if self.default_model == 'haiku' else self.sonnet_model}")
        if self.style_context:
            print(f"🎨 Voice matching enabled for {client_id}")
    
    def set_tier(self, tier: str):
        """Set plan tier for model selection (called by route handlers)."""
        self._tier = tier or "pro"

    def _select_model(self, message: str, context: str) -> str:
        """
        Select Claude model based on plan tier and message complexity.

        Tier-based rules (via ai_config):
        - Free / Starter: always Haiku for engagement (simple task)
        - Growth / Pro: may use Sonnet for complex scenarios
        """
        from utils.ai_config import get_text_model

        # Engagement replies are fundamentally "simple" tasks
        # but very complex messages may deserve a "complex" call
        complexity = "simple"

        if self.default_model == "sonnet":
            complexity = "complex"
        else:
            word_count = len(message.split())
            context_tokens = len(context.split()) * 1.3

            complexity_keywords = [
                "explain", "how does", "why", "compare", "difference",
                "detailed", "technical", "complicated", "complex"
            ]
            if word_count > 100 or context_tokens > 500:
                complexity = "complex"
            elif any(kw in message.lower() for kw in complexity_keywords):
                complexity = "complex"

        model = get_text_model(self._tier, complexity)
        print(f"{'📊' if complexity == 'complex' else '⚡'} Using {model} (tier={self._tier})")
        return model
    
    # === SCENE 3: START (Voice Profile Loading) ===
    def _load_voice_profile(self, client_id: str) -> str:
        """Load voice profile from Voice Matching System."""
        if not self.voice_system:
            return ""
        
        try:
            # Get formatted style context for prompts
            style_context = self.voice_system.get_style_context_for_prompt(client_id)
            if style_context:
                print(f"✅ Loaded voice profile for {client_id}")
                return style_context
        except Exception as e:
            print(f"⚠️ Could not load voice profile: {e}")
        
        # Fallback to file-based style references
        return self._load_style_references(client_id)
    
    def _load_style_references(self, client_id: str) -> str:
        """Load style reference files for voice/tone matching (fallback method)."""
        # Try client-specific folder first
        client_folder = Path("style_references") / client_id
        if client_folder.exists():
            style_text = load_texts_from_folder(str(client_folder))
            if style_text:
                return style_text
        
        # Fallback to root style_references folder
        root_folder = Path("style_references")
        if root_folder.exists():
            style_text = load_texts_from_folder(str(root_folder))
            if style_text:
                return style_text
        
        # No style files found
        return ""
    # === SCENE 3: END (Voice Profile Loading) ===

    def _load_tone_prefs(self, client_id: str) -> dict:
        """Load saved tone/style preferences — DB first, file fallback."""
        import json as _json
        # 1. Try PostgreSQL (survives Railway redeploys)
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            _db = SessionLocal()
            try:
                _prof = _db.query(_CP).filter(_CP.client_id == client_id).first()
                if _prof and getattr(_prof, "tone_preferences_json", None):
                    return _json.loads(_prof.tone_preferences_json)
            finally:
                _db.close()
        except Exception:
            pass
        # 2. File fallback
        path = os.path.join("style_references", client_id, "tone_prefs.json")
        if os.path.exists(path):
            try:
                with open(path) as _f:
                    return _json.load(_f)
            except Exception:
                pass
        return {}

    def respond_to_message(self, message: str, client_id: str, sender_id: str = "unknown",
                          thread_id: str = None, use_memory: bool = True,
                          cross_channel_context: str = "",
                          channel: str = "dm", platform: str = "instagram") -> str:
        """
        Generate a response to a message with optional conversation memory.

        Args:
            message: The user's message
            client_id: Client identifier for RAG lookup
            sender_id: User's platform ID
            thread_id: Conversation thread ID (enables memory if provided)
            use_memory: Whether to use conversation memory (default: True)
            cross_channel_context: Pre-formatted cross-channel history string
                                   from CrossChannelMemory.get_context_for_prompt().
                                   When provided, it is injected into the system
                                   prompt so the agent is aware of the user's full
                                   journey across comments, DMs, etc.
        
        Returns:
            AI-generated response
        """
        print(f"\n💬 Message: '{message}'")
        
        # Run guardrail checks before processing
        is_valid, reason, blocked_response = validate_message(message, sender_id)
        if not is_valid:
            print(f"🛡️ Message blocked by guardrails: {reason}")
            return blocked_response
        
        # Get conversation context if thread_id provided and memory enabled
        conversation_context = ""
        if thread_id and use_memory:
            conversation_context = conversation_memory.format_context_for_prompt(thread_id, max_messages=10)
            if conversation_context != "No previous conversation context available.":
                print(f"🧠 Retrieved conversation memory ({len(conversation_memory.get_conversation_context(thread_id))} messages)")
        
        print("🔍 Searching knowledge...")
        relevant_info = self.rag.search(query=message, client_id=client_id, limit=3)
        
        context = "\n".join([f"- {info['text']}" for info in relevant_info])
        if not context:
            context = "No information found."
        
        print(f"📚 Context: {context}\n")
        print("🤖 Generating response...")
        
        # === SCENE 3: START (Style Injection) ===
        # Build style section if available
        style_section = ""
        if self.style_context:
            # If using Voice Matching System, context is already formatted
            if self.use_voice_matching and self.voice_system:
                style_section = self.style_context  # Already formatted by VoiceMatchingSystem
            else:
                # Legacy format for file-based style references
                style_section = f"""
### STYLE & TONE INSTRUCTIONS
Analyze the following examples of past writing. You must mimic this tone, sentence length, and vocabulary exactly.

--- BEGIN STYLE SAMPLES ---
{self.style_context}
--- END STYLE SAMPLES ---
"""
        # === SCENE 3: END (Style Injection) ===

        # ── Channel-specific adjustments ─────────────────────────────────────
        _adj_key  = f"{platform}_{channel}"  # e.g. "instagram_dm"
        _adj_list = self.tone_prefs.get("platform_adjustments", {}).get(_adj_key, [])
        adjustments_section = ""
        if _adj_list:
            _bullets = "\n".join(f"- {a}" for a in _adj_list)
            adjustments_section = f"""
### CHANNEL-SPECIFIC ADJUSTMENTS ({_adj_key.replace('_', ' ').title()})
Apply these behaviour rules for THIS channel only — they take precedence over your defaults:
{_bullets}
"""

        # ── Humor instructions ────────────────────────────────────────────────
        humor_section = ""
        _humor_prefs = self.tone_prefs.get("humor", {})
        if _humor_prefs.get("enabled"):
            try:
                from api.settings_routes import _generate_humor_prompt
                humor_section = _generate_humor_prompt(_humor_prefs)
            except Exception:
                humor_section = (
                    "\n### HUMOR\n"
                    "Be naturally witty when the moment allows. Let genuine personality show. "
                    "Never force jokes — good humor emerges from precise observation and timing.\n"
                )

        # ── Conversation Categorizer — always runs to inform response tone ────
        # Categorizes every incoming message so humor, casual mode, and tone
        # settings all respond to the actual type of conversation.
        casual_section = ""
        category_section = ""
        try:
            from agents.conversation_categorizer import ConversationCategorizer
            _cat = ConversationCategorizer(client_id=client_id)
            _cat_res = _cat.categorize_message(
                message=message,
                context=f"{platform}_{channel}",
                sender_id=sender_id,
                conversation_history=[],
                force_detailed=False,
            )
            _cat_tone = _cat_res.suggested_response_tone
            # Per-category response guidance injected into every system prompt
            _cat_instructions = {
                "SALE":       "The customer has HIGH purchase intent. Be enthusiastic, direct, and "
                              "action-oriented. Lead them toward a clear next step (pricing, sign-up, "
                              "demo). Urgency is appropriate.",
                "LEAD":       "The customer is gathering information. Be informative and inviting. "
                              "Build curiosity and trust. Offer a clear path forward without being pushy.",
                "COMPLAINT":  "The customer is frustrated or unhappy. Lead with genuine empathy and "
                              "validation BEFORE offering any solution. Never be defensive.",
                "SUPPORT":    "The customer needs practical help. Be clear, efficient, and solution-focused. "
                              "Step-by-step guidance works well here.",
                "ESCALATION": "⚠️ HIGH PRIORITY — the customer is distressed or very angry. Respond with "
                              "maximum empathy and urgency. A human will follow up — your role is to "
                              "de-escalate and reassure, NOT to solve the issue yourself.",
                "GENERAL":    "This is casual conversation. Be warm, natural, and personable.",
            }
            _instruction = _cat_instructions.get(_cat_res.category, "")
            category_section = (
                f"\n### CONVERSATION TYPE\n"
                f"This message is classified as **{_cat_res.category}** "
                f"(confidence: {_cat_res.confidence:.0%}, tone: {_cat_tone}).\n"
                f"{_instruction}\n"
            )
            # Casual mode only activates for GENERAL category
            if self.tone_prefs.get("casual_conversation") and _cat_res.category == "GENERAL" and _cat_res.confidence > 0.6:
                casual_section = """
### CASUAL CONVERSATION MODE
This message is casual small talk (not a business enquiry). You have permission to:
- Reply naturally and warmly as a friendly person would
- Engage genuinely even if the topic is off-business
- Show personality and curiosity
- Keep it brief and human
IMPORTANT: The instant any sign of a business need, question, or complaint appears, switch back to professional mode.
"""
        except Exception:
            pass
        
        # Build conversation memory section if available
        memory_section = ""
        if conversation_context and conversation_context != "No previous conversation context available.":
            memory_section = f"""
### CONVERSATION HISTORY
You are continuing an ongoing conversation. Use this context to provide relevant, coherent responses.

{conversation_context}
"""

        # Build cross-channel history section if available
        cross_channel_section = ""
        if cross_channel_context and cross_channel_context.strip():
            cross_channel_section = f"""
### CROSS-CHANNEL CONVERSATION JOURNEY
This user has interacted with us across multiple locations (comments, DMs, mentions).
Here is their FULL interaction history so you can maintain continuity and avoid re-asking
questions they've already answered:

{cross_channel_context}

Important: If the user was already asked something or gave information in a comment before
starting this DM, reference it naturally rather than asking again.
"""
            print(f"🔗 Cross-channel context injected ({len(cross_channel_context)} chars)")

        system_prompt = f"""You are an AI Engagement Agent.
{style_section}
{humor_section}
{adjustments_section}
{category_section}
{casual_section}
{cross_channel_section}
{memory_section}
### CONSTRAINTS
- Keep responses under 800 characters maximum (aim for ~400 when possible).
- Do not be robotic - sound natural and conversational.
- Use only standard emojis that work across all platforms (avoid rare Unicode characters).
- If the answer is long, summarize key points or ask if they want more details.
- If you have conversation history, reference it naturally when relevant.

CONTEXT:
{context}

CUSTOMER QUESTION:
{message}

Answer using the context. Be friendly and professional."""
        
        # Intelligently select the best model for this message
        selected_model = self._select_model(message, context)
        
        response = self.claude_client.messages.create(
            model=selected_model,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": system_prompt
            }]
        )
        ai_response = response.content[0].text
        print("✅ Response generated!")
        
        # Clean response to ensure proper encoding (remove problematic Unicode characters)
        ai_response = ai_response.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore').strip()
        
        # Store conversation in memory if thread_id provided and memory enabled
        if thread_id and use_memory:
            # Store user message
            conversation_memory.add_message(
                thread_id=thread_id,
                user_id=sender_id,
                sender="user",
                text=message,
                consent_given=True  # For now, assume consent; add consent flow in production
            )
            # Store agent response
            conversation_memory.add_message(
                thread_id=thread_id,
                user_id=sender_id,
                sender="agent",
                text=ai_response,
                consent_given=True
            )
            print(f"💾 Conversation saved to memory (expires in {conversation_memory.ttl_hours}h)")
        
        return ai_response
    
    async def generate_response(self, text: str, sender_id: str = "unknown") -> str:
        """Generate response to text using default client."""
        # Use default client_id for demo purposes
        return self.respond_to_message(message=text, client_id="demo_client", sender_id=sender_id)
    
    # === NEW METHODS: Multi-Client Engagement Handlers ===
    
    async def handle_comment(self, comment_data: dict, client_id: str = None, platform: str = "instagram") -> dict:
        """
        Handle social media comment with AI-powered response.
        
        Args:
            comment_data: Comment data from webhook
                - text: Comment text
                - id: Comment ID
                - post_id: Parent post ID (optional)
                - sender_id: Commenter's ID (optional)
            client_id: Client identifier for voice/RAG matching
            platform: Platform name (instagram, facebook, tiktok, etc.)
        
        Returns:
            dict: {"success": bool, "response": str, "comment_id": str}
        """
        import asyncio
        import random
        
        try:
            comment_text = comment_data.get("text", "")
            comment_id = comment_data.get("id", "")
            sender_id = comment_data.get("sender_id", "unknown")
            
            if not comment_text or not comment_id:
                return {"success": False, "error": "Missing comment text or ID"}
            
            # Use instance client_id if not provided
            if not client_id:
                client_id = self.client_id
            
            print(f"\n💬 [{platform.upper()}] Processing comment from {sender_id}")
            print(f"   Comment: '{comment_text}'")
            print(f"   ID: {comment_id}")
            
            # Add human-like delay (30-90 seconds) to avoid bot detection
            delay = random.randint(30, 90)
            print(f"⏳ Waiting {delay}s before replying (human-like delay)...")
            await asyncio.sleep(delay)
            
            # Generate AI response with voice matching and RAG
            response = self.respond_to_message(
                message=comment_text,
                client_id=client_id,
                sender_id=sender_id,
                thread_id=f"{platform}_comment_{comment_id}",  # Enable conversation memory
                use_memory=True,
                channel="comment",
                platform=platform,
            )
            
            print(f"🤖 AI Response: {response}")
            
            return {
                "success": True,
                "response": response,
                "comment_id": comment_id,
                "platform": platform,
                "delay_seconds": delay
            }
            
        except Exception as e:
            print(f"❌ Error handling {platform} comment: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_dm(self, dm_data: dict, client_id: str = None, platform: str = "instagram") -> dict:
        """
        Handle direct message with AI-powered response.
        
        Args:
            dm_data: DM data from webhook
                - text: Message text
                - sender_id: Sender's platform ID
                - message_id: Platform message ID (for idempotency)
                - attachments: List of attachment objects (optional)
            client_id: Client identifier for voice/RAG matching
            platform: Platform name (instagram, facebook, linkedin, etc.)
        
        Returns:
            dict: {"success": bool, "response": str, "sender_id": str}
        """
        import asyncio
        import random
        
        try:
            message_text = dm_data.get("text", "")
            sender_id = dm_data.get("sender_id", "")
            message_id = dm_data.get("message_id", "")
            attachments = dm_data.get("attachments", [])
            
            if not sender_id:
                return {"success": False, "error": "Missing sender_id"}
            
            # Use instance client_id if not provided
            if not client_id:
                client_id = self.client_id
            
            print(f"\n📩 [{platform.upper()}] Processing DM from {sender_id}")
            print(f"   Message: '{message_text or '[attachment only]'}'")
            print(f"   ID: {message_id}")
            
            # Handle story mentions/attachments (no text)
            if (not message_text or message_text.strip() == "") and attachments:
                print(f"📸 Story mention/attachment detected")
                delay = random.randint(30, 60)
                print(f"⏳ Waiting {delay}s before replying to story mention...")
                await asyncio.sleep(delay)
                
                response = "Thanks for the mention! 🔥 We'll check it out."
                
                return {
                    "success": True,
                    "response": response,
                    "sender_id": sender_id,
                    "platform": platform,
                    "type": "story_mention",
                    "delay_seconds": delay
                }
            
            # Handle normal text DMs
            if not message_text:
                return {"success": False, "error": "No text content to process"}
            
            # Add human-like delay (30-90 seconds) to avoid bot detection
            delay = random.randint(30, 90)
            print(f"⏳ Waiting {delay}s before replying to DM...")
            await asyncio.sleep(delay)
            
            # Generate AI response with voice matching, RAG, and conversation memory
            response = self.respond_to_message(
                message=message_text,
                client_id=client_id,
                sender_id=sender_id,
                thread_id=f"{platform}_dm_{sender_id}",  # Persistent conversation per user
                use_memory=True,
                channel="dm",
                platform=platform,
            )
            
            print(f"🤖 AI DM Response: {response}")
            
            return {
                "success": True,
                "response": response,
                "sender_id": sender_id,
                "platform": platform,
                "type": "dm",
                "delay_seconds": delay
            }
            
        except Exception as e:
            print(f"❌ Error handling {platform} DM: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_story_mention(self, mention_data: dict, client_id: str = None, platform: str = "instagram") -> dict:
        """
        Handle story mention with AI-powered response.
        
        Args:
            mention_data: Story mention data from webhook
                - sender_id: User who mentioned the account
                - story_id: Story ID (optional)
                - media_url: Media URL (optional)
            client_id: Client identifier for voice/RAG matching
            platform: Platform name (instagram, facebook, snapchat, etc.)
        
        Returns:
            dict: {"success": bool, "response": str, "sender_id": str}
        """
        import asyncio
        import random
        
        try:
            sender_id = mention_data.get("sender_id", "")
            story_id = mention_data.get("story_id", "")
            
            if not sender_id:
                return {"success": False, "error": "Missing sender_id"}
            
            # Use instance client_id if not provided
            if not client_id:
                client_id = self.client_id
            
            print(f"\n📸 [{platform.upper()}] Processing story mention from {sender_id}")
            print(f"   Story ID: {story_id}")
            
            # Add human-like delay (30-60 seconds)
            delay = random.randint(30, 60)
            print(f"⏳ Waiting {delay}s before responding to story mention...")
            await asyncio.sleep(delay)
            
            # Generate contextual response
            response = "Thanks for the mention! 🔥 We'll check it out."
            
            # Could enhance this with RAG lookup for more context-aware responses
            # For now, keep it simple and friendly
            
            print(f"🤖 Story Mention Response: {response}")
            
            return {
                "success": True,
                "response": response,
                "sender_id": sender_id,
                "platform": platform,
                "type": "story_mention",
                "delay_seconds": delay
            }
            
        except Exception as e:
            print(f"❌ Error handling {platform} story mention: {e}")
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    print("\n🧪 Testing Engagement Agent...\n")
    agent = EngagementAgent()
    
    agent.rag.add_knowledge(
        text="Our cruises start at $999 per person from Miami.",
        client_id="cruise_123"
    )
    
    response = agent.respond_to_message(
        message="How much does a cruise cost?",
        client_id="cruise_123"
    )
    
    print("\n" + "="*50)
    print("RESPONSE:")
    print("="*50)
    print(response)