# Example Antigravity Implementation Plan: Adding Webhook Support

Provide a brief description of the problem, any background context, and what the change accomplishes.

*Example:* This plan details the implementation of webhook support for processing payment events from Stripe. It allows our system to listen to `payment_intent.succeeded` events and update the database accordingly, enabling automated order fulfillment.

---

## User Review Required

Document anything that requires user review or feedback, for example, breaking changes or significant design decisions. Use GitHub alerts (IMPORTANT/WARNING/CAUTION) to highlight critical items.

> [!WARNING]
> This feature introduces a new public API endpoint: `/api/webhooks/stripe`. Since this is a public endpoint, signature verification is strictly enforced using Stripe's signing secret.

> [!IMPORTANT]
> The database schema changes require a migration. Make sure the database credentials are set correctly in `.env` before starting the execution.

---

## Open Questions

Any clarifying or design questions for the user that will impact the implementation plan. Use GitHub alerts (IMPORTANT/WARNING/CAUTION) to highlight critical items.

> [!NOTE]
> 1. Should we retry failed webhook deliveries?
>    *Yes, we will handle Stripe's automatic retries by returns a 200 OK after staging the event, then processing asynchronously.*
> 2. What is the retention policy for processed webhook logs?
>    *Currently, we will retain logs for 30 days.*

---

## Proposed Changes

Group files by component (e.g., package, feature area, dependency layer) and order logically (dependencies first). Separate components with horizontal rules for visual clarity.

### Database & Models

We need to add a table to keep track of processed webhook events to avoid duplicate processing (idempotency).

#### [NEW] [migrations/20260529_create_webhooks.sql](file:///c:/Users/DO%20DO/Desktop/your-project/migrations/20260529_create_webhooks.sql)
* Create SQL migration defining `StripeWebhookEvent` table with fields: `id` (text, primary key), `status` (text), and `receivedAt` (timestamp).

---

### API Routing & Controller

Implement the signature verification and webhook handler logic.

#### [NEW] [controllers/webhook.ts](file:///c:/Users/DO%20DO/Desktop/your-project/controllers/webhook.ts)
* Create controller to verify Stripe webhook signatures and enqueue events for background processing.

#### [MODIFY] [routes/api.ts](file:///c:/Users/DO%20DO/Desktop/your-project/routes/api.ts)
* Mount the new webhook handler on `/api/webhooks/stripe`. Ensure it disables standard JSON body parsing to read raw bodies for signature verification.

---

## Verification Plan

Summary of how you will verify that your changes have the desired effects.

### Automated Tests
- Run unit tests for webhook signature validation logic:
  ```bash
  npm run test controllers/webhook.test.ts
  ```
- Run integration tests to simulate a signed Stripe payload:
  ```bash
  npm run test:integration
  ```

### Manual Verification
- Trigger webhook events locally using the Stripe CLI:
  ```bash
  stripe trigger payment_intent.succeeded
  ```
- Verify receipt and processing status in database logs.
