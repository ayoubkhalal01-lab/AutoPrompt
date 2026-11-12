# Setup Guide

## Prerequisites
- **Node.js** (v20 or later) – only needed if you want to run the optional test script or install additional packages. The prototype itself runs purely in the browser.
- **Git** (optional) – to clone the repository.
- A modern web browser (Chrome, Edge, Firefox, Safari) that supports ES6 modules and CSS custom properties.

## Getting the Project Locally
1. **Clone or copy the folder**
   ```bash
   git clone <repo‑url> autoprompt-prototype   # or copy the existing folder
   cd autoprompt-prototype
   ```
2. **(Optional) Install dev dependencies for testing**
   ```bash
   npm install   # installs jsdom for the QA script (requires PowerShell execution policy to allow npm scripts)
   ```
   *If you cannot run `npm` due to execution‑policy restrictions, you can still run the prototype without installing anything.*

## Running the Prototype
- Open `index.html` directly in a browser (double‑click the file or `file://` URL). No server is required because all assets are local.
- Alternatively, serve it via a simple static server (e.g., `npx serve .` or Python's `http.server`) to avoid CORS restrictions when loading fonts.

```bash
# Using Python (built‑in)
python -m http.server 8000
# then open http://localhost:8000 in your browser
```

## Browser Requirements
- **CSS Custom Properties** – for theme variables.
- **Flexbox / Grid** – used extensively for layout.
- **JavaScript ES6** – arrow functions, `const/let`, `classList`, `fetch` (not used here but present).
- **Clipboard API** – for the *Copy Prompt* button (supported in all modern browsers).

## Troubleshooting
| Symptom | Possible Cause | Fix |
|---------|----------------|-----|
| The page appears blank or styles are missing | `style.css` or `responsive.css` not loaded | Ensure the `<link>` tags in `index.html` point to `css/style.css` and `css/responsive.css` with the correct relative path. |
| Theme toggle does nothing | `localStorage` blocked or JavaScript error | Open DevTools console → look for errors. Make sure JavaScript is enabled and no extensions block `localStorage`. |
| Validation messages never show | The textarea IDs have changed | Verify that the elements have IDs `prompt-main-idea` (Generate) and `prompt-optimize-input` (Optimize) as expected. |
| Copy button does nothing | Clipboard permission denied | Some browsers require a user gesture; click the button directly. In headless environments (e.g., automated tests) the clipboard is mocked. |
| Responsive layout still scrolls horizontally on mobile | Old CSS cached | Hard‑refresh the page (`Ctrl+F5` or clear browser cache). |
| Running `npm install` fails on Windows | Execution‑policy blocks PowerShell scripts | Open PowerShell as Administrator and run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`, then retry `npm install`. |

---
Once the prototype is verified locally, you can proceed to the next phase (backend integration) using the **Future Integration** document.
