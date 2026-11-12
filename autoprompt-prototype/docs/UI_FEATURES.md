# UI Features

## 1. Dashboard
- **Header** – displays the brand word‑mark, a language selector (English / French), a theme toggle button (light/dark), and a placeholder **Log In** button.
- **Service selector bar** – two tabs labelled **Generate** and **Optimize**. The active tab is highlighted and controls which workspace view is shown.
- The dashboard is responsive; on mobile the header actions stack vertically and the service tabs become full‑width stacked buttons.

## 2. Generate Workflow
- **Quick Mode** (default) – a single large textarea labelled *"Describe what you want AI to do"* with a character counter. The user types an idea and clicks **Generate Prompt**.
- **Advanced Mode** – toggled via a button. When opened an additional section appears with optional fields:
  - Role / Persona
  - Objective
  - Context
  - Constraints
  - Expected Output Format
- A **Category selector** dropdown lists several use‑case categories (Education, Programming, …). The field is optional.
- **Validation** – if the main textarea is empty, a red validation banner appears and the generate action is blocked.
- **Processing overlay** – after clicking Generate the UI shows a spinner with the message *"Working on your prompt…"* for a simulated 1 second.
- **Error view** – a developer toggle can force a simulated error; an accessible error card with a retry button appears.

## 3. Optimize Workflow
- A single textarea for pasting an existing prompt.
- Validation and processing behaviour mirrors the Generate workflow.
- The **Optimize** button triggers the same simulated processing overlay.
- Input is preserved when the user switches back to the Generate tab and returns.

## 4. Results Interface
- Appears after the simulated processing finishes for either service.
- **Header** – shows *"Your prompt is ready"* with a subtitle indicating whether the service was Generate or Optimize.
- **Original Prompt** – displayed in a read‑only block; a *"View Original"* toggle can expand/collapse it.
- **Generated / Optimized Prompt** – displayed in a separate block with a **Copy Prompt** button.
- **Token Metrics** – four cards (Original Tokens, Optimized Tokens, Tokens Saved, Reduction %). Values are static demo numbers and are labelled as “Demo data”.
- **Before / After Comparison** – side‑by‑side panels (desktop/tablet) or stacked (mobile) showing the original versus the refined prompt.
- **Explain Changes** – a static list of mock explanations (e.g., *Improved clarity*, *Removed unnecessary repetition*).
- Action buttons at the top and bottom:
  - **Edit** – returns the user to the workspace with all previous inputs restored.
  - **Try Again** – re‑runs the simulated processing.
  - **Copy** – copies the refined prompt to the clipboard.

## 5. Theme System
- Light theme is the default for first‑time visitors.
- The **theme toggle** swaps between Light and Dark by adding/removing the `[data‑theme="dark"]` attribute on the `<html>` element.
- Theme preference is stored in `localStorage` under the key `theme` and restored on page load.
- All colours, backgrounds, borders, and text use CSS custom properties (`--bg‑app`, `--text‑primary`, etc.). No hard‑coded whites remain in Dark mode.
- The toggle button is keyboard accessible (`Enter`/`Space`) and updates `aria‑pressed`.

## 6. Responsive Behaviour
- **Desktop (≥ 1024 px)** – full header, multi‑column metric grid, side‑by‑side comparison.
- **Tablet (768 – 1023 px)** – compact header, metric grid switches to two columns, workspace takes most of the width.
- **Mobile (< 768 px)** – header actions stack vertically, service tabs become full‑width stacked buttons, all inputs expand to 100 % width, advanced mode collapses by default, metric and comparison cards stack vertically, touch targets are ≥ 44 px.
- No horizontal scrolling occurs at any breakpoint; overflow is prevented via CSS (`overflow‑x: hidden` on `body`).

---
All of the above behaviours are implemented using **vanilla HTML, CSS, and JavaScript** – no frameworks or external libraries are required for the prototype.
