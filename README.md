# PrepQ

AI-powered interview preparation agent for Indian students and freshers.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router), Tailwind CSS, TypeScript |
| Backend | FastAPI, Python 3.12, Uvicorn |
| AI | Anthropic Claude claude-sonnet-4-5, Tavily Search |
| Database | Supabase (PostgreSQL + pgvector) |
| Auth | Supabase JWT |
| Cache | Upstash Redis |
| Infra | Docker, GitHub Actions, AWS EC2, Vercel |

---

## Local Setup

### 1. Environment variables

```bash
cp .env.example .env
```

Fill in all values in `.env`:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) |
| `SUPABASE_URL` | Project Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Project Settings → API → service_role secret |
| `JWT_SECRET` | Project Settings → API → JWT Secret |
| `UPSTASH_REDIS_URL` | [console.upstash.com](https://console.upstash.com) → Redis → REST URL |
| `UPSTASH_REDIS_TOKEN` | Upstash Redis REST token |

### 2. Supabase setup

1. Create a new Supabase project.
2. Go to **Database → Extensions** and enable the **vector** extension.
3. Run the migration SQL:
   - Open **SQL Editor** in your Supabase dashboard
   - Paste and run the contents of `backend/db/migrations/001_initial.sql`

### 3. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env .env   # or set env vars directly
uvicorn main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

### 4. Frontend

```bash
cd frontend
npm install
# .env.local already contains NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000`

---

## Docker (local)

```bash
cp .env.example .env   # fill in values first
docker-compose up --build
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

---

## Project Structure

```
PrepQ/
├── frontend/
│   ├── app/
│   │   ├── page.tsx              # Landing page
│   │   ├── chat/page.tsx         # Chat + onboarding
│   │   └── plan/page.tsx         # Plan view + mock interview
│   ├── components/
│   │   ├── ChatWindow.tsx        # Streaming chat UI
│   │   ├── OnboardingFlow.tsx    # Step-by-step onboarding
│   │   ├── PrepPlan.tsx          # Tiered plan display
│   │   └── MockInterview.tsx     # Mock Q&A with scoring
│   └── lib/api.ts                # All API calls
│
├── backend/
│   ├── main.py                   # FastAPI app
│   ├── agents/
│   │   ├── prepq_agent.py        # Claude claude-sonnet-4-5 agent + streaming
│   │   ├── retrieval.py          # Tavily company intel
│   │   └── scorer.py             # Mock answer evaluator
│   ├── routers/
│   │   ├── chat.py               # /chat SSE endpoint
│   │   ├── plan.py               # /plan endpoint
│   │   └── mock.py               # /mock endpoints
│   ├── middleware/
│   │   ├── auth.py               # JWT verification
│   │   ├── rate_limit.py         # Redis sliding window (20 req/min)
│   │   └── security.py           # Input sanitization
│   ├── models/schemas.py         # Pydantic models
│   ├── db/
│   │   ├── supabase.py           # DB client + queries
│   │   └── migrations/001_initial.sql
│   └── monitoring/prometheus.py  # Prometheus metrics
│
├── docker-compose.yml
├── .env.example
└── .github/workflows/pipeline.yml
```

---

## Security

- **Input sanitization**: All request bodies scanned for prompt injection, XSS, SQL injection
- **Rate limiting**: 20 requests/minute per user via Redis sliding window
- **Auth**: Supabase JWT required on all `/chat`, `/plan`, `/mock` routes
- **CORS**: Locked to `FRONTEND_URL` and `localhost:3000`
- **Secrets**: All via `.env`, never hardcoded

---

## Deploy

### Backend (AWS EC2)

1. Push to `main` — GitHub Actions builds and pushes the Docker image
2. SSH to EC2 and run `docker-compose up -d`
3. Configure nginx as reverse proxy on port 80/443

### Frontend (Vercel)

1. Connect `PrepQ/frontend` to Vercel
2. Set `NEXT_PUBLIC_BACKEND_URL` to your EC2 backend URL
3. Deploy

---

## Monitoring

- Prometheus metrics: `GET /metrics`
- Grafana: import the standard FastAPI dashboard and point to your Prometheus instance
