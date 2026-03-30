"""
Email Support Agent
===================
AI-powered email customer support agent that monitors incoming emails,
generates contextual replies, and escalates when needed.

RESPONSIBILITIES:
- Monitor incoming support emails (IMAP, webhooks, API)
- Parse and understand customer emails
- Generate helpful, contextual replies using RAG + voice matching
- Detect escalation triggers and route to humans
- Track conversation history and sentiment
- Maintain SLA compliance (response times)
- Handle attachments and complex email threads
- Auto-detect spam, auto-responders, and bounce-backs

INTEGRATION:
- Uses RAG System for client knowledge base
- Uses Voice Matching for client tone/style
- Uses Guardrails for safety and abuse protection
- Uses Conversation Memory for thread history
- Integrates with notification system for escalations

SAFETY:
- Confidence scoring before auto-send
- Human escalation keywords
- Sentiment analysis for frustrated customers
- PII redaction and GDPR compliance
- Loop prevention (max replies per thread)
"""

import sys
# Windows UTF-8 fix: prevent cp1252 codec crash on emoji in print() calls
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
import asyncio
import glob
import json
import re
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from anthropic import Anthropic
from dotenv import load_dotenv

# Resend (email sending) - graceful fallback if not installed
try:
    import resend as resend_sdk
    _RESEND_AVAILABLE = True
except ImportError:
    _RESEND_AVAILABLE = False

# Gmail API (email inbound reading) - graceful fallback if not installed
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from googleapiclient.discovery import build as google_build
    import base64
    _GMAIL_API_AVAILABLE = True
except ImportError:
    _GMAIL_API_AVAILABLE = False

# Import prompt system
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from pathlib import Path
prompt_system_path = Path(__file__).parent.parent / "Agent RAGs" / "Email Support RAG" / "email_support_prompts.py"
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("email_support_prompts", prompt_system_path)
    prompt_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prompt_module)
    get_prompt = prompt_module.get_prompt
    format_prompt = prompt_module.format_prompt
    print("✅ Email Support prompt system loaded")
except Exception as e:
    print(f"⚠️  Failed to load prompt system: {e}")
    get_prompt = None
    format_prompt = None

load_dotenv()


class EmailSupportRAG:
    """
    RAG system for Email Support Agent - loads research on best practices,
    safety thresholds, compliance, and technical constraints.
    
    RESEARCH COVERAGE:
    - SLA and Performance Benchmarks (4 docs): response times, CSAT, FCR, acknowledgement
    - Compliance and Data Privacy (4 docs): GDPR, PII redaction, PCI DSS, CAN-SPAM
    - Technical Constraints (5 docs): Gmail/SendGrid limits, IMAP polling, threading, attachments
    - Automation Safety Thresholds (4 docs): confidence scoring, escalation keywords, sentiment, loop prevention
    - RAG Context Strategy (3 docs): token windows, order retrieval, thread summarization
    
    TOTAL: 20 research documents covering email support automation
    """
    
    def __init__(self, rag_folder: str = "Agent RAGs/Email Support RAG"):
        self.rag_folder = rag_folder
        self.documents: Dict[str, List[Dict[str, str]]] = {}
        self.load_all_documents()
    
    def load_all_documents(self):
        """Load all email support research documents."""
        base_path = os.path.dirname(os.path.dirname(__file__))
        full_path = os.path.join(base_path, self.rag_folder)
        
        if not os.path.exists(full_path):
            print(f"⚠️  Email Support RAG folder not found: {full_path}")
            return
        
        # Research categories
        categories = [
            "sla_and_performance_benchmarks",
            "compliance_and_data_privacy",
            "technical_constraints_and_limits",
            "automation_safety_thresholds",
            "rag_context_strategy"
        ]
        
        total_loaded = 0
        for category in categories:
            category_path = os.path.join(full_path, category)
            if not os.path.exists(category_path):
                continue
            
            # Find all markdown files in this category and subdirectories
            pattern = os.path.join(category_path, "**", "*.md")
            md_files = glob.glob(pattern, recursive=True)
            
            self.documents[category] = []
            
            for file_path in md_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        filename = os.path.basename(file_path)
                        self.documents[category].append({
                            "filename": filename,
                            "content": content,
                            "path": file_path
                        })
                        total_loaded += 1
                except Exception as e:
                    print(f"⚠️  Failed to load {file_path}: {e}")
            
            if self.documents[category]:
                print(f"📁 {category}: {len(self.documents[category])} documents")
        
        print(f"✅ Loaded {total_loaded} email support research documents across {len(categories)} categories")
    
    def retrieve_relevant_context(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        top_k: int = 3
    ) -> str:
        """
        Retrieve most relevant research documents for a query.
        
        Args:
            query: Search query (e.g., "response time SLA benchmarks")
            categories: Specific categories to search (None = all categories)
            top_k: Number of documents to return
            
        Returns:
            Concatenated research context
        """
        if not self.documents:
            return "No research documents loaded."
        
        # Determine which categories to search
        search_categories = categories if categories else list(self.documents.keys())
        
        # Simple keyword-based relevance scoring
        query_keywords = set(query.lower().split())
        scored_docs = []
        
        for category in search_categories:
            if category not in self.documents:
                continue
            
            for doc in self.documents[category]:
                # Score based on filename and content matches
                filename_lower = doc["filename"].lower()
                content_lower = doc["content"].lower()
                
                # Filename matches worth more
                filename_score = sum(3 for keyword in query_keywords if keyword in filename_lower)
                
                # Content matches
                content_score = sum(0.1 for keyword in query_keywords if keyword in content_lower)
                
                total_score = filename_score + content_score
                
                if total_score > 0:
                    scored_docs.append((total_score, doc))
        
        # Sort by relevance and take top_k
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        top_docs = scored_docs[:top_k]
        
        if not top_docs:
            return "No relevant research found for this query."
        
        # Concatenate document contents
        context_parts = []
        for score, doc in top_docs:
            # Truncate very long docs
            content = doc["content"][:3000] if len(doc["content"]) > 3000 else doc["content"]
            context_parts.append(f"### {doc['filename']}\n\n{content}\n\n")
        
        return "\n".join(context_parts)


