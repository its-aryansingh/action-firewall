---
paths:
  - "frontend/**/*.{ts,tsx,css,mjs,json}"
---

# Frontend rules

- Keep provider credentials and payment actuation on the server.
- Use `frontend/lib/api.ts` as the canonical browser-to-backend contract.
- Prefer Server Components; add `"use client"` only for interactive state or
  browser APIs.
- Use Tailwind or existing utility classes. Do not add inline `style` objects.
- Use explicit TypeScript types; do not introduce `any`.
- User-facing language says policy, authorization, action issued, and confirmed
  payment. Do not present link creation as paid or settled.
- Every denied, stale, in-progress, and unknown state must show one safe next action.
- Render every authoritative Purchase Envelope field before activation. A model
  summary or natural-language goal is never a substitute for structured approval.
- Show a field-level Policy Delta whenever execution would require broader authority.
- Never add a browser-side path that can mint a grant, compute authoritative prices,
  or invoke Razorpay directly.
- Run the production build after UI or API-contract changes.
