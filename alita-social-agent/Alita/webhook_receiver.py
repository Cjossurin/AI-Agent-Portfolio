# webhook_receiver.py
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import PlainTextResponse
from agents.engagement_agent import EngagementAgent
from agents.content_agent import ContentCreationAgent
from agents.conversation_categorizer import ConversationCategorizer
from utils.notification_manager import NotificationManager
from utils.meta_inbox_store import record_message as record_meta_message
from utils.meta_graph import send_instagram_dm as meta_send_instagram_dm
from utils.meta_graph import reply_to_instagram_comment as meta_reply_to_instagram_comment
from utils.meta_graph import send_facebook_dm as meta_send_facebook_dm
from utils.meta_graph import reply_to_facebook_comment as meta_reply_to_facebook_comment
from utils.cross_channel_memory import cross_channel_memory
import uvicorn
import httpx
import os
import asyncio
import random
import re
from dotenv import load_dotenv
import json
from datetime import datetime
from utils.plan_limits import check_limit, increment_usage

load_dotenv()

# ═══════════════════════════════════════════════════════════════════════
# WEBHOOK REQUEST LOGGING (for debugging when webhooks don't arrive)
# ═══════════════════════════════════════════════════════════════════════
WEBHOOK_LOG_FILE = "webhook_requests.log"
WEBHOOK_REQUEST_HISTORY = []  # In-memory for quick access
MAX_HISTORY_SIZE = 50  # Keep last 50 requests

def log_webhook_request(event_type: str, body: dict, status: str = "received"):
    """Log incoming webhook request to both file and memory."""
    timestamp = datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "type": event_type,
        "status": status,
        "body_summary": {
            "object": body.get("object"),
            "entry_count": len(body.get("entry", [])),
            "entry_ids": [e.get("id") for e in body.get("entry", [])],
        }
    }
    
    # Add to in-memory history
    WEBHOOK_REQUEST_HISTORY.append(log_entry)
    if len(WEBHOOK_REQUEST_HISTORY) > MAX_HISTORY_SIZE:
        WEBHOOK_REQUEST_HISTORY.pop(0)
    
    # Write to file
    try:
        with open(WEBHOOK_LOG_FILE, "a") as f:
            f.write(f"\n{timestamp} | {event_type} | {status}\n")
            f.write(f"  Object: {body.get('object')}\n")
            f.write(f"  Entries: {len(body.get('entry', []))}\n")
            for i, entry in enumerate(body.get("entry", [])):
                has_changes = "changes" in entry
                has_messaging = "messaging" in entry
                f.write(f"    Entry {i}: id={entry.get('id')} | changes={has_changes} | messaging={has_messaging}\n")
                if has_changes:
                    for change in entry.get("changes", []):
                        f.write(f"      - field={change.get('field')} item={change.get('value', {}).get('item', 'N/A')}\n")
    except Exception as e:
        print(f"⚠️  Failed to write webhook log: {e}")

router = APIRouter(tags=["Meta Webhooks"])

# Standalone app (created at bottom of file after all routes are defined)
app = None  # Initialized at bottom of file

# === OAuth Token Manager (for user token lookup) ===
_token_manager = None

def get_token_manager():
    """Lazy-load TokenManager for OAuth token lookups."""
    global _token_manager
    if _token_manager is None:
        try:
            from api.token_manager import TokenManager
            _token_manager = TokenManager()
            _token_manager.initialize()
            print("✅ TokenManager loaded for webhook OAuth token routing")
        except Exception as e:
            print(f"⚠️  TokenManager not available: {e}")
            print("   Falling back to env var tokens for webhooks")
    return _token_manager

# === Client Mapping & Agent Cache ===
# Static fallback mapping (used when TokenManager is unavailable)
INSTAGRAM_CLIENT_MAP = {
    "17841474794582911": "default_client"  # Add more mappings as needed
}

# Static fallback mapping for Facebook Page IDs (used when TokenManager is unavailable)
FACEBOOK_CLIENT_MAP = {
    "673651702495432": "default_client"
}

def resolve_client_id(instagram_business_account_id: str) -> str:
    """
    Resolve an Instagram Business Account ID to a client_id.
    
    Priority:
    1. OAuth TokenManager database (dynamic, from user auth)
    2. Static INSTAGRAM_CLIENT_MAP (fallback)
    3. "default_client" (default)
    """
    # Try OAuth database first
    tm = get_token_manager()
    if tm:
        user_id = tm.get_user_by_instagram_id(str(instagram_business_account_id))
        if user_id:
            print(f"🔑 Resolved IG account {instagram_business_account_id} → user {user_id} (OAuth)")
            return user_id
    
    # Fallback to static mapping
    client_id = INSTAGRAM_CLIENT_MAP.get(str(instagram_business_account_id), "default_client")
    print(f"🔑 Resolved IG account {instagram_business_account_id} → {client_id} (static map)")
    return client_id


def resolve_client_id_for_facebook_page(facebook_page_id: str) -> str:
    """Resolve a Facebook Page ID to a client_id using TokenManager or fallback maps."""
    tm = get_token_manager()
    if tm:
        try:
            user_id = tm.get_user_by_facebook_page_id(str(facebook_page_id))
        except Exception:
            user_id = None
        if user_id:
            print(f"🔑 Resolved FB Page {facebook_page_id} → user {user_id} (OAuth)")
            return user_id

    client_id = FACEBOOK_CLIENT_MAP.get(str(facebook_page_id), "default_client")
    print(f"🔑 Resolved FB Page {facebook_page_id} → {client_id} (static map)")
    return client_id

def get_access_token_for_account(instagram_business_account_id: str) -> str:
    """
    Get the correct access token for an Instagram Business Account.
    
    Priority:
    1. OAuth user token from database (if user connected via OAuth)
    2. Server token from env var (fallback)
    """
    tm = get_token_manager()
    if tm:
        token = tm.get_token_by_instagram_id(str(instagram_business_account_id))
        if token:
            print(f"🔑 Using OAuth token for IG account {instagram_business_account_id}")
            return token
    
    # Fallback to env var
    return os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

# EngagementAgent cache per client_id
AGENT_CACHE = {}
CATEGORIZER_CACHE = {}
NOTIFIER_CACHE = {}

def get_agent_for_client(client_id: str):
    if client_id not in AGENT_CACHE:
        AGENT_CACHE[client_id] = EngagementAgent(client_id=client_id)
    return AGENT_CACHE[client_id]

