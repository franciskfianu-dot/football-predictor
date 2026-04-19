# Football Score Predictor

AI-powered football match prediction engine covering EPL, La Liga, Serie A, Bundesliga, and Ligue 1.

Predicts correct scores, 1X2, BTTS, Over/Under, Asian Handicap, and HT/FT markets with statistically derived betting value ratings.

## Architecture

| Layer | Service | Free Tier |
|---|---|---|
| Frontend | Vercel | Unlimited |
| Backend API | Fly.io | 3 always-on VMs |
| Database | Supabase (PostgreSQL) | 500MB |
| Cache / Queue | Upstash Redis | 10k req/day |
| CI/CD + Cron | GitHub Actions | Unlimited (public repo) |
| Weather | OpenWeatherMap | 1,000 calls/day |

## Quick Start (Local Dev)

### Prerequisites
- Docker + Docker Compose
- Node.js 20+
- Python 3.11+
- Git

### 1. Clone and configure
```bash
git clone https://github.com/YOUR_USERNAME/football-predictor.git
cd football-predictor
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

### 2. Fill in .env files
Edit `backend/.env` with your credentials (see Environment Variables section below).

### 3. Start local stack
```bash
docker compose up -d
```

### 4. Run database migrations
```bash
docker compose exec api alembic upgrade head
```

### 5. Seed initial data + run first scrape
```bash
docker compose exec api python -m pipeline.seed_leagues
docker compose exec api python -m pipeline.run_scrape --leagues epl,laliga,seriea,bundesliga,ligue1 --seasons 3
```

### 6. Train initial models
```bash
docker compose exec api python -m pipeline.train_all
```

### 7. Frontend dev server
```bash
cd frontend && npm install && npm run dev
```

App runs at http://localhost:5173, API at http://localhost:8000, MLflow at http://localhost:5001

## Environment Variables

### Backend (`backend/.env`)
```
DATABASE_URL=postgresql://postgres:password@db:5432/football_predictor
REDIS_URL=redis://redis:6379/0
OPENWEATHER_API_KEY=your_key_here          # free at openweathermap.org
ADMIN_SECRET_TOKEN=change_me_to_random_string
MLFLOW_TRACKING_URI=http://mlflow:5001
ENVIRONMENT=development
SCRAPE_DELAY_SECONDS=3
CORS_ORIGINS=http://localhost:5173
GOOGLE_SERVICE_ACCOUNT_JSON={}             # filled in during Sheets setup
```

### Frontend (`frontend/.env`)
```
VITE_API_URL=http://localhost:8000
```

## Deployment

### Deploy to Fly.io (backend)
```bash
cd backend
fly auth login
fly launch --name football-predictor-api --no-deploy
fly secrets set DATABASE_URL="..." REDIS_URL="..." OPENWEATHER_API_KEY="..."
fly deploy
```

### Deploy to Vercel (frontend)
```bash
cd frontend
npx vercel --prod
# Set VITE_API_URL to your Fly.io app URL in Vercel dashboard
```

### Set up Supabase
1. Create project at supabase.com
2. Copy the connection string from Settings → Database
3. Set as DATABASE_URL in Fly.io secrets

### Set up Upstash Redis
1. Create database at upstash.com
2. Copy Redis URL
3. Set as REDIS_URL in Fly.io secrets

## Google Sheets Setup

The app includes a setup wizard at /settings/sheets. You will need:
1. A Google Cloud project (console.cloud.google.com)
2. Sheets API + Drive API enabled
3. A service account with a JSON key

The wizard walks through each step in-app.

## Daily Retraining

Runs automatically at 02:00 UTC via GitHub Actions (`.github/workflows/retrain.yml`).
Requires `FLY_API_TOKEN` and `ADMIN_SECRET_TOKEN` set as GitHub repository secrets.

## Project Structure

```
football-predictor/
├── frontend/                  # React 18 + Vite + TailwindCSS
│   └── src/
│       ├── components/        # Reusable UI components
│       ├── pages/             # Route-level page components
│       ├── hooks/             # Custom React hooks
│       ├── utils/             # Helpers, formatters
│       └── store/             # Zustand state management
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/  # FastAPI route handlers
│   │   ├── core/              # Config, security, logging
│   │   ├── db/                # SQLAlchemy models + Alembic
│   │   └── schemas/           # Pydantic v2 request/response models
│   ├── scrapers/              # One scraper per data source
│   ├── features/              # Feature engineering pipeline
│   ├── models/                # ML model training + evaluation
│   ├── pipeline/              # Orchestration + daily cron tasks
│   └── tests/
├── .github/workflows/         # CI, CD, daily retrain
├── docker-compose.yml         # Local dev stack
└── infra/                     # Fly.io + Vercel config
```

## Disclaimer

Statistical model outputs only. Not financial or gambling advice. Gamble responsibly. Past model performance does not guarantee future results.
