# Deploying on Railway

Two services from this one repository, no credentials anywhere. The deployed
instance runs the real authorization engine against the **simulated** provider,
which is exactly what the evidence in this repository claims — no Razorpay keys
are baked into either image and none are needed.

Everything the platform needs is already committed:

| File | Service | What it pins |
| --- | --- | --- |
| `railway.json` | backend | Builds `backend/Dockerfile` from the repo root, health check on `/health` |
| `backend/Dockerfile` | backend | Simulated provider, ephemeral DB, binds `0.0.0.0:$PORT` |
| `frontend/railway.json` | frontend | Builds `frontend/Dockerfile`, health check on `/` |
| `frontend/Dockerfile` | frontend | Next.js standalone build, binds `0.0.0.0:$PORT` |
| `.dockerignore` | both | Keeps `.env` and `*.db` out of the build context entirely |

---

## The one thing that will bite you

`NEXT_PUBLIC_API_BASE` is a **build-time** variable. Next.js inlines every
`NEXT_PUBLIC_*` value into the browser bundle during `next build`, so setting it
after the fact and restarting does nothing — the bundle still holds whatever it
was built with. Change the API base and you must **rebuild**, not restart.

`frontend/Dockerfile` fails the build outright when that variable is empty,
rather than shipping a bundle that quietly calls `localhost:8000` from a judge's
browser. So a red build here is the guard working, not a bug.

---

## 1. Create the project

Railway → **New Project → Deploy from GitHub repo** → pick this repository.

Railway will create one service. That one is the **backend**: leave its root
directory at the repository root, because `backend/Dockerfile` copies
`data/catalog.json` from there and cannot see outside its build context.

Rename it to `backend` in Settings. The name matters — the frontend refers to it
by name in step 3.

## 2. Add the frontend service

In the same project: **New → GitHub Repo** → the same repository again. Then in
that service's **Settings**:

- **Root Directory:** `/frontend`
- **Config-as-code file path:** `/frontend/railway.json`

Set the config path explicitly. Railway's config file does not follow the root
directory setting, so without it this service would look for the root
`railway.json` and try to build the backend. Rename the service to `frontend`.

## 3. Generate both domains, then set two variables

Generate a public domain for **each** service first (Settings → Networking →
Generate Domain). The variables below reference those domains, so they resolve to
empty strings until the domains exist.

On **backend** → Variables:

```
FRONTEND_ORIGIN = https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
```

On **frontend** → Variables:

```
NEXT_PUBLIC_API_BASE = https://${{backend.RAILWAY_PUBLIC_DOMAIN}}
```

Those are Railway variable references, typed literally — Railway resolves them.
Nothing is pasted by hand, so the two services cannot drift apart when a domain
changes.

`FRONTEND_ORIGIN` is what the backend's CORS layer allows. Without it the
browser is refused and every panel in the control plane sits empty while the
backend looks perfectly healthy.

## 4. Redeploy both, frontend last

Backend first, then frontend — the frontend bakes the backend's URL in at build
time and needs the value present before it builds.

---

## Verifying the deployment is honest

```bash
curl -s https://<backend-domain>/health
```

The response reports the active provider mode. It must say `"payment_provider":
"simulated"`. If a deployed instance ever reports a live provider, something has
been configured that this repository does not intend — `backend/Dockerfile` pins
`PAYMENT_PROVIDER=simulated` and no key is present in the image.

Two more worth opening, because they are the parts a reviewer is most likely to
check and the least likely to guess exist:

```bash
curl -s https://<backend-domain>/agent-commerce/v1/acceptance-policy
```

The published refusal rules, served without authentication, carrying a
`policy_hash` an agent can pin.

Then open `https://<frontend-domain>/` and confirm the panels populate. If the
page renders but every number is blank, it is CORS: check `FRONTEND_ORIGIN` on
the backend.

---

## When it does not come up

**"Application failed to respond."** The process is not on the port Railway
expects. Both Dockerfiles bind `0.0.0.0` and honour `$PORT`, so the usual cause
is a public domain whose target port was detected as something else: set the
service's domain target port to match, or set `PORT=8000` (backend) / `PORT=3000`
(frontend) explicitly as a service variable.

**Frontend loads, all data blank.** CORS. `FRONTEND_ORIGIN` on the backend must
be the frontend's full origin including `https://` and no trailing slash.

**Frontend calls `localhost:8000` in the browser console.** It was built without
`NEXT_PUBLIC_API_BASE`. Set it and **redeploy** the frontend; a restart will not
change an already-built bundle.

**Backend build fails on `COPY data ./data`.** The backend service's root
directory was changed away from the repository root. Put it back — that image
needs the repo root as its build context.

---

## What is deliberately not configured

**No volume.** The database is ephemeral, so every restart returns the deployed
demo to the same clean state. Two judges opening the link an hour apart see the
same starting point rather than each other's leftovers. `DB_PATH=/tmp/action_firewall.db`
in `backend/Dockerfile` is what makes that true; attaching a Railway volume and
pointing `DB_PATH` at it is the one change needed if you ever want the opposite.

**No Razorpay credentials.** `PAYMENT_PROVIDER=simulated` and
`FAULT_INJECTION_ENABLED=true` are pinned in the image, and `app/config.py`
refuses to start with fault injection enabled against a live provider. There is
no configuration of this deployment that both injects faults and touches a real
payment rail.

**Optional, if you want them:** `ACTION_RECEIPT_SECRET` (any random string —
signs action receipts; a demo default is used when unset) and `OPENAI_API_KEY`
(enables the LLM drafting and voice paths; the deterministic replay drafter runs
without it).

---

## Other platforms

`render.yaml` at the repo root still describes the backend as a Render
blueprint, and `backend/Dockerfile` runs unchanged on Fly or any container host
that injects `$PORT`. Railway is the documented path because it hosts both
halves from one repository with one set of cross-references.