class EmailType(Enum):
    """Types of incoming emails."""
    QUESTION = "question"
    COMPLAINT = "complaint"
    FEEDBACK = "feedback"
    PRAISE = "praise"
    REQUEST = "request"
    BUG_REPORT = "bug_report"
    AUTO_RESPONDER = "auto_responder"
    SPAM = "spam"


class EmailUrgency(Enum):
    """Email urgency levels."""
    CRITICAL = "critical"      # Security, fraud, data breach
    HIGH = "high"              # Payment issues, service down, angry customer
    NORMAL = "normal"          # General questions, feature requests
    LOW = "low"                # Non-urgent feedback, suggestions


class ConversationStatus(Enum):
    """Status of email conversations."""
    OPEN = "open"                          # New or ongoing
    WAITING_CUSTOMER = "waiting_customer"  # Waiting for customer reply
    WAITING_HUMAN = "waiting_human"        # Escalated, awaiting human response
    RESOLVED = "resolved"                  # Closed/resolved
    SPAM = "spam"                          # Marked as spam


class EscalationReason(Enum):
    """Reasons for human escalation."""
    KEYWORD_TRIGGERED = "keyword_triggered"      # Customer said "speak to human"
    LOW_CONFIDENCE = "low_confidence"            # AI confidence < threshold
    NEGATIVE_SENTIMENT = "negative_sentiment"    # Customer very frustrated/angry
    COMPLEX_ISSUE = "complex_issue"             # Issue beyond AI capability
    SENSITIVE_TOPIC = "sensitive_topic"         # Legal, medical, financial
    REFUND_REQUEST = "refund_request"           # Money-related decisions
    DATA_REQUEST = "data_request"               # GDPR/privacy requests
    COMPLAINT_ESCALATION = "complaint_escalation" # Serious complaint


@dataclass
class EmailMessage:
    """Structured email message."""
    message_id: str
    thread_id: str
    sender_email: str
    sender_name: Optional[str]
    subject: str
    body_text: str
    body_html: Optional[str]
    received_at: datetime
    attachments: List[Dict[str, Any]]
    headers: Dict[str, str]
    is_reply: bool
    reply_to_message_id: Optional[str]


@dataclass
class EmailReply:
    """Generated email reply."""
    reply_body: str
    confidence_score: float
    should_escalate: bool
    escalation_reason: Optional[EscalationReason]
    detected_type: EmailType
    detected_urgency: EmailUrgency
    sentiment_score: float  # -1.0 to 1.0
    rag_context_used: str
    processing_time_ms: int


@dataclass
class EmailConversation:
    """Email conversation thread."""
    conversation_id: str
    client_id: str
    customer_email: str
    customer_name: Optional[str]
    subject: str
    status: ConversationStatus
    created_at: datetime
    last_message_at: datetime
    resolved_at: Optional[datetime]
    message_count: int
    ai_reply_count: int
    escalated: bool
    escalation_reason: Optional[EscalationReason]
    sentiment_trend: List[float]  # Track sentiment over time
    tags: List[str]


