# Build context is apps/web (see docker-compose.yml).
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1

# NEXT_PUBLIC_* variables are inlined into the client bundle at build time -
# setting NEXT_PUBLIC_API_URL only as a container *runtime* env var (e.g. in
# docker-compose's `environment:` block) has no effect on an already-built
# bundle. It must be supplied as a build arg instead; see docker-compose.yml.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
# HOSTNAME must be forced to 0.0.0.0 here. Next's generated standalone
# server.js does `process.env.HOSTNAME || '0.0.0.0'` - but Docker
# auto-injects HOSTNAME=<container-id> into every container's environment
# by default, which short-circuits that fallback. Without this override,
# Node resolves the container-id "hostname" via Docker's embedded DNS to
# the container's bridge-network IP and binds ONLY there - so the app is
# reachable from the host (Docker's port-publish NAT targets that same
# bound IP) but NOT via localhost/127.0.0.1 from inside the container's
# own network namespace, which is exactly what the HEALTHCHECK below (and
# any in-container diagnostic) uses.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
    CMD node -e "fetch('http://localhost:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
