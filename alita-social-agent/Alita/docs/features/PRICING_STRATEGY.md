# Alita AI — Pricing Strategy & Cost Analysis

**Date:** 2026-02-22  
**Purpose:** Determine per-client costs, competitive positioning, tier structure, and payment setup.

---

## 1. YOUR ACTUAL COSTS PER CLIENT (per month)

### A. Fixed Monthly Costs (shared across ALL clients)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| **Railway Hosting** | ~$5–20 | Hobby/Pro plan; scales with traffic |
| **Late API** (social posting) | ~$33 | Flat rate, covers all clients' TikTok/LinkedIn/X/Threads/YouTube/etc. posting |
| **Resend Email** | $0–20 | Free up to 3K emails/mo, $20/mo for 50K |
| **Twilio SMS** | ~$2–5 | Only critical alerts, very few messages |
| **Domain/SSL** | ~$1–2 | Amortized |
| **TOTAL FIXED** | **~$41–80/mo** | Amortized across your client base |

**Per client fixed share:** If you have 5 clients → ~$8–16/client. At 20 clients → ~$2–4/client.

---

### B. Variable Costs Per Client (usage-based)

These are the costs that scale directly with how much each client uses the platform.

#### Text AI (Claude + OpenAI Embeddings)

| Activity | Calls/mo (typical) | Model | Cost/call | Monthly Cost |
|----------|-------------------|-------|-----------|-------------|
| Content creation (captions) | 30 posts | Haiku | ~$0.005 | $0.15 |
| DM/Comment engagement | 100 interactions | Haiku | ~$0.003 | $0.30 |
| Calendar recommendations | 4 sessions | Sonnet | ~$0.05 | $0.20 |
| Email drafting (support) | 20 emails | Sonnet | ~$0.04 | $0.80 |
| Email campaigns | 4 campaigns | Sonnet | ~$0.06 | $0.24 |
| Growth strategy | 2 sessions | Sonnet | ~$0.08 | $0.16 |
| Alita Assistant chat | 30 chats | Haiku | ~$0.003 | $0.09 |
| Auto topic generation | 15 auto-creates | Haiku | ~$0.003 | $0.05 |
| RAG embeddings | 200 queries | Ada-002 | ~$0.0001 | $0.02 |
| Style learning | 1 (onboarding) | Haiku | ~$0.01 | $0.01 |
| **TEXT AI SUBTOTAL** | | | | **~$2.02** |

#### Image Generation

| Tier | Images/mo | Cost/image | Monthly Cost |
|------|----------|-----------|-------------|
| Budget (DALL-E 3) | 10 | $0.04 | $0.40 |
| Standard (Flux) | 10 | $0.055 | $0.55 |
| Premium (Midjourney/GoAPI) | 5 | $0.08 | $0.40 |
| Text/Flyer (Ideogram) | 5 | $0.02 | $0.10 |
| Style extraction (GPT-4o-mini) | 10 | $0.01 | $0.10 |
| **IMAGE SUBTOTAL** | **40 images** | | **~$1.55** |

#### Faceless Video Generation (THE BIG COST DRIVER)

| Component | Per Video | Videos/mo | Monthly Cost |
|-----------|----------|----------|-------------|
| Script (Claude Sonnet) | ~$0.08 | varies | varies |
| Voiceover (ElevenLabs) | ~$0.10 | varies | varies |
| Stock footage (Pexels/Pixabay) | FREE | varies | $0 |
| Images - Budget (DALL-E 3) | $0.04×5 scenes | varies | varies |
| Images - Standard (Flux) | $0.055×5 scenes | varies | varies |
| Images - Premium (Midjourney) | $0.08×5 scenes | varies | varies |
| AI Animation (fal.ai Kling) | $0.35×3 clips | varies | varies |
| Smart keywords (Haiku) | ~$0.003 | varies | varies |

**Cost per faceless video by quality:**

| Quality | Cost Per Video | 5 videos/mo | 10 videos/mo | 20 videos/mo |
|---------|---------------|-------------|-------------|-------------|
| **Tier 1** (stock footage only) | ~$0.19 | $0.95 | $1.90 | $3.80 |
| **Tier 2** (AI images, standard) | ~$0.47 | $2.35 | $4.70 | $9.40 |
| **Tier 3** (AI images + animation) | ~$1.72 | $8.60 | $17.20 | $34.40 |
| **Tier 3 Premium** (Midjourney + animation) | ~$2.00 | $10.00 | $20.00 | $40.00 |

#### Other Variable Costs

