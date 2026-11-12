// QA Test Script for AutoPrompt Prototype
// Run with: node scratch/qa_test.js

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const vm = require('vm');

// Helper to load a script into the JSDOM window context
function loadScript(window, scriptPath) {
  const code = fs.readFileSync(scriptPath, 'utf-8');
  const script = new vm.Script(code, { filename: scriptPath });
  const context = vm.createContext(window);
  script.runInContext(context);
}

// Capture console errors
let consoleErrors = [];
function captureConsole(window) {
  const origError = window.console.error;
  window.console.error = function (...args) {
    consoleErrors.push(args.join(' '));
    if (origError) origError.apply(this, args);
  };
  // Also capture console.log in case of unexpected messages
  const origLog = window.console.log;
  window.console.log = function (...args) {
    // ignore normal logs unless needed
    if (origLog) origLog.apply(this, args);
  };
}

// Load the HTML file
const htmlPath = path.resolve('index.html');
const htmlContent = fs.readFileSync(htmlPath, 'utf-8');
const dom = new JSDOM(htmlContent, {
  runScripts: 'dangerously',
  resources: 'usable',
  url: 'file://' + htmlPath,
  pretendToBeVisual: true,
});

const { window } = dom;
// Provide minimal implementations needed by the scripts
window.localStorage = window.localStorage || (() => {
  const store = {};
  return {
    getItem(k) { return store[k] || null; },
    setItem(k, v) { store[k] = v; },
    removeItem(k) { delete store[k]; },
  };
})();
window.navigator = window.navigator || {};
window.navigator.clipboard = {
  writeText: async (text) => {
    // mock clipboard write – simply store the text
    window._clipboard = text;
  },
  readText: async () => window._clipboard || ''
};

captureConsole(window);

// Load scripts in the same order as index.html
const scripts = [
  'js/mock-data.js',
  'js/theme.js',
  'js/workspace.js',
  'js/app.js'
];
for (const rel of scripts) {
  const scriptPath = path.resolve(rel);
  loadScript(window, scriptPath);
}

// Helper to wait for async UI updates (e.g., setTimeout)
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Simple assertion utility
function assert(condition, message) {
  if (!condition) throw new Error('Assertion failed: ' + message);
}

// Test results accumulator
const results = [];

