"""
Shared layout shell for all authenticated pages.
Provides a consistent sidebar + topbar + main content area.

Usage:
    from utils.shared_layout import build_page

    html = build_page(
        title="Inbox",
        active_nav="inbox",          # highlights the correct sidebar item
        body_content="<h1>Hello</h1>",
        extra_css="",                # page-specific CSS injected into <style>
        extra_js="",                 # page-specific JS injected before </body>
        user_name="Admin",
        business_name="Nexarily AI",
    )
    return HTMLResponse(html)
"""

from datetime import datetime as _dt


# ──────────────────────────────────────────────────────────────────────────────
# Navigation definitions  (id, label, icon_entity, href, optional badge_id)
# ──────────────────────────────────────────────────────────────────────────────
_NAV_MAIN = [
    ("dashboard",        "Dashboard",        "&#127968;", "/dashboard",              None),
    ("create-post",      "Create Post",      "&#9997;",   "/create-post/dashboard",  None),
    ("calendar",         "Calendar",         "&#128197;", "/calendar",               None),
    ("inbox",            "Inbox",            "&#128232;", "/inbox/dashboard",        None),
    ("comments",         "Comments",         "&#128172;", "/comments/dashboard",     None),
    ("notifications",    "Notifications",    "&#128276;", "/notifications",          "notif-nav-badge"),
    ("analytics",        "Analytics",        "&#128202;", "/analytics/dashboard",    None),
]

_NAV_TOOLS = [
    ("image-generator", "Image Generator",  "&#127912;", "/image-generator",        None),
    ("faceless-video",  "Faceless Video",   "&#127916;", "/faceless-video",          None),
    ("social",          "Growth",           "&#128640;", "/growth/dashboard",        None),
    ("email",           "Email",            "&#128231;", "/email",                   None),
    ("intelligence",    "Intelligence",     "&#129504;", "/intelligence/dashboard",  None),
]

_NAV_SETTINGS = [
    ("settings",   "Settings",           "&#9881;",    "/settings",            None),
    ("connect",    "Social Accounts",    "&#128241;",  "/connect/dashboard",   None),
    ("notifications","Notifications",     "&#128276;",  "/settings/notifications", None),
    ("auto-reply", "Auto-Reply",         "&#129302;",  "/settings/auto-reply", None),
    ("growth-interests","Growth Interests","&#127793;",  "/settings/growth-interests", None),
    ("tone",       "Tone &amp; Style",   "&#127897;",  "/settings/tone",       None),
    ("knowledge",  "Knowledge Base",     "&#128218;",  "/settings/knowledge",  None),
    ("creative",   "Creative Style",     "&#127912;",  "/settings/creative",   None),
    ("security",   "Security",           "&#128274;",  "/settings/security",   None),
    ("billing",    "Billing &amp; Plan", "&#128179;",  "/billing",             None),
]


