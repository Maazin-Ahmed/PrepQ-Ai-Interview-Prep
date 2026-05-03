# PrepQ

**The AI prep agent that tells you exactly what to study — not everything.**

Built for Indian freshers and final-year students who are done reading generic roadmaps and want a plan that's actually built around their situation.

---

## The Problem

Most interview prep advice is built for people with months to spare and unlimited energy. You have neither. You're juggling college, applications, anxiety, and a list of topics so long it might as well say "give up."

The guides are generic. The courses are too slow. The mentors are too expensive. And everyone keeps telling you to "just do LeetCode" while you don't even know what round you're being tested for.

PrepQ was built to cut through all of that.

---

## What PrepQ Does

You tell PrepQ where you are. It tells you exactly what to do next.

There are three modes — each one handles a different situation you're actually in right now.

### 🎯 Interview Prep
You have an interview coming up. You know the company, the role, maybe the round. PrepQ builds you a day-by-day prep plan — ruthlessly prioritized by what's most likely to come up, not what's most comprehensive to cover. It skips what you've already done and focuses on where you're weakest.

### 📈 Upskill Roadmap
No interview lined up yet, but you're building towards a goal. Tell PrepQ what role you want and where you are today, and it maps out exactly what to learn and in what order — no filler, no padding, no "first, understand the fundamentals" when you're already past that.

### 🔍 Why Am I Not Getting Shortlisted?
You're applying and nothing's happening. PrepQ analyzes your profile — your background, target companies, experience level — and tells you what's actually holding you back. Not a guess. A real breakdown with next steps.

---

## How It Works

**1. Tell PrepQ your situation**
Answer a few questions: company, role, days left, what you've already covered, what you've skipped. Takes two minutes.

**2. Get a ruthlessly prioritized plan**
PrepQ generates a tiered breakdown — what to focus on first, what to do if you have time, and what to skip entirely. Backed by real company intel pulled in at runtime.

**3. Prep smarter**
Chat with PrepQ like a tutor who actually knows your situation. Ask follow-ups, run mock Q&As, get scored, and adjust the plan as you go.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Vanilla CSS |
| Backend | FastAPI, Python 3.12, Uvicorn |
| AI | Groq (LLaMA 3), Tavily Search API |
| Auth | Supabase (Google OAuth + JWT) |
| Database | Supabase (PostgreSQL) |
| Cache / Rate Limiting | Upstash Redis |
| Infra | Docker, GitHub Actions, AWS EC2 |

---

## Local Setup

### 1. Clone and configure

```bash
git clone https://github.com/Maazin-Ahmed/PrepQ-Ai-Interview-Prep.git
cd PrepQ-Ai-Interview-Prep
cp .env.example .env
```

Fill in `.env` with your keys:

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) |
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Supabase → Project Settings → API → service_role |
| `JWT_SECRET` | Supabase → Project Settings → API → JWT Secret |
| `UPSTASH_REDIS_URL` | [console.upstash.com](https://console.upstash.com) → Redis → REST URL |
| `UPSTASH_REDIS_TOKEN` | Upstash → Redis → REST Token |

Frontend env (`frontend/.env.local`):

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Same as `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase → Project Settings → API → anon key |
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` |

### 2. Run with Docker (easiest)

```bash
docker-compose up --build
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

### 3. Or run manually

**Backend:**
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## Supabase Setup

1. Create a new Supabase project at [supabase.com](https://supabase.com)
2. Go to **Authentication → Providers** and enable Google
3. Add your redirect URL: `http://localhost:3000/auth/callback`
4. Run the migration: **SQL Editor** → paste and run `backend/db/migrations/001_initial.sql`

---

## Project Structure

```
PrepQ/
├── frontend/
│   ├── app/
│   │   ├── page.tsx              # Landing page
│   │   ├── login/page.tsx        # Google sign-in
│   │   ├── auth/callback/        # OAuth callback handler
│   │   └── chat/page.tsx         # Chat + onboarding
│   ├── components/
│   │   ├── AuthGuard.tsx         # Route protection
│   │   ├── Sidebar.tsx           # Session history + user
│   │   ├── ChatWindow.tsx        # Streaming chat UI
│   │   ├── OnboardingFlow.tsx    # Step-by-step onboarding
│   │   └── PrepPlan.tsx          # Tiered plan display
│   └── lib/
│       ├── api.ts                # All backend API calls
│       ├── storage.ts            # Session state (localStorage)
│       └── supabase.ts           # Supabase client singleton
│
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── agents/
│   │   ├── prepq_agent.py        # AI agent + streaming
│   │   ├── retrieval.py          # Tavily company intel
│   │   └── scorer.py             # Mock answer evaluator
│   ├── routers/
│   │   ├── chat.py               # /chat SSE endpoint
│   │   ├── plan.py               # /plan endpoint
│   │   └── mock.py               # /mock endpoints
│   ├── middleware/
│   │   ├── auth.py               # JWT verification
│   │   ├── rate_limit.py         # Redis rate limiting
│   │   └── security.py           # Input sanitization
│   └── db/
│       ├── supabase.py           # DB client
│       └── migrations/
│
├── docker-compose.yml
├── .env.example
└── .github/workflows/pipeline.yml
```

---

## Contributing

This is open for contributions. If you have a feature idea or a bug fix, open an issue or a PR — just keep it focused and don't add dependencies without a reason.

Things that would genuinely make PrepQ better:
- More onboarding modes (e.g. off-campus placement prep, PSU prep)
- Better company-specific intel retrieval
- Session sync across devices (Supabase persistence layer is already in place)
- Mobile-first UI improvements

---

## License

MIT — see [LICENSE](./LICENSE).

Copyright 2026 Maazin Ahmed.
