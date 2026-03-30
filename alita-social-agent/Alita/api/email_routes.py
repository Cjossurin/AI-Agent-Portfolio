"""
api/email_routes.py  —  Unified Email Hub
==========================================
Single page at /email with three tabs: Connect · Inbox · Campaigns.
All email operations go through utils/email_service.py for provider dispatch.

Routes (HTML)
─────────────
GET  /email                       → Merged email hub
GET  /email/dashboard             → redirect → /email?tab=campaigns

Routes (OAuth / Connect)
────────────────────────
GET  /email/authorize-microsoft   → Microsoft OAuth step 1
GET  /email/callback-microsoft    → Microsoft OAuth step 2

Routes (JSON API)
─────────────────
GET  /api/email/connection-status → {connected, provider, email}
POST /api/email/fetch-now         → manual inbox poll
GET  /api/email/inbox             → paginated threads
GET  /api/email/thread/<id>       → full conversation
POST /api/email/approve-draft/<id>
POST /api/email/reject-draft/<id>
POST /api/email/edit-draft/<id>
POST /api/email/manual-reply/<thread_id>
POST /api/email/plan-campaign
GET  /api/email/campaigns
GET  /api/email/campaign-stats
POST /api/email/send-campaign/<id>
GET  /api/email/subscribers
POST /api/email/subscribers
POST /api/email/subscribers/import
DELETE /api/email/subscribers/<id>
POST /api/email/process-inbox     (legacy compat → redirects to fetch-now)
GET  /api/email/support-stats     (legacy compat)
"""

import os, json, sys, uuid, csv, io
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request, Form, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from database.db import get_db
from utils.shared_layout import build_page, get_user_context
from utils.plan_limits import check_limit, increment_usage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

router = APIRouter(tags=["Email"])

EMAIL_STORAGE = Path("storage") / "email_campaigns"


# ── helper ────────────────────────────────────────────────────────────────────
def _encrypt_token(raw: str) -> str:
    from cryptography.fernet import Fernet
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        return raw
    return Fernet(key.encode()).encrypt(raw.encode()).decode()

def _decrypt_token(enc: str) -> str:
    from cryptography.fernet import Fernet
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        return enc
    try:
        return Fernet(key.encode()).decrypt(enc.encode()).decode()
    except Exception:
        return enc


# ══════════════════════════════════════════════════════════════════════════════
# MICROSOFT OAUTH
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/email/authorize-microsoft")
async def microsoft_authorize(request: Request):
    """Redirect the user to Microsoft's OAuth consent screen."""
    import secrets as _sec
    from urllib.parse import urlencode as _ue

    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)

        # Block if user hasn't accepted the email AI agreement
        if not getattr(profile, "email_ai_agreed_at", None):
            return RedirectResponse("/email?tab=connect&error=agreement_required", status_code=303)

        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        if not client_id:
            return JSONResponse({"error": "Microsoft OAuth not configured"}, status_code=500)

        redirect_uri = os.getenv(
            "MICROSOFT_REDIRECT_URI",
            os.getenv("APP_BASE_URL", "http://localhost:8000") + "/email/callback-microsoft"
        )
        state = f"{profile.id}:{_sec.token_urlsafe(16)}"

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email Mail.Read Mail.Send offline_access User.Read",
            "response_mode": "query",
            "prompt": "consent",
            "state": state,
            "login_hint": user.email,
        }
        url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{_ue(params)}"
        return RedirectResponse(url=url)
    finally:
        db.close()


@router.get("/email/callback-microsoft")
async def microsoft_callback(request: Request, code: str = Query(...), state: str = Query("")):
    """Exchange Microsoft authorization code for tokens and store them."""
    import httpx

    parts = state.split(":", 1)
    if len(parts) != 2:
        return JSONResponse({"error": "Invalid state parameter"}, status_code=400)
    profile_id = parts[0]

    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "MICROSOFT_REDIRECT_URI",
        os.getenv("APP_BASE_URL", "http://localhost:8000") + "/email/callback-microsoft"
    )

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "openid email Mail.Read Mail.Send offline_access User.Read",
            },
        )

    if resp.status_code != 200:
        err = resp.json().get("error_description", resp.text[:300])
        return JSONResponse({"error": f"Microsoft token exchange failed: {err}"}, status_code=400)

    data = resp.json()
    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    expires_in = int(data.get("expires_in", 3600))

    if not refresh_token:
        return JSONResponse({"error": "Microsoft did not return a refresh token. Ensure offline_access scope is granted."}, status_code=400)

    # Fetch user's email via Graph
    ms_email = ""
    async with httpx.AsyncClient() as client:
        me_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me_resp.status_code == 200:
            me_data = me_resp.json()
            ms_email = me_data.get("mail") or me_data.get("userPrincipalName", "")

    # Store tokens in DB
    from database.models import MicrosoftOAuthToken
    from datetime import timedelta
    db = next(get_db())
    try:
        existing = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.client_profile_id == profile_id
        ).first()

        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        if existing:
            existing.access_token_enc = _encrypt_token(access_token)
            existing.refresh_token_enc = _encrypt_token(refresh_token)
            existing.email_address = ms_email or existing.email_address
            existing.token_expires_at = token_expires_at
            existing.scopes = "Mail.Read,Mail.Send,User.Read,offline_access"
            existing.updated_at = datetime.utcnow()
        else:
            existing = MicrosoftOAuthToken(
                id=str(uuid.uuid4()),
                client_profile_id=profile_id,
                email_address=ms_email,
                access_token_enc=_encrypt_token(access_token),
                refresh_token_enc=_encrypt_token(refresh_token),
                token_expires_at=token_expires_at,
                scopes="Mail.Read,Mail.Send,User.Read,offline_access",
            )
            db.add(existing)
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/email?tab=connect&connected=1", status_code=303)


@router.post("/email/disconnect-microsoft")
async def microsoft_disconnect(request: Request):
    """Remove Microsoft OAuth tokens."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)

        from database.models import MicrosoftOAuthToken
        tok = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.client_profile_id == profile.id
        ).first()
        if tok:
            db.delete(tok)
            db.commit()
    finally:
        db.close()
    return RedirectResponse(url="/email?tab=connect&disconnected=1", status_code=303)


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION STATUS API
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/email/connection-status")
async def api_connection_status(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        from utils.email_service import get_connection_status
        return JSONResponse(get_connection_status(profile.client_id))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL AI AGREEMENT — permanent record of user consent
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/email/accept-agreement")
async def accept_email_agreement(request: Request):
    """Record the user's acceptance of the AI Email Processing Agreement permanently."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "No profile found"}, status_code=400)

        if profile.email_ai_agreed_at:
            return JSONResponse({"ok": True, "message": "Already accepted"})

        from datetime import datetime as _dt
        # Record IP address from request
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

        profile.email_ai_agreed_at = _dt.utcnow()
        profile.email_ai_agreement_ip = client_ip
        db.commit()
        print(f"[AGREEMENT] Email AI agreement accepted by user {user.id} (client {profile.client_id}) from IP {client_ip}")
        return JSONResponse({"ok": True})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# INBOX API  —  fetch, list threads, view thread, approve/reject/edit drafts
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/email/fetch-now")
async def api_fetch_now(request: Request, background_tasks: BackgroundTasks):
    """Manually poll the connected inbox, store new emails, generate AI drafts."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "No profile"}, status_code=400)

        from utils.email_service import get_connection
        conn = get_connection(profile.client_id)
        if not conn:
            return JSONResponse({"ok": False, "error": "No email connected. Go to the Connect tab first."})

        background_tasks.add_task(_bg_fetch_and_process, profile.client_id, profile.id)
        return JSONResponse({"ok": True, "message": "Fetching inbox — new emails will appear shortly."})
    finally:
        db.close()


def _bg_fetch_and_process(client_id: str, profile_id: str):
    """Sync wrapper for background task."""
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_bg_fetch_and_process_async(client_id, profile_id))


async def _bg_fetch_and_process_async(client_id: str, profile_id: str):
    """Fetch inbox, store new messages in DB, run AI categorization + draft."""
    try:
        from utils.email_service import fetch_inbox as _fetch
        from database.db import get_db as _gdb
        from database.models import EmailThread, EmailMessageRecord, EmailCategory, DraftStatus

        raw_emails = await _fetch(client_id, max_results=20, unread_only=True)
        if not raw_emails:
            print(f"[email] No new emails for {client_id}")
            return

        db = next(_gdb())
        new_count = 0
        try:
            for raw in raw_emails:
                ext_msg_id = raw.get("message_id", "")
                # Skip if already stored
                if ext_msg_id:
                    existing = db.query(EmailMessageRecord).filter(
                        EmailMessageRecord.external_message_id == ext_msg_id,
                        EmailMessageRecord.client_profile_id == profile_id,
                    ).first()
                    if existing:
                        continue

                # Find or create thread
                ext_thread_id = raw.get("thread_id", ext_msg_id)
                thread = db.query(EmailThread).filter(
                    EmailThread.external_thread_id == ext_thread_id,
                    EmailThread.client_profile_id == profile_id,
                ).first()

                if not thread:
                    thread = EmailThread(
                        id=uuid.uuid4().hex,
                        client_profile_id=profile_id,
                        external_thread_id=ext_thread_id,
                        subject=raw.get("subject", "(no subject)"),
                        sender_email=raw.get("sender_email", ""),
                        sender_name=raw.get("sender_name", ""),
                        category=EmailCategory.general,
                        message_count=0,
                        last_message_at=datetime.utcnow(),
                    )
                    db.add(thread)
                    db.flush()

                # AI categorize
                category_str = "general"
                ai_draft = ""
                try:
                    from agents.email_support_agent import EmailSupportAgent
                    agent = EmailSupportAgent(client_id=client_id)
                    # Quick categorization using the agent's AI
                    cat_result = await agent.categorize_email_text(
                        subject=raw.get("subject", ""),
                        body=raw.get("body", "")[:2000],
                        sender=raw.get("sender_email", ""),
                    )
                    category_str = cat_result.get("category", "general")
                    ai_draft = cat_result.get("draft_reply", "")
                except Exception as cat_err:
                    print(f"[email] Categorize failed: {cat_err}")

                # Update thread category
                try:
                    thread.category = EmailCategory(category_str)
                except Exception:
                    thread.category = EmailCategory.general

                # Create message record
                msg_record = EmailMessageRecord(
                    id=uuid.uuid4().hex,
                    thread_id=thread.id,
                    client_profile_id=profile_id,
                    external_message_id=ext_msg_id,
                    direction="inbound",
                    sender_email=raw.get("sender_email", ""),
                    sender_name=raw.get("sender_name", ""),
                    subject=raw.get("subject", ""),
                    body_text=raw.get("body", ""),
                    ai_category=category_str,
                    ai_draft_reply=ai_draft if ai_draft else None,
                    draft_status=DraftStatus.pending if ai_draft else DraftStatus.none,
                    received_at=datetime.utcnow(),
                )
                db.add(msg_record)

                thread.message_count = (thread.message_count or 0) + 1
                thread.last_message_at = datetime.utcnow()
                new_count += 1

            db.commit()
            print(f"[email] Stored {new_count} new emails for {client_id}")

        except Exception as db_err:
            db.rollback()
            print(f"[email] DB error storing emails: {db_err}")
            import traceback; traceback.print_exc()
        finally:
            db.close()

    except Exception as e:
        print(f"[email] _bg_fetch_and_process failed: {e}")
        import traceback; traceback.print_exc()


@router.get("/api/email/inbox")
async def api_inbox(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1, le=100)):
    """Return paginated email threads for the current client."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"threads": [], "total": 0})

        from database.models import EmailThread, EmailMessageRecord
        q = db.query(EmailThread).filter(
            EmailThread.client_profile_id == profile.id
        ).order_by(EmailThread.last_message_at.desc())

        total = q.count()
        threads = q.offset((page - 1) * per_page).limit(per_page).all()

        result = []
        for t in threads:
            # Get latest message
            latest = db.query(EmailMessageRecord).filter(
                EmailMessageRecord.thread_id == t.id
            ).order_by(EmailMessageRecord.received_at.desc()).first()

            has_pending = db.query(EmailMessageRecord).filter(
                EmailMessageRecord.thread_id == t.id,
                EmailMessageRecord.draft_status == "pending",
            ).count() > 0

            result.append({
                "id": t.id,
                "subject": t.subject or "(no subject)",
                "sender_email": t.sender_email or "",
                "sender_name": t.sender_name or "",
                "category": t.category.value if t.category else "general",
                "status": t.status.value if t.status else "active",
                "message_count": t.message_count or 0,
                "has_pending_draft": has_pending,
                "last_message_at": t.last_message_at.isoformat() if t.last_message_at else "",
                "snippet": (latest.body_text or "")[:120] if latest else "",
            })

        return JSONResponse({"threads": result, "total": total, "page": page, "per_page": per_page})
    finally:
        db.close()


