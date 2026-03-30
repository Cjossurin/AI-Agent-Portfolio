"""
utils/email_service.py — Unified email service dispatcher.

Single entry-point for ALL email I/O in Alita:
  • get_connection(client_id) — which provider is connected?
  • fetch_inbox(client_id, …) — read emails (Gmail API / Microsoft Graph / IMAP)
  • send_email(client_id, …) — send a single email
  • send_campaign_batch(client_id, recipients, …) — bulk send with rate-limiting

Supported connection types:
  1. Gmail OAuth 2.0  (google-auth + Gmail API)
  2. Microsoft OAuth 2.0  (MSAL / Graph API — Outlook, Hotmail, Live)
  3. IMAP + App-Password  (Yahoo, iCloud, Zoho, custom domains)
"""

import os
import asyncio
import imaplib
import smtplib
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header as _decode_header_raw
from typing import Any, Dict, List, Optional

# ── Helpers ──────────────────────────────────────────────────────────────────

def _fernet():
    """Return a Fernet instance, or None when TOKEN_ENCRYPTION_KEY is unset."""
    try:
        from cryptography.fernet import Fernet
        key = os.getenv("TOKEN_ENCRYPTION_KEY")
        if key:
            return Fernet(key.encode())
    except Exception:
        pass
    return None

def _decrypt(enc_text: str) -> str:
    """Decrypt a Fernet-encrypted string. Falls back to raw if key is unavailable."""
    f = _fernet()
    if f and enc_text:
        try:
            return f.decrypt(enc_text.encode()).decode()
        except Exception:
            pass
    return enc_text or ""

def _encrypt(plain: str) -> str:
    """Encrypt a string with Fernet. Falls back to raw if key is unavailable."""
    f = _fernet()
    if f and plain:
        return f.encrypt(plain.encode()).decode()
    return plain


# ═════════════════════════════════════════════════════════════════════════════
# 1. CONNECTION LOOKUP
# ═════════════════════════════════════════════════════════════════════════════

def get_connection(client_id: str) -> Optional[Dict[str, Any]]:
    """
    Return email connection credentials for *client_id*.

    Checks in order:  Gmail OAuth → Microsoft OAuth → IMAP/App-Password → None.

    Returns dict with ``type`` key = ``'gmail'`` | ``'microsoft'`` | ``'imap'``,
    plus the relevant credential fields.
    """
    try:
        from database.db import get_db
        from database.models import (
            ClientProfile, GmailOAuthToken, MicrosoftOAuthToken, EmailIMAPConnection,
        )
        db = next(get_db())
        profile = db.query(ClientProfile).filter(
            ClientProfile.client_id == client_id
        ).first()
        if not profile:
            db.close()
            return None

        # 1. Gmail OAuth
        gtok = db.query(GmailOAuthToken).filter(
            GmailOAuthToken.client_profile_id == profile.id
        ).first()
        if gtok:
            db.close()
            return {
                "type": "gmail",
                "email": gtok.email_address,
                "refresh_token": _decrypt(gtok.refresh_token_enc),
            }

        # 2. Microsoft OAuth
        mtok = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.client_profile_id == profile.id
        ).first()
        if mtok:
            db.close()
            return {
                "type": "microsoft",
                "email": mtok.email_address,
                "access_token": _decrypt(mtok.access_token_enc),
                "refresh_token": _decrypt(mtok.refresh_token_enc),
                "expires_at": mtok.token_expires_at,
                "profile_id": mtok.client_profile_id,
            }

        # 3. IMAP / App-Password
        itok = db.query(EmailIMAPConnection).filter(
            EmailIMAPConnection.client_profile_id == profile.id
        ).first()
        if itok:
            db.close()
            return {
                "type": "imap",
                "email": itok.email_address,
                "password": _decrypt(itok.password_enc),
                "imap_host": itok.imap_host,
                "imap_port": itok.imap_port,
                "smtp_host": itok.smtp_host,
                "smtp_port": itok.smtp_port,
            }

        db.close()
    except Exception as e:
        print(f"[email_service] get_connection error: {e}")
    return None