# ──────────────────────────────────────────────────────────────────────────────
# Shared CSS  (sidebar, topbar, cards, common utilities)
# ──────────────────────────────────────────────────────────────────────────────
SHELL_CSS = """
/* ── Reset & base ──────────────────────────────────────── */
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f0f2f5;color:#1c1e21;min-height:100vh;display:flex}
a{text-decoration:none;color:inherit}
button{cursor:pointer;border:none;background:none;font:inherit}

/* ── Left Sidebar ──────────────────────────────────────── */
.sidebar{
  width:240px;min-height:100vh;background:#fff;
  border-right:1px solid #dde0e4;
  display:flex;flex-direction:column;
  position:fixed;top:0;left:0;bottom:0;
  z-index:100;overflow-y:auto;
}
.sidebar-brand{
  padding:18px 20px 14px;border-bottom:1px solid #f0f2f5;
  display:flex;align-items:center;gap:10px;
  position:sticky;top:0;background:#fff;
}
.brand-logo{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  display:flex;align-items:center;justify-content:center;
  font-size:1.1rem;color:#fff;font-weight:800;
}
.brand-name{font-weight:800;font-size:1.05rem;color:#1c1e21}
.brand-sub{font-size:.7rem;color:#90949c;margin-top:1px}

.nav-section{padding:10px 0}
.nav-label{
  font-size:.68rem;font-weight:700;color:#90949c;
  text-transform:uppercase;letter-spacing:.08em;
  padding:6px 20px 4px;
}
.nav-item{
  display:flex;align-items:center;gap:12px;
  padding:9px 20px;border-radius:8px;
  margin:1px 8px;font-size:.9rem;font-weight:500;
  color:#444;transition:background .12s;cursor:pointer;
}
.nav-item:hover{background:#f0f2f5;color:#1c1e21}
.nav-item.active{background:#ede8f5;color:#5c6ac4;font-weight:600}
.nav-icon{font-size:1.05rem;width:22px;text-align:center}
.nav-badge{
  margin-left:auto;background:#e41e3f;color:#fff;
  font-size:.65rem;font-weight:700;border-radius:99px;
  padding:1px 6px;min-width:18px;text-align:center;
}

.sidebar-footer{
  margin-top:auto;padding:16px 20px;
  border-top:1px solid #f0f2f5;
  display:flex;align-items:center;gap:10px;
  position:sticky;bottom:0;background:#fff;
}
.avatar{
  width:34px;height:34px;border-radius:50%;
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-weight:700;font-size:.85rem;flex-shrink:0;
}
.footer-name{font-size:.85rem;font-weight:600;line-height:1.2}
.footer-role{font-size:.72rem;color:#90949c}
.logout-btn{
  margin-left:auto;font-size:.75rem;color:#90949c;
  padding:4px 8px;border-radius:6px;
}
.logout-btn:hover{background:#f0f2f5;color:#1c1e21}

/* ── Top header ────────────────────────────────────────── */
.topbar{
  position:fixed;top:0;left:240px;right:0;height:56px;
  background:#fff;border-bottom:1px solid #dde0e4;
  display:flex;align-items:center;padding:0 28px;
  z-index:99;gap:14px;
}
.topbar-title{font-size:1.05rem;font-weight:700;flex:1}
.topbar-date{font-size:.82rem;color:#90949c}
.search-bar{
  display:flex;align-items:center;gap:8px;
  background:#f0f2f5;border-radius:20px;
  padding:7px 14px;min-width:200px;
}
.search-bar input{
  border:none;background:transparent;font-size:.85rem;
  outline:none;color:#1c1e21;width:140px;
}
.icon-btn{
  width:36px;height:36px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:1.05rem;color:#606770;background:#f0f2f5;
  position:relative;transition:background .12s;
}
.icon-btn:hover{background:#e4e6eb;color:#1c1e21}
.notif-dot{
  position:absolute;top:-2px;right:-4px;
  min-width:18px;height:18px;border-radius:9px;
  background:#e41e3f;border:2px solid #fff;
  color:#fff;font-size:10px;font-weight:700;
  display:flex;align-items:center;justify-content:center;
  padding:0 4px;line-height:1;
}

/* ── Main content area ─────────────────────────────────── */
.main{margin-left:240px;padding-top:56px;flex:1;min-height:100vh}
.content-wrap{max-width:1100px;margin:0 auto;padding:24px 28px}

/* ── Common card ───────────────────────────────────────── */
.card{
  background:#fff;border-radius:12px;
  box-shadow:0 1px 4px rgba(0,0,0,.06);
  overflow:hidden;margin-bottom:18px;
}
.card-header{
  display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px 0;
}
.card-title{font-size:.92rem;font-weight:700;display:flex;align-items:center;gap:8px}
.card-action{font-size:.8rem;color:#5c6ac4;font-weight:600}
.card-action:hover{text-decoration:underline}
.card-body{padding:14px 20px 18px}

/* ── Common buttons ────────────────────────────────────── */
.btn-primary{
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  color:#fff;border:none;border-radius:8px;padding:10px 20px;
  font-size:.88rem;font-weight:700;cursor:pointer;
  transition:opacity .15s;display:inline-flex;align-items:center;gap:8px;
}
.btn-primary:hover{opacity:.88}
.btn-secondary{
  background:#f0f2f5;color:#1c1e21;border:1px solid #dde0e4;
  border-radius:8px;padding:8px 16px;font-size:.85rem;font-weight:600;
  cursor:pointer;transition:background .12s;
}
.btn-secondary:hover{background:#e4e6eb}

/* ── Common form inputs ────────────────────────────────── */
.form-input{
  width:100%;padding:10px 14px;border:1px solid #dde0e4;
  border-radius:8px;font-size:.88rem;color:#1c1e21;
  background:#fff;transition:border-color .15s;
}
.form-input:focus{border-color:#5c6ac4;outline:none;box-shadow:0 0 0 3px rgba(92,106,196,.12)}
textarea.form-input{resize:vertical;min-height:100px}
select.form-input{cursor:pointer}
.form-label{font-size:.82rem;font-weight:600;color:#444;margin-bottom:6px;display:block}

/* ── Common table ──────────────────────────────────────── */
.data-table{width:100%;border-collapse:collapse;font-size:.85rem}
.data-table th{
  text-align:left;font-weight:700;color:#606770;font-size:.75rem;
  text-transform:uppercase;letter-spacing:.04em;
  padding:10px 14px;border-bottom:2px solid #e4e6eb;
}
.data-table td{padding:12px 14px;border-bottom:1px solid #f0f2f5;color:#1c1e21}
.data-table tr:hover td{background:#f8f9fb}

/* ── Status badges ─────────────────────────────────────── */
.badge{
  display:inline-block;font-size:.72rem;font-weight:700;
  padding:2px 8px;border-radius:99px;
}
.badge-success{background:#e8f5e9;color:#2e7d32}
.badge-warning{background:#fff3e0;color:#e65100}
.badge-error{background:#fce4ec;color:#c62828}
.badge-info{background:#e8f0fe;color:#1565c0}
.badge-neutral{background:#f0f2f5;color:#606770}

/* ── Empty state ───────────────────────────────────────── */
.empty-state{text-align:center;padding:48px 20px;color:#90949c}
.empty-state .em-icon{font-size:2.5rem;margin-bottom:12px}
.empty-state p{font-size:.88rem;margin-bottom:8px}
.empty-state a{color:#5c6ac4;font-weight:600;font-size:.85rem}

/* ── Responsive ────────────────────────────────────────── */
@media(max-width:900px){
  .sidebar{width:64px}
  .sidebar .brand-sub,.sidebar .nav-label,.sidebar .footer-name,
  .sidebar .footer-role,.sidebar .nav-item span:not(.nav-icon):not(.nav-badge),
  .sidebar .brand-name{display:none}
  .sidebar-brand{justify-content:center;padding:14px 0}
  .sidebar-footer{justify-content:center}
  .topbar{left:64px}
  .main{margin-left:64px}
  .nav-item{justify-content:center;padding:9px 0;margin:1px 4px}
}

/* ── Sidebar collapse button ────────────────────────────── */
.sidebar-toggle-btn{
  margin-left:auto;width:26px;height:26px;border-radius:6px;
  display:flex;align-items:center;justify-content:center;
  font-size:.72rem;color:#606770;background:#f0f2f5;
  cursor:pointer;border:none;flex-shrink:0;transition:background .12s;
}
.sidebar-toggle-btn:hover{background:#e4e6eb;color:#1c1e21}

/* ── Collapsed sidebar state ────────────────────────────── */
body.sidebar-collapsed .sidebar{width:64px}
body.sidebar-collapsed .sidebar .brand-sub,
body.sidebar-collapsed .sidebar .nav-label,
body.sidebar-collapsed .sidebar .footer-name,
body.sidebar-collapsed .sidebar .footer-role,
body.sidebar-collapsed .sidebar .brand-name{display:none}
body.sidebar-collapsed .sidebar-brand{justify-content:center;padding:14px 0}
body.sidebar-collapsed .sidebar-footer{justify-content:center}
body.sidebar-collapsed .topbar{left:64px}
body.sidebar-collapsed .main{margin-left:64px}
body.sidebar-collapsed .sidebar .nav-item{justify-content:center;padding:9px 0;margin:1px 4px}
body.sidebar-collapsed .sidebar-toggle-btn{margin-left:0}

::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#d8d8d8;border-radius:99px}

/* ── Alita Floating Assistant (Chief of Staff) ──────────── */
#fab-alita-btn{
  position:fixed;bottom:28px;right:28px;
  width:56px;height:56px;border-radius:16px;
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  color:#fff;font-size:1.1rem;font-weight:800;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;border:none;
  box-shadow:0 4px 20px rgba(92,106,196,.4);
  z-index:9999;transition:transform .18s,box-shadow .18s,border-radius .18s;
  letter-spacing:-.02em;
  animation:fabPulseGlow 3s ease-in-out infinite;
}
@keyframes fabPulseGlow{
  0%,100%{box-shadow:0 4px 20px rgba(92,106,196,.4)}
  50%{box-shadow:0 4px 20px rgba(92,106,196,.4),0 0 0 8px rgba(92,106,196,.12)}
}
#fab-alita-btn:hover{transform:scale(1.06);box-shadow:0 6px 28px rgba(92,106,196,.55);border-radius:14px;animation:none}
#fab-alita-btn .fab-badge-dot{
  position:absolute;top:-3px;right:-3px;width:14px;height:14px;
  border-radius:50%;background:#e41e3f;border:2.5px solid #fff;
  display:none;
}

/* Panel */
#fab-alita-panel{
  position:fixed;bottom:96px;right:24px;
  width:390px;max-height:560px;
  background:#fff;border-radius:16px;
  box-shadow:0 8px 40px rgba(0,0,0,.16);
  z-index:9998;display:none;flex-direction:column;overflow:hidden;
}
#fab-alita-panel.fab-open{display:flex;animation:fabSlideIn .2s ease}
@keyframes fabSlideIn{
  from{opacity:0;transform:translateY(12px) scale(.97)}
  to  {opacity:1;transform:translateY(0)    scale(1)}
}

/* Header — animated gradient */
.fab-header{
  padding:16px 18px 14px;
  display:flex;align-items:center;gap:10px;flex-shrink:0;
  background:linear-gradient(135deg,#5c6ac4 0%,#764ba2 50%,#5c6ac4 100%);
  background-size:200% 200%;
  animation:fabHeaderShift 6s ease infinite;
  position:relative;
}
.fab-header::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(255,255,255,.06) 0%,transparent 100%);pointer-events:none}
@keyframes fabHeaderShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
.fab-logo{
  width:36px;height:36px;border-radius:10px;
  background:rgba(255,255,255,.18);
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-weight:800;font-size:.95rem;flex-shrink:0;
  animation:fabLogoPulse 3s ease-in-out infinite;
}
@keyframes fabLogoPulse{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,.25)}50%{box-shadow:0 0 0 6px rgba(255,255,255,0)}}
.fab-header-title{font-weight:800;font-size:.95rem;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.12)}
.fab-header-sub{font-size:.72rem;color:rgba(255,255,255,.78);margin-top:1px;display:flex;align-items:center;gap:5px}
.fab-header-sub::before{content:'';width:7px;height:7px;border-radius:50%;background:#4ade80;display:inline-block;animation:fabDotPulse 2s ease-in-out infinite}
@keyframes fabDotPulse{0%,100%{box-shadow:0 0 0 0 rgba(74,222,128,.4)}50%{box-shadow:0 0 0 4px rgba(74,222,128,0)}}
.fab-ctrl-btn{
  background:rgba(255,255,255,.15);backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.15);
  color:#fff;
  width:28px;height:28px;border-radius:6px;cursor:pointer;font-size:.82rem;
  display:flex;align-items:center;justify-content:center;transition:all .12s;
}
.fab-ctrl-btn:hover{background:rgba(255,255,255,.28);color:#fff}

/* Tabs */
.fab-tabs{
  display:flex;border-bottom:1px solid #f0f2f5;flex-shrink:0;background:#fff;
}
.fab-tab{
  flex:1;padding:10px 0;text-align:center;font-size:.8rem;font-weight:600;
  color:#90949c;cursor:pointer;border-bottom:2px solid transparent;
  transition:all .12s;background:none;border-top:none;border-left:none;border-right:none;
}
.fab-tab:hover{color:#1c1e21}
.fab-tab.active{color:#5c6ac4;border-bottom-color:#5c6ac4}

/* Briefing body */
#fab-briefing{
  flex:1;overflow-y:auto;padding:14px 16px;
  display:flex;flex-direction:column;gap:10px;
}

/* Insight cards */
.insight-card{
  background:#f8f9fb;border:1px solid #eef0f3;
  border-radius:10px;padding:12px 14px;
  display:flex;gap:10px;align-items:flex-start;
  transition:box-shadow .12s,border-color .12s;cursor:default;
}
.insight-card:hover{border-color:#d0d4e0;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.insight-card.card-alert{border-left:3px solid #e41e3f}
.insight-card.card-suggestion{border-left:3px solid #5c6ac4}
.insight-card.card-win{border-left:3px solid #2e7d32}
.insight-card.card-nudge{border-left:3px solid #e0a200}
.ic-icon{font-size:1.15rem;flex-shrink:0;margin-top:1px}
.ic-content{flex:1;min-width:0}
.ic-title{font-weight:700;font-size:.82rem;color:#1c1e21;line-height:1.3}
.ic-body{font-size:.78rem;color:#606770;line-height:1.45;margin-top:3px}
.ic-action{
  display:inline-block;margin-top:6px;font-size:.74rem;font-weight:700;
  color:#5c6ac4;text-decoration:none;
}
.ic-action:hover{text-decoration:underline}

/* Loading skeleton */
.insight-skel{
  background:#f0f2f5;border-radius:10px;height:72px;
  animation:skelPulse 1.2s ease infinite;
}
@keyframes skelPulse{
  0%,100%{opacity:.6} 50%{opacity:.3}
}

/* Chat body */
#fab-chat{
  flex:1;overflow-y:auto;padding:14px 16px;
  display:none;flex-direction:column;gap:12px;
  scroll-behavior:smooth;
  background:linear-gradient(180deg,#fafbff 0%,#f5f6fa 100%);
}
#fab-chat::-webkit-scrollbar{width:5px}
#fab-chat::-webkit-scrollbar-track{background:transparent}
#fab-chat::-webkit-scrollbar-thumb{background:#d4cef0;border-radius:99px}
#fab-chat::-webkit-scrollbar-thumb:hover{background:#b0a8d8}
.fab-msg-alita{display:flex;gap:8px;align-items:flex-start;animation:fabMsgIn .3s cubic-bezier(.22,1,.36,1) both}
.fab-msg-user {display:flex;gap:8px;align-items:flex-start;justify-content:flex-end;animation:fabMsgIn .3s cubic-bezier(.22,1,.36,1) both}
@keyframes fabMsgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.fab-bubble{max-width:78%;padding:10px 13px;border-radius:14px;font-size:.84rem;line-height:1.5;word-break:break-word}
.fab-bubble-alita{background:#fff;color:#1c1e21;border-radius:4px 14px 14px 14px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.fab-bubble-user {background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border-radius:14px 4px 14px 14px;box-shadow:0 2px 6px rgba(92,106,196,.2)}
.fab-avatar{
  width:26px;height:26px;border-radius:50%;
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  display:flex;align-items:center;justify-content:center;
  font-size:.78rem;flex-shrink:0;color:#fff;font-weight:700;
  box-shadow:0 1px 4px rgba(92,106,196,.2);
}
.fab-typing-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#90949c;margin:0 2px;animation:fabBounce .9s infinite}
.fab-typing-dot:nth-child(2){animation-delay:.15s}
.fab-typing-dot:nth-child(3){animation-delay:.3s}
@keyframes fabBounce{0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)}}
.fab-typing-shimmer{position:relative;overflow:hidden}
.fab-typing-shimmer::after{content:'';position:absolute;top:0;left:-100%;width:200%;height:100%;background:linear-gradient(90deg,transparent 25%,rgba(92,106,196,.06) 50%,transparent 75%);animation:fabShimmer 1.5s ease infinite}
@keyframes fabShimmer{to{transform:translateX(50%)}}
/* Suggestion chips (FAB) */
.fab-chip-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.fab-chip{background:#fff;border:1.5px solid #d4cef0;color:#5c6ac4;padding:5px 11px;border-radius:99px;font-size:.74rem;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap;line-height:1.3}
.fab-chip:hover{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border-color:transparent;transform:translateY(-1px);box-shadow:0 2px 8px rgba(92,106,196,.2)}
.fab-chip:active{transform:translateY(0)}

/* Footer input */
#fab-alita-footer{
  padding:10px 14px;border-top:1px solid #f0f2f5;
  display:flex;gap:8px;align-items:flex-end;flex-shrink:0;
  background:#fff;
}
#fab-alita-input{
  flex:1;border:1.5px solid #dde0e4;border-radius:10px;
  padding:9px 13px;font-size:.84rem;font-family:inherit;
  resize:none;outline:none;line-height:1.5;
  max-height:90px;overflow-y:auto;transition:all .2s;
}
#fab-alita-input:focus{border-color:#5c6ac4;box-shadow:0 0 0 3px rgba(92,106,196,.12)}
#fab-alita-send{
  background:linear-gradient(135deg,#5c6ac4,#764ba2);
  color:#fff;border:none;width:36px;height:36px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;flex-shrink:0;transition:all .2s;
}
#fab-alita-send:hover{transform:scale(1.08);box-shadow:0 3px 10px rgba(92,106,196,.3)}
#fab-alita-send:active{transform:scale(.95)}
#fab-alita-send:disabled{opacity:.4;cursor:default;transform:none;box-shadow:none}
@media(max-width:500px){
  #fab-alita-panel{width:calc(100vw - 20px);right:10px;max-height:70vh}
}

/* ── Action card styles (FAB widget) ── */
.fab-action-card{background:#f8f6ff;border:1px solid #d4cef0;border-left:3px solid #5c6ac4;border-radius:10px;padding:12px 14px;margin:4px 8px;font-size:.82rem;animation:fabMsgIn .3s both}
.fab-action-card .fac-hdr{font-weight:700;color:#3d2b8c;margin-bottom:8px;font-size:.86rem}
.fab-action-card .fac-row{color:#444;padding:2px 0}
.fab-action-card .fac-row b{color:#1c1e21}
.fab-action-card .fac-opt{color:#5c6ac4;font-style:italic;font-size:.78rem;padding:1px 0}
.fab-action-card .fac-btns{display:flex;gap:6px;margin-top:10px}
.fab-action-card .fac-btn{padding:6px 14px;border-radius:7px;font-weight:700;font-size:.78rem;border:none;cursor:pointer;transition:all .15s}
.fab-action-card .fac-go{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff}
.fab-action-card .fac-go:hover{transform:translateY(-1px);box-shadow:0 2px 8px rgba(92,106,196,.25)}
.fab-action-card .fac-no{background:#f0f2f5;color:#606770}
.fab-action-card .fac-no:hover{background:#e4e6eb}
.fab-progress-card{background:#fff;border:1px solid #e4e6eb;border-left:3px solid #5c6ac4;border-radius:8px;padding:10px 12px;margin:4px 8px;display:flex;align-items:center;gap:8px;font-size:.8rem;color:#444;animation:fabMsgIn .3s both}
.fab-progress-card .fpc-spin{width:16px;height:16px;border:2px solid #d4cef0;border-top-color:#5c6ac4;border-radius:50%;animation:fabPcSpin .7s linear infinite}
@keyframes fabPcSpin{to{transform:rotate(360deg)}}
.fab-result-card{background:#f0faf0;border:1px solid #c6e6c6;border-left:3px solid #2e7d32;border-radius:10px;padding:10px 14px;margin:4px 8px;font-size:.82rem;animation:fabMsgIn .3s both}
.fab-result-card.fab-result-err{background:#fff5f5;border-color:#e6c6c6;border-left-color:#c62828}
.fab-result-card .frc-hdr{font-weight:700;color:#2e7d32;margin-bottom:6px;font-size:.84rem}
.fab-result-card.fab-result-err .frc-hdr{color:#c62828}
.fab-result-card .frc-body{color:#333;line-height:1.5}
.fab-result-card .frc-body img{max-width:100%;border-radius:6px;margin:6px 0}
"""