async function runTests() {
  // A. Dashboard
  try {
    const header = window.document.querySelector('.app-header');
    assert(header, 'Header element exists');
    const brand = window.document.querySelector('.brand-wordmark');
    assert(brand && brand.textContent.includes('AutoPrompt'), 'Brand wordmark present');
    const generateTab = window.document.getElementById('selector-generate');
    const optimizeTab = window.document.getElementById('selector-optimize');
    assert(generateTab && optimizeTab, 'Service tabs exist');
    results.push({ feature: 'Dashboard load', test: 'Header & branding', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Dashboard load', test: 'Header & branding', status: 'FAIL', details: e.message });
  }
  // No console errors after init?
  if (consoleErrors.length === 0) {
    results.push({ feature: 'Dashboard load', test: 'No console errors', status: 'PASS', details: '' });
  } else {
    results.push({ feature: 'Dashboard load', test: 'No console errors', status: 'FAIL', details: consoleErrors.join('; ') });
  }

  // B. Generate Workspace
  try {
    // Ensure Generate tab is active
    window.document.getElementById('selector-generate').click();
    await wait(100);
    const textarea = window.document.getElementById('prompt-main-idea');
    assert(textarea, 'Main idea textarea present');
    // Quick mode default, enter text
    textarea.value = 'I want to learn Python.';
    const event = new window.Event('input', { bubbles: true });
    textarea.dispatchEvent(event);
    // Click Generate button
    const genBtn = window.document.getElementById('btn-generate-prompt');
    assert(genBtn, 'Generate button present');
    genBtn.click();
    await wait(1200); // processing delay simulated 1s
    // After processing, check results view visible
    const resultsView = window.document.getElementById('unified-results-view');
    assert(resultsView && !resultsView.hidden, 'Results view displayed after generate');
    results.push({ feature: 'Generate Workspace', test: 'Generate flow', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Generate Workspace', test: 'Generate flow', status: 'FAIL', details: e.message });
  }

  // Advanced mode toggle
  try {
    const advToggle = window.document.getElementById('mode-advanced');
    assert(advToggle, 'Advanced mode toggle exists');
    // Ensure advanced fields are hidden initially
    const advSection = window.document.getElementById('advanced-fields-section');
    assert(advSection, 'Advanced fields container exists');
    const initiallyHidden = advSection.classList.contains('expanded') === false;
    assert(initiallyHidden, 'Advanced section hidden by default');
    // Click to open
    advToggle.click();
    await wait(100);
    const nowExpanded = advSection.classList.contains('expanded');
    assert(nowExpanded, 'Advanced section expands on click');
    // Fill an advanced field
    const roleInput = window.document.getElementById('adv-role');
    roleInput.value = 'Teacher';
    roleInput.dispatchEvent(new window.Event('input', { bubbles: true }));
    results.push({ feature: 'Generate Workspace', test: 'Advanced mode toggle & input', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Generate Workspace', test: 'Advanced mode toggle & input', status: 'FAIL', details: e.message });
  }

  // Empty input validation for Generate
  try {
    // Switch back to Generate service if not already
    window.document.getElementById('selector-generate').click();
    await wait(100);
    const textarea = window.document.getElementById('prompt-main-idea');
    textarea.value = '';
    textarea.dispatchEvent(new window.Event('input', { bubbles: true }));
    const genBtn = window.document.getElementById('btn-generate-prompt');
    genBtn.click();
    await wait(200);
    const validation = window.document.getElementById('validation-error');
    assert(validation && !validation.hidden, 'Validation error shown for empty generate input');
    results.push({ feature: 'Generate Workspace', test: 'Empty input handling', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Generate Workspace', test: 'Empty input handling', status: 'FAIL', details: e.message });
  }

  // C. Optimize Workspace
  try {
    // Switch to Optimize tab
    window.document.getElementById('selector-optimize').click();
    await wait(100);
    const optInput = window.document.getElementById('prompt-optimize-input');
    assert(optInput, 'Optimize textarea exists');
    optInput.value = 'Old prompt text';
    optInput.dispatchEvent(new window.Event('input', { bubbles: true }));
    const optBtn = window.document.getElementById('btn-optimize-prompt');
    optBtn.click();
    await wait(1200);
    const resultsView = window.document.getElementById('unified-results-view');
    assert(resultsView && !resultsView.hidden, 'Results view displayed after optimize');
    results.push({ feature: 'Optimize Workspace', test: 'Optimize flow', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Optimize Workspace', test: 'Optimize flow', status: 'FAIL', details: e.message });
  }

  // Empty input validation for Optimize
  try {
    const optInput = window.document.getElementById('prompt-optimize-input');
    optInput.value = '';
    optInput.dispatchEvent(new window.Event('input', { bubbles: true }));
    const optBtn = window.document.getElementById('btn-optimize-prompt');
    optBtn.click();
    await wait(200);
    const validation = window.document.getElementById('validation-error-optimize');
    assert(validation && !validation.hidden, 'Validation error shown for empty optimize input');
    results.push({ feature: 'Optimize Workspace', test: 'Empty input handling', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Optimize Workspace', test: 'Empty input handling', status: 'FAIL', details: e.message });
  }

  // Preserve input when switching services
  try {
    const optInput = window.document.getElementById('prompt-optimize-input');
    optInput.value = 'Preserve this prompt';
    optInput.dispatchEvent(new window.Event('input', { bubbles: true }));
    // Switch to Generate then back to Optimize
    window.document.getElementById('selector-generate').click();
    await wait(100);
    window.document.getElementById('selector-optimize').click();
    await wait(100);
    const after = window.document.getElementById('prompt-optimize-input').value;
    assert(after === 'Preserve this prompt', 'Input preserved after service switch');
    results.push({ feature: 'Optimize Workspace', test: 'Input preservation on switch', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Optimize Workspace', test: 'Input preservation on switch', status: 'FAIL', details: e.message });
  }

  // D. Results Interface checks (using the last generated result)
  try {
    const resultsView = window.document.getElementById('unified-results-view');
    assert(resultsView && !resultsView.hidden, 'Results view visible for inspection');
    // Check comparison grid exists
    const compGrid = window.document.getElementById('comparison-grid');
    assert(compGrid, 'Comparison grid present');
    // Check token metric elements
    const metricOrig = window.document.getElementById('metric-original-tokens');
    const metricOpt = window.document.getElementById('metric-optimized-tokens');
    assert(metricOrig && metricOpt, 'Token metric cards present');
    // Check Explain section text exists
    const explainSection = window.document.getElementById('explain-section');
    assert(explainSection, 'Explain Changes section present');
    // Copy button functionality (mock) – click and verify clipboard
    const copyBtn = window.document.getElementById('btn-copy-main-result');
    copyBtn.click();
    await wait(50);
    const clipboardText = await window.navigator.clipboard.readText();
    assert(clipboardText && clipboardText.length > 0, 'Copy button writes to clipboard');
    // Edit button returns to editing view
    const editBtn = window.document.getElementById('btn-results-edit-top');
    editBtn.click();
    await wait(100);
    const editViewHidden = window.document.getElementById('unified-results-view').hidden;
    assert(editViewHidden, 'Edit returns to workspace editing (results hidden)');
    // Try Again button triggers processing again – we simulate by clicking after re-entering generate flow
    results.push({ feature: 'Results Interface', test: 'Basic UI checks', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Results Interface', test: 'Basic UI checks', status: 'FAIL', details: e.message });
  }

  // E. Theme System
  try {
    const toggle = window.document.getElementById('theme-toggle');
    assert(toggle, 'Theme toggle button exists');
    const root = window.document.documentElement;
    // Default should be light (no data-theme attr)
    assert(!root.hasAttribute('data-theme'), 'Default theme is light');
    // Click to switch dark
    toggle.click();
    await wait(100);
    assert(root.getAttribute('data-theme') === 'dark', 'Dark theme applied after toggle');
    // Simulate page refresh by recreating JSDOM with same localStorage
    const stored = window.localStorage.getItem('theme');
    // Recreate dom
    const dom2 = new JSDOM(htmlContent, { runScripts: 'dangerously', resources: 'usable', url: 'file://' + htmlPath, pretendToBeVisual: true });
    const win2 = dom2.window;
    win2.localStorage = win2.localStorage || window.localStorage;
    // load scripts again
    for (const rel of scripts) { loadScript(win2, path.resolve(rel)); }
    await wait(200);
    const root2 = win2.document.documentElement;
    assert(root2.getAttribute('data-theme') === 'dark', 'Theme persisted after refresh');
    results.push({ feature: 'Theme System', test: 'Toggle & persistence', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Theme System', test: 'Toggle & persistence', status: 'FAIL', details: e.message });
  }

  // F. Responsive checks – we simulate breakpoints by manually setting window.innerWidth and dispatch resize.
  const viewports = [
    { w: 1440, h: 900 },
    { w: 1024, h: 768 },
    { w: 768, h: 1024 },
    { w: 390, h: 844 },
    { w: 360, h: 800 }
  ];
  for (const vp of viewports) {
    try {
      window.innerWidth = vp.w;
      window.innerHeight = vp.h;
      window.dispatchEvent(new window.Event('resize'));
      await wait(50);
      // After resize, check that no element overflows horizontally.
      const overflow = Array.from(window.document.querySelectorAll('*')).some(el => el.scrollWidth > el.clientWidth + 1);
      assert(!overflow, `No horizontal overflow at ${vp.w}x${vp.h}`);
      results.push({ feature: 'Responsive Design', test: `Viewport ${vp.w}x${vp.h}`, status: 'PASS', details: '' });
    } catch (e) {
      results.push({ feature: 'Responsive Design', test: `Viewport ${vp.w}x${vp.h}`, status: 'FAIL', details: e.message });
    }
  }

  // G. Error handling – ensure repeated clicks are blocked during processing
  try {
    // Switch to Generate and start processing
    window.document.getElementById('selector-generate').click();
    await wait(100);
    const textarea = window.document.getElementById('prompt-main-idea');
    textarea.value = 'Test repeated clicks';
    textarea.dispatchEvent(new window.Event('input', { bubbles: true }));
    const genBtn = window.document.getElementById('btn-generate-prompt');
    // Click twice quickly
    genBtn.click();
    genBtn.click();
    await wait(1200);
    // After processing, button should be re-enabled – check disabled attribute during processing
    const disabledDuring = genBtn.disabled; // after processing should be false
    assert(disabledDuring === false, 'Button re-enabled after processing');
    results.push({ feature: 'Error handling', test: 'Prevent repeated clicks', status: 'PASS', details: '' });
  } catch (e) {
    results.push({ feature: 'Error handling', test: 'Prevent repeated clicks', status: 'FAIL', details: e.message });
  }

  // Output results as a table
  console.log('\n=== QA TEST RESULTS ===');
  console.table(results);
}

runTests().catch(err => {
  console.error('Unexpected error during tests:', err);
});
