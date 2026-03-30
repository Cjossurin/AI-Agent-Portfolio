"""
api/billing_routes.py — Full payment system for Alita AI.

Public routes (no auth required):
    GET  /pricing                  — public pricing + feature comparison page

Authenticated routes:
    GET  /billing                  — client billing management page
    POST /api/billing/checkout     — create Stripe checkout session
    GET  /api/billing/portal       — redirect to Stripe customer portal
    POST /api/billing/validate-promo — validate promo code before checkout

Webhook (Stripe signature-verified):
    POST /api/billing/webhook      — handles Stripe subscription events

Setup checklist (run once in Stripe Dashboard):
  1. Create 6 Price objects (Starter/Growth/Pro × Monthly/Annual)
  2. Copy the price_xxx IDs → .env as STRIPE_PRICE_STARTER_MONTHLY etc.
  3. Create Promo codes in Coupons section
  4. Add webhook endpoint: https://your-domain.com/api/billing/webhook
     Events: checkout.session.completed, invoice.payment_succeeded,
             invoice.payment_failed, customer.subscription.deleted,
             customer.subscription.updated
  5. Copy webhook signing secret → .env as STRIPE_WEBHOOK_SECRET
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.auth_routes import get_current_user, require_auth
from database.db import get_db
from database.models import ClientProfile
from utils.plan_limits import (
    PLANS, PLAN_PRICE_MONTHLY, PLAN_PRICE_ANNUAL_MONTHLY,
    PLAN_PRICE_ANNUAL_TOTAL, PLAN_DISPLAY_NAMES, PLAN_TAGLINES,
    STRIPE_PRICE_IDS, PLAN_ORDER,
    ADDONS, ADDON_STRIPE_PRICE_IDS, ADDON_PROD_TO_KEY, ADDON_PRICE_TO_KEY,
    get_effective_limit, _parse_active_addons,
)
from utils.shared_layout import build_page

router = APIRouter(tags=["billing"])

STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_BASE_URL          = os.getenv("APP_BASE_URL", "https://web-production-00e4.up.railway.app")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stripe():
    """Return a configured stripe module, or raise if not installed/configured."""
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET_KEY
        return _stripe
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Stripe library not installed. Run: pip install stripe"
        )


def _get_profile(user, db: Session) -> Optional[ClientProfile]:
    """Resolve ClientProfile for the logged-in user."""
    if not user:
        return None
    return db.query(ClientProfile).filter(
        ClientProfile.user_id == user.id
    ).first()


def _tier_from_price_id(price_id: str) -> tuple[str, str]:
    """Map a Stripe price ID back to (tier, period). Returns ('free','monthly') on miss."""
    for (tier, period), pid in STRIPE_PRICE_IDS.items():
        if pid and pid == price_id:
            return tier, period
    return "free", "monthly"


# ─────────────────────────────────────────────────────────────────────────────
# Feature matrix for pricing page
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val) -> str:
    """Format a limit value for display."""
    if val is True:   return "✅"
    if val is False:  return "—"
    if val == -1:     return "Unlimited"
    if val == 0:      return "—"
    return str(val)


FEATURE_SECTIONS = [
    {
        "label": "Social Media Platforms",
        "rows": [
            ("Connected social accounts",          "social_accounts",      "free",False),
            ("Instagram",                          "plat_instagram",       "free",True),
            ("Facebook",                           "plat_facebook",        "free",True),
            ("TikTok",                             "plat_tiktok",          "free",True),
            ("Twitter / X",                        "plat_twitter",         "free",True),
            ("LinkedIn",                           "plat_linkedin",        "free",True),
            ("Threads",                            "plat_threads",         "free",True),
            ("YouTube",                            "plat_youtube",         "free",True),
            ("All future platforms (auto-added)",  "plat_future",          "free",True),
        ],
    },
    {
        "label": "AI Content & Posting",
        "rows": [
            ("AI-generated posts / month",         "posts_created",        "free",False),
            ("Scheduled posting calendar",         "calendar_agent",       "free",True),
            ("AI-recommended posting times",       "recommended_times",    "free",True),
            ("Platform-optimized content",         "platform_optimized",   "free",True),
            ("SEO keyword suggestions",            "seo_keywords",         "free",True),
        ],
    },
    {
        "label": "AI Images",
        "rows": [
            ("AI images / month",                  "images_created",       "free",False),
            ("Premium AI images (Midjourney)",     "premium_images",       "free",True),
        ],
    },
    {
        "label": "AI Faceless Videos",
        "rows": [
            ("Faceless videos / month",            "videos_created",       "free",False),
            ("AI voiceover + subtitles",           "voice_clone",          "free",True),
            ("Stock footage (Pexels/Pixabay)",     "plat_tiktok",          "free",True),
            ("AI animation (cinematic quality)",   "ai_animation",         "free",True),
        ],
    },
    {
        "label": "AI Engagement",
        "rows": [
            ("AI engagement replies / month (social DMs, comments & email)", "replies_sent", "free",False),
            ("Digital voice clone",                "voice_clone",          "free",True),
            ("Auto-reply to DMs",                  "auto_dm_reply",        "free",True),
            ("Auto-reply to comments",             "auto_comment_reply",   "free",True),
        ],
    },
    {
        "label": "Email Marketing",
        "rows": [
            ("Email campaigns / month",            "campaigns_sent",       "free",False),
            ("Email support agent",                "email_support_agent",  "free",True),
            ("Campaign analytics",                 "campaign_analytics",   "free",True),
        ],
    },
    {
        "label": "Intelligence & Strategy",
        "rows": [
            ("Competitive research / month",       "competitive_research", "free",False),
            ("Growth strategy sessions / month",   "growth_strategy",      "free",False),
            ("Deep research sessions / month",     "research_run",         "free",False),
            ("Trend intelligence",                 "trend_intelligence",   "free",True),
        ],
    },
    {
        "label": "Analytics & Notifications",
        "rows": [
            ("Analytics dashboard",                "advanced_analytics",   "free",True),
            ("SMS notifications",                  "sms_notifications",    "free",True),
        ],
    },
]

# We hard-code certain display values because the feature matrix
# doesn't perfectly map to plan_limits keys for display purposes.
FEATURE_OVERRIDES = {
    # ── Platform access ────────────────────────────────────────────────────
    ("plat_instagram", "free"):    "✅",
    ("plat_instagram", "starter"): "✅",
    ("plat_instagram", "growth"):  "✅",
    ("plat_instagram", "pro"):     "✅",
    ("plat_facebook",  "free"):    "✅",
    ("plat_facebook",  "starter"): "✅",
    ("plat_facebook",  "growth"):  "✅",
    ("plat_facebook",  "pro"):     "✅",
    ("plat_tiktok",    "free"):    "—",
    ("plat_tiktok",    "starter"): "✅",
    ("plat_tiktok",    "growth"):  "✅",
    ("plat_tiktok",    "pro"):     "✅",
    ("plat_twitter",   "free"):    "—",
    ("plat_twitter",   "starter"): "✅",
    ("plat_twitter",   "growth"):  "✅",
    ("plat_twitter",   "pro"):     "✅",
    ("plat_linkedin",  "free"):    "—",
    ("plat_linkedin",  "starter"): "—",
    ("plat_linkedin",  "growth"):  "✅",
    ("plat_linkedin",  "pro"):     "✅",
    ("plat_threads",   "free"):    "—",
    ("plat_threads",   "starter"): "—",
    ("plat_threads",   "growth"):  "✅",
    ("plat_threads",   "pro"):     "✅",
    ("plat_youtube",   "free"):    "—",
    ("plat_youtube",   "starter"): "—",
    ("plat_youtube",   "growth"):  "—",
    ("plat_youtube",   "pro"):     "✅",
    ("plat_future",    "free"):    "—",
    ("plat_future",    "starter"): "—",
    ("plat_future",    "growth"):  "—",
    ("plat_future",    "pro"):     "✅ Auto",
    # ── Social accounts ───────────────────────────────────────────────────
    ("social_accounts", "free"):    "2",
    ("social_accounts", "starter"): "4",
    ("social_accounts", "growth"):  "6",
    ("social_accounts", "pro"):     "Unlimited",
    # ── Posts ─────────────────────────────────────────────────────────────
    ("posts_created", "free"):     "5",
    ("posts_created", "starter"):  "30",
    ("posts_created", "growth"):   "90",
    ("posts_created", "pro"):      "Unlimited",
    # ── Images ────────────────────────────────────────────────────────────
    ("images_created", "free"):    "3",
    ("images_created", "starter"): "15",
    ("images_created", "growth"):  "40",
    ("images_created", "pro"):     "100",
    # ── Videos ────────────────────────────────────────────────────────────
    ("videos_created", "free"):    "—",
    ("videos_created", "starter"): "1",
    ("videos_created", "growth"):  "5",
    ("videos_created", "pro"):     "15",
    # ── Replies ───────────────────────────────────────────────────────────
    ("replies_sent", "free"):      "20",
    ("replies_sent", "starter"):   "150",
    ("replies_sent", "growth"):    "500",
    ("replies_sent", "pro"):       "Unlimited",
    # ── Campaigns ─────────────────────────────────────────────────────────
    ("campaigns_sent", "free"):    "—",
    ("campaigns_sent", "starter"): "2",
    ("campaigns_sent", "growth"):  "8",
    ("campaigns_sent", "pro"):     "Unlimited",
    # ── Research ──────────────────────────────────────────────────────────
    ("competitive_research", "free"):    "—",
    ("competitive_research", "starter"): "3",
    ("competitive_research", "growth"):  "10",
    ("competitive_research", "pro"):     "Unlimited",
    ("growth_strategy", "free"):    "—",
    ("growth_strategy", "starter"): "1",
    ("growth_strategy", "growth"):  "4",
    ("growth_strategy", "pro"):     "Unlimited",
    ("research_run", "free"):    "—",
    ("research_run", "starter"): "—",
    ("research_run", "growth"):  "2",
    ("research_run", "pro"):     "10",
    # ── Analytics ─────────────────────────────────────────────────────────
    ("advanced_analytics", "free"):    "Basic",
    ("advanced_analytics", "starter"): "Full",
    ("advanced_analytics", "growth"):  "Full",
    ("advanced_analytics", "pro"):     "Full",
    # ── Stock footage row (uses plat_tiktok key — reuse for video rows) ───
}


def _cell(key: str, tier: str) -> str:
    if (key, tier) in FEATURE_OVERRIDES:
        return FEATURE_OVERRIDES[(key, tier)]
    val = PLANS[tier].get(key)
    return _fmt(val)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Public Pricing Page  GET /pricing
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    """Public pricing page — no authentication required."""

    # Build the feature comparison table rows HTML
    table_rows = ""
    for section in FEATURE_SECTIONS:
        table_rows += f"""
        <tr class="section-header">
          <td colspan="5">{section['label']}</td>
        </tr>"""
        for (label, key, _, _is_bool) in section["rows"]:
            cells = "".join(
                f'<td class="feat-cell">{_cell(key, t)}</td>'
                for t in ["free", "starter", "growth", "pro"]
            )
            table_rows += f"""
        <tr>
          <td class="feat-label">{label}</td>
          {cells}
        </tr>"""

    _PRICING_CSS = """