@router.get("/api/email/thread/{thread_id}")
async def api_thread_detail(request: Request, thread_id: str):
    """Return all messages in a thread."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        from database.models import EmailThread, EmailMessageRecord
        thread = db.query(EmailThread).filter(
            EmailThread.id == thread_id,
            EmailThread.client_profile_id == profile.id,
        ).first()
        if not thread:
            return JSONResponse({"error": "Thread not found"}, status_code=404)

        messages = db.query(EmailMessageRecord).filter(
            EmailMessageRecord.thread_id == thread_id
        ).order_by(EmailMessageRecord.received_at.asc()).all()

        msgs = []
        for m in messages:
            msgs.append({
                "id": m.id,
                "direction": m.direction,
                "sender_email": m.sender_email or "",
                "sender_name": m.sender_name or "",
                "subject": m.subject or "",
                "body_text": m.body_text or "",
                "ai_category": m.ai_category or "",
                "ai_draft_reply": m.ai_draft_reply or "",
                "draft_status": m.draft_status.value if m.draft_status else "none",
                "received_at": m.received_at.isoformat() if m.received_at else "",
            })

        return JSONResponse({
            "thread": {
                "id": thread.id,
                "subject": thread.subject,
                "category": thread.category.value if thread.category else "general",
                "status": thread.status.value if thread.status else "active",
            },
            "messages": msgs,
        })
    finally:
        db.close()


@router.post("/api/email/approve-draft/{message_id}")
async def api_approve_draft(request: Request, message_id: str):
    """Approve an AI draft reply and send it."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        from database.models import EmailMessageRecord, EmailThread, DraftStatus
        msg = db.query(EmailMessageRecord).filter(
            EmailMessageRecord.id == message_id,
            EmailMessageRecord.client_profile_id == profile.id,
        ).first()
        if not msg or not msg.ai_draft_reply:
            return JSONResponse({"error": "Draft not found"}, status_code=404)

        # Send the reply
        from utils.email_service import send_email
        subject = msg.subject or ""
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        result = await send_email(
            client_id=profile.client_id,
            to=msg.sender_email,
            subject=subject,
            body_html=msg.ai_draft_reply.replace("\n", "<br>"),
            body_text=msg.ai_draft_reply,
            in_reply_to=msg.external_message_id or "",
        )

        if result.get("status") == "sent":
            msg.draft_status = DraftStatus.sent

            # Create outbound message record
            thread = db.query(EmailThread).filter(EmailThread.id == msg.thread_id).first()
            outbound = EmailMessageRecord(
                id=uuid.uuid4().hex,
                thread_id=msg.thread_id,
                client_profile_id=profile.id,
                external_message_id=result.get("message_id", ""),
                direction="outbound",
                sender_email=profile.client_id,
                subject=subject,
                body_text=msg.ai_draft_reply,
                draft_status=DraftStatus.none,
                received_at=datetime.utcnow(),
            )
            db.add(outbound)
            if thread:
                thread.message_count = (thread.message_count or 0) + 1
            db.commit()
            return JSONResponse({"ok": True, "message": "Reply sent!"})
        else:
            return JSONResponse({"ok": False, "error": result.get("error", "Send failed")})
    finally:
        db.close()


@router.post("/api/email/reject-draft/{message_id}")
async def api_reject_draft(request: Request, message_id: str):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        from database.models import EmailMessageRecord, DraftStatus
        msg = db.query(EmailMessageRecord).filter(
            EmailMessageRecord.id == message_id,
            EmailMessageRecord.client_profile_id == profile.id,
        ).first()
        if msg:
            msg.draft_status = DraftStatus.rejected
            db.commit()
        return JSONResponse({"ok": True})
    finally:
        db.close()


@router.post("/api/email/edit-draft/{message_id}")
async def api_edit_draft(request: Request, message_id: str):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        body = await request.json()
        new_text = body.get("draft_text", "")
        from database.models import EmailMessageRecord, DraftStatus
        msg = db.query(EmailMessageRecord).filter(
            EmailMessageRecord.id == message_id,
            EmailMessageRecord.client_profile_id == profile.id,
        ).first()
        if msg:
            msg.ai_draft_reply = new_text
            msg.draft_status = DraftStatus.pending
            db.commit()
        return JSONResponse({"ok": True})
    finally:
        db.close()


@router.post("/api/email/manual-reply/{thread_id}")
async def api_manual_reply(request: Request, thread_id: str):
    """Send a free-form reply to a thread."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        body = await request.json()
        reply_text = body.get("reply_text", "").strip()
        if not reply_text:
            return JSONResponse({"error": "Reply text is required"}, status_code=400)

        from database.models import EmailThread, EmailMessageRecord, DraftStatus
        thread = db.query(EmailThread).filter(
            EmailThread.id == thread_id,
            EmailThread.client_profile_id == profile.id,
        ).first()
        if not thread:
            return JSONResponse({"error": "Thread not found"}, status_code=404)

        from utils.email_service import send_email
        subject = thread.subject or ""
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        result = await send_email(
            client_id=profile.client_id,
            to=thread.sender_email,
            subject=subject,
            body_html=reply_text.replace("\n", "<br>"),
            body_text=reply_text,
        )

        if result.get("status") == "sent":
            outbound = EmailMessageRecord(
                id=uuid.uuid4().hex,
                thread_id=thread.id,
                client_profile_id=profile.id,
                external_message_id=result.get("message_id", ""),
                direction="outbound",
                sender_email=profile.client_id,
                subject=subject,
                body_text=reply_text,
                draft_status=DraftStatus.none,
                received_at=datetime.utcnow(),
            )
            db.add(outbound)
            thread.message_count = (thread.message_count or 0) + 1
            db.commit()
            return JSONResponse({"ok": True, "message": "Reply sent!"})
        else:
            return JSONResponse({"ok": False, "error": result.get("error", "Send failed")})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN API  —  plan, list, send
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/email/plan-campaign")
async def api_plan_campaign(request: Request):
    """Plan an email campaign using EmailMarketingAgent, persist to DB."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"error": "No profile found"}, status_code=400)

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        allowed, msg = check_limit(profile, "campaigns_sent")
        if not allowed:
            return JSONResponse({"error": msg, "upgrade_url": "/billing"}, status_code=402)
        increment_usage(profile, "campaigns_sent", db)

        from agents.email_marketing_agent import (
            EmailMarketingAgent, CampaignType, CampaignGoal, AudienceSegment
        )

        def _ct(v):
            try: return CampaignType(v)
            except Exception: return CampaignType.NEWSLETTER
        def _cg(v):
            try: return CampaignGoal(v)
            except Exception: return CampaignGoal.ENGAGEMENT
        def _seg(v):
            try: return AudienceSegment(v)
            except Exception: return AudienceSegment.ALL_SUBSCRIBERS

        agent = EmailMarketingAgent(client_id=profile.client_id)
        agent.set_tier(getattr(profile, "plan_tier", "pro") or "pro")

        import asyncio
        from utils.agent_executor import AGENT_POOL
        loop = asyncio.get_running_loop()
        rec = await loop.run_in_executor(
            AGENT_POOL,
            lambda: agent.plan_campaign(
                campaign_type=_ct(body.get("campaign_type", "newsletter")),
                campaign_goal=_cg(body.get("campaign_goal", "engagement")),
                target_segment=_seg(body.get("target_segment", "all_subscribers")),
                content_brief=body.get("content_brief", f"Campaign for {profile.business_name}"),
                client_knowledge=body.get("client_knowledge", ""),
                industry=body.get("industry", profile.niche or "default"),
            )
        )

        # Persist to DB instead of disk
        from database.models import EmailCampaignRecord
        plan_id = uuid.uuid4().hex
        plan_json = json.dumps({
            "subject_lines": [s if isinstance(s, str) else str(s) for s in (rec.subject_lines or [])],
            "recommended_send_times": [t if isinstance(t, str) else str(t) for t in (rec.recommended_send_times or [])],
            "segmentation_recommendations": rec.segmentation_recommendations or [],
            "content_recommendations": rec.content_recommendations or [],
            "estimated_open_rate": rec.estimated_open_rate,
            "estimated_click_rate": rec.estimated_click_rate,
            "ab_test_suggestions": rec.ab_test_suggestions or [],
            "deliverability_tips": rec.deliverability_tips or [],
        }, ensure_ascii=False)

        campaign = EmailCampaignRecord(
            id=plan_id,
            client_profile_id=profile.id,
            campaign_type=body.get("campaign_type", "newsletter"),
            campaign_goal=body.get("campaign_goal", "engagement"),
            target_segment=body.get("target_segment", "all_subscribers"),
            content_brief=body.get("content_brief", ""),
            plan_json=plan_json,
        )
        db.add(campaign)
        db.commit()

        return JSONResponse({"ok": True, "plan_id": plan_id, "plan": json.loads(plan_json)})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