# ──────────────────────────────────────────────────────────────────────────────
# Floating Alita Assistant widget  (injected into every page)
# ──────────────────────────────────────────────────────────────────────────────

_FAB_HTML = """
<!-- ════ ALITA CHIEF OF STAFF ════ -->
<button id="fab-alita-btn" onclick="fabToggle()" title="Ask Alita">
  A<span class="fab-badge-dot" id="fab-bdot"></span>
</button>
<div id="fab-alita-panel">
  <div class="fab-header">
    <div class="fab-logo">A</div>
    <div style="flex:1">
      <div class="fab-header-title">Alita</div>
      <div class="fab-header-sub">Your AI Strategist \u2022 Online</div>
    </div>
    <button class="fab-ctrl-btn" onclick="fabRefresh()" title="Refresh insights" style="font-size:.72rem">&#8635;</button>
    <a class="fab-ctrl-btn" href="/alita/chat" title="Full conversation" style="font-size:.7rem;text-decoration:none">&#8599;</a>
    <button class="fab-ctrl-btn" onclick="fabClose()" title="Close">&#10005;</button>
  </div>
  <div class="fab-tabs">
    <button class="fab-tab active" id="fab-tab-briefing" onclick="fabSwitchTab('briefing')">Briefing</button>
    <button class="fab-tab" id="fab-tab-chat" onclick="fabSwitchTab('chat')">Chat</button>
  </div>
  <div id="fab-briefing">
    <div class="insight-skel"></div>
    <div class="insight-skel" style="height:60px"></div>
    <div class="insight-skel" style="height:52px"></div>
  </div>
  <div id="fab-chat">
    <div class="fab-msg-alita">
      <div class="fab-avatar">A</div>
      <div>
        <div class="fab-bubble fab-bubble-alita">Hey! What can I help you with? &#128640;</div>
        <div class="fab-chip-row" id="fab-chips">
          <button class="fab-chip" onclick="fabChipSend(this)">&#9997;&#65039; Create a post</button>
          <button class="fab-chip" onclick="fabChipSend(this)">&#127912; Generate image</button>
          <button class="fab-chip" onclick="fabChipSend(this)">&#128202; Analytics</button>
          <button class="fab-chip" onclick="fabChipSend(this)">&#128161; Content ideas</button>
        </div>
      </div>
    </div>
  </div>
  <div id="fab-alita-footer">
    <textarea id="fab-alita-input" rows="1" placeholder="Ask Alita anything&hellip;"
      onkeydown="fabHandleKey(event)" oninput="fabResize(this)"
      onfocus="fabSwitchTab('chat')"></textarea>
    <button id="fab-alita-send" onclick="fabSend()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
  </div>
</div>
"""

