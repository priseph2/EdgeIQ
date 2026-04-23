# EdgeIQ — Personal Sports Betting Intelligence Platform

AI-powered predictions, value bet detection, arbitrage hunting, and bet tracking for NBA, EuroLeague, and Top 5 European football leagues. Targets Nigerian bookmaker markets (1xBet, Betway). Web dashboard + Telegram bot.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase project
- API keys (see table below)

### 1. Clone and configure
```bash
git clone https://github.com/priseph2/edgeiq
cd EdgeIQ
cp .env.example .env
# Fill in all API keys in .env
```

### 2. Backend setup
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Apply database schema
```bash
# In Supabase dashboard → SQL Editor, run:
supabase/schema.sql
```

### 4. Ingest historical data
```bash
cd backend
python -m data.ingest_nba          # NBA 3 seasons (free, no key)
python -m data.ingest_euro_bb      # EuroLeague 2 seasons (RapidAPI key)
python -m data.ingest_football     # Top 5 leagues 3 seasons (football-data.org)
```

### 5. Train models
```bash
python -m ml.train --sport all
# Outputs: models/basketball_v1.pkl, models/football_v1.pkl
```

### 6. Start backend
```bash
uvicorn main:app --reload --port 8000
```

### 7. Frontend setup
```bash
cd frontend
npm install
npm run dev       # http://localhost:3000
```

### 8. Start Telegram bot (optional)
```bash
cd backend
python telegram_bot.py
```

---

## API Keys Required

| API | Purpose | Cost | Get it |
|-----|---------|------|--------|
| Supabase | Database + Auth | Free | supabase.com |
| The Odds API | Live odds (1xBet, Betway, Pinnacle) | 500 req/mo free | the-odds-api.com |
| RapidAPI | EuroLeague stats + football xG | 100 req/day free | rapidapi.com |
| football-data.org | Top 5 league results | Free | football-data.org |
| Anthropic (Claude) | AI match analysis | Pay-per-use | console.anthropic.com |
| Telegram BotFather | Bot token | Free | t.me/BotFather |
| Upstash Redis | Prediction cache | Free tier | upstash.com |

---

## Architecture

```
EdgeIQ/
├── frontend/               # Next.js 14 (App Router) + Tailwind CSS
│   ├── app/page.tsx        # Dashboard: today's predictions
│   ├── app/predictions/    # Full list with sport/league/value filters
│   ├── app/tracker/        # Bet logging + P&L analytics
│   └── components/         # PredictionCard, Nav
├── backend/                # FastAPI Python service
│   ├── routers/
│   │   ├── predictions.py  # ML inference + Claude analysis endpoints
│   │   └── bets.py         # Bet tracker + analytics endpoints
│   ├── ml/
│   │   ├── features.py     # Feature engineering (xG, rolling stats, H2H)
│   │   ├── train.py        # LightGBM + Platt calibration
│   │   ├── predict.py      # Inference + value bet detection
│   │   └── claude_analysis.py  # Claude API with prompt caching
│   ├── data/
│   │   ├── ingest_nba.py       # BallDontLie API (free)
│   │   ├── ingest_euro_bb.py   # api-basketball RapidAPI
│   │   ├── ingest_football.py  # football-data.org + API-Football (xG)
│   │   └── ingest_odds.py      # The Odds API
│   ├── telegram_bot.py     # Daily digest + command bot
│   └── scheduler.py        # Cron: odds every 60s, retrain weekly, digest 9am
└── supabase/schema.sql     # All tables + RLS policies
```

---

## ML Models

| Model | Algorithm | Target | Brier Target | Accuracy Target |
|-------|-----------|--------|-------------|-----------------|
| Basketball | LightGBM binary | Home win (1/0) | < 0.22 | > 59% |
| Football | LightGBM multi-class | H/D/A (0/1/2) | < 0.22 | > 54% |

**Key features:**
- Football: xG for/against (last 5 matches) — strongest single predictor
- Basketball: rolling points, ORTG/DRTG, rest days, back-to-back flag
- Both: H2H record, home/away split, season win %, recent streak

**Primary success metric: positive CLV vs Pinnacle closing line** (not raw accuracy)

Calibration: Platt scaling via `CalibratedClassifierCV(method='isotonic')`
Training split: time-based only (never random — avoids data leakage)

---

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register + welcome message |
| `/today` | Today's full predictions digest |
| `/value` | Value bets only |
| `/predict <team>` | Prediction for a team's next match |
| `/stats` | Model accuracy and Brier scores |
| `/help` | Command list |

Daily digest sent automatically at **9am Africa/Lagos**.
Value bet and arb alerts pushed **immediately** when detected.

---

## Value Bet Detection

A bet is flagged as value when:
```
model_probability - (1 / best_odds) > 0.05
```
i.e. the model gives at least 5% more probability than the market implies.

---

## Verification Checklist

After setup, verify each component:

```bash
# 1. Predictions endpoint
curl http://localhost:8000/predictions/today

# 2. Model stats
curl http://localhost:8000/predictions/model/stats

# 3. Health check
curl http://localhost:8000/health
```

- Telegram: send `/predict Lakers` — should return today's Lakers match
- Dashboard: open http://localhost:3000 — should show prediction cards
- Value bets: flagged with green border on cards + 💰 badge

---

## Environment Variables

See `.env.example` for full list. Minimum required for core functionality:

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Odds, xG features, and EuroLeague data require additional API keys but are optional for initial model training on NBA + football-data.org data.
