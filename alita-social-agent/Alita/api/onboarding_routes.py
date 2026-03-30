"""
api/onboarding_routes.py
6-Step Onboarding Wizard:
  Step 1: Welcome / Meet Alita (tutorial + direct line to founder)
  Step 2: Business Profile (business name, niche, description)
  Step 3: Knowledge Base (website scrape / file upload / manual)
  Step 4: Tone & Style (skippable)
  Step 5: Connect Platforms (skippable)
  Step 6: Choose a Plan (required -- explicit choice including Free)
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import anthropic
from fastapi import APIRouter, File, Request, Form, Depends, BackgroundTasks, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from api.auth_routes import get_current_user, require_auth
from database.db import get_db
from database.models import (
    ClientProfile, DeepResearchRequest,
    OnboardingStatus, OnboardingMethod, DeepResearchStatus
)

router = APIRouter(tags=["onboarding"])

TOTAL_STEPS = 6  # steps 1-6, step 7 = complete

# -------------------------------------------------------
# Shared CSS / layout
# -------------------------------------------------------

SHARED_CSS = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
  min-height: 100vh;
  color: white;
  padding: 20px;
}
.wrap { max-width: 720px; margin: 0 auto; padding: 40px 0; }
.logo { text-align: center; margin-bottom: 32px; }
.logo h1 { font-size: 2rem; font-weight: 800; background: linear-gradient(135deg, #6366f1, #8b5cf6, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.logo p { color: rgba(255,255,255,0.4); margin-top: 6px; }
.card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 36px; margin-bottom: 24px; }
.card h2 { font-size: 1.4rem; font-weight: 700; margin-bottom: 8px; }
.card .sub { color: rgba(255,255,255,0.5); font-size: 0.9rem; margin-bottom: 24px; }
label { display: block; font-size: 0.85rem; color: rgba(255,255,255,0.6); margin-bottom: 6px; margin-top: 16px; }
input[type=text], input[type=url], textarea, select {
  width: 100%; padding: 12px 16px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 10px; color: white; font-size: 0.95rem; outline: none;
}
input:focus, textarea:focus { border-color: #6366f1; }
input::placeholder, textarea::placeholder { color: rgba(255,255,255,0.25); }
textarea { min-height: 90px; resize: vertical; }
.btn {
  display: inline-block; padding: 14px 28px; margin-top: 24px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white; border: none; border-radius: 12px;
  font-size: 1rem; font-weight: 700; cursor: pointer;
  text-decoration: none; transition: opacity 0.2s;
}
.btn:hover { opacity: 0.9; }
.btn-outline { background: transparent; border: 2px solid rgba(255,255,255,0.2); }
.btn-outline:hover { background: rgba(255,255,255,0.05); opacity: 1; }
.btn-full { width: 100%; text-align: center; }
.tabs { display: flex; gap: 12px; margin-bottom: 28px; }
.tab { flex: 1; padding: 20px; border-radius: 14px; cursor: pointer; text-align: center; border: 2px solid transparent; transition: all 0.2s; background: rgba(255,255,255,0.04); }
.tab.active { border-color: #6366f1; background: rgba(99,102,241,0.1); }
.tab .icon { font-size: 2rem; margin-bottom: 8px; }
.tab .label { font-weight: 700; font-size: 1rem; }
.tab .desc { font-size: 0.78rem; color: rgba(255,255,255,0.4); margin-top: 4px; }
.status-box { border-radius: 14px; padding: 24px; text-align: center; }
.status-box.processing { background: rgba(251,191,36,0.1); border: 1px solid rgba(251,191,36,0.3); }
.status-box.success { background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.3); }
.status-box.error { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); }
.status-box.pending { background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.3); }
.status-box h3 { font-size: 1.2rem; margin-bottom: 8px; }
.status-box p { font-size: 0.88rem; color: rgba(255,255,255,0.6); }
.step-list { list-style: none; }
.step-list li { display: flex; align-items: flex-start; gap: 12px; padding: 8px 0; font-size: 0.9rem; color: rgba(255,255,255,0.7); }
.step-list .dot { width: 8px; height: 8px; border-radius: 50%; background: #6366f1; margin-top: 6px; flex-shrink: 0; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; }
.badge-pending { background: rgba(251,191,36,0.2); color: #fbbf24; }
.badge-approved { background: rgba(52,211,153,0.2); color: #34d399; }
.badge-rejected { background: rgba(239,68,68,0.2); color: #f87171; }
.hint { font-size: 0.78rem; color: rgba(255,255,255,0.3); margin-top: 4px; }
.divider { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 24px 0; }
.nav-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }
.nav-top a { color: rgba(255,255,255,0.4); text-decoration: none; font-size: 0.85rem; }
.nav-top a:hover { color: white; }
.spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: white; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.upload-zone {
  border: 2px dashed rgba(99,102,241,0.4); border-radius: 14px;
  padding: 40px 20px; text-align: center; cursor: pointer;
  transition: all 0.2s; user-select: none;
}
.upload-zone:hover, .upload-zone.dragover {
  border-color: #6366f1; background: rgba(99,102,241,0.08);
}
.upload-zone .uz-icon { font-size: 3rem; margin-bottom: 10px; }
.upload-zone .uz-label { font-weight: 700; font-size: 1rem; margin-bottom: 4px; }
.upload-zone .uz-sub { font-size: 0.8rem; color: rgba(255,255,255,0.4); }
.file-list { margin-top: 14px; }
.file-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; background: rgba(255,255,255,0.06);
  border-radius: 8px; margin-top: 6px; font-size: 0.85rem;
}
.file-item .f-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-item .f-size { color: rgba(255,255,255,0.4); font-size: 0.78rem; flex-shrink: 0; }
input[type=file] { display: none; }

/* -- Progress bar ---------------------------------------- */
.progress-bar { display: flex; align-items: center; gap: 0; margin: 0 auto 36px; max-width: 480px; }
.progress-step {
  display: flex; flex-direction: column; align-items: center; flex: 1; position: relative;
}
.progress-step .circle {
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.78rem; font-weight: 700;
  border: 2px solid rgba(255,255,255,0.15);
  color: rgba(255,255,255,0.35);
  background: rgba(255,255,255,0.04);
  transition: all 0.3s;
  z-index: 2;
}
.progress-step.done .circle {
  background: #6366f1; border-color: #6366f1; color: white;
}
.progress-step.active .circle {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-color: #8b5cf6; color: white;
  box-shadow: 0 0 14px rgba(99,102,241,0.5);
}
.progress-step .step-label {
  font-size: 0.62rem; color: rgba(255,255,255,0.3);
  margin-top: 6px; text-align: center; white-space: nowrap;
}
.progress-step.done .step-label,
.progress-step.active .step-label { color: rgba(255,255,255,0.7); }
.progress-line {
  flex: 1; height: 2px; background: rgba(255,255,255,0.1);
  position: relative; top: -10px;
}
.progress-line.done { background: #6366f1; }

/* -- Feature grid (Welcome step) ------------------------- */
.feat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 24px 0; }
.feat-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 14px; background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px; font-size: 0.85rem; color: rgba(255,255,255,0.75);
}
.feat-item .fi-icon { font-size: 1.3rem; flex-shrink: 0; }
.feat-item .fi-text { line-height: 1.35; }
.feat-item .fi-text strong { display: block; color: white; font-weight: 700; margin-bottom: 2px; }

/* -- Direct line callout --------------------------------- */
.direct-line {
  background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(139,92,246,0.12));
  border: 1px solid rgba(99,102,241,0.25); border-radius: 14px;
  padding: 20px 24px; margin-top: 20px; display: flex; align-items: flex-start; gap: 14px;
}
.direct-line .dl-icon { font-size: 1.6rem; flex-shrink: 0; }
.direct-line .dl-body { font-size: 0.88rem; color: rgba(255,255,255,0.7); line-height: 1.5; }
.direct-line .dl-body strong { color: white; }
.direct-line a { color: #a78bfa; text-decoration: underline; }

/* -- Plan cards ------------------------------------------ */
.plan-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 24px 0; }
@media (max-width: 700px) { .plan-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 440px) { .plan-grid { grid-template-columns: 1fr; } }
.plan-card {
  background: rgba(255,255,255,0.04); border: 2px solid rgba(255,255,255,0.08);
  border-radius: 16px; padding: 24px 18px; text-align: center; cursor: pointer;
  transition: all 0.25s;
}
.plan-card:hover { border-color: rgba(99,102,241,0.4); background: rgba(99,102,241,0.06); }
.plan-card.selected { border-color: #6366f1; background: rgba(99,102,241,0.12); box-shadow: 0 0 20px rgba(99,102,241,0.2); }
.plan-card .plan-name { font-size: 1.1rem; font-weight: 800; margin-bottom: 4px; }
.plan-card .plan-price { font-size: 1.6rem; font-weight: 800; background: linear-gradient(135deg, #6366f1, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.plan-card .plan-period { font-size: 0.72rem; color: rgba(255,255,255,0.35); margin-bottom: 10px; }
.plan-card .plan-feat { font-size: 0.76rem; color: rgba(255,255,255,0.5); line-height: 1.55; text-align: left; padding-left: 0; }
.plan-card .plan-feat li { margin-bottom: 3px; list-style: none; }
.plan-card .plan-feat li::before { content: "\\2713  "; color: #6366f1; font-weight: 700; }

/* -- Tone quick setup ------------------------------------ */
.tone-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
@media (max-width: 500px) { .tone-grid { grid-template-columns: 1fr 1fr; } }
.tone-chip {
  padding: 14px 10px; border-radius: 12px; text-align: center; cursor: pointer;
  border: 2px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04);
  transition: all 0.2s; font-size: 0.88rem; font-weight: 600;
}
.tone-chip:hover { border-color: rgba(99,102,241,0.3); }
.tone-chip.selected { border-color: #6366f1; background: rgba(99,102,241,0.12); }
.tone-chip .tc-icon { font-size: 1.5rem; display: block; margin-bottom: 6px; }

/* -- Platform connect cards ------------------------------ */
.platform-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 20px 0; }
@media (max-width: 500px) { .platform-grid { grid-template-columns: 1fr 1fr; } }
.plat-card {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 18px 12px; border-radius: 14px; text-align: center;
  border: 2px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04);
  transition: all 0.2s; cursor: pointer; text-decoration: none; color: white;
}
.plat-card:hover { border-color: rgba(99,102,241,0.35); background: rgba(99,102,241,0.06); }
.plat-card.connected { border-color: #34d399; background: rgba(52,211,153,0.08); }
.plat-card .plat-icon { font-size: 1.8rem; }
.plat-card .plat-name { font-weight: 700; font-size: 0.88rem; }
.plat-card .plat-status { font-size: 0.72rem; color: rgba(255,255,255,0.35); }
.plat-card.connected .plat-status { color: #34d399; }

/* -- Button row ------------------------------------------ */
.btn-row { display: flex; gap: 12px; margin-top: 28px; flex-wrap: wrap; }
.btn-row .btn { flex: 1; min-width: 140px; text-align: center; }
</style>"""