_FAB_JS = """
// ── Alita Chief of Staff ─────────────────────────────────────
let _fabInsightsLoaded = false;
let _fabCurrentTab = 'briefing';

function fabToggle() {
  const panel = document.getElementById('fab-alita-panel');
  if (!panel) return;
  const opening = !panel.classList.contains('fab-open');
  panel.classList.toggle('fab-open');
  if (opening) {
    if (!_fabInsightsLoaded) fabLoadInsights();
    // hide badge dot
    const dot = document.getElementById('fab-bdot');
    if (dot) dot.style.display = 'none';
  }
}
function fabClose() {
  const p = document.getElementById('fab-alita-panel');
  if (p) p.classList.remove('fab-open');
}

// ── Tab switching ──
function fabSwitchTab(tab) {
  _fabCurrentTab = tab;
  const bTab = document.getElementById('fab-tab-briefing');
  const cTab = document.getElementById('fab-tab-chat');
  const bDiv = document.getElementById('fab-briefing');
  const cDiv = document.getElementById('fab-chat');
  if (tab === 'briefing') {
    bTab.classList.add('active'); cTab.classList.remove('active');
    bDiv.style.display = 'flex'; cDiv.style.display = 'none';
  } else {
    cTab.classList.add('active'); bTab.classList.remove('active');
    cDiv.style.display = 'flex'; bDiv.style.display = 'none';
    fabChatScroll();
  }
}

// ── Insights ──
async function fabLoadInsights(force) {
  const box = document.getElementById('fab-briefing');
  if (!box) return;
  const page = document.body.getAttribute('data-alita-page') || 'dashboard';
  const url = '/api/alita/insights?page=' + encodeURIComponent(page) + (force ? '&force=1' : '');
  // Show skeleton
  box.innerHTML = '<div class="insight-skel"></div><div class="insight-skel" style="height:60px"></div><div class="insight-skel" style="height:52px"></div>';
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error('status ' + r.status);
    const data = await r.json();
    const cards = data.cards || [];
    if (cards.length === 0) {
      box.innerHTML = '<div style="text-align:center;padding:28px 10px;color:#90949c;font-size:.84rem">No insights right now — check back later!</div>';
      _fabInsightsLoaded = true;
      return;
    }
    box.innerHTML = '';
    cards.forEach(function(c) {
      const typeClass = 'card-' + (c.type || 'suggestion');
      const action = (c.action_url && c.action_label)
        ? '<a class="ic-action" href="' + c.action_url + '">' + c.action_label + ' &rarr;</a>'
        : '';
      const el = document.createElement('div');
      el.className = 'insight-card ' + typeClass;
      el.innerHTML =
        '<div class="ic-icon">' + (c.icon || '\\ud83d\\udca1') + '</div>' +
        '<div class="ic-content">' +
          '<div class="ic-title">' + fabEsc(c.title || '') + '</div>' +
          '<div class="ic-body">' + fabEsc(c.body || '') + '</div>' +
          action +
        '</div>';
      box.appendChild(el);
    });
    _fabInsightsLoaded = true;
    // Show dot on FAB if there are high-priority items and panel is closed
    const panel = document.getElementById('fab-alita-panel');
    if (!panel || !panel.classList.contains('fab-open')) {
      const hasHigh = cards.some(function(c) { return c.priority === 'high'; });
      const dot = document.getElementById('fab-bdot');
      if (dot && hasHigh) dot.style.display = '';
    }
  } catch(e) {
    box.innerHTML = '<div style="text-align:center;padding:28px 10px;color:#90949c;font-size:.84rem">Could not load insights. <a href="javascript:fabRefresh()" style="color:#5c6ac4;font-weight:600">Try again</a></div>';
  }
}
function fabRefresh() { fabLoadInsights(true); }

// ── Chat ──
function fabResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 90) + 'px';
}
function fabHandleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); fabSend(); }
}
function fabChatScroll() {
  const box = document.getElementById('fab-chat');
  if (box) box.scrollTop = box.scrollHeight;
}
function fabEsc(t) {
  return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fabFmt(t) {
  t = fabEsc(t);
  t = t.replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');
  t = t.replace(/\\n- /g,'<br>&bull; ');
  t = t.replace(/\\n/g,'<br>');
  return t;
}
function fabAddMsg(role, text) {
  const box = document.getElementById('fab-chat');
  if (!box) return;
  // Remove suggestion chips after first real message
  const chips = document.getElementById('fab-chips');
  if (chips) chips.remove();
  const d = document.createElement('div');
  d.className = role === 'user' ? 'fab-msg-user' : 'fab-msg-alita';
  if (role === 'assistant') {
    d.innerHTML = '<div class="fab-avatar">A</div><div class="fab-bubble fab-bubble-alita">' + fabFmt(text) + '</div>';
  } else {
    d.innerHTML = '<div class="fab-bubble fab-bubble-user">' + fabEsc(text) + '</div>';
  }
  box.appendChild(d);
  fabChatScroll();
}
function fabShowTyping() {
  const box = document.getElementById('fab-chat');
  if (!box) return;
  const d = document.createElement('div');
  d.className = 'fab-msg-alita'; d.id = 'fab-typing';
  d.innerHTML = '<div class="fab-avatar">A</div><div class="fab-bubble fab-bubble-alita fab-typing-shimmer" style="padding:10px 14px"><span class="fab-typing-dot"></span><span class="fab-typing-dot"></span><span class="fab-typing-dot"></span></div>';
  box.appendChild(d); fabChatScroll();
}
function fabHideTyping() {
  const el = document.getElementById('fab-typing');
  if (el) el.remove();
}
async function fabSend() {
  const input = document.getElementById('fab-alita-input');
  const btn   = document.getElementById('fab-alita-send');
  if (!input || !btn) return;
  const msg = input.value.trim();
  if (!msg) return;
  // Switch to chat tab
  if (_fabCurrentTab !== 'chat') fabSwitchTab('chat');
  btn.disabled = true;
  input.value = ''; input.style.height = 'auto';
  fabAddMsg('user', msg);
  fabShowTyping();
  try {
    const r = await fetch('/api/alita/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg}),
    });
    const data = await r.json();
    fabHideTyping();
    if (data.reply) {
      fabAddMsg('assistant', data.reply);
      if (data.navigate_url) {
        setTimeout(function() { window.location.href = data.navigate_url; }, 1500);
      }
      if (data.action) {
        fabShowActionCard(data.action);
      }
      if (data.project_interest_detected) {
        const box = document.getElementById('fab-chat');
        if (box) {
          const d = document.createElement('div');
          d.style.cssText = 'background:#ede8f5;border:1px solid #c5bce8;border-radius:8px;padding:8px 12px;font-size:.78rem;color:#3d2b8c;font-weight:600;text-align:center;margin:2px 0';
          d.textContent = '\\ud83d\\udd14 Your account manager has been notified!';
          box.appendChild(d); fabChatScroll();
        }
      }
    } else { fabAddMsg('assistant', 'Sorry, something went wrong. Try again!'); }
  } catch(e) { fabHideTyping(); fabAddMsg('assistant', 'Connection error \\u2014 please try again.'); }
  btn.disabled = false;
  if (input) input.focus();
}

// ── Action cards (FAB widget) ──
let _fabPendingAction = null;

function fabShowActionCard(action) {
  _fabPendingAction = action;
  const box = document.getElementById('fab-chat');
  if (!box) return;
  const card = document.createElement('div');
  card.className = 'fab-action-card';
  card.id = 'fab-ac-' + action.action_id;
  let rows = '';
  if (action.rows) {
    action.rows.forEach(function(r) { rows += '<div class="fac-row"><b>' + fabEsc(r.label) + ':</b> ' + fabEsc(r.value) + '</div>'; });
  }
  let opts = '';
  if (action.optimizations && action.optimizations.length) {
    action.optimizations.forEach(function(o) { opts += '<div class="fac-opt">\\u2728 ' + fabEsc(o) + '</div>'; });
  }
  card.innerHTML =
    '<div class="fac-hdr">' + (action.emoji || '\\ud83d\\ude80') + ' ' + fabEsc(action.display_name || 'Action') + '</div>' +
    rows + opts +
    '<div class="fac-btns">' +
      '<button class="fac-btn fac-go" onclick="fabExecAction(\\'' + action.action_id + '\\')">\\u2713 Execute</button>' +
      '<button class="fac-btn fac-no" onclick="fabCancelAction(\\'' + action.action_id + '\\')">Cancel</button>' +
    '</div>';
  box.appendChild(card);
  fabChatScroll();
}

function fabShowProgress(actionId, msg) {
  let el = document.getElementById('fab-prog-' + actionId);
  if (!el) {
    const box = document.getElementById('fab-chat');
    if (!box) return;
    el = document.createElement('div');
    el.className = 'fab-progress-card';
    el.id = 'fab-prog-' + actionId;
    el.innerHTML = '<div class="fpc-spin"></div><span></span>';
    box.appendChild(el);
    fabChatScroll();
  }
  el.querySelector('span').textContent = msg;
  fabChatScroll();
}

function fabShowResult(actionId, event) {
  const prog = document.getElementById('fab-prog-' + actionId);
  if (prog) prog.remove();
  const ac = document.getElementById('fab-ac-' + actionId);
  if (ac) ac.remove();
  const box = document.getElementById('fab-chat');
  if (!box) return;
  const card = document.createElement('div');
  const isErr = event.status === 'error';
  card.className = 'fab-result-card' + (isErr ? ' fab-result-err' : '');
  if (isErr) {
    card.innerHTML = '<div class="frc-hdr">\\u274c Error</div><div class="frc-body">' + fabEsc(event.message || 'Something went wrong') + '</div>';
  } else {
    const result = event.result || {};
    const rtype = event.result_type || '';
    let body = '';
    if (rtype === 'content' || rtype === 'ideas' || rtype === 'strategy' || rtype === 'calendar') {
      body = fabFmt(result.content || result.ideas || result.strategy || result.calendar || JSON.stringify(result));
    } else if (rtype === 'image') {
      body = (result.image_url ? '<img src="' + result.image_url + '" />' : '') + '<div>' + fabEsc(result.prompt || '') + '</div>';
    } else if (rtype === 'schedule') {
      body = '\\ud83d\\udcc5 ' + fabEsc(result.message || 'Scheduled!');
    } else if (rtype === 'analytics') {
      body = fabFmt(result.summary || JSON.stringify(result));
    } else if (rtype === 'times') {
      body = fabFmt(result.times || JSON.stringify(result));
    } else {
      body = fabFmt(JSON.stringify(result));
    }
    card.innerHTML = '<div class="frc-hdr">\\u2705 Done!</div><div class="frc-body">' + body + '</div>';
  }
  box.appendChild(card);
  fabChatScroll();
  _fabPendingAction = null;
}

async function fabExecAction(actionId) {
  const ac = document.getElementById('fab-ac-' + actionId);
  if (ac) { ac.querySelectorAll('button').forEach(function(b) { b.disabled = true; }); }
  fabShowProgress(actionId, 'Starting...');
  try {
    const resp = await fetch('/api/alita/execute', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action_id: actionId}),
    });
    if (!resp.ok) {
      const ed = await resp.json().catch(function() { return {}; });
      fabShowResult(actionId, {status:'error', message: ed.error || 'Action failed'});
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const lines = buf.split('\\n');
      buf = lines.pop();
      lines.forEach(function(line) {
        if (line.startsWith('data: ')) {
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.status === 'progress') fabShowProgress(actionId, ev.message);
            else if (ev.status === 'complete') fabShowResult(actionId, ev);
            else if (ev.status === 'error') fabShowResult(actionId, ev);
          } catch(e) {}
        }
      });
    }
  } catch(e) {
    fabShowResult(actionId, {status:'error', message:'Connection error'});
  }
}

async function fabCancelAction(actionId) {
  const ac = document.getElementById('fab-ac-' + actionId);
  if (ac) ac.remove();
  try { await fetch('/api/alita/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action_id:actionId})}); } catch(e) {}
  fabAddMsg('assistant', 'Action cancelled. What else can I help with?');
  _fabPendingAction = null;
}

// ── Pre-load insights on page load (after small delay) ──
setTimeout(function() { fabLoadInsights(); }, 2000);

function fabChipSend(btn) {
  var raw = btn.textContent.trim();
  var text = raw.replace(/^\\S+\\s*/, '').trim() || raw;
  var input = document.getElementById('fab-alita-input');
  if (input) { input.value = text; fabSend(); }
}
"""

