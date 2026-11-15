/**
 * AutoPrompt — Phase 6: Persistence Manager
 * Handles all saved prompts and history interactions with the backend API.
 *
 * Depends on:
 *   - WorkspaceManager (workspace.js) for lastRunData and switchService / updateCharCounters
 *   - #toast-container in the DOM
 *   - Modal structures defined in index.html
 */

(function (global) {
  'use strict';

  /**
   * Resolves the backend API base URL dynamically:
   * - window.AUTOPROMPT_API_URL if explicitly defined (takes precedence)
   * - '' (same-origin relative paths) when deployed on HTTPS (Vercel, custom domain)
   *   or non-localhost hosts, or when port is 8000 / 3000 (FastAPI or Vercel CLI)
   * - 'http://127.0.0.1:8000' only during local standalone development (e.g. port 5500 or file://)
   */
  function resolveApiBaseUrl() {
    if (typeof window !== 'undefined' && typeof window.AUTOPROMPT_API_URL === 'string') {
      return window.AUTOPROMPT_API_URL;
    }
    if (typeof window !== 'undefined' && window.location) {
      var protocol = window.location.protocol;
      var hostname = window.location.hostname;
      var port = window.location.port;

      if (protocol === 'https:') {
        return '';
      }
      if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
        return '';
      }
      if (port === '8000' || port === '3000') {
        return '';
      }
      return 'http://127.0.0.1:8000';
    }
    return '';
  }

  const API_BASE_URL = resolveApiBaseUrl();
  const TOAST_DURATION_MS = 3500;
  const SEARCH_DEBOUNCE_MS = 400;
  const CONTENT_SNIPPET_LENGTH = 220;
  const DEFAULT_PAGE_LIMIT = 20;

  const CATEGORIES = [
    'General',
    'Coding',
    'Data Science',
    'Academic',
    'Business',
    'Creative',
  ];

  // ─── Internal State ───────────────────────────────────────────────────────────
  let _pendingConfirmCallback = null;
  let _searchDebounceTimer = null;
  let _currentSaveOperationType = 'generate';

  // ─── Utility Helpers ──────────────────────────────────────────────────────────

  /**
   * Truncate a string to maxLen characters, appending '…' when trimmed.
   * @param {string} text
   * @param {number} maxLen
   * @returns {string}
   */
  function truncate(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.slice(0, maxLen) + '…' : text;
  }

  /**
   * Escape HTML special characters for safe insertion into innerHTML.
   * @param {string} str
   * @returns {string}
   */
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Format an ISO date string into a human-readable local date/time.
   * @param {string} isoString
   * @returns {string}
   */
  function formatDate(isoString) {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  }

  // ─── Toast Notifications ──────────────────────────────────────────────────────

  /**
   * Show a transient toast notification.
   * @param {string} message  - Text to display.
   * @param {'success'|'error'|'info'} type - Visual style.
   */
  function showToast(message, type) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast toast-' + (type || 'info');
    toast.setAttribute('role', 'alert');
    toast.textContent = message;

    container.appendChild(toast);

    // Trigger entry animation on next frame
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        toast.classList.add('toast-visible');
      });
    });

    setTimeout(() => {
      toast.classList.remove('toast-visible');
      toast.addEventListener('transitionend', () => toast.remove(), { once: true });
      // Fallback removal in case transition never fires
      setTimeout(() => toast.remove(), 600);
    }, TOAST_DURATION_MS);
  }

  // ─── Modal Helpers ────────────────────────────────────────────────────────────

  /**
   * Open a modal by removing its `hidden` attribute and trapping focus.
   * @param {string} modalId
   */
  function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.removeAttribute('hidden');
    // Focus the first interactive element for accessibility
    requestAnimationFrame(() => {
      const focusable = modal.querySelector(
        'input:not([type="hidden"]), select, textarea, button:not([disabled])'
      );
      if (focusable) focusable.focus();
    });
  }

  /**
   * Close a modal by setting its `hidden` attribute.
   * @param {string} modalId
   */
  function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.setAttribute('hidden', '');
  }

  /**
   * Close all persistence modals.
   */
  function closeAllModals() {
    [
      'modal-save-prompt',
      'modal-saved-prompts',
      'modal-prompt-history',
      'modal-edit-prompt',
      'modal-confirm-action',
    ].forEach(closeModal);
  }

  // ─── Badge Count ──────────────────────────────────────────────────────────────

  /**
   * Refresh the saved-prompts and history count badges in the nav bar.
   * Fetches only 1 item to get the total count without loading full data.
   */
  async function refreshBadgeCount() {
    // 1. Saved Prompts count badge
    try {
      const savedData = await apiFetch('/api/saved-prompts?limit=1&offset=0');
      const savedBadge = document.getElementById('saved-prompts-count-badge');
      if (savedBadge) {
        const total = (savedData && savedData.total) || 0;
        savedBadge.textContent = total > 99 ? '99+' : String(total);
        savedBadge.style.display = total > 0 ? 'inline-flex' : 'none';
      }
    } catch {
      // Silently ignore badge update failures
    }

    // 2. Prompt History count badge
    try {
      const histData = await apiFetch('/api/history?limit=1&offset=0');
      const histBadge = document.getElementById('history-count-badge');
      if (histBadge) {
        const total = (histData && histData.total) || 0;
        histBadge.textContent = total > 99 ? '99+' : String(total);
        histBadge.style.display = total > 0 ? 'inline-flex' : 'none';
      }
    } catch {
      // Silently ignore badge update failures
    }
  }

  // ─── API Communication ────────────────────────────────────────────────────────

  /**
   * Base fetch wrapper.
   * @param {string} path       - Relative path starting with /
   * @param {RequestInit} [opts] - Fetch options
   * @returns {Promise<any>}    - Parsed JSON or null for 204 No Content
   * @throws {Error} with a user-friendly message on failure
   */
  async function apiFetch(path, opts) {
    try {
      const response = await fetch(API_BASE_URL + path, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
      });

      if (response.status === 204) return null;

      let body;
      try {
        body = await response.json();
      } catch {
        body = null;
      }

      if (!response.ok) {
        const detail =
          (body && (body.detail || body.message)) ||
          `HTTP ${response.status} ${response.statusText}`;
        throw new Error(detail);
      }

      return body;
    } catch (err) {
      if (err instanceof TypeError) {
        // Network error (backend unreachable)
        throw new Error('Cannot reach the backend. Is the server running?');
      }
      throw err;
    }
  }

  // ── Saved Prompts API ──

  async function fetchSavedPrompts(search, category, operationType, limit, offset) {
    const params = new URLSearchParams();
    if (search && search.trim()) params.set('search', search.trim());
    if (category && category !== 'all') params.set('category', category);
    if (operationType && operationType !== 'all') params.set('operation_type', operationType);
    params.set('limit', String(limit || DEFAULT_PAGE_LIMIT));
    params.set('offset', String(offset || 0));
    return apiFetch('/api/saved-prompts?' + params.toString());
  }

  async function createSavedPrompt(title, content, category, operationType) {
    return apiFetch('/api/saved-prompts', {
      method: 'POST',
      body: JSON.stringify({
        title: title.trim(),
        content: content,
        category: category || null,
        operation_type: operationType || 'generate',
      }),
    });
  }

  async function updateSavedPrompt(id, title, category) {
    return apiFetch('/api/saved-prompts/' + id, {
      method: 'PUT',
      body: JSON.stringify({
        title: title.trim(),
        category: category || null,
      }),
    });
  }

  async function deleteSavedPrompt(id) {
    return apiFetch('/api/saved-prompts/' + id, { method: 'DELETE' });
  }

  // ── History API ──

  async function fetchHistory(operationType, limit, offset) {
    const params = new URLSearchParams();
    if (operationType && operationType !== 'all') params.set('operation_type', operationType);
    params.set('limit', String(limit || DEFAULT_PAGE_LIMIT));
    params.set('offset', String(offset || 0));
    return apiFetch('/api/history?' + params.toString());
  }

  async function deleteHistoryItem(id) {
    return apiFetch('/api/history/' + id, { method: 'DELETE' });
  }

  async function clearHistory() {
    return apiFetch('/api/history', { method: 'DELETE' });
  }

  // ─── Rendering ────────────────────────────────────────────────────────────────

  /**
   * Build the pill HTML for an operation type badge.
   * @param {'generate'|'optimize'} opType
   * @returns {string} HTML string
   */
  function renderOperationPill(opType) {
    const label = opType === 'optimize' ? 'Optimize' : 'Generate';
    const cls = opType === 'optimize' ? 'badge-optimize' : 'badge-generate';
    return `<span class="persistence-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  /**
   * Render a single saved-prompt card.
   * @param {Object} item
   * @returns {string} HTML string
   */
  function renderSavedPromptCard(item) {
    const snippet = escapeHtml(truncate(item.content, CONTENT_SNIPPET_LENGTH));
    const dateStr = escapeHtml(formatDate(item.created_at));
    const categoryBadge = item.category
      ? `<span class="persistence-badge badge-category">${escapeHtml(item.category)}</span>`
      : '';

    return `
      <div class="persistence-card" data-prompt-id="${item.id}">
        <div class="persistence-card-header">
          <span class="persistence-card-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</span>
          <div class="persistence-card-badges">
            ${renderOperationPill(item.operation_type)}
            ${categoryBadge}
          </div>
        </div>
        <p class="persistence-card-snippet">${snippet}</p>
        <div class="persistence-card-footer">
          <span class="persistence-card-date">${dateStr}</span>
          <div class="persistence-card-actions">
            <button
              class="btn btn-ghost btn-xs btn-use-prompt"
              data-id="${item.id}"
              data-operation="${escapeHtml(item.operation_type)}"
              data-content="${escapeHtml(item.content)}"
              title="Load this prompt into the workspace"
              type="button"
            >Use</button>
            <button
              class="btn btn-ghost btn-xs btn-edit-prompt"
              data-id="${item.id}"
              data-title="${escapeHtml(item.title)}"
              data-category="${escapeHtml(item.category || '')}"
              title="Edit title and category"
              type="button"
            >Edit</button>
            <button
              class="btn btn-ghost btn-xs btn-delete-prompt"
              data-id="${item.id}"
              data-title="${escapeHtml(item.title)}"
              title="Delete this saved prompt"
              type="button"
              style="color: var(--danger-color);"
            >Delete</button>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Render a single history card.
   * @param {Object} item
   * @returns {string} HTML string
   */
  function renderHistoryCard(item) {
    const inputSnippet = escapeHtml(truncate(item.original_input, 160));
    const outputSnippet = escapeHtml(
      truncate(item.generated_output || item.optimized_output || '', 160)
    );
    const dateStr = escapeHtml(formatDate(item.created_at));
    const modelStr = item.model_name ? escapeHtml(item.model_name) : '—';

    // Token metrics row — only shown when data is present
    let tokenRow = '';
    if (item.tokens_before != null || item.tokens_after != null) {
      const before = item.tokens_before != null ? item.tokens_before : '—';
      const after = item.tokens_after != null ? item.tokens_after : '—';
      let savedCell = '';
      if (item.tokens_saved != null) {
        const sign = item.tokens_saved > 0 ? '−' : item.tokens_saved < 0 ? '+' : '±';
        const absVal = Math.abs(item.tokens_saved);
        const cls = item.tokens_saved > 0
          ? 'token-saved-positive'
          : item.tokens_saved < 0
          ? 'token-saved-negative'
          : '';
        savedCell = `<span class="token-metric-item ${cls}">${sign}${absVal} tokens</span>`;
      }
      tokenRow = `
        <div class="history-token-row">
          <span class="token-metric-item">Before: <strong>${before}</strong></span>
          <span class="token-metric-item">After: <strong>${after}</strong></span>
          ${savedCell}
        </div>
      `;
    }

    return `
      <div class="persistence-card history-card" data-history-id="${item.id}">
        <div class="persistence-card-header">
          ${renderOperationPill(item.operation_type)}
          <span class="persistence-card-date" style="margin-left: auto;">${dateStr}</span>
        </div>
        <div class="history-snippets">
          <div class="history-snippet-block">
            <span class="history-snippet-label">Input</span>
            <p class="persistence-card-snippet">${inputSnippet}</p>
          </div>
          ${outputSnippet ? `
          <div class="history-snippet-block">
            <span class="history-snippet-label">Output</span>
            <p class="persistence-card-snippet">${outputSnippet}</p>
          </div>` : ''}
        </div>
        ${tokenRow}
        <div class="persistence-card-footer">
          <span class="token-metric-item" style="font-size: 0.75rem; color: var(--text-muted);">Model: ${modelStr}</span>
          <button
            class="btn btn-ghost btn-xs btn-delete-history"
            data-id="${item.id}"
            title="Delete this history entry"
            type="button"
            style="color: var(--danger-color);"
          >Delete</button>
        </div>
      </div>
    `;
  }

  // ─── Saved Prompts Modal ──────────────────────────────────────────────────────

  async function loadSavedPrompts() {
    const loadingEl = document.getElementById('saved-prompts-loading');
    const emptyEl = document.getElementById('saved-prompts-empty');
    const listEl = document.getElementById('saved-prompts-list-container');

    if (!listEl) return;

    // Show loading state
    if (loadingEl) loadingEl.removeAttribute('hidden');
    if (emptyEl) emptyEl.setAttribute('hidden', '');
    listEl.innerHTML = '';

    const search = (document.getElementById('input-search-saved') || {}).value || '';
    const category = (document.getElementById('select-filter-saved-category') || {}).value || 'all';
    const operationType = (document.getElementById('select-filter-saved-operation') || {}).value || 'all';

    try {
      const data = await fetchSavedPrompts(search, category, operationType, DEFAULT_PAGE_LIMIT, 0);
      if (loadingEl) loadingEl.setAttribute('hidden', '');

      if (!data || !data.items || data.items.length === 0) {
        if (emptyEl) emptyEl.removeAttribute('hidden');
        return;
      }

      listEl.innerHTML = data.items.map(renderSavedPromptCard).join('');
    } catch (err) {
      if (loadingEl) loadingEl.setAttribute('hidden', '');
      if (emptyEl) {
        emptyEl.removeAttribute('hidden');
        const msgEl = emptyEl.querySelector('p, .persistence-empty-text');
        if (msgEl) msgEl.textContent = 'Could not load saved prompts. Is the backend running?';
      }
      showToast(err.message || 'Failed to load saved prompts.', 'error');
    }
  }

  function openSavedPromptsModal() {
    openModal('modal-saved-prompts');
    loadSavedPrompts();
  }

  function closeSavedPromptsModal() {
    closeModal('modal-saved-prompts');
  }

  // ─── History Modal ────────────────────────────────────────────────────────────

  async function loadHistory() {
    const loadingEl = document.getElementById('history-loading');
    const emptyEl = document.getElementById('history-empty');
    const listEl = document.getElementById('history-list-container');

    if (!listEl) return;

    if (loadingEl) loadingEl.removeAttribute('hidden');
    if (emptyEl) emptyEl.setAttribute('hidden', '');
    listEl.innerHTML = '';

    const operationType = (document.getElementById('select-filter-history-operation') || {}).value || 'all';

    try {
      const data = await fetchHistory(operationType, DEFAULT_PAGE_LIMIT, 0);
      if (loadingEl) loadingEl.setAttribute('hidden', '');

      if (!data || !data.items || data.items.length === 0) {
        if (emptyEl) emptyEl.removeAttribute('hidden');
        return;
      }

      listEl.innerHTML = data.items.map(renderHistoryCard).join('');
    } catch (err) {
      if (loadingEl) loadingEl.setAttribute('hidden', '');
      if (emptyEl) {
        emptyEl.removeAttribute('hidden');
        const msgEl = emptyEl.querySelector('p, .persistence-empty-text');
        if (msgEl) msgEl.textContent = 'Could not load history. Is the backend running?';
      }
      showToast(err.message || 'Failed to load history.', 'error');
    }
  }

  function openHistoryModal() {
    openModal('modal-prompt-history');
    loadHistory();
  }

  function closeHistoryModal() {
    closeModal('modal-prompt-history');
  }

  // ─── Save Prompt Modal ────────────────────────────────────────────────────────

  /**
   * Open the save-prompt modal, pre-filling content and operation type.
   * @param {string} promptText
   * @param {'generate'|'optimize'} operationType
   * @param {string} [category]
   */
  function openSavePromptModal(promptText, operationType, category) {
    _currentSaveOperationType = operationType || 'generate';
    const contentEl = document.getElementById('preview-save-prompt-content');
    const titleEl = document.getElementById('input-save-prompt-title');
    const categoryEl = document.getElementById('select-save-prompt-category');
    const hiddenOpEl = document.getElementById('input-save-prompt-operation-type');

    if (contentEl) contentEl.value = promptText || '';
    if (titleEl) titleEl.value = '';
    if (categoryEl && category) {
      // Try to select the matching option; fall back to '' (blank)
      const opt = Array.from(categoryEl.options).find(
        (o) => o.value.toLowerCase() === (category || '').toLowerCase()
      );
      categoryEl.value = opt ? opt.value : '';
    }
    if (hiddenOpEl) hiddenOpEl.value = _currentSaveOperationType;

    openModal('modal-save-prompt');
  }

  function closeSavePromptModal() {
    closeModal('modal-save-prompt');
  }

  // ─── Edit Prompt Modal ────────────────────────────────────────────────────────

  function openEditModal(id, title, category) {
    const idEl = document.getElementById('input-edit-prompt-id');
    const titleEl = document.getElementById('input-edit-prompt-title');
    const categoryEl = document.getElementById('select-edit-prompt-category');

    if (idEl) idEl.value = String(id);
    if (titleEl) titleEl.value = title || '';
    if (categoryEl) {
      const opt = Array.from(categoryEl.options).find(
        (o) => o.value.toLowerCase() === (category || '').toLowerCase()
      );
      categoryEl.value = opt ? opt.value : '';
    }

    openModal('modal-edit-prompt');
  }

  function closeEditModal() {
    closeModal('modal-edit-prompt');
  }

  // ─── Confirm Action Modal ─────────────────────────────────────────────────────

  /**
   * Show the reusable confirmation dialog.
   * @param {string} title
   * @param {string} message
   * @param {Function} onConfirm - Called when the user clicks "Proceed".
   */
  function openConfirmModal(title, message, onConfirm) {
    const titleEl = document.getElementById('modal-confirm-title');
    const msgEl = document.getElementById('modal-confirm-message');

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;
    _pendingConfirmCallback = onConfirm;

    openModal('modal-confirm-action');
  }

  function closeConfirmModal() {
    closeModal('modal-confirm-action');
    _pendingConfirmCallback = null;
  }

  // ─── "Use in Workspace" Action ────────────────────────────────────────────────

  /**
   * Load a saved prompt into the appropriate workspace input.
   * @param {string} content
   * @param {'generate'|'optimize'} operationType
   */
  function usePromptInWorkspace(content, operationType) {
    const wm = global.WorkspaceManager;
    if (!wm) {
      showToast('Workspace not available.', 'error');
      return;
    }

    if (operationType === 'optimize') {
      const el = document.getElementById('prompt-optimize-input');
      if (el) el.value = content;
      if (typeof wm.switchService === 'function') wm.switchService('optimize');
    } else {
      const el = document.getElementById('prompt-main-idea');
      if (el) el.value = content;
      if (typeof wm.switchService === 'function') wm.switchService('generate');
    }

    if (typeof wm.updateCharCounters === 'function') wm.updateCharCounters();

    closeSavedPromptsModal();
    showToast('Prompt loaded into workspace.', 'success');
  }

  // ─── Event Delegation for Dynamic Cards ──────────────────────────────────────

  /**
   * Handle delegated clicks on saved-prompt cards (Use / Edit / Delete).
   * @param {MouseEvent} evt
   */
  function handleSavedPromptCardClick(evt) {
    const btn = evt.target.closest('button[data-id]');
    if (!btn) return;

    const id = parseInt(btn.dataset.id, 10);

    if (btn.classList.contains('btn-use-prompt')) {
      usePromptInWorkspace(btn.dataset.content, btn.dataset.operation);
    } else if (btn.classList.contains('btn-edit-prompt')) {
      openEditModal(id, btn.dataset.title, btn.dataset.category);
    } else if (btn.classList.contains('btn-delete-prompt')) {
      openConfirmModal(
        'Delete Saved Prompt',
        `Are you sure you want to delete "${btn.dataset.title || 'this prompt'}"? This cannot be undone.`,
        async () => {
          closeConfirmModal();
          try {
            await deleteSavedPrompt(id);
            showToast('Prompt deleted.', 'success');
            loadSavedPrompts();
            refreshBadgeCount();
          } catch (err) {
            showToast(err.message || 'Failed to delete prompt.', 'error');
          }
        }
      );
    }
  }

  /**
   * Handle delegated clicks on history cards (Delete).
   * @param {MouseEvent} evt
   */
  function handleHistoryCardClick(evt) {
    const btn = evt.target.closest('button.btn-delete-history');
    if (!btn) return;

    const id = parseInt(btn.dataset.id, 10);
    openConfirmModal(
      'Delete History Entry',
      'Are you sure you want to delete this history entry? This cannot be undone.',
      async () => {
        closeConfirmModal();
        try {
          await deleteHistoryItem(id);
          showToast('History entry deleted.', 'success');
          loadHistory();
          refreshBadgeCount();
        } catch (err) {
          showToast(err.message || 'Failed to delete history entry.', 'error');
        }
      }
    );
  }

  // ─── Category <select> Population ────────────────────────────────────────────

  /**
   * Populate a <select> element with standard category options.
   * @param {string} selectId
   * @param {boolean} [includeAll] - Whether to prepend an "All Categories" option.
   */
  function populateCategorySelect(selectId, includeAll) {
    const el = document.getElementById(selectId);
    if (!el) return;

    // Preserve any existing placeholder option (first option with empty value)
    const placeholder = el.options[0] && el.options[0].value === '' ? el.options[0] : null;
    el.innerHTML = '';

    if (includeAll) {
      const allOpt = document.createElement('option');
      allOpt.value = 'all';
      allOpt.textContent = 'All Categories';
      el.appendChild(allOpt);
    } else if (placeholder) {
      el.appendChild(placeholder);
    } else {
      const blankOpt = document.createElement('option');
      blankOpt.value = '';
      blankOpt.textContent = '— Select Category (optional) —';
      el.appendChild(blankOpt);
    }

    CATEGORIES.forEach((cat) => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat;
      el.appendChild(opt);
    });
  }

  // ─── Event Binding ────────────────────────────────────────────────────────────

  function bindEvents() {
    // ── Nav buttons ──
    bindClick('btn-nav-saved-prompts', openSavedPromptsModal);
    bindClick('btn-nav-history', openHistoryModal);

    // ── Save prompt trigger buttons (from results view) ──
    ['btn-results-save-top', 'btn-results-save-bottom', 'btn-save-main-result'].forEach((id) => {
      bindClick(id, () => {
        const wm = global.WorkspaceManager;
        const data = (wm && wm.lastRunData) || {};
        const text = data.resultText || '';
        const service = data.service || 'generate';
        const category = data.category || '';
        if (!text.trim()) {
          showToast('Nothing to save yet — run Generate or Optimize first.', 'info');
          return;
        }
        openSavePromptModal(text, service, category);
      });
    });

    // ── Save-prompt modal actions ──
    bindClick('btn-confirm-save-prompt', async () => {
      const titleEl = document.getElementById('input-save-prompt-title');
      const categoryEl = document.getElementById('select-save-prompt-category');
      const contentEl = document.getElementById('preview-save-prompt-content');
      const hiddenOpEl = document.getElementById('input-save-prompt-operation-type');

      const title = (titleEl && titleEl.value.trim()) || '';
      const category = (categoryEl && categoryEl.value) || '';
      const content = (contentEl && contentEl.value) || '';
      const operationType = (hiddenOpEl && hiddenOpEl.value) || _currentSaveOperationType || 'generate';

      if (!title) {
        showToast('Please enter a title for this prompt.', 'info');
        if (titleEl) titleEl.focus();
        return;
      }
      if (!content.trim()) {
        showToast('No prompt content to save.', 'error');
        return;
      }

      try {
        await createSavedPrompt(title, content, category || null, operationType);
        closeSavePromptModal();
        showToast('Prompt saved to your library!', 'success');
        refreshBadgeCount();
      } catch (err) {
        showToast(err.message || 'Failed to save prompt.', 'error');
      }
    });

    bindClick('btn-cancel-save-prompt', closeSavePromptModal);
    bindClick('btn-close-save-modal', closeSavePromptModal);

    // ── Saved-prompts list modal actions ──
    bindClick('btn-close-saved-list-modal', closeSavedPromptsModal);
    bindClick('btn-dismiss-saved-list', closeSavedPromptsModal);

    // Event delegation for card buttons inside saved-prompts list
    const savedListEl = document.getElementById('saved-prompts-list-container');
    if (savedListEl) {
      savedListEl.addEventListener('click', handleSavedPromptCardClick);
    }

    // ── Search and filter controls ──
    const searchInput = document.getElementById('input-search-saved');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        clearTimeout(_searchDebounceTimer);
        _searchDebounceTimer = setTimeout(loadSavedPrompts, SEARCH_DEBOUNCE_MS);
      });
    }

    const filterCategory = document.getElementById('select-filter-saved-category');
    if (filterCategory) filterCategory.addEventListener('change', loadSavedPrompts);

    const filterOperation = document.getElementById('select-filter-saved-operation');
    if (filterOperation) filterOperation.addEventListener('change', loadSavedPrompts);

    // ── History modal actions ──
    bindClick('btn-close-history-modal', closeHistoryModal);
    bindClick('btn-dismiss-history', closeHistoryModal);

    const historyListEl = document.getElementById('history-list-container');
    if (historyListEl) {
      historyListEl.addEventListener('click', handleHistoryCardClick);
    }

    const filterHistoryOp = document.getElementById('select-filter-history-operation');
    if (filterHistoryOp) filterHistoryOp.addEventListener('change', loadHistory);

    bindClick('btn-trigger-clear-history', () => {
      openConfirmModal(
        'Clear All History',
        'This will permanently delete all recorded Generate and Optimize history entries. This cannot be undone.',
        async () => {
          closeConfirmModal();
          try {
            await clearHistory();
            showToast('All history cleared.', 'success');
            loadHistory();
            refreshBadgeCount();
          } catch (err) {
            showToast(err.message || 'Failed to clear history.', 'error');
          }
        }
      );
    });

    // ── Edit prompt modal actions ──
    bindClick('btn-close-edit-modal', closeEditModal);
    bindClick('btn-cancel-edit-prompt', closeEditModal);

    bindClick('btn-confirm-edit-prompt', async () => {
      const idEl = document.getElementById('input-edit-prompt-id');
      const titleEl = document.getElementById('input-edit-prompt-title');
      const categoryEl = document.getElementById('select-edit-prompt-category');

      const id = idEl && parseInt(idEl.value, 10);
      const title = (titleEl && titleEl.value.trim()) || '';
      const category = (categoryEl && categoryEl.value) || '';

      if (!id) {
        showToast('No prompt selected for editing.', 'error');
        return;
      }
      if (!title) {
        showToast('Please enter a title.', 'info');
        if (titleEl) titleEl.focus();
        return;
      }

      try {
        await updateSavedPrompt(id, title, category || null);
        closeEditModal();
        showToast('Prompt updated.', 'success');
        loadSavedPrompts();
      } catch (err) {
        showToast(err.message || 'Failed to update prompt.', 'error');
      }
    });

    // ── Confirm action modal ──
    bindClick('btn-close-confirm-modal', closeConfirmModal);
    bindClick('btn-cancel-confirm', closeConfirmModal);

    bindClick('btn-proceed-confirm', () => {
      if (typeof _pendingConfirmCallback === 'function') {
        _pendingConfirmCallback();
      }
      // Callback is responsible for closing the modal
    });

    // ── Backdrop click to close (Escape is handled globally below) ──
    [
      { backdropId: 'modal-save-prompt', closeFn: closeSavePromptModal },
      { backdropId: 'modal-saved-prompts', closeFn: closeSavedPromptsModal },
      { backdropId: 'modal-prompt-history', closeFn: closeHistoryModal },
      { backdropId: 'modal-edit-prompt', closeFn: closeEditModal },
      { backdropId: 'modal-confirm-action', closeFn: closeConfirmModal },
    ].forEach(({ backdropId, closeFn }) => {
      const el = document.getElementById(backdropId);
      if (el) {
        el.addEventListener('click', (evt) => {
          // Only close if clicking the backdrop itself, not inner content
          if (evt.target === el) closeFn();
        });
      }
    });

    // ── Global Escape key ──
    document.addEventListener('keydown', (evt) => {
      if (evt.key !== 'Escape') return;
      // Close whichever modal is open (innermost first)
      const order = [
        { id: 'modal-confirm-action', fn: closeConfirmModal },
        { id: 'modal-edit-prompt', fn: closeEditModal },
        { id: 'modal-save-prompt', fn: closeSavePromptModal },
        { id: 'modal-saved-prompts', fn: closeSavedPromptsModal },
        { id: 'modal-prompt-history', fn: closeHistoryModal },
      ];
      for (const { id, fn } of order) {
        const el = document.getElementById(id);
        if (el && !el.hasAttribute('hidden')) {
          fn();
          break;
        }
      }
    });
  }

  // ─── Utility: safe bindClick ──────────────────────────────────────────────────

  /**
   * Attach a click handler to an element by ID (no-op if not found).
   * @param {string} id
   * @param {Function} handler
   */
  function bindClick(id, handler) {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', handler);
  }

  // ─── Initialisation ───────────────────────────────────────────────────────────

  function init() {
    // Populate category selects
    populateCategorySelect('select-save-prompt-category', false);
    populateCategorySelect('select-edit-prompt-category', false);
    populateCategorySelect('select-filter-saved-category', true);

    bindEvents();
    refreshBadgeCount();
  }

  // ─── Public API ───────────────────────────────────────────────────────────────

  global.PersistenceManager = {
    // Modal openers (useful for external callers)
    openSavePromptModal,
    openSavedPromptsModal,
    openHistoryModal,
    // Toast (useful for workspace.js or app.js to surface messages)
    showToast,
    // Badge refresh (call after operations in workspace.js if needed)
    refreshBadgeCount,
  };

  // Boot on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
