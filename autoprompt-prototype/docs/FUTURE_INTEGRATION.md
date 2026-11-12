# Future Integration Plan

## 1. AI API Integration
- **Endpoint**: Connect to a large‑language‑model (LLM) service (e.g., Gemini, OpenAI, Anthropic) via a REST endpoint that accepts a prompt payload and returns generated text.
- **Client‑side changes**:
  - Replace the simulated `setTimeout` in `workspace.js` with an `async` call to `fetch('/api/generate', { method: 'POST', body: JSON.stringify(payload) })`.
  - Show a loading spinner while awaiting the network response.
- **Security**:
  - API keys must never be exposed in the front‑end. Calls should be proxied through a backend service that injects authentication headers.
- **Rate limiting & error handling**:
  - Implement exponential back‑off for transient failures.
  - Surface clear error messages (e.g., *"Prompt generation failed – please try again later."*).

## 2. Backend Requirements
- **Node/Express (or any preferred stack)** exposing two endpoints:
  - `POST /api/generate` – receives `{ service: 'generate', prompt: '...', options: { ... } }` and returns `{ result: '...', tokenCount: 123 }`.
  - `POST /api/optimize` – receives an existing prompt and returns an optimized version with token metrics.
- **Authentication** – optional JWT for user‑specific quota tracking.
- **Session persistence** – store the last prompt and settings per user (e.g., in Redis or a relational DB) so that a page refresh can restore the workspace.
- **Logging & monitoring** – capture request latency, error rates, and usage metrics.

## 3. Token Counting
- Integrate a tokenizer matching the chosen LLM (e.g., `tiktoken` for OpenAI models or a BPE tokenizer for Gemini).
- The backend should calculate:
  - `originalTokens`
  - `optimizedTokens`
  - `tokensSaved`
  - `reductionPercent`
- Return these numbers in the API response; the front‑end will display them directly (no demo labeling needed once real data is supplied).

## 4. Database & Persistence
- **User profiles** – store language preference, theme, and saved prompts.
- **Prompt history** – allow users to view past generations/optimizations, with timestamps and result text.
- **Metrics** – optional analytics on token usage per user for billing or quota enforcement.

## 5. Authentication & Authorization
- **Sign‑in flow** – integrate with an identity provider (Google, Auth0, etc.).
- Store a JWT in `localStorage`/`sessionStorage` and attach it to API calls via the `Authorization: Bearer <token>` header.
- Protect the backend endpoints; unauthenticated users can be limited to a demo mode with static data.

## 6. Additional UI Enhancements (post‑integration)
- Show real‑time token counts as the user types (via a debounce call to the backend tokenizer endpoint).
- Enable **Save Prompt** and **Load Prompt** actions linked to the database.
- Provide **Export** (JSON/Markdown) of prompt histories.
- Add **Usage dashboard** displaying token consumption per period.

---
This document outlines the components that would need to be built to evolve the current front‑end prototype into a fully functional SaaS product that generates and optimizes AI prompts using real backend services.
