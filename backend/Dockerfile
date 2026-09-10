# Deployable demo image.
#
# Deliberately runs in the offline demo configuration: simulated provider, no
# Razorpay credentials baked in, fault injection on so the demo scenarios work.
# A judge opening the deployed URL sees the real authorization engine against a
# simulated actuator — which is exactly what the evidence in this repo claims,
# and nothing more.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEMO_MODE=true \
    PAYMENT_PROVIDER=simulated \
    FAULT_INJECTION_ENABLED=true \
    ENVELOPE_DRAFTING_MODE=replay \
    CATALOG_RETRIEVAL_MODE=keyword

WORKDIR /srv

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY data ./data

# The database is ephemeral by design: this is a demo, and a container restart
# should return a clean, reproducible state rather than accumulate history. No
# Railway volume is mounted for exactly this reason — every judge who opens the
# deployed URL gets the same starting state as the one before them.
ENV DB_PATH=/tmp/action_firewall.db

# Browser origin allowed by CORS. Railway sets this per service; the default
# keeps a local `docker run` usable against a local frontend.
ENV FRONTEND_ORIGIN=http://localhost:3000

WORKDIR /srv/backend
EXPOSE 8000

# Railway, Render and Fly all inject $PORT, and Railway additionally requires
# the process to bind 0.0.0.0 — binding localhost is the usual cause of its
# "Application failed to respond" page. The fallback keeps `docker run -p 8000:8000`
# working with no environment at all.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