def _nav_html(items: list, active: str) -> str:
    out = []
    for nav_id, label, icon, href, badge_id in items:
        cls = "nav-item active" if nav_id == active else "nav-item"
        badge = ""
        if badge_id:
            badge = f'<span class="nav-badge" id="{badge_id}" style="display:none">0</span>'
        out.append(
            f'<a class="{cls}" href="{href}">'
            f'<span class="nav-icon">{icon}</span> {label}{badge}'
            f'</a>'
        )
    return "\n    ".join(out)


def build_page(
    *,
    title: str,
    active_nav: str,
    body_content: str,
    user_name: str = "User",
    business_name: str = "My Business",
    extra_css: str = "",
    extra_js: str = "",
    topbar_title: str | None = None,
    show_alita_widget: bool = True,
) -> str:
    """
    Return a complete HTML page wrapped in the shared sidebar + topbar shell.

    Parameters
    ----------
    title        : Browser tab title (after "Alita AI - ")
    active_nav   : One of the nav IDs (dashboard, inbox, comments, etc.)
    body_content : Raw HTML to inject inside <main class="main"><div class="content-wrap">
    user_name    : Current user's full_name
    business_name: Client business name (shown under sidebar logo)
    extra_css    : CSS rules appended inside <style> (no <style> tags needed)
    extra_js     : JS code appended inside <script> before </body> (no <script> tags needed)
    topbar_title : Override for the topbar left-side text (defaults to title)
    """
    first_initial = user_name[0].upper() if user_name else "?"
    today = _dt.now().strftime("%A, %B %d").replace(" 0", " ")
    tb_title = topbar_title or title

    main_nav  = _nav_html(_NAV_MAIN, active_nav)
    tools_nav = _nav_html(_NAV_TOOLS, active_nav)
    sett_nav  = _nav_html(_NAV_SETTINGS, active_nav)

    safe_bname = (business_name or "My Business")[:28]

    # Floating widget
    _fab_html = _FAB_HTML if show_alita_widget else ""
    _fab_extra_js = _FAB_JS if show_alita_widget else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Alita AI &mdash; {title}</title>
  <style>
{SHELL_CSS}
{extra_css}
  </style>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/all.min.css">