def _page(body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alita AI &mdash; Setup</title>
{SHARED_CSS}
{extra_head}
</head>
<body>{body}</body>
</html>"""


STEP_LABELS = ["Welcome", "Business", "Knowledge", "Tone", "Platforms", "Plan"]


def _progress_bar(current: int) -> str:
    """Render the top progress indicator. current = 1..6."""
    parts = []
    for i in range(1, TOTAL_STEPS + 1):
        cls = "done" if i < current else ("active" if i == current else "")
        check = "&#10003;" if i < current else str(i)
        parts.append(
            f'<div class="progress-step {cls}">'
            f'<div class="circle">{check}</div>'
            f'<div class="step-label">{STEP_LABELS[i-1]}</div></div>'
        )
        if i < TOTAL_STEPS:
            line_cls = "done" if i < current else ""
            parts.append(f'<div class="progress-line {line_cls}"></div>')
    return '<div class="progress-bar">' + "".join(parts) + '</div>'


# ===========================================================
# Main dispatcher
# ===========================================================

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile: Optional[ClientProfile] = db.query(ClientProfile).filter(
        ClientProfile.user_id == current_user.id
    ).first()

    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    step = getattr(profile, "onboarding_step", None) or 0

    # Already complete
    if step >= 7 or (step == 0 and profile.onboarding_status == OnboardingStatus.complete):
        return RedirectResponse("/dashboard", status_code=303)

    # If KB is building (scraping / researching) redirect to status poller
    if step == 3 and profile.onboarding_status in (
        OnboardingStatus.scraping,
        OnboardingStatus.research_queue,
        OnboardingStatus.research_run,
    ):
        return RedirectResponse("/onboarding/status", status_code=303)

    # Clamp step to valid range
    if step < 1:
        step = 1
        profile.onboarding_step = 1
        db.commit()

    render_map = {
        1: _render_step1_welcome,
        2: _render_step2_business,
        3: _render_step3_knowledge,
        4: _render_step4_tone,
        5: _render_step5_platforms,
        6: _render_step6_plan,
    }
    renderer = render_map.get(step, _render_step1_welcome)
    return renderer(current_user, profile, db)


# ===========================================================
# Step 1: Welcome / Meet Alita
# ===========================================================

def _render_step1_welcome(current_user, profile, db) -> HTMLResponse:
    first_name = (current_user.full_name or "there").split()[0]
  support_email = os.getenv("SUPPORT_EMAIL", "support@alita.ai")
    body = f"""
    <div class="wrap">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Your AI-powered marketing team</p>
      </div>
      {_progress_bar(1)}
      <div class="card">
        <h2>Welcome, {first_name}! &#128075; Meet Alita.</h2>
        <p class="sub">Alita is your full-stack AI marketing team. Here's what she can do for you:</p>

        <div class="feat-grid">
          <div class="feat-item">
            <span class="fi-icon">&#128221;</span>
            <div class="fi-text"><strong>AI Content Creation</strong>Blog posts, social captions, hooks &mdash; all in your brand voice.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#128197;</span>
            <div class="fi-text"><strong>Content Calendar</strong>Auto-schedule across all your platforms at the perfect times.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#127912;</span>
            <div class="fi-text"><strong>AI Image Generation</strong>Professional branded visuals for every post.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#127909;</span>
            <div class="fi-text"><strong>Faceless Videos</strong>Cinematic quality AI videos with voiceover &amp; subtitles.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#128172;</span>
            <div class="fi-text"><strong>AI Engagement</strong>Auto-reply to DMs, comments, and emails in your tone.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#128200;</span>
            <div class="fi-text"><strong>Analytics &amp; Growth</strong>Competitive intelligence, trend analysis, growth strategies.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#128231;</span>
            <div class="fi-text"><strong>Email Marketing</strong>AI-crafted campaigns, drip sequences, newsletter support.</div>
          </div>
          <div class="feat-item">
            <span class="fi-icon">&#129302;</span>
            <div class="fi-text"><strong>Alita Chat Assistant</strong>Ask Alita anything about your marketing &mdash; 24/7.</div>
          </div>
        </div>

        <div class="direct-line">
          <span class="dl-icon">&#128241;</span>
          <div class="dl-body">
            <strong>Direct Line to the Founder</strong><br>
            Have a custom AI project in mind? Need something built specifically for your business?
            Reach out to <strong>Prince</strong> directly at
            <a href="mailto:{support_email}">{support_email}</a>
            &mdash; we love building bespoke AI solutions.
          </div>
        </div>

        <form method="post" action="/onboarding/step">
          <input type="hidden" name="next_step" value="2">
          <div class="btn-row">
            <button type="submit" class="btn btn-full">Let's Get Started &#8594;</button>
          </div>
        </form>
      </div>
    </div>"""
    return HTMLResponse(_page(body))


# ===========================================================
# Step 2: Business Profile
# ===========================================================

def _render_step2_business(current_user, profile, db) -> HTMLResponse:
    bname = profile.business_name or ""
    niche = profile.niche or ""
    desc = profile.description or ""
    website = profile.website_url or ""
    body = f"""
    <div class="wrap">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Tell us about your business</p>
      </div>
      {_progress_bar(2)}
      <div class="card">
        <h2>&#127970; Your Business Profile</h2>
        <p class="sub">Help Alita understand your business so she can create perfectly-targeted content.</p>

        <form method="post" action="/onboarding/save-business">
          <label>Business Name <span style="color:#f87171">*</span></label>
          <input type="text" name="business_name" value="{_esc(bname)}" placeholder="e.g. Cool Cruise Co." required>

          <label>Industry / Niche <span style="color:#f87171">*</span></label>
          <input type="text" name="niche" value="{_esc(niche)}" placeholder="e.g. Travel Agency, SaaS, Life Coach, Restaurant..." required>

          <label>Website URL</label>
          <input type="url" name="website_url" value="{_esc(website)}" placeholder="https://yourwebsite.com">

          <label>Short Description <span style="color:#f87171">*</span></label>
          <textarea name="description" placeholder="What does your business do? Who do you serve?" required>{_esc(desc)}</textarea>

          <div class="btn-row">
            <a href="/onboarding/step-back?to=1" class="btn btn-outline" style="text-align:center">&#8592; Back</a>
            <button type="submit" class="btn" style="flex:2">Continue &#8594;</button>
          </div>
        </form>
      </div>
    </div>"""
    return HTMLResponse(_page(body))


@router.post("/onboarding/save-business")
async def save_business(
    request: Request,
    business_name: str = Form(...),
    niche: str = Form(...),
    website_url: str = Form(""),
    description: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)
    profile.business_name = business_name.strip()
    profile.niche = niche.strip()
    profile.website_url = website_url.strip() or None
    profile.description = description.strip()
    profile.onboarding_step = 3
    db.commit()
    return RedirectResponse("/onboarding", status_code=303)


# ===========================================================
# Step 3: Knowledge Base (website / files / manual)
# ===========================================================

def _render_step3_knowledge(current_user, profile, db) -> HTMLResponse:
    # If KB already done (e.g. came back from later step), show success
    if profile.rag_ready:
        body = f"""
        <div class="wrap">
          <div class="logo"><h1>Alita AI</h1><p>Knowledge base</p></div>
          {_progress_bar(3)}
          <div class="card">
            <div class="status-box success">
              <h3>&#9989; Knowledge Base Ready</h3>
              <p>Your knowledge base was already set up. You can continue or redo it.</p>
            </div>
            <div class="btn-row">
              <a href="/onboarding/step-back?to=2" class="btn btn-outline" style="text-align:center">&#8592; Back</a>
              <a href="/onboarding/reset-kb" class="btn btn-outline" style="text-align:center">Redo KB</a>
              <form method="post" action="/onboarding/step" style="flex:2;display:contents">
                <input type="hidden" name="next_step" value="4">
                <button type="submit" class="btn" style="flex:2;width:100%">Continue &#8594;</button>
              </form>
            </div>
          </div>
        </div>"""
        return HTMLResponse(_page(body))

    if profile.onboarding_status == OnboardingStatus.failed:
        error_msg = profile.onboarding_error or "An error occurred during setup."
        return _render_retry_step3(profile, error_msg)

    body = f"""
    <div class="wrap">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Build your knowledge base</p>
      </div>
      {_progress_bar(3)}
      <div class="card">
        <h2>&#128218; Teach Alita About Your Business</h2>
        <p class="sub">Choose how you'd like to build your knowledge base. This is how Alita learns to create content in your voice.</p>

        <div class="tabs">
          <div class="tab active" id="tab-website" onclick="showTab('website')">
            <div class="icon">&#127760;</div>
            <div class="label">Website</div>
            <div class="desc">Fastest &mdash; auto-scan</div>
          </div>
          <div class="tab" id="tab-files" onclick="showTab('files')">
            <div class="icon">&#128194;</div>
            <div class="label">Upload Files</div>
            <div class="desc">PDF, DOCX, TXT, MD</div>
          </div>
          <div class="tab" id="tab-manual" onclick="showTab('manual')">
            <div class="icon">&#9999;&#65039;</div>
            <div class="label">Manual</div>
            <div class="desc">Fill a short form</div>
          </div>
        </div>

        <!-- PATH A: Website URL -->
        <div id="section-website">
          <form method="post" action="/onboarding/website">
            <label>Your Business Website URL</label>
            <input type="url" name="website_url" placeholder="https://yourwebsite.com" value="{_esc(profile.website_url or '')}" required>
            <p class="hint">We'll scan your site and automatically build your knowledge base. Takes about 60 seconds.</p>
            <button type="submit" class="btn btn-full">Scan My Website &#8594;</button>
          </form>
        </div>

        <!-- PATH C: File upload -->
        <div id="section-files" style="display:none">
          <form method="post" action="/onboarding/files" enctype="multipart/form-data" id="file-form">
            <div class="upload-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
              <div class="uz-icon">&#128194;</div>
              <div class="uz-label">Drop files here or click to browse</div>
              <div class="uz-sub">PDF &middot; DOCX &middot; TXT &middot; Markdown (.md)</div>
            </div>
            <input type="file" id="file-input" name="files" multiple
                   accept=".pdf,.docx,.txt,.md,.markdown">
            <div class="file-list" id="file-list"></div>
            <p class="hint" style="margin-top:16px">Files are stored securely and used only to train your AI assistant.</p>
            <button type="submit" class="btn btn-full" id="upload-btn" style="opacity:.4;cursor:not-allowed" disabled>
              Upload &amp; Build Knowledge Base &#8594;
            </button>
          </form>
        </div>

        <!-- PATH B: Manual form -->
        <div id="section-manual" style="display:none">
          <form method="post" action="/onboarding/manual">
            <label>What does your business do? <span style="color:#f87171">*</span></label>
            <textarea name="description" placeholder="We provide luxury cruise packages to the Caribbean and Mediterranean for couples and families..." required>{_esc(profile.description or '')}</textarea>

            <label>Your Industry / Niche <span style="color:#f87171">*</span></label>
            <input type="text" name="niche" placeholder="e.g. Travel Agency, Life Coach, SaaS, Restaurant..." value="{_esc(profile.niche or '')}" required>

            <label>Main Services or Products <span style="color:#f87171">*</span></label>
            <textarea name="services" placeholder="List your main offerings, one per line or separated by commas...">{_esc(profile.services_products or '')}</textarea>

            <label>Who are your ideal customers?</label>
            <textarea name="target_audience" placeholder="e.g. Couples aged 35-60 interested in luxury travel...">{_esc(profile.target_audience or '')}</textarea>

            <label>Your Location (City, State)</label>
            <input type="text" name="location" placeholder="e.g. Fort Lauderdale, FL" value="{_esc(profile.location or '')}">

            <label>Top competitors? (optional)</label>
            <input type="text" name="competitors" placeholder="e.g. Royal Caribbean, Carnival Cruise..." value="{_esc(profile.competitors or '')}">

            <label>What makes you different?</label>
            <textarea name="unique_value_prop" placeholder="Your main selling point or competitive advantage?">{_esc(profile.unique_value_prop or '')}</textarea>

            <hr class="divider">
            <p style="font-size:0.82rem; color:rgba(255,255,255,0.4);">
              &#9203; After submitting, Alita will run an AI research session to build your knowledge base. Takes 1&ndash;2 minutes.
            </p>
            <button type="submit" class="btn btn-full">Submit &amp; Research &#8594;</button>
          </form>
        </div>

        <div style="margin-top:16px; text-align:center;">
          <a href="/onboarding/step-back?to=2" style="color:rgba(255,255,255,0.35); font-size:0.82rem; text-decoration:none;">&#8592; Back to Business Profile</a>
        </div>
      </div>
    </div>

    <script>
    function showTab(tab) {{
      ['website','files','manual'].forEach(t => {{
        document.getElementById('section-' + t).style.display = t === tab ? 'block' : 'none';
        document.getElementById('tab-' + t).className = 'tab' + (t === tab ? ' active' : '');
      }});
    }}
    const dropZone  = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileList  = document.getElementById('file-list');
    const uploadBtn = document.getElementById('upload-btn');
    function fmtSize(b) {{
      if (b < 1024) return b + ' B';
      if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
      return (b/1048576).toFixed(1) + ' MB';
    }}
    const EXT_ICON = {{pdf:'&#128196;',docx:'&#128221;',doc:'&#128221;',txt:'&#128203;',md:'&#128209;',markdown:'&#128209;'}};
    function renderFiles(files) {{
      fileList.innerHTML = '';
      Array.from(files).forEach(f => {{
        const ext = f.name.split('.').pop().toLowerCase();
        const icon = EXT_ICON[ext] || '&#128206;';
        fileList.innerHTML += '<div class="file-item"><span>'+icon+'</span><span class="f-name">'+f.name+'</span><span class="f-size">'+fmtSize(f.size)+'</span></div>';
      }});
      const ok = files.length > 0;
      uploadBtn.disabled = !ok;
      uploadBtn.style.opacity = ok ? '1' : '.4';
      uploadBtn.style.cursor  = ok ? 'pointer' : 'not-allowed';
    }}
    fileInput.addEventListener('change', () => renderFiles(fileInput.files));
    dropZone.addEventListener('dragover',  e => {{ e.preventDefault(); dropZone.classList.add('dragover'); }});
    dropZone.addEventListener('dragleave', ()  => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', e => {{
      e.preventDefault();
      dropZone.classList.remove('dragover');
      const dt = new DataTransfer();
      Array.from(e.dataTransfer.files).forEach(f => dt.items.add(f));
      fileInput.files = dt.files;
      renderFiles(fileInput.files);
    }});
    </script>"""
    return HTMLResponse(_page(body))


def _render_retry_step3(profile, error_msg) -> HTMLResponse:
    body = f"""
    <div class="wrap">
      <div class="logo"><h1>Alita AI</h1></div>
      {_progress_bar(3)}
      <div class="card">
        <div class="status-box error">
          <h3>&#10060; Setup failed</h3>
          <p>{error_msg}</p>
        </div>
        <a href="/onboarding/reset-kb" class="btn btn-full" style="margin-top:24px; display:block; text-align:center;">Try Again</a>
      </div>
    </div>"""
    return HTMLResponse(_page(body))


# ===========================================================
# Step 4: Tone & Style (SKIPPABLE)
# ===========================================================

TONE_PRESETS = [
    ("professional", "Professional", "&#128188;"),
    ("casual", "Casual & Friendly", "&#128522;"),
    ("witty", "Witty & Bold", "&#128526;"),
    ("inspirational", "Inspirational", "&#10024;"),
    ("educational", "Educational", "&#128218;"),
    ("luxury", "Luxury & Premium", "&#128142;"),
]

def _render_step4_tone(current_user, profile, db) -> HTMLResponse:
    already_done = profile.tone_configured
    if already_done:
        msg = '<div class="status-box success" style="margin-bottom:20px"><h3>&#9989; Tone already configured</h3><p>You can update it later in Settings.</p></div>'
    else:
        msg = ""

    chips_html = ""
    for key, label, icon in TONE_PRESETS:
        chips_html += (
            f'<div class="tone-chip" data-tone="{key}" onclick="selectTone(this, \'{key}\')">'
            f'<span class="tc-icon">{icon}</span>{label}</div>'
        )

    body = f"""
    <div class="wrap">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Set your brand voice</p>
      </div>
      {_progress_bar(4)}
      <div class="card">
        <h2>&#127908; Tone &amp; Style</h2>
        <p class="sub">Choose a starting tone preset. You can fine-tune this later in Settings.</p>
        {msg}

        <form method="post" action="/onboarding/save-tone" id="tone-form">
          <input type="hidden" name="tone_preset" id="tone-preset" value="">
          <div class="tone-grid">{chips_html}</div>
          <div class="btn-row">
            <a href="/onboarding/step-back?to=3" class="btn btn-outline" style="text-align:center">&#8592; Back</a>
            <a href="/onboarding/skip-step?to=5" class="btn btn-outline" style="text-align:center">Skip for Now</a>
            <button type="submit" class="btn" style="flex:2" id="tone-submit" disabled>Save &amp; Continue &#8594;</button>
          </div>
        </form>
      </div>
    </div>
    <script>
    let selectedTone = '';
    function selectTone(el, key) {{
      document.querySelectorAll('.tone-chip').forEach(c => c.classList.remove('selected'));
      el.classList.add('selected');
      selectedTone = key;
      document.getElementById('tone-preset').value = key;
      document.getElementById('tone-submit').disabled = false;
    }}
    </script>"""
    return HTMLResponse(_page(body))


@router.post("/onboarding/save-tone")
async def save_tone(
    request: Request,
    tone_preset: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    if tone_preset:
        prefs = {"preset": tone_preset, "configured_at": datetime.utcnow().isoformat()}
        profile.tone_preferences_json = json.dumps(prefs)
        profile.tone_configured = True
    profile.onboarding_step = 5
    db.commit()
    return RedirectResponse("/onboarding", status_code=303)


# ===========================================================
# Step 5: Connect Platforms (SKIPPABLE)
# ===========================================================

PLATFORMS_INFO = [
    ("instagram", "Instagram", "&#128247;", "/meta/oauth/start"),
    ("facebook", "Facebook", "&#128218;", "/meta/oauth/start"),
    ("twitter", "Twitter / X", "&#128038;", "/connect/twitter/start"),
    ("tiktok", "TikTok", "&#127909;", "/connect/tiktok/start"),
    ("linkedin", "LinkedIn", "&#128188;", "/connect/linkedin/start"),
    ("threads", "Threads", "&#128172;", "/connect/threads/start"),
    ("youtube", "YouTube", "&#9654;&#65039;", "/connect/youtube/start"),
]


def _render_step5_platforms(current_user, profile, db) -> HTMLResponse:
    # Check which platforms are connected
    connected = set()
    try:
        from api.client_connections_routes import load_connections, _has_meta_token_for_client
        all_conns = load_connections()
        client_conns = all_conns.get(profile.client_id, {})
        for plat_key in client_conns:
            connected.add(plat_key.lower())
        if _has_meta_token_for_client(profile.client_id):
            connected.add("instagram")
            connected.add("facebook")
    except Exception:
        pass

    cards_html = ""
    for key, name, icon, url in PLATFORMS_INFO:
        is_connected = key in connected
        cls = "plat-card connected" if is_connected else "plat-card"
        status = "&#9989; Connected" if is_connected else "Click to connect"
        href = "javascript:void(0)" if is_connected else url
        cards_html += (
            f'<a href="{href}" class="{cls}"><span class="plat-icon">{icon}</span>'
            f'<span class="plat-name">{name}</span>'
            f'<span class="plat-status">{status}</span></a>'
        )

    count_msg = (
        f"{len(connected)} platform{'s' if len(connected) != 1 else ''} connected"
        if connected else "No platforms connected yet"
    )

    body = f"""
    <div class="wrap">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Connect your social accounts</p>
      </div>
      {_progress_bar(5)}
      <div class="card">
        <h2>&#128279; Connect Your Platforms</h2>
        <p class="sub">Link your social accounts so Alita can post, engage, and analyze on your behalf. <strong>{count_msg}.</strong></p>

        <div class="platform-grid">{cards_html}</div>

        <p class="hint" style="margin-top:16px">You can always add more platforms later from your Settings page.</p>

        <div class="btn-row">
          <a href="/onboarding/step-back?to=4" class="btn btn-outline" style="text-align:center">&#8592; Back</a>
          <a href="/onboarding/skip-step?to=6" class="btn btn-outline" style="text-align:center">Skip for Now</a>
          <form method="post" action="/onboarding/step" style="flex:2;display:contents">
            <input type="hidden" name="next_step" value="6">
            <button type="submit" class="btn" style="flex:2;width:100%">Continue &#8594;</button>
          </form>
        </div>
      </div>
    </div>"""
    return HTMLResponse(_page(body))


# ===========================================================
# Step 6: Choose a Plan (REQUIRED)
# ===========================================================

PLAN_CARDS_DATA = [
    ("free", "Free", "$0", "/mo", [
        "5 AI posts/mo", "3 AI images/mo", "20 engagement replies",
        "Instagram + Facebook", "Basic analytics",
    ]),
    ("starter", "Starter", "$97", "/mo", [
        "30 AI posts/mo", "15 AI images/mo", "1 faceless video",
        "150 engagement replies", "4 social accounts", "2 email campaigns",
    ]),
    ("growth", "Growth", "$197", "/mo", [
        "90 AI posts/mo", "40 AI images/mo", "5 faceless videos",
        "500 engagement replies", "6 social accounts", "8 email campaigns",
        "Competitive intelligence",
    ]),
    ("pro", "Pro", "$397", "/mo", [
        "Unlimited posts", "100 AI images/mo", "15 faceless videos",
        "Unlimited replies", "Unlimited accounts", "Unlimited campaigns",
        "Full intelligence suite", "Priority support",
    ]),
]


def _render_step6_plan(current_user, profile, db) -> HTMLResponse:
    cards_html = ""
    for tier, name, price, period, feats in PLAN_CARDS_DATA:
        feats_li = "".join(f"<li>{f}</li>" for f in feats)
        cards_html += (
            f'<div class="plan-card" data-tier="{tier}" onclick="selectPlan(this, \'{tier}\')">'
            f'<div class="plan-name">{name}</div>'
            f'<div class="plan-price">{price}</div>'
            f'<div class="plan-period">{period}</div>'
            f'<ul class="plan-feat">{feats_li}</ul>'
            f'</div>'
        )

    body = f"""
    <div class="wrap">
      <div class="logo">
        <h1>Alita AI</h1>
        <p>Choose your plan</p>
      </div>
      {_progress_bar(6)}
      <div class="card">
        <h2>&#128176; Choose Your Plan</h2>
        <p class="sub">Pick the plan that fits your needs. You can upgrade or downgrade anytime.</p>

        <div class="plan-grid">{cards_html}</div>

        <form method="post" action="/onboarding/save-plan" id="plan-form">
          <input type="hidden" name="plan_tier" id="plan-tier" value="">
          <div class="btn-row">
            <a href="/onboarding/step-back?to=5" class="btn btn-outline" style="text-align:center">&#8592; Back</a>
            <button type="submit" class="btn" style="flex:2" id="plan-submit" disabled>
              Complete Setup &#8594;
            </button>
          </div>
        </form>
        <p class="hint" style="margin-top:12px; text-align:center">
          Paid plans use Stripe for secure billing. You can start with Free and upgrade any time.
        </p>
      </div>
    </div>
    <script>
    let selectedPlan = '';
    function selectPlan(el, tier) {{
      document.querySelectorAll('.plan-card').forEach(c => c.classList.remove('selected'));
      el.classList.add('selected');
      selectedPlan = tier;
      document.getElementById('plan-tier').value = tier;
      document.getElementById('plan-submit').disabled = false;
    }}
    </script>"""
    return HTMLResponse(_page(body))


@router.post("/onboarding/save-plan")
async def save_plan(
    request: Request,
    plan_tier: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    valid_tiers = {"free", "starter", "growth", "pro"}
    tier = plan_tier.strip().lower()
    if tier not in valid_tiers:
        tier = "free"

    if tier == "free":
        # Free plan -- complete onboarding immediately
        profile.plan_tier = "free"
        profile.plan_status = "active"
        profile.onboarding_step = 7
        profile.onboarding_status = OnboardingStatus.complete
        db.commit()
        _auto_register_scheduler(profile.client_id)
        return RedirectResponse("/dashboard", status_code=303)
    else:
        # Paid plan -- create Stripe checkout session directly and redirect
        from utils.plan_limits import STRIPE_PRICE_IDS

        STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
        APP_BASE_URL = os.getenv("APP_BASE_URL", "https://web-production-00e4.up.railway.app")

        if not STRIPE_SECRET_KEY:
            # Stripe not configured — fall back to free
            profile.plan_tier = "free"
            profile.plan_status = "active"
            profile.onboarding_step = 7
            profile.onboarding_status = OnboardingStatus.complete
            db.commit()
            _auto_register_scheduler(profile.client_id)
            return RedirectResponse("/dashboard", status_code=303)

        price_id = STRIPE_PRICE_IDS.get((tier, "monthly"), "")
        if not price_id:
            profile.plan_tier = "free"
            profile.plan_status = "active"
            profile.onboarding_step = 7
            profile.onboarding_status = OnboardingStatus.complete
            db.commit()
            _auto_register_scheduler(profile.client_id)
            return RedirectResponse("/dashboard", status_code=303)

        try:
            import stripe as _stripe_mod
            _stripe_mod.api_key = STRIPE_SECRET_KEY

            # Get or create Stripe customer
            customer_id = profile.stripe_customer_id
            if not customer_id:
                customer = _stripe_mod.Customer.create(
                    email=current_user.email,
                    name=current_user.full_name,
                    metadata={"client_id": profile.client_id, "user_id": current_user.id},
                )
                customer_id = customer["id"]
                profile.stripe_customer_id = customer_id
                db.add(profile)
                db.commit()

            session = _stripe_mod.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{APP_BASE_URL}/onboarding/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{APP_BASE_URL}/onboarding",
                subscription_data={
                    "metadata": {
                        "client_id": profile.client_id,
                        "tier": tier,
                        "period": "monthly",
                        "onboarding": "1",
                    }
                },
                metadata={
                    "client_id": profile.client_id,
                    "tier": tier,
                    "period": "monthly",
                    "onboarding": "1",
                },
                allow_promotion_codes=True,
            )

            # Store intended tier but don't complete yet — webhook will confirm
            profile.plan_tier = tier
            db.commit()
            return RedirectResponse(session["url"], status_code=303)

        except Exception as e:
            print(f"Stripe checkout error during onboarding: {e}")
            # Fall back to free plan on error
            profile.plan_tier = "free"
            profile.plan_status = "active"
            profile.onboarding_step = 7
            profile.onboarding_status = OnboardingStatus.complete
            db.commit()
            _auto_register_scheduler(profile.client_id)
            return RedirectResponse("/dashboard", status_code=303)


@router.get("/onboarding/payment-success")
async def payment_success(
    request: Request,
    session_id: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """
    Stripe redirects here after successful checkout during onboarding.
    Mark onboarding as complete. The webhook will separately confirm
    plan_status=active, but we complete the wizard immediately so the
    user isn't stuck.
    """
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if profile:
        profile.plan_status = "active"
        profile.onboarding_step = 7
        profile.onboarding_status = OnboardingStatus.complete
        db.commit()
        _auto_register_scheduler(profile.client_id)
    return RedirectResponse("/dashboard?welcome=1", status_code=303)


# ===========================================================
# Generic step navigation
# ===========================================================

@router.post("/onboarding/step")
async def advance_step(
    request: Request,
    next_step: int = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Generic step advancement (for steps that don't need form data)."""
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)
    if 1 <= next_step <= 7:
        profile.onboarding_step = next_step
        db.commit()
    return RedirectResponse("/onboarding", status_code=303)


