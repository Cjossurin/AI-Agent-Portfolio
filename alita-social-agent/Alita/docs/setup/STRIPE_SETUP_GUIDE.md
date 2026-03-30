# Stripe Setup Guide for Alita AI

**Status:** Your API keys are live and added to `.env` ✅  
**Next step:** Create 6 prices in Stripe Dashboard, then enable payment methods

---

## Part 1: Create the 6 Pricing Products (15 mins)

### Overview
You need to create **3 products** (Starter, Growth, Pro) with **2 prices each** (Monthly & Annual):

| Product | Monthly Price | Annual Price |
|---------|---------------|--------------|
| Starter | $97/mo | $936/year |
| Growth | $197/mo | $1,896/year |
| Pro | $397/mo | $3,816/year |

---

### Step-by-Step: Create First Product (Starter)

#### 1. Open Stripe Dashboard
- Go to https://dashboard.stripe.com
- Log in with your account
- You should be in **Live mode** (top-left shows "Live" toggle)

#### 2. Create the "Starter" Product
- Left menu → **Products**
- Click **+ Add product** (top right)

**Fill in:**
```
Name: Starter Plan
Description: For solopreneurs and side hustlers
Type: Service (not Physical good)
Tax code: (leave blank)
Image: (optional)
```

- Click **Create product**

#### 3. Add Monthly Price to Starter
- Product page opens → scroll to **Pricing** section
- Click **+ Add price**

**Fill in:**
```
Pricing model: Standard pricing
Price in USD: 97.00
Billing period: Monthly
Recurring

For monthly subscription:
- Leave "Usage charges" unchecked
- Tax behavior: Unspecified

Then: [Add price]
```

- **Copy the price ID** that appears (format: `price_xxx...`)
- Add to your `.env`: `STRIPE_PRICE_STARTER_MONTHLY=price_xxx...`

#### 4. Add Annual Price to Same Product
- Still in Starter product → **+ Add price** again

**Fill in:**
```
Pricing model: Standard pricing
Price in USD: 936.00
Billing period: Annual (12 months)
Recurring

For annual subscription:
- Leave "Usage charges" unchecked
- Tax behavior: Unspecified

Then: [Add price]
```

- **Copy this price ID**
- Add to `.env`: `STRIPE_PRICE_STARTER_ANNUAL=price_xxx...`

---

### Repeat for Growth Product (Same Process)

#### 1. Create Product
- Products → **+ Add product**

**Fill in:**
```
Name: Growth Plan
Description: Full marketing department in your pocket
Type: Service
```

- Click **Create product**

#### 2. Add Monthly ($197)
- **+ Add price**
- Price: `197.00`
- Billing: Monthly
- [Add price]
- **Copy ID** → `.env`: `STRIPE_PRICE_GROWTH_MONTHLY=price_xxx...`

#### 3. Add Annual ($1,896)
- **+ Add price**
- Price: `1896.00`
- Billing: Annual
- [Add price]
- **Copy ID** → `.env`: `STRIPE_PRICE_GROWTH_ANNUAL=price_xxx...`

---

### Repeat for Pro Product (Same Process)

#### 1. Create Product
- Products → **+ Add product**

**Fill in:**
```
Name: Pro Plan
Description: Replace your $3K/mo marketing agency
Type: Service
```

- Click **Create product**

#### 2. Add Monthly ($397)
- **+ Add price**
- Price: `397.00`
- Billing: Monthly
- [Add price]
- **Copy ID** → `.env`: `STRIPE_PRICE_PRO_MONTHLY=price_xxx...`

#### 3. Add Annual ($3,816)
- **+ Add price**
- Price: `3816.00`
- Billing: Annual
- [Add price]
- **Copy ID** → `.env`: `STRIPE_PRICE_PRO_ANNUAL=price_xxx...`

---

## Part 2: Enable PayPal + Google Pay (2 mins)

Once all 6 prices are created, enable payment methods:

#### 1. Open Settings
- Stripe Dashboard → Left menu → **Settings** (gear icon, bottom)
- Click **Payment methods**

#### 2. Enable Each Payment Method

**PayPal:**
- Find "PayPal" in the list
- Toggle to **Enabled** ✅
- (Optional) Set a preferred position (PayPal usually shows first)

**Google Pay:**
- Find "Google Pay" in the list
- Toggle to **Enabled** ✅

**Apple Pay (bonus):**
- Find "Apple Pay" in the list
- Toggle to **Enabled** ✅