@router.get("/api/email/campaigns")
@router.get("/api/email/campaign-stats")
async def api_campaigns(request: Request):
    """Return saved campaign plans from DB."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"plans": []})

        from database.models import EmailCampaignRecord
        campaigns = db.query(EmailCampaignRecord).filter(
            EmailCampaignRecord.client_profile_id == profile.id
        ).order_by(EmailCampaignRecord.created_at.desc()).limit(30).all()

        plans = []
        for c in campaigns:
            plan_data = {}
            try:
                plan_data = json.loads(c.plan_json) if c.plan_json else {}
            except Exception:
                pass
            plans.append({
                "plan_id": c.id,
                "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
                "campaign_type": c.campaign_type or "",
                "campaign_goal": c.campaign_goal or "",
                "status": c.status.value if c.status else "draft",
                "est_open_rate": plan_data.get("estimated_open_rate"),
                "est_click_rate": plan_data.get("estimated_click_rate"),
                "subject_lines_count": len(plan_data.get("subject_lines", [])),
                "total_recipients": c.total_recipients or 0,
                "sent_count": c.sent_count or 0,
            })

        # Also load any legacy disk-based plans
        legacy_dir = EMAIL_STORAGE / "marketing" / (profile.client_id if profile else "")
        if legacy_dir.exists():
            for f in sorted(legacy_dir.glob("*.json"), reverse=True)[:10]:
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    plans.append({
                        "plan_id": d.get("plan_id"),
                        "created_at": d.get("created_at", "")[:10],
                        "campaign_type": d.get("campaign_type", ""),
                        "campaign_goal": d.get("campaign_goal", ""),
                        "status": "draft",
                        "est_open_rate": d.get("estimated_open_rate"),
                        "est_click_rate": d.get("estimated_click_rate"),
                        "subject_lines_count": len(d.get("subject_lines", [])),
                        "total_recipients": 0,
                        "sent_count": 0,
                    })
                except Exception:
                    pass

        return JSONResponse({"plans": plans})
    finally:
        db.close()


@router.post("/api/email/send-campaign/{campaign_id}")
async def api_send_campaign(request: Request, campaign_id: str, background_tasks: BackgroundTasks):
    """Send a campaign to all active subscribers."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        from database.models import EmailCampaignRecord, EmailSubscriber, CampaignStatus, SubscriberStatus
        campaign = db.query(EmailCampaignRecord).filter(
            EmailCampaignRecord.id == campaign_id,
            EmailCampaignRecord.client_profile_id == profile.id,
        ).first()
        if not campaign:
            return JSONResponse({"error": "Campaign not found"}, status_code=404)

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        subject = body.get("subject", "")
        body_html = body.get("body_html", "")
        if not subject or not body_html:
            return JSONResponse({"error": "subject and body_html are required"}, status_code=400)

        subscribers = db.query(EmailSubscriber).filter(
            EmailSubscriber.client_profile_id == profile.id,
            EmailSubscriber.status == SubscriberStatus.active,
        ).all()

        if not subscribers:
            return JSONResponse({"error": "No active subscribers. Add subscribers first."}, status_code=400)

        campaign.status = CampaignStatus.queued
        campaign.total_recipients = len(subscribers)
        db.commit()

        recipients = [{"email": s.email, "name": s.name or ""} for s in subscribers]
        background_tasks.add_task(
            _bg_send_campaign, profile.client_id, campaign_id, recipients, subject, body_html
        )

        return JSONResponse({"ok": True, "message": f"Sending to {len(recipients)} subscribers...", "total": len(recipients)})
    finally:
        db.close()


def _bg_send_campaign(client_id: str, campaign_id: str, recipients: list, subject: str, body_html: str):
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_bg_send_campaign_async(client_id, campaign_id, recipients, subject, body_html))


