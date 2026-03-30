"""
Conversation Categorizer Agent - OPTIMIZED VERSION
===================================================
Automatically categorizes incoming messages and comments to help clients
prioritize responses and identify high-value conversations.

Optimization Features:
- Phase 1: Few-shot prompting with real examples per category
- Phase 2: RAG integration for business context awareness
- Phase 3: Multi-stage classification (keyword → quick AI → detailed AI)

Categories:
- SALE: Purchase inquiry, pricing questions, ready to buy
- LEAD: Interested prospect, wants more info, potential customer
- COMPLAINT: Problem with product/service, negative feedback
- SUPPORT: Technical questions, how-to, general help
- GENERAL: Casual conversation, thank you, compliments
- ESCALATION: Urgent issues, angry customer, needs immediate attention

Usage:
    categorizer = ConversationCategorizer(client_id="demo_client")
    result = categorizer.categorize_message(
        message="How much does your coaching program cost?",
        context="Instagram DM",
        sender_id="user_123"
    )
    
    print(result.category)  # "SALE"
    print(result.confidence)  # 0.95
    print(result.priority)  # "high"
"""

import os
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Import Conversation Categorizer prompt system from Agent RAGs folder
# Follows the same importlib.util pattern used by email_support_agent.py
# and email_marketing_agent.py so prompts live in the RAG folder, not here.
# ---------------------------------------------------------------------------
import sys as _sys
from pathlib import Path as _Path
_CATEGORIZER_PROMPT_PATH = (
    _Path(__file__).parent.parent
    / "Agent RAGs"
    / "Conversation Categorizer RAG(CRITICAL)"
    / "conversation_categorizer_prompts.py"
)
try:
    import importlib.util as _importlib_util
    _spec = _importlib_util.spec_from_file_location(
        "conversation_categorizer_prompts", _CATEGORIZER_PROMPT_PATH
    )
    _prompt_module = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_prompt_module)
    _get_prompt = _prompt_module.get_prompt
    _format_prompt = _prompt_module.format_prompt
    _ConversationCategorizerRAG = _prompt_module.ConversationCategorizerRAG
    print("\u2705 Conversation Categorizer prompt system loaded")
except Exception as _prompt_load_err:
    print(f"\u26a0\ufe0f  Failed to load categorizer prompt system: {_prompt_load_err}")
    _get_prompt = None
    _format_prompt = None
    _ConversationCategorizerRAG = None