**Save** (if there's a save button)

---

## Part 3: Set Up Webhooks (5 mins)

Your app needs to listen for Stripe events (payments received, subscriptions canceled, etc.)

#### 1. Open Webhooks
- Stripe Dashboard → Left menu → **Developers**
- Click **Webhooks** (left submenu)
- Click **+ Add endpoint** (top right)

#### 2. Configure Webhook
**Fill in:**
```
Endpoint URL: https://web-production-00e4.up.railway.app/api/billing/webhook
(This is your APP_BASE_URL from .env)

Events to send:
✅ checkout.session.completed
✅ invoice.payment_succeeded
✅ invoice.payment_failed
✅ customer.subscription.deleted
✅ customer.subscription.updated

Then: [Add endpoint]
```

#### 3. Copy Webhook Secret
- New webhook appears in the list
- Click it to open details
- Scroll down → copy **Signing secret** (starts with `whsec_`)
- Add to `.env`: `STRIPE_WEBHOOK_SECRET=whsec_...`

---

## Part 4: Test Locally (Optional but Recommended)

Before going live, test the webhook locally:

#### 1. Install Stripe CLI
- Download from: https://stripe.com/docs/stripe-cli
- Run: `stripe login` (authenticates to your account)

#### 2. Forward Webhooks to Local Dev
- Terminal: `stripe listen --forward-to localhost:8000/api/billing/webhook`
- Copy the webhook signing secret it shows
- Update `.env`: `STRIPE_WEBHOOK_SECRET=whsec_test_...` (test mode secret)

#### 3. Test a Payment Flow
- Start your app: `python main.py`
- Go to http://localhost:8000/pricing
- Click "Get Started" on Growth plan
- Use Stripe test card: `4242 4242 4242 4242` (any future expiry, any 3-digit CVC)
- Complete checkout → webhook should trigger locally
- Check your terminal for the webhook log

#### 4. Switch Back to Live
- Stop local testing
- In `.env`, set back to live credentials:
  ```
  STRIPE_SECRET_KEY=sk_live_51T3XuVF9oATlcOnl...
  STRIPE_PUBLISHABLE_KEY=pk_live_51T3XuVF9oATlcOnl...
  STRIPE_WEBHOOK_SECRET=whsec_live_...
  ```

---

## Part 5: Create Promo/Coupon Codes (5 mins, Optional)

Users can enter promo codes at checkout. Create some:

#### 1. Create a Coupon
- Stripe Dashboard → Left menu → **Products**
- Scroll down → **Coupons** (or navigate via left menu)
- Click **+ Create coupon**

**Example: LAUNCH50 (50% off, one-time use)**
```
Coupon code: LAUNCH50
Discount type: Percentage
Percentage off: 50
Valid for: Specific products (or leave All products)
Duration: Once (applies once only)
Redemption limit: Limit number of redemptions → 100
Expiration: Set an end date
```

- Click **Create coupon**

**Example: ANNUAL20 (20% off, ongoing)**
```
Coupon code: ANNUAL20
Discount type: Percentage
Percentage off: 20
Duration: Forever
Redemption limit: 1000
```

- Click **Create coupon**

#### 2. Create Promotion Code (Links Coupon to UI)
- Same Products menu → **Promotion codes**
- Click **+ Create promotion code**

```
Coupon: Select "LAUNCH50"
Code: LAUNCH50
Active: Yes
Redemption limit: 100
Restrictions: (optional - limit to specific products)
```

- Click **Create**

Users will now see these codes work at checkout and on your pricing page!

---

## Part 6: Verify Your Setup

Once all 6 prices are created and both webhooks + payment methods are enabled, test:

```bash
# 1. Verify keys are in .env
cat .env | grep STRIPE_PRICE

# 2. Start your app
python main.py

# 3. Go to pricing page
# http://localhost:8000/pricing
# or https://web-production-00e4.up.railway.app/pricing

# 4. Try each tier - it should redirect to Stripe Checkout
# 5. Look for PayPal + Google Pay buttons alongside credit card

# 6. For webhooks: check Railway logs
# Go to https://railway.app → your project → Deployments → View logs
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No Stripe price configured" | Check that all 6 `price_xxx` IDs are in `.env` |
| Webhook shows "Failed" in Stripe | Webhook URL must be publicly accessible (https, not localhost) |
| PayPal/Google Pay not showing | Ensure you toggled "Enabled" in Settings > Payment methods |
| Test card gets declined | Use `4242 4242 4242 4242` for successful charge, `4000 0000 0000 0002` for decline |
| Can't log into Stripe CLI | Run `stripe login --fresh` to re-authenticate |

---

## Your Checklist ✓

- [ ] Created 3 Products (Starter, Growth, Pro)
- [ ] Created 6 Prices (3 products × 2 periods)
- [ ] Copied all 6 `price_xxx` IDs to `.env`
- [ ] Enabled PayPal in Settings
- [ ] Enabled Google Pay in Settings
- [ ] Added Webhook endpoint and copied `whsec_` secret to `.env`
- [ ] (Optional) Created promo codes
- [ ] (Optional) Tested locally with Stripe CLI
- [ ] Verified pricing page shows all tiers
- [ ] Tested checkout flow end-to-end

---

## Questions?

- Stripe docs: https://stripe.com/docs
- Stripe support: https://support.stripe.com
- Your webhook logs: Stripe Dashboard → Developers → Webhooks → click endpoint

**Done? Commit your `.env` changes:**

```bash
git add .env
git commit -m "config: add live Stripe API keys and price placeholders"
```

Then once prices are created:

```bash
# Update just the price IDs
git add .env
git commit -m "config: add Stripe price IDs after dashboard setup"
```