def get_connection_status(client_id: str) -> Dict[str, Any]:
    """Return a summary dict suitable for UI display."""
    conn = get_connection(client_id)
    if not conn:
        return {"connected": False, "provider": None, "email": None}
    prov_label = {"gmail": "Gmail", "microsoft": "Outlook", "imap": "IMAP"}.get(conn["type"], conn["type"])
    return {"connected": True, "provider": prov_label, "email": conn.get("email", ""), "type": conn["type"]}


# ═════════════════════════════════════════════════════════════════════════════
# 2. MICROSOFT TOKEN REFRESH
# ═════════════════════════════════════════════════════════════════════════════

async def _refresh_microsoft_token(conn: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh Microsoft access token if expired. Updates DB row. Returns updated conn."""
    expires = conn.get("expires_at")
    if expires and isinstance(expires, datetime) and expires > datetime.utcnow() + timedelta(minutes=5):
        return conn  # Still valid

    import httpx
    client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("[email_service] MICROSOFT_CLIENT_ID/SECRET not set — cannot refresh token")
        return conn

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": conn["refresh_token"],
                "grant_type": "refresh_token",
                "scope": "openid email Mail.Read Mail.Send offline_access",
            },
        )
    if resp.status_code != 200:
        print(f"[email_service] Microsoft token refresh failed: {resp.text}")
        return conn

    data = resp.json()
    new_access = data.get("access_token", "")
    new_refresh = data.get("refresh_token", conn["refresh_token"])
    expires_in = int(data.get("expires_in", 3600))
    new_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Update DB
    try:
        from database.db import get_db
        from database.models import MicrosoftOAuthToken
        db = next(get_db())
        tok = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.client_profile_id == conn["profile_id"]
        ).first()
        if tok:
            tok.access_token_enc = _encrypt(new_access)
            tok.refresh_token_enc = _encrypt(new_refresh)
            tok.token_expires_at = new_expires_at
            tok.updated_at = datetime.utcnow()
            db.commit()
        db.close()
    except Exception as e:
        print(f"[email_service] Could not persist refreshed MS token: {e}")

    conn["access_token"] = new_access
    conn["refresh_token"] = new_refresh
    conn["expires_at"] = new_expires_at
    return conn


# ═════════════════════════════════════════════════════════════════════════════
# 3. GMAIL API HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _get_gmail_service(refresh_token: str):
    """Build a gmail API service object from a refresh token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GMAIL_CLIENT_ID"),
        client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send"],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


async def _fetch_inbox_gmail(conn: Dict[str, Any], max_results: int = 20,
                              unread_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch emails via Gmail API."""
    import base64

    def _sync():
        svc = _get_gmail_service(conn["refresh_token"])
        q = "in:inbox" + (" is:unread" if unread_only else "")
        resp = svc.users().messages().list(
            userId="me", q=q, maxResults=max_results
        ).execute()
        messages = resp.get("messages", [])
        results = []
        for m_stub in messages:
            msg = svc.users().messages().get(
                userId="me", id=m_stub["id"], format="full"
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            # Extract body
            body = ""
            payload = msg.get("payload", {})

            def _extract_body(part):
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                for sub in part.get("parts", []):
                    r = _extract_body(sub)
                    if r:
                        return r
                return ""

            body = _extract_body(payload)
            if not body and payload.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

            sender_raw = headers.get("from", "")
            sender_name, sender_email = "", sender_raw
            if "<" in sender_raw and ">" in sender_raw:
                sender_name = sender_raw[:sender_raw.index("<")].strip().strip('"')
                sender_email = sender_raw[sender_raw.index("<") + 1:sender_raw.index(">")].strip()

            results.append({
                "message_id": msg.get("id", ""),
                "thread_id": msg.get("threadId", ""),
                "sender_email": sender_email,
                "sender_name": sender_name,
                "subject": headers.get("subject", ""),
                "date": headers.get("date", ""),
                "body": body,
                "snippet": msg.get("snippet", body[:200]),
                "labels": msg.get("labelIds", []),
            })
        return results

    return await asyncio.get_running_loop().run_in_executor(None, _sync)


async def _send_gmail(conn: Dict[str, Any], to: str, subject: str,
                       body_html: str, body_text: str,
                       in_reply_to: str = "", references: str = "") -> Dict[str, Any]:
    """Send an email via Gmail API."""
    import base64

    def _sync():
        svc = _get_gmail_service(conn["refresh_token"])
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = svc.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"status": "sent", "message_id": result.get("id", ""), "error": None}

    try:
        return await asyncio.get_running_loop().run_in_executor(None, _sync)
    except Exception as e:
        return {"status": "error", "message_id": None, "error": str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# 4. MICROSOFT GRAPH API HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _fetch_inbox_microsoft(conn: Dict[str, Any], max_results: int = 20,
                                   unread_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch emails via Microsoft Graph API."""
    conn = await _refresh_microsoft_token(conn)
    import httpx

    filter_q = "&$filter=isRead eq false" if unread_only else ""
    url = (
        f"https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        f"?$top={max_results}&$orderby=receivedDateTime desc{filter_q}"
        f"&$select=id,conversationId,from,subject,bodyPreview,body,receivedDateTime,isRead"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {conn['access_token']}"})

    if resp.status_code != 200:
        print(f"[email_service] Microsoft inbox fetch failed: {resp.status_code} {resp.text[:300]}")
        return []

    messages = resp.json().get("value", [])
    results = []
    for msg in messages:
        from_obj = msg.get("from", {}).get("emailAddress", {})
        results.append({
            "message_id": msg.get("id", ""),
            "thread_id": msg.get("conversationId", ""),
            "sender_email": from_obj.get("address", ""),
            "sender_name": from_obj.get("name", ""),
            "subject": msg.get("subject", ""),
            "date": msg.get("receivedDateTime", ""),
            "body": msg.get("body", {}).get("content", ""),
            "snippet": msg.get("bodyPreview", "")[:200],
            "labels": [] if msg.get("isRead") else ["UNREAD"],
        })
    return results


async def _send_microsoft(conn: Dict[str, Any], to: str, subject: str,
                            body_html: str, body_text: str,
                            in_reply_to: str = "", references: str = "") -> Dict[str, Any]:
    """Send an email via Microsoft Graph API."""
    conn = await _refresh_microsoft_token(conn)
    import httpx

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": "true",
    }
    # If replying, use the reply endpoint
    if in_reply_to:
        payload["message"]["internetMessageHeaders"] = [
            {"name": "In-Reply-To", "value": in_reply_to},
            {"name": "References", "value": references or in_reply_to},
        ]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            json=payload,
            headers={
                "Authorization": f"Bearer {conn['access_token']}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code in (200, 202):
        return {"status": "sent", "message_id": f"ms-{uuid.uuid4().hex[:12]}", "error": None}
    print(f"[email_service] Microsoft send failed: {resp.status_code} {resp.text[:300]}")
    return {"status": "error", "message_id": None, "error": resp.text[:300]}


# ═════════════════════════════════════════════════════════════════════════════
# 5. IMAP / SMTP HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _decode_header(raw: str) -> str:
    parts = _decode_header_raw(raw or "")
    decoded = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded += part.decode(enc or "utf-8", errors="replace")
        else:
            decoded += part
    return decoded


async def _fetch_inbox_imap(conn: Dict[str, Any], max_results: int = 20,
                              unread_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch emails via IMAP4_SSL using stored app-password credentials."""
    import email as _email_lib

    def _sync():
        mail = imaplib.IMAP4_SSL(conn["imap_host"], conn["imap_port"])
        mail.login(conn["email"], conn["password"])
        mail.select("INBOX")
        criterion = "UNSEEN" if unread_only else "ALL"
        _, data = mail.search(None, criterion)
        mail_ids = data[0].split() if data[0] else []
        mail_ids = list(reversed(mail_ids))[:max_results]
        results: List[Dict[str, Any]] = []
        for num in mail_ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw_bytes = msg_data[0][1]
            msg = _email_lib.message_from_bytes(raw_bytes)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                        body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")

            sender_raw = _decode_header(msg.get("From", ""))
            sender_name, sender_email = "", sender_raw
            if "<" in sender_raw and ">" in sender_raw:
                sender_name = sender_raw[:sender_raw.index("<")].strip().strip('"')
                sender_email = sender_raw[sender_raw.index("<") + 1:sender_raw.index(">")].strip()

            results.append({
                "message_id": msg.get("Message-ID", "").strip(),
                "thread_id": msg.get("References", msg.get("Message-ID", "")).strip(),
                "sender_email": sender_email,
                "sender_name": sender_name,
                "subject": _decode_header(msg.get("Subject", "")),
                "date": msg.get("Date", ""),
                "body": body,
                "snippet": body[:200],
                "labels": ["INBOX"] + (["UNREAD"] if unread_only else []),
            })
        mail.logout()
        return results

    try:
        return await asyncio.get_running_loop().run_in_executor(None, _sync)
    except Exception as e:
        print(f"[email_service] IMAP fetch failed: {e}")
        return []


async def _send_imap_smtp(conn: Dict[str, Any], to: str, subject: str,
                            body_html: str, body_text: str,
                            in_reply_to: str = "", references: str = "",
                            from_name: str = "") -> Dict[str, Any]:
    """Send an email via SMTP using IMAP connection credentials."""
    display_name = from_name or conn["email"]

    html_body = body_html
    if "<" not in html_body:
        html_body = html_body.replace("\n", "<br>")
        html_body = f"<div style='font-family:Arial,sans-serif;line-height:1.6'>{html_body}</div>"

    def _sync():
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{display_name} <{conn['email']}>"
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        smtp_port = int(conn.get("smtp_port", 587))
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(conn["smtp_host"], smtp_port)
        else:
            server = smtplib.SMTP(conn["smtp_host"], smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()
        server.login(conn["email"], conn["password"])
        server.sendmail(conn["email"], to, msg.as_string())
        server.quit()
        return {"status": "sent", "message_id": f"smtp-{uuid.uuid4().hex[:12]}", "error": None}

    try:
        return await asyncio.get_running_loop().run_in_executor(None, _sync)
    except Exception as e:
        print(f"[email_service] SMTP send failed: {e}")
        return {"status": "error", "message_id": None, "error": str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# 6. PUBLIC API  —  fetch_inbox / send_email / send_campaign_batch
# ═════════════════════════════════════════════════════════════════════════════

async def fetch_inbox(client_id: str, max_results: int = 20,
                       unread_only: bool = True) -> List[Dict[str, Any]]:
    """
    Fetch inbox emails for *client_id*.
    Dispatches to the right provider based on stored connection.
    Returns a list of normalised email dicts (same shape regardless of provider).
    """
    conn = get_connection(client_id)
    if not conn:
        print(f"[email_service] No connection for '{client_id}'")
        return []

    if conn["type"] == "gmail":
        return await _fetch_inbox_gmail(conn, max_results, unread_only)
    if conn["type"] == "microsoft":
        return await _fetch_inbox_microsoft(conn, max_results, unread_only)
    if conn["type"] == "imap":
        return await _fetch_inbox_imap(conn, max_results, unread_only)
    return []


async def send_email(client_id: str, to: str, subject: str,
                      body_html: str, body_text: str = "",
                      in_reply_to: str = "", references: str = "",
                      from_name: str = "") -> Dict[str, Any]:
    """
    Send a single email from the client's connected mailbox.
    Returns ``{"status": "sent"|"error", "message_id": ..., "error": ...}``.
    """
    conn = get_connection(client_id)
    if not conn:
        return {"status": "error", "message_id": None, "error": "No email connection"}

    if not body_text:
        # Strip HTML tags for plain-text fallback
        import re
        body_text = re.sub(r"<[^>]+>", "", body_html)

    # ── AI Disclosure Footer (legal compliance) ──────────────────────
    _ai_footer_html = (
        '<div style="margin-top:24px;padding-top:12px;border-top:1px solid #e5e7eb;'
        'font-size:11px;color:#9ca3af;line-height:1.5">'
        'This email was composed with AI assistance via '
        '<a href="https://app.nexarilyai.com" style="color:#6366f1;text-decoration:none">'
        'Alita AI</a> by NexarilyAI.</div>'
    )
    _ai_footer_text = "\n\n---\nThis email was composed with AI assistance via Alita AI by NexarilyAI."
    body_html = body_html + _ai_footer_html
    body_text = body_text + _ai_footer_text

    if conn["type"] == "gmail":
        return await _send_gmail(conn, to, subject, body_html, body_text, in_reply_to, references)
    if conn["type"] == "microsoft":
        return await _send_microsoft(conn, to, subject, body_html, body_text, in_reply_to, references)
    if conn["type"] == "imap":
        return await _send_imap_smtp(conn, to, subject, body_html, body_text, in_reply_to, references, from_name)
    return {"status": "error", "message_id": None, "error": f"Unknown provider: {conn['type']}"}


# Daily send limits per provider (conservative defaults)
_DAILY_LIMITS = {"gmail": 450, "microsoft": 280, "imap": 180}


async def send_campaign_batch(
    client_id: str,
    recipients: List[Dict[str, str]],  # [{"email": "…", "name": "…"}, …]
    subject: str,
    body_html: str,
    body_text: str = "",
    delay_seconds: float = 2.0,
) -> Dict[str, Any]:
    """
    Send a campaign email to a list of recipients via the client's own mailbox.

    Rate-limits to avoid provider bans. Returns progress dict.
    """
    conn = get_connection(client_id)
    if not conn:
        return {"ok": False, "error": "No email connection", "sent": 0, "failed": 0}

    limit = _DAILY_LIMITS.get(conn["type"], 180)
    if len(recipients) > limit:
        return {
            "ok": False,
            "error": f"Too many recipients ({len(recipients)}). Your {conn['type']} account supports up to {limit}/day.",
            "sent": 0,
            "failed": 0,
        }

    sent = 0
    failed = 0
    errors: List[str] = []
    for rcpt in recipients:
        try:
            # Personalise greeting if name available
            personalised_html = body_html
            personalised_text = body_text
            name = rcpt.get("name", "").strip()
            if name:
                personalised_html = personalised_html.replace("{{name}}", name)
                personalised_text = personalised_text.replace("{{name}}", name)
            else:
                personalised_html = personalised_html.replace("{{name}}", "there")
                personalised_text = personalised_text.replace("{{name}}", "there")

            result = await send_email(
                client_id=client_id,
                to=rcpt["email"],
                subject=subject,
                body_html=personalised_html,
                body_text=personalised_text,
            )
            if result.get("status") == "sent":
                sent += 1
            else:
                failed += 1
                errors.append(f"{rcpt['email']}: {result.get('error', 'unknown')}")
        except Exception as e:
            failed += 1
            errors.append(f"{rcpt['email']}: {e}")

        # Rate limit delay between sends
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return {
        "ok": failed == 0,
        "sent": sent,
        "failed": failed,
        "total": len(recipients),
        "errors": errors[:10],  # cap error log
    }
