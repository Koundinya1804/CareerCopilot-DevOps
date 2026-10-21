# ── Dockerfile (frontend) ───────────────────────────────────────────────────
# Multi-stage build: Node builds the static Vite bundle, nginx serves it.

FROM node:20-alpine AS builder

WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# VITE_API_BASE_URL is baked into the JS bundle at build time (Vite env vars
# are compile-time, not runtime) — override via --build-arg if the API isn't
# reverse-proxied at /api/v1 on the same origin as the frontend.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ── Final stage ───────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS final

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