@dataclass
class CategoryResult:
    """Result of message categorization"""
    category: str  # SALE, LEAD, COMPLAINT, SUPPORT, GENERAL, ESCALATION
    confidence: float  # 0.0 to 1.0
    priority: str  # critical, high, medium, low
    reasoning: str  # Why this category was chosen
    suggested_response_tone: str  # urgent, helpful, friendly, professional, empathetic
    requires_notification: bool  # Should client be notified?
    secondary_category: Optional[str] = None  # If message fits multiple categories
    classification_stage: str = "unknown"  # keyword, quick_ai, detailed_ai
    business_context: Optional[str] = None  # Relevant knowledge from RAG
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class ConversationCategorizer:
    """
    Optimized Conversation Categorizer with:
    - Few-shot learning (Phase 1)
    - RAG integration (Phase 2)  
    - Multi-stage classification (Phase 3)
    """
    
    # =========================================================================
    # CATEGORY DEFINITIONS WITH ENHANCED METADATA
    # =========================================================================
    CATEGORIES = {
        "SALE": {
            "description": "Customer ready to buy, asking about pricing, payment, or wants to place an order",
            "keywords": [
                "price", "cost", "buy", "purchase", "order", "how much", 
                "payment", "checkout", "sign up", "get started", "pricing",
                "pay", "afford", "budget", "investment", "fee", "rate",
                "discount", "deal", "package", "plan"
            ],
            "strong_keywords": ["buy", "purchase", "order", "sign up", "checkout", "pricing"],
            "priority": "high",
            "notify": True,
            "response_urgency": "within 1 hour",
            "typical_intent": "Ready to convert, high purchase intent"
        },
        "LEAD": {
            "description": "Interested prospect gathering information, considering but not yet ready to buy",
            "keywords": [
                "interested", "tell me more", "learn more", "info", "details",
                "schedule", "demo", "call", "how does", "what is", "curious",
                "considering", "thinking about", "want to know", "explain",
                "how long", "what's involved", "process", "work with you"
            ],
            "strong_keywords": ["interested", "schedule", "demo", "tell me more", "considering"],
            "priority": "high",
            "notify": True,
            "response_urgency": "within 2 hours",
            "typical_intent": "Researching, comparing options, needs nurturing"
        },
        "COMPLAINT": {
            "description": "Customer has a problem, is dissatisfied, or providing negative feedback",
            "keywords": [
                "problem", "issue", "broken", "doesn't work", "disappointed",
                "refund", "cancel", "unhappy", "frustrated", "wrong", "bad",
                "terrible", "failed", "not working", "error", "mistake",
                "charged", "never received", "missing", "damaged"
            ],
            "strong_keywords": ["refund", "cancel", "terrible", "disappointed", "broken", "wrong"],
            "priority": "high",
            "notify": True,
            "response_urgency": "within 30 minutes",
            "typical_intent": "Needs resolution, may churn if not addressed"
        },
        "SUPPORT": {
            "description": "Customer needs help, has questions about how to use product/service",
            "keywords": [
                "how to", "help", "question", "can you", "does it", "what is",
                "where", "when", "why", "tutorial", "guide", "instructions",
                "setup", "configure", "settings", "access", "login", "account"
            ],
            "strong_keywords": ["how to", "help", "tutorial", "instructions", "setup"],
            "priority": "medium",
            "notify": False,
            "response_urgency": "within 4 hours",
            "typical_intent": "Needs assistance, not urgent unless repeated"
        },
        "GENERAL": {
            "description": "Casual conversation, compliments, gratitude, or low-priority chit-chat",
            "keywords": [
                "thanks", "thank you", "awesome", "love", "great", "nice",
                "cool", "amazing", "appreciate", "wonderful", "good job",
                "well done", "congrats", "hello", "hi", "hey", "lol", "haha"
            ],
            "strong_keywords": ["thanks", "thank you", "appreciate", "love it", "amazing"],
            "priority": "low",
            "notify": False,
            "response_urgency": "within 24 hours",
            "typical_intent": "Positive engagement, no action needed"
        },
        "ESCALATION": {
            "description": "Urgent issue requiring immediate attention - angry customer, legal threat, or crisis",
            "keywords": [
                "urgent", "immediately", "lawyer", "sue", "terrible", "worst",
                "scam", "fraud", "asap", "emergency", "unacceptable", "disgusting",
                "outraged", "furious", "never again", "report", "bbb", "attorney",
                "legal action", "police", "media", "viral"
            ],
            "strong_keywords": ["lawyer", "sue", "scam", "fraud", "legal action", "attorney", "police"],
            "priority": "critical",
            "notify": True,
            "response_urgency": "immediately",
            "typical_intent": "Crisis situation, requires senior attention"
        }
    }
    
    # =========================================================================
    # FEW-SHOT EXAMPLES FOR EACH CATEGORY (Phase 1)
    # =========================================================================
    FEW_SHOT_EXAMPLES = {
        "SALE": [
            "How much does your coaching program cost?",
            "I want to sign up for the monthly plan",
            "What's the pricing for your services?",
            "Can I pay in installments?",
            "I'm ready to get started, what's next?",
            "Do you offer any discounts for yearly plans?",
            "What payment methods do you accept?",
        ],
        "LEAD": [
            "Tell me more about what you offer",
            "I'm interested in learning about your services",
            "Can we schedule a call to discuss?",
            "How long have you been doing this?",
            "What results have your clients seen?",
            "I've been thinking about working with someone like you",
            "What's involved in the first session?",
        ],
        "COMPLAINT": [
            "This product doesn't work as advertised",
            "I'm very disappointed with the service",
            "I need a refund, this wasn't what I expected",
            "Your support team never got back to me",
            "I've been waiting weeks and still nothing",
            "The quality is way worse than what was shown",
            "I want to cancel my subscription immediately",
        ],
        "SUPPORT": [
            "How do I reset my password?",
            "Where can I find my invoices?",
            "Can you help me set this up?",
            "I'm having trouble logging in",
            "What's the best way to use this feature?",
            "Is there a tutorial for beginners?",
            "How do I change my account settings?",
        ],
        "GENERAL": [
            "Thank you so much for your help!",
            "This is amazing, I love it!",
            "Great job on the new update",
            "You guys are awesome 😊",
            "Just wanted to say hi!",
            "Keep up the good work!",
            "Happy holidays to the team!",
        ],
        "ESCALATION": [
            "This is a SCAM and I'm contacting my lawyer",
            "I'm going to report you to the BBB",
            "This is URGENT - I need help NOW",
            "Absolutely unacceptable, I want to speak to a manager",
            "I'm posting this everywhere if you don't fix it",
            "This is fraud and I'm calling my attorney",
            "I'm filing a complaint with consumer protection",
        ],
    }
    
    # =========================================================================
    # CONFIDENCE THRESHOLDS FOR MULTI-STAGE CLASSIFICATION (Phase 3)
    # =========================================================================
    KEYWORD_HIGH_CONFIDENCE_THRESHOLD = 3  # Strong keyword matches needed for instant classification
    QUICK_AI_CONFIDENCE_THRESHOLD = 0.85  # Confidence needed to skip detailed classification
    
    def __init__(self, client_id: str = "demo_client", use_rag: bool = True):
        """
        Initialize the optimized categorizer.
        
        Args:
            client_id: Client identifier for RAG lookup
            use_rag: Whether to use RAG for business context (Phase 2)
        """
        self.client_id = client_id
        self.use_rag = use_rag
        self.claude_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Models - Haiku for fast, Sonnet for detailed
        self.haiku_model = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
        self.sonnet_model = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
        
        # Initialize RAG system (Phase 2)
        self.rag = None
        if use_rag:
            try:
                from agents.rag_system import RAGSystem
                self.rag = RAGSystem()
                print(f"✅ RAG system integrated for business context")
            except Exception as e:
                print(f"⚠️ RAG not available: {e}")
                self.use_rag = False
        
        # Statistics tracking
        self.stats = {
            "total_classified": 0,
            "by_stage": {"keyword": 0, "quick_ai": 0, "detailed_ai": 0},
            "by_category": {cat: 0 for cat in self.CATEGORIES},
            "avg_confidence": 0.0,
        }
        
        # Initialize research context from Categorizer RAG (15 static research docs)
        # This is separate from self.rag (Qdrant — client-specific business knowledge).
        # The research context provides 2026 benchmark guidance baked into every prompt.
        self.research_context = ""
        self.escalation_keywords = ""
        self.categorizer_rag = None
        if _ConversationCategorizerRAG is not None:
            try:
                self.categorizer_rag = _ConversationCategorizerRAG()
                self.research_context = self.categorizer_rag.get_classification_guidance()
                self.escalation_keywords = self.categorizer_rag.get_escalation_keywords()
                print(
                    f"\u2705 Categorizer research context loaded "
                    f"({self.categorizer_rag.get_document_count()} docs)"
                )
            except Exception as _rag_err:
                print(f"\u26a0\ufe0f  Could not load categorizer research context: {_rag_err}")

        print(f"\u2705 Conversation Categorizer ready (Optimized)")
        print(f"   Client: {client_id}")
        print(f"   RAG: {'Enabled' if self.use_rag else 'Disabled'}")
        print(f"   Stages: Keyword \u2192 Quick AI \u2192 Detailed AI")
    
    # =========================================================================
    # MAIN CLASSIFICATION METHOD (Multi-Stage - Phase 3)
    # =========================================================================
    def categorize_message(
        self,
        message: str,
        context: Optional[str] = None,
        sender_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        force_detailed: bool = False
    ) -> CategoryResult:
        """
        Categorize a message using multi-stage classification.
        
        Stage 1: Keyword check (instant, free)
        Stage 2: Quick AI classification (fast, low cost)
        Stage 3: Detailed AI classification (accurate, higher cost)
        
        Args:
            message: The message text to categorize
            context: Optional context (platform, previous interactions, etc.)
            sender_id: Optional sender identifier
            conversation_history: Optional previous messages in conversation
            force_detailed: Skip stages 1-2 and go straight to detailed
            
        Returns:
            CategoryResult with category, confidence, and metadata
        """
        print(f"\n🔍 Categorizing: '{message[:60]}{'...' if len(message) > 60 else ''}'")
        
        # Get business context from RAG (Phase 2)
        business_context = None
        if self.use_rag and self.rag:
            business_context = self._get_business_context(message)
        
        # Stage 1: Keyword-based classification (instant)
        if not force_detailed:
            keyword_result = self._stage1_keyword_classification(message)
            if keyword_result:
                keyword_result.business_context = business_context
                self._update_stats(keyword_result)
                return keyword_result
        
        # Stage 2: Quick AI classification (fast)
        if not force_detailed:
            quick_result = self._stage2_quick_ai_classification(
                message=message,
                context=context,
                business_context=business_context
            )
            if quick_result and quick_result.confidence >= self.QUICK_AI_CONFIDENCE_THRESHOLD:
                self._update_stats(quick_result)
                return quick_result
        
        # Stage 3: Detailed AI classification (accurate)
        detailed_result = self._stage3_detailed_ai_classification(
            message=message,
            context=context,
            conversation_history=conversation_history,
            business_context=business_context
        )
        self._update_stats(detailed_result)
        return detailed_result
    
    # =========================================================================
    # STAGE 1: KEYWORD-BASED CLASSIFICATION (Instant, Free)
    # =========================================================================
    def _stage1_keyword_classification(self, message: str) -> Optional[CategoryResult]:
        """
        Fast keyword-based pre-filter for obvious categories.
        Only returns result if HIGH confidence match (multiple strong keywords).
        """
        message_lower = message.lower()
        
        # Count strong keyword matches per category
        category_scores: Dict[str, Tuple[int, int]] = {}  # {category: (strong_matches, total_matches)}
        
        for category, config in self.CATEGORIES.items():
            strong_matches = sum(1 for kw in config.get("strong_keywords", []) if kw in message_lower)
            total_matches = sum(1 for kw in config["keywords"] if kw in message_lower)
            category_scores[category] = (strong_matches, total_matches)
        
        # Check for ESCALATION first (highest priority)
        esc_strong, esc_total = category_scores["ESCALATION"]
        if esc_strong >= 1 or esc_total >= 2:
            print(f"⚡ Stage 1 (Keyword): ESCALATION detected ({esc_strong} strong, {esc_total} total)")
            return self._create_result(
                category="ESCALATION",
                confidence=0.95 if esc_strong >= 1 else 0.85,
                reasoning=f"Escalation keywords detected: {esc_total} matches",
                tone="urgent",
                stage="keyword"
            )
        
        # Find best category by strong matches, then total matches
        best_category = None
        best_strong = 0
        best_total = 0
        
        for category, (strong, total) in category_scores.items():
            if category == "ESCALATION":
                continue
            if strong > best_strong or (strong == best_strong and total > best_total):
                best_category = category
                best_strong = strong
                best_total = total
        
        # Only return if we have high confidence (multiple strong matches)
        if best_strong >= 2 or (best_strong >= 1 and best_total >= self.KEYWORD_HIGH_CONFIDENCE_THRESHOLD):
            confidence = min(0.90, 0.70 + (best_strong * 0.10) + (best_total * 0.03))
            print(f"⚡ Stage 1 (Keyword): {best_category} ({best_strong} strong, {best_total} total) → conf={confidence:.2f}")
            
            return self._create_result(
                category=best_category,
                confidence=confidence,
                reasoning=f"Keyword match: {best_total} matches ({best_strong} strong)",
                tone=self._suggest_tone(best_category),
                stage="keyword"
            )
        
        # Not confident enough for keyword-only classification
        print(f"   Stage 1 (Keyword): No high-confidence match, proceeding to Stage 2")
        return None
    
    # =========================================================================
    # STAGE 2: QUICK AI CLASSIFICATION (Fast, Low Cost)
    # =========================================================================
    def _stage2_quick_ai_classification(
        self,
        message: str,
        context: Optional[str] = None,
        business_context: Optional[str] = None
    ) -> Optional[CategoryResult]:
        """
        Quick AI classification using Haiku with minimal context.
        Uses few-shot examples for better accuracy.
        """
        prompt = self._build_quick_prompt(message, context, business_context)
        
        try:
            response = self.claude_client.messages.create(
                model=self.haiku_model,
                max_tokens=150,
                temperature=0.2,  # Lower temperature for consistency
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            result = self._parse_ai_response(result_text, stage="quick_ai")
            
            print(f"🚀 Stage 2 (Quick AI): {result.category} (conf={result.confidence:.2f})")
            
            if result.confidence >= self.QUICK_AI_CONFIDENCE_THRESHOLD:
                result.business_context = business_context
                return result
            else:
                print(f"   Confidence below threshold ({self.QUICK_AI_CONFIDENCE_THRESHOLD}), proceeding to Stage 3")
                return result  # Return but let caller decide to continue
                
        except Exception as e:
            print(f"⚠️ Stage 2 error: {e}")
            return None
    
    def _build_quick_prompt(
        self,
        message: str,
        context: Optional[str] = None,
        business_context: Optional[str] = None
    ) -> str:
        """
        Build compact Stage 2 prompt (Haiku) with few-shot examples.
        Uses the QUICK_CLASSIFICATION_PROMPT template from the RAG prompts file
        when available; falls back to inline prompt if the module failed to load.
        """
        # Build few-shot examples block (2 per category for speed)
        examples_text = ""
        for category, examples in self.FEW_SHOT_EXAMPLES.items():
            examples_text += f"\n{category}:\n"
            for ex in examples[:2]:
                examples_text += f"  - \"{ex}\"\n"

        # Use structured metaprompt when available
        if _get_prompt is not None and _format_prompt is not None:
            try:
                template = _get_prompt("quick_classification")
                return _format_prompt(
                    template,
                    message=message,
                    context=context or "Not specified",
                    few_shot_examples=examples_text,
                    business_context=business_context or "No specific client context available",
                    research_context=self.research_context or "Use standard classification thresholds",
                )
            except Exception as _e:
                print(f"\u26a0\ufe0f  Quick prompt template error, using fallback: {_e}")

        # Fallback: original inline prompt (prompt system not loaded)
        context_text = f"\nContext: {context}" if context else ""
        business_text = f"\nBusiness context: {business_context}" if business_context else ""
        return (
            f"Classify this message into ONE category. Be decisive.\n\n"
            f"CATEGORIES & EXAMPLES:{examples_text}\n"
            f"MESSAGE: \"{message}\"{context_text}{business_text}\n\n"
            f"Respond EXACTLY as:\n"
            f"CATEGORY: [SALE|LEAD|COMPLAINT|SUPPORT|GENERAL|ESCALATION]\n"
            f"CONFIDENCE: [0.0-1.0]\n"
            f"TONE: [urgent|helpful|friendly|professional|empathetic]"
        )
    
    # =========================================================================
    # STAGE 3: DETAILED AI CLASSIFICATION (Accurate, Full Context)
    # =========================================================================
    def _stage3_detailed_ai_classification(
        self,
        message: str,
        context: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        business_context: Optional[str] = None
    ) -> CategoryResult:
        """
        Detailed AI classification using Sonnet with full context.
        Uses all few-shot examples + conversation history + business context.
        """
        prompt = self._build_detailed_prompt(
            message=message,
            context=context,
            conversation_history=conversation_history,
            business_context=business_context
        )
        
        try:
            response = self.claude_client.messages.create(
                model=self.sonnet_model,
                max_tokens=300,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            result = self._parse_ai_response(result_text, stage="detailed_ai")
            result.business_context = business_context
            
            print(f"🎯 Stage 3 (Detailed AI): {result.category} (conf={result.confidence:.2f})")
            print(f"   Reasoning: {result.reasoning}")
            
            return result
            
        except Exception as e:
            print(f"❌ Stage 3 error: {e}")
            return self._create_fallback_result("GENERAL")
    
    def _build_detailed_prompt(
        self,
        message: str,
        context: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        business_context: Optional[str] = None
    ) -> str:
        """
        Build comprehensive Stage 3 prompt (Sonnet) with full context.
        Uses the DETAILED_CLASSIFICATION_PROMPT template from the RAG prompts file
        when available; falls back to inline prompt if the module failed to load.
        Conversation history: last 3-5 messages per 2026 research (beyond 5 = <0.5% gain).
        """
        # Build detailed category definitions block with all examples
        categories_text = ""
        for category, config in self.CATEGORIES.items():
            examples = self.FEW_SHOT_EXAMPLES.get(category, [])
            examples_str = "\n    ".join(f'- "{ex}"' for ex in examples[:5])
            categories_text += (
                f"\n**{category}** - {config['description']}\n"
                f"  Priority: {config['priority']}\n"
                f"  Typical intent: {config['typical_intent']}\n"
                f"  Examples:\n    {examples_str}\n"
            )

        # Build conversation history block
        # Research: last 3-5 messages optimal; use sliding summary strategy for longer threads
        history_text = ""
        if conversation_history and len(conversation_history) > 0:
            history_text = "\n**CONVERSATION HISTORY** (most recent last, last 5 messages):\n"
            for msg in conversation_history[-5:]:
                sender = msg.get("sender", "User")
                text = msg.get("text", "")[:100]
                history_text += f"  {sender}: {text}\n"

        # Use structured metaprompt when available
        if _get_prompt is not None and _format_prompt is not None:
            try:
                template = _get_prompt("detailed_classification")
                return _format_prompt(
                    template,
                    message=message,
                    context=context or "Not specified",
                    conversation_history=history_text or "No prior messages in this conversation.",
                    category_definitions=categories_text,
                    business_context=business_context or "No specific client context available",
                    research_context=self.research_context or "Use standard classification thresholds",
                )
            except Exception as _e:
                print(f"\u26a0\ufe0f  Detailed prompt template error, using fallback: {_e}")

        # Fallback: original inline prompt (prompt system not loaded)
        context_text = f"\n**Platform/Source:** {context}" if context else ""
        business_text = f"\n**Business Context:** {business_context}" if business_context else ""
        return (
            f"You are an expert conversation categorization system. Analyze the message carefully and classify it.\n\n"
            f"## CATEGORIES:\n{categories_text}\n\n"
            f"## MESSAGE TO CLASSIFY:\n\"{message}\"\n"
            f"{context_text}{history_text}{business_text}\n\n"
            f"## ANALYSIS INSTRUCTIONS:\n"
            f"1. Consider the customer's PRIMARY intent (what do they want?)\n"
            f"2. Look for emotional signals (urgency, frustration, enthusiasm)\n"
            f"3. Consider conversation history if available\n"
            f"4. If message fits multiple categories, choose the one requiring faster response\n"
            f"5. Rate your confidence honestly (0.0-1.0)\n\n"
            f"## RESPONSE FORMAT (exactly):\n"
            f"CATEGORY: [one of: SALE, LEAD, COMPLAINT, SUPPORT, GENERAL, ESCALATION]\n"
            f"CONFIDENCE: [0.0 to 1.0]\n"
            f"REASONING: [1-2 sentence explanation]\n"
            f"TONE: [urgent|helpful|friendly|professional|empathetic]\n"
            f"SECONDARY: [optional secondary category if applicable, or NONE]"
        )
    
    # =========================================================================
    # RAG INTEGRATION (Phase 2)
    # =========================================================================
    def _get_business_context(self, message: str) -> Optional[str]:
        """Fetch relevant business context from RAG system."""
        if not self.rag:
            return None
        
        try:
            results = self.rag.search(message, client_id=self.client_id, limit=2)
            if results:
                context_parts = [r["text"][:200] for r in results if r.get("score", 0) > 0.7]
                if context_parts:
                    return " | ".join(context_parts)
        except Exception as e:
            print(f"⚠️ RAG lookup failed: {e}")
        
        return None
    
    # =========================================================================
    # RESPONSE PARSING & RESULT CREATION
    # =========================================================================
    def _parse_ai_response(self, result_text: str, stage: str) -> CategoryResult:
        """Parse Claude's response into a CategoryResult."""
        lines = result_text.strip().split("\n")
        
        # Defaults
        category = "GENERAL"
        confidence = 0.5
        reasoning = "Unable to parse response"
        tone = "friendly"
        secondary = None
        
        # Parse each line
        for line in lines:
            line_upper = line.upper()
            if line_upper.startswith("CATEGORY:"):
                cat_value = line.split(":", 1)[1].strip().upper()
                # Handle potential extra text
                cat_value = cat_value.split()[0] if cat_value else "GENERAL"
                if cat_value in self.CATEGORIES:
                    category = cat_value
            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    conf_str = line.split(":", 1)[1].strip()
                    # Handle formats like "0.85" or "85%" or "0.85 (high)"
                    conf_str = re.search(r"[\d.]+", conf_str)
                    if conf_str:
                        confidence = float(conf_str.group())
                        if confidence > 1:
                            confidence = confidence / 100
                except:
                    confidence = 0.5
            elif line_upper.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line_upper.startswith("TONE:"):
                tone = line.split(":", 1)[1].strip().lower()
            elif line_upper.startswith("SECONDARY:"):
                sec_value = line.split(":", 1)[1].strip().upper()
                if sec_value and sec_value != "NONE" and sec_value in self.CATEGORIES:
                    secondary = sec_value
        
        return self._create_result(
            category=category,
            confidence=confidence,
            reasoning=reasoning,
            tone=tone,
            stage=stage,
            secondary=secondary
        )
    
    def _create_result(
        self,
        category: str,
        confidence: float,
        reasoning: str,
        tone: str,
        stage: str,
        secondary: Optional[str] = None,
        business_context: Optional[str] = None
    ) -> CategoryResult:
        """Create a CategoryResult with proper defaults."""
        config = self.CATEGORIES.get(category, self.CATEGORIES["GENERAL"])
        
        return CategoryResult(
            category=category,
            confidence=confidence,
            priority=config["priority"],
            reasoning=reasoning,
            suggested_response_tone=tone,
            requires_notification=config["notify"],
            secondary_category=secondary,
            classification_stage=stage,
            business_context=business_context
        )
    
    def _create_fallback_result(self, category: str) -> CategoryResult:
        """Create a fallback result when AI classification fails."""
        return self._create_result(
            category=category,
            confidence=0.5,
            reasoning="Fallback categorization (AI classification failed)",
            tone="friendly",
            stage="fallback"
        )
    
    def _suggest_tone(self, category: str) -> str:
        """Suggest response tone based on category."""
        tone_map = {
            "SALE": "professional",
            "LEAD": "helpful",
            "COMPLAINT": "empathetic",
            "SUPPORT": "helpful",
            "GENERAL": "friendly",
            "ESCALATION": "urgent"
        }
        return tone_map.get(category, "friendly")
    
    # =========================================================================
    # STATISTICS & UTILITIES
    # =========================================================================
    def _update_stats(self, result: CategoryResult):
        """Update internal statistics."""
        self.stats["total_classified"] += 1
        self.stats["by_stage"][result.classification_stage] = \
            self.stats["by_stage"].get(result.classification_stage, 0) + 1
        self.stats["by_category"][result.category] = \
            self.stats["by_category"].get(result.category, 0) + 1
        
        # Update rolling average confidence
        n = self.stats["total_classified"]
        old_avg = self.stats["avg_confidence"]
        self.stats["avg_confidence"] = old_avg + (result.confidence - old_avg) / n
        
        # Log notification requirement
        if result.requires_notification:
            print(f"   🔔 Notification required: {result.priority} priority")
    
    def get_stats(self) -> Dict:
        """Get classification statistics."""
        return self.stats.copy()
    
    def batch_categorize(self, messages: List[Dict]) -> List[CategoryResult]:
        """
        Categorize multiple messages in batch.
        
        Args:
            messages: List of dicts with 'message', 'context', 'sender_id' keys
            
        Returns:
            List of CategoryResult objects
        """
        results = []
        
        print(f"\n📊 Batch categorizing {len(messages)} messages...")
        
        for i, msg in enumerate(messages, 1):
            print(f"\n[{i}/{len(messages)}]")
            result = self.categorize_message(
                message=msg.get("message", ""),
                context=msg.get("context"),
                sender_id=msg.get("sender_id"),
                conversation_history=msg.get("history")
            )
            results.append(result)
        
        # Summary
        print(f"\n✅ Batch complete! Summary:")
        print(f"   Total: {len(results)}")
        print(f"   By stage: {self.stats['by_stage']}")
        print(f"   Require notification: {sum(1 for r in results if r.requires_notification)}")
        
        return results
    
    def get_category_stats(self, results: List[CategoryResult]) -> Dict:
        """Get statistics from categorization results."""
        stats = {
            "total": len(results),
            "by_category": {},
            "by_priority": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "by_stage": {"keyword": 0, "quick_ai": 0, "detailed_ai": 0},
            "requires_notification": 0,
            "avg_confidence": 0.0
        }
        
        if not results:
            return stats
        
        for result in results:
            stats["by_category"][result.category] = stats["by_category"].get(result.category, 0) + 1
            stats["by_priority"][result.priority] += 1
            stats["by_stage"][result.classification_stage] = \
                stats["by_stage"].get(result.classification_stage, 0) + 1
            if result.requires_notification:
                stats["requires_notification"] += 1
        
        stats["avg_confidence"] = sum(r.confidence for r in results) / len(results)
        
        return stats


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING OPTIMIZED CONVERSATION CATEGORIZER")
    print("="*70)
    
    # Initialize with RAG disabled for testing (faster)
    categorizer = ConversationCategorizer(client_id="demo_client", use_rag=False)
    
    # Test cases covering all categories and stages
    test_messages = [
        # SALE - should trigger Stage 1 (keyword) or Stage 2 (quick)
        {"message": "How much does your coaching program cost? I'm ready to sign up!", "context": "Instagram DM"},
        {"message": "What's the pricing for the premium package?", "context": "Website chat"},
        
        # LEAD - Stage 2 likely
        {"message": "I'm interested in learning more about your services. Can we schedule a call?", "context": "LinkedIn message"},
        {"message": "What kind of results have your clients seen?", "context": "Email"},
        
        # COMPLAINT - should trigger quickly
        {"message": "This product is broken and I want a refund immediately!", "context": "Facebook comment"},
        {"message": "I'm disappointed, this wasn't what I expected", "context": "Email"},
        
        # SUPPORT - Stage 2 likely
        {"message": "How do I reset my password?", "context": "Email"},
        {"message": "Where can I find my invoice?", "context": "DM"},
        
        # GENERAL - Stage 1 or 2
        {"message": "Thank you so much! This was really helpful 😊", "context": "Instagram comment"},
        {"message": "You guys are awesome, keep it up!", "context": "Twitter reply"},
        
        # ESCALATION - must trigger Stage 1 (keyword)
        {"message": "This is a SCAM! I'm calling my lawyer!", "context": "DM"},
        {"message": "I'm going to report you to the BBB if this isn't fixed TODAY", "context": "Email"},
        
        # AMBIGUOUS - should trigger Stage 3 (detailed)
        {"message": "Can I get a discount if I sign up today?", "context": "DM"},  # Could be SALE or LEAD
        {"message": "I've been waiting for a response", "context": "Email"},  # Could be COMPLAINT or SUPPORT
    ]
    
    print("\n" + "-"*70)
    results = categorizer.batch_categorize(test_messages)
    
    print("\n" + "="*70)
    print("📊 DETAILED RESULTS")
    print("="*70)
    
    for i, (msg, result) in enumerate(zip(test_messages, results), 1):
        print(f"\n{i}. \"{msg['message'][:55]}...\"")
        print(f"   Category: {result.category}" + (f" (secondary: {result.secondary_category})" if result.secondary_category else ""))
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Stage: {result.classification_stage}")
        print(f"   Priority: {result.priority}")
        print(f"   Notify: {'✅' if result.requires_notification else '❌'}")
        print(f"   Tone: {result.suggested_response_tone}")
        print(f"   Reasoning: {result.reasoning}")
    
    # Final stats
    print("\n" + "="*70)
    print("📈 FINAL STATISTICS")
    print("="*70)
    stats = categorizer.get_category_stats(results)
    print(f"Total: {stats['total']}")
    print(f"Average confidence: {stats['avg_confidence']:.2f}")
    print(f"\nBy Stage (cost optimization):")
    for stage, count in stats['by_stage'].items():
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {stage}: {count} ({pct:.0f}%)")
    print(f"\nBy Category:")
    for cat, count in sorted(stats['by_category'].items()):
        print(f"  {cat}: {count}")
    print(f"\nNotifications required: {stats['requires_notification']}")
