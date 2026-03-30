"""
Notification Manager
===================
Handles client notifications across multiple channels:
- Dashboard alerts (in-app)
- Email notifications
- SMS notifications (via Twilio)
- Webhook notifications

Integrates with Conversation Categorizer to alert clients about
high-priority conversations (Sales, Leads, Complaints, Escalations).

Usage:
    notifier = NotificationManager(client_id="demo_client")
    
    # Send notification
    await notifier.send_notification(
        notification_type="sale",
        title="New Sale Inquiry",
        message="Customer asking about pricing",
        priority="high",
        channels=["email", "dashboard"]
    )
"""

import os
import sys
import asyncio
from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from dotenv import load_dotenv

# Windows UTF-8 fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Resend (email notifications)
try:
    import resend as resend_sdk
    _RESEND_AVAILABLE = True
except ImportError:
    _RESEND_AVAILABLE = False

# Twilio (SMS notifications)
try:
    from twilio.rest import Client as TwilioClient
    _TWILIO_AVAILABLE = True
except ImportError:
    _TWILIO_AVAILABLE = False

load_dotenv()


@dataclass
class Notification:
    """Notification data structure"""
    notification_id: str
    client_id: str
    notification_type: str  # sale, lead, complaint, support, escalation
    title: str
    message: str
    priority: str  # critical, high, medium, low
    channels: List[str]  # dashboard, email, sms, webhook
    metadata: Optional[Dict] = None
    created_at: str = None
    sent_at: Optional[str] = None
    status: str = "pending"  # pending, sent, failed
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class NotificationManager:
    """Manages multi-channel notifications for clients"""
    
    def __init__(self, client_id: str):
        """
        Initialize notification manager.
        
        Args:
            client_id: Client identifier
        """
        self.client_id = client_id
        
        # Load notification preferences
        self.preferences = self._load_preferences()
        
        # Notification storage
        self.storage_path = Path("storage") / "notifications"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Notification log
        self.log_file = self.storage_path / f"{client_id}_notifications.jsonl"
        
        # Email settings — uses Resend (same provider as email marketing)
        self.email_enabled = bool(_RESEND_AVAILABLE and os.getenv("RESEND_API_KEY"))
        self.email_from = (
            os.getenv("NOTIFICATION_EMAIL_FROM", "").strip()
            or os.getenv("EMAIL_FROM_ADDRESS", "").strip()
            or "onboarding@resend.dev"
        )
        
        # SMS settings (optional - for production)
        self.sms_enabled = (
            os.getenv("TWILIO_SMS_ENABLED", "false").lower() == "true"
            and bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"))
        )
        
        # Webhook settings
        self.webhook_url = os.getenv(f"WEBHOOK_NOTIFICATION_URL_{client_id}", "")
        
        print(f"✅ Notification Manager ready for {client_id}")
        print(f"   Email: {'✅ Enabled' if self.email_enabled else '⚠️ Not configured'}")
        print(f"   SMS: {'✅ Enabled' if self.sms_enabled else '⚠️ Not configured'}")
        print(f"   Webhook: {'✅ Enabled' if self.webhook_url else '⚠️ Not configured'}")
    
    def _load_preferences(self) -> Dict:
        """Load notification preferences for client"""
        defaults = {
            "enabled": True,
            "channels": ["dashboard"],  # Default to dashboard only
            "email": os.getenv(f"CLIENT_EMAIL_{self.client_id}", ""),
            "phone": os.getenv(f"CLIENT_PHONE_{self.client_id}", ""),
            # Per-type email toggles (default ON for all known types)
            "email_types": {
                "sale": True,
                "lead": True,
                "complaint": True,
                "escalation": True,
                "support": True,
                "follow_suggestion": True,
                "group_opportunity": True,
                "competitor_alert": True,
                "content_idea": True,
                "growth_tip": True,
                "viral_alert": True,
                "milestone": True,
                "budget_alert": True,
                "sentiment_alert": True,
                "post": True,
                "system": True,
            },
            # Expanded set — all meaningful notification types
            "notify_on": [
                # Urgent alerts (DM / comment triggered)
                "sale", "lead", "complaint", "escalation", "support",
                # Growth opportunities (AI triggered)
                "follow_suggestion", "group_opportunity", "competitor_alert",
                "growth_report",
                # Intelligence (AI insights)
                "content_idea", "growth_tip",
                # Wins
                "viral_alert", "milestone",
                # Account health
                "budget_alert", "sentiment_alert", "post", "system",
                # Email
                "message_received",
                # Platform events
                "platform_connected", "platform_disconnected",
            ],
            "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00"}
        }

        # Try to load email type toggles from DB (ClientProfile.notification_email_prefs_json)
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile

            db = SessionLocal()
            try:
                prof = db.query(ClientProfile).filter(ClientProfile.client_id == self.client_id).first()
                raw = getattr(prof, "notification_email_prefs_json", None) if prof else None
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        merged = dict(defaults.get("email_types", {}))
                        for k, v in data.items():
                            if k in merged:
                                merged[k] = bool(v)
                        defaults["email_types"] = merged
            finally:
                db.close()
        except Exception:
            pass

        return defaults

    def _email_enabled_for_type(self, notification_type: str) -> bool:
        try:
            m = self.preferences.get("email_types") or {}
            if isinstance(m, dict) and notification_type in m:
                return bool(m.get(notification_type))
        except Exception:
            pass
        return True
    
    async def send_notification(
        self,
        notification_type: str,
        title: str,
        message: str,
        priority: str = "medium",
        channels: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> Notification:
        """
        Send notification across specified channels.
        
        Args:
            notification_type: Type (sale, lead, complaint, support, escalation)
            title: Notification title
            message: Notification message
            priority: Priority level (critical, high, medium, low)
            channels: Channels to use (None = use preferences)
            metadata: Additional data (sender_id, platform, etc.)
            
        Returns:
            Notification object with status
        """
        import logging as _nm_log_mod
        _nm_log = _nm_log_mod.getLogger("notification_manager")

        # Check if notifications are enabled
        if not self.preferences.get("enabled", True):
            _nm_log.warning(f"Notifications disabled for client {self.client_id}")
            return None
        
        # Check if this notification type should be sent
        _allowed = self.preferences.get("notify_on", [])
        if notification_type not in _allowed:
            _nm_log.warning(f"Notification type '{notification_type}' NOT in notify_on for {self.client_id}. Allowed: {_allowed}")
            return None
        _nm_log.info(f"Notification type '{notification_type}' ALLOWED for {self.client_id} — proceeding to send")
        
        # Use preference channels if not specified
        if channels is None:
            channels = self.preferences.get("channels", ["dashboard"])

        # Auto-include email for high / critical priority notifications
        if (
            self.email_enabled
            and priority in ("high", "critical")
            and "email" not in channels
            and self._email_enabled_for_type(notification_type)
        ):
            channels = list(channels) + ["email"]
        
        # Create notification
        notification = Notification(
            notification_id=f"notif_{datetime.now().timestamp()}",
            client_id=self.client_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            channels=channels,
            metadata=metadata or {}
        )
        
        print(f"\n📢 Sending notification: {title}")
        print(f"   Type: {notification_type}")
        print(f"   Priority: {priority}")
        print(f"   Channels: {', '.join(channels)}")
        
        # Send to each channel
        results = []
        for channel in channels:
            try:
                if channel == "dashboard":
                    result = await self._send_dashboard_notification(notification)
                elif channel == "email":
                    if not self._email_enabled_for_type(notification.notification_type):
                        print(f"   Email disabled for type '{notification.notification_type}', skipping")
                        result = False
                    else:
                        result = await self._send_email_notification(notification)
                elif channel == "sms":
                    result = await self._send_sms_notification(notification)
                elif channel == "webhook":
                    result = await self._send_webhook_notification(notification)
                else:
                    result = False
                
                results.append(result)
                
            except Exception as e:
                print(f"   ❌ Failed to send to {channel}: {e}")
                results.append(False)
        
        # Update status
        notification.sent_at = datetime.now().isoformat()
        notification.status = "sent" if any(results) else "failed"
        
        # Log notification
        self._log_notification(notification)
        
        status_emoji = "✅" if notification.status == "sent" else "❌"
        print(f"   {status_emoji} Notification {notification.status}")
        
        return notification
    
    async def _send_dashboard_notification(self, notification: Notification) -> bool:
        """Save notification to PostgreSQL (persists across Railway redeploys).

        On failure retries once, then writes an emergency recovery JSON file
        that the startup watchdog will import on next boot. NEVER falls back
        to the old JSONL append — that file is ephemeral on Railway.
        """
        import logging as _log_mod
        _db_log = _log_mod.getLogger("notification_manager")

        if not notification.client_id:
            _db_log.error(
                f"Cannot save notification without client_id! "
                f"type={notification.notification_type} title={notification.title}"
            )
            return False

        from database.db import get_db
        from database.models import ClientNotification
        import json as _json

        meta = notification.metadata or {}
        last_err = None

        def _sanitize(s):
            """Strip surrogate chars that break PostgreSQL UTF-8."""
            if isinstance(s, str):
                return s.encode('utf-8', errors='replace').decode('utf-8')
            return s

        for _attempt in range(2):           # try twice (handles connection-pool hiccups)
            try:
                db = next(get_db())
                try:
                    row = ClientNotification(
                        id=notification.notification_id,
                        client_id=str(notification.client_id),
                        notification_type=notification.notification_type,
                        title=_sanitize(notification.title),
                        message=_sanitize(notification.message or ""),
                        priority=notification.priority or "medium",
                        read=False,
                        metadata_json=_json.dumps(meta, ensure_ascii=True),
                    )
                    db.add(row)
                    db.commit()
                    _db_log.info(
                        f"✅ Notification saved to DB: id={notification.notification_id} "
                        f"client={notification.client_id} type={notification.notification_type}"
                    )
                    return True
                except Exception as inner:
                    db.rollback()
                    last_err = inner
                finally:
                    db.close()
            except Exception as outer:
                last_err = outer

        # Both attempts failed — write emergency recovery file
        _db_log.error(f"DB save failed after 2 attempts: {last_err}", exc_info=True)
        try:
            import os
            recovery_dir = os.path.join("storage", "notification_recovery")
            os.makedirs(recovery_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{notification.client_id}_{ts}_{notification.notification_type}.json"
            fpath = os.path.join(recovery_dir, fname)
            with open(fpath, "w") as rf:
                _json.dump({
                    "id": notification.notification_id,
                    "client_id": str(notification.client_id),
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "message": notification.message or "",
                    "priority": notification.priority or "medium",
                    "metadata": meta,
                    "created_at": notification.created_at,
                }, rf)
            _db_log.warning(f"Emergency notification written to {fpath}")
        except Exception as recov_err:
            _db_log.error(f"Emergency recovery file also failed: {recov_err}")
        return False

    async def _send_dashboard_notification_file(self, notification: Notification) -> bool:
        """Fallback: save notification to JSONL file."""
        try:
            alerts_file = self.storage_path / f"{self.client_id}_dashboard_alerts.jsonl"
            meta = notification.metadata or {}

            with open(alerts_file, 'a') as f:
                f.write(json.dumps({
                    "id": notification.notification_id,
                    "type": notification.notification_type,
                    "title": notification.title,
                    "message": notification.message,
                    "priority": notification.priority,
                    "timestamp": notification.created_at,
                    "read": False,
                    "metadata": meta,
                }) + "\n")

            print(f"   ✅ Dashboard notification saved (file fallback)")
            return True

        except Exception as e:
            print(f"   ❌ Dashboard notification failed: {e}")
            return False

    async def send_growth_notification(
        self,
        notification_type: str,
        title: str,
        message: str,
        priority: str = "medium",
        action_url: str = "",
        action_label: str = "",
        action_type: str = "open_url",   # "open_url" | "internal_link"
        platform: str = "",
        extra_meta: Optional[Dict] = None,
    ) -> "Notification":
        """
        Convenience wrapper for growth / intelligence / win / health notifications
        that include an action button the client can click.

        action_type values:
          "open_url"       — opens an external URL (platform profile, group, post)
          "internal_link"  — navigates within the Alita app (e.g. /billing)
        """
        meta: Dict = extra_meta or {}
        if platform:
            meta["platform"] = platform
        if action_url:
            meta["action_url"]   = action_url
            meta["action_label"] = action_label
            meta["action_type"]  = action_type

        return await self.send_notification(
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            channels=["dashboard", "email"],
            metadata=meta,
        )
    
    def _resolve_client_email(self) -> str:
        """Look up the client's signup email from the database."""
        try:
            from database.db import get_db
            from database.models import ClientProfile

            db = next(get_db())
            try:
                profile = (
                    db.query(ClientProfile)
                    .filter(ClientProfile.client_id == self.client_id)
                    .first()
                )
                if profile and profile.user and profile.user.email:
                    return profile.user.email
            finally:
                db.close()
        except Exception as e:
            print(f"   ⚠️  DB email lookup failed: {e}")
        return ""

    async def _send_email_notification(self, notification: Notification) -> bool:
        """Send email notification via Resend."""
        if not self.email_enabled:
            print(f"   Email not configured (install resend + set RESEND_API_KEY), skipping")
            return False

        # Resolve email from DB (User.email via ClientProfile), fall back to env var
        email_to = self._resolve_client_email()
        if not email_to:
            email_to = self.preferences.get("email", "")
        if not email_to:
            print(f"   No email address found for client '{self.client_id}' (checked DB + env)")
            return False

        # Priority-based subject prefix
        prefix_map = {"critical": "[URGENT] ", "high": "[Action Required] ", "medium": "", "low": ""}
        subject = prefix_map.get(notification.priority, "") + notification.title

        # Build HTML email body
        priority_colors = {"critical": "#dc2626", "high": "#ea580c", "medium": "#2563eb", "low": "#16a34a"}
        color = priority_colors.get(notification.priority, "#2563eb")
        meta = notification.metadata or {}
        platform = meta.get("platform", "")
        sender_id = meta.get("sender_id", "")
        action_url = meta.get("action_url", "")
        action_label = meta.get("action_label", "")
        error_code = meta.get("error_code", "")
        error_details = meta.get("error_details", "")
        failed_items = meta.get("failed_items", [])  # list of {"item", "error", "time"}
        event_time = meta.get("event_time", "")
        job_name = meta.get("job_name", "")
        report_id = meta.get("report_id", "")

        # --- Build detail rows ---
        detail_rows = []
        if job_name:
            detail_rows.append(("Job / Task", job_name))
        if event_time:
            detail_rows.append(("Event Time (UTC)", event_time))
        if platform:
            detail_rows.append(("Platform", platform))
        if sender_id:
            detail_rows.append(("Sender ID", sender_id))
        if error_code:
            detail_rows.append(("Error Code", f"<code style='background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px'>{error_code}</code>"))
        if error_details:
            detail_rows.append(("Error Details", error_details))
        if report_id:
            detail_rows.append(("Report ID", report_id))

        details_html = ""
        if detail_rows:
            rows = "".join(
                f"<tr><td style='padding:6px 12px;font-size:13px;color:#6b7280;white-space:nowrap;vertical-align:top'>{label}</td>"
                f"<td style='padding:6px 12px;font-size:13px;color:#111827;word-break:break-word'><strong>{value}</strong></td></tr>"
                for label, value in detail_rows
            )
            details_html = (
                f"<table style='width:100%;border-collapse:collapse;margin:16px 0;background:#fff;"
                f"border:1px solid #e5e7eb;border-radius:6px'>"
                f"<tbody>{rows}</tbody></table>"
            )

        # --- Build failed items table (for post failures, campaign errors, etc.) ---
        failures_html = ""
        if failed_items and isinstance(failed_items, list):
            fail_rows = ""
            for item in failed_items[:20]:
                item_name = item.get("item", item.get("platform", "Unknown"))
                item_error = item.get("error", "Unknown error")
                item_time = item.get("time", "")
                fail_rows += (
                    f"<tr>"
                    f"<td style='padding:6px 10px;font-size:13px;border-bottom:1px solid #fecaca'>{item_name}</td>"
                    f"<td style='padding:6px 10px;font-size:13px;color:#991b1b;border-bottom:1px solid #fecaca'>{item_error}</td>"
                    f"<td style='padding:6px 10px;font-size:12px;color:#6b7280;border-bottom:1px solid #fecaca'>{item_time}</td>"
                    f"</tr>"
                )
            failures_html = (
                f"<div style='margin:16px 0'>"
                f"<p style='font-size:14px;font-weight:600;color:#991b1b;margin:0 0 8px'>Failure Details:</p>"
                f"<table style='width:100%;border-collapse:collapse;background:#fff;border:1px solid #fecaca;border-radius:6px'>"
                f"<thead><tr style='background:#fef2f2'>"
                f"<th style='padding:8px 10px;font-size:12px;text-align:left;color:#991b1b'>Item</th>"
                f"<th style='padding:8px 10px;font-size:12px;text-align:left;color:#991b1b'>Error</th>"
                f"<th style='padding:8px 10px;font-size:12px;text-align:left;color:#991b1b'>Time</th>"
                f"</tr></thead>"
                f"<tbody>{fail_rows}</tbody></table></div>"
            )

        # --- Action button ---
        action_html = ""
        if action_url and action_label:
            action_html = (
                f"<div style='margin:20px 0 8px;text-align:center'>"
                f"<a href='{action_url}' style='display:inline-block;padding:10px 24px;"
                f"background:{color};color:#fff;text-decoration:none;border-radius:6px;"
                f"font-size:14px;font-weight:600'>{action_label} &rarr;</a></div>"
            )

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
          <div style="background:{color};color:white;padding:16px 24px;border-radius:8px 8px 0 0">
            <h2 style="margin:0;font-size:18px">{notification.title}</h2>
            <p style="margin:4px 0 0;opacity:0.9;font-size:13px">Priority: {notification.priority.upper()} &bull; Type: {notification.notification_type}</p>
          </div>
          <div style="background:#f9fafb;padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px">
            <div style="font-size:15px;color:#111827;line-height:1.6;margin:0 0 16px">{notification.message}</div>
            {details_html}
            {failures_html}
            {action_html}
            <p style="font-size:12px;color:#9ca3af;margin-top:24px;border-top:1px solid #e5e7eb;padding-top:12px">
              Alita AI Notification &bull; Sent at {notification.created_at[:19].replace('T', ' ')} UTC &bull; Client: {self.client_id}
            </p>
          </div>
        </div>
        """

        # --- Build rich plain text fallback ---
        text_parts = [notification.title, "", notification.message, ""]
        for label, value in detail_rows:
            # Strip HTML tags from value for plain text
            import re as _re_strip
            clean_val = _re_strip.sub(r'<[^>]+>', '', str(value))
            text_parts.append(f"{label}: {clean_val}")
        if failed_items:
            text_parts.append("\nFailure Details:")
            for item in failed_items[:20]:
                item_name = item.get("item", item.get("platform", "Unknown"))
                item_error = item.get("error", "Unknown error")
                item_time = item.get("time", "")
                text_parts.append(f"  - {item_name}: {item_error}" + (f" (at {item_time})" if item_time else ""))
        if action_url:
            text_parts.append(f"\n{action_label}: {action_url}")
        text_parts.append(f"\nSent at {notification.created_at[:19].replace('T', ' ')} UTC")
        plain_text = "\n".join(text_parts)

        try:
            resend_sdk.api_key = os.getenv("RESEND_API_KEY", "")
            result = resend_sdk.Emails.send({
                "from": f"Alita Notifications <{self.email_from}>",
                "to": [email_to],
                "subject": subject,
                "html": html,
                "text": plain_text,
                "tags": [{"name": "type", "value": notification.notification_type}]
            })
            msg_id = result.get("id", "unknown")
            print(f"   Email sent via Resend | ID: {msg_id} | To: {email_to}")
            return True
        except Exception as e:
            print(f"   Email send failed: {e}")
            return False
    
    async def _send_sms_notification(self, notification: Notification) -> bool:
        """Send SMS notification via Twilio."""
        if not self.sms_enabled:
            print(f"   SMS not configured (install twilio + set TWILIO_ACCOUNT_SID/AUTH_TOKEN), skipping")
            return False

        if not _TWILIO_AVAILABLE:
            print(f"   Twilio package not installed. Run: pip install twilio")
            return False

        phone = self.preferences.get("phone")
        if not phone:
            print(f"   No phone number for client '{self.client_id}'. Set CLIENT_PHONE_{self.client_id} in .env")
            return False

        twilio_from = os.getenv("TWILIO_PHONE_NUMBER", "")
        if not twilio_from:
            print(f"   TWILIO_PHONE_NUMBER not set in .env")
            return False

        # Keep SMS concise — 160 char limit
        priority_tag = {"critical": "[URGENT] ", "high": "[ALERT] ", "medium": "", "low": ""}.get(notification.priority, "")
        body = f"{priority_tag}{notification.title}: {notification.message}"
        if len(body) > 155:
            body = body[:152] + "..."

        try:
            client = TwilioClient(
                os.getenv("TWILIO_ACCOUNT_SID"),
                os.getenv("TWILIO_AUTH_TOKEN")
            )
            message = client.messages.create(
                body=body,
                from_=twilio_from,
                to=phone
            )
            print(f"   SMS sent via Twilio | SID: {message.sid} | To: {phone}")
            return True
        except Exception as e:
            print(f"   SMS send failed: {e}")
            return False
    
    async def _send_webhook_notification(self, notification: Notification) -> bool:
        """Send webhook notification"""
        if not self.webhook_url:
            print(f"   ⚠️  No webhook URL configured, skipping")
            return False
        
        try:
            import httpx
            
            payload = {
                "id": notification.notification_id,
                "client_id": self.client_id,
                "type": notification.notification_type,
                "title": notification.title,
                "message": notification.message,
                "priority": notification.priority,
                "timestamp": notification.created_at,
                "metadata": notification.metadata
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
            
            print(f"   ✅ Webhook notification sent")
            return True
            
        except Exception as e:
            print(f"   ❌ Webhook notification failed: {e}")
            return False
    
    def _log_notification(self, notification: Notification):
        """Log notification to persistent storage"""
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps({
                    "id": notification.notification_id,
                    "type": notification.notification_type,
                    "title": notification.title,
                    "message": notification.message,
                    "priority": notification.priority,
                    "channels": notification.channels,
                    "status": notification.status,
                    "created_at": notification.created_at,
                    "sent_at": notification.sent_at,
                    "metadata": notification.metadata
                }) + "\n")
        except Exception as e:
            print(f"   ⚠️  Failed to log notification: {e}")
    
    def get_recent_notifications(self, limit: int = 50) -> List[Dict]:
        """Get recent notifications for this client from PostgreSQL."""
        try:
            from database.db import get_db
            from database.models import ClientNotification
            db = next(get_db())
            try:
                rows = (
                    db.query(ClientNotification)
                    .filter(ClientNotification.client_id == self.client_id)
                    .order_by(ClientNotification.created_at.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "id": r.id,
                        "type": r.notification_type,
                        "title": r.title,
                        "message": r.message or "",
                        "priority": r.priority or "medium",
                        "channels": ["dashboard"],
                        "status": "sent",
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                        "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
                    }
                    for r in rows
                ]
            finally:
                db.close()
        except Exception as e:
            import logging as _log_mod
            _log_mod.getLogger("notification_manager").error(
                f"get_recent_notifications DB read failed: {e}", exc_info=True
            )
            return []   # No filesystem fallback — Railway wipes it on redeploy
    
    def get_unread_dashboard_alerts(self) -> List[Dict]:
        """Get unread dashboard alerts from PostgreSQL."""
        try:
            from database.db import get_db
            from database.models import ClientNotification
            db = next(get_db())
            try:
                rows = (
                    db.query(ClientNotification)
                    .filter(
                        ClientNotification.client_id == self.client_id,
                        ClientNotification.read == False,
                    )
                    .order_by(ClientNotification.created_at.desc())
                    .all()
                )
                return [
                    {
                        "id": r.id,
                        "type": r.notification_type,
                        "title": r.title,
                        "message": r.message or "",
                        "priority": r.priority or "medium",
                        "timestamp": r.created_at.isoformat() if r.created_at else "",
                        "read": False,
                        "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
                    }
                    for r in rows
                ]
            finally:
                db.close()
        except Exception as e:
            import logging as _log_mod
            _log_mod.getLogger("notification_manager").error(
                f"get_unread_dashboard_alerts DB read failed: {e}", exc_info=True
            )
            return []   # No filesystem fallback — Railway wipes it on redeploy
    
    def mark_alert_as_read(self, alert_id: str) -> bool:
        """Mark a dashboard alert as read in PostgreSQL."""
        try:
            from database.db import get_db
            from database.models import ClientNotification
            from datetime import datetime as _dt
            db = next(get_db())
            try:
                row = db.query(ClientNotification).filter(
                    ClientNotification.id == alert_id,
                    ClientNotification.client_id == self.client_id,
                ).first()
                if not row:
                    return False
                row.read = True
                row.read_at = _dt.utcnow()
                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            print(f"❌ DB mark_alert_as_read failed: {e}")
            return False
    
    def update_preferences(self, preferences: Dict) -> bool:
        """Update notification preferences"""
        try:
            self.preferences.update(preferences)
            
            # In production, save to database
            # For now, just update in memory
            
            print(f"✅ Notification preferences updated")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update preferences: {e}")
            return False


# Example usage and testing
if __name__ == "__main__":
    async def test_notifications():
        """Test the notification system"""
        print("\n" + "="*70)
        print("🧪 TESTING NOTIFICATION MANAGER")
        print("="*70)
        
        notifier = NotificationManager(client_id="demo_client")
        
        # Test 1: Dashboard notification
        print("\n--- TEST 1: Dashboard Notification ---")
        await notifier.send_notification(
            notification_type="sale",
            title="New Sale Inquiry",
            message="Customer asking about pricing for premium coaching package",
            priority="high",
            channels=["dashboard"],
            metadata={"sender_id": "user_123", "platform": "instagram"}
        )
        
        # Test 2: Multi-channel notification
        print("\n--- TEST 2: Multi-Channel Notification ---")
        await notifier.send_notification(
            notification_type="complaint",
            title="Customer Complaint",
            message="Customer unhappy with service response time",
            priority="high",
            channels=["dashboard", "email"],
            metadata={"sender_id": "user_456", "platform": "facebook"}
        )
        
        # Test 3: Critical escalation
        print("\n--- TEST 3: Critical Escalation ---")
        await notifier.send_notification(
            notification_type="escalation",
            title="⚠️ URGENT: Customer Escalation",
            message="Customer threatening legal action",
            priority="critical",
            channels=["dashboard", "email", "sms"],
            metadata={"sender_id": "user_789", "platform": "twitter"}
        )
        
        # Get recent notifications
        print("\n--- Recent Notifications ---")
        recent = notifier.get_recent_notifications(limit=5)
        for notif in recent:
            print(f"• [{notif['priority']}] {notif['title']}")
        
        # Get unread alerts
        print("\n--- Unread Dashboard Alerts ---")
        unread = notifier.get_unread_dashboard_alerts()
        print(f"Unread alerts: {len(unread)}")
        for alert in unread:
            print(f"• {alert['title']} ({alert['type']})")
    
    asyncio.run(test_notifications())