| Service | Usage/mo | Cost/unit | Monthly Cost |
|---------|---------|-----------|-------------|
| Competitive research (Tavily) | 5 searches | ~$0.01 | $0.05 |
| Deep research (Gemini) | 2 sessions | ~$0.02 | $0.04 |
| ImgBB image hosting | 30 uploads | FREE | $0.00 |
| Social posting (Late API) | 60 posts | included in flat | $0.00 |
| IG/FB posting (Meta API) | 30 posts | FREE | $0.00 |

---

### C. TOTAL COST PER CLIENT (SUMMARY)

| Client Profile | Text AI | Images | Faceless Videos | Fixed Share (10 clients) | **TOTAL** |
|----------------|---------|--------|----------------|------------------------|-----------|
| **Light** (small biz, text-only posts) | $1.50 | $0.60 | $0 | $5 | **~$7/mo** |
| **Standard** (regular posting + images) | $2.00 | $1.55 | $0 | $5 | **~$9/mo** |
| **Active** (daily posts + some video) | $3.00 | $2.50 | $2.35 (5 Tier 2) | $5 | **~$13/mo** |
| **Heavy** (daily posts + heavy video) | $4.00 | $3.00 | $17.20 (10 Tier 3) | $5 | **~$29/mo** |
| **Power** (max everything + premium video) | $6.00 | $5.00 | $40.00 (20 Tier 3 Premium) | $5 | **~$56/mo** |

---

## 2. COMPETITIVE LANDSCAPE

### What Competitors Charge (monthly, SaaS tools only — no human services)

| Tool | Cheapest Plan | Mid Plan | Premium Plan | AI Content? | AI Images? | AI Video? |
|------|-------------|----------|-------------|-------------|-----------|-----------|
| **Hootsuite** | $199/mo | $399/mo | Enterprise custom | Caption AI only | No (Canva link) | No |
| **Sprout Social** | $199/mo | $299/mo | $399/mo | Basic AI | No | No |
| **Buffer** | Free / $20/mo | $40/mo | — | AI Assistant | No | No |
| **SocialPilot** | $25/mo | $42/mo | $85–170/mo | 500–5000 AI credits | No | No |
| **Loomly** | ~$30/mo | ~$60/mo | Enterprise | AI captions | No | No |
| **Predis.ai** | $19/mo | $40/mo | $212/mo | Full AI content | AI images | AI video |
| **Later** | $25/mo | $45/mo | $80/mo | AI captions | No | No |

### Key Insight: Your Platform Is WILDLY Different

**None of the $25–50/mo tools offer what you do.** They're scheduling tools with light AI captions. Your platform provides:

1. **AI-powered content creation** (full captions, SEO, hashtags — not just "rewrite this")
2. **AI image generation** (DALL-E, Flux, Midjourney, Ideogram — 4 engines)
3. **AI faceless video creation** (scripting + voiceover + stock/AI footage + animation)
4. **Digital clone** (learns the client's voice/style from their messages)
5. **Auto DM/comment engagement** (AI responds in the client's voice)
6. **Email support agent** (reads, categorizes, drafts replies)
7. **Email marketing campaigns** (AI-written, sent via Resend)
8. **Multi-platform posting** (IG, FB, TikTok, X, LinkedIn, Threads, YouTube, etc.)
9. **AI calendar agent** (optimal scheduling, auto-generate topics)
10. **Competitive intelligence** (Tavily + NewsAPI + YouTube trending)
11. **Growth hacking strategies** (AI-generated platform-specific tactics)
12. **PPC/Ads analysis**
13. **Deep research** (Gemini w/ web search)
14. **Real-time notifications** (email + SMS + in-app)
15. **Analytics dashboard**

**You are closer to an AI marketing agency than a SaaS tool.** The right comparison is:
- A human social media manager: **$1,500–5,000/mo**
- A marketing agency: **$3,000–10,000/mo**
- Done-for-you AI competitors (like Jasper + Hootsuite + Canva combined): **$300–600/mo**

---

## 3. RECOMMENDED PRICING TIERS

### The Strategy: Position as "AI Marketing Team" not "Social Media Tool"

You should NOT compete with Buffer/SocialPilot at $25–50/mo. Those are scheduling tools. You're replacing a marketing hire. Price accordingly, but be accessible enough for small businesses.

---

### TIER 1: **Starter** — $97/mo

**Target:** Solopreneurs, freelancers, side hustlers  
**Positioning:** "Your first AI marketing hire"

| Feature | Limit |
|---------|-------|
| Social accounts connected | 5 |
| AI-generated posts/mo | 30 |
| AI images/mo | 15 (Budget tier only: DALL-E) |
| Faceless videos/mo | 0 |
| Email campaigns/mo | 2 |
| Engagement replies/mo | 50 |
| Calendar recommendations | Yes |
| Competitive research | 3/mo |
| Growth strategy sessions | 1/mo |
| Platforms | IG, FB, TikTok, X, LinkedIn |
| Support | In-app chat |

**Your cost:** ~$7–9/mo → **Margin: ~90%**

---

### TIER 2: **Growth** — $197/mo ← *Most Popular*

**Target:** Small businesses, coaches, e-commerce brands  
**Positioning:** "A full marketing department in your pocket"

| Feature | Limit |
|---------|-------|
| Social accounts connected | 10 |
| AI-generated posts/mo | 90 |
| AI images/mo | 40 (Budget + Standard tiers) |
| Faceless videos/mo | 5 (Tier 1–2 quality) |
| Email campaigns/mo | 8 |
| Email support agent | Yes |
| Engagement replies/mo | 200 |
| Calendar agent (full) | Yes |
| Competitive research | 10/mo |
| Growth strategy sessions | 4/mo |
| Deep research | 2/mo |
| SMS notifications | Yes |
| All platforms | Yes |
| Support | Priority email |

**Your cost:** ~$13–18/mo → **Margin: ~90%**

---

### TIER 3: **Pro** — $397/mo

**Target:** Agencies, influencers, multi-location brands  
**Positioning:** "Replace your $3K/mo marketing agency"

| Feature | Limit |
|---------|-------|
| Social accounts connected | 25 |
| AI-generated posts/mo | Unlimited |
| AI images/mo | 100 (All tiers including Premium/Midjourney) |
| Faceless videos/mo | 15 (All tiers including Tier 3 animation) |
| Email campaigns/mo | Unlimited |
| Email support agent | Yes |
| Engagement replies/mo | Unlimited |
| Calendar agent (full) | Yes |
| Competitive research | Unlimited |
| Growth strategy sessions | Unlimited |
| Deep research | 10/mo |
| SMS + email notifications | Yes |
| All platforms | Yes |
| White-label reports | Yes |
| Support | Priority + Slack |

**Your cost:** ~$29–45/mo → **Margin: ~89%**

---

### TIER 4: **Agency** — $697/mo (or custom)

**Target:** Marketing agencies managing multiple client brands  
**Positioning:** "Scale your agency with AI"

| Feature | Limit |
|---------|-------|
| Client brands managed | Up to 10 |
| Social accounts | 50+ |
| Everything in Pro | Unlimited |
| Faceless videos/mo | 40 (All tiers) |
| API access | Yes |
| Custom onboarding | Yes |
| Dedicated support | Yes |

**Your cost:** ~$56–80/mo (total for all 10 sub-clients) → **Margin: ~88%**

---

### ADD-ONS (for clients who need more of specific features)

| Add-On | Price | Your Cost | Margin |
|--------|-------|-----------|--------|
| +10 Faceless Videos (Tier 2) | $29/mo | ~$4.70 | 84% |
| +10 Faceless Videos (Tier 3 w/ animation) | $49/mo | ~$17.20 | 65% |
| +50 Premium AI Images (Midjourney) | $19/mo | ~$4.00 | 79% |
| +5 Extra Email Campaigns | $15/mo | ~$0.50 | 97% |
| +1 Extra Client Brand (Agency) | $49/mo | ~$5–8 | 85% |

This is key for handling the "clients who want more videos" problem — they buy add-on packs instead of you eating the cost.

---

## 4. PAYMENT SETUP RECOMMENDATION

### Payment Processor: **Stripe**

**Why Stripe:**
- Industry standard for SaaS billing
- Handles subscriptions, recurring billing, plan upgrades/downgrades
- Built-in customer portal (clients manage their own payment method)
- Supports add-ons and metered billing
- 2.9% + $0.30 per transaction
- Works with your existing Railway deployment
- Has a Python SDK (`stripe` library)

### Implementation Plan

```
1. Stripe Subscription Products (create in Stripe Dashboard):
   - prod_starter  → $97/mo
   - prod_growth   → $197/mo
   - prod_pro      → $397/mo
   - prod_agency   → $697/mo
   
2. Stripe Add-On Products:
   - prod_addon_videos_t2  → $29/mo
   - prod_addon_videos_t3  → $49/mo
   - prod_addon_images     → $19/mo
   - prod_addon_campaigns  → $15/mo
   - prod_addon_brand      → $49/mo

3. Annual billing discount: 
   - Offer 2 months free (17% off) for annual plans
   - $97/mo → $970/yr ($81/mo effective)
   - $197/mo → $1,970/yr ($164/mo effective)
   - $397/mo → $3,970/yr ($331/mo effective)

4. Free trial:
   - 14-day free trial on Growth plan
   - No credit card required to start
   - Convert to paid at trial end
```

### Stripe Integration Architecture

```
Client signs up → Free trial (14 days)
                → Stripe Checkout Session
                → Subscription created
                → Webhook updates client_profile.plan_tier
                → Usage tracking middleware checks limits
                → Overage → prompt to upgrade or buy add-on
```

### What You Need to Build

1. **Usage tracking middleware** — count AI calls per client per month
2. **Plan enforcement** — check limits before allowing actions
3. **Stripe webhook handler** — update client plan status on payment events
4. **Billing page in portal** — show current plan, usage, upgrade button
5. **Stripe Customer Portal link** — let clients update payment method

---

## 5. ANNUAL REVENUE PROJECTIONS

| Scenario | Clients | Avg Revenue/Client | Monthly Revenue | Annual Revenue | Your Monthly Costs | Monthly Profit |
|----------|---------|-------------------|----------------|---------------|-------------------|----------------|
| **Early Stage** | 5 | $150 | $750 | $9,000 | ~$115 | **$635** |
| **Growing** | 15 | $200 | $3,000 | $36,000 | ~$280 | **$2,720** |
| **Established** | 50 | $250 | $12,500 | $150,000 | ~$750 | **$11,750** |
| **Scaling** | 100 | $275 | $27,500 | $330,000 | ~$1,400 | **$26,100** |

The margins are extraordinary because AI API costs are measured in pennies while the *value* delivered is thousands of dollars of marketing work.

---

## 6. PRICING PSYCHOLOGY & LAUNCH STRATEGY

### Launch Pricing (First 3 Months)

Offer "Founding Member" pricing to get initial traction:

| Tier | Normal | Founding (locked in) | Savings |
|------|--------|---------------------|---------|
| Starter | $97 | $67/mo | 31% off, forever |
| Growth | $197 | $147/mo | 25% off, forever |
| Pro | $397 | $297/mo | 25% off, forever |

**Why:** Your first 10–20 clients are also your beta testers. Give them a deal they can't refuse, lock them in, and use their feedback + testimonials to sell at full price.

### Pricing Page Best Practices

1. **Anchor high** — show Agency tier first or show "comparable agency cost: $5,000/mo"
2. **Highlight Growth as "Most Popular"** — that's your bread-and-butter
3. **Show savings calculator** — "You're paying $X/mo to replace a $4,000/mo marketing hire"
4. **Annual toggle** — default to annual with "save 17%"
5. **Social proof** — testimonials under pricing table

---

## 7. QUICK COMPARISON CHEAT SHEET

| What clients get with Alita | What they'd pay otherwise |
|-----------------------------|--------------------------|
| 90 AI posts/mo across all platforms | Social media manager: $2,000–4,000/mo |
| 40 AI-generated images/mo | Designer on Fiverr: $500–1,000/mo |
| 5 faceless videos/mo | Video editor: $1,000–2,500/mo |
| AI engagement (DMs + comments) | VA for engagement: $500–1,500/mo |
| Email marketing campaigns | Mailchimp + copywriter: $300–800/mo |
| Competitive intelligence | Market research: $500–2,000/mo |
| Growth strategy | Marketing consultant: $1,000–3,000/mo |
| **TOTAL EQUIVALENT** | **$5,800–14,800/mo** |
| **Alita Growth Plan** | **$197/mo** |

---

## 8. IMMEDIATE NEXT STEPS

1. **Create Stripe account** → stripe.com (if you don't have one)
2. **Set up 4 subscription products** with the pricing above
3. **Build usage tracking** — add counters per client_id for images, videos, posts, etc.
4. **Build plan enforcement** — middleware that checks `client.plan_tier` vs limits
5. **Build billing page** — show plan, usage bars, upgrade CTAs
6. **Build Stripe webhook** — handle `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`
7. **Create pricing page** — public-facing page with the tier comparison
8. **Set up annual billing** — create annual price variants in Stripe

---

*This document is your complete pricing playbook. The numbers are based on actual API cost analysis of your codebase as of February 2026.*
