# What's Next

The menu API is deliberately scoped to what the test asks. This is the roadmap
for where it goes — three tracks, roughly in the order a real product would
need them. Nothing here is built; each track is sized and sequenced so it
*could* be.

## 1. Viewing layer — React / React Native app

- Web (Next.js/React) and mobile (React Native) clients sharing one GraphQL
  client layer against this API — the card → detail query pattern documented
  in the README is the contract these apps consume.
- Persisted queries at build time: the apps register their query shapes, the
  server executes only those — locks down the open GraphQL surface and enables
  CDN/HTTP caching of menu reads.
- Design system with atomic components and design tokens shared across web and
  native, so brand apps stay consistent.
- Feature flagging and experimentation wired in from the start — GraphQL helps
  here: experiment arms select different fields without API versioning.
- Session model: cookie-based by default; when no cookie is present (shared
  links, embedded webviews, SMS links), the app can recreate everything it
  needs from a unique URL — a signed token that resolves basket/session state
  server-side.

## 2. Cart + Ordering system

- **Async, event-driven core.** Order lifecycle is a chain of events, not a
  request/response — built on a durable event backbone (Kafka for scale,
  Inngest for faster time-to-value with built-in retries/step functions; start
  with the lighter tool, the event contracts are what matter).
- **Fan-out on order placement.** One `order.placed` event feeds independent
  consumers: store/kitchen systems, delivery dispatch, loyalty, receipts.
  Consumers fail and retry independently — a delivery-provider outage must
  never block the kitchen ticket.
- **Status flows back, user stays informed.** Store and delivery systems emit
  status updates (`accepted`, `preparing`, `out_for_delivery`, `delivered`);
  a notification consumer translates these into email/SMS/push to the customer
  (SES/Twilio-class providers behind the same observability seam).
- **Two kinds of customers from day one:**
  - *Direct* — our web/app users (cookie or unique-URL session as above).
  - *Third-party* — orders arriving through marketplaces like Uber Eats,
    DoorDash. Same internal order pipeline, different ingress and identity.
- **Uber Eats (and similar) integration:**
  - RESTful endpoints implementing their menu/store/order APIs
    (https://developer.uber.com/docs/eats/introduction) — our normalized menu
    schema already maps cleanly to their menu upload shape.
  - Webhooks for order events (https://developer.uber.com/docs/eats/guides/webhooks),
    treated with the same rules as payment callbacks: signature verification,
    idempotency on the provider's event ID, tolerate duplicates and reordering.
  - **Production-grade webhook ingress:** AWS API Gateway + Lambda + SQS +
    Postgres — the gateway absorbs bursts and verifies signatures, Lambda
    validates and enqueues, SQS buffers so our order service consumes at its
    own pace, events land durably before any processing. (Supabase is a
    candidate for the durable store here if we want managed Postgres +
    realtime status streams to clients.)
- **Non-negotiables carried over from the menu API's discipline:** order state
  machine with DB-enforced transitions; order items snapshot price/options at
  submit time; payment treated as eventually consistent; every consumer
  idempotent; money paths audited.

## 3. Authentication / Authorization layer

- **Customer identity:** social logins (Apple/Google/Facebook) plus guest
  checkout — guests get the unique-URL session; orders attach to an account
  later if they sign up.
- **Web:** httpOnly secure cookies (session or short-lived JWT + refresh).
  **Mobile:** token-based with secure storage. Same identity service behind
  both.
- **Unique-URL recovery:** signed, expiring tokens that rebuild session state
  when cookies are absent — also the mechanism for "track your order" links
  in email/SMS.
- **Partners are principals too:** Uber Eats-class integrations authenticate
  via OAuth client credentials / API keys; webhook payloads verified by
  signature, never trusted by source IP alone.
- **Internal/ops surface:** the ingest trigger and future admin endpoints move
  behind staff RBAC; rate limiting on public GraphQL; audit trail on anything
  that mutates orders or money.