</head>
<body data-alita-page="{active_nav}">

<!-- ════ LEFT SIDEBAR ════ -->
<aside class="sidebar">
  <div class="sidebar-brand">
    <div class="brand-logo">A</div>
    <div>
      <div class="brand-name">Alita AI</div>
      <div class="brand-sub">{safe_bname}</div>
    </div>
    <button class="sidebar-toggle-btn" id="sidebar-toggle"
            onclick="toggleSidebar()" title="Collapse sidebar">&#9776;</button>
  </div>

  <nav class="nav-section">
    <div class="nav-label">Main</div>
    {main_nav}
  </nav>

  <nav class="nav-section">
    <div class="nav-label">Tools</div>
    {tools_nav}
  </nav>

  <nav class="nav-section">
    <div class="nav-label">Settings</div>
    {sett_nav}
  </nav>

  <div class="sidebar-footer">
    <div class="avatar">{first_initial}</div>
    <div>
      <div class="footer-name">{user_name}</div>
      <div class="footer-role">Client Admin</div>
    </div>
    <a class="logout-btn" href="/account/logout">Sign out</a>
  </div>
</aside>

<!-- ════ TOP HEADER ════ -->
<header class="topbar">
  <div class="topbar-title">{tb_title}</div>
  <span class="topbar-date">{today}</span>
  <div style="flex:1"></div>
  <div class="search-bar">
    <span style="color:#90949c;font-size:.9rem">&#128269;</span>
    <input type="text" placeholder="Search&hellip;" />
  </div>
  <a class="icon-btn" href="/notifications" title="Notifications" id="bell-btn">
    &#128276;
    <span class="notif-dot" id="bell-dot" style="display:none">0</span>
  </a>
  <div class="icon-btn" style="background:#ede8f5;color:#5c6ac4;font-weight:700">{first_initial}</div>
