# Project Structure

```
autoprompt-prototype/
├─ index.html                # Main entry point (HTML shell)
├─ css/
│   ├─ style.css            # Core design system, variables, base styles, transitions
│   └─ responsive.css       # Media‑queries for desktop, tablet, mobile
├─ js/
│   ├─ mock-data.js         # Small static data used for demo prompts and token metrics
│   ├─ theme.js             # Light/Dark theme toggle, persistence via localStorage
│   ├─ workspace.js         # State machine for the Generate & Optimize services
│   └─ app.js               # Application bootstrap – binds UI events, initializes ThemeManager
├─ assets/
│   └─ icons/…              # SVG/icon assets referenced in the UI
├─ docs/                     # Documentation (this folder)
│   ├─ PROJECT_OVERVIEW.md
│   ├─ PROJECT_STRUCTURE.md
│   ├─ UI_FEATURES.md
│   ├─ TESTING_REPORT.md
│   ├─ SETUP_GUIDE.md
│   └─ FUTURE_INTEGRATION.md
└─ scratch/                  # Temporary scripts (e.g., QA test script)
    └─ qa_test.js
```

## File Descriptions
| Path | Purpose |
|------|---------|
| **index.html** | Minimal HTML shell loading the two CSS files and four JavaScript modules (deferred). Contains the header, dashboard, workspace cards, processing overlay, error view, and results view. |
| **css/style.css** | Defines CSS custom properties (design tokens, colour palette, spacing, radii). Holds reset, base component styles, transitions, and dark‑theme overrides. |
| **css/responsive.css** | Media‑queries for the three break‑points (desktop ≥ 1024 px, tablet 768‑1023 px, mobile < 768 px). Adjusts layout, padding, grid columns, and header actions to ensure no horizontal overflow. |
| **js/mock-data.js** | Provides static objects that mimic generated prompts, token counts, and explanatory text. No network calls. |
| **js/theme.js** | Exposes `ThemeManager` on `window`. Handles toggle clicks, keyboard interaction, `aria‑pressed` updates, stores the selected theme in `localStorage`, and applies the appropriate `[data‑theme]` attribute. |
| **js/workspace.js** | Central state manager (`WorkspaceManager`). Manages service selection (Generate/Optimize), mode (quick/advanced), UI validation, simulated processing (`setTimeout`), error handling, results rendering, and navigation between views. All UI updates are performed via DOM manipulation – no framework. |
| **js/app.js** | Entry point called after DOM is ready. Instantiates `ThemeManager` and `WorkspaceManager`, then calls their `init` methods. |
| **assets/icons/** | SVG icons used for language selector, theme toggle (sun/moon), service tabs, processing spinner, and error icon. |
| **scratch/qa_test.js** | Temporary test script (uses `jsdom`) that programmatically verifies UI behaviour, validation, theme persistence, and responsive overflow checks. Not part of the production bundle. |
| **docs/** | Contains all delivery documentation (this folder). |

## Main JavaScript Responsibilities
- **theme.js** – Theme toggling, persistence, ARIA handling, and smooth CSS transitions.
- **workspace.js** – All interactive logic: service tab switching, quick/advanced mode handling, form validation, simulated processing flow, error view, result rendering, copy‑to‑clipboard, and UI state restoration.
- **app.js** – Application bootstrap; wires up the theme and workspace managers.
- **mock-data.js** – Supplies static demo data for the results view (prompt text, token metrics, explanations).