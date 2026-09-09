# Deploying the demo

Fifteen minutes, no credentials anywhere. The deployed instance runs the real
authorization engine against the **simulated** provider, which is exactly what
the evidence in this repository claims — no Razorpay keys are baked into the
image and none are needed.

## Backend — Render

1. Push this repository to GitHub.
2. Render → **New → Blueprint** → point it at the repo. It reads `render.yaml`
   at the root and builds `backend/Dockerfile`.
3. Wait for the health check at `/health` to go green.

You get `https://action-firewall.onrender.com` or similar. The free plan sleeps
after inactivity, so the first request after a pause takes ~30s — open it a
minute before a demo.

## Frontend — Vercel

1. Vercel → **New Project** → import the repo → set the root directory to
   `frontend`.
2. Add one environment variable:
   `NEXT_PUBLIC_API_BASE = https://<your-render-url>`
3. Deploy.

`frontend/lib/api.ts` already reads that variable and falls back to
`http://localhost:8000`, so nothing else changes.

## Then do this, and it is the part people forget

Put the frontend URL in the GitHub repository's **`homepage`** field
(Settings → General, or the ⚙ beside "About"). It then appears at the top right
of the repo page, so a judge sees a working link before they open the README.

Add the same URL to the first line of `README.md`.

## Verifying the deployment is honest

```bash
curl -s https://<render-url>/health
```

The response reports the active provider mode. It must say the provider is
simulated. If a deployed instance ever reports a live provider, something has
been configured that this repository does not intend — the Dockerfile pins
`PAYMENT_PROVIDER=simulated` and no key is present in the image.