</header>

<!-- ════ MAIN CONTENT ════ -->
<main class="main">
  <div class="content-wrap">
    {body_content}
  </div>
</main>

<script>
// ── Sidebar collapse (persisted) ──────────────────────────
(function(){{
  if (localStorage.getItem('sidebarCollapsed') === '1') {{
    document.body.classList.add('sidebar-collapsed');
    const btn = document.getElementById('sidebar-toggle');
    if (btn) btn.title = 'Expand sidebar';
  }}
}})();
function toggleSidebar() {{
  const collapsed = document.body.classList.toggle('sidebar-collapsed');
  localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
  const btn = document.getElementById('sidebar-toggle');
  if (btn) btn.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
}}

// ── Notification badge polling (shared across all pages) ──
async function refreshNotifBadge() {{
  try {{
    const r = await fetch('/api/notifications?unread_only=true&limit=1');
    if (r.status === 401) {{ clearInterval(notifPoll); return; }}
    const data = await r.json();
    const cnt = data.unread_count || 0;
    const dot = document.getElementById('bell-dot');
    const badge = document.getElementById('notif-nav-badge');
    if (cnt > 0) {{
      if (dot) {{ dot.textContent = cnt > 99 ? '99+' : cnt; dot.style.display = ''; }}
      if (badge) {{ badge.textContent = cnt; badge.style.display = ''; }}
    }} else {{
      if (dot) dot.style.display = 'none';
      if (badge) badge.style.display = 'none';
    }}
  }} catch(e) {{}}
}}
let notifPoll = setInterval(refreshNotifBadge, 60000);
refreshNotifBadge();