def get_categorizer_for_client(client_id: str):
    if client_id not in CATEGORIZER_CACHE:
        # Initialize optimized categorizer with client_id and RAG integration
        CATEGORIZER_CACHE[client_id] = ConversationCategorizer(client_id=client_id, use_rag=True)
    return CATEGORIZER_CACHE[client_id]

def get_notifier_for_client(client_id: str):
    if client_id not in NOTIFIER_CACHE:
        NOTIFIER_CACHE[client_id] = NotificationManager(client_id=client_id)
    return NOTIFIER_CACHE[client_id]
# === END Client Mapping & Agent Cache ===

# ContentCreationAgent cache per client_id
CONTENT_AGENT_CACHE = {}

def get_content_agent_for_client(client_id: str):
    if client_id not in CONTENT_AGENT_CACHE:
        CONTENT_AGENT_CACHE[client_id] = ContentCreationAgent(client_id=client_id)
    return CONTENT_AGENT_CACHE[client_id]


def _check_reply_quota(client_id: str) -> bool:
    """Return True if the client still has reply quota (or is unlimited).
    Also increments usage_replies_sent on success.
    Returns False when the monthly limit is exhausted."""
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile
        db = SessionLocal()
        profile = db.query(ClientProfile).filter(
            ClientProfile.client_id == client_id
        ).first()
        if not profile:
            db.close()
            return True  # no profile yet → allow (free defaults will kick in later)
        allowed, _msg = check_limit(profile, "replies_sent")
        if allowed:
            increment_usage(profile, "replies_sent", db)
        db.close()
        return allowed
    except Exception as e:
        print(f"⚠️  Reply quota check failed ({e}); allowing reply")
        return True

def _auto_reply_delay_seconds() -> int:
    """Max random delay before replying. Defaults to 0 for responsiveness."""
    try:
        return max(0, int(os.getenv("AUTO_REPLY_MAX_DELAY_SECONDS", "0")))
    except Exception:
        return 0

# === SCENE 1: START (Conversation State & Escalation Logic) ===
# Global sets to track processed comment and message IDs for idempotency
processed_comments = set()
processed_messages = set()

# Global set to track escalated conversations (sender IDs that requested a human)
escalated_conversations = set()

# === SCENE 2: START (ESCALATION_KEYWORDS) ===
# Keywords that trigger human escalation (be specific to avoid false positives)
ESCALATION_KEYWORDS = [
    "human", "agent", "person", "real person", "real human",
    "speak to someone", "talk to someone", "live person", "live agent",
    "representative"
    # Removed: 'support', 'help me', 'speak with' (too broad)
]
# === SCENE 2: END (ESCALATION_KEYWORDS) ===

