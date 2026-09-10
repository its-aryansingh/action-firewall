# Operations control plane, built for Railway.
#
# Build context is this directory, not the repository root: the frontend needs
# nothing from outside it, which is what lets the Railway service set its root
# directory to /frontend and rebuild only when the frontend changes.
#
# NEXT_PUBLIC_API_BASE IS A BUILD-TIME VARIABLE, NOT A RUNTIME ONE.
# Next.js inlines every NEXT_PUBLIC_* value into the client bundle during
# `next build`, so a value set only at runtime arrives too late and the browser
# silently calls http://localhost:8000 instead of the deployed API. Railway
# passes service variables into a Docker build only when the Dockerfile declares
# them with ARG, which is what the builder stage below does. If you change the
# API base, you must REBUILD — restarting is not enough.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_BASE=https://action-firewall-production.up.railway.app
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Fail the build rather than ship a bundle that points at localhost. A frontend
# deployed with the wrong API base looks fine until every request fails in the
# browser, which is the worst moment to discover it.
RUN if [ -z "$NEXT_PUBLIC_API_BASE" ]; then \
      echo "ERROR: NEXT_PUBLIC_API_BASE is empty at build time." >&2; \
      echo "Set it on the Railway frontend service before deploying, e.g." >&2; \
      echo '  NEXT_PUBLIC_API_BASE=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}' >&2; \
      exit 1; \
    fi
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# `output: "standalone"` in next.config.mjs produces a self-contained server
# with only the packages it actually imports, so the runtime image carries no
# build toolchain and no dev dependencies.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001 \
    && chown -R nextjs:nodejs /app
USER nextjs

EXPOSE 3000

# Railway injects PORT and requires the process to bind 0.0.0.0; localhost-only
# binding is the usual cause of "Application failed to respond".
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 PORT=${PORT:-3000} node server.js"]