/* ── Pricing page shell ─────────────────────────────── */
.content-wrap{padding:0!important;max-width:100%!important}
.pricing-shell{
  background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);
  min-height:calc(100vh - 56px);color:#fff;padding-bottom:60px;
}
*{box-sizing:border-box}
.hero{text-align:center;padding:60px 20px 20px}
.hero h1{font-size:2.6rem;font-weight:800;margin-bottom:12px}
.hero p{font-size:1.15rem;opacity:.8;max-width:550px;margin:0 auto 32px}
.toggle-wrap{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:48px}
.toggle-label{font-size:.9rem;font-weight:600}
.annual-badge{background:#f59e0b;color:#000;font-size:.75rem;font-weight:700;
              padding:2px 8px;border-radius:20px;margin-left:6px}
.toggle{position:relative;display:inline-block;width:52px;height:28px}
.toggle input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;inset:0;background:#444;border-radius:28px;transition:.3s}
.slider:before{position:absolute;content:"";height:20px;width:20px;left:4px;bottom:4px;
               background:#fff;border-radius:50%;transition:.3s}
input:checked+.slider{background:#7c3aed}
input:checked+.slider:before{transform:translateX(24px)}
.plans-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
            gap:24px;max-width:1100px;margin:0 auto;padding:0 20px 60px}
.plan-card{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);
           border-radius:16px;padding:32px 24px;text-align:center;position:relative;transition:.2s}
