# AI Agent Ecosystem

A portfolio of three production-grade, autonomous AI agent systems — each targeting a distinct vertical, sharing a common architectural DNA: multi-model LLM orchestration, retrieval-augmented generation (RAG), and environment-driven configuration.

---

## Agents at a Glance

| Agent | Domain | Core Model | Entry Point |
|---|---|---|---|
| [Alita](#alita--ai-social-media--marketing-automation) | Social Media & Marketing Automation | Claude Haiku / Sonnet | `web_app.py` |
| [Chucky](#chucky--autonomous-horror-video-pipeline) | AI Content Generation (Short-Form Video) | Claude Sonnet + Gemini | `main.py` |
| [Jergen](#jergen--ai-credit-dispute-engine) | Legal Document Automation (Credit) | Claude Sonnet 4.5 | `main.py` |

---

## Alita — AI Social Media & Marketing Automation

`alita-social-agent/`

Alita is a multi-tenant SaaS platform that automates end-to-end social media and marketing operations for 10–50+ simultaneous clients. It abstracts an entire marketing team into a coordinated fleet of 18+ specialized AI agents.

### Capabilities

- **Multi-Platform Content Engine** — Generates platform-native posts across Instagram, Facebook, TikTok, LinkedIn, Twitter/X, Threads, YouTube, Bluesky, Reddit, and Pinterest using 86 prompt templates segmented by platform × goal type (conversions, growth, engagement).
- **Faceless Video Pipeline** — 3-tier generation (stock footage → Ken Burns stills → AI animation via Kling/Wan on fal.ai) with ElevenLabs voiceover and auto-captioning.
- **AI Image Generation** — Routes requests across DALL-E 3, Flux, Midjourney (GoAPI), and Ideogram based on content type and quality requirements.
- **Engagement Automation** — DM auto-reply and comment management with 30–90s simulated human latency; conversation categorization (SALE / LEAD / COMPLAINT / SUPPORT / ESCALATION) with human escalation routing.
- **Marketing Intelligence** — Competitive research (Tavily), news aggregation (NewsAPI), YouTube trend analysis via Google Data API.
- **Email & SMS** — Outbound campaigns (Resend), inbound support parsing (Gmail IMAP), SMS alerts and OTP (Twilio).
- **Client Portal** — Multi-tenant dashboard, OAuth SSO (Google, Facebook, Microsoft), TOTP + WebAuthn passkey 2FA, Stripe billing.
- **Per-Client Voice Matching** — Each client's tone, vocabulary, and style is learned and enforced across all generated content.
- **RAG Knowledge System** — 15 agent-specific Qdrant vector knowledge bases for semantic retrieval.

### Tech Stack

| Layer | Technology |
|---|---|
| LLM | Anthropic Claude Haiku (speed), Claude Sonnet (reasoning) |
| Secondary LLM | OpenAI (DALL-E 3, fallback reasoning) |
| Vector DB | Qdrant (15 knowledge bases) |
| Relational DB | PostgreSQL via SQLAlchemy |
| Web Framework | FastAPI + Uvicorn |
| Social Publishing | Late API (10 platforms) |
| Media Generation | ElevenLabs, fal.ai (Kling, Flux), GoAPI (Midjourney), Ideogram |
| Email | Resend, Gmail API |
| SMS | Twilio |
| Payments | Stripe |
| Auth | python-jose, passlib, pyotp, WebAuthn |

---

## Chucky — Autonomous Horror Video Pipeline

`chucky-persona-bot/`

Chucky is a fully autonomous 7-agent pipeline that transforms a paranormal topic into a published 60-second horror short — research, script, visuals, narration, captions, SEO metadata, and multi-platform upload — with zero human intervention required.

### Pipeline Architecture

```
[Agent 0: Brainstormer] → Selects fresh paranormal topic (prevents repeats via used_topics.json)
        ↓
[Agent 1: Researcher]   → Google Gemini deep-research on case facts (structured JSON output)
        ↓
[Agent 2: Writer]       → Claude narration script (<60s "Department of Unknown" voice)
        ↓
[Agent 3: Director]     → Visual storyboard + Flux image prompts; auto-selects art style
        ↓
[Agent 4: Integrator]   → ElevenLabs TTS narration + Fal-Kling image-to-video synthesis
        ↓
[Agent 4.5: Captioner]  → OpenAI Whisper transcription → word-level grouped captions
        ↓
[Agent 5: SEO]          → Platform-specific titles, descriptions, tags, hashtags
        ↓
[Agent 6: Composer]     → Remotion video render config + CLI trigger
        ↓
[Agent 7: Publisher]    → Zernio API → TikTok, YouTube, Instagram, Facebook, X
```

### Tech Stack

| Layer | Technology |
|---|---|
| Orchestration / Scripting | Anthropic Claude Sonnet |
| Research | Google Gemini |
| Text-to-Speech | ElevenLabs |
| Image Generation | fal.ai Flux (dark comic & vintage illustration styles) |
| Video Synthesis | fal.ai Kling (image-to-video motion) |
| Transcription / Captions | OpenAI Whisper |
| Video Composition | Remotion (Node.js) |
| Publishing | Zernio API |

---

## Jergen — AI Credit Dispute Engine

`jergen-credit-ai/`

Jergen automates the generation of FCRA-compliant credit dispute letters. Given raw credit report PDFs from one or all three major bureaus (Experian, Equifax, TransUnion), it runs a 4-stage agentic pipeline that extracts structured data, evaluates disputable items against federal statute, validates against frivolous-dispute guardrails, and drafts professionally formatted DOCX + PDF letters — each backed by an immutable SHA-256 chained audit log.

### Pipeline Architecture

```
[Stage 1: DataExtraction_Agent] → pdfplumber + Claude → PersonalInfo, CreditAccounts,
                                   HardInquiries, PublicRecords (structured JSON per bureau)
        ↓
[Stage 2: Evaluation_Agent]     → FCRA §1681b / §1681i / §1681c rule engine
                                   5-tier creditor matching (exact → abbrev → Jaro-Winkler
                                   ≥0.92 → LLM disambiguation → no-match)
                                   SHA-256 chained audit log (JSONL)
        ↓
[Stage 3: Validation_Agent]     → Guardrail QA: catches frivolous / irrelevant disputes
                                   Hard stops (halt pipeline) vs. soft warnings
        ↓
[Stage 4: Drafting_Agent]       → RAG-augmented 3-pass Claude drafting
                                   (late payments → inquiries → final assembly)
                                   Output: Dispute Letters/[ClientName]/[Bureau].docx + .pdf
```

### Tech Stack

| Layer | Technology |
|---|---|
| LLM | Claude 4.5 Sonnet (`claude-sonnet-4-20250514`) |
| Vector DB | ChromaDB (local persistent, RAG over FCRA knowledge base) |
| PDF Parsing | pdfplumber |
| Document Output | python-docx + docx2pdf (Microsoft Word COM) |
| Fuzzy Matching | jellyfish (Jaro-Winkler, threshold 0.92) |
| Data Validation | pydantic v2 |
| Audit Trail | SHA-256 chained JSONL log (immutable) |

---

## Shared Architecture Patterns

All three agents are built on the same foundational patterns:

- **RAG (Retrieval-Augmented Generation)** — Each agent maintains its own domain knowledge base (Qdrant / ChromaDB) for grounded, context-aware generation rather than relying solely on LLM parametric knowledge.
- **Multi-Model Routing** — Tasks are dispatched to the most capable (or cost-efficient) model per operation rather than using a single model uniformly across all workloads.
- **Environment-Driven Configuration** — All credentials and API keys are loaded from `.env` files; no secrets are hardcoded anywhere in the codebase.
- **Modular Agent Design** — Each capability is an independent agent module with clear input/output contracts, composable into larger pipelines.

## Prompt Security Note

Production-grade prompts are intentionally abstracted from repository source files. Prompt templates in this portfolio are placeholders only; full operational prompts are stored in private infrastructure (secure environment variables and/or protected database records) to reduce prompt leakage risk.

---

## Repository Structure

```
AI-Portfolio/
├── .gitignore                        # Root secret & artifact exclusions
├── README.md                         # This file
├── requirements.txt                  # Combined dependency reference
│
├── alita-social-agent/
│   └── Alita/
│       ├── web_app.py                # FastAPI entry point
│       ├── agents/                   # 18+ specialized agent modules
│       ├── Agent RAGs/               # 15 per-agent knowledge bases
│       ├── requirements.txt          # Alita-specific dependencies
│       └── .env                      # ← NOT committed (see .gitignore)
│
├── chucky-persona-bot/
│   └── Chucky AI/
│       ├── main.py                   # CLI pipeline runner
│       ├── app.py                    # Streamlit web UI
│       ├── agents/                   # 7 pipeline agents + 2 image generators
│       ├── Agent RAGs/               # 4 research / style knowledge bases
│       ├── requirements.txt          # Chucky-specific dependencies
│       └── .env                      # ← NOT committed (see .gitignore)
│
└── jergen-credit-ai/
    └── Jergen AI/
        ├── main.py                   # CLI entry point
        ├── config.py                 # Model, token, and path configuration
        ├── agents/                   # 4-stage pipeline agents
        ├── Agent RAGs/               # FCRA knowledge base documents
        ├── chroma_db/                # ← NOT committed (locally generated)
        ├── audit_logs/               # ← NOT committed (client PII audit chain)
        ├── requirements.txt          # Jergen-specific dependencies
        └── .env                      # ← NOT committed (see .gitignore)
```

---

## Environment Setup

Each agent runs in its own virtual environment and reads from its own `.env` file. The root `requirements.txt` is a combined reference — install from each sub-project's own file.

```bash
# Alita
cd alita-social-agent/Alita
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt

# Chucky
cd chucky-persona-bot/"Chucky AI"
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Jergen
cd jergen-credit-ai/"Jergen AI"
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the `.env.example` from each sub-project (if provided) and populate with your API keys before running.

---

## License

See individual `LICENSE` files within each sub-project directory.