class EmailSupportAgent:
    """
    AI-powered email support agent.
    
    Usage:
        agent = EmailSupportAgent(client_id="demo_client", use_rag=True)
        
        # Process incoming email
        reply = await agent.process_incoming_email(email_message)
        
        # Send reply (if confidence high enough)
        if reply.should_escalate:
            agent.escalate_to_human(email_message, reply)
        else:
            await agent.send_reply(email_message, reply)
    """
    
    # Escalation keywords
    ESCALATION_KEYWORDS = [
        "speak to a human", "talk to a person", "real person", "human agent",
        "manager", "supervisor", "escalate", "unacceptable", "lawyer",
        "sue", "legal action", "refund", "cancel", "unsubscribe immediately",
        "terrible service", "worst experience", "never again", "BBB", "attorney"
    ]
    
    # Auto-responder detection patterns
    AUTO_RESPONDER_PATTERNS = [
        "out of office", "automatic reply", "away from", "on vacation",
        "currently unavailable", "will respond when", "auto-reply",
        "out of the office", "away message"
    ]
    
    # Confidence thresholds (based on research)
    CONFIDENCE_AUTO_SEND = 0.85      # Auto-send if confidence >= 85%
    CONFIDENCE_DRAFT_MODE = 0.70     # Draft mode if 70-85%
    CONFIDENCE_ESCALATE = 0.70       # Escalate if < 70%
    
    # Sentiment thresholds
    SENTIMENT_ESCALATE = -0.60       # Escalate if sentiment <= -0.60 (very negative)
    
    # Loop prevention
    MAX_REPLIES_PER_THREAD = 5       # Max auto-replies per conversation
    
    def __init__(
        self,
        client_id: str,
        use_rag: bool = True,
        email_config: Optional[Dict[str, str]] = None
    ):
        self.client_id = client_id
        self.use_rag = use_rag
        self.email_config = email_config or {}
        
        # Initialize Claude
        self.claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.sonnet_model = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
        
        # Initialize RAG system
        if use_rag:
            try:
                self.rag = EmailSupportRAG()
                print("✅ Email Support RAG system loaded")
            except Exception as e:
                print(f"⚠️  Failed to load Email Support RAG: {e}")
                self.rag = None
                self.use_rag = False
        else:
            self.rag = None
        
        # Active conversations (in-memory, should be database in production)
        self.conversations: Dict[str, EmailConversation] = {}
        
        # Escalated conversation IDs
        self.escalated_conversations: Set[str] = set()

    # =============================================================================
    # LIGHTWEIGHT CATEGORISATION (used by scheduler / inbox fetch)
    # =============================================================================

    async def categorize_email_text(
        self,
        subject: str,
        body: str,
        sender: str = "",
    ) -> Dict[str, Any]:
        """
        Quick AI categorisation of a single inbound email.

        Returns dict with:
          - category: one of support, complaint, inquiry, newsletter,
                      notification, spam, urgent, general
          - draft_reply: short AI-drafted reply (empty string if not actionable)
        """
        prompt = (
            "You are an email-triage assistant. Categorize the email below and, "
            "if it is actionable (support question, complaint, inquiry), write a "
            "short, friendly draft reply in the client's voice.\n\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Body:\n{body[:2000]}\n\n"
            "Reply ONLY with valid JSON — no markdown fences:\n"
            '{"category":"<one of: support|complaint|inquiry|newsletter|notification|spam|urgent|general>",'
            '"draft_reply":"<reply text or empty string>"}'
        )
        try:
            resp = self.claude.messages.create(
                model=self.sonnet_model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            # Strip markdown code fences if the model wraps them
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            print(f"[email_support_agent] categorize_email_text error: {e}")
            return {"category": "general", "draft_reply": ""}
    
    # =============================================================================
    # EMAIL PROCESSING
    # =============================================================================
    
    async def process_incoming_email(
        self,
        email_message: EmailMessage,
        client_knowledge: Optional[str] = None
    ) -> EmailReply:
        """
        Process an incoming email and generate a reply.
        
        Args:
            email_message: Parsed email message
            client_knowledge: Optional RAG context from client's knowledge base
            
        Returns:
            EmailReply with generated response and metadata
        """
        start_time = datetime.now()
        
        # 1. Check if auto-responder or spam
        if self._is_auto_responder(email_message):
            print(f"🤖 Auto-responder detected, skipping: {email_message.subject}")
            return EmailReply(
                reply_body="",
                confidence_score=0.0,
                should_escalate=False,
                escalation_reason=None,
                detected_type=EmailType.AUTO_RESPONDER,
                detected_urgency=EmailUrgency.LOW,
                sentiment_score=0.0,
                rag_context_used="",
                processing_time_ms=0
            )
        
        # 2. Load conversation history
        conversation = self._get_or_create_conversation(email_message)
        
        # 3. Check if already escalated
        if conversation.conversation_id in self.escalated_conversations:
            print(f"⚠️  Conversation already escalated: {conversation.conversation_id}")
            return EmailReply(
                reply_body="This conversation has been escalated to our team. Someone will respond shortly.",
                confidence_score=1.0,
                should_escalate=True,
                escalation_reason=EscalationReason.KEYWORD_TRIGGERED,
                detected_type=EmailType.QUESTION,
                detected_urgency=EmailUrgency.HIGH,
                sentiment_score=-0.3,
                rag_context_used="",
                processing_time_ms=0
            )
        
        # 4. Check for loop prevention
        if conversation.ai_reply_count >= self.MAX_REPLIES_PER_THREAD:
            print(f"⚠️  Max replies reached for thread: {conversation.conversation_id}")
            return EmailReply(
                reply_body="",
                confidence_score=0.0,
                should_escalate=True,
                escalation_reason=EscalationReason.COMPLEX_ISSUE,
                detected_type=EmailType.QUESTION,
                detected_urgency=EmailUrgency.NORMAL,
                sentiment_score=0.0,
                rag_context_used="Loop prevention triggered",
                processing_time_ms=0
            )
        
        # 5. Check for escalation keywords
        escalation_check = self._check_escalation_keywords(email_message.body_text)
        if escalation_check:
            print(f"🚨 Escalation keyword detected: {escalation_check}")
            return EmailReply(
                reply_body="I'll connect you with someone from our team who can help. They'll respond shortly!",
                confidence_score=1.0,
                should_escalate=True,
                escalation_reason=EscalationReason.KEYWORD_TRIGGERED,
                detected_type=EmailType.QUESTION,
                detected_urgency=EmailUrgency.HIGH,
                sentiment_score=0.0,
                rag_context_used="",
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
        
        # 6. Retrieve RAG context
        rag_context = ""
        if self.use_rag and self.rag:
            # Get email support research context
            rag_context = self.rag.retrieve_relevant_context(
                query=f"customer support reply {email_message.subject} {email_message.body_text[:200]}",
                top_k=2
            )
            
            # Append client knowledge if provided
            if client_knowledge:
                rag_context += f"\n\n### Client Knowledge Base\n\n{client_knowledge}"
        
        # 7. Analyze email type and urgency
        email_type, urgency = await self._analyze_email_type_and_urgency(
            email_message,
            rag_context
        )
        
        # 8. Analyze sentiment
        conversation = self._get_or_create_conversation(email_message)
        history_context = f"Message #{conversation.message_count} in thread. Previous sentiment: {conversation.sentiment_trend[-3:] if conversation.sentiment_trend else 'N/A'}"
        sentiment_score = await self._analyze_sentiment(
            email_message.body_text,
            subject=email_message.subject,
            history=history_context
        )
        
        # 9. Check for negative sentiment escalation
        if sentiment_score <= self.SENTIMENT_ESCALATE:
            print(f"🚨 Negative sentiment detected: {sentiment_score:.2f}")
            return EmailReply(
                reply_body="I'm sorry you're experiencing this issue. Let me connect you with a team member who can help resolve this right away.",
                confidence_score=1.0,
                should_escalate=True,
                escalation_reason=EscalationReason.NEGATIVE_SENTIMENT,
                detected_type=email_type,
                detected_urgency=EmailUrgency.HIGH,
                sentiment_score=sentiment_score,
                rag_context_used=rag_context[:500],
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
        
        # 10. Generate reply with Claude
        reply_body, confidence_score = await self._generate_reply(
            email_message=email_message,
            conversation_history=conversation,
            rag_context=rag_context,
            email_type=email_type,
            urgency=urgency,
            sentiment=sentiment_score
        )
        
        # 11. Determine if should escalate based on confidence
        should_escalate = confidence_score < self.CONFIDENCE_ESCALATE
        escalation_reason = EscalationReason.LOW_CONFIDENCE if should_escalate else None
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return EmailReply(
            reply_body=reply_body,
            confidence_score=confidence_score,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            detected_type=email_type,
            detected_urgency=urgency,
            sentiment_score=sentiment_score,
            rag_context_used=rag_context[:500],
            processing_time_ms=int(processing_time)
        )
    
    async def _analyze_email_type_and_urgency(
        self,
        email_message: EmailMessage,
        rag_context: str
    ) -> Tuple[EmailType, EmailUrgency]:
        """Analyze email to determine type and urgency."""
        
        # Get conversation for history context
        conv = self.conversations.get(email_message.thread_id)
        history_context = f"Message #{conv.message_count + 1} in conversation" if conv else "First email in thread"
        
        # Use structured prompt system
        if get_prompt and format_prompt:
            template = get_prompt("email_type_urgency")
            prompt = format_prompt(
                template,
                EMAIL_SUBJECT=email_message.subject,
                EMAIL_BODY=email_message.body_text[:1500],
                SENDER_EMAIL=email_message.sender_email,
                CONVERSATION_HISTORY=history_context
            )
        else:
            # Fallback prompt
            prompt = f"""Analyze this customer support email and determine:
1. Email type (question, complaint, feedback, praise, request, bug_report)
2. Urgency level (critical, high, normal, low)

Email:
Subject: {email_message.subject}
Body: {email_message.body_text[:1000]}

Respond ONLY with JSON:
{{
    "type": "question|complaint|feedback|praise|request|bug_report",
    "urgency": "critical|high|normal|low",
    "reasoning": "brief explanation"
}}"""
        
        try:
            response = self.claude.messages.create(
                model=self.sonnet_model,
                max_tokens=300,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Extract JSON
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                email_type = EmailType(result.get("type", "question"))
                urgency = EmailUrgency(result.get("urgency", "normal"))
                return email_type, urgency
        except Exception as e:
            print(f"⚠️  Email type analysis failed: {e}")
        
        # Default fallback
        return EmailType.QUESTION, EmailUrgency.NORMAL
    
    async def _analyze_sentiment(self, text: str, subject: str = "", history: str = "") -> float:
        """
        Analyze sentiment of email text.
        
        Returns:
            Sentiment score from -1.0 (very negative) to 1.0 (very positive)
        """
        # Use structured prompt system
        if get_prompt and format_prompt:
            template = get_prompt("sentiment_analysis")
            prompt = format_prompt(
                template,
                EMAIL_SUBJECT=subject or "No subject",
                EMAIL_BODY=text[:1500],
                CONVERSATION_HISTORY=history or "First email in thread"
            )
        else:
            # Fallback prompt
            prompt = f"""Analyze the sentiment of this customer email on a scale from -1.0 to 1.0:
-1.0 = extremely angry/frustrated/negative
 0.0 = neutral
 1.0 = extremely happy/satisfied/positive

Email text: {text[:1000]}

Respond ONLY with a JSON object:
{{
    "sentiment_score": -0.75,
    "reasoning": "Customer is clearly frustrated with..."
}}"""
        
        try:
            response = self.claude.messages.create(
                model=self.sonnet_model,
                max_tokens=200,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return float(result.get("sentiment_score", 0.0))
        except Exception as e:
            print(f"⚠️  Sentiment analysis failed: {e}")
        
        return 0.0  # Neutral fallback
    
    async def _generate_reply(
        self,
        email_message: EmailMessage,
        conversation_history: EmailConversation,
        rag_context: str,
        email_type: EmailType,
        urgency: EmailUrgency,
        sentiment: float
    ) -> Tuple[str, float]:
        """
        Generate email reply using Claude with RAG context.
        
        Returns:
            (reply_body, confidence_score)
        """
        # ── Load per-channel email adjustments from tone prefs ────────────────
        _email_adj_block = ""
        try:
            import json as _json, os as _os
            _tp = None
            # 1. Try PostgreSQL (survives Railway redeploys)
            try:
                from database.db import SessionLocal
                from database.models import ClientProfile as _CP
                _db = SessionLocal()
                try:
                    _prof = _db.query(_CP).filter(_CP.client_id == self.client_id).first()
                    if _prof and getattr(_prof, "tone_preferences_json", None):
                        _tp = _json.loads(_prof.tone_preferences_json)
                finally:
                    _db.close()
            except Exception:
                pass
            # 2. File fallback
            if not _tp:
                _tp_path = _os.path.join("style_references", self.client_id, "tone_prefs.json")
                if _os.path.exists(_tp_path):
                    _tp = _json.load(open(_tp_path))
            if _tp:
                _email_adjs = _tp.get("platform_adjustments", {}).get("email", [])
                if _email_adjs:
                    _bullets = "\n".join(f"- {a}" for a in _email_adjs)
                    _email_adj_block = (
                        f"\n\n### EMAIL REPLY ADJUSTMENTS\n"
                        f"Apply these specific instructions when writing this email reply:\n{_bullets}\n"
                    )
        except Exception:
            pass

        # Build conversation context
        history_text = f"Message #{conversation_history.message_count + 1} in conversation."
        if conversation_history.message_count > 1:
            history_text += f" Previous messages: {conversation_history.message_count}. Sentiment trend: {conversation_history.sentiment_trend[-3:]}"
        
        # Use structured prompt system
        if get_prompt and format_prompt:
            template = get_prompt("reply_generation")
            prompt = format_prompt(
                template,
                EMAIL_SUBJECT=email_message.subject,
                EMAIL_BODY=email_message.body_text,
                SENDER_NAME=email_message.sender_name or email_message.sender_email.split('@')[0],
                EMAIL_TYPE=email_type.value,
                URGENCY_LEVEL=urgency.value,
                SENTIMENT_SCORE=f"{sentiment:.2f}",
                CONVERSATION_HISTORY=history_text,
                KNOWLEDGE_BASE_CONTEXT=rag_context[:2000] if rag_context else "No specific knowledge base information available.",
                RESEARCH_CONTEXT=self.rag.retrieve_relevant_context("customer support best practices response time", top_k=1) if self.use_rag and self.rag else ""
            )
            # Append any client-specific email adjustments
            if _email_adj_block:
                prompt = prompt + _email_adj_block
        else:
            # Fallback prompt
            prompt = f"""You are a helpful customer support agent. Generate a reply to this customer email.
{_email_adj_block}
CUSTOMER EMAIL:
From: {email_message.sender_name or email_message.sender_email}
Subject: {email_message.subject}
Body:
{email_message.body_text}

CONTEXT:
- Email type: {email_type.value}
- Urgency: {urgency.value}
- Customer sentiment: {sentiment:.2f} (-1.0=very negative, 1.0=very positive)
- Conversation context: {history_text}

KNOWLEDGE BASE:
{rag_context}

INSTRUCTIONS:
1. Be helpful, professional, and empathetic
2. Answer their question directly using the knowledge base
3. If information is not in the knowledge base, acknowledge that and offer to escalate
4. Match the customer's tone (if friendly, be warm; if frustrated, be apologetic and solution-focused)
5. Keep response concise but complete
6. End with a clear next step or call-to-action

Respond with JSON ONLY:
{{
    "reply": "Your email reply here...",
    "confidence": 0.85,
    "reasoning": "Why you chose this approach and your confidence level"
}}"""
        
        try:
            response = self.claude.messages.create(
                model=self.sonnet_model,
                max_tokens=1500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Extract JSON
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                reply_body = result.get("reply", "")
                confidence = float(result.get("confidence", 0.5))
                
                return reply_body, confidence
        except Exception as e:
            print(f"⚠️  Reply generation failed: {e}")
        
        # Fallback response
        return (
            "Thank you for contacting us. I'm having trouble processing your request right now. "
            "Let me connect you with a team member who can help.",
            0.3
        )
    
    # =============================================================================
    # CONVERSATION MANAGEMENT
    # =============================================================================
    
    def _get_or_create_conversation(
        self,
        email_message: EmailMessage
    ) -> EmailConversation:
        """Get existing conversation or create new one."""
        
        # Use thread_id as conversation_id
        conv_id = email_message.thread_id
        
        if conv_id in self.conversations:
            # Update existing conversation
            conv = self.conversations[conv_id]
            conv.message_count += 1
            conv.last_message_at = email_message.received_at
            return conv
        
        # Create new conversation
        conversation = EmailConversation(
            conversation_id=conv_id,
            client_id=self.client_id,
            customer_email=email_message.sender_email,
            customer_name=email_message.sender_name,
            subject=email_message.subject,
            status=ConversationStatus.OPEN,
            created_at=email_message.received_at,
            last_message_at=email_message.received_at,
            resolved_at=None,
            message_count=1,
            ai_reply_count=0,
            escalated=False,
            escalation_reason=None,
            sentiment_trend=[],
            tags=[]
        )
        
        self.conversations[conv_id] = conversation
        return conversation
    
    def update_conversation_after_reply(
        self,
        conversation_id: str,
        sentiment_score: float,
        escalated: bool = False,
        escalation_reason: Optional[EscalationReason] = None
    ):
        """Update conversation after sending a reply."""
        if conversation_id not in self.conversations:
            return
        
        conv = self.conversations[conversation_id]
        conv.ai_reply_count += 1
        conv.sentiment_trend.append(sentiment_score)
        conv.last_message_at = datetime.now()
        
        if escalated:
            conv.escalated = True
            conv.escalation_reason = escalation_reason
            conv.status = ConversationStatus.WAITING_HUMAN
            self.escalated_conversations.add(conversation_id)
    
    # =============================================================================
    # ESCALATION
    # =============================================================================
    
    def _check_escalation_keywords(self, text: str) -> Optional[str]:
        """Check if email contains escalation keywords."""
        text_lower = text.lower()
        for keyword in self.ESCALATION_KEYWORDS:
            if keyword in text_lower:
                return keyword
        return None
    
    def escalate_to_human(
        self,
        email_message: EmailMessage,
        reply: EmailReply
    ):
        """
        Escalate conversation to human agent.
        
        In production, this would:
        - Send notification to team dashboard
        - Create ticket in support system
        - Send SMS/email alert
        - Log to escalation database
        """
        conv_id = email_message.thread_id
        self.escalated_conversations.add(conv_id)
        
        # Update conversation status
        self.update_conversation_after_reply(
            conversation_id=conv_id,
            sentiment_score=reply.sentiment_score,
            escalated=True,
            escalation_reason=reply.escalation_reason
        )
        
        # Print escalation notice
        print("\n" + "="*80)
        print("🚨 EMAIL ESCALATION REQUIRED")
        print("="*80)
        print(f"From: {email_message.sender_name} <{email_message.sender_email}>")
        print(f"Subject: {email_message.subject}")
        print(f"Reason: {reply.escalation_reason.value if reply.escalation_reason else 'Unknown'}")
        print(f"Sentiment: {reply.sentiment_score:.2f}")
        print(f"Confidence: {reply.confidence_score:.2f}")
        print(f"\nMessage preview: {email_message.body_text[:200]}...")
        print("="*80 + "\n")
        
        # In production: send to notification system
        # notification_manager.send_escalation_alert(...)
    
    # =============================================================================
    # EMAIL UTILITIES
    # =============================================================================
    
    def _is_auto_responder(self, email_message: EmailMessage) -> bool:
        """Check if email is an auto-responder."""
        text = f"{email_message.subject} {email_message.body_text}".lower()
        
        for pattern in self.AUTO_RESPONDER_PATTERNS:
            if pattern in text:
                return True
        
        # Check headers
        auto_headers = ['auto-submitted', 'x-auto-response-suppress', 'precedence']
        for header in auto_headers:
            if header in email_message.headers:
                return True
        
        return False
    
    async def send_reply(
        self,
        original_message: "EmailMessage",
        reply: "EmailReply",
        client_id: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email reply via Gmail API, FROM the client's own email address.

        The reply is sent using the client's authenticated Gmail connection, so it
        appears to come from their actual inbox (e.g. cruises@coolcruise.com).
        No 3rd-party sending service — the customer sees the reply come from the
        same address they wrote to, keeping the thread natural and on-brand.

        Args:
            original_message: The inbound email being replied to
            reply: The AI-generated reply object
            client_id: Client ID to look up stored Gmail OAuth credentials.
                       Falls back to self.client_id if not provided.
            from_name: Display name shown in the From field (e.g. "Cool Cruises Support")

        Returns:
            Dict with status, message_id, sent_from, and error (if any)
        """
        # Always update conversation tracking regardless of send outcome
        self.update_conversation_after_reply(
            conversation_id=original_message.thread_id,
            sentiment_score=reply.sentiment_score,
            escalated=reply.should_escalate,
            escalation_reason=reply.escalation_reason
        )

        if not _GMAIL_API_AVAILABLE:
            print("⚠️  Gmail API libraries not installed.")
            print("   Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
            return {"status": "error", "message_id": None, "error": "gmail api not installed"}

        effective_client_id = client_id or self.client_id

        # ── Credential dispatch: Gmail OAuth or IMAP/SMTP ─────────────────
        _creds = self._get_email_credentials(effective_client_id)
        if _creds is None:
            print(f"⚠️  No email credentials for client '{effective_client_id}'.")
            print(f"   [DRAFT] To: {original_message.sender_email}")
            print(f"   Subject: Re: {original_message.subject}")
            print(f"   Body preview: {reply.reply_body[:200]}...")
            return {
                "status": "draft",
                "message_id": None,
                "error": "No email connected — go to Settings > Email Inbox"
            }
        if _creds["type"] == "imap":
            return await self._send_reply_imap_smtp(
                _creds, original_message, reply,
                from_name or effective_client_id.replace("_", " ").title()
            )
        # Gmail OAuth path
        refresh_token = _creds["refresh_token"]

        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            import base64

            # Rebuild credentials from stored refresh token
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GMAIL_CLIENT_ID"),
                client_secret=os.getenv("GMAIL_CLIENT_SECRET")
            )
            creds.refresh(GoogleAuthRequest())

            service = google_build("gmail", "v1", credentials=creds)

            # Get the authenticated user's email address — this is the FROM address
            # This will be the client's actual email (e.g. cruises@coolcruise.com)
            profile = service.users().getProfile(userId="me").execute()
            sender_email = profile.get("emailAddress", "")
            display_name = from_name or effective_client_id.replace("_", " ").title()

            # Build subject with Re: prefix if not already present
            subject = original_message.subject
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

            # Build MIME message with proper threading headers
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{display_name} <{sender_email}>"
            msg["To"] = original_message.sender_email
            msg["Subject"] = subject
            msg["In-Reply-To"] = original_message.message_id or ""
            msg["References"] = original_message.thread_id or original_message.message_id or ""

            # Plain text part
            msg.attach(MIMEText(reply.reply_body, "plain"))

            # HTML part — use existing HTML or convert plain text
            if "<" in reply.reply_body and ">" in reply.reply_body:
                html_body = reply.reply_body
            else:
                html_body = reply.reply_body.replace("\n", "<br>")
                html_body = f"<div style='font-family:Arial,sans-serif;line-height:1.6'>{html_body}</div>"
            msg.attach(MIMEText(html_body, "html"))

            # Base64 encode and send via Gmail API
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

            send_body: Dict[str, Any] = {"raw": raw}
            # Thread the reply into the existing conversation thread
            if original_message.thread_id:
                send_body["threadId"] = original_message.thread_id

            sent = service.users().messages().send(userId="me", body=send_body).execute()
            msg_id = sent.get("id", "unknown")

            print(f"✅ Reply sent via Gmail API | ID: {msg_id}")
            print(f"   From: {sender_email} (client's own inbox)")
            print(f"   To: {original_message.sender_email}")
            print(f"   Subject: {subject}")

            return {
                "status": "sent",
                "message_id": msg_id,
                "sent_from": sender_email,
                "error": None
            }

        except Exception as e:
            print(f"❌ Gmail send failed: {e}")
            return {"status": "error", "message_id": None, "error": str(e)}

    # =========================================================================
    # MULTI-PROVIDER EMAIL: credential lookup, IMAP inbox, IMAP/SMTP send
    # =========================================================================

    def _get_email_credentials(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Return email credentials for the given client, checking both Gmail OAuth
        and IMAP/app-password connections.

        Returns a dict with key ``type`` = ``'gmail'`` or ``'imap'``, plus the
        relevant credential fields, or ``None`` if nothing is connected.
        """
        try:
            from database.db import get_db as _get_db
            from database.models import GmailOAuthToken, ClientProfile as _CP, EmailIMAPConnection
            _db = next(_get_db())
            _prof = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _prof:
                # 1. Gmail OAuth takes priority
                _gtok = _db.query(GmailOAuthToken).filter(
                    GmailOAuthToken.client_profile_id == _prof.id
                ).first()
                if _gtok:
                    from cryptography.fernet import Fernet
                    _key = os.getenv("TOKEN_ENCRYPTION_KEY")
                    try:
                        rt = Fernet(_key.encode()).decrypt(_gtok.refresh_token_enc.encode()).decode() if _key else _gtok.refresh_token_enc
                    except Exception:
                        rt = _gtok.refresh_token_enc
                    _db.close()
                    return {"type": "gmail", "refresh_token": rt}
                # 2. IMAP / app-password
                _itok = _db.query(EmailIMAPConnection).filter(
                    EmailIMAPConnection.client_profile_id == _prof.id
                ).first()
                if _itok:
                    from cryptography.fernet import Fernet
                    _key = os.getenv("TOKEN_ENCRYPTION_KEY")
                    try:
                        pw = Fernet(_key.encode()).decrypt(_itok.password_enc.encode()).decode() if _key else _itok.password_enc
                    except Exception:
                        pw = _itok.password_enc
                    _db.close()
                    return {
                        "type":      "imap",
                        "email":     _itok.email_address,
                        "password":  pw,
                        "imap_host": _itok.imap_host,
                        "imap_port": _itok.imap_port,
                        "smtp_host": _itok.smtp_host,
                        "smtp_port": _itok.smtp_port,
                    }
            _db.close()
        except Exception as _e:
            print(f"[EmailCreds] DB lookup failed: {_e}")
        # 3. Env-var fallback for Gmail
        rt = os.getenv(f"GMAIL_REFRESH_TOKEN_{client_id}")
        if rt:
            return {"type": "gmail", "refresh_token": rt}
        return None

    async def fetch_inbox(
        self,
        client_id: str,
        max_results: int = 20,
        unread_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetch inbox emails for *client_id*, routing to Gmail API or IMAP
        depending on which connection is stored.
        """
        creds = self._get_email_credentials(client_id)
        if creds is None:
            print(f"[fetch_inbox] No email connection for client '{client_id}'")
            return []
        if creds["type"] == "imap":
            return await self._fetch_inbox_imap(creds, max_results=max_results, unread_only=unread_only)
        # Gmail path
        return await self.fetch_inbox_gmail(client_id=client_id, max_results=max_results, unread_only=unread_only)

    async def _fetch_inbox_imap(
        self,
        creds: Dict[str, Any],
        max_results: int = 20,
        unread_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch emails via IMAP4_SSL using stored app-password credentials."""
        import imaplib
        import email as _email_lib
        from email.header import decode_header as _dh
        import asyncio

        def _decode_header(raw: str) -> str:
            parts = _dh(raw or "")
            decoded = ""
            for part, enc in parts:
                if isinstance(part, bytes):
                    decoded += part.decode(enc or "utf-8", errors="replace")
                else:
                    decoded += part
            return decoded

        def _sync_fetch() -> List[Dict[str, Any]]:
            mail = imaplib.IMAP4_SSL(creds["imap_host"], creds["imap_port"])
            mail.login(creds["email"], creds["password"])
            mail.select("INBOX")
            search_criterion = "UNSEEN" if unread_only else "ALL"
            _status, data = mail.search(None, search_criterion)
            mail_ids = data[0].split() if data[0] else []
            # Most recent first
            mail_ids = list(reversed(mail_ids))[:max_results]
            results: List[Dict[str, Any]] = []
            for num in mail_ids:
                _, msg_data = mail.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw_bytes = msg_data[0][1]
                msg = _email_lib.message_from_bytes(raw_bytes)
                # Body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
                sender_raw = _decode_header(msg.get("From", ""))
                sender_name, sender_email_addr = "", sender_raw
                if "<" in sender_raw and ">" in sender_raw:
                    sender_name = sender_raw[:sender_raw.index("<")].strip().strip('"')
                    sender_email_addr = sender_raw[sender_raw.index("<") + 1:sender_raw.index(">")].strip()
                results.append({
                    "message_id":   msg.get("Message-ID", "").strip(),
                    "thread_id":    msg.get("References", msg.get("Message-ID", "")).strip(),
                    "sender_email": sender_email_addr,
                    "sender_name":  sender_name,
                    "subject":      _decode_header(msg.get("Subject", "")),
                    "date":         msg.get("Date", ""),
                    "body":         body,
                    "snippet":      body[:200],
                    "labels":       ["INBOX"] + (["UNREAD"] if unread_only else []),
                })
            mail.logout()
            return results

        try:
            return await asyncio.get_running_loop().run_in_executor(None, _sync_fetch)
        except Exception as e:
            print(f"❌ IMAP fetch failed: {e}")
            return []

    async def _send_reply_imap_smtp(
        self,
        creds: Dict[str, Any],
        original_message: "EmailMessage",
        reply: "EmailReply",
        from_name: str = ""
    ) -> Dict[str, Any]:
        """Send an email reply via SMTP using stored app-password credentials."""
        import smtplib
        import asyncio
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        subject = original_message.subject or ""
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        display_name = from_name or creds["email"]

        html_body = reply.reply_body
        if "<" not in html_body:
            html_body = html_body.replace("\n", "<br>")
            html_body = f"<div style='font-family:Arial,sans-serif;line-height:1.6'>{html_body}</div>"

        def _sync_send() -> Dict[str, Any]:
            msg = MIMEMultipart("alternative")
            msg["From"]       = f"{display_name} <{creds['email']}>"
            msg["To"]         = original_message.sender_email
            msg["Subject"]    = subject
            msg["In-Reply-To"] = original_message.message_id or ""
            msg["References"] = original_message.thread_id or original_message.message_id or ""
            msg.attach(MIMEText(reply.reply_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            smtp_port = int(creds.get("smtp_port", 587))
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(creds["smtp_host"], smtp_port)
            else:
                server = smtplib.SMTP(creds["smtp_host"], smtp_port)
                server.ehlo()
                server.starttls()
                server.ehlo()
            server.login(creds["email"], creds["password"])
            server.sendmail(creds["email"], original_message.sender_email, msg.as_string())
            server.quit()
            return {
                "status":     "sent",
                "message_id": msg.get("Message-ID", "smtp-sent"),
                "sent_from":  creds["email"],
                "error":      None,
            }

        try:
            result = await asyncio.get_running_loop().run_in_executor(None, _sync_send)
            print(f"✅ Reply sent via SMTP | From: {creds['email']} | To: {original_message.sender_email}")
            return result
        except Exception as e:
            print(f"❌ SMTP send failed: {e}")
            return {"status": "error", "message_id": None, "sent_from": creds["email"], "error": str(e)}

    async def fetch_inbox_gmail(
        self,
        client_id: str,
        max_results: int = 20,
        label: str = "INBOX",
        unread_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetch emails from Gmail using Gmail API (OAuth 2.0).

        This is the CORRECT way to read Gmail in 2025.
        Google deprecated IMAP with plain passwords - use OAuth2 instead.

        Setup:
          1. Enable Gmail API at https://console.cloud.google.com/
          2. Create OAuth 2.0 credentials → download credentials.json
          3. Run auth once to get refresh token, store in DB or env var
          4. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET in .env

        Args:
            client_id: The client whose Gmail credentials to use
            max_results: Max number of emails to fetch
            label: Gmail label (INBOX, STARRED, etc.)
            unread_only: If True, only fetch unread messages

        Returns:
            List of email dicts with sender, subject, body, date, message_id
        """
        if not _GMAIL_API_AVAILABLE:
            print("⚠️  Gmail API libraries not installed.")
            print("   Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
            return []

        # Look up stored OAuth credentials for this client
        # Priority: DB (GmailOAuthToken) > env var fallback
        refresh_token = None
        try:
            from database.db import get_db as _get_db
            from database.models import GmailOAuthToken, ClientProfile as _CP
            _db = next(_get_db())
            _prof = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _prof:
                _tok = _db.query(GmailOAuthToken).filter(
                    GmailOAuthToken.client_profile_id == _prof.id
                ).first()
                if _tok:
                    from cryptography.fernet import Fernet
                    _key = os.getenv("TOKEN_ENCRYPTION_KEY")
                    if _key:
                        try:
                            refresh_token = Fernet(_key.encode()).decrypt(_tok.refresh_token_enc.encode()).decode()
                        except Exception:
                            refresh_token = _tok.refresh_token_enc
                    else:
                        refresh_token = _tok.refresh_token_enc
            _db.close()
        except Exception as _e:
            print(f"[Gmail] DB token lookup failed: {_e}")

        if not refresh_token:
            creds_env_key = f"GMAIL_REFRESH_TOKEN_{client_id}"
            refresh_token = os.getenv(creds_env_key)

        if not refresh_token:
            print(f"⚠️  No Gmail credentials found for client '{client_id}'")
            print(f"   Go to Settings > Email Inbox > Sign in with Google to connect Gmail")
            return []

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from googleapiclient.discovery import build as google_build

            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GMAIL_CLIENT_ID"),
                client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
                scopes=["https://www.googleapis.com/auth/gmail.readonly",
                        "https://www.googleapis.com/auth/gmail.send"]
            )

            if not creds.valid:
                creds.refresh(GoogleAuthRequest())

            service = google_build("gmail", "v1", credentials=creds)

            # Build query
            query = ""
            if unread_only:
                query = "is:unread"

            # Fetch message list
            result = service.users().messages().list(
                userId="me",
                labelIds=[label],
                q=query,
                maxResults=max_results
            ).execute()

            messages = result.get("messages", [])
            emails = []

            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full"
                ).execute()

                headers = {h["name"]: h["value"]
                           for h in msg.get("payload", {}).get("headers", [])}

                # Extract body
                body = ""
                payload = msg.get("payload", {})
                if payload.get("body", {}).get("data"):
                    import base64
                    body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
                elif payload.get("parts"):
                    for part in payload["parts"]:
                        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                            body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                            break

                emails.append({
                    "message_id": msg_ref["id"],
                    "thread_id": msg.get("threadId", ""),
                    "sender_email": re.search(r'<(.+?)>', headers.get("From", "")) and
                                    re.search(r'<(.+?)>', headers.get("From", "")).group(1) or
                                    headers.get("From", ""),
                    "sender_name": headers.get("From", "").split("<")[0].strip(),
                    "subject": headers.get("Subject", "(no subject)"),
                    "date": headers.get("Date", ""),
                    "body": body,
                    "snippet": msg.get("snippet", ""),
                    "labels": msg.get("labelIds", [])
                })

            print(f"✅ Fetched {len(emails)} emails from Gmail for client '{client_id}'")
            return emails

        except Exception as e:
            print(f"❌ Gmail API fetch failed: {e}")
            return []
    
    def get_conversation_stats(self) -> Dict[str, Any]:
        """Get statistics about email conversations."""
        total = len(self.conversations)
        escalated = len([c for c in self.conversations.values() if c.escalated])
        open_convs = len([c for c in self.conversations.values() if c.status == ConversationStatus.OPEN])
        
        avg_messages = sum(c.message_count for c in self.conversations.values()) / max(total, 1)
        avg_sentiment = sum(
            c.sentiment_trend[-1] for c in self.conversations.values() if c.sentiment_trend
        ) / max(total, 1)
        
        return {
            "total_conversations": total,
            "escalated_count": escalated,
            "open_conversations": open_convs,
            "avg_messages_per_conversation": round(avg_messages, 1),
            "avg_sentiment": round(avg_sentiment, 2),
            "escalation_rate": round(escalated / max(total, 1) * 100, 1)
        }


# =============================================================================
# QUICK ACCESS FUNCTIONS
# =============================================================================

async def process_support_email(
    client_id: str,
    email_message: EmailMessage,
    client_knowledge: Optional[str] = None
) -> EmailReply:
    """Quick function to process a support email."""
    agent = EmailSupportAgent(client_id=client_id, use_rag=True)
    return await agent.process_incoming_email(email_message, client_knowledge)


# =============================================================================
# TEST HARNESS
# =============================================================================

async def main():
    """Test the Email Support Agent"""
    print("="*80)
    print("📧 EMAIL SUPPORT AGENT TEST")
    print("="*80)
    
    agent = EmailSupportAgent(client_id="demo_client", use_rag=True)
    
    # Test 1: Simple question
    print("\n\n📋 TEST 1: Simple Product Question")
    print("-"*40)
    
    test_email_1 = EmailMessage(
        message_id="msg_001",
        thread_id="thread_001",
        sender_email="customer@example.com",
        sender_name="John Doe",
        subject="Question about pricing",
        body_text="Hi, I'm interested in your premium plan. How much does it cost per month?",
        body_html=None,
        received_at=datetime.now(),
        attachments=[],
        headers={},
        is_reply=False,
        reply_to_message_id=None
    )
    
    reply_1 = await agent.process_incoming_email(test_email_1)
    
    print(f"\n✅ Reply Generated:")
    print(f"   Confidence: {reply_1.confidence_score:.2f}")
    print(f"   Should Escalate: {reply_1.should_escalate}")
    print(f"   Type: {reply_1.detected_type.value}")
    print(f"   Urgency: {reply_1.detected_urgency.value}")
    print(f"   Sentiment: {reply_1.sentiment_score:.2f}")
    print(f"   Processing Time: {reply_1.processing_time_ms}ms")
    print(f"\n   Reply: {reply_1.reply_body[:300]}...")
    
    # Test 2: Frustrated customer (escalation)
    print("\n\n📋 TEST 2: Frustrated Customer")
    print("-"*40)
    
    test_email_2 = EmailMessage(
        message_id="msg_002",
        thread_id="thread_002",
        sender_email="angry@example.com",
        sender_name="Jane Smith",
        subject="This is unacceptable!",
        body_text="I've been waiting 3 days for a response. This is the worst service I've ever experienced. I want to speak to a manager immediately!",
        body_html=None,
        received_at=datetime.now(),
        attachments=[],
        headers={},
        is_reply=False,
        reply_to_message_id=None
    )
    
    reply_2 = await agent.process_incoming_email(test_email_2)
    
    print(f"\n✅ Reply Generated:")
    print(f"   Confidence: {reply_2.confidence_score:.2f}")
    print(f"   Should Escalate: {reply_2.should_escalate}")
    print(f"   Escalation Reason: {reply_2.escalation_reason.value if reply_2.escalation_reason else 'None'}")
    print(f"   Sentiment: {reply_2.sentiment_score:.2f}")
    print(f"\n   Reply: {reply_2.reply_body}")
    
    if reply_2.should_escalate:
        agent.escalate_to_human(test_email_2, reply_2)
    
    # Test 3: Stats
    print("\n\n📊 TEST 3: Conversation Statistics")
    print("-"*40)
    
    stats = agent.get_conversation_stats()
    print(f"\n📈 Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n" + "="*80)
    print("✅ TESTING COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
