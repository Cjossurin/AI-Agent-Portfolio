# api/alita_assistant_routes.py
"""
Alita Assistant Chat Routes
============================
  GET  /alita/chat             -> Full-page standalone chat
  POST /api/alita/chat         -> Send message, get reply (JSON)
  GET  /api/alita/history      -> Get conversation history (JSON)
  POST /api/alita/clear        -> Clear conversation history
  GET  /api/alita/insights     -> Proactive insight cards for current page (JSON)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import StreamingResponse
from utils.shared_layout import build_page

router = APIRouter()


def _get_user_and_profile(request: Request):
    """Returns (user, profile) or (None, None). Never raises."""
    try:
        from database.db import get_db
        from api.auth_routes import get_current_user
        from database.models import ClientProfile
        db = next(get_db())
        try:
            user = get_current_user(request, db)
            if not user:
                return None, None, db
            profile = db.query(ClientProfile).filter(
                ClientProfile.user_id == user.id
            ).first()
            return user, profile, db
        except Exception:
            return None, None, db
    except Exception:
        return None, None, None


# ─── POST /api/alita/chat ─────────────────────────────────────────────────────

@router.post("/api/alita/chat")
async def alita_chat(request: Request):
    user, profile, db = _get_user_and_profile(request)
    if db:
        try:
            db.close()
        except Exception:
            pass

    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    if len(message) > 2000:
        return JSONResponse({"error": "Message too long (max 2000 chars)"}, status_code=400)

    # ── Super-duty guardrails ──────────────────────────────────────────────
    from utils.guardrails import validate_message_quick, check_rate_limit

    # Rate limit check (per-user sliding window)
    rate_ok, rate_msg = check_rate_limit(str(user.id))
    if not rate_ok:
        return JSONResponse({"error": rate_msg, "blocked": True}, status_code=429)

    # Content guardrails (banned patterns, profanity, jailbreak, gibberish, etc.)
    guard_ok, guard_msg = validate_message_quick(message)
    if not guard_ok:
        return JSONResponse({"error": guard_msg, "blocked": True}, status_code=400)
    # ── End guardrails ─────────────────────────────────────────────────────

    from agents.alita_assistant import chat
    business_name = (profile.business_name if profile else None) or "your business"
    client_id = (profile.client_id if profile else None) or user.id

    result = chat(
        user_id=user.id,
        message=message,
        business_name=business_name,
        client_id=client_id,
        profile=profile,
        tier=getattr(profile, "plan_tier", "pro") or "pro",
    )

    resp = {
        "reply": result["reply"],
        "project_interest_detected": result["project_interest_detected"],
        "history_length": result["history_length"],
    }
    if result.get("action"):
        resp["action"] = result["action"]
    if result.get("limit_error"):
        resp["limit_error"] = result["limit_error"]
    if result.get("navigate_url"):
        resp["navigate_url"] = result["navigate_url"]
    if result.get("setting_result"):
        resp["setting_result"] = result["setting_result"]
    return JSONResponse(resp)


# ─── POST /api/alita/execute (SSE streaming) ──────────────────────────────────

@router.post("/api/alita/execute")
async def alita_execute(request: Request):
    """Execute a confirmed pending action, streaming SSE progress events."""
    user, profile, db = _get_user_and_profile(request)
    if not user:
        if db:
            try: db.close()
            except Exception: pass
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        if db:
            try: db.close()
            except Exception: pass
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    action_id = (body.get("action_id") or "").strip()
    if not action_id:
        if db:
            try: db.close()
            except Exception: pass
        return JSONResponse({"error": "Missing action_id"}, status_code=400)

    from agents.alita_action_router import pop_pending
    action = pop_pending(action_id, user_id=str(user.id))
    if not action:
        if db:
            try: db.close()
            except Exception: pass
        return JSONResponse({"error": "Action expired or not found"}, status_code=404)

    # ── Re-check plan limits at execution time (closes TOCTOU gap) ────────
    from agents.alita_action_router import check_action_allowed
    if profile:
        allowed, limit_msg = check_action_allowed(profile, action["tool"])
        if not allowed:
            if db:
                try: db.close()
                except Exception: pass
            return JSONResponse({"error": limit_msg, "limit_error": True}, status_code=403)

    import json, asyncio
    from agents.alita_action_router import execute_action
    from utils.guardrails import sanitize_error

    async def event_stream():
        nonlocal db
        try:
            async for event in execute_action(
                tool_name=action["tool"],
                params=action["optimized_params"],
                client_id=action["client_id"],
                profile=profile,
                db=db,
            ):
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)  # yield control
        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'status': 'error', 'message': sanitize_error(exc)})}\n\n"
        finally:
            if db:
                try: db.close()
                except Exception: pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── POST /api/alita/cancel ────────────────────────────────────────────────────

@router.post("/api/alita/cancel")
async def alita_cancel(request: Request):
    """Cancel a pending action before execution."""
    user, profile, db = _get_user_and_profile(request)
    if db:
        try: db.close()
        except Exception: pass
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    action_id = (body.get("action_id") or "").strip()
    if not action_id:
        return JSONResponse({"error": "Missing action_id"}, status_code=400)

    from agents.alita_action_router import cancel_pending
    ok = cancel_pending(action_id, user_id=str(user.id))
    return JSONResponse({"ok": ok})


# ─── GET /api/alita/history ───────────────────────────────────────────────────

@router.get("/api/alita/history")
async def alita_history(request: Request):
    user, profile, db = _get_user_and_profile(request)
    if db:
        try:
            db.close()
        except Exception:
            pass

    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from agents.alita_assistant import get_history
    history = get_history(user.id)
    return JSONResponse({"history": history})


# ─── GET /api/alita/insights ──────────────────────────────────────────────────

@router.get("/api/alita/insights")
async def alita_insights(request: Request):
    """Return proactive insight cards for the given page context."""
    user, profile, db = _get_user_and_profile(request)
    # keep db open — gatherers open their own sessions
    if db:
        try:
            db.close()
        except Exception:
            pass

    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    page = (request.query_params.get("page") or "dashboard").strip().lower()
    force = request.query_params.get("force", "0") == "1"

    from agents.alita_insights import generate_insights
    import concurrent.futures

    business_name = (profile.business_name if profile else None) or "your business"
    client_id = (profile.client_id if profile else None) or str(user.id)

    # Run insight generation in a thread to avoid blocking the event loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        cards = await request.app.state._loop_ref if hasattr(request.app.state, "_loop_ref") else None  # noqa
        import asyncio
        loop = asyncio.get_event_loop()
        cards = await loop.run_in_executor(
            pool,
            lambda: generate_insights(
                client_id=client_id,
                page=page,
                profile=profile,
                business_name=business_name,
                force=force,
            ),
        )

    return JSONResponse({"cards": cards, "page": page})


# ─── POST /api/alita/clear ────────────────────────────────────────────────────

@router.post("/api/alita/clear")
async def alita_clear(request: Request):
    user, profile, db = _get_user_and_profile(request)
    if db:
        try:
            db.close()
        except Exception:
            pass

    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from agents.alita_assistant import clear_history
    clear_history(user.id)
    return JSONResponse({"status": "cleared"})


# ─── GET /alita/chat (full-page standalone) ───────────────────────────────────

@router.get("/alita/chat", response_class=HTMLResponse)
async def alita_chat_page(request: Request):
    from fastapi.responses import RedirectResponse
    user, profile, db = _get_user_and_profile(request)
    if db:
        try:
            db.close()
        except Exception:
            pass

    if not user:
        return RedirectResponse("/account/login", status_code=303)

    business_name = (profile.business_name if profile else "") or ""

    body = """
  <div style="max-width:760px;margin:0 auto;padding:0 0 40px">
    <div class="chat-shell">

      <!-- Header -->
      <div class="chat-header">
        <div class="chat-avatar-ring">
          <div class="chat-avatar">🤖</div>
        </div>
        <div style="flex:1">
          <div style="font-weight:800;font-size:1.05rem;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.15)">Alita AI</div>
          <div class="chat-status"><span class="status-dot"></span> Online &mdash; Ready to help</div>
        </div>
        <button onclick="clearChat()" class="clear-btn">Clear chat</button>
      </div>

      <!-- Messages -->
      <div id="chat-messages" class="chat-messages">
        <div class="msg-alita msg-enter">
          <div class="mini-avatar">🤖</div>
          <div>
            <div class="msg-bubble alita-bubble">
              Hi! I'm <strong>Alita</strong> 👋<br>
              I'm your AI marketing assistant. Ask me anything about growing your business, creating content, or what NexarilyAI can build for you!
            </div>
            <div class="chip-row" id="suggestion-chips">
              <button class="suggestion-chip" onclick="chipSend(this)">✍️ Create a post</button>
              <button class="suggestion-chip" onclick="chipSend(this)">🎨 Generate an image</button>
              <button class="suggestion-chip" onclick="chipSend(this)">📊 Show my analytics</button>
              <button class="suggestion-chip" onclick="chipSend(this)">💡 Content ideas</button>
              <button class="suggestion-chip" onclick="chipSend(this)">📅 Plan my calendar</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="chat-input-area">
        <div style="display:flex;gap:10px;align-items:flex-end">
          <textarea
            id="chat-input"
            placeholder="Ask me anything..."
            rows="1"
            class="chat-textarea"
            onkeydown="handleKey(event)"
            oninput="autoResize(this)"
          ></textarea>
          <button id="send-btn" onclick="sendMessage()" class="send-btn">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </button>
        </div>
        <div style="font-size:.72rem;color:#90949c;margin-top:8px;text-align:center">
          Press <kbd style='background:#e4e6eb;padding:1px 5px;border-radius:4px;font-size:.7rem'>Enter</kbd> to send &middot; <kbd style='background:#e4e6eb;padding:1px 5px;border-radius:4px;font-size:.7rem'>Shift+Enter</kbd> for new line
        </div>
      </div>
    </div>
  </div>
