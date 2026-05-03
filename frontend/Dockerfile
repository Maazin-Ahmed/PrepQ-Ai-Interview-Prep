# ──────────────────────────────────────────
# Stage 1: Install dependencies
# ──────────────────────────────────────────
FROM node:20-alpine AS deps
# libc6-compat is required for some native Node modules on Alpine
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline

# ──────────────────────────────────────────
# Stage 2: Build the Next.js application
# ──────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

# NEXT_PUBLIC_* vars must be present at build time so Next.js can inline them
# into the client bundle. Pass them via --build-arg in docker-compose.
ARG NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL

# Ensure public/ always exists so the COPY in the runner stage never fails
# (Next.js does not require this directory — projects may omit it entirely).
RUN mkdir -p public && npm run build

# ──────────────────────────────────────────
# Stage 3: Minimal production runner
# ──────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Non-root user for security
RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# Pre-create .next with correct ownership so Next.js can write its runtime cache
RUN mkdir -p .next && chown nextjs:nodejs .next

# Copy the standalone server output (includes node_modules trace, no extras)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

# Copy static assets (JS chunks, CSS, images)
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# public/ is guaranteed to exist (created with mkdir -p in builder stage)
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