async def _bg_send_campaign_async(client_id: str, campaign_id: str, recipients: list, subject: str, body_html: str):
    try:
        from utils.email_service import send_campaign_batch
        from database.db import get_db as _gdb
        from database.models import EmailCampaignRecord, CampaignStatus

        db = next(_gdb())
        campaign = db.query(EmailCampaignRecord).filter(EmailCampaignRecord.id == campaign_id).first()
        if campaign:
            campaign.status = CampaignStatus.sending
            db.commit()

        result = await send_campaign_batch(
            client_id=client_id,
            recipients=recipients,
            subject=subject,
            body_html=body_html,
        )

        if campaign:
            campaign.sent_count = result.get("sent", 0)
            campaign.status = CampaignStatus.sent if result.get("ok") else CampaignStatus.failed
            campaign.error_log = json.dumps(result.get("errors", []))[:2000]
            db.commit()

        db.close()
        print(f"[email] Campaign {campaign_id}: sent={result.get('sent')}, failed={result.get('failed')}")

        # ── Send notification email about campaign result ──────────────
        try:
            import importlib
            nm_mod = importlib.import_module("utils.notification_manager")
            NotificationManager = getattr(nm_mod, "NotificationManager", None)
            if NotificationManager:
                nm = NotificationManager(client_id)
                _sent = result.get("sent", 0)
                _failed = result.get("failed", 0)
                _total = result.get("total", len(recipients))
                _errors = result.get("errors", [])
                _ok = result.get("ok", False)

                if _ok and _failed == 0:
                    _camp_msg = (
                        f"Your email campaign was sent successfully.\n\n"
                        f"Recipients: {_total}\n"
                        f"Delivered: {_sent}\n"
                        f"Failed: 0\n\n"
                        f"No errors occurred during sending."
                    )
                    _prio = "medium"
                else:
                    _fail_items = []
                    for err in _errors[:20]:
                        if isinstance(err, dict):
                            _fail_items.append({
                                "item": err.get("email", "Unknown recipient"),
                                "error": err.get("error", str(err)),
                                "time": err.get("time", ""),
                            })
                        else:
                            _fail_items.append({"item": "Recipient", "error": str(err), "time": ""})

                    _camp_msg = (
                        f"Your email campaign finished with errors.\n\n"
                        f"Total recipients: {_total}\n"
                        f"Successfully sent: {_sent}\n"
                        f"Failed: {_failed}\n\n"
                    )
                    if _errors:
                        _camp_msg += (
                            f"See the failure details below for each recipient that failed "
                            f"and the specific error returned by the email provider."
                        )
                    _prio = "high"

                from datetime import datetime as _dt_camp
                await nm.send_growth_notification(
                    notification_type="system",
                    title=f"Email Campaign: {_sent}/{_total} sent" + ("" if _ok else " (errors)"),
                    message=_camp_msg,
                    priority=_prio,
                    action_url="/email",
                    action_label="View Campaign",
                    extra_meta={
                        "job_name": f"email_campaign ({campaign_id})",
                        "event_time": _dt_camp.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                        "failed_items": _fail_items if not _ok else [],
                        "error_code": "" if _ok else "CAMPAIGN_PARTIAL_FAILURE",
                    },
                )
        except Exception as _notif_err:
            print(f"[email] Campaign notification failed: {_notif_err}")

    except Exception as e:
        print(f"[email] Campaign send failed: {e}")
        import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIBER API
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/email/subscribers")
async def api_list_subscribers(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        from database.models import EmailSubscriber
        subs = db.query(EmailSubscriber).filter(
            EmailSubscriber.client_profile_id == profile.id
        ).order_by(EmailSubscriber.created_at.desc()).all()
        return JSONResponse({"subscribers": [
            {"id": s.id, "email": s.email, "name": s.name or "", "tags": s.tags or "", "status": s.status.value if s.status else "active"}
            for s in subs
        ]})
    finally:
        db.close()


@router.post("/api/email/subscribers")
async def api_add_subscriber(request: Request):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        body = await request.json()
        email = body.get("email", "").strip()
        if not email or "@" not in email:
            return JSONResponse({"error": "Valid email required"}, status_code=400)

        from database.models import EmailSubscriber
        existing = db.query(EmailSubscriber).filter(
            EmailSubscriber.client_profile_id == profile.id,
            EmailSubscriber.email == email,
        ).first()
        if existing:
            return JSONResponse({"error": "Subscriber already exists"}, status_code=409)

        sub = EmailSubscriber(
            id=uuid.uuid4().hex,
            client_profile_id=profile.id,
            email=email,
            name=body.get("name", "").strip(),
            tags=body.get("tags", "").strip(),
        )
        db.add(sub)
        db.commit()
        return JSONResponse({"ok": True, "id": sub.id})
    finally:
        db.close()


@router.post("/api/email/subscribers/import")
async def api_import_subscribers(request: Request):
    """Import subscribers from CSV (columns: email, name, tags)."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        body = await request.json()
        csv_text = body.get("csv", "")
        if not csv_text:
            return JSONResponse({"error": "No CSV data"}, status_code=400)

        from database.models import EmailSubscriber
        reader = csv.DictReader(io.StringIO(csv_text))
        added = 0
        skipped = 0
        for row in reader:
            email = (row.get("email") or row.get("Email") or "").strip()
            if not email or "@" not in email:
                skipped += 1
                continue
            existing = db.query(EmailSubscriber).filter(
                EmailSubscriber.client_profile_id == profile.id,
                EmailSubscriber.email == email,
            ).first()
            if existing:
                skipped += 1
                continue
            sub = EmailSubscriber(
                id=uuid.uuid4().hex,
                client_profile_id=profile.id,
                email=email,
                name=(row.get("name") or row.get("Name") or "").strip(),
                tags=(row.get("tags") or row.get("Tags") or "").strip(),
            )
            db.add(sub)
            added += 1
        db.commit()
        return JSONResponse({"ok": True, "added": added, "skipped": skipped})
    finally:
        db.close()


@router.delete("/api/email/subscribers/{sub_id}")
async def api_delete_subscriber(request: Request, sub_id: str):
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        from database.models import EmailSubscriber
        sub = db.query(EmailSubscriber).filter(
            EmailSubscriber.id == sub_id,
            EmailSubscriber.client_profile_id == profile.id,
        ).first()
        if sub:
            db.delete(sub)
            db.commit()
        return JSONResponse({"ok": True})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY COMPAT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/email/process-inbox")
async def api_process_inbox_legacy(request: Request, background_tasks: BackgroundTasks):
    """Legacy endpoint — forwards to fetch-now."""
    return await api_fetch_now(request, background_tasks)

@router.get("/api/email/support-stats")
async def api_support_stats(request: Request):
    """Legacy support stats — returns thread counts from DB."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        if not profile:
            return JSONResponse({"stats": {}})

        from database.models import EmailThread, EmailMessageRecord
        total_threads = db.query(EmailThread).filter(
            EmailThread.client_profile_id == profile.id
        ).count()
        total_messages = db.query(EmailMessageRecord).filter(
            EmailMessageRecord.client_profile_id == profile.id,
            EmailMessageRecord.direction == "inbound",
        ).count()
        pending_drafts = db.query(EmailMessageRecord).filter(
            EmailMessageRecord.client_profile_id == profile.id,
            EmailMessageRecord.draft_status == "pending",
        ).count()

        return JSONResponse({"stats": {
            "last_run": datetime.utcnow().isoformat(),
            "processed": total_messages,
            "escalated": pending_drafts,
            "threads": total_threads,
        }})
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# HTML  —  Unified Email Page (/email)
# ══════════════════════════════════════════════════════════════════════════════

# Settings-style CSS shared across tabs
_EMAIL_CSS = """
.email-tabs{display:flex;gap:0;border-bottom:2px solid #e9ebee;margin-bottom:0}
.email-tab{padding:12px 24px;background:none;border:none;border-bottom:3px solid transparent;
  font-size:.88rem;font-weight:600;color:#606770;cursor:pointer;margin-bottom:-2px;transition:all .15s}
.email-tab.active{border-bottom-color:#5c6ac4;color:#5c6ac4;font-weight:700}
.email-tab:hover:not(.active){color:#1c1e21}
.email-pane{display:none;padding-top:24px}
.email-pane.active{display:block}
.card{background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:26px;margin-bottom:20px}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.75rem;font-weight:700}
.pill-green{background:#dcfce7;color:#166534} .pill-yellow{background:#fef9c3;color:#854d0e}
.pill-blue{background:#dbeafe;color:#1e40af} .pill-red{background:#fee2e2;color:#991b1b}
.pill-gray{background:#f3f4f6;color:#4b5563}
.btn{display:inline-block;padding:10px 22px;border-radius:10px;font-size:.88rem;font-weight:700;
  text-decoration:none;border:none;cursor:pointer;transition:all .15s}
.btn-primary{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff}
.btn-primary:hover{opacity:.9}
.btn-success{background:#16a34a;color:#fff}.btn-success:hover{opacity:.9}
.btn-danger{background:#dc2626;color:#fff}.btn-danger:hover{opacity:.9}
.btn-secondary{background:#f3f4f6;color:#374151;border:1px solid #d1d5db}
.btn-secondary:hover{background:#e5e7eb}
.btn-sm{padding:6px 14px;font-size:.8rem;border-radius:8px}
.banner-success{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;
  margin-bottom:16px;color:#166534;font-size:.87rem;font-weight:600}
.banner-warn{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 16px;
  margin-bottom:16px;color:#9a3412;font-size:.87rem;font-weight:600}
.thread-row{display:flex;align-items:center;padding:12px 14px;border-bottom:1px solid #f0f2f5;
  cursor:pointer;gap:12px;transition:background .1s}
.thread-row:hover{background:#f8f9fb}
.thread-sender{font-weight:700;font-size:.85rem;color:#1c1e21;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px}
.thread-subject{font-size:.84rem;color:#444;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.thread-time{font-size:.75rem;color:#90949c;white-space:nowrap}
.thread-detail{background:#fff;border-radius:14px;border:1px solid #e9ebee;padding:24px}
.msg-bubble{padding:14px 18px;border-radius:12px;margin-bottom:12px;max-width:85%;font-size:.86rem;line-height:1.6}
.msg-in{background:#f3f4f6;color:#1c1e21;align-self:flex-start}
.msg-out{background:#eef2ff;color:#1c1e21;align-self:flex-end}
.draft-box{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:16px;margin-top:14px}
.sub-table{width:100%;border-collapse:collapse;font-size:.84rem}
.sub-table th{text-align:left;padding:8px 12px;border-bottom:2px solid #e9ebee;font-size:.78rem;color:#606770;font-weight:700}
.sub-table td{padding:8px 12px;border-bottom:1px solid #f0f2f5}
"""


@router.get("/email", response_class=HTMLResponse)
async def email_page(request: Request):
    """Unified email hub: Connect · Inbox · Campaigns."""
    db = next(get_db())
    try:
        user, profile = get_user_context(request, db)
        if not user:
            return RedirectResponse("/account/login", status_code=303)
        if not profile:
            return RedirectResponse("/onboarding", status_code=303)

        # Which tab to show
        qp = dict(request.query_params)
        active_tab = qp.get("tab", "inbox")
        if active_tab not in ("connect", "inbox", "campaigns"):
            active_tab = "inbox"

        # Banner
        banner = ""
        if "connected" in qp:
            banner = '<div class="banner-success">&#x2705; Email connected successfully!</div>'
        elif "disconnected" in qp:
            banner = '<div class="banner-warn">&#x26D4; Email disconnected.</div>'
        elif qp.get("error") == "imap_auth":
            banner = '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px 16px;margin-bottom:16px;color:#991b1b;font-size:.87rem"><strong>Authentication failed.</strong> Double-check your email and app password.</div>'
        elif qp.get("error") == "imap_connect":
            banner = '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px 16px;margin-bottom:16px;color:#991b1b;font-size:.87rem"><strong>Could not connect to mail server.</strong> Verify the IMAP host and port.</div>'
        elif qp.get("error") == "agreement_required":
            banner = '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px 16px;margin-bottom:16px;color:#991b1b;font-size:.87rem"><strong>Agreement required.</strong> Please accept the AI Email Processing Agreement below before connecting your email.</div>'

        # Connection status
        from utils.email_service import get_connection_status
        conn_status = get_connection_status(profile.client_id)
        is_connected = conn_status["connected"]
        conn_provider = conn_status.get("provider", "")
        conn_email = conn_status.get("email", "")

        has_gmail_oauth = bool(os.getenv("GMAIL_CLIENT_ID"))
        has_ms_oauth = bool(os.getenv("MICROSOFT_CLIENT_ID"))

        # Check if user has accepted the email AI agreement
        has_agreed = bool(getattr(profile, "email_ai_agreed_at", None))

        # PROVIDER_IMAP_CONFIG for detect JS (reuse from settings_routes)
        try:
            from api.settings_routes import PROVIDER_IMAP_CONFIG
        except Exception:
            PROVIDER_IMAP_CONFIG = {}

        # ── CONNECT TAB ──────────────────────────────────────────────────
        if is_connected:
            _provider_icon = {"Gmail": "&#128231;", "Outlook": "&#128233;"}.get(conn_provider, "&#128231;")
            connect_html = f"""
<div class="card">
  <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
    <span style="font-size:1.6rem">{_provider_icon}</span>
    <div>
      <div style="font-weight:700;font-size:.95rem;color:#166534">{conn_provider} Connected</div>
      <div style="font-size:.84rem;color:#444">{conn_email}</div>
    </div>
    <span class="pill pill-green" style="margin-left:auto">Active</span>
  </div>
  <p style="font-size:.83rem;color:#606770;line-height:1.5;margin-bottom:16px">
    Your AI can read incoming emails, draft smart replies, and send campaigns from this inbox.
  </p>
  <div style="display:flex;gap:10px;flex-wrap:wrap">
    <form method="post" action="{'/settings/email/disconnect' if conn_status.get('type')=='gmail' else ('/email/disconnect-microsoft' if conn_status.get('type')=='microsoft' else '/settings/email/disconnect-imap')}" style="margin:0">
      <button type="submit" class="btn btn-danger btn-sm"
        onclick="return confirm('Disconnect email? AI will stop reading and replying.')">
        Disconnect
      </button>
    </form>
    <a href="/email?tab=inbox" class="btn btn-secondary btn-sm">Go to Inbox →</a>
  </div>
</div>
"""
        else:
            _gmail_btn = (
                '<a href="/settings/email/authorize" '
                'style="display:inline-flex;align-items:center;gap:8px;padding:10px 22px;font-size:.9rem;'
                'font-weight:600;text-decoration:none;background:#fff;border:1.5px solid #dadce0;'
                'border-radius:8px;color:#3c4043;cursor:pointer;transition:box-shadow .15s" '
                'onmouseover="this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.15)\'" '
                'onmouseout="this.style.boxShadow=\'none\'">'
                '<svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>'
                'Sign in with Google</a>'
            ) if has_gmail_oauth else '<p style="color:#888;font-size:.85rem">Gmail OAuth not configured yet.</p>'

            _ms_btn = (
                '<a href="/email/authorize-microsoft" '
                'style="display:inline-flex;align-items:center;gap:8px;padding:10px 22px;font-size:.9rem;'
                'font-weight:600;text-decoration:none;background:#fff;border:1.5px solid #dadce0;'
                'border-radius:8px;color:#3c4043;cursor:pointer;transition:box-shadow .15s" '
                'onmouseover="this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.15)\'" '
                'onmouseout="this.style.boxShadow=\'none\'">'
                '<svg width="18" height="18" viewBox="0 0 21 21"><rect x="1" y="1" width="9" height="9" fill="#F25022"/>'
                '<rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>'
                '<rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>'
                '<rect x="11" y="11" width="9" height="9" fill="#FFB900"/></svg>'
                'Sign in with Microsoft</a>'
            ) if has_ms_oauth else ''

            # -- Build agreement gate and agreement card as separate vars --
            _agreement_gate_html = ""
            _agreement_card_html = ""
            if not has_agreed:
                _agreement_gate_html = (
                    '<div id="agreement-gate" style="margin-top:18px;border-top:1px solid #e9ebee;padding-top:18px">'
                    '<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 16px;margin-bottom:14px">'
                    '<div style="font-weight:700;font-size:.88rem;color:#92400e;margin-bottom:6px">&#9888;&#65039; Agreement Required Before Connecting</div>'
                    '<p style="font-size:.82rem;color:#78350f;line-height:1.55;margin:0">'
                    'You must review and accept the AI Email Processing Agreement below before connecting your email inbox.'
                    '</p></div></div>'
                )
                _agreement_card_html = (
                    '<div class="card" id="email-agreement-card" style="border:1.5px solid #c7d2fe;background:linear-gradient(135deg,#f5f3ff 0%,#eff6ff 100%)">'
                    '<h3 style="font-size:.95rem;font-weight:700;margin-bottom:10px;color:#312e81">&#128220; AI Email Processing Agreement</h3>'
                    '<div style="max-height:340px;overflow-y:auto;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px;font-size:.82rem;color:#374151;line-height:1.7">'

                    '<p style="font-weight:700;color:#1e1b4b;margin-top:0">NEXARILY AI, INC. &#8212; ALITA AI EMAIL PROCESSING AGREEMENT</p>'
                    '<p style="color:#6b7280;font-size:.78rem">Effective upon acceptance. Last updated: March 2026.</p>'
                    '<p>By connecting your email account to Alita AI (the &#8220;Service&#8221;), operated by NexarilyAI (&#8220;Company&#8221;, &#8220;we&#8221;, &#8220;us&#8221;), you acknowledge and agree to the following terms:</p>'

                    '<p style="font-weight:700;color:#1e1b4b">1. PURPOSE &amp; SCOPE</p>'
                    '<p>When you connect your email inbox, the Service will: (a) read incoming email messages to categorize them (lead, support, general, spam); '
                    '(b) use artificial intelligence to draft suggested reply text based on your knowledge base and configured tone; '
                    '(c) send replies <strong>only upon your explicit approval</strong> unless you separately enable auto-send; '
                    'and (d) send email marketing campaigns you create through the Campaigns tab.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">2. AI-GENERATED CONTENT DISCLOSURE</p>'
                    '<p>All outbound emails sent through the Service that contain AI-drafted content will include a brief footer disclosing: '
                    '<em>&#8220;This email was composed with AI assistance via Alita AI.&#8221;</em> '
                    'This disclosure is required for legal compliance under consumer protection regulations and cannot be removed.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">3. HUMAN REVIEW &amp; APPROVAL</p>'
                    '<p>By default, AI-drafted replies are held in &#8220;pending&#8221; status for your manual review and approval before being sent. '
                    'You retain full editorial control. You are solely responsible for reviewing AI-generated content before approving it for delivery. '
                    'NexarilyAI shall not be liable for content you approve and send.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">4. DATA PROCESSING &amp; PRIVACY</p>'
                    '<p>(a) <strong>Email Content:</strong> We process email bodies and headers solely to provide the Service. '
                    'Email content is used for AI draft generation and is not sold to third parties. '
                    '(b) <strong>PII Handling:</strong> Personally identifiable information in emails is handled in accordance with our Privacy Policy. '
                    'We implement encryption in transit (TLS) and at rest. '
                    '(c) <strong>Data Retention:</strong> Email data is retained for the duration of your subscription and deleted within 30 days of account closure or email disconnection, unless otherwise required by law. '
                    '(d) <strong>GDPR / CCPA:</strong> If you or your contacts are subject to GDPR or CCPA, you are responsible for ensuring you have the legal basis to process their emails through the Service. '
                    'We act as a data processor on your behalf.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">5. CAN-SPAM &amp; EMAIL COMPLIANCE</p>'
                    '<p>(a) Marketing campaign emails will include an unsubscribe mechanism as required by CAN-SPAM. '
                    '(b) Support/transactional replies will use accurate header information and non-deceptive subject lines. '
                    '(c) You agree not to use the Service to send unsolicited commercial email (spam) or phishing content.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">6. YOUR RESPONSIBILITIES</p>'
                    '<p>You represent that: (a) you have authority to grant access to the email account you are connecting; '
                    '(b) you will comply with all applicable email laws (CAN-SPAM, GDPR, CASL, CCPA/CPRA, etc.); '
                    '(c) you will review AI-drafted content before approving it; '
                    '(d) you will not use the Service to engage in deceptive, illegal, or harmful communications.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">7. LIMITATION OF LIABILITY</p>'
                    '<p>NexarilyAI provides AI-drafted email content on an &#8220;as-is&#8221; basis. '
                    'We do not guarantee the accuracy, tone, or appropriateness of any AI-generated text. '
                    'You are solely responsible for reviewing and approving all outbound communications. '
                    'To the maximum extent permitted by law, NexarilyAI shall not be liable for any damages arising from emails you approve and send through the Service.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">8. RECORD OF AGREEMENT</p>'
                    '<p>Your acceptance of this agreement, including the date, time, and IP address, is permanently recorded in our systems. '
                    'This record may be used to demonstrate your informed consent in the event of a dispute.</p>'

                    '<p style="font-weight:700;color:#1e1b4b">9. MODIFICATIONS</p>'
                    '<p>We may update this agreement. Material changes will be communicated via email or in-app notification. '
                    'Continued use of the email features after notification constitutes acceptance of the updated terms.</p>'
                    '</div>'

                    '<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:16px">'
                    '<input type="checkbox" id="email-agree-cb" style="margin-top:3px;width:18px;height:18px;accent-color:#4f46e5;cursor:pointer;flex-shrink:0">'
                    '<label for="email-agree-cb" style="font-size:.84rem;color:#1e1b4b;line-height:1.5;cursor:pointer">'
                    'I have read and agree to the <strong>AI Email Processing Agreement</strong>. '
                    'I understand that AI-generated email replies will include a disclosure footer, '
                    'and that I am responsible for reviewing all AI-drafted content before sending.'
                    '</label></div>'

                    '<button id="accept-agreement-btn" class="btn btn-primary" disabled '
                    'style="opacity:.5;cursor:not-allowed;width:100%" '
                    'onclick="acceptEmailAgreement()">'
                    '&#9989; Accept Agreement &amp; Enable Email Connection</button>'
                    '<p style="font-size:.76rem;color:#9ca3af;margin-top:8px;margin-bottom:0;text-align:center">'
                    'Your acceptance will be permanently recorded with a timestamp and your IP address.</p>'
                    '</div>'

                    '<script>'
                    '(function(){'
                    'var cb=document.getElementById("email-agree-cb");'
                    'var btn=document.getElementById("accept-agreement-btn");'
                    'if(cb&&btn){cb.addEventListener("change",function(){'
                    'btn.disabled=!cb.checked;btn.style.opacity=cb.checked?"1":".5";'
                    'btn.style.cursor=cb.checked?"pointer":"not-allowed";});}'
                    '})();'
                    'async function acceptEmailAgreement(){'
                    'var btn=document.getElementById("accept-agreement-btn");'
                    'btn.disabled=true;btn.textContent="Recording agreement...";'
                    'try{var r=await fetch("/api/email/accept-agreement",{method:"POST",headers:{"Content-Type":"application/json"}});'
                    'var d=await r.json();'
                    'if(d.ok){window.location.reload();}else{'
                    'alert(d.error||"Failed to record agreement. Please try again.");'
                    'btn.disabled=false;btn.innerHTML="&#9989; Accept Agreement & Enable Email Connection";}}'
                    'catch(e){alert("Something went wrong. Please try again.");'
                    'btn.disabled=false;btn.innerHTML="&#9989; Accept Agreement & Enable Email Connection";}}'
                    '</script>'
                )

            connect_html = f"""
<div class="card">
  <h3 style="font-size:.95rem;font-weight:700;margin-bottom:6px;color:#1c1e21">Connect your email inbox</h3>
  <p style="font-size:.84rem;color:#606770;line-height:1.5;margin-bottom:18px">
    Connect your email so your AI can read incoming emails, draft smart replies, and send campaigns.
    Pick your provider below — it takes under 30 seconds.
  </p>

  <div id="connect-controls" style="{'display:block' if has_agreed else 'display:none'}">
  <!-- One-click OAuth providers -->
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">
    {_gmail_btn}
    {_ms_btn}
  </div>

  <!-- Divider -->
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px">
    <hr style="flex:1;border:none;border-top:1px solid #e9ebee">
    <span style="font-size:.8rem;color:#90949c;font-weight:600">OR CONNECT WITH APP PASSWORD</span>
    <hr style="flex:1;border:none;border-top:1px solid #e9ebee">
  </div>

  <!-- Email detect + IMAP form -->
  <div style="margin-bottom:12px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
      <input type="email" id="email-addr-inp" placeholder="you@yourcompany.com" autocomplete="email"
        style="flex:1;min-width:220px;max-width:340px;padding:9px 14px;border:1.5px solid #dde0e4;border-radius:8px;font-size:.9rem;outline:none"
        onfocus="this.style.borderColor='#5c6ac4'" onblur="this.style.borderColor='#dde0e4'">
      <span id="provider-badge" style="display:none;background:#e0f2fe;color:#0369a1;border-radius:20px;padding:4px 12px;font-size:.8rem;font-weight:600;white-space:nowrap"></span>
    </div>
    <div id="imap-section" style="display:none">
      <div id="imap-instr-box" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:11px 14px;margin-bottom:14px;font-size:.83rem;color:#1e40af;display:none">
        <span id="imap-instr"></span>&nbsp;
        <a id="imap-pw-link" href="#" target="_blank" style="font-weight:600;color:#1d4ed8">Get app password &#x2197;</a>
      </div>
      <form method="post" action="/settings/email/connect-imap" id="imap-form">
        <input type="hidden" id="imap-email-h" name="email">
        <input type="hidden" id="imap-provider-h" name="provider">
        <input type="hidden" id="imap-host-h" name="imap_host">
        <input type="hidden" id="imap-port-h" name="imap_port" value="993">
        <input type="hidden" id="imap-smtp-h" name="smtp_host">
        <input type="hidden" id="imap-smtpp-h" name="smtp_port" value="587">
        <div id="imap-manual" style="display:none;margin-bottom:14px">
          <div style="display:grid;grid-template-columns:1fr 80px 1fr 80px;gap:8px;align-items:end">
            <div><label style="font-size:.8rem;font-weight:600;color:#374151;display:block;margin-bottom:4px">IMAP Host</label>
              <input type="text" id="c-imap-host" placeholder="imap.yourdomain.com" style="width:100%;padding:8px 12px;border:1.5px solid #dde0e4;border-radius:7px;font-size:.85rem"></div>
            <div><label style="font-size:.8rem;font-weight:600;color:#374151;display:block;margin-bottom:4px">Port</label>
              <input type="number" id="c-imap-port" value="993" style="width:100%;padding:8px 12px;border:1.5px solid #dde0e4;border-radius:7px;font-size:.85rem"></div>
            <div><label style="font-size:.8rem;font-weight:600;color:#374151;display:block;margin-bottom:4px">SMTP Host</label>
              <input type="text" id="c-smtp-host" placeholder="smtp.yourdomain.com" style="width:100%;padding:8px 12px;border:1.5px solid #dde0e4;border-radius:7px;font-size:.85rem"></div>
            <div><label style="font-size:.8rem;font-weight:600;color:#374151;display:block;margin-bottom:4px">Port</label>
              <input type="number" id="c-smtp-port" value="587" style="width:100%;padding:8px 12px;border:1.5px solid #dde0e4;border-radius:7px;font-size:.85rem"></div>
          </div>
        </div>
        <div style="margin-bottom:16px">
          <label style="font-size:.8rem;font-weight:600;color:#374151;display:block;margin-bottom:5px">
            App Password <span style="font-weight:400;color:#9ca3af">(not your regular login password)</span>
          </label>
          <input type="password" name="password" required placeholder="Paste your app password here"
            style="width:100%;max-width:380px;padding:9px 14px;border:1.5px solid #dde0e4;border-radius:8px;font-size:.9rem;outline:none"
            onfocus="this.style.borderColor='#5c6ac4'" onblur="this.style.borderColor='#dde0e4'">
        </div>
        <button type="submit" class="btn btn-primary btn-sm">Connect Email</button>
      </form>
    </div>
  </div>
  </div><!-- end connect-controls -->

  {_agreement_gate_html}

  <p style="font-size:.8rem;color:#9ca3af;margin-top:14px;margin-bottom:0">
    Supports Gmail, Outlook, Hotmail, Yahoo, AOL, iCloud, Zoho, Fastmail, GMX, AT&amp;T, Comcast, and any IMAP provider.
  </p>
</div>

{_agreement_card_html}

<div class="card">
  <h3 style="font-size:.92rem;font-weight:700;margin-bottom:8px">How it works</h3>
  <ol style="padding-left:20px;line-height:2;font-size:.86rem;color:#444;margin:0">
    <li>Connect your email inbox above</li>
    <li>Incoming emails are automatically categorised (lead, support, general, spam)</li>
    <li>Your AI drafts a reply using your knowledge base and tone</li>
    <li>Review and approve drafts in the Inbox tab, or let them send automatically</li>
    <li>High-priority emails generate a notification</li>
  </ol>
</div>
"""

        # ── INBOX TAB ────────────────────────────────────────────────────
        inbox_html = f"""
<div id="inbox-container">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px">
    <div>
      <span style="font-size:.88rem;font-weight:700;color:#1c1e21">Email Inbox</span>
      <span class="pill {'pill-green' if is_connected else 'pill-yellow'}" style="margin-left:8px">
        {'Connected' if is_connected else 'Not connected'}
      </span>
    </div>
    <button onclick="fetchNow()" class="btn btn-success btn-sm" id="fetch-btn">
      &#128229; Fetch New Emails
    </button>
  </div>
  <div id="fetch-status" style="font-size:.83rem;color:#606770;margin-bottom:12px"></div>

  <!-- Thread list + detail split -->
  <div style="display:grid;grid-template-columns:minmax(280px,380px) 1fr;gap:18px;min-height:400px" id="inbox-grid">
    <div style="border:1px solid #e9ebee;border-radius:12px;overflow:hidden;background:#fff">
      <div style="padding:10px 14px;border-bottom:1px solid #e9ebee;background:#f8f9fb;font-size:.8rem;font-weight:700;color:#606770">
        CONVERSATIONS
      </div>
      <div id="thread-list" style="max-height:500px;overflow-y:auto">
        <p style="padding:20px;color:#90949c;font-size:.84rem;text-align:center">
          {'Click "Fetch New Emails" to check your inbox.' if is_connected else 'Connect your email first to see your inbox.'}
        </p>
      </div>
    </div>
    <div id="thread-detail" class="thread-detail" style="min-height:400px">
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:#90949c;font-size:.88rem">
        Select a conversation to view
      </div>
    </div>
  </div>
</div>
"""

        # ── CAMPAIGNS TAB ────────────────────────────────────────────────
        try:
            from agents.email_marketing_agent import CampaignType, CampaignGoal, AudienceSegment
            ct_opts = "".join(f'<option value="{e.value}">{e.value.replace("_"," ").title()}</option>' for e in CampaignType)
            cg_opts = "".join(f'<option value="{e.value}">{e.value.replace("_"," ").title()}</option>' for e in CampaignGoal)
            seg_opts = "".join(f'<option value="{e.value}">{e.value.replace("_"," ").title()}</option>' for e in AudienceSegment)
        except Exception:
            ct_opts = '<option value="newsletter">Newsletter</option><option value="promotional">Promotional</option>'
            cg_opts = '<option value="engagement">Engagement</option><option value="sales">Sales</option>'
            seg_opts = '<option value="all_subscribers">All Subscribers</option>'

        campaigns_html = f"""
<!-- Subscriber Management -->
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:16px">
    <h3 style="font-size:.95rem;font-weight:700;margin:0">&#128101; Subscribers</h3>
    <div style="display:flex;gap:8px">
      <button onclick="showAddSub()" class="btn btn-primary btn-sm">+ Add Subscriber</button>
      <button onclick="showImportCSV()" class="btn btn-secondary btn-sm">&#128196; Import CSV</button>
    </div>
  </div>
  <div id="add-sub-form" style="display:none;margin-bottom:14px;padding:14px;background:#f8f9fb;border-radius:10px">
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
      <div><label style="font-size:.78rem;font-weight:600;display:block;margin-bottom:4px">Email *</label>
        <input type="email" id="sub-email" placeholder="name@example.com" style="padding:8px 12px;border:1px solid #dde0e4;border-radius:7px;font-size:.84rem;width:220px"></div>
      <div><label style="font-size:.78rem;font-weight:600;display:block;margin-bottom:4px">Name</label>
        <input type="text" id="sub-name" placeholder="John Smith" style="padding:8px 12px;border:1px solid #dde0e4;border-radius:7px;font-size:.84rem;width:160px"></div>
      <div><label style="font-size:.78rem;font-weight:600;display:block;margin-bottom:4px">Tags</label>
        <input type="text" id="sub-tags" placeholder="vip, lead" style="padding:8px 12px;border:1px solid #dde0e4;border-radius:7px;font-size:.84rem;width:140px"></div>
      <button onclick="addSubscriber()" class="btn btn-success btn-sm">Add</button>
      <button onclick="document.getElementById('add-sub-form').style.display='none'" class="btn btn-secondary btn-sm">Cancel</button>
    </div>
  </div>
  <div id="import-csv-form" style="display:none;margin-bottom:14px;padding:14px;background:#f8f9fb;border-radius:10px">
    <p style="font-size:.82rem;color:#606770;margin-bottom:8px">Paste CSV with columns: <strong>email, name, tags</strong></p>
    <textarea id="csv-text" rows="4" placeholder="email,name,tags&#10;john@example.com,John Smith,lead&#10;jane@example.com,Jane Doe,vip"
      style="width:100%;padding:8px 12px;border:1px solid #dde0e4;border-radius:7px;font-size:.84rem;resize:vertical;margin-bottom:8px"></textarea>
    <div style="display:flex;gap:8px">
      <button onclick="importCSV()" class="btn btn-success btn-sm">Import</button>
      <button onclick="document.getElementById('import-csv-form').style.display='none'" class="btn btn-secondary btn-sm">Cancel</button>
    </div>
  </div>
  <div id="sub-status" style="font-size:.83rem;color:#606770;margin-bottom:8px"></div>
  <div id="sub-list"></div>
</div>

<!-- Campaign Planner -->
<div class="card">
  <h3 style="font-size:.95rem;font-weight:700;margin-bottom:16px">&#129504; Plan a New Campaign</h3>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
    <div><label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Campaign Type</label>
      <select id="f-ct" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;background:#fff">{ct_opts}</select></div>
    <div><label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Campaign Goal</label>
      <select id="f-cg" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;background:#fff">{cg_opts}</select></div>
    <div><label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Audience Segment</label>
      <select id="f-seg" style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;background:#fff">{seg_opts}</select></div>
    <div style="grid-column:1/-1"><label style="font-size:.78rem;font-weight:600;color:#444;display:block;margin-bottom:5px">Content Brief *</label>
      <textarea id="f-brief" rows="3" placeholder="Describe the campaign: what's the offer, hook, or message?"
        style="width:100%;padding:9px 12px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;resize:vertical"></textarea></div>
  </div>
  <input id="f-ind" type="hidden" value="{profile.niche or ''}" />
  <div style="display:flex;align-items:center;gap:12px;margin-top:16px">
    <button onclick="planCampaign()" class="btn btn-primary">&#129504; Generate Campaign Plan</button>
    <span id="m-status" style="font-size:.83rem;color:#606770"></span>
  </div>
</div>

<!-- Past campaigns -->
<div class="card">
  <h3 style="font-size:.95rem;font-weight:700;margin-bottom:16px">&#128196; Campaign History</h3>
  <div id="plans-list"><p style="color:#90949c;font-size:.84rem">Loading...</p></div>
</div>
"""

        # ── Assemble the page ────────────────────────────────────────────
        def _tab_cls(tab):
            return "email-tab active" if tab == active_tab else "email-tab"

        body_html = f"""
<div style="max-width:1020px;margin:0 auto">
  {banner}
  <div style="margin-bottom:4px">
    <h1 style="font-size:1.4rem;font-weight:800;margin-bottom:4px">&#128231; Email</h1>
    <p style="font-size:.86rem;color:#606770;max-width:600px">Connect your email, manage your inbox with AI-powered replies, and run campaigns — all from one place.</p>
  </div>
  <div class="email-tabs">
    <button class="{_tab_cls('connect')}" onclick="switchTab('connect')">&#128268; Connect</button>
    <button class="{_tab_cls('inbox')}" onclick="switchTab('inbox')">&#128229; Inbox</button>
    <button class="{_tab_cls('campaigns')}" onclick="switchTab('campaigns')">&#128140; Campaigns</button>
  </div>
  <div class="email-pane {'active' if active_tab=='connect' else ''}" id="pane-connect">{connect_html}</div>
  <div class="email-pane {'active' if active_tab=='inbox' else ''}" id="pane-inbox">{inbox_html}</div>
  <div class="email-pane {'active' if active_tab=='campaigns' else ''}" id="pane-campaigns">{campaigns_html}</div>
</div>
"""

        js = r"""
// ── Tab switching ────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.email-tab').forEach((el,i) => {
    const tabs = ['connect','inbox','campaigns'];
    el.classList.toggle('active', tabs[i]===tab);
  });
  document.querySelectorAll('.email-pane').forEach(el => el.classList.remove('active'));
  const pane = document.getElementById('pane-'+tab);
  if(pane) pane.classList.add('active');
  history.replaceState(null,'','/email?tab='+tab);
  if(tab==='inbox') loadThreads();
  if(tab==='campaigns'){loadPlans();loadSubscribers();}
}

// ── IMAP detect (reuse settings logic) ──────────────────────────────
(function(){
  var t;
  var inp=document.getElementById('email-addr-inp');
  if(!inp) return;
  inp.addEventListener('input',function(){
    clearTimeout(t);
    var v=this.value.trim(), parts=v.split('@');
    if(parts.length<2||!parts[1]||!parts[1].includes('.')){hide();return;}
    t=setTimeout(function(){detect(v);},480);
  });
  function hide(){
    document.getElementById('provider-badge').style.display='none';
    document.getElementById('imap-section').style.display='none';
  }
  async function detect(email){
    try{
      var r=await fetch('/settings/email/detect-provider?email='+encodeURIComponent(email));
      var d=await r.json();
      var badge=document.getElementById('provider-badge');
      badge.textContent=d.label||'Unknown';
      badge.style.display='inline-block';
      if(d.provider==='gmail'){
        document.getElementById('imap-section').style.display='none';
      } else {
        document.getElementById('imap-section').style.display='block';
        set('imap-email-h',email);set('imap-provider-h',d.provider||'custom');
        set('imap-host-h',d.imap_host||'');set('imap-port-h',d.imap_port||993);
        set('imap-smtp-h',d.smtp_host||'');set('imap-smtpp-h',d.smtp_port||587);
        document.getElementById('imap-manual').style.display=(d.provider==='custom')?'block':'none';
        var ibox=document.getElementById('imap-instr-box');
        if(d.instructions){
          document.getElementById('imap-instr').textContent=d.instructions;
          var lnk=document.getElementById('imap-pw-link');
          lnk.href=d.app_password_url||'#';
          lnk.textContent='Get app password for '+d.label+' \u2197';
          ibox.style.display='block';
        } else {ibox.style.display='none';}
      }
    }catch(e){console.error(e);}
  }
  function set(id,val){var el=document.getElementById(id);if(el) el.value=val;}
  var fm={'c-imap-host':'imap-host-h','c-imap-port':'imap-port-h','c-smtp-host':'imap-smtp-h','c-smtp-port':'imap-smtpp-h'};
  Object.keys(fm).forEach(function(id){var el=document.getElementById(id);if(!el) return;el.addEventListener('input',function(){set(fm[id],this.value);});});
})();

// ── Inbox ────────────────────────────────────────────────────────────
let _currentThreadId = null;

async function fetchNow(){
  const btn=document.getElementById('fetch-btn');
  const st=document.getElementById('fetch-status');
  btn.disabled=true; btn.textContent='Fetching...';
  st.textContent='';
  try{
    const r=await fetch('/api/email/fetch-now',{method:'POST',headers:{'Content-Type':'application/json'}});
    const d=await r.json();
    st.textContent=d.ok?d.message:(d.error||'Error');
    if(d.ok) setTimeout(loadThreads, 3000);
  }catch(e){st.textContent=e.message;}
  btn.disabled=false;btn.textContent='\u{1F4E5} Fetch New Emails';
}

async function loadThreads(){
  try{
    const r=await fetch('/api/email/inbox');
    const d=await r.json();
    const el=document.getElementById('thread-list');
    if(!d.threads||d.threads.length===0){
      el.innerHTML='<p style="padding:20px;color:#90949c;font-size:.84rem;text-align:center">No emails yet. Click Fetch to check your inbox.</p>';
      return;
    }
    const catPill={lead:'pill-blue',support:'pill-yellow',general:'pill-gray',spam:'pill-red'};
    let html=d.threads.map(t=>{
      const time=t.last_message_at?new Date(t.last_message_at).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'';
      const draft=t.has_pending_draft?'<span class="pill pill-yellow" style="font-size:.68rem;margin-left:4px">Draft</span>':'';
      return `<div class="thread-row" onclick="openThread('${t.id}')">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="thread-sender">${t.sender_name||t.sender_email}</span>
            <span class="pill ${catPill[t.category]||'pill-gray'}" style="font-size:.68rem">${t.category}</span>
            ${draft}
          </div>
          <div class="thread-subject">${t.subject}</div>
        </div>
        <div class="thread-time">${time}</div>
      </div>`;
    }).join('');
    el.innerHTML=html;
  }catch(e){console.error(e);}
}

async function openThread(tid){
  _currentThreadId=tid;
  const el=document.getElementById('thread-detail');
  el.innerHTML='<div style="padding:20px;color:#90949c">Loading...</div>';
  try{
    const r=await fetch('/api/email/thread/'+tid);
    const d=await r.json();
    if(!d.messages){el.innerHTML='<p style="padding:20px;color:#c62828">Thread not found</p>';return;}
    let html=`<div style="margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #e9ebee">
      <h3 style="font-size:.95rem;font-weight:700;margin-bottom:4px">${d.thread.subject||'(no subject)'}</h3>
      <span class="pill ${d.thread.category==='lead'?'pill-blue':d.thread.category==='support'?'pill-yellow':'pill-gray'}">${d.thread.category}</span>
    </div><div style="display:flex;flex-direction:column;gap:4px">`;
    for(const m of d.messages){
      if(m.direction==='inbound'){
        html+=`<div class="msg-bubble msg-in">
          <div style="font-size:.78rem;font-weight:700;margin-bottom:4px">${m.sender_name||m.sender_email} <span style="font-weight:400;color:#90949c">${m.received_at?new Date(m.received_at).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):''}</span></div>
          <div style="white-space:pre-wrap">${escHtml(m.body_text)}</div>
        </div>`;
        if(m.draft_status==='pending'&&m.ai_draft_reply){
          html+=`<div class="draft-box">
            <div style="font-size:.78rem;font-weight:700;color:#92400e;margin-bottom:6px">&#129504; AI Draft Reply</div>
            <textarea id="draft-${m.id}" style="width:100%;min-height:80px;padding:10px;border:1px solid #fde68a;border-radius:8px;font-size:.84rem;resize:vertical;margin-bottom:10px">${escHtml(m.ai_draft_reply)}</textarea>
            <div style="display:flex;gap:8px">
              <button onclick="approveDraft('${m.id}')" class="btn btn-success btn-sm">&#x2705; Approve & Send</button>
              <button onclick="editDraft('${m.id}')" class="btn btn-secondary btn-sm">&#x270F; Save Edit</button>
              <button onclick="rejectDraft('${m.id}')" class="btn btn-danger btn-sm">&#x274C; Reject</button>
            </div>
          </div>`;
        } else if(m.draft_status==='sent'){
          html+=`<div style="font-size:.78rem;color:#16a34a;margin-bottom:8px;padding-left:18px">&#x2705; AI reply sent</div>`;
        } else if(m.draft_status==='rejected'){
          html+=`<div style="font-size:.78rem;color:#dc2626;margin-bottom:8px;padding-left:18px">&#x274C; Draft rejected</div>`;
        }
      } else {
        html+=`<div class="msg-bubble msg-out">
          <div style="font-size:.78rem;font-weight:700;margin-bottom:4px;color:#5c6ac4">You <span style="font-weight:400;color:#90949c">${m.received_at?new Date(m.received_at).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):''}</span></div>
          <div style="white-space:pre-wrap">${escHtml(m.body_text)}</div>
        </div>`;
      }
    }
    html+=`</div>`;
    // Manual reply box
    html+=`<div style="margin-top:18px;padding-top:14px;border-top:1px solid #e9ebee">
      <textarea id="manual-reply" placeholder="Write a reply..." style="width:100%;min-height:70px;padding:10px;border:1px solid #dde0e4;border-radius:8px;font-size:.84rem;resize:vertical;margin-bottom:8px"></textarea>
      <button onclick="sendManualReply('${tid}')" class="btn btn-primary btn-sm">&#128228; Send Reply</button>
    </div>`;
    el.innerHTML=html;
  }catch(e){el.innerHTML='<p style="padding:20px;color:#c62828">'+e.message+'</p>';}
}

function escHtml(s){
  const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;
}

async function approveDraft(mid){
  try{
    const r=await fetch('/api/email/approve-draft/'+mid,{method:'POST',headers:{'Content-Type':'application/json'}});
    const d=await r.json();
    alert(d.ok?'Reply sent!':('Error: '+(d.error||'Unknown')));
    if(_currentThreadId) openThread(_currentThreadId);
    loadThreads();
  }catch(e){alert(e.message);}
}
async function rejectDraft(mid){
  try{
    await fetch('/api/email/reject-draft/'+mid,{method:'POST'});
    if(_currentThreadId) openThread(_currentThreadId);
    loadThreads();
  }catch(e){alert(e.message);}
}
async function editDraft(mid){
  const txt=document.getElementById('draft-'+mid);
  if(!txt) return;
  try{
    await fetch('/api/email/edit-draft/'+mid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft_text:txt.value})});
    alert('Draft saved');
  }catch(e){alert(e.message);}
}
async function sendManualReply(tid){
  const txt=document.getElementById('manual-reply');
  if(!txt||!txt.value.trim()){alert('Please type a reply');return;}
  try{
    const r=await fetch('/api/email/manual-reply/'+tid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reply_text:txt.value})});
    const d=await r.json();
    alert(d.ok?'Reply sent!':('Error: '+(d.error||'Unknown')));
    if(_currentThreadId) openThread(_currentThreadId);
    loadThreads();
  }catch(e){alert(e.message);}
}

// ── Campaigns ────────────────────────────────────────────────────────
async function planCampaign(){
  const st=document.getElementById('m-status');
  st.textContent='\u23F3 Generating campaign plan...';
  try{
    const r=await fetch('/api/email/plan-campaign',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({campaign_type:document.getElementById('f-ct').value,campaign_goal:document.getElementById('f-cg').value,
        target_segment:document.getElementById('f-seg').value,industry:document.getElementById('f-ind').value,
        content_brief:document.getElementById('f-brief').value})});
    const d=await r.json();
    st.textContent=d.ok?('\u2713 Plan created'):('\u2717 '+(d.error||'Error'));
    loadPlans();
  }catch(e){st.textContent='\u2717 '+e.message;}
}

async function loadPlans(){
  try{
    const r=await fetch('/api/email/campaigns');
    const d=await r.json();
    const el=document.getElementById('plans-list');
    if(!el) return;
    if(!d.plans||d.plans.length===0){
      el.innerHTML='<p style="color:#90949c;font-size:.84rem">No campaigns yet. Create your first above.</p>';
      return;
    }
    el.innerHTML=d.plans.map(p=>`
      <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid #f0f2f5;flex-wrap:wrap;gap:8px">
        <div>
          <span style="font-size:.82rem;font-weight:700">${p.campaign_type} \u2192 ${p.campaign_goal}</span>
          <span style="font-size:.76rem;color:#90949c;margin-left:10px">${p.created_at}</span>
          <span class="pill ${p.status==='sent'?'pill-green':p.status==='sending'?'pill-yellow':'pill-gray'}" style="margin-left:6px;font-size:.68rem">${p.status||'draft'}</span>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <span style="font-size:.76rem;background:#e8f5e9;color:#2e7d32;padding:2px 9px;border-radius:99px;font-weight:700">~${p.est_open_rate||'?'}% open</span>
          <span style="font-size:.76rem;background:#e8eaf6;color:#3949ab;padding:2px 9px;border-radius:99px;font-weight:700">${p.subject_lines_count} subjects</span>
          ${p.sent_count>0?`<span style="font-size:.76rem;color:#16a34a">${p.sent_count}/${p.total_recipients} sent</span>`:''}
        </div>
      </div>`).join('');
  }catch(e){console.error(e);}
}

// ── Subscribers ──────────────────────────────────────────────────────
function showAddSub(){document.getElementById('add-sub-form').style.display='block';document.getElementById('import-csv-form').style.display='none';}
function showImportCSV(){document.getElementById('import-csv-form').style.display='block';document.getElementById('add-sub-form').style.display='none';}

async function loadSubscribers(){
  try{
    const r=await fetch('/api/email/subscribers');
    const d=await r.json();
    const el=document.getElementById('sub-list');
    if(!el) return;
    if(!d.subscribers||d.subscribers.length===0){
      el.innerHTML='<p style="color:#90949c;font-size:.84rem">No subscribers yet. Add one above or import a CSV.</p>';
      return;
    }
    let html='<table class="sub-table"><thead><tr><th>Email</th><th>Name</th><th>Tags</th><th>Status</th><th></th></tr></thead><tbody>';
    for(const s of d.subscribers){
      html+=`<tr><td>${s.email}</td><td>${s.name||'—'}</td><td>${s.tags||'—'}</td>
        <td><span class="pill ${s.status==='active'?'pill-green':'pill-red'}">${s.status}</span></td>
        <td><button onclick="deleteSub('${s.id}')" style="background:none;border:none;color:#dc2626;cursor:pointer;font-size:.8rem">\u2716</button></td></tr>`;
    }
    html+='</tbody></table>';
    el.innerHTML=html;
  }catch(e){console.error(e);}
}

async function addSubscriber(){
  const email=document.getElementById('sub-email').value;
  const name=document.getElementById('sub-name').value;
  const tags=document.getElementById('sub-tags').value;
  const st=document.getElementById('sub-status');
  if(!email){st.textContent='Email is required';return;}
  try{
    const r=await fetch('/api/email/subscribers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,name,tags})});
    const d=await r.json();
    st.textContent=d.ok?'Subscriber added':(d.error||'Error');
    document.getElementById('add-sub-form').style.display='none';
    loadSubscribers();
  }catch(e){st.textContent=e.message;}
}

async function importCSV(){
  const csv=document.getElementById('csv-text').value;
  const st=document.getElementById('sub-status');
  if(!csv.trim()){st.textContent='Paste CSV data';return;}
  try{
    const r=await fetch('/api/email/subscribers/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv})});
    const d=await r.json();
    st.textContent=d.ok?`Imported ${d.added}, skipped ${d.skipped}`:(d.error||'Error');
    document.getElementById('import-csv-form').style.display='none';
    loadSubscribers();
  }catch(e){st.textContent=e.message;}
}

async function deleteSub(id){
  if(!confirm('Remove this subscriber?')) return;
  try{
    await fetch('/api/email/subscribers/'+id,{method:'DELETE'});
    loadSubscribers();
  }catch(e){console.error(e);}
}

// ── Init ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded',function(){
  const tab=new URLSearchParams(window.location.search).get('tab')||'inbox';
  if(tab==='inbox') loadThreads();
  if(tab==='campaigns'){loadPlans();loadSubscribers();}
});
"""

        return HTMLResponse(build_page(
            title="Email",
            active_nav="email",
            body_content=body_html,
            extra_css=_EMAIL_CSS,
            extra_js=js,
            user_name=user.full_name,
            business_name=profile.business_name,
        ))
    finally:
        db.close()


# ── Legacy redirects ─────────────────────────────────────────────────────────

@router.get("/email/dashboard", response_class=HTMLResponse)
async def email_dashboard_redirect(request: Request):
    return RedirectResponse("/email?tab=campaigns", status_code=301)

@router.get("/email/campaigns", response_class=HTMLResponse)
async def email_campaigns_redirect(request: Request):
    return RedirectResponse("/email?tab=campaigns", status_code=301)

@router.get("/email/support", response_class=HTMLResponse)
async def email_support_redirect(request: Request):
    return RedirectResponse("/email?tab=inbox", status_code=301)