"""

    css = """
    /* ── Chat shell ───────────────────────────── */
    .chat-shell{background:#fff;border-radius:18px;box-shadow:0 4px 24px rgba(92,106,196,.12),0 1px 4px rgba(0,0,0,.06);overflow:hidden;height:calc(100vh - 140px);display:flex;flex-direction:column}

    /* ── Animated gradient header ─────────────── */
    .chat-header{padding:18px 24px;display:flex;align-items:center;gap:14px;flex-shrink:0;background:linear-gradient(135deg,#5c6ac4 0%,#764ba2 50%,#5c6ac4 100%);background-size:200% 200%;animation:headerShift 6s ease infinite;position:relative}
    .chat-header::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(255,255,255,.06) 0%,transparent 100%);pointer-events:none}
    @keyframes headerShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}

    .chat-avatar-ring{width:48px;height:48px;border-radius:50%;padding:2px;background:rgba(255,255,255,.25);flex-shrink:0;animation:avatarPulse 3s ease-in-out infinite}
    .chat-avatar{width:100%;height:100%;border-radius:50%;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;font-size:1.5rem}
    @keyframes avatarPulse{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,.3)}50%{box-shadow:0 0 0 8px rgba(255,255,255,0)}}

    .chat-status{font-size:.78rem;color:rgba(255,255,255,.88);font-weight:600;display:flex;align-items:center;gap:6px}
    .status-dot{width:8px;height:8px;border-radius:50%;background:#4ade80;display:inline-block;animation:dotPulse 2s ease-in-out infinite}
    @keyframes dotPulse{0%,100%{box-shadow:0 0 0 0 rgba(74,222,128,.5)}50%{box-shadow:0 0 0 5px rgba(74,222,128,0)}}

    .clear-btn{background:rgba(255,255,255,.18);backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.2);padding:7px 14px;border-radius:8px;font-size:.8rem;font-weight:600;color:#fff;cursor:pointer;transition:all .2s}
    .clear-btn:hover{background:rgba(255,255,255,.3)}

    /* ── Messages area ────────────────────────── */
    .chat-messages{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:14px;scroll-behavior:smooth;background:linear-gradient(180deg,#fafbff 0%,#f5f6fa 100%)}

    .msg-alita { display:flex; gap:10px; align-items:flex-start; }
    .msg-user  { display:flex; gap:10px; align-items:flex-start; justify-content:flex-end; }
    .msg-bubble{ max-width:72%; padding:12px 16px; border-radius:16px; font-size:.88rem; line-height:1.6; word-break:break-word; }
    .alita-bubble{ background:#fff; color:#1c1e21; border-radius:4px 16px 16px 16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
    .user-bubble { background:linear-gradient(135deg,#5c6ac4,#764ba2); color:#fff; border-radius:16px 4px 16px 16px; box-shadow:0 2px 8px rgba(92,106,196,.25); }

    .mini-avatar{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#5c6ac4,#764ba2);display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0;box-shadow:0 2px 6px rgba(92,106,196,.2)}

    /* Entrance animation */
    .msg-enter{animation:msgSlideIn .35s cubic-bezier(.22,1,.36,1) both}
    @keyframes msgSlideIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}

    /* Timestamp */
    .msg-time{font-size:.7rem;color:#90949c;margin-top:4px;padding:0 4px}
    .msg-user .msg-time{text-align:right}

    /* ── Suggestion chips ─────────────────────── */
    .chip-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;padding-left:2px}
    .suggestion-chip{background:#fff;border:1.5px solid #d4cef0;color:#5c6ac4;padding:7px 14px;border-radius:99px;font-size:.8rem;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap}
    .suggestion-chip:hover{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border-color:transparent;transform:translateY(-1px);box-shadow:0 3px 10px rgba(92,106,196,.25)}
    .suggestion-chip:active{transform:translateY(0)}

    /* ── Typing indicator ─────────────────────── */
    .typing-dot{ display:inline-block; width:7px; height:7px; border-radius:50%; background:#90949c; margin:0 2px; animation:bounce .9s infinite; }
    .typing-dot:nth-child(2){animation-delay:.15s}
    .typing-dot:nth-child(3){animation-delay:.3s}
    @keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}
    .typing-shimmer{position:relative;overflow:hidden}
    .typing-shimmer::after{content:'';position:absolute;top:0;left:-100%;width:200%;height:100%;background:linear-gradient(90deg,transparent 25%,rgba(92,106,196,.06) 50%,transparent 75%);animation:shimmerSlide 1.5s ease infinite}
    @keyframes shimmerSlide{to{transform:translateX(50%)}}

    /* ── Input area ───────────────────────────── */
    .chat-input-area{padding:16px 24px;border-top:1px solid #e4e6eb;flex-shrink:0;background:#fff}
    .chat-textarea{flex:1;border:1.5px solid #dde0e4;border-radius:12px;padding:10px 14px;font-size:.9rem;font-family:inherit;resize:none;outline:none;line-height:1.5;max-height:120px;overflow-y:auto;transition:all .2s}
    .chat-textarea:focus{border-color:#5c6ac4;box-shadow:0 0 0 3px rgba(92,106,196,.12)}
    .send-btn{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff;border:none;width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .2s;flex-shrink:0}
    .send-btn:hover{transform:scale(1.05);box-shadow:0 4px 12px rgba(92,106,196,.35)}
    .send-btn:active{transform:scale(.97)}
    .send-btn:disabled{opacity:.5;cursor:default;transform:none;box-shadow:none}

    /* ── Action card ──────────────────────────── */
    .action-card{background:#f8f6ff;border:1px solid #d4cef0;border-left:4px solid #5c6ac4;border-radius:12px;padding:16px 18px;max-width:70%;margin:4px 0;animation:msgSlideIn .35s cubic-bezier(.22,1,.36,1) both}
    .action-card .ac-hdr{font-weight:700;font-size:.92rem;color:#3d2b8c;margin-bottom:10px}
    .action-card .ac-row{font-size:.82rem;color:#444;padding:3px 0}
    .action-card .ac-row b{color:#1c1e21}
    .action-card .ac-opt{font-size:.78rem;color:#5c6ac4;font-style:italic;padding:2px 0}
    .action-card .ac-btns{display:flex;gap:8px;margin-top:12px}
    .action-card .ac-btn{padding:8px 18px;border-radius:8px;font-weight:700;font-size:.82rem;border:none;cursor:pointer;transition:all .2s}
    .action-card .ac-btn-go{background:linear-gradient(135deg,#5c6ac4,#764ba2);color:#fff}
    .action-card .ac-btn-go:hover{transform:translateY(-1px);box-shadow:0 3px 10px rgba(92,106,196,.25)}
    .action-card .ac-btn-cancel{background:#f0f2f5;color:#606770}
    .action-card .ac-btn-cancel:hover{background:#e4e6eb}

    /* ── Progress card ────────────────────────── */
    .progress-card{background:#fff;border:1px solid #e4e6eb;border-left:4px solid #5c6ac4;border-radius:10px;padding:12px 16px;max-width:70%;margin:4px 0;display:flex;align-items:center;gap:10px;animation:msgSlideIn .35s both}
    .progress-card .pc-spin{width:20px;height:20px;border:2px solid #d4cef0;border-top-color:#5c6ac4;border-radius:50%;animation:pcSpin .7s linear infinite}
    @keyframes pcSpin{to{transform:rotate(360deg)}}
    .progress-card .pc-msg{font-size:.82rem;color:#444}

    /* ── Result card ──────────────────────────── */
    .result-card{background:#f0faf0;border:1px solid #c6e6c6;border-left:4px solid #2e7d32;border-radius:12px;padding:14px 18px;max-width:75%;margin:4px 0;animation:msgSlideIn .35s both}
    .result-card.result-error{background:#fff5f5;border-color:#e6c6c6;border-left-color:#c62828}
    .result-card .rc-hdr{font-weight:700;font-size:.88rem;color:#2e7d32;margin-bottom:8px}
    .result-card.result-error .rc-hdr{color:#c62828}
    .result-card .rc-body{font-size:.84rem;color:#333;line-height:1.55}
    .result-card .rc-body img{max-width:100%;border-radius:8px;margin:8px 0}

    /* ── Scrollbar ────────────────────────────── */
    .chat-messages::-webkit-scrollbar{width:6px}
    .chat-messages::-webkit-scrollbar-track{background:transparent}
    .chat-messages::-webkit-scrollbar-thumb{background:#d4cef0;border-radius:99px}
    .chat-messages::-webkit-scrollbar-thumb:hover{background:#b0a8d8}
    """

    js = """
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function scrollToBottom() {
  const box = document.getElementById('chat-messages');
  box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
}

function _timeLabel() {
  const d = new Date();
  let h = d.getHours(), m = d.getMinutes(), ap = 'AM';
  if (h >= 12) { ap = 'PM'; if (h > 12) h -= 12; }
  if (h === 0) h = 12;
  return h + ':' + (m < 10 ? '0' : '') + m + ' ' + ap;
}

function addMessage(role, text) {
  // hide suggestion chips after first real message
  const chips = document.getElementById('suggestion-chips');
  if (chips) chips.remove();

  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = (role === 'user' ? 'msg-user' : 'msg-alita') + ' msg-enter';

  if (role === 'assistant') {
    div.innerHTML =
      '<div class="mini-avatar">🤖</div>' +
      '<div><div class="msg-bubble alita-bubble">' + formatText(text) + '</div>' +
      '<div class="msg-time">' + _timeLabel() + '</div></div>';
  } else {
    div.innerHTML =
      '<div><div class="msg-bubble user-bubble">' + escHtml(text) + '</div>' +
      '<div class="msg-time">' + _timeLabel() + '</div></div>';
  }
  box.appendChild(div);
  scrollToBottom();
}

function chipSend(btn) {
  var raw = btn.textContent.trim();
  // strip leading emoji (first 1-2 chars + space)
  var text = raw.replace(/^\\S+\\s*/, '').trim() || raw;
  var input = document.getElementById('chat-input');
  input.value = text;
  sendMessage();
}

function showTyping() {
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg-alita msg-enter';
  div.id = 'typing-indicator';
  div.innerHTML =
    '<div class="mini-avatar">🤖</div>' +
    '<div class="msg-bubble alita-bubble typing-shimmer" style="padding:14px 18px">' +
      '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>' +
    '</div>';
  box.appendChild(div);
  scrollToBottom();
}

function hideTyping() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

function escHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
}

function formatText(t) {
  t = t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  t = t.replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');
  t = t.replace(/\\n- /g,'<br>• ');
  t = t.replace(/^- /g,'• ');
  t = t.replace(/\\n/g,'<br>');
  return t;
}

/* ── Action card for confirmations ── */
function showActionCard(action) {
  const box = document.getElementById('chat-messages');
  const card = document.createElement('div');
  card.className = 'action-card';
  card.id = 'action-' + action.action_id;

  let rows = '';
  if (action.rows) {
    action.rows.forEach(function(r) { rows += '<div class="ac-row"><b>' + escHtml(r.label) + ':</b> ' + escHtml(r.value) + '</div>'; });
  }
  let opts = '';
  if (action.optimizations && action.optimizations.length) {
    action.optimizations.forEach(function(o) { opts += '<div class="ac-opt">✨ ' + escHtml(o) + '</div>'; });
  }
  card.innerHTML =
    '<div class="ac-hdr">' + (action.emoji || '🚀') + ' ' + escHtml(action.display_name || 'Action') + '</div>' +
    rows + opts +
    '<div class="ac-btns">' +
      '<button class="ac-btn ac-btn-go" onclick="executeAction(\\'' + action.action_id + '\\')">✓ Execute</button>' +
      '<button class="ac-btn ac-btn-cancel" onclick="cancelAction(\\'' + action.action_id + '\\')">Cancel</button>' +
    '</div>';
  box.appendChild(card);
  scrollToBottom();
}

function showProgress(actionId, msg) {
  let el = document.getElementById('progress-' + actionId);
  if (!el) {
    const box = document.getElementById('chat-messages');
    el = document.createElement('div');
    el.className = 'progress-card';
    el.id = 'progress-' + actionId;
    el.innerHTML = '<div class="pc-spin"></div><div class="pc-msg"></div>';
    box.appendChild(el);
    scrollToBottom();
  }
  el.querySelector('.pc-msg').textContent = msg;
  scrollToBottom();
}

function showResult(actionId, event) {
  // remove progress
  const prog = document.getElementById('progress-' + actionId);
  if (prog) prog.remove();
  // remove action card
  const ac = document.getElementById('action-' + actionId);
  if (ac) ac.remove();

  const box = document.getElementById('chat-messages');
  const card = document.createElement('div');
  const isErr = event.status === 'error';
  card.className = 'result-card' + (isErr ? ' result-error' : '');

  if (isErr) {
    card.innerHTML = '<div class="rc-hdr">❌ Error</div><div class="rc-body">' + escHtml(event.message || 'Something went wrong') + '</div>';
  } else {
    const result = event.result || {};
    const rtype = event.result_type || '';
    let body = '';
    if (rtype === 'content' || rtype === 'ideas' || rtype === 'strategy' || rtype === 'calendar') {
      body = formatText(result.content || result.ideas || result.strategy || result.calendar || JSON.stringify(result));
    } else if (rtype === 'image') {
      body = (result.image_url ? '<img src="' + result.image_url + '" />' : '') + '<div>' + escHtml(result.prompt || '') + '</div>';
    } else if (rtype === 'schedule') {
      body = '📅 ' + escHtml(result.message || 'Scheduled successfully');
    } else if (rtype === 'analytics') {
      body = formatText(result.summary || JSON.stringify(result));
    } else if (rtype === 'times') {
      body = formatText(result.times || JSON.stringify(result));
    } else {
      body = formatText(JSON.stringify(result));
    }
    card.innerHTML = '<div class="rc-hdr">✅ Done!</div><div class="rc-body">' + body + '</div>';
  }
  box.appendChild(card);
  scrollToBottom();
}

async function executeAction(actionId) {
  // disable buttons on the card
  const ac = document.getElementById('action-' + actionId);
  if (ac) { ac.querySelectorAll('button').forEach(function(b) { b.disabled = true; }); }
  showProgress(actionId, 'Starting...');
  try {
    const resp = await fetch('/api/alita/execute', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action_id: actionId}),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(function() { return {}; });
      showResult(actionId, {status: 'error', message: errData.error || 'Action failed'});
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
            if (ev.status === 'progress') showProgress(actionId, ev.message);
            else if (ev.status === 'complete') showResult(actionId, ev);
            else if (ev.status === 'error') showResult(actionId, ev);
          } catch(e) {}
        }
      });
    }
  } catch(e) {
    showResult(actionId, {status: 'error', message: 'Connection error — please try again.'});
  }
}

async function cancelAction(actionId) {
  const ac = document.getElementById('action-' + actionId);
  if (ac) ac.remove();
  try { await fetch('/api/alita/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action_id:actionId})}); } catch(e) {}
  addMessage('assistant', 'Action cancelled. What else can I help with?');
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;

  const btn = document.getElementById('send-btn');
  btn.disabled = true;
  input.value = '';
  input.style.height = 'auto';

  addMessage('user', msg);
  showTyping();

  try {
    const resp = await fetch('/api/alita/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg}),
    });
    const data = await resp.json();
    hideTyping();

    if (data.reply) {
      addMessage('assistant', data.reply);
      if (data.navigate_url) {
        setTimeout(function() { window.location.href = data.navigate_url; }, 1500);
      }
      if (data.action) {
        showActionCard(data.action);
      }
      if (data.project_interest_detected) {
        showProjectBanner();
      }
    } else {
      addMessage('assistant', 'Sorry, something went wrong. Please try again.');
    }
  } catch(e) {
    hideTyping();
    addMessage('assistant', 'Connection error — please try again.');
  }

  btn.disabled = false;
  input.focus();
}

function showProjectBanner() {
  const box = document.getElementById('chat-messages');
  const already = document.getElementById('project-banner');
  if (already) return;
  const div = document.createElement('div');
  div.id = 'project-banner';
  div.style.cssText = 'background:#ede8f5;border:1px solid #c5bce8;border-radius:10px;padding:12px 16px;font-size:.83rem;color:#3d2b8c;font-weight:600;text-align:center;margin:4px 0';
  div.innerHTML = '🔔 Your account manager has been notified and will reach out within 24 hours!';
  box.appendChild(div);
  scrollToBottom();
}

async function clearChat() {
  if (!confirm('Clear conversation history?')) return;
  await fetch('/api/alita/clear', {method:'POST'});
  const box = document.getElementById('chat-messages');
  box.innerHTML =
    '<div class="msg-alita msg-enter">' +
      '<div class="mini-avatar">🤖</div>' +
      '<div><div class="msg-bubble alita-bubble">Chat cleared! How can I help you today? 🚀</div>' +
      '<div class="chip-row" id="suggestion-chips">' +
        '<button class="suggestion-chip" onclick="chipSend(this)">✍️ Create a post</button>' +
        '<button class="suggestion-chip" onclick="chipSend(this)">🎨 Generate an image</button>' +
        '<button class="suggestion-chip" onclick="chipSend(this)">📊 Show my analytics</button>' +
        '<button class="suggestion-chip" onclick="chipSend(this)">💡 Content ideas</button>' +
        '<button class="suggestion-chip" onclick="chipSend(this)">📅 Plan my calendar</button>' +
      '</div></div>' +
    '</div>';
}
"""

    return HTMLResponse(build_page(
        title="Chat with Alita",
        active_nav="dashboard",
        body_content=body,
        extra_css=css,
        extra_js=js,
        user_name=user.full_name,
        business_name=business_name,
        topbar_title="Chat with Alita",
        show_alita_widget=False,  # full page already IS the chat — no FAB needed
    ))