@router.get("/onboarding/step-back")
async def step_back(
    request: Request,
    to: int = 1,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Go back to a previous step."""
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if profile and 1 <= to <= 6:
        profile.onboarding_step = to
        db.commit()
    return RedirectResponse("/onboarding", status_code=303)


@router.get("/onboarding/skip-step")
async def skip_step(
    request: Request,
    to: int = 5,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Skip a skippable step (tone=4, platforms=5)."""
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if profile and 1 <= to <= 7:
        profile.onboarding_step = to
        db.commit()
    return RedirectResponse("/onboarding", status_code=303)


# ===========================================================
# KB Reset (stays on step 3)
# ===========================================================

@router.get("/onboarding/reset-kb")
async def reset_kb(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    """Reset KB status so user can retry step 3."""
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if profile:
        profile.onboarding_status = OnboardingStatus.pending
        profile.onboarding_error = None
        profile.rag_ready = False
        profile.onboarding_step = 3
        db.commit()
    return RedirectResponse("/onboarding", status_code=303)


# ===========================================================
# Path A: Website URL -> scrape -> RAG
# ===========================================================

@router.post("/onboarding/website")
async def onboarding_website_submit(
    background_tasks: BackgroundTasks,
    request: Request,
    website_url: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    profile.website_url = website_url.strip()
    profile.onboarding_method = OnboardingMethod.website
    profile.onboarding_status = OnboardingStatus.scraping
    db.commit()

    background_tasks.add_task(
        _run_website_scrape,
        profile_id=profile.id,
        client_id=profile.client_id,
        business_name=profile.business_name,
        url=website_url.strip(),
    )
    return RedirectResponse("/onboarding/status", status_code=303)


async def _run_website_scrape(profile_id: str, client_id: str, business_name: str, url: str):
    """Background task: scrape website -> ingest RAG -> advance to step 4."""
    from database.db import SessionLocal
    from utils.website_scraper import scrape_and_ingest

    db = SessionLocal()
    try:
        result = await scrape_and_ingest(
            url=url, client_id=client_id,
            business_name=business_name, db_profile_id=profile_id,
        )
        profile = db.query(ClientProfile).filter(ClientProfile.id == profile_id).first()
        if not profile:
            return

        if result["success"]:
            facts = result.get("facts", {})
            profile.niche            = facts.get("niche") or profile.niche
            profile.description      = facts.get("description") or profile.description
            profile.services_products = facts.get("services") or profile.services_products
            profile.target_audience  = facts.get("target_audience") or profile.target_audience
            profile.location         = facts.get("location") or profile.location
            profile.unique_value_prop = facts.get("unique_value_prop") or profile.unique_value_prop
            profile.onboarding_status = OnboardingStatus.complete
            profile.rag_ready         = True
            profile.onboarding_step   = 4  # Advance to Tone step
        else:
            profile.onboarding_status = OnboardingStatus.failed
            profile.onboarding_error  = result.get("error", "Unknown scrape error")
        db.commit()
    except Exception as e:
        try:
            profile = db.query(ClientProfile).filter(ClientProfile.id == profile_id).first()
            if profile:
                profile.onboarding_status = OnboardingStatus.failed
                profile.onboarding_error  = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ===========================================================
# Path C: File upload -> extract -> ingest RAG
# ===========================================================

@router.post("/onboarding/files")
async def onboarding_files_submit(
    background_tasks: BackgroundTasks,
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    upload_dir = Path("storage") / "uploaded_docs" / profile.client_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[str] = []
    allowed_ext = {".pdf", ".docx", ".txt", ".md", ".markdown"}
    for uf in files:
        ext = Path(uf.filename).suffix.lower()
        if ext not in allowed_ext:
            continue
        dest = upload_dir / uf.filename
        contents = await uf.read()
        dest.write_bytes(contents)
        saved_paths.append(str(dest))

    if not saved_paths:
        return RedirectResponse("/onboarding?error=no_valid_files", status_code=303)

    profile.onboarding_method = OnboardingMethod.files
    profile.onboarding_status = OnboardingStatus.scraping
    db.commit()

    background_tasks.add_task(
        _run_file_ingest,
        profile_id=profile.id,
        client_id=profile.client_id,
        file_paths=saved_paths,
    )
    return RedirectResponse("/onboarding/status", status_code=303)


async def _run_file_ingest(profile_id: str, client_id: str, file_paths: List[str]):
    """Background task: extract text from uploaded files -> ingest into RAG."""
    from database.db import SessionLocal
    from agents.rag_system import RAGSystem
    from utils.file_reader import extract_text_from_file

    _CHUNK = 4_000

    db = SessionLocal()
    try:
        rag = RAGSystem()
        ingested = 0
        errors: List[str] = []

        for fpath in file_paths:
            fname = Path(fpath).name
            try:
                text = extract_text_from_file(fpath)
                if not text or not text.strip():
                    errors.append(f"{fname}: no extractable text")
                    continue
                for i in range(0, len(text), _CHUNK):
                    chunk = text[i:i + _CHUNK].strip()
                    if not chunk:
                        continue
                    rag.add_knowledge(
                        text=chunk, client_id=client_id,
                        source=fname, category="uploaded_document",
                        tags=["file_upload", Path(fpath).suffix.lstrip(".")],
                    )
                ingested += 1
            except Exception as fe:
                errors.append(f"{fname}: {fe}")

        profile = db.query(ClientProfile).filter(ClientProfile.id == profile_id).first()
        if not profile:
            return

        if ingested > 0:
            profile.onboarding_status = OnboardingStatus.complete
            profile.rag_ready         = True
            profile.onboarding_step   = 4  # Advance to Tone step
            if errors:
                profile.onboarding_error = f"Partial: {len(errors)} file(s) failed - {'; '.join(errors[:3])}"
        else:
            profile.onboarding_status = OnboardingStatus.failed
            profile.onboarding_error  = f"Could not extract text from any file. {'; '.join(errors[:3])}"
        db.commit()
    except Exception as e:
        try:
            profile = db.query(ClientProfile).filter(ClientProfile.id == profile_id).first()
            if profile:
                profile.onboarding_status = OnboardingStatus.failed
                profile.onboarding_error  = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ===========================================================
# Path B: Manual form -> deep research queue
# ===========================================================

@router.post("/onboarding/manual")
async def onboarding_manual_submit(
    request: Request,
    description: str = Form(...),
    niche: str = Form(...),
    services: str = Form(""),
    target_audience: str = Form(""),
    location: str = Form(""),
    competitors: str = Form(""),
    unique_value_prop: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    profile.description        = description.strip()
    profile.niche              = niche.strip()
    profile.services_products  = services.strip()
    profile.target_audience    = target_audience.strip()
    profile.location           = location.strip()
    profile.competitors        = competitors.strip()
    profile.unique_value_prop  = unique_value_prop.strip()
    profile.onboarding_method  = OnboardingMethod.manual
    db.commit()

    research_query = _build_research_query(
        business_name=profile.business_name,
        niche=niche, description=description,
        services=services, target_audience=target_audience,
        location=location, competitors=competitors,
    )

    from jose import jwt as _jwt
    _secret = os.getenv("TOKEN_ENCRYPTION_KEY", "fallback-secret")
    _token = _jwt.encode(
        {"query": research_query, "profile_id": profile.id},
        _secret, algorithm="HS256",
    )
    response = RedirectResponse("/onboarding/review-query", status_code=303)
    response.set_cookie("_rq", _token, httponly=True, max_age=3600, samesite="lax")
    return response


# --- Review query page ------------------------------------

@router.get("/onboarding/review-query", response_class=HTMLResponse)
async def onboarding_review_query(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    from jose import jwt as _jwt, JWTError
    _secret = os.getenv("TOKEN_ENCRYPTION_KEY", "fallback-secret")
    cookie = request.cookies.get("_rq", "")
    research_query = ""
    try:
        payload = _jwt.decode(cookie, _secret, algorithms=["HS256"])
        research_query = payload.get("query", "")
    except (JWTError, Exception):
        research_query = _build_research_query(
            business_name=profile.business_name,
            niche=profile.niche or "", description=profile.description or "",
            services=profile.services_products or "",
            target_audience=profile.target_audience or "",
            location=profile.location or "",
            competitors=profile.competitors or "",
        )

    body = f"""
    <div class="wrap">
      <div class="logo"><h1>Alita AI</h1><p>Review research plan</p></div>
      {_progress_bar(3)}
      <div class="card">
        <h2>Review your research plan</h2>
        <p class="sub">Here's what Alita will research for <strong>{_esc(profile.business_name)}</strong>. You can edit this before we start.</p>

        <form method="post" action="/onboarding/approve-research">
          <label>Research Query</label>
          <textarea name="research_query" style="min-height:200px; line-height:1.6" required>{_esc(research_query)}</textarea>
          <p class="hint">Tip: Add specific competitors, topics, or questions you want answered.</p>

          <div class="btn-row">
            <a href="/onboarding/reset-kb" class="btn btn-outline" style="text-align:center">Go Back</a>
            <button type="submit" class="btn" style="flex:2">Start Research &#8594;</button>
          </div>
        </form>
      </div>
    </div>"""
    return HTMLResponse(_page(body))


# --- Approve & run research -------------------------------

@router.post("/onboarding/approve-research")
async def onboarding_approve_research(
    background_tasks: BackgroundTasks,
    request: Request,
    research_query: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    profile.onboarding_status = OnboardingStatus.research_run
    db.commit()

    raw_details = json.dumps({
        "business_name": profile.business_name,
        "niche": profile.niche or "",
        "description": profile.description or "",
        "services": profile.services_products or "",
        "target_audience": profile.target_audience or "",
        "location": profile.location or "",
        "competitors": profile.competitors or "",
        "unique_value_prop": profile.unique_value_prop or "",
    }, ensure_ascii=False)

    dr = DeepResearchRequest(
        id=str(uuid.uuid4()),
        client_profile_id=profile.id,
        research_query=research_query.strip(),
        raw_business_details=raw_details,
        status=DeepResearchStatus.approved,
    )
    db.add(dr)
    db.commit()

    background_tasks.add_task(
        _run_client_research,
        request_id=dr.id,
        client_profile_id=profile.id,
        client_id=profile.client_id,
    )

    response = RedirectResponse("/onboarding/status", status_code=303)
    response.delete_cookie("_rq")
    return response


# --- Background: Gemini deep research --------------------

_RAG_CHUNK = 4_000

def _run_client_research(request_id: str, client_profile_id: str, client_id: str):
    from utils.agent_executor import run_agent_in_background
    run_agent_in_background(_run_client_research_async(request_id, client_profile_id, client_id))


async def _run_client_research_async(request_id: str, client_profile_id: str, client_id: str):
    from database.db import SessionLocal
    from agents.rag_system import RAGSystem

    db = SessionLocal()
    try:
        dr      = db.query(DeepResearchRequest).filter(DeepResearchRequest.id == request_id).first()
        profile = db.query(ClientProfile).filter(ClientProfile.id == client_profile_id).first()
        if not dr or not profile:
            return

        dr.status = DeepResearchStatus.running
        db.commit()

        research_text = await _execute_gemini_research(dr.research_query, profile.business_name)

        if research_text:
            rag = RAGSystem()
            for i in range(0, len(research_text), _RAG_CHUNK):
                chunk = research_text[i:i + _RAG_CHUNK].strip()
                if chunk:
                    rag.add_knowledge(
                        text=chunk, client_id=client_id,
                        source="deep_research", category="market_research",
                        tags=["deep_research", "onboarding", "market_analysis"],
                    )
            try:
                details = json.loads(dr.raw_business_details)
                details_text = "\n".join(f"{k.replace('_',' ').title()}: {v}" for k, v in details.items() if v)
                rag.add_knowledge(
                    text=f"Business Profile:\n{details_text}",
                    client_id=client_id,
                    source="manual_onboarding", category="business_profile",
                    tags=["profile", "onboarding"],
                )
            except Exception:
                pass

            dr.research_results = research_text[:10000]
            dr.status           = DeepResearchStatus.complete
            dr.ingested_at      = datetime.utcnow()
            profile.onboarding_status = OnboardingStatus.complete
            profile.rag_ready         = True
            profile.onboarding_step   = 4  # Advance to Tone step
        else:
            dr.status = DeepResearchStatus.failed
            profile.onboarding_status = OnboardingStatus.failed
            profile.onboarding_error  = "Deep research returned no content. Please try again."
        db.commit()

    except Exception as e:
        try:
            dr      = db.query(DeepResearchRequest).filter(DeepResearchRequest.id == request_id).first()
            profile = db.query(ClientProfile).filter(ClientProfile.id == client_profile_id).first()
            if dr:
                dr.status = DeepResearchStatus.failed
            if profile:
                profile.onboarding_status = OnboardingStatus.failed
                profile.onboarding_error  = str(e)[:500]
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def _execute_gemini_research(query: str, business_name: str) -> Optional[str]:
    """Run deep research using Gemini 2.5 Pro with Google Search grounding.
    Falls back to Claude Sonnet if Gemini is unavailable."""

    gemini_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-2.5-pro")
    if gemini_key:
        try:
            import httpx
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": query}], "role": "user"}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 65536},
                "tools": [{"googleSearch": {}}],
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    text = " ".join(p.get("text", "") for p in parts if "text" in p)
                    if text.strip():
                        return f"Market Research for {business_name}\n\nQuery: {query}\n\n{text}"
                else:
                    print(f"[Research] Gemini {model} returned {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            print(f"[Research] Gemini error: {e}")

    try:
        client  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        sonnet  = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929")
        prompt  = f"""You are conducting market research for a client's AI marketing system.

Business: {business_name}
Research Query: {query}

Please provide comprehensive research covering:
1. Industry overview and key trends (2024-2026)
2. Target customer pain points and desires
3. Effective content marketing strategies for this niche
4. Key topics and themes for social media content
5. Competitor positioning and market gaps
6. Best platforms and content formats for this industry
7. Common objections and how to address them
8. Seasonal trends or events relevant to this business

Be thorough and specific. This will be used to train an AI marketing system."""
        msg = client.messages.create(
            model=sonnet, max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        print(f"[Research] Claude fallback error: {e}")
        return None


def _build_research_query(business_name, niche, description, services, target_audience, location, competitors) -> str:
    parts = [f"Research the market landscape for {business_name}, a {niche} business."]
    if description:
        parts.append(f"Business description: {description}")
    if services:
        parts.append(f"Their services/products: {services}")
    if target_audience:
        parts.append(f"Target audience: {target_audience}")
    if location:
        parts.append(f"Based in: {location}")
    if competitors:
        parts.append(f"Main competitors to research: {competitors}")
    parts.append(
        "Please research: industry trends, common customer pain points, "
        "effective marketing strategies for this niche, competitor positioning, "
        "and key topics this business should create content about."
    )
    return " ".join(parts)


# ===========================================================
# Status page (KB processing spinner -- step 3 only)
# ===========================================================

@router.get("/onboarding/status", response_class=HTMLResponse)
async def onboarding_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse("/account/login", status_code=303)

    status = profile.onboarding_status
    step = getattr(profile, "onboarding_step", 3) or 3

    # If KB finished while we were polling, go to next step
    if profile.rag_ready and step <= 3:
        if profile.onboarding_step and profile.onboarding_step >= 4:
            return RedirectResponse("/onboarding", status_code=303)
    if status == OnboardingStatus.complete and step >= 4:
        return RedirectResponse("/onboarding", status_code=303)

    if status == OnboardingStatus.scraping:
        refresh = '<meta http-equiv="refresh" content="5">'
        is_file = profile.onboarding_method == OnboardingMethod.files
        h3_msg   = "Processing your files..." if is_file else "Scanning your website..."
        sub_msg  = (
            "Extracting and indexing your documents. Almost done!"
            if is_file else
            "Reading your website and building your knowledge base. About 60 seconds."
        )
        steps = (
            ["Reading uploaded files", "Extracting text content", "Normalising &amp; chunking", "Building knowledge base"]
            if is_file else
            ["Fetching website pages", "Extracting business content", "Summarising with AI", "Building knowledge base"]
        )
        steps_html = "".join(f'<li><span class="dot"></span>{s}</li>' for s in steps)
        body = f"""
        <div class="wrap">
          <div class="logo"><h1>Alita AI</h1></div>
          {_progress_bar(3)}
          <div class="card">
            <div class="status-box processing">
              <div class="spinner" style="margin:0 auto 16px"></div>
              <h3>{h3_msg}</h3>
              <p>{sub_msg}</p>
            </div>
            <ul class="step-list" style="margin-top:24px">{steps_html}</ul>
          </div>
        </div>"""
        return HTMLResponse(_page(body, extra_head=refresh))

    elif status in (OnboardingStatus.research_queue, OnboardingStatus.research_run):
        label = "Researching your industry..." if status == OnboardingStatus.research_run else "Awaiting review"
        detail = (
            "Alita is analyzing your market, competitors, and industry trends. 1&ndash;2 minutes."
            if status == OnboardingStatus.research_run
            else "Your research is queued and will start shortly."
        )
        badge_class = "badge-approved" if status == OnboardingStatus.research_run else "badge-pending"
        refresh = '<meta http-equiv="refresh" content="8">'
        steps_html = ""
        if status == OnboardingStatus.research_run:
            steps = ["Analyzing business details", "Searching industry trends", "Building knowledge base", "Finalizing workspace"]
            steps_html = (
                '<ul class="step-list" style="margin-top:24px">'
                + "".join(f'<li><span class="dot"></span>{s}</li>' for s in steps)
                + '</ul>'
            )
        body = f"""
        <div class="wrap">
          <div class="logo"><h1>Alita AI</h1></div>
          {_progress_bar(3)}
          <div class="card">
            <div class="status-box processing">
              <div class="spinner" style="margin:0 auto 16px"></div>
              <span class="badge {badge_class}" style="margin-bottom:12px; display:inline-block">{label}</span>
              <h3 style="margin-top:8px">Building Your Knowledge Base</h3>
              <p>{detail}</p>
            </div>
            {steps_html}
          </div>
        </div>"""
        return HTMLResponse(_page(body, extra_head=refresh))

    elif status == OnboardingStatus.failed:
        return _render_retry_step3(profile, profile.onboarding_error or "An error occurred.")

    return RedirectResponse("/onboarding", status_code=303)


# --- Legacy reset route (backward compat) -----------------

@router.get("/onboarding/reset")
async def onboarding_reset(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    profile = db.query(ClientProfile).filter(ClientProfile.user_id == current_user.id).first()
    if profile:
        profile.onboarding_status = OnboardingStatus.pending
        profile.onboarding_error  = None
        profile.onboarding_step   = 1
        db.commit()
    return RedirectResponse("/onboarding", status_code=303)


# ===========================================================
# Helpers
# ===========================================================

def _esc(val: str) -> str:
    """HTML-escape a value for use in attributes / textareas."""
    return (val or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _auto_register_scheduler(client_id: str):
    """Best-effort: add client to agent scheduler."""
    try:
        from agents.agent_scheduler import scheduler as _sched
        _sched.add_client(client_id)
    except Exception:
        pass