def check_escalation_keywords(text: str) -> bool:
    """Check if message contains keywords requesting a human."""
    text_lower = text.lower()
    for keyword in ESCALATION_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def log_escalation(sender_id: str, message_text: str):
    """Log escalation to console and file for notification."""
    timestamp = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Print to terminal with attention-grabbing formatting
    print("\n" + "🚨" * 30)
    print("🚨 HUMAN ESCALATION REQUESTED 🚨")
    print(f"🚨 Time: {timestamp}")
    print(f"🚨 Sender ID: {sender_id}")
    print(f"🚨 Message: {message_text}")
    print("🚨 ACTION REQUIRED: Respond manually to this conversation!")
    print("🚨" * 30 + "\n")
    
    # Also write to a file for persistent tracking
    try:
        with open("escalations.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"ESCALATION REQUEST\n")
            f.write(f"Time: {timestamp}\n")
            f.write(f"Sender ID: {sender_id}\n")
            f.write(f"Message: {message_text}\n")
            f.write(f"Status: PENDING - Needs manual response\n")
            f.write(f"{'='*60}\n")
    except Exception as e:
        print(f"⚠️ Could not write to escalations.txt: {e}")
# === SCENE 1: END (Conversation State & Escalation Logic) ===

async def send_instagram_dm(recipient_id: str, text: str, account_id: str = None):
    """Send a DM to an Instagram user using the Graph API (Meta-only)."""
    try:
        ig_business_id = str(account_id or "").strip() or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        if not ig_business_id:
            print("❌ Missing Instagram business account id for DM send")
            return {"error": "Missing business account id"}
        result = await meta_send_instagram_dm(
            ig_business_account_id=ig_business_id,
            recipient_id=str(recipient_id),
            text=str(text or ""),
        )
        if "error" in result:
            error_msg = (result.get("error") or {}).get("error", {}).get("message") if isinstance(result.get("error"), dict) else str(result.get("error"))
            print(f"❌ Failed to send DM to {recipient_id}: {error_msg}")
        else:
            print(f"✅ Successfully sent DM to {recipient_id}")
        return result
    except Exception as e:
        print(f"❌ Error sending DM: {e}")
        return {"error": str(e)}


async def send_facebook_dm(recipient_id: str, text: str, page_id: str):
    """Send a Facebook Messenger DM from a Page using Graph API (Meta-only)."""
    try:
        fb_page_id = str(page_id or "").strip() or os.getenv("FACEBOOK_PAGE_ID", "")
        if not fb_page_id:
            print("❌ Missing Facebook Page id for DM send")
            return {"error": "Missing page id"}

        result = await meta_send_facebook_dm(
            page_id=fb_page_id,
            recipient_id=str(recipient_id),
            text=str(text or ""),
        )
        if "error" in result:
            # Extract error details from Graph API response
            error_data = result.get("error", {})
            if isinstance(error_data, dict):
                if "error" in error_data:  # Nested error structure
                    inner_error = error_data["error"]
                    error_msg = inner_error.get("message", "Unknown error")
                    error_code = inner_error.get("code", "N/A")
                    error_type = inner_error.get("type", "N/A")
                else:  # Single-level error
                    error_msg = error_data.get("message", str(error_data))
                    error_code = error_data.get("code", "N/A")
                    error_type = error_data.get("type", "N/A")
                print(f"❌ Failed to send Facebook DM to {recipient_id}:")
                print(f"   Error: {error_msg}")
                print(f"   Code: {error_code}")
                print(f"   Type: {error_type}")
                print(f"   Full response: {result}")
            else:
                print(f"❌ Failed to send Facebook DM to {recipient_id}: {error_data}")
        else:
            print(f"✅ Successfully sent Facebook DM to {recipient_id}")
        return result
    except Exception as e:
        print(f"❌ Error sending Facebook DM: {e}")
        return {"error": str(e)}


async def reply_to_facebook_comment(comment_id: str, response: str, page_id: str):
    """Reply to a Facebook comment using Graph API (Meta-only)."""
    try:
        fb_page_id = str(page_id or "").strip() or os.getenv("FACEBOOK_PAGE_ID", "")
        if not fb_page_id:
            print("❌ Missing Facebook Page id for comment reply")
            return {"error": "Missing page id"}

        print(f"📤 Replying to Facebook comment {comment_id} with: {response[:100]}...")
        result = await meta_reply_to_facebook_comment(
            page_id=fb_page_id,
            comment_id=str(comment_id),
            text=str(response or ""),
        )
        if "error" in result:
            # Extract error details from Graph API response
            error_data = result.get("error", {})
            if isinstance(error_data, dict):
                if "error" in error_data:  # Nested error structure
                    inner_error = error_data["error"]
                    error_msg = inner_error.get("message", "Unknown error")
                    error_code = inner_error.get("code", "N/A")
                    error_type = inner_error.get("type", "N/A")
                else:  # Single-level error
                    error_msg = error_data.get("message", str(error_data))
                    error_code = error_data.get("code", "N/A")
                    error_type = error_data.get("type", "N/A")
                print(f"❌ Failed to reply to Facebook comment {comment_id}:")
                print(f"   Error: {error_msg}")
                print(f"   Code: {error_code}")
                print(f"   Type: {error_type}")
                print(f"   Full response: {result}")
            else:
                print(f"❌ Failed to reply to Facebook comment {comment_id}: {error_data}")
        else:
            print(f"✅ Successfully replied to Facebook comment {comment_id}")
        return result
    except Exception as e:
        print(f"❌ Error replying to Facebook comment: {e}")
        return {"error": str(e)}

# Auto-load knowledge from knowledge_base.txt on startup
def load_knowledge_on_startup():
    """Load knowledge from knowledge_base.txt into RAG if file exists."""
    knowledge_file = "knowledge_base.txt"
    if os.path.exists(knowledge_file):
        print(f"\n📚 Loading knowledge from {knowledge_file}...")
        try:
            with open(knowledge_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create a temporary agent to load knowledge into RAG
            temp_agent = get_agent_for_client("default_client")
            
            # Split by document separators and add each
            docs = content.split("="*60)
            added_count = 0
            for doc in docs:
                if doc.strip() and "Source:" in doc:
                    temp_agent.rag.add_knowledge(text=doc.strip(), client_id="default_client")
                    added_count += 1
            
            print(f"✅ Loaded {added_count} documents into knowledge base")
        except Exception as e:
            print(f"⚠️  Failed to load knowledge: {e}")
    else:
        print(f"ℹ️  No {knowledge_file} found. Run 'python ingest.py' to create it.")

# Load knowledge when server starts
load_knowledge_on_startup()

@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == os.getenv("VERIFY_TOKEN"):
        print("✅ Webhook verified!")
        # Meta expects the raw challenge string in the response body (not JSON).
        return PlainTextResponse(content=str(challenge or ""), status_code=200)
    return PlainTextResponse(content="Verification failed", status_code=403)

async def reply_to_instagram_comment(comment_id: str, response: str, account_id: str = None):
    """Reply to Instagram comment using Graph API (Meta-only)."""
    try:
        ig_business_id = str(account_id or "").strip() or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        if not ig_business_id:
            print("❌ Missing Instagram business account id for comment reply")
            return {"error": "Missing business account id"}

        print(f"📤 Replying to comment {comment_id} with: {response}")
        result = await meta_reply_to_instagram_comment(
            ig_business_account_id=ig_business_id,
            comment_id=str(comment_id),
            text=str(response or ""),
        )
        if "error" in result:
            error_msg = (result.get("error") or {}).get("error", {}).get("message") if isinstance(result.get("error"), dict) else str(result.get("error"))
            print(f"❌ Failed to reply to comment {comment_id}: {error_msg}")
        else:
            print(f"✅ Successfully replied to comment {comment_id}")
        return result
    except Exception as e:
        print(f"❌ Error replying to Instagram comment: {e}")
        return {"error": str(e)}

# === SCENE 2: START (handle_comment) ===
async def handle_comment(comment_data: dict, client_id: str):
    """Handle Instagram comment by generating and posting a reply."""
    try:
        comment_text = comment_data.get("text", "")
        comment_id = comment_data.get("id", "")
        
        print(f"💬 Processing comment: {comment_text}")
        
        # Generate AI response
        agent = get_agent_for_client(client_id)
        response = await agent.generate_response(comment_text)
        print(f"🤖 AI Response: {response}")
        
        # Reply to Instagram comment
        business_account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        await reply_to_instagram_comment(comment_id, response, account_id=business_account_id)
        
        return {"success": True, "response": response}
    except Exception as e:
        print(f"❌ Error handling comment: {e}")
        return {"success": False, "error": str(e)}
# === SCENE 2: END (handle_comment) ===

@router.post("/webhook")
async def receive_webhook(request: Request):
    # Capture request timestamp
    request_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # Debug: Print headers
    print("\n" + "="*60)
    print(f"🔔 POST WEBHOOK RECEIVED - {request_time}")
    print("="*60)
    print("\n📋 HEADERS:")
    for header, value in request.headers.items():
        print(f"   {header}: {value}")
    
    # Get and print full body
    try:
        body = await request.json()
        print(f"\n📦 FULL REQUEST BODY:")
        print(f"{body}")
        print(f"\n🔍 OBJECT TYPE: {body.get('object')}")
        print(f"🔍 HAS ENTRY: {bool(body.get('entry'))}")
        if body.get('entry'):
            for i, entry in enumerate(body.get('entry', [])):
                print(f"🔍 ENTRY {i}: {entry}")
        print("="*60 + "\n")
        
        # Log the request
        log_webhook_request(body.get('object', 'unknown'), body, "received")
    except Exception as e:
        raw_body = await request.body()
        print(f"\n❌ JSON PARSE ERROR: {e}")
        print(f"📦 RAW BODY: {raw_body.decode('utf-8')}")
        print("="*60 + "\n")
        log_webhook_request("error", {"error": str(e), "raw": raw_body.decode('utf-8')}, "json_error")
        return {"status": "json_error", "error": str(e)}
    
    from utils.auto_reply_settings import is_enabled as _auto_reply_enabled

    # === Instagram webhooks (Meta-only) ===
    if body.get("object") == "instagram":
        print("✅ Instagram webhook detected")
        default_business_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        for entry in body.get("entry", []):
            my_business_id = str(entry.get("id") or default_business_id or "").strip()
            if not my_business_id:
                print("⚠️  Missing Instagram business account id (entry.id / env)")
                continue

            # Log what keys the entry contains for debugging
            entry_keys = list(entry.keys())
            has_changes = "changes" in entry
            has_messaging = "messaging" in entry
            print(f"📂 Entry keys: {entry_keys} | changes={has_changes} | messaging={has_messaging}")
            if not has_changes and not has_messaging:
                print(f"⚠️ Entry has NEITHER 'changes' nor 'messaging' — nothing to process. Keys: {entry_keys}")

            reply_account_id = my_business_id
            client_id = resolve_client_id(my_business_id)
            agent = get_agent_for_client(client_id)
            content_agent = get_content_agent_for_client(client_id)
            # --- Handle Comments ---
            # Only respond to incoming comments (reactive, not proactive)
            if "changes" in entry:
                for change in entry.get("changes", []):
                    field = change.get("field")
                    if field != "comments":
                        print(f"ℹ️ Skipping non-comment change field: '{field}'")
                        continue
                    print("💬 Comment event detected")

                    if not _auto_reply_enabled("comment", "instagram"):
                        print("⏸️ Instagram comment auto-reply is OFF; skipping")
                        continue

                    value = change.get("value", {}) or {}
                    comment_id = value.get("id")
                    text = value.get("text") or ""
                    sender_id = (value.get("from") or {}).get("id")

                    # Debug logging to understand comment structure
                    print(f"📋 Comment Details - ID: {comment_id}, Sender: {sender_id}, Text: {text}")
                    print(f"📋 Full value object: {value}")

                    if not comment_id:
                        continue

                    # Prevent self-reply
                    if str(sender_id or "") == str(my_business_id or ""):
                        print(f"🛑 Ignoring comment from self ({sender_id})")
                        continue
                    # Idempotency
                    if comment_id in processed_comments:
                        print(f"🚫 Skipping duplicate comment {comment_id}")
                        continue
                    processed_comments.add(comment_id)

                    # Normalize text: remove @mentions and extra whitespace for command detection
                    normalized_text = text.lower().strip()
                    # Remove @mentions (e.g., "@nexarilyai resume bot" -> "resume bot")
                    normalized_text = re.sub(r"@\w+\s*", "", normalized_text).strip()

                    # Check if this sender's conversation is already escalated
                    print(f"🔍 Checking escalation status for sender {sender_id}. Currently escalated: {sender_id in escalated_conversations}")
                    print(f"🔍 All escalated conversations: {escalated_conversations}")
                    print(f"🔍 Original text: '{text}' | Normalized: '{normalized_text}'")

                    # Check for 'resume bot' command FIRST, regardless of escalation status
                    # This allows users to resume from anywhere (new comment or reply)
                    if "resume bot" in normalized_text or normalized_text == "resume bot":
                        if sender_id in escalated_conversations:
                            escalated_conversations.discard(sender_id)
                            print(f"✅ User {sender_id} resumed bot responses via comment")
                            print(f"✅ Updated escalated conversations: {escalated_conversations}")
                            await reply_to_instagram_comment(
                                comment_id,
                                "Bet, I'm back! 🙌 What you need help with?",
                                account_id=reply_account_id,
                            )
                        else:
                            print(f"ℹ️ User {sender_id} sent 'resume bot' but wasn't escalated. Already active!")
                            await reply_to_instagram_comment(
                                comment_id,
                                "I'm already here! 👋 What's up?",
                                account_id=reply_account_id,
                            )
                        continue  # Don't process "resume bot" as a regular question

                    # ── Escalation gate: skip if this sender is already handled by a human ──
                    if sender_id in escalated_conversations:
                        print(f"⏸️ Skipping automated reply - sender {sender_id} is escalated to human")
                        continue

                    # === SCENE 1: START (Escalation Message Generation) ===
                    # Check if user is requesting a human (use normalized text to catch @mentions)
                    if check_escalation_keywords(normalized_text):
                        print(f"🚨 Human escalation detected in comment from {sender_id}")
                        escalated_conversations.add(sender_id)
                        log_escalation(sender_id, text)
                        # Use EngagementAgent to generate escalation message in brand style
                        escalation_prompt = (
                            "Let the user know a human will respond soon, but do it in our brand's friendly, conversational style. "
                            "Add: 'If you want to continue with automated help, just reply with resume bot.'"
                        )
                        escalation_message = await agent.generate_response(escalation_prompt, sender_id=sender_id)
                        await reply_to_instagram_comment(comment_id, escalation_message, account_id=reply_account_id)
                        continue
                    # === SCENE 1: END (Escalation Message Generation) ===

                    print(f"💬 Processing comment: {text}")

                    # ── Plan gate: check reply quota ──
                    if not _check_reply_quota(client_id):
                        print(f"⛔ Reply quota exhausted for {client_id}; skipping IG comment reply")
                        continue

                    # === CATEGORIZATION & NOTIFICATION START ===
                    categorizer = get_categorizer_for_client(client_id)
                    notifier = get_notifier_for_client(client_id)

                    category_result = categorizer.categorize_message(
                        message=text,
                        context=f"Instagram comment from {sender_id}",
                        sender_id=sender_id
                    )

                    print(f"📊 Conversation categorized as: {category_result.category} (priority: {category_result.priority})")

                    # Send notification if required
                    if category_result.requires_notification:
                        _snippet = (text[:120] + "...") if len(text) > 120 else text
                        await notifier.send_notification(
                            notification_type=category_result.category.lower(),
                            title=f"Instagram Comment — {category_result.category.replace('_', ' ').title()}",
                            message=f"{_snippet}",
                            priority=category_result.priority,
                            metadata={
                                "sender_id": sender_id,
                                "platform": "instagram",
                                "message_type": "comment",
                                "category": category_result.category,
                                "confidence": category_result.confidence,
                                "action_url": "/comments/dashboard",
                                "action_label": "View Comment",
                                "action_type": "internal_link",
                            }
                        )
                    # === CATEGORIZATION & NOTIFICATION END ===

                    max_delay = _auto_reply_delay_seconds()
                    if max_delay:
                        delay = random.randint(0, max_delay)
                        print(f"⏰ Waiting {delay} seconds before replying...")
                        await asyncio.sleep(delay)

                    # ── Cross-channel memory: record incoming comment + fetch context ──
                    _cc_context = ""
                    try:
                        _post_id = value.get("media", {}).get("id") or value.get("post_id")
                        cross_channel_memory.add_event(
                            client_id=client_id,
                            sender_id=str(sender_id or ""),
                            channel="comment",
                            direction="incoming",
                            text=text,
                            post_id=_post_id,
                            message_id=comment_id,
                        )
                        _cc_context = cross_channel_memory.get_context_for_prompt(client_id, str(sender_id or ""))
                    except Exception as _cce:
                        print(f"⚠️  cross_channel_memory error (comment in): {_cce}")

                    # Route through ContentCreationAgent → EngagementAgent pipeline
                    # (RAG + guardrails + style matching + cross-channel + conversation memory)
                    response = await content_agent.generate_engagement_reply(
                        message=text,
                        sender_id=sender_id,
                        platform="instagram",
                        cross_channel_context=_cc_context,
                    )
                    print(f"🤖 AI Response: {response}")

                    # Record outgoing comment reply
                    try:
                        cross_channel_memory.add_event(
                            client_id=client_id,
                            sender_id=str(sender_id or ""),
                            channel="comment",
                            direction="outgoing",
                            text=response,
                        )
                    except Exception as _cce:
                        print(f"⚠️  cross_channel_memory error (comment out): {_cce}")

                    await reply_to_instagram_comment(comment_id, response, account_id=reply_account_id)
            # === SCENE 2: START (handle_dm) ===
            # --- Handle DMs (Direct Messages) ---
            if "messaging" in entry:
                for event in entry.get("messaging", []):
                    # ── Detect event type and skip non-message events ──
                    if "message_edit" in event:
                        print(f"📝 Skipping message_edit event (mid={event['message_edit'].get('mid','?')}, num_edit={event['message_edit'].get('num_edit','?')})")
                        continue
                    if "read" in event:
                        print(f"👁️ Skipping read receipt event")
                        continue
                    if "delivery" in event:
                        print(f"📬 Skipping delivery receipt event")
                        continue
                    if "reaction" in event:
                        print(f"❤️ Skipping reaction event")
                        continue
                    if "postback" in event:
                        print(f"🔙 Skipping postback event")
                        continue
                    if "referral" in event:
                        print(f"🔗 Skipping referral event")
                        continue
                    if "message" not in event:
                        # Completely unknown event type – log keys for debugging
                        print(f"❓ Skipping unknown messaging event. Keys: {list(event.keys())}")
                        continue

                    # ── We have an actual message event ──
                    print(f"📨 ACTUAL MESSAGE EVENT received!")

                    sender_id = event.get("sender", {}).get("id")
                    message = event.get("message", {})
                    message_text = message.get("text", "")
                    attachments = message.get("attachments", [])
                    message_id = message.get("mid")

                    # Check for echo (messages sent BY the page, not TO the page)
                    if message.get("is_echo"):
                        print(f"🔄 Skipping echo message (sent by page, mid={message_id})")
                        continue

                    print(f"📨 Message from {sender_id}: {message_text or '[no text]'} (mid={message_id})")

                    # Persist inbound to Meta inbox store (for UI)
                    try:
                        inbound_text = message_text or ("[Attachment]" if attachments else "")
                        record_meta_message(
                            platform="instagram",
                            business_account_id=my_business_id,
                            participant_id=str(sender_id or ""),
                            direction="incoming",
                            text=inbound_text,
                            message_id=message_id,
                        )
                    except Exception as _e:
                        pass

                    if not _auto_reply_enabled("dm", "instagram"):
                        print("⏸️ Instagram DM auto-reply is OFF; skipping")
                        continue
                    # Only process if message_id exists
                    if not message_id:
                        continue
                    # Prevent self-reply
                    if sender_id == my_business_id:
                        print(f"🛑 Ignoring DM from self ({sender_id})")
                        continue
                    # Idempotency
                    if message_id in processed_messages:
                        print(f"🚫 Skipping duplicate DM {message_id}")
                        continue
                    processed_messages.add(message_id)
                    # Resolve client_id for this business account (for DMs)
                    client_id = resolve_client_id(my_business_id)
                    agent = get_agent_for_client(client_id)
                    content_agent = get_content_agent_for_client(client_id)
                    # === SCENE 2: START (handle_mention) ===
                    # Handle Story Mention/Attachment (no text, but has attachments)
                    if (not message_text or message_text.strip() == "") and attachments:
                        print(f"📸 Received story mention/attachment from {sender_id}.")
                        # Add human-like delay before replying to Story Mention
                        delay = random.randint(30, 60)
                        print(f"⏳ Waiting {delay} seconds before replying to Story Mention...")
                        await asyncio.sleep(delay)
                        out_text = "Thanks for the mention! 🔥 We'll check it out."
                        await send_instagram_dm(sender_id, out_text, account_id=reply_account_id)
                        try:
                            record_meta_message(
                                platform="instagram",
                                business_account_id=my_business_id,
                                participant_id=str(sender_id or ""),
                                direction="outgoing",
                                text=out_text,
                            )
                        except Exception:
                            pass
                        continue
                    # === SCENE 2: END (handle_mention) ===
                    # Handle normal text DMs
                    if message_text:
                        # Normalize text: remove @mentions and extra whitespace for command detection
                        normalized_dm_text = message_text.lower().strip()
                        normalized_dm_text = re.sub(r'@\w+\s*', '', normalized_dm_text).strip()
                        
                        print(f"🔍 DM - Original: '{message_text}' | Normalized: '{normalized_dm_text}'")
                        
                        # Check for 'resume bot' command FIRST, regardless of escalation status
                        if "resume bot" in normalized_dm_text or normalized_dm_text == "resume bot":
                            if sender_id in escalated_conversations:
                                escalated_conversations.discard(sender_id)
                                print(f"✅ User {sender_id} resumed bot responses via DM")
                                out_text = "Bet, I'm back! 🙌 What you need help with?"
                                await send_instagram_dm(sender_id, out_text, account_id=reply_account_id)
                                try:
                                    record_meta_message(
                                        platform="instagram",
                                        business_account_id=my_business_id,
                                        participant_id=str(sender_id or ""),
                                        direction="outgoing",
                                        text=out_text,
                                    )
                                except Exception:
                                    pass
                            else:
                                print(f"ℹ️ User {sender_id} sent 'resume bot' but wasn't escalated. Already active!")
                                out_text = "I'm already here! 👋 What's up?"
                                await send_instagram_dm(sender_id, out_text, account_id=reply_account_id)
                                try:
                                    record_meta_message(
                                        platform="instagram",
                                        business_account_id=my_business_id,
                                        participant_id=str(sender_id or ""),
                                        direction="outgoing",
                                        text=out_text,
                                    )
                                except Exception:
                                    pass
                            continue  # Don't process "resume bot" as a regular question
                        
                        # Check if this conversation is already escalated
                        if sender_id in escalated_conversations:
                            print(f"⏸️ Skipping automated response - conversation {sender_id} is escalated to human")
                            continue
                        
                        # === SCENE 1: START (Escalation Message Generation) ===
                        # Check if user is requesting a human
                        if check_escalation_keywords(message_text):
                            print(f"🚨 Human escalation detected from {sender_id}")
                            escalated_conversations.add(sender_id)
                            log_escalation(sender_id, message_text)
                            # Use EngagementAgent to generate escalation message in brand style
                            escalation_prompt = (
                                "Let the user know a human will respond soon, but do it in our brand's friendly, conversational style. "
                                "Add: 'If you want to continue with automated help, just reply with resume bot.'"
                            )
                            escalation_message = await agent.generate_response(escalation_prompt, sender_id=sender_id)
                            await send_instagram_dm(sender_id, escalation_message, account_id=reply_account_id)
                            try:
                                record_meta_message(
                                    platform="instagram",
                                    business_account_id=my_business_id,
                                    participant_id=str(sender_id or ""),
                                    direction="outgoing",
                                    text=escalation_message,
                                )
                            except Exception:
                                pass
                            continue
                        # === SCENE 1: END (Escalation Message Generation) ===
                        
                        # Only respond to incoming DMs (reactive, not proactive)
                        # Check for escalation before responding
                        print(f"📩 Processing DM from {sender_id}: {message_text}")

                        # ── Plan gate: check reply quota ──
                        if not _check_reply_quota(client_id):
                            print(f"⛔ Reply quota exhausted for {client_id}; skipping IG DM reply")
                            continue
                        
                        # === CATEGORIZATION & NOTIFICATION START ===
                        # Categorize the conversation
                        categorizer = get_categorizer_for_client(client_id)
                        notifier = get_notifier_for_client(client_id)
                        
                        category_result = categorizer.categorize_message(
                            message=message_text,
                            context=f"Instagram DM from {sender_id}",
                            sender_id=sender_id
                        )
                        
                        print(f"📊 Conversation categorized as: {category_result.category} (priority: {category_result.priority})")
                        
                        # Send notification if required
                        if category_result.requires_notification:
                            _snippet = (message_text[:120] + "...") if len(message_text) > 120 else message_text
                            await notifier.send_notification(
                                notification_type=category_result.category.lower(),
                                title=f"Instagram DM — {category_result.category.replace('_', ' ').title()}",
                                message=f"{_snippet}",
                                priority=category_result.priority,
                                metadata={
                                    "sender_id": sender_id,
                                    "platform": "instagram",
                                    "message_type": "dm",
                                    "category": category_result.category,
                                    "confidence": category_result.confidence,
                                    "action_url": "/inbox/dashboard",
                                    "action_label": "Open Inbox",
                                    "action_type": "internal_link",
                                }
                            )
                        # === CATEGORIZATION & NOTIFICATION END ===
                        
                        max_delay = _auto_reply_delay_seconds()
                        if max_delay:
                            delay = random.randint(0, max_delay)
                            print(f"⏰ Waiting {delay} seconds before replying to DM...")
                            await asyncio.sleep(delay)

                        # ── Cross-channel memory: record incoming DM + fetch full journey context ──
                        _cc_context = ""
                        try:
                            cross_channel_memory.add_event(
                                client_id=client_id,
                                sender_id=str(sender_id or ""),
                                channel="dm",
                                direction="incoming",
                                text=message_text,
                                message_id=message_id,
                            )
                            _cc_context = cross_channel_memory.get_context_for_prompt(client_id, str(sender_id or ""))
                        except Exception as _cce:
                            print(f"⚠️  cross_channel_memory error (DM in): {_cce}")

                        # Route through ContentCreationAgent → EngagementAgent pipeline
                        # (RAG + guardrails + style matching + cross-channel + conversation memory)
                        response = await content_agent.generate_engagement_reply(
                            message=message_text,
                            sender_id=sender_id,
                            platform="instagram",
                            cross_channel_context=_cc_context,
                        )
                        print(f"🤖 AI DM Response: {response}")

                        # Record outgoing DM reply
                        try:
                            cross_channel_memory.add_event(
                                client_id=client_id,
                                sender_id=str(sender_id or ""),
                                channel="dm",
                                direction="outgoing",
                                text=response,
                            )
                        except Exception as _cce:
                            print(f"⚠️  cross_channel_memory error (DM out): {_cce}")

                        await send_instagram_dm(sender_id, response, account_id=reply_account_id)
                        try:
                            record_meta_message(
                                platform="instagram",
                                business_account_id=my_business_id,
                                participant_id=str(sender_id or ""),
                                direction="outgoing",
                                text=response,
                            )
                        except Exception:
                            pass
            # === SCENE 2: END (handle_dm) ===
        return {"status": "received"}

    # === Facebook Page webhooks (Meta-only) ===
    if body.get("object") == "page":
        print("✅ Facebook Page webhook detected")
        default_page_id = os.getenv("FACEBOOK_PAGE_ID")

        for entry in body.get("entry", []):
            my_page_id = str(entry.get("id") or default_page_id or "").strip()
            if not my_page_id:
                print("⚠️  Missing Facebook Page id (entry.id / env)")
                continue

            client_id = resolve_client_id_for_facebook_page(my_page_id)
            agent = get_agent_for_client(client_id)
            content_agent = get_content_agent_for_client(client_id)

            # --- Handle Facebook comments (Page feed) ---
            if "changes" in entry:
                print(f"📝 Facebook feed changes detected ({len(entry.get('changes', []))} change(s))")
                for change in entry.get("changes", []):
                    field = change.get("field")
                    print(f"   Field: {field}")
                    if field != "feed":
                        print(f"   Skipping non-feed field: {field}")
                        continue
                    value = change.get("value", {}) or {}
                    item_type = (value.get("item") or "").lower()
                    print(f"   Item type: {item_type}")
                    if item_type != "comment":
                        print(f"   Skipping non-comment item: {item_type}")
                        continue

                    if not _auto_reply_enabled("comment", "facebook"):
                        print("⏸️ Facebook comment auto-reply is OFF; skipping")
                        continue

                    comment_id = str(value.get("comment_id") or value.get("id") or "").strip()
                    comment_text = value.get("message") or value.get("text") or ""
                    sender_id = (value.get("from") or {}).get("id")

                    if not comment_id or not comment_text:
                        continue

                    if str(sender_id or "") == my_page_id:
                        print(f"🛑 Ignoring Facebook comment from self ({sender_id})")
                        continue

                    dedupe_key = f"fb_comment:{comment_id}"
                    if dedupe_key in processed_comments:
                        print(f"🚫 Skipping duplicate Facebook comment {comment_id}")
                        continue
                    processed_comments.add(dedupe_key)

                    # ── Plan gate: check reply quota ──
                    if not _check_reply_quota(client_id):
                        print(f"⛔ Reply quota exhausted for {client_id}; skipping FB comment reply")
                        continue

                    try:
                        # Cross-channel memory: record incoming comment + fetch context
                        _fb_cc_ctx = ""
                        try:
                            cross_channel_memory.add_event(
                                client_id=client_id,
                                sender_id=str(sender_id or ""),
                                channel="facebook_comment",
                                direction="incoming",
                                text=comment_text,
                                message_id=comment_id,
                            )
                            _fb_cc_ctx = cross_channel_memory.get_context_for_prompt(client_id, str(sender_id or ""))
                        except Exception as _cce:
                            print(f"⚠️  cross_channel_memory error (fb comment in): {_cce}")

                        # === CATEGORIZATION & NOTIFICATION START ===
                        categorizer = get_categorizer_for_client(client_id)
                        notifier = get_notifier_for_client(client_id)

                        category_result = categorizer.categorize_message(
                            message=comment_text,
                            context=f"Facebook comment from {sender_id}",
                            sender_id=str(sender_id or "")
                        )

                        print(f"📊 Conversation categorized as: {category_result.category} (priority: {category_result.priority})")

                        if category_result.requires_notification:
                            _snippet = (comment_text[:120] + "...") if len(comment_text) > 120 else comment_text
                            await notifier.send_notification(
                                notification_type=category_result.category.lower(),
                                title=f"Facebook Comment — {category_result.category.replace('_', ' ').title()}",
                                message=f"{_snippet}",
                                priority=category_result.priority,
                                metadata={
                                    "sender_id": str(sender_id or ""),
                                    "platform": "facebook",
                                    "message_type": "comment",
                                    "category": category_result.category,
                                    "confidence": category_result.confidence,
                                    "action_url": "/comments/dashboard",
                                    "action_label": "View Comment",
                                    "action_type": "internal_link",
                                }
                            )
                        # === CATEGORIZATION & NOTIFICATION END ===

                        response = await content_agent.generate_engagement_reply(
                            message=comment_text,
                            sender_id=str(sender_id or ""),
                            platform="facebook",
                            cross_channel_context=_fb_cc_ctx,
                        )
                        print(f"🤖 AI FB Comment Response: {response}")

                        try:
                            cross_channel_memory.add_event(
                                client_id=client_id,
                                sender_id=str(sender_id or ""),
                                channel="facebook_comment",
                                direction="outgoing",
                                text=response,
                            )
                        except Exception as _cce:
                            print(f"⚠️  cross_channel_memory error (fb comment out): {_cce}")

                        await reply_to_facebook_comment(comment_id, response, page_id=my_page_id)
                    except Exception as e:
                        print(f"❌ Error handling Facebook comment reply: {e}")

            # --- Handle Facebook DMs (Messenger) ---
            if "messaging" in entry:
                print(f"💬 Facebook messaging events detected ({len(entry.get('messaging', []))} event(s))")
                for event in entry.get("messaging", []):
                    if "read" in event or "delivery" in event or "reaction" in event or "postback" in event:
                        continue
                    if "message" not in event:
                        continue

                    sender_id = event.get("sender", {}).get("id")
                    message = event.get("message", {})
                    message_text = message.get("text", "")
                    attachments = message.get("attachments", [])
                    message_id = message.get("mid")

                    if message.get("is_echo"):
                        continue

                    inbound_text = message_text or ("[Attachment]" if attachments else "")
                    try:
                        record_meta_message(
                            platform="facebook",
                            business_account_id=my_page_id,
                            participant_id=str(sender_id or ""),
                            direction="incoming",
                            text=inbound_text,
                            message_id=message_id,
                        )
                    except Exception:
                        pass

                    if not _auto_reply_enabled("dm", "facebook"):
                        print("⏸️ Facebook DM auto-reply is OFF; skipping")
                        continue

                    if not message_id:
                        continue

                    dedupe_mid = f"fb_dm:{message_id}"
                    if dedupe_mid in processed_messages:
                        print(f"🚫 Skipping duplicate Facebook DM {message_id}")
                        continue
                    processed_messages.add(dedupe_mid)

                    # Attachment-only message
                    if (not message_text or message_text.strip() == "") and attachments:
                        out_text = "Thanks for reaching out! 🙌 How can I help?"
                        await send_facebook_dm(sender_id, out_text, page_id=my_page_id)
                        try:
                            record_meta_message(
                                platform="facebook",
                                business_account_id=my_page_id,
                                participant_id=str(sender_id or ""),
                                direction="outgoing",
                                text=out_text,
                            )
                        except Exception:
                            pass
                        continue

                    if not message_text:
                        continue

                    # ── Plan gate: check reply quota ──
                    if not _check_reply_quota(client_id):
                        print(f"⛔ Reply quota exhausted for {client_id}; skipping FB DM reply")
                        continue

                    # Escalation handling mirrors Instagram logic
                    normalized_fb_text = message_text.lower().strip()
                    if "resume bot" in normalized_fb_text or normalized_fb_text == "resume bot":
                        if sender_id in escalated_conversations:
                            escalated_conversations.discard(sender_id)
                            out_text = "Bet, I'm back! 🙌 What you need help with?"
                        else:
                            out_text = "I'm already here! 👋 What's up?"
                        await send_facebook_dm(sender_id, out_text, page_id=my_page_id)
                        try:
                            record_meta_message(
                                platform="facebook",
                                business_account_id=my_page_id,
                                participant_id=str(sender_id or ""),
                                direction="outgoing",
                                text=out_text,
                            )
                        except Exception:
                            pass
                        continue

                    if sender_id in escalated_conversations:
                        print(f"⏸️ Skipping automated response - conversation {sender_id} is escalated to human")
                        continue

                    if check_escalation_keywords(message_text):
                        print(f"🚨 Human escalation detected from {sender_id} (Facebook DM)")
                        escalated_conversations.add(sender_id)
                        log_escalation(sender_id, message_text)
                        escalation_prompt = (
                            "Let the user know a human will respond soon, but do it in our brand's friendly, conversational style. "
                            "Add: 'If you want to continue with automated help, just reply with resume bot.'"
                        )
                        escalation_message = await agent.generate_response(escalation_prompt, sender_id=sender_id)
                        await send_facebook_dm(sender_id, escalation_message, page_id=my_page_id)
                        try:
                            record_meta_message(
                                platform="facebook",
                                business_account_id=my_page_id,
                                participant_id=str(sender_id or ""),
                                direction="outgoing",
                                text=escalation_message,
                            )
                        except Exception:
                            pass
                        continue

                    # Cross-channel memory: record incoming FB DM + fetch full journey context
                    _fb_dm_cc_ctx = ""
                    try:
                        cross_channel_memory.add_event(
                            client_id=client_id,
                            sender_id=str(sender_id or ""),
                            channel="facebook_dm",
                            direction="incoming",
                            text=message_text,
                            message_id=message_id,
                        )
                        _fb_dm_cc_ctx = cross_channel_memory.get_context_for_prompt(client_id, str(sender_id or ""))
                    except Exception as _cce:
                        print(f"⚠️  cross_channel_memory error (fb DM in): {_cce}")

                    # === CATEGORIZATION & NOTIFICATION START ===
                    categorizer = get_categorizer_for_client(client_id)
                    notifier = get_notifier_for_client(client_id)

                    category_result = categorizer.categorize_message(
                        message=message_text,
                        context=f"Facebook DM from {sender_id}",
                        sender_id=str(sender_id or "")
                    )

                    print(f"📊 Conversation categorized as: {category_result.category} (priority: {category_result.priority})")

                    if category_result.requires_notification:
                        _snippet = (message_text[:120] + "...") if len(message_text) > 120 else message_text
                        await notifier.send_notification(
                            notification_type=category_result.category.lower(),
                            title=f"Facebook DM — {category_result.category.replace('_', ' ').title()}",
                            message=f"{_snippet}",
                            priority=category_result.priority,
                            metadata={
                                "sender_id": str(sender_id or ""),
                                "platform": "facebook",
                                "message_type": "dm",
                                "category": category_result.category,
                                "confidence": category_result.confidence,
                                "action_url": "/inbox/dashboard",
                                "action_label": "Open Inbox",
                                "action_type": "internal_link",
                            }
                        )
                    # === CATEGORIZATION & NOTIFICATION END ===

                    response = await content_agent.generate_engagement_reply(
                        message=message_text,
                        sender_id=str(sender_id or ""),
                        platform="facebook",
                        cross_channel_context=_fb_dm_cc_ctx,
                    )
                    print(f"🤖 AI FB DM Response: {response}")

                    try:
                        cross_channel_memory.add_event(
                            client_id=client_id,
                            sender_id=str(sender_id or ""),
                            channel="facebook_dm",
                            direction="outgoing",
                            text=response,
                        )
                    except Exception as _cce:
                        print(f"⚠️  cross_channel_memory error (fb DM out): {_cce}")

                    await send_facebook_dm(sender_id, response, page_id=my_page_id)
                    try:
                        record_meta_message(
                            platform="facebook",
                            business_account_id=my_page_id,
                            participant_id=str(sender_id or ""),
                            direction="outgoing",
                            text=response,
                        )
                    except Exception:
                        pass

            # Log what was in this entry if neither messaging nor changes were found
            entry_keys = list(entry.keys())
            if "messaging" not in entry and "changes" not in entry:
                print(f"⚠️ Facebook entry had neither 'messaging' nor 'changes' keys: {entry_keys}")

        return {"status": "received"}

    return {"status": "ignored"}
    # === SCENE 1: END (Get client_id & Use EngagementAgent) ===

@router.get("/escalations")
async def get_escalations():
    """Get list of all escalated conversation IDs."""
    return {
        "escalated_conversations": list(escalated_conversations),
        "count": len(escalated_conversations)
    }

@router.delete("/escalations/{sender_id}")
async def clear_escalation(sender_id: str):
    """Clear escalation for a specific sender, resuming automated responses."""
    if sender_id in escalated_conversations:
        escalated_conversations.discard(sender_id)
        print(f"✅ Cleared escalation for {sender_id} - automated responses resumed")
        return {"status": "cleared", "sender_id": sender_id}
    return {"status": "not_found", "sender_id": sender_id}

@router.delete("/escalations")
async def clear_all_escalations():
    """Clear all escalations, resuming automated responses for all conversations."""
    count = len(escalated_conversations)
    escalated_conversations.clear()
    print(f"✅ Cleared all {count} escalations - automated responses resumed for all")
    return {"status": "cleared_all", "count": count}

@router.get("/health")
async def health_check():
    return {"status": "running", "message": "Server is up and running"}

@router.get("/debug/webhooks")
async def get_webhook_history():
    """GET endpoint to view recent webhook requests (for debugging)."""
    try:
        with open(WEBHOOK_LOG_FILE, "r") as f:
            recent_logs = f.read()[-2000:]  # Last 2000 chars
    except FileNotFoundError:
        recent_logs = "No webhook log file yet. Webhooks will be logged here."
    
    return {
        "status": "ok",
        "in_memory_history_count": len(WEBHOOK_REQUEST_HISTORY),
        "recent_requests": WEBHOOK_REQUEST_HISTORY[-10:],  # Last 10 in-memory requests
        "file_excerpt": recent_logs,
        "tips": [
            "1. If this list is empty, Meta is NOT sending webhooks to your server.",
            "2. Check Meta App Dashboard → Webhooks → Delivery logs.",
            "3. If app is in Dev mode, webhooks only fire for admins/testers.",
            "4. Make sure to comment as a DIFFERENT USER (not as Page).",
            "5. Check if the Page is subscribed to 'feed' field at app level."
        ]
    }

# Standalone app (initialized AFTER all routes are defined on router)
app = FastAPI()
app.include_router(router)

if __name__ == "__main__":
    print("🚀 Starting webhook receiver...")
    uvicorn.run(app, host="0.0.0.0", port=8000)