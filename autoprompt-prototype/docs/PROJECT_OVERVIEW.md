# Project Overview

## Product Purpose
AutoPrompt is a lightweight web‑based prototype that helps users **craft better AI prompts**.  The interface guides the user through a simple workflow where an idea or an existing prompt is entered, optionally refined with additional details, and a mock‑generated or optimized prompt is displayed.  The goal of the prototype is to demonstrate the UI/UX flow, theme handling, and responsive design for a future SaaS prompt‑engineering tool.

## Main Features (Prototype)
- **Header** with brand wordmark, language selector (English / French), theme toggle (light / dark), and a login placeholder button.
- **Service selector** – two tabs: **Generate** and **Optimize**.
- **Generate workflow** – quick mode (single textarea) and advanced mode (optional fields: role, objective, context, constraints, output format, category).
- **Optimize workflow** – single textarea for an existing prompt.
- **Processing overlay** – simulated loading indicator with a short timeout.
- **Results interface** – shows original and refined prompts, a side‑by‑side comparison, token‑metric cards (demo values), and an explanatory section.
- **Theme system** – light theme by default, dark theme toggle persisting via `localStorage`.
- **Responsive design** – layout adapts for desktop, tablet, and mobile viewports.
- **Client‑side validation** – empty‑input warnings, error view with retry option.

## Target Users
- Prompt engineers and content creators who want a quick visual aid for structuring prompts.
- Product designers evaluating UI concepts for a prompt‑engineering SaaS.
- Developers looking for a vanilla‑JS example of a multi‑step interactive dashboard.

## Current Prototype Limitations
- **No real AI generation or optimization** – all results are static mock data.
- **Token metrics are illustrative**; they are labelled as “Demo data” and do not reflect actual token counts.
- **No backend, authentication, or persistence** beyond theme preference.
- **Language selector only changes UI text; it does not load external translations.
- **Clipboard actions are simulated in the browser only.
- **All data is lost on page reload** (except the chosen theme).

---
*The prototype is intentionally limited to front‑end behavior; any reference to AI services, token calculations, or storage is explicitly marked as simulated.*