.plan-card:hover{border-color:rgba(255,255,255,.3);transform:translateY(-2px)}
.plan-card.popular{border:2px solid #7c3aed;background:rgba(124,58,237,.12)}
.popular-badge{position:absolute;top:-14px;left:50%;transform:translateX(-50%);
               background:#7c3aed;color:#fff;font-size:.8rem;font-weight:700;
               padding:4px 16px;border-radius:20px}
.plan-name{font-size:1.3rem;font-weight:700;margin-bottom:6px}
.plan-tagline{font-size:.85rem;opacity:.65;margin-bottom:24px;min-height:36px}
.plan-price{font-size:2.8rem;font-weight:800;margin-bottom:4px}
.plan-price span{font-size:1rem;font-weight:400;opacity:.7}
.plan-annual-note{font-size:.8rem;opacity:.6;margin-bottom:24px;min-height:18px}
.plan-cta{display:block;width:100%;padding:12px;border-radius:10px;
          font-size:1rem;font-weight:700;cursor:pointer;border:none;
          transition:.15s;margin-bottom:8px}
.plan-cta.primary{background:#7c3aed;color:#fff}
.plan-cta.primary:hover{background:#6d28d9}
.plan-cta.outline{background:transparent;border:2px solid rgba(255,255,255,.3);color:#fff}
.plan-cta.outline:hover{border-color:#7c3aed;color:#c4b5fd}
.promo-row{margin-top:16px}
.promo-input{width:100%;padding:9px 12px;background:rgba(255,255,255,.07);
             border:1px solid rgba(255,255,255,.2);border-radius:8px;color:#fff;
             font-size:.85rem;text-align:center}
.promo-input::placeholder{opacity:.5}
.promo-msg{font-size:.78rem;margin-top:5px;min-height:18px}
.compare-section{max-width:1100px;margin:0 auto 80px;padding:0 20px}
.compare-section h2{font-size:1.8rem;font-weight:700;text-align:center;margin-bottom:32px}
.compare-table{width:100%;border-collapse:collapse;font-size:.88rem}
.compare-table th{background:rgba(124,58,237,.25);padding:14px 12px;
                  text-align:center;font-weight:700;border-bottom:1px solid rgba(255,255,255,.1)}
.compare-table th.col-feature{text-align:left}
.compare-table th.col-popular{background:rgba(124,58,237,.45)}
.compare-table td{padding:11px 12px;border-bottom:1px solid rgba(255,255,255,.06);
                  text-align:center;color:rgba(255,255,255,.85)}
.compare-table td.feat-label{text-align:left;color:rgba(255,255,255,.7)}
.compare-table tr.section-header td{background:rgba(255,255,255,.05);
  font-weight:700;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;
  color:rgba(255,255,255,.5);padding:10px 12px;text-align:left}
.compare-table tr:hover td{background:rgba(255,255,255,.03)}
.footer-cta{text-align:center;padding:40px 20px;opacity:.7;font-size:.9rem}
.footer-cta a{color:#c4b5fd}
"""

    contact_email = os.getenv("CONTACT_EMAIL", "support@alita.ai")

    _body = f"""
<div class="pricing-shell">
<div class="hero">
  <h1>Simple, transparent pricing</h1>
  <p>Replace your $5,000/mo marketing team with AI. No contracts, cancel anytime.</p>
  <div class="toggle-wrap">
    <span class="toggle-label">Monthly</span>
    <label class="toggle">
      <input type="checkbox" id="billing-toggle" onchange="switchBilling()">
      <span class="slider"></span>
    </label>
    <span class="toggle-label">Annual <span class="annual-badge">Save 20%</span></span>
  </div>
</div>

<div class="plans-grid">
  <div class="plan-card">
    <div class="plan-name">Free</div>
    <div class="plan-tagline">Get started — no credit card needed</div>
    <div class="plan-price">$0<span>/mo</span></div>
    <div class="plan-annual-note">&nbsp;</div>
    <a href="/account/signup" class="plan-cta outline">Get Started Free</a>
  </div>
  <div class="plan-card">
    <div class="plan-name">Starter</div>
    <div class="plan-tagline">Your first AI marketing hire</div>
    <div class="plan-price" id="price-starter">$97<span>/mo</span></div>
    <div class="plan-annual-note" id="note-starter">&nbsp;</div>
    <button class="plan-cta outline" onclick="startCheckout('starter')">Get Started</button>
  </div>
  <div class="plan-card popular">
    <span class="popular-badge">Most Popular</span>
    <div class="plan-name">Growth</div>
    <div class="plan-tagline">A full marketing department in your pocket</div>
    <div class="plan-price" id="price-growth">$197<span>/mo</span></div>
    <div class="plan-annual-note" id="note-growth">&nbsp;</div>
    <button class="plan-cta primary" onclick="startCheckout('growth')">Get Started</button>
  </div>
  <div class="plan-card">
    <div class="plan-name">Pro</div>
    <div class="plan-tagline">Replace your $3K/mo marketing agency</div>
    <div class="plan-price" id="price-pro">$397<span>/mo</span></div>
    <div class="plan-annual-note" id="note-pro">&nbsp;</div>
    <button class="plan-cta outline" onclick="startCheckout('pro')">Get Started</button>
  </div>
</div>

<div class="compare-section">
  <h2>Full Feature Comparison</h2>
  <table class="compare-table">
    <thead>
      <tr>
        <th class="col-feature">Feature</th>
        <th>Free</th>
        <th>Starter<br><small>$97/mo</small></th>
        <th class="col-popular">Growth<br><small>$197/mo</small></th>
        <th>Pro<br><small>$397/mo</small></th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
      <tr class="section-header"><td colspan="5">Support</td></tr>
      <tr><td class="feat-label">Support level</td>
          <td>Community</td><td>In-app chat</td>
          <td>Priority email</td><td>Priority + Slack</td></tr>
    </tbody>
  </table>
</div>

<div class="footer-cta">
  Already have an account? <a href="/account/login">Log in</a> &nbsp;|&nbsp;
    Questions? Email us at <a href="mailto:{contact_email}">{contact_email}</a>
</div>
</div>
"""

    _PRICING_JS = """
let billingPeriod = 'monthly';

const PRICES = {
  starter: { monthly: 97, annual_monthly: 78, annual_total: 936 },
  growth:  { monthly: 197, annual_monthly: 158, annual_total: 1896 },
  pro:     { monthly: 397, annual_monthly: 318, annual_total: 3816 },
};

function switchBilling() {
  billingPeriod = document.getElementById('billing-toggle').checked ? 'annual' : 'monthly';
  updatePrices();
}

function updatePrices() {
  ['starter','growth','pro'].forEach(tier => {
    const p = PRICES[tier];
    const priceEl = document.getElementById('price-'+tier);
    const noteEl  = document.getElementById('note-'+tier);
    if (billingPeriod === 'annual') {
      priceEl.innerHTML = '$'+p.annual_monthly+'<span>/mo</span>';
      noteEl.textContent = 'Billed $'+p.annual_total.toLocaleString()+' / year';
    } else {
      priceEl.innerHTML = '$'+p.monthly+'<span>/mo</span>';
      noteEl.textContent = '';
    }
  });
}

async function startCheckout(tier) {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Loading\u2026';
  try {
    const r = await fetch('/api/billing/checkout', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ tier, period: billingPeriod })
    });
    const data = await r.json();
    if (data.checkout_url) { window.location.href = data.checkout_url; }
    else if (data.redirect) { window.location.href = data.redirect; }
    else { alert(data.error || 'Could not start checkout. Please try again.'); btn.disabled=false; btn.textContent='Get Started'; }
  } catch(e) { alert('Something went wrong. Please try again.'); btn.disabled=false; btn.textContent='Get Started'; }
}
"""

    return HTMLResponse(build_page(
        title="Plans & Pricing",
        active_nav="billing",
        body_content=_body,
        extra_css=_PRICING_CSS,
        extra_js=_PRICING_JS,
        topbar_title="Plans &amp; Pricing",
    ))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Billing Management Page  GET /billing
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request, db: Session = Depends(get_db)):
    """Authenticated billing/plan management page."""
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/account/login?next=/billing", status_code=302)

    profile = _get_profile(user, db)
    if not profile:
        return RedirectResponse("/onboarding", status_code=302)

    tier    = profile.plan_tier or "free"
    status  = profile.plan_status or "active"
    period  = profile.plan_period or "monthly"
    limits  = PLANS.get(tier, PLANS["free"])

    # Pre-compute posts_created from JSONL (the source of truth for post scheduling)
    from utils.plan_limits import count_scheduled_posts_this_month, get_effective_limit
    _posts_used = count_scheduled_posts_this_month(profile.client_id)
    _active_addons = {}
    try:
        import json as _j
        _active_addons = _j.loads(profile.active_addons or "{}")
    except Exception:
        pass

    def usage_bar(metric: str, label: str, icon: str) -> str:
        if metric == "posts_created":
            used = _posts_used
            limit = get_effective_limit(tier, "posts_created", _active_addons)
        else:
            used  = getattr(profile, f"usage_{metric}", 0) or 0
            limit = limits.get(metric, 0)
        if limit == -1:
            pct = 5  # show tiny bar for "unlimited"
            limit_str = "Unlimited"
            pct_str = ""
        elif limit == 0:
            pct = 0
            limit_str = "Not included"
            pct_str = ""
        else:
            pct = min(100, round(used / limit * 100))
            limit_str = str(limit)
            pct_str = f"{used}/{limit}"
        color = "#ef4444" if pct >= 90 else "#f59e0b" if pct >= 70 else "#7c3aed"
        return f"""
        <div class="usage-item">
          <div class="usage-header">
            <span>{icon} {label}</span>
            <span class="usage-count">{pct_str if pct_str else limit_str}</span>
          </div>
          <div class="usage-track">
            <div class="usage-fill" style="width:{pct}%;background:{color}"></div>
          </div>
        </div>"""

    usage_html = (
        usage_bar("posts_created",         "AI Posts",                  "📝") +
        usage_bar("images_created",        "AI Images",                 "🎨") +
        usage_bar("videos_created",        "Faceless Videos",           "🎬") +
        usage_bar("replies_sent",          "Engagement Replies",        "💬") +
        usage_bar("campaigns_sent",        "Email Campaigns",           "📧") +
        usage_bar("research_run",          "Deep Research",             "🔬") +
        usage_bar("competitive_research",  "Competitive Research",      "🕵️") +
        usage_bar("growth_strategy",       "Growth Strategy Sessions",  "📈")
    )

    status_badge_color = {
        "active":   "#4ade80", "trialing": "#60a5fa",
        "past_due": "#f59e0b", "canceled": "#ef4444", "paused": "#94a3b8",
    }.get(status, "#94a3b8")

    price_mo = (PLAN_PRICE_ANNUAL_MONTHLY if period == "annual" else PLAN_PRICE_MONTHLY).get(tier, 0)
    price_display = f"${price_mo}/mo (billed {'annually' if period == 'annual' else 'monthly'})" if price_mo else "Free"

    next_tiers = [t for t in PLAN_ORDER if PLAN_ORDER.index(t) > PLAN_ORDER.index(tier)]

    # ── Build plan-switch cards (all paid tiers except current) ────
    has_sub      = bool(profile.stripe_subscription_id)
    is_canceling = (status == "canceling")
    cancel_end   = ""
    if is_canceling and getattr(profile, "trial_ends_at", None):
        cancel_end = profile.trial_ends_at.strftime("%B %d, %Y")

    switch_cards = ""
    for pt in PLAN_ORDER:
        if pt == "free" or pt == tier:
            continue
        mo       = PLAN_PRICE_MONTHLY.get(pt, 0)
        ann_mo   = PLAN_PRICE_ANNUAL_MONTHLY.get(pt, 0)
        is_up    = PLAN_ORDER.index(pt) > PLAN_ORDER.index(tier)
        arrow    = "⬆️ Upgrade" if is_up else "⬇️ Downgrade"
        btn_cls  = "uc-btn" if is_up else "uc-btn-down"
        switch_cards += f"""
        <div class="upgrade-card">
          <div class="uc-badge">{arrow}</div>
          <div class="uc-name">{PLAN_DISPLAY_NAMES[pt]}</div>
          <div class="uc-price" id="price-{pt}"><span class="price-mo">${mo}</span><span class="price-ann" style="display:none">${ann_mo}</span><span>/mo</span></div>
          <div class="uc-tag">{PLAN_TAGLINES.get(pt,'')}</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin-top:10px">
            <button class="{btn_cls}" onclick="doSwitch('{pt}', 'monthly')" id="btn-{pt}-monthly">Monthly</button>
            <button class="{btn_cls} btn-secondary" onclick="doSwitch('{pt}', 'annual')" id="btn-{pt}-annual">Annual (save 20%)</button>
          </div>
        </div>"""

    # ── Build active addons display ─────────────────────────────────
    active_addons_dict = _parse_active_addons(profile)
    active_addon_html = ""
    for ak, is_active in active_addons_dict.items():
        if not is_active:
            continue
        addon_info = ADDONS.get(ak)
        if not addon_info:
            continue
        active_addon_html += f"""
        <div class="addon-active-item">
          <span class="addon-check">✅</span>
          <div>
            <div class="addon-active-name">{addon_info['name']}</div>
            <div class="addon-active-desc">{addon_info['description']}</div>
          </div>
          <span class="addon-active-price">${addon_info['price']}/mo</span>
        </div>"""

    if not active_addon_html:
        active_addon_html = '<div style="color:#94a3b8;font-size:.9rem;padding:8px 0">No active add-ons yet.</div>'

    # ── Build add-on shop ───────────────────────────────────────────
    addon_shop_html = ""
    for ak, addon_info in ADDONS.items():
        is_active = active_addons_dict.get(ak, False)
        if is_active:
            btn = f'<button class="addon-btn addon-btn-active" disabled>✅ Active</button>'
        else:
            btn = f'<button class="addon-btn" onclick="buyAddon(\'{ak}\')">Add ${addon_info["price"]}/mo</button>'
        addon_shop_html += f"""
        <div class="addon-card">
          <div class="addon-card-name">{addon_info['name']}</div>
          <div class="addon-card-desc">{addon_info['description']}</div>
          {btn}
        </div>"""

    # ── Cancellation / resume banner ───────────────────────────────
    cancel_banner = ""
    if is_canceling and cancel_end:
        cancel_banner = f"""
  <div style="background:#fff8e1;border-left:4px solid #f59e0b;padding:14px 18px;border-radius:0 10px 10px 0;
              margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div>
      <p style="font-weight:700;color:#92400e;margin-bottom:2px">⏳ Cancellation scheduled</p>
      <p style="font-size:.86rem;color:#78350f">Your {PLAN_DISPLAY_NAMES.get(tier,tier.title())} plan is active until <strong>{cancel_end}</strong>. After that you'll move to Free.</p>
    </div>
    <button class="btn-primary" style="background:#16a34a" onclick="resumePlan()">↩️ Keep My Plan</button>
  </div>"""
    elif status == "canceled":
        cancel_banner = """
  <div style="background:#fef2f2;border-left:4px solid #ef4444;padding:14px 18px;border-radius:0 10px 10px 0;margin-bottom:20px">
    <p style="font-weight:700;color:#991b1b;margin-bottom:2px">🔴 Subscription ended</p>
    <p style="font-size:.86rem;color:#7f1d1d">Your paid plan has expired. Choose a plan below to reactivate.</p>
  </div>"""

    # ── Action buttons for current plan card ───────────────────────
    if tier == "free":
        plan_actions = '<a href="/pricing" class="btn-primary" style="text-decoration:none">⬆️ Upgrade Plan</a>'
    elif is_canceling:
        portal_btn = '<button class="btn-outline" onclick="openPortal()">⚙️ Billing Portal</button>' if profile.stripe_customer_id else ''
        plan_actions = f'<button class="btn-primary" style="background:#16a34a" onclick="resumePlan()">↩️ Resume Subscription</button>\n      {portal_btn}'
    else:
        mgr_btn = '<button class="btn-primary" onclick="openPortal()">⚙️ Manage Billing</button>' if profile.stripe_customer_id else ''
        plan_actions = f'{mgr_btn}\n      <button class="btn-danger" onclick="confirmCancel()">Cancel Plan</button>'

    switch_label = "Switch Plan" if has_sub else "Upgrade Your Plan"
    switch_note  = ("Upgrades take effect immediately with proration — you only pay the difference. "
                    "Downgrades activate at the next billing date.") if has_sub else "Choose a plan to get started."
    if switch_cards or next_tiers:
        plan_switch_section = (
            f'<div class="card">'
            f'<div class="card-label">{switch_label}</div>'
            f'<p style="font-size:.84rem;color:#64748b;margin:4px 0 16px">{switch_note}</p>'
            f'<div class="upgrade-grid">{switch_cards}</div>'
            f'</div>'
        )
    else:
        plan_switch_section = ""

    body = f"""
<div class="billing-wrap">
  <h1 class="page-title">💳 Billing &amp; Plan</h1>
  {cancel_banner}

  <!-- Current plan -->
  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-label">Current Plan</div>
        <div class="current-plan-name">{PLAN_DISPLAY_NAMES.get(tier, tier.title())}</div>
        <div class="current-plan-price">{price_display}</div>
      </div>
      <div>
        <span class="status-badge" style="background:{status_badge_color}20;color:{status_badge_color};
          padding:6px 14px;border-radius:20px;font-size:.85rem;font-weight:700;border:1px solid {status_badge_color}44">
          {"Cancels " + cancel_end if is_canceling and cancel_end else status.replace('_',' ').title()}
        </span>
      </div>
    </div>
    <div class="card-actions">
      {plan_actions}
      <a href="/pricing" class="btn-outline">View All Plans</a>
    </div>
  </div>

  <!-- Usage this month -->
  <div class="card">
    <div class="card-label">Usage This Month</div>
    <div class="usage-grid">
      {usage_html}
    </div>
    {'<div class="reset-note">Resets on your next billing date.</div>' if tier != 'free' else ''}
  </div>

  <!-- Switch / Upgrade / Downgrade plan -->
  {plan_switch_section}

  <!-- Active add-ons -->
  <div class="card">
    <div class="card-label">Active Add-Ons</div>
    <div class="addon-active-list">
      {active_addon_html}
    </div>
    {'<div style="margin-top:10px;font-size:.8rem;color:#64748b">Manage or cancel add-ons via <button class="link-btn" onclick="openPortal()">billing portal</button>.</div>' if profile.stripe_customer_id else ''}
  </div>

  <!-- Add-on shop -->
  <div class="card">
    <div class="card-label">Boost Packs & Add-Ons</div>
    <p style="font-size:.85rem;color:#64748b;margin:6px 0 16px">
      Stack extra capacity on top of your current plan. Available to all plans, cancel anytime.
    </p>
    <div class="addon-shop-grid">
      {addon_shop_html}
    </div>
  </div>

  <!-- Promo code -->
  <div class="card">
    <div class="card-label">Apply Promo Code</div>
    <div style="display:flex;gap:10px;margin-top:12px">
      <input id="promo-input" type="text" placeholder="Enter promo code"
        style="flex:1;padding:10px 14px;border-radius:8px;border:1px solid #e2e8f0;font-size:.95rem">
      <button class="btn-primary" onclick="applyPromo()" style="white-space:nowrap">Apply</button>
    </div>
    <div id="promo-result" style="margin-top:8px;font-size:.85rem"></div>
  </div>

</div>
<style>
.billing-wrap{{max-width:780px;margin:0 auto;padding:24px}}
.page-title{{font-size:1.6rem;font-weight:700;color:#1e293b;margin-bottom:24px}}
.card{{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;
       box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card-label{{font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
            color:#94a3b8;margin-bottom:8px}}
.card-header{{display:flex;justify-content:space-between;align-items:flex-start}}
.current-plan-name{{font-size:1.6rem;font-weight:800;color:#1e293b}}
.current-plan-price{{font-size:.9rem;color:#64748b;margin-top:4px}}
.card-actions{{display:flex;gap:12px;margin-top:20px;flex-wrap:wrap;align-items:center}}
.btn-primary{{padding:10px 20px;background:#7c3aed;color:#fff;border:none;
             border-radius:8px;font-weight:700;cursor:pointer;font-size:.95rem;text-decoration:none}}
.btn-primary:hover{{background:#6d28d9}}
.btn-outline{{padding:10px 20px;background:transparent;color:#7c3aed;
             border:2px solid #7c3aed;border-radius:8px;font-weight:700;cursor:pointer;font-size:.95rem;text-decoration:none}}
.btn-danger{{padding:10px 20px;background:transparent;color:#dc2626;
            border:2px solid #dc2626;border-radius:8px;font-weight:700;cursor:pointer;font-size:.95rem}}
.btn-danger:hover{{background:#fef2f2}}
.usage-grid{{display:flex;flex-direction:column;gap:14px;margin-top:14px}}
.usage-item{{}}
.usage-header{{display:flex;justify-content:space-between;font-size:.9rem;margin-bottom:5px;color:#374151}}
.usage-count{{font-weight:700;color:#1e293b}}
.usage-track{{height:7px;background:#f1f5f9;border-radius:4px;overflow:hidden}}
.usage-fill{{height:100%;border-radius:4px;transition:.3s}}
.reset-note{{font-size:.8rem;color:#94a3b8;margin-top:14px}}
.upgrade-grid{{display:flex;gap:14px;flex-wrap:wrap;margin-top:4px}}
.upgrade-card{{flex:1;min-width:200px;border:2px solid #e2e8f0;border-radius:12px;padding:20px;
              text-align:center;transition:.15s}}
.upgrade-card:hover{{border-color:#7c3aed}}
.uc-badge{{font-size:.75rem;font-weight:700;margin-bottom:6px;color:#6d28d9}}
.uc-name{{font-weight:700;font-size:1.1rem;margin-bottom:4px}}
.uc-price{{font-size:1.8rem;font-weight:800;color:#7c3aed;margin-bottom:2px}}
.uc-price span{{font-size:.9rem;font-weight:400;color:#64748b}}
.uc-tag{{font-size:.78rem;color:#64748b;margin:4px 0 12px}}
.uc-btn{{padding:7px 14px;background:#7c3aed;color:#fff;border:none;
         border-radius:7px;font-weight:700;cursor:pointer;font-size:.8rem}}
.uc-btn-down{{padding:7px 14px;background:#f1f5f9;color:#374151;border:1px solid #cbd5e1;
             border-radius:7px;font-weight:700;cursor:pointer;font-size:.8rem}}
.uc-btn:hover,.uc-btn-down:hover{{opacity:.85}}
.btn-secondary{{background:#f3f4f6 !important;color:#374151 !important;border:1px solid #d1d5db !important}}
/* Add-on styles */
.addon-active-list{{display:flex;flex-direction:column;gap:10px;margin-top:10px}}
.addon-active-item{{display:flex;align-items:center;gap:12px;padding:10px 14px;
  background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px}}
.addon-check{{font-size:1.1rem}}
.addon-active-name{{font-weight:700;font-size:.95rem;color:#166534}}
.addon-active-desc{{font-size:.8rem;color:#16a34a}}
.addon-active-price{{margin-left:auto;font-weight:700;font-size:.85rem;color:#15803d;white-space:nowrap}}
.addon-shop-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}}
.addon-card{{border:1px solid #e2e8f0;border-radius:10px;padding:16px;text-align:center}}
.addon-card-name{{font-weight:700;font-size:.95rem;margin-bottom:6px;color:#1e293b}}
.addon-card-desc{{font-size:.78rem;color:#64748b;margin-bottom:12px;min-height:32px}}
.addon-btn{{padding:8px 14px;background:#7c3aed;color:#fff;border:none;
            border-radius:7px;font-weight:700;cursor:pointer;font-size:.82rem;width:100%}}
.addon-btn:hover{{background:#6d28d9}}
.addon-btn-active{{background:#16a34a;cursor:default}}
.addon-btn-active:hover{{background:#16a34a}}
.link-btn{{background:none;border:none;color:#7c3aed;cursor:pointer;
           font-size:.8rem;text-decoration:underline;padding:0}}
</style>
<script>
const HAS_SUB = {'true' if has_sub else 'false'};

async function openPortal() {{
  const r = await fetch('/api/billing/portal', {{method:'POST'}});
  const d = await r.json();
  if (d.portal_url) window.location.href = d.portal_url;
  else alert('Could not open billing portal. Please try again.');
}}

async function doSwitch(tier, period) {{
  if (!HAS_SUB) {{
    // No subscription yet — go to checkout
    return startCheckout(tier, period);
  }}
  const action = {PLAN_ORDER!r}.indexOf(tier) > {PLAN_ORDER!r}.indexOf('{tier}') ? 'upgrade' : 'downgrade';
  const msg = action === 'upgrade'
    ? `Upgrade to ${{tier}} (${{period}})? You'll be charged the prorated difference immediately.`
    : `Downgrade to ${{tier}} (${{period}})? This takes effect at your next billing date.`;
  if (!confirm(msg)) return;
  const r = await fetch('/api/billing/change-plan', {{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{tier, period}})
  }});
  const d = await r.json();
  if (d.ok) {{
    alert(`✅ Plan ${{d.action}} to ${{tier}} (${{period}}) successfully!`);
    window.location.reload();
  }} else if (d.redirect) {{
    window.location.href = d.redirect;
  }} else {{
    alert('❌ ' + (d.error || 'Something went wrong. Please try again.'));
  }}
}}

async function startCheckout(tier, period='monthly') {{
  const r = await fetch('/api/billing/checkout', {{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{tier, period, promo_code:null}})
  }});
  const d = await r.json();
  if (d.checkout_url) window.location.href = d.checkout_url;
  else if (d.redirect) window.location.href = d.redirect;
  else alert(d.error || 'Could not start checkout.');
}}

function confirmCancel() {{
  if (!confirm('Cancel your subscription? You\\'ll keep access until the end of the current billing period, then move to the free plan. You can resume anytime before then.')) return;
  cancelPlan();
}}

async function cancelPlan() {{
  const r = await fetch('/api/billing/cancel', {{method:'POST'}});
  const d = await r.json();
  if (d.ok) {{
    alert('Your subscription has been scheduled for cancellation at the end of the billing period.');
    window.location.reload();
  }} else {{
    alert('❌ ' + (d.error || 'Could not cancel. Please try again or use the billing portal.'));
  }}
}}

async function resumePlan() {{
  const r = await fetch('/api/billing/resume', {{method:'POST'}});
  const d = await r.json();
  if (d.ok) {{
    alert('✅ Cancellation reversed — your subscription will continue!');
    window.location.reload();
  }} else {{
    alert('❌ ' + (d.error || 'Could not resume. Please contact support.'));
  }}
}}

async function applyPromo() {{
  const code = document.getElementById('promo-input').value.trim().toUpperCase();
  if (!code) return;
  const resultEl = document.getElementById('promo-result');
  resultEl.style.color = '#94a3b8';
  resultEl.textContent = 'Checking…';
  const r = await fetch('/api/billing/validate-promo', {{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{code}})
  }});
  const d = await r.json();
  if (d.valid) {{
    resultEl.style.color = '#16a34a';
    resultEl.textContent = '✅ ' + d.message + ' — your discount will be applied at checkout.';
  }} else {{
    resultEl.style.color = '#dc2626';
    resultEl.textContent = '❌ ' + (d.message || 'Invalid promo code');
  }}
}}

async function buyAddon(addonKey) {{
  try {{
    const r = await fetch('/api/billing/addon-checkout', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{addon_key: addonKey}})
    }});
    const d = await r.json();
    if (d.checkout_url) window.location.href = d.checkout_url;
    else if (d.redirect) window.location.href = d.redirect;
    else alert(d.error || 'Could not start checkout. Please try again.');
  }} catch(e) {{
    alert('Something went wrong. Please try again.');
  }}
}}
</script>
"""

    return HTMLResponse(build_page(
        title="Billing & Plan",
        active_nav="billing",
        body_content=body,
        user_name=user.full_name,
        business_name=getattr(profile, "business_name", ""),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Create Stripe Checkout Session  POST /api/billing/checkout
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/checkout")
async def create_checkout(request: Request, db: Session = Depends(get_db)):
    """
    Create a Stripe Checkout session. If the user isn't logged in,
    redirect them to signup with a return URL.
    """
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)

    try:
        body = await request.json()
    except Exception:
        body = {}

    tier       = body.get("tier", "starter")
    period     = body.get("period", "monthly")
    promo_code = body.get("promo_code", None)

    # Redirect unauthenticated users to signup
    if not user:
        return JSONResponse({"redirect": f"/account/signup?next=/pricing&tier={tier}&period={period}"})

    profile = _get_profile(user, db)
    if not profile:
        return JSONResponse({"redirect": "/onboarding"})

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Payment system not configured. Contact support."}, status_code=503)

    price_id = STRIPE_PRICE_IDS.get((tier, period), "")
    if not price_id:
        return JSONResponse({"error": f"No Stripe price configured for {tier}/{period}. Contact support."}, status_code=400)

    stripe = _stripe()

    # Get or create Stripe customer
    customer_id = profile.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name,
            metadata={"client_id": profile.client_id, "user_id": user.id},
        )
        customer_id = customer["id"]
        profile.stripe_customer_id = customer_id
        db.add(profile)
        db.commit()

    session_params = {
        "customer": customer_id,
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{APP_BASE_URL}/billing?success=1",
        "cancel_url":  f"{APP_BASE_URL}/pricing",
        "subscription_data": {
            "metadata": {
                "client_id": profile.client_id,
                "tier": tier,
                "period": period,
            }
        },
        "metadata": {
            "client_id": profile.client_id,
            "tier": tier,
            "period": period,
        },
        "allow_promotion_codes": True,   # lets clients enter codes at Stripe checkout too
    }

    # Pre-apply promo code if provided and valid
    if promo_code:
        try:
            coupons = stripe.Coupon.list(limit=100)
            # Also check promotion codes
            promo_codes = stripe.PromotionCode.list(code=promo_code, active=True, limit=1)
            if promo_codes.data:
                session_params["discounts"] = [{"promotion_code": promo_codes.data[0]["id"]}]
                session_params.pop("allow_promotion_codes", None)
        except Exception:
            pass

    session = stripe.checkout.Session.create(**session_params)
    return JSONResponse({"checkout_url": session["url"]})


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stripe Customer Portal  POST /api/billing/portal
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/portal")
async def customer_portal(request: Request, db: Session = Depends(get_db)):
    """Redirect client to Stripe's self-service billing portal."""
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    profile = _get_profile(user, db)
    if not profile or not profile.stripe_customer_id:
        return JSONResponse({"error": "No billing account found."}, status_code=400)

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Payment system not configured."}, status_code=503)

    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=profile.stripe_customer_id,
        return_url=f"{APP_BASE_URL}/billing",
    )
    return JSONResponse({"portal_url": session["url"]})


# ─────────────────────────────────────────────────────────────────────────────
# 4b. Purchase Add-On  POST /api/billing/addon-checkout
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/addon-checkout")
async def addon_checkout(request: Request, db: Session = Depends(get_db)):
    """
    Create a Stripe Checkout session for a single add-on product.
    Add-ons are separate recurring subscriptions stacked on top of any base plan.
    Available to all tiers including Free.
    """
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"redirect": "/account/login?next=/billing"})

    profile = _get_profile(user, db)
    if not profile:
        return JSONResponse({"redirect": "/onboarding"})

    try:
        body = await request.json()
    except Exception:
        body = {}

    addon_key = body.get("addon_key", "")
    addon = ADDONS.get(addon_key)
    if not addon:
        return JSONResponse({"error": f"Unknown add-on: {addon_key}"}, status_code=400)

    price_id = ADDON_STRIPE_PRICE_IDS.get(addon_key, "")
    if not price_id:
        return JSONResponse({"error": f"Add-on not yet configured — price ID missing. Contact support."}, status_code=400)

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Payment system not configured."}, status_code=503)

    stripe = _stripe()

    # Get or create Stripe customer
    customer_id = profile.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name,
            metadata={"client_id": profile.client_id, "user_id": user.id},
        )
        customer_id = customer["id"]
        profile.stripe_customer_id = customer_id
        db.add(profile)
        db.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{APP_BASE_URL}/billing?addon_success=1&addon={addon_key}",
        cancel_url=f"{APP_BASE_URL}/billing",
        subscription_data={
            "metadata": {
                "client_id": profile.client_id,
                "addon_key": addon_key,
                "type": "addon",
            }
        },
        metadata={
            "client_id": profile.client_id,
            "addon_key": addon_key,
            "type": "addon",
        },
        allow_promotion_codes=True,
    )
    return JSONResponse({"checkout_url": session["url"]})


# ─────────────────────────────────────────────────────────────────────────────
# 5. Validate Promo Code  POST /api/billing/validate-promo
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/validate-promo")
async def validate_promo(request: Request):
    """
    Validate a Stripe promotion code.
    Returns {valid: true, percent_off: 20, message: "20% off applied!"}
    or      {valid: false, message: "Invalid or expired code"}
    """
    try:
        body = await request.json()
        code = (body.get("code") or "").strip().upper()
    except Exception:
        return JSONResponse({"valid": False, "message": "Bad request"})

    if not code:
        return JSONResponse({"valid": False, "message": "Please enter a code"})

    if not STRIPE_SECRET_KEY:
        # If Stripe isn't configured, still allow basic testing
        return JSONResponse({"valid": False, "message": "Payment system not configured"})

    stripe = _stripe()
    try:
        promo_codes = stripe.PromotionCode.list(code=code, active=True, limit=1)
        if not promo_codes.data:
            return JSONResponse({"valid": False, "message": "Invalid or expired promo code"})

        pc = promo_codes.data[0]
        coupon = pc["coupon"]

        if not coupon.get("valid", False):
            return JSONResponse({"valid": False, "message": "This promo code has expired"})

        percent_off  = coupon.get("percent_off") or 0
        amount_off   = coupon.get("amount_off") or 0
        duration     = coupon.get("duration", "once")
        duration_map = {"once": "one-time", "repeating": f"for {coupon.get('duration_in_months','')} months", "forever": "forever"}

        if percent_off:
            msg = f"{int(percent_off)}% off {duration_map.get(duration,'')}"
        elif amount_off:
            msg = f"${amount_off/100:.0f} off {duration_map.get(duration,'')}"
        else:
            msg = "Discount applied"

        return JSONResponse({
            "valid":       True,
            "percent_off": percent_off or 0,
            "amount_off":  amount_off,
            "message":     msg.strip(),
        })

    except Exception as e:
        return JSONResponse({"valid": False, "message": f"Could not validate code: {str(e)}"})


# ─────────────────────────────────────────────────────────────────────────────
# 6a. Change Plan (Upgrade / Downgrade)  POST /api/billing/change-plan
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/change-plan")
async def change_plan(request: Request, db: Session = Depends(get_db)):
    """
    Upgrade or downgrade an existing Stripe subscription in-place.
    Stripe automatically prorates: credits unused days of old plan, charges
    the difference for the new plan immediately.
    No need to create separate "difference price" products in Stripe.
    """
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    profile = _get_profile(user, db)
    if not profile:
        return JSONResponse({"error": "No profile found."}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    new_tier   = body.get("tier", "")
    new_period = body.get("period", profile.plan_period or "monthly")

    if not new_tier or new_tier not in PLAN_ORDER:
        return JSONResponse({"error": f"Invalid plan tier: {new_tier}"}, status_code=400)

    if new_tier == profile.plan_tier and new_period == profile.plan_period:
        return JSONResponse({"error": "You are already on this plan."}, status_code=400)

    new_price_id = STRIPE_PRICE_IDS.get((new_tier, new_period), "")
    if not new_price_id:
        return JSONResponse(
            {"error": f"No Stripe price configured for {new_tier}/{new_period}. Contact support."},
            status_code=400,
        )

    if not profile.stripe_subscription_id:
        # No active subscription — fall through to checkout flow
        return JSONResponse({"redirect": f"/pricing?tier={new_tier}&period={new_period}"})

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Payment system not configured."}, status_code=503)

    stripe = _stripe()

    try:
        sub = stripe.Subscription.retrieve(profile.stripe_subscription_id)
        if sub["status"] in ("canceled", "incomplete_expired"):
            # Subscription already gone — create a fresh one
            return JSONResponse({"redirect": f"/pricing?tier={new_tier}&period={new_period}"})

        # Get the current subscription item ID to replace
        current_item_id = sub["items"]["data"][0]["id"]
        is_upgrade = PLAN_ORDER.index(new_tier) > PLAN_ORDER.index(profile.plan_tier)

        # Modify the subscription with immediate proration
        updated_sub = stripe.Subscription.modify(
            profile.stripe_subscription_id,
            cancel_at_period_end=False,   # undo any pending cancellation on upgrade
            proration_behavior="create_prorations",
            items=[{
                "id":    current_item_id,
                "price": new_price_id,
            }],
            metadata={
                "client_id": profile.client_id,
                "tier":      new_tier,
                "period":    new_period,
            },
        )

        # Update DB immediately (webhook will re-confirm)
        profile.plan_tier   = new_tier
        profile.plan_period = new_period
        profile.plan_status = "active"
        db.add(profile)
        db.commit()

        action = "upgraded" if is_upgrade else "downgraded"
        print(f"✅ Plan {action}: {profile.client_id} → {new_tier}/{new_period}")
        return JSONResponse({"ok": True, "action": action, "tier": new_tier, "period": new_period})

    except Exception as e:
        print(f"⚠️  change-plan error for {profile.client_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────────────────────────────────────
# 6b. Cancel Subscription  POST /api/billing/cancel
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/cancel")
async def cancel_subscription(request: Request, db: Session = Depends(get_db)):
    """
    Schedule cancellation at the end of the current billing period.
    The user keeps full access until period end — no immediate downgrade.
    """
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    profile = _get_profile(user, db)
    if not profile or not profile.stripe_subscription_id:
        return JSONResponse({"error": "No active subscription found."}, status_code=400)

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Payment system not configured."}, status_code=503)

    stripe = _stripe()
    try:
        sub = stripe.Subscription.modify(
            profile.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        # Store the period-end date so we can show it in the UI
        period_end = sub.get("current_period_end")
        profile.plan_status = "canceling"
        if period_end:
            from datetime import timezone
            profile.trial_ends_at = datetime.fromtimestamp(period_end, tz=timezone.utc)
        db.add(profile)
        db.commit()
        print(f"🔶 Cancellation scheduled for {profile.client_id} at period end")
        return JSONResponse({"ok": True, "period_end": period_end})
    except Exception as e:
        print(f"⚠️  cancel error for {profile.client_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────────────────────────────────────
# 6c. Resume Subscription  POST /api/billing/resume
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/resume")
async def resume_subscription(request: Request, db: Session = Depends(get_db)):
    """Undo a scheduled cancellation — keeps the subscription active."""
    from api.auth_routes import get_current_user
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    profile = _get_profile(user, db)
    if not profile or not profile.stripe_subscription_id:
        return JSONResponse({"error": "No subscription found."}, status_code=400)

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Payment system not configured."}, status_code=503)

    stripe = _stripe()
    try:
        stripe.Subscription.modify(
            profile.stripe_subscription_id,
            cancel_at_period_end=False,
        )
        profile.plan_status  = "active"
        profile.trial_ends_at = None
        db.add(profile)
        db.commit()
        print(f"✅ Cancellation reversed for {profile.client_id}")
        return JSONResponse({"ok": True})
    except Exception as e:
        print(f"⚠️  resume error for {profile.client_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Stripe Webhook  POST /api/billing/webhook
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/billing/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe sends signed events here.
    Handles: checkout.session.completed, invoice.payment_succeeded,
             invoice.payment_failed, customer.subscription.deleted,
             customer.subscription.updated
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_SECRET_KEY:
        return JSONResponse({"error": "Stripe not configured"}, status_code=503)

    stripe = _stripe()

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            # Dev mode — no signature check
            import json as _json
            event = _json.loads(payload)
    except Exception as e:
        print(f"⚠️  Stripe webhook error: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)

    event_type = event.get("type", "")
    data_obj   = event.get("data", {}).get("object", {})
    print(f"📦 Stripe webhook: {event_type}")

    def _find_profile_by_customer(customer_id: str):
        return db.query(ClientProfile).filter(
            ClientProfile.stripe_customer_id == customer_id
        ).first()

    def _find_profile_by_client_id(client_id: str):
        return db.query(ClientProfile).filter(
            ClientProfile.client_id == client_id
        ).first()

    # ── checkout.session.completed ─────────────────────────────────────────
    if event_type == "checkout.session.completed":
        meta        = data_obj.get("metadata", {})
        client_id   = meta.get("client_id")
        event_type_ = meta.get("type", "subscription")   # "addon" or "subscription"
        sub_id      = data_obj.get("subscription")
        customer_id = data_obj.get("customer")

        profile = _find_profile_by_client_id(client_id) if client_id else None
        if not profile and customer_id:
            profile = _find_profile_by_customer(customer_id)

        if not profile:
            print(f"⚠️  No profile found for client_id={client_id}")
            return JSONResponse({"received": True})

        if event_type_ == "addon":
            # ── Add-on purchase ──────────────────────────────────────
            addon_key = meta.get("addon_key", "")
            if addon_key and addon_key in ADDONS:
                import json as _json
                # Activate the addon
                raw = profile.active_addons or "{}"
                current = {}
                try:
                    current = _json.loads(raw) if isinstance(raw, str) else (raw or {})
                except Exception:
                    pass
                current[addon_key] = True
                profile.active_addons = _json.dumps(current)

                # Track the subscription ID for cancellation
                raw_subs = profile.addon_subscription_ids or "{}"
                subs = {}
                try:
                    subs = _json.loads(raw_subs) if isinstance(raw_subs, str) else (raw_subs or {})
                except Exception:
                    pass
                if sub_id:
                    subs[addon_key] = sub_id
                profile.addon_subscription_ids = _json.dumps(subs)

                db.add(profile)
                db.commit()
                print(f"✅ Add-on activated: {addon_key} for {profile.client_id}")
        else:
            # ── Base plan subscription ────────────────────────────────
            tier   = meta.get("tier", "starter")
            period = meta.get("period", "monthly")

            profile.plan_tier              = tier
            profile.plan_status            = "active"
            profile.plan_period            = period
            profile.stripe_subscription_id = sub_id
            if customer_id:
                profile.stripe_customer_id = customer_id
            profile.plan_activated_at      = datetime.now(timezone.utc)

            # If this checkout was initiated during onboarding, complete the wizard
            if meta.get("onboarding") == "1" or (
                getattr(profile, "onboarding_step", None) is not None
                and 1 <= (profile.onboarding_step or 0) <= 6
            ):
                profile.onboarding_step = 7
                profile.onboarding_status = "complete"

            db.add(profile)
            db.commit()
            print(f"✅ Client {profile.client_id} activated on {tier}/{period}")

    # ── invoice.payment_succeeded ──────────────────────────────────────────
    elif event_type == "invoice.payment_succeeded":
        customer_id = data_obj.get("customer")
        profile = _find_profile_by_customer(customer_id)
        if profile:
            profile.plan_status = "active"
            # Reset monthly usage counters on successful payment / renewal
            profile.usage_posts_created        = 0
            profile.usage_images_created       = 0
            profile.usage_videos_created       = 0
            profile.usage_replies_sent         = 0
            profile.usage_campaigns_sent       = 0
            profile.usage_research_run         = 0
            profile.usage_competitive_research = 0
            profile.usage_growth_strategy      = 0
            profile.usage_reset_at             = datetime.now(timezone.utc)
            db.add(profile)
            db.commit()
            print(f"✅ Renewed + usage reset for {profile.client_id}")

    # ── invoice.payment_failed ──────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        customer_id = data_obj.get("customer")
        profile = _find_profile_by_customer(customer_id)
        if profile:
            profile.plan_status = "past_due"
            db.add(profile)
            db.commit()
            print(f"⚠️  Payment failed for {profile.client_id}")

    # ── customer.subscription.deleted ──────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        customer_id = data_obj.get("customer")
        sub_id      = data_obj.get("id")
        profile = _find_profile_by_customer(customer_id)
        if profile:
            import json as _json
            # Check if this is an addon subscription
            raw_subs = profile.addon_subscription_ids or "{}"
            subs = {}
            try:
                subs = _json.loads(raw_subs) if isinstance(raw_subs, str) else (raw_subs or {})
            except Exception:
                pass

            addon_key_canceled = next((k for k, v in subs.items() if v == sub_id), None)
            if addon_key_canceled:
                # Deactivate the addon
                raw = profile.active_addons or "{}"
                current = {}
                try:
                    current = _json.loads(raw) if isinstance(raw, str) else (raw or {})
                except Exception:
                    pass
                current.pop(addon_key_canceled, None)
                profile.active_addons = _json.dumps(current)
                subs.pop(addon_key_canceled, None)
                profile.addon_subscription_ids = _json.dumps(subs)
                db.add(profile)
                db.commit()
                print(f"🔴 Add-on canceled: {addon_key_canceled} for {profile.client_id}")
            elif data_obj.get("id") == profile.stripe_subscription_id:
                # Main plan cancelled
                profile.plan_tier              = "free"
                profile.plan_status            = "canceled"
                profile.stripe_subscription_id = None
                db.add(profile)
                db.commit()
                print(f"🔴 Plan canceled for {profile.client_id}, downgraded to free")

    # ── customer.subscription.updated ──────────────────────────────────────
    elif event_type == "customer.subscription.updated":
        customer_id = data_obj.get("customer")
        profile = _find_profile_by_customer(customer_id)
        if profile:
            stripe_status       = data_obj.get("status", "active")
            cancel_at_period_end = data_obj.get("cancel_at_period_end", False)
            cancel_at           = data_obj.get("cancel_at")   # unix timestamp or None

            status_map = {
                "active":               "active",
                "trialing":             "trialing",
                "past_due":             "past_due",
                "canceled":             "canceled",
                "paused":               "paused",
                "incomplete":           "past_due",
                "incomplete_expired":   "canceled",
            }
            new_status = status_map.get(stripe_status, "active")

            # If scheduled to cancel, override status to "canceling"
            if cancel_at_period_end and new_status == "active":
                new_status = "canceling"
                if cancel_at:
                    from datetime import timezone
                    profile.trial_ends_at = datetime.fromtimestamp(cancel_at, tz=timezone.utc)
            elif not cancel_at_period_end and profile.plan_status == "canceling":
                # Cancellation was undone
                profile.trial_ends_at = None

            profile.plan_status = new_status

            # Check if tier/price changed (upgrade or downgrade)
            items = data_obj.get("items", {}).get("data", [])
            if items:
                price_id = items[0].get("price", {}).get("id", "")
                new_tier, new_period = _tier_from_price_id(price_id)
                if new_tier != "free":
                    profile.plan_tier   = new_tier
                    profile.plan_period = new_period
                else:
                    # Fallback: check subscription metadata for tier
                    sub_meta = data_obj.get("metadata", {})
                    meta_tier = sub_meta.get("tier", "")
                    meta_period = sub_meta.get("period", "")
                    if meta_tier and meta_tier != "free":
                        profile.plan_tier   = meta_tier
                        profile.plan_period = meta_period or profile.plan_period
                        print(f"🔄 Used subscription metadata fallback: {meta_tier}/{meta_period}")
            db.add(profile)
            db.commit()
            print(f"🔄 Subscription updated for {profile.client_id}: {profile.plan_tier}/{profile.plan_status} cancel_at_period_end={cancel_at_period_end}")

    return JSONResponse({"received": True})


# ─────────────────────────────────────────────────────────────────────────────
# 7. DB migration helper — adds new columns if they don't exist (SQLite safe)
# ─────────────────────────────────────────────────────────────────────────────

def migrate_billing_columns(engine):
    """
    Safely add billing + usage columns to client_profiles table
    if they don't already exist. Call once at startup.
    """
    new_columns = [
        ("plan_tier",              "VARCHAR(20) DEFAULT 'free' NOT NULL"),
        ("plan_status",            "VARCHAR(20) DEFAULT 'active' NOT NULL"),
        ("plan_period",            "VARCHAR(20) DEFAULT 'monthly' NOT NULL"),
        ("stripe_customer_id",     "VARCHAR(100)"),
        ("stripe_subscription_id", "VARCHAR(100)"),
        ("trial_ends_at",          "DATETIME"),
        ("plan_activated_at",      "DATETIME"),
        ("usage_posts_created",        "INTEGER DEFAULT 0"),
        ("usage_images_created",       "INTEGER DEFAULT 0"),
        ("usage_videos_created",        "INTEGER DEFAULT 0"),
        ("usage_replies_sent",          "INTEGER DEFAULT 0"),
        ("usage_campaigns_sent",        "INTEGER DEFAULT 0"),
        ("usage_research_run",          "INTEGER DEFAULT 0"),
        ("usage_competitive_research",  "INTEGER DEFAULT 0"),
        ("usage_growth_strategy",       "INTEGER DEFAULT 0"),
        ("usage_reset_at",              "DATETIME"),
        # Add-on tracking
        ("active_addons",               "TEXT DEFAULT '{}'"),
        ("addon_subscription_ids",      "TEXT DEFAULT '{}'"),
    ]
    with engine.connect() as conn:
        from sqlalchemy import text, inspect
        inspector = inspect(engine)
        try:
            existing = {c["name"] for c in inspector.get_columns("client_profiles")}
        except Exception:
            return
        for col_name, col_def in new_columns:
            if col_name not in existing:
                try:
                    conn.execute(text(
                        f"ALTER TABLE client_profiles ADD COLUMN {col_name} {col_def}"
                    ))
                    conn.commit()
                    print(f"✅ Added column: client_profiles.{col_name}")
                except Exception as e:
                    print(f"⚠️  Could not add {col_name}: {e}")
