# 🛵 Atumwa Delivery Bot

WhatsApp-first delivery service for Harare, Zimbabwe.  
Customers order deliveries via WhatsApp. The bot finds the 5 nearest riders, lets the customer pick one (InDrive-style), then opens a private relay chat between them — no phone numbers ever shared.

---

## Project structure

```
atumwa/
├── app/
│   ├── main.py                  # FastAPI app + startup
│   ├── core/
│   │   ├── config.py            # Settings (from .env)
│   │   ├── database.py          # Async SQLAlchemy engine
│   │   └── session.py           # Redis conversation state
│   ├── models/
│   │   └── db.py                # SQLAlchemy models (Customer, Rider, Order, Rating)
│   ├── routers/
│   │   └── webhook.py           # WhatsApp webhook (GET verify + POST messages)
│   └── services/
│       ├── bot.py               # Conversation state machine ← the brain
│       ├── whatsapp.py          # Meta Cloud API sender
│       ├── rider_service.py     # Rider DB operations + PostGIS location queries
│       └── order_service.py     # Order DB operations + rating
├── docker-compose.yml           # PostgreSQL/PostGIS + Redis + API
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Quick start (local dev)

### 1. Clone and configure

```bash
cp .env.example .env
# Fill in your WhatsApp credentials (see Step 3 below)
```

### 2. Start the stack

```bash
docker compose up -d
```

The API runs on `http://localhost:8000`.  
Tables are auto-created on first startup in dev mode.

### 3. Get your WhatsApp Cloud API credentials

1. Go to https://developers.facebook.com and create an app (Business type)
2. Add the **WhatsApp** product
3. Under WhatsApp → API Setup, note your:
   - **Phone Number ID** → `WHATSAPP_PHONE_NUMBER_ID`
   - **Temporary Access Token** → `WHATSAPP_ACCESS_TOKEN`
4. For production, create a **System User** token (doesn't expire):
   - Business Settings → System Users → Add → Generate Token

### 4. Expose your local server for webhook registration

Meta needs to call your `/webhook` endpoint. Use [ngrok](https://ngrok.com):

```bash
ngrok http 8000
# Copy the https URL e.g. https://abc123.ngrok.io
```

### 5. Register the webhook with Meta

In your Meta app:
- WhatsApp → Configuration → Webhook
- URL: `https://your-ngrok-url.ngrok.io/webhook`
- Verify token: `atumwa_webhook_verify_token` (or whatever you set in .env)
- Subscribe to: `messages`

### 6. Test it!

Send a WhatsApp message to your test number. You should get the Atumwa greeting back.

---

## Conversation flows

### Customer ordering a delivery

```
Customer: Hi
Bot: Welcome! Where should we pick up?

Customer: [shares location pin or types address]
Bot: Got it. Where to deliver?

Customer: [drop-off address]
Bot: What are you sending? 1-Document 2-Parcel 3-Groceries 4-Large

Customer: 2
Bot: Any special instructions? (or type skip)

Customer: skip
Bot: How to pay? 1-EcoCash 2-Cash

Customer: 1
Bot: Enter your EcoCash number:

Customer: 0771234567
Bot: [Order summary] Here are your 5 nearest riders:
     1 – Tafadzwa 🏍️ ⭐ 4.8
     2 – Blessing 🚗 ⭐ 4.6
     ...

Customer: 1
Bot: Tafadzwa is on the way! You're now connected. All messages go through Atumwa.

[Customer and rider chat privately through the bot]

Customer: done
Bot: Delivery complete! Rate your rider: 1⭐ 2⭐⭐ ... 5⭐⭐⭐⭐⭐
```

### Rider registration

```
Rider: rider
Bot: Welcome to Atumwa Rider Registration! What's your full name?

Rider: Tafadzwa Moyo
Bot: What vehicle? 1-Bike 2-Car 3-Truck

Rider: 1
Bot: Enter your plate number (or "none"):

Rider: ACZ 1234
Bot: Registered! Share your location to go online.

Rider: [shares location]
Bot: Online ✅ We'll ping you when there's a delivery near you.
```

---

## Deployment (Railway / Render)

1. Push code to GitHub
2. Create a new project on [Railway](https://railway.app) or [Render](https://render.com)
3. Add PostgreSQL + Redis plugins
4. Set environment variables from `.env.example`
5. The `DATABASE_URL` will be provided by Railway/Render — use the async version:
   ```
   postgresql+asyncpg://user:pass@host:5432/dbname
   ```
6. Point your Meta webhook to the production URL

---

## Phase 2 (next)

- [ ] Rider job push notifications (broadcast to 5 riders simultaneously)
- [ ] Estimated price calculator (based on distance via Google Maps API)
- [ ] Rider accept/decline button messages (WhatsApp interactive buttons)
- [ ] Auto-reassign if rider doesn't accept within 2 minutes

## Phase 3 (next)

- [ ] EcoCash payment initiation via API
- [ ] Admin dashboard (FastAPI + simple HTML — track all orders live)
- [ ] Rider earnings tracker
- [ ] Customer order history ("track my last order")