/* ── Inactivity auto-logout (30 min) ── */
(function() {{
  const IDLE_MS      = 30 * 60 * 1000;   // 30 minutes
  const WARN_MS      = 25 * 60 * 1000;   // warn at 25 min
  const STORAGE_KEY  = 'alita_lastActivity';
  const LOGOUT_URL   = '/account/logout';

  function stamp() {{ return Date.now(); }}

  // Persist activity across tabs via localStorage
  let _last = stamp();
  localStorage.setItem(STORAGE_KEY, _last);

  let _throttle = 0;
  function onActivity() {{
    const now = stamp();
    if (now - _throttle < 1000) return;   // throttle to 1 /sec
    _throttle = now;
    _last = now;
    localStorage.setItem(STORAGE_KEY, now);
    hideWarning();                         // dismiss warning if shown
  }}

  ['keydown','scroll','click','submit','change','input'].forEach(function(evt) {{
    document.addEventListener(evt, onActivity, {{ passive: true }});
  }});

  // Warning toast ─────────────────────────────────────────────
  let _toastEl = null;
  function showWarning() {{
    if (_toastEl) return;
    _toastEl = document.createElement('div');
    _toastEl.id = 'idle-warning-toast';
    _toastEl.innerHTML =
      '<div style="display:flex;align-items:center;gap:12px;">' +
        '<span style="font-size:14px;">You\\'ll be logged out in <b>5 minutes</b> due to inactivity.</span>' +
        '<button id="idle-stay-btn" style="' +
          'background:#6c5ce7;color:#fff;border:none;border-radius:8px;' +
          'padding:6px 16px;font-size:13px;cursor:pointer;white-space:nowrap;' +
        '">Stay Logged In</button>' +
      '</div>';
    Object.assign(_toastEl.style, {{
      position:'fixed', top:'24px', right:'24px', zIndex:'99999',
      background:'#1e1e2e', color:'#fff', padding:'14px 20px',
      borderRadius:'12px', boxShadow:'0 4px 24px rgba(0,0,0,.35)',
      fontFamily:'-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif',
      transition:'opacity .3s', opacity:'0'
    }});
    document.body.appendChild(_toastEl);
    requestAnimationFrame(function() {{ _toastEl.style.opacity = '1'; }});
    document.getElementById('idle-stay-btn').addEventListener('click', function() {{
      onActivity();
    }});
  }}
  function hideWarning() {{
    if (!_toastEl) return;
    _toastEl.remove();
    _toastEl = null;
  }}

  // Check loop (every 30 s) ───────────────────────────────────
  setInterval(function() {{
    // Read from localStorage so activity in ANY tab keeps all tabs alive
    const last = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10) || _last;
    const idle  = stamp() - last;
    if (idle >= IDLE_MS) {{
      localStorage.removeItem(STORAGE_KEY);
      window.location.href = LOGOUT_URL;
    }} else if (idle >= WARN_MS) {{
      showWarning();
    }}
  }}, 30000);
}})();

{_fab_extra_js}
{extra_js}
</script>
{_fab_html}
</body>
</html>"""


def get_user_context(request, db):
    """
    Helper: fetch current user + client profile for any authenticated page.
    Returns (user, profile) or (None, None).
    """
    from api.auth_routes import get_current_user
    from database.models import ClientProfile

    user = get_current_user(request, db)
    if not user:
        return None, None
    profile = db.query(ClientProfile).filter(
        ClientProfile.user_id == user.id
    ).first()
    return user, profile


def require_auth_and_profile(request, db):
    """
    Helper: get user + profile, return redirect if missing.
    Returns (user, profile) or raises a redirect response.
    """
    from fastapi.responses import RedirectResponse
    from database.models import OnboardingStatus

    user, profile = get_user_context(request, db)
    if not user:
        raise _Redirect("/account/login")
    if not profile:
        raise _Redirect("/onboarding")
    if profile.onboarding_status != OnboardingStatus.complete:
        raise _Redirect("/onboarding/status")
    return user, profile


class _Redirect(Exception):
    """Raised by require_auth_and_profile to signal a redirect."""
    def __init__(self, url):
        self.url = url
        super().__init__(url)

    def response(self):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(self.url, status_code=303)
