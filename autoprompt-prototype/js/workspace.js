/**
 * AutoPrompt — Phase 5.3B: Frontend–Backend Integration
 * Workspace Interaction Module (workspace.js)
 * 
 * Manages full lifecycle and state transitions for Generate and Optimize services:
 * - States: 'idle' | 'processing' | 'success' | 'error'
 * - Prevention of repeated submissions & double-click protection
 * - Real async API calls to FastAPI backend (http://127.0.0.1:8000)
 * - Complete Results Interface:
 *   - Results Header with service indication & response time
 *   - Original Prompt preservation & View Original toggle
 *   - Final prompt display with Copy action
 *   - 4 Token Analysis metric cards (real backend data, accurate negative savings)
 *   - Before / After Comparison panels
 *   - "What changed and why?" explanations
 *   - Edit, Try Again, and Copy actions
 * - Token counting via /api/count-tokens with debounce
 * - Keyboard accessibility (Ctrl+Enter, focus restoration, aria attributes)
 * - Multilingual UI support (English / French)
 */

(function (root) {
  'use strict';

  // Constants
  const SERVICE_GENERATE = 'generate';
  const SERVICE_OPTIMIZE = 'optimize';

  const MODE_QUICK = 'quick';
  const MODE_ADVANCED = 'advanced';

  const STATE_IDLE = 'idle';
  const STATE_PROCESSING = 'processing';
  const STATE_SUCCESS = 'success';
  const STATE_ERROR = 'error';

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

  // Token count debounce delay in milliseconds
  const TOKEN_COUNT_DEBOUNCE_MS = 600;

  // Request timeout in milliseconds (45 seconds for Gemini thinking latency)
  const REQUEST_TIMEOUT_MS = 45000;

  const WorkspaceManager = {
    // Current runtime states
    activeService: SERVICE_GENERATE,
    activeModeGenerate: MODE_QUICK,
    activeModeOptimize: MODE_QUICK,
    currentState: STATE_IDLE,
    currentLang: 'en',
    isProcessing: false,
    simulateError: false,

    // Token count debounce timers
    _tokenCountTimerGenerate: null,
    _tokenCountTimerOptimize: null,

    // Store active run results
    lastRunData: {
      service: SERVICE_GENERATE,
      originalText: '',
      resultText: '',
      category: '',
      metrics: null,
      responseTimeMs: 0
    },

    // Cached DOM elements
    elements: {},

    /**
     * Initializes all workspace events, modes, and default states.
     */
    init: function () {
      this.cacheElements();
      this.bindServiceSelectors();
      this.bindModeSelectors();
      this.bindInputEvents();
      this.bindActionButtons();
      this.bindResultsActions();
      this.bindLanguageSelector();
      this.bindDevErrorToggle();

      // Set initial defaults
      this.switchService(SERVICE_GENERATE);
      this.switchMode(SERVICE_GENERATE, MODE_QUICK);
      this.switchMode(SERVICE_OPTIMIZE, MODE_QUICK);
      this.updateCharCounters();
      this.transitionToState(STATE_IDLE);
    },

    /**
     * Cache all key DOM elements.
     */
    cacheElements: function () {
      this.elements = {
        // Workspace Shell & Tabs
        workspaceCard: document.getElementById('main-workspace-card'),
        selectorGenerate: document.getElementById('selector-generate'),
        selectorOptimize: document.getElementById('selector-optimize'),
        serviceStatusDot: document.getElementById('service-status-dot'),
        serviceStatusText: document.getElementById('service-status-text'),

        // Service Views & Forms
        viewGenerate: document.getElementById('view-generate'),
        viewOptimize: document.getElementById('view-optimize'),
        generateFormContainer: document.getElementById('generate-form-container'),
        optimizeFormContainer: document.getElementById('optimize-form-container'),

        // Unified Processing & Error Views
        unifiedProcessingView: document.getElementById('unified-processing-view'),
        processingServiceLabel: document.getElementById('processing-service-label'),
        unifiedErrorView: document.getElementById('unified-error-view'),
        errorDescription: document.getElementById('error-description'),
        btnRetryProcess: document.getElementById('btn-retry-process'),
        btnReturnEditError: document.getElementById('btn-return-edit-error'),
        toggleSimError: document.getElementById('toggle-sim-error'),

        // Complete Results Interface
        unifiedResultsView: document.getElementById('unified-results-view'),
        resultsServiceBadge: document.getElementById('results-service-badge'),
        resultsSubtitle: document.getElementById('results-subtitle'),
        resultsFinalPromptText: document.getElementById('results-final-prompt-text'),
        resultsOriginalPromptText: document.getElementById('results-original-prompt-text'),
        resultsComparisonRefinedText: document.getElementById('results-comparison-refined-text'),
        metricOriginalTokens: document.getElementById('metric-original-tokens'),
        metricOptimizedTokens: document.getElementById('metric-optimized-tokens'),
        metricTokensSaved: document.getElementById('metric-tokens-saved'),
        metricReductionPercent: document.getElementById('metric-reduction-percent'),
        labelMetric1: document.getElementById('label-metric-1'),
        subtextMetric1: document.getElementById('subtext-metric-1'),
        labelMetric2: document.getElementById('label-metric-2'),
        subtextMetric2: document.getElementById('subtext-metric-2'),
        labelMetric3: document.getElementById('label-metric-3'),
        subtextMetric3: document.getElementById('subtext-metric-3'),
        labelMetric4: document.getElementById('label-metric-4'),
        subtextMetric4: document.getElementById('subtext-metric-4'),
        comparisonGrid: document.getElementById('comparison-grid'),
        colOriginalPrompt: document.getElementById('col-original-prompt'),
        btnToggleViewOriginal: document.getElementById('btn-toggle-view-original'),
        toggleOriginalText: document.getElementById('toggle-original-text'),

        // Results Action Buttons
        btnResultsCopyTop: document.getElementById('btn-results-copy-top'),
        btnResultsEditTop: document.getElementById('btn-results-edit-top'),
        btnResultsTryAgainTop: document.getElementById('btn-results-try-again-top'),
        btnCopyMainResult: document.getElementById('btn-copy-main-result'),
        btnResultsCopyBottom: document.getElementById('btn-results-copy-bottom'),
        btnResultsEditBottom: document.getElementById('btn-results-edit-bottom'),
        btnResultsTryAgainBottom: document.getElementById('btn-results-try-again-bottom'),

        // Generate Controls
        modeQuick: document.getElementById('mode-quick'),
        modeAdvanced: document.getElementById('mode-advanced'),
        advancedSection: document.getElementById('advanced-fields-section'),
        promptCategory: document.getElementById('prompt-category'),
        promptMainIdea: document.getElementById('prompt-main-idea'),
        charCounter: document.getElementById('char-counter'),
        validationError: document.getElementById('validation-error'),
        validationErrorText: document.getElementById('validation-error-text'),
        advRole: document.getElementById('adv-role'),
        advObjective: document.getElementById('adv-objective'),
        advContext: document.getElementById('adv-context'),
        advConstraints: document.getElementById('adv-constraints'),
        advFormat: document.getElementById('adv-format'),
        btnGenerate: document.getElementById('btn-generate-prompt'),
        btnClearGenerate: document.getElementById('btn-clear-generate'),

        // Optimize Controls
        modeQuickOptimize: document.getElementById('mode-quick-optimize'),
        modeAdvancedOptimize: document.getElementById('mode-advanced-optimize'),
        advancedSectionOptimize: document.getElementById('advanced-fields-section-optimize'),
        advOptimizeInstructions: document.getElementById('adv-optimize-instructions'),
        promptOptimizeInput: document.getElementById('prompt-optimize-input'),
        charCounterOptimize: document.getElementById('char-counter-optimize'),
        validationErrorOptimize: document.getElementById('validation-error-optimize'),
        validationErrorOptimizeText: document.getElementById('validation-error-optimize-text'),
        btnOptimize: document.getElementById('btn-optimize-prompt'),
        btnClearOptimize: document.getElementById('btn-clear-optimize'),

        // Header controls
        langSelect: document.getElementById('lang-select')
      };
    },

    /**
     * Binds click events to Service selectors (Generate vs. Optimize).
     */
    bindServiceSelectors: function () {
      const { selectorGenerate, selectorOptimize } = this.elements;

      if (selectorGenerate) {
        selectorGenerate.addEventListener('click', () => {
          if (this.isProcessing) return;
          this.switchService(SERVICE_GENERATE);
        });
      }

      if (selectorOptimize) {
        selectorOptimize.addEventListener('click', () => {
          if (this.isProcessing) return;
          this.switchService(SERVICE_OPTIMIZE);
        });
      }
    },

    /**
     * Switches between Generate and Optimize services, preserving all input data.
     * @param {string} service - 'generate' | 'optimize'
     */
    switchService: function (service) {
      if (service !== SERVICE_GENERATE && service !== SERVICE_OPTIMIZE) return;
      this.activeService = service;

      const {
        selectorGenerate,
        selectorOptimize,
        viewGenerate,
        viewOptimize
      } = this.elements;

      const isGenerate = service === SERVICE_GENERATE;

      if (selectorGenerate) {
        selectorGenerate.classList.toggle('active', isGenerate);
        selectorGenerate.setAttribute('aria-selected', isGenerate ? 'true' : 'false');
      }

      if (selectorOptimize) {
        selectorOptimize.classList.toggle('active', !isGenerate);
        selectorOptimize.setAttribute('aria-selected', !isGenerate ? 'true' : 'false');
      }

      if (viewGenerate) {
        viewGenerate.classList.toggle('active', isGenerate);
        viewGenerate.hidden = !isGenerate;
      }

      if (viewOptimize) {
        viewOptimize.classList.toggle('active', !isGenerate);
        viewOptimize.hidden = isGenerate;
      }

      // If we are currently in results or error, return to idle view of new service
      this.transitionToState(STATE_IDLE);
      this.updateStatusPill();
    },

    /**
     * Binds mode selection events for both Generate and Optimize.
     */
    bindModeSelectors: function () {
      // Generate Mode Selectors
      const { modeQuick, modeAdvanced } = this.elements;

      if (modeQuick) {
        modeQuick.addEventListener('click', () => {
          if (!this.isProcessing) this.switchMode(SERVICE_GENERATE, MODE_QUICK);
        });
        modeQuick.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            this.switchMode(SERVICE_GENERATE, MODE_ADVANCED);
            modeAdvanced.focus();
          }
        });
      }

      if (modeAdvanced) {
        modeAdvanced.addEventListener('click', () => {
          if (!this.isProcessing) this.switchMode(SERVICE_GENERATE, MODE_ADVANCED);
        });
        modeAdvanced.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            this.switchMode(SERVICE_GENERATE, MODE_QUICK);
            modeQuick.focus();
          }
        });
      }

      // Optimize Mode Selectors
      const { modeQuickOptimize, modeAdvancedOptimize } = this.elements;

      if (modeQuickOptimize) {
        modeQuickOptimize.addEventListener('click', () => {
          if (!this.isProcessing) this.switchMode(SERVICE_OPTIMIZE, MODE_QUICK);
        });
        modeQuickOptimize.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            this.switchMode(SERVICE_OPTIMIZE, MODE_ADVANCED);
            modeAdvancedOptimize.focus();
          }
        });
      }

      if (modeAdvancedOptimize) {
        modeAdvancedOptimize.addEventListener('click', () => {
          if (!this.isProcessing) this.switchMode(SERVICE_OPTIMIZE, MODE_ADVANCED);
        });
        modeAdvancedOptimize.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            this.switchMode(SERVICE_OPTIMIZE, MODE_QUICK);
            modeQuickOptimize.focus();
          }
        });
      }
    },

    /**
     * Switches mode and toggles expandable section while preserving all user inputs.
     * @param {string} service - 'generate' | 'optimize'
     * @param {string} mode - 'quick' | 'advanced'
     */
    switchMode: function (service, mode) {
      if (typeof service === 'string' && (service === MODE_QUICK || service === MODE_ADVANCED)) {
        // Polymorphic overload: switchMode(mode) defaults to active service
        mode = service;
        service = this.activeService;
      }

      const isAdvanced = mode === MODE_ADVANCED;

      if (service === SERVICE_GENERATE) {
        this.activeModeGenerate = mode;
        const { modeQuick, modeAdvanced, advancedSection } = this.elements;

        if (modeQuick) {
          modeQuick.classList.toggle('active', !isAdvanced);
          modeQuick.setAttribute('aria-checked', !isAdvanced ? 'true' : 'false');
        }
        if (modeAdvanced) {
          modeAdvanced.classList.toggle('active', isAdvanced);
          modeAdvanced.setAttribute('aria-checked', isAdvanced ? 'true' : 'false');
        }
        if (advancedSection) {
          advancedSection.classList.toggle('collapsed', !isAdvanced);
          advancedSection.setAttribute('aria-hidden', !isAdvanced ? 'true' : 'false');
        }
      } else {
        this.activeModeOptimize = mode;
        const { modeQuickOptimize, modeAdvancedOptimize, advancedSectionOptimize } = this.elements;

        if (modeQuickOptimize) {
          modeQuickOptimize.classList.toggle('active', !isAdvanced);
          modeQuickOptimize.setAttribute('aria-checked', !isAdvanced ? 'true' : 'false');
        }
        if (modeAdvancedOptimize) {
          modeAdvancedOptimize.classList.toggle('active', isAdvanced);
          modeAdvancedOptimize.setAttribute('aria-checked', isAdvanced ? 'true' : 'false');
        }
        if (advancedSectionOptimize) {
          advancedSectionOptimize.classList.toggle('collapsed', !isAdvanced);
          advancedSectionOptimize.setAttribute('aria-hidden', !isAdvanced ? 'true' : 'false');
        }
      }
    },

    /**
     * Binds textarea and input events for live character counting, validation reset,
     * and debounced token counting.
     */
    bindInputEvents: function () {
      const { promptMainIdea, promptOptimizeInput } = this.elements;

      if (promptMainIdea) {
        promptMainIdea.addEventListener('input', () => {
          this.updateCharCounters();
          this.clearValidationError(SERVICE_GENERATE);
          this._debouncedTokenCount(SERVICE_GENERATE);
        });

        promptMainIdea.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            this.handleGenerate();
          }
        });
      }

      if (promptOptimizeInput) {
        promptOptimizeInput.addEventListener('input', () => {
          this.updateCharCounters();
          this.clearValidationError(SERVICE_OPTIMIZE);
          this._debouncedTokenCount(SERVICE_OPTIMIZE);
        });

        promptOptimizeInput.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            this.handleOptimize();
          }
        });
      }
    },

    /**
     * Debounced token counting — avoids sending a request on every keystroke.
     * @param {string} service - 'generate' | 'optimize'
     */
    _debouncedTokenCount: function (service) {
      if (service === SERVICE_GENERATE) {
        if (this._tokenCountTimerGenerate) clearTimeout(this._tokenCountTimerGenerate);
        this._tokenCountTimerGenerate = setTimeout(() => {
          const text = this.elements.promptMainIdea ? this.elements.promptMainIdea.value.trim() : '';
          if (text.length > 0) {
            this._fetchTokenCount(text, this.elements.charCounter);
          }
        }, TOKEN_COUNT_DEBOUNCE_MS);
      } else {
        if (this._tokenCountTimerOptimize) clearTimeout(this._tokenCountTimerOptimize);
        this._tokenCountTimerOptimize = setTimeout(() => {
          const text = this.elements.promptOptimizeInput ? this.elements.promptOptimizeInput.value.trim() : '';
          if (text.length > 0) {
            this._fetchTokenCount(text, this.elements.charCounterOptimize);
          }
        }, TOKEN_COUNT_DEBOUNCE_MS);
      }
    },

    /**
     * Fetches real token count from the backend and updates the counter display.
     * @param {string} text - Text to count tokens for
     * @param {HTMLElement} counterEl - The counter element to update
     */
    _fetchTokenCount: function (text, counterEl) {
      if (!counterEl || !text) return;

      var self = this;
      fetch(API_BASE_URL + '/api/count-tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.success && typeof data.token_count === 'number') {
          var charLen = text.length;
          var tokenLabel = self.currentLang === 'fr' ? 'tokens' : 'tokens';
          var charLabel = self.currentLang === 'fr' ? 'caractères' : 'characters';
          counterEl.textContent = charLen.toLocaleString() + ' ' + charLabel + ' · ' + data.token_count.toLocaleString() + ' ' + tokenLabel;
        }
      })
      .catch(function () {
        // Silently fail — character count is already displayed via updateCharCounters
      });
    },

    /**
     * Updates character counters for both Generate and Optimize inputs.
     */
    updateCharCounters: function () {
      const { promptMainIdea, charCounter, promptOptimizeInput, charCounterOptimize } = this.elements;

      if (charCounter && promptMainIdea) {
        const len = promptMainIdea.value.length;
        charCounter.textContent = this.currentLang === 'fr'
          ? `${len.toLocaleString()} caractère${len !== 1 ? 's' : ''}`
          : `${len.toLocaleString()} character${len !== 1 ? 's' : ''}`;
      }

      if (charCounterOptimize && promptOptimizeInput) {
        const len = promptOptimizeInput.value.length;
        charCounterOptimize.textContent = this.currentLang === 'fr'
          ? `${len.toLocaleString()} caractère${len !== 1 ? 's' : ''}`
          : `${len.toLocaleString()} character${len !== 1 ? 's' : ''}`;
      }
    },

    /**
     * Clears validation error messages and styling for a given service.
     * @param {string} service
     */
    clearValidationError: function (service) {
      if (service === SERVICE_GENERATE) {
        const { promptMainIdea, validationError } = this.elements;
        if (promptMainIdea) promptMainIdea.classList.remove('has-error');
        if (validationError) validationError.hidden = true;
      } else if (service === SERVICE_OPTIMIZE) {
        const { promptOptimizeInput, validationErrorOptimize } = this.elements;
        if (promptOptimizeInput) promptOptimizeInput.classList.remove('has-error');
        if (validationErrorOptimize) validationErrorOptimize.hidden = true;
      }
    },

    /**
     * Displays a validation error message for a given service.
     * @param {string} service
     * @param {string} message
     */
    showValidationError: function (service, message) {
      if (service === SERVICE_GENERATE) {
        const { promptMainIdea, validationError, validationErrorText } = this.elements;
        if (promptMainIdea) {
          promptMainIdea.classList.add('has-error');
          promptMainIdea.focus();
        }
        if (validationError && validationErrorText) {
          validationErrorText.textContent = message;
          validationError.hidden = false;
        }
      } else if (service === SERVICE_OPTIMIZE) {
        const { promptOptimizeInput, validationErrorOptimize, validationErrorOptimizeText } = this.elements;
        if (promptOptimizeInput) {
          promptOptimizeInput.classList.add('has-error');
          promptOptimizeInput.focus();
        }
        if (validationErrorOptimize && validationErrorOptimizeText) {
          validationErrorOptimizeText.textContent = message;
          validationErrorOptimize.hidden = false;
        }
      }
    },

    /**
     * Binds primary form action buttons (Generate, Optimize, Clear, Retry).
     */
    bindActionButtons: function () {
      const {
        btnGenerate,
        btnOptimize,
        btnClearGenerate,
        btnClearOptimize,
        btnRetryProcess,
        btnReturnEditError
      } = this.elements;

      if (btnGenerate) {
        btnGenerate.addEventListener('click', () => this.handleGenerate());
      }

      if (btnOptimize) {
        btnOptimize.addEventListener('click', () => this.handleOptimize());
      }

      if (btnClearGenerate) {
        btnClearGenerate.addEventListener('click', () => this.handleClearGenerate());
      }

      if (btnClearOptimize) {
        btnClearOptimize.addEventListener('click', () => this.handleClearOptimize());
      }

      if (btnRetryProcess) {
        btnRetryProcess.addEventListener('click', () => this.handleRetry());
      }

      if (btnReturnEditError) {
        btnReturnEditError.addEventListener('click', () => this.transitionToState(STATE_IDLE));
      }
    },

    /**
     * Binds Results Interface action buttons (Copy, Edit, Try Again, View Original).
     */
    bindResultsActions: function () {
      const {
        btnResultsCopyTop,
        btnResultsCopyBottom,
        btnCopyMainResult,
        btnResultsEditTop,
        btnResultsEditBottom,
        btnResultsTryAgainTop,
        btnResultsTryAgainBottom,
        btnToggleViewOriginal
      } = this.elements;

      // Copy actions (all copy buttons trigger unified copy feedback)
      const copyHandler = () => this.handleCopyCurrentResult();
      if (btnResultsCopyTop) btnResultsCopyTop.addEventListener('click', copyHandler);
      if (btnResultsCopyBottom) btnResultsCopyBottom.addEventListener('click', copyHandler);
      if (btnCopyMainResult) btnCopyMainResult.addEventListener('click', copyHandler);

      // Edit actions (return to the input workspace preserving text)
      const editHandler = () => this.transitionToState(STATE_IDLE);
      if (btnResultsEditTop) btnResultsEditTop.addEventListener('click', editHandler);
      if (btnResultsEditBottom) btnResultsEditBottom.addEventListener('click', editHandler);

      // Try Again actions (re-run processing with existing inputs)
      const tryAgainHandler = () => this.handleTryAgain();
      if (btnResultsTryAgainTop) btnResultsTryAgainTop.addEventListener('click', tryAgainHandler);
      if (btnResultsTryAgainBottom) btnResultsTryAgainBottom.addEventListener('click', tryAgainHandler);

      // View Original toggle button
      if (btnToggleViewOriginal) {
        btnToggleViewOriginal.addEventListener('click', () => this.toggleViewOriginal());
      }
    },

    /**
     * Binds the Dev Error toggle in footer.
     */
    bindDevErrorToggle: function () {
      const { toggleSimError } = this.elements;
      if (toggleSimError) {
        toggleSimError.addEventListener('change', (e) => {
          this.simulateError = e.target.checked;
        });
      }
    },

    /**
     * Helper to programmatically toggle simulated error for testing.
     * @param {boolean} value
     */
    setSimulateError: function (value) {
      this.simulateError = Boolean(value);
      if (this.elements.toggleSimError) {
        this.elements.toggleSimError.checked = this.simulateError;
      }
    },

    /**
     * Centralized State Transition Engine.
     * Manages 'idle' | 'processing' | 'success' | 'error'.
     * @param {string} newState
     */
    transitionToState: function (newState) {
      this.currentState = newState;
      const {
        workspaceCard,
        unifiedProcessingView,
        unifiedErrorView,
        unifiedResultsView,
        generateFormContainer,
        optimizeFormContainer,
        viewGenerate,
        viewOptimize,
        promptMainIdea,
        promptOptimizeInput
      } = this.elements;

      switch (newState) {
        case STATE_IDLE:
          this.isProcessing = false;
          if (workspaceCard) workspaceCard.setAttribute('aria-busy', 'false');

          // Hide overlays & results
          if (unifiedProcessingView) unifiedProcessingView.hidden = true;
          if (unifiedErrorView) unifiedErrorView.hidden = true;
          if (unifiedResultsView) unifiedResultsView.hidden = true;

          // Show current service's form container
          if (this.activeService === SERVICE_GENERATE) {
            if (viewGenerate) { viewGenerate.hidden = false; viewGenerate.classList.add('active'); }
            if (viewOptimize) { viewOptimize.hidden = true; viewOptimize.classList.remove('active'); }
            if (generateFormContainer) generateFormContainer.hidden = false;
            if (promptMainIdea) promptMainIdea.focus();
          } else {
            if (viewOptimize) { viewOptimize.hidden = false; viewOptimize.classList.add('active'); }
            if (viewGenerate) { viewGenerate.hidden = true; viewGenerate.classList.remove('active'); }
            if (optimizeFormContainer) optimizeFormContainer.hidden = false;
            if (promptOptimizeInput) promptOptimizeInput.focus();
          }

          // Restore action buttons
          this.setButtonsDisabled(false);
          this.updateStatusPill();
          break;

        case STATE_PROCESSING:
          this.isProcessing = true;
          if (workspaceCard) workspaceCard.setAttribute('aria-busy', 'true');

          // Prevent repeated submissions
          this.setButtonsDisabled(true);

          // Hide other views & errors
          if (unifiedErrorView) unifiedErrorView.hidden = true;
          if (unifiedResultsView) unifiedResultsView.hidden = true;

          // Temporarily hide form inputs while processing overlay is shown
          if (generateFormContainer) generateFormContainer.hidden = true;
          if (optimizeFormContainer) optimizeFormContainer.hidden = true;

          // Update service indicator in processing card
          if (this.elements.processingServiceLabel) {
            this.elements.processingServiceLabel.textContent = this.activeService === SERVICE_GENERATE
              ? (this.currentLang === 'fr' ? 'Service Génération' : 'Generate Service')
              : (this.currentLang === 'fr' ? 'Service Optimisation' : 'Optimize Service');
          }

          if (unifiedProcessingView) {
            unifiedProcessingView.hidden = false;
            unifiedProcessingView.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }

          this.updateStatusPill();
          break;

        case STATE_SUCCESS:
          this.isProcessing = false;
          if (workspaceCard) workspaceCard.setAttribute('aria-busy', 'false');

          if (unifiedProcessingView) unifiedProcessingView.hidden = true;
          if (unifiedErrorView) unifiedErrorView.hidden = true;
          this.setButtonsDisabled(false);

          // Hide forms
          if (generateFormContainer) generateFormContainer.hidden = true;
          if (optimizeFormContainer) optimizeFormContainer.hidden = true;

          // Render Complete Results Interface
          this.renderResultsView();

          if (unifiedResultsView) {
            unifiedResultsView.hidden = false;
            unifiedResultsView.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }

          this.updateStatusPill();
          break;

        case STATE_ERROR:
          this.isProcessing = false;
          if (workspaceCard) workspaceCard.setAttribute('aria-busy', 'false');

          if (unifiedProcessingView) unifiedProcessingView.hidden = true;
          if (unifiedResultsView) unifiedResultsView.hidden = true;
          this.setButtonsDisabled(false);

          if (unifiedErrorView) {
            unifiedErrorView.hidden = false;
            unifiedErrorView.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }

          this.updateStatusPill();
          break;
      }
    },

    /**
     * Enables or disables action buttons to prevent repeated submissions.
     * @param {boolean} disabled
     */
    setButtonsDisabled: function (disabled) {
      const { btnGenerate, btnOptimize } = this.elements;
      if (btnGenerate) btnGenerate.disabled = disabled;
      if (btnOptimize) btnOptimize.disabled = disabled;
    },

    /**
     * Updates header status indicator dot and text based on active state.
     */
    updateStatusPill: function () {
      const { serviceStatusDot, serviceStatusText } = this.elements;
      if (!serviceStatusDot || !serviceStatusText) return;

      serviceStatusDot.classList.remove('processing', 'error');

      if (this.currentState === STATE_PROCESSING) {
        serviceStatusDot.classList.add('processing');
        serviceStatusText.textContent = this.currentLang === 'fr' ? 'Traitement en cours...' : 'Working on your prompt...';
      } else if (this.currentState === STATE_ERROR) {
        serviceStatusDot.classList.add('error');
        serviceStatusText.textContent = this.currentLang === 'fr' ? 'Erreur de traitement' : 'Processing issue';
      } else if (this.currentState === STATE_SUCCESS) {
        serviceStatusText.textContent = this.currentLang === 'fr' ? 'Prompt prêt' : 'Prompt is ready';
      } else {
        // Idle
        serviceStatusText.textContent = this.activeService === SERVICE_GENERATE
          ? (this.currentLang === 'fr' ? 'Prêt à générer' : 'Ready to generate')
          : (this.currentLang === 'fr' ? 'Prêt à optimiser' : 'Ready to optimize');
      }
    },

    /**
     * Renders the Results view components with the active run's data.
     * Uses real backend metrics, accurately handling positive and negative savings.
     */
    renderResultsView: function () {
      const {
        resultsServiceBadge,
        resultsSubtitle,
        resultsFinalPromptText,
        resultsOriginalPromptText,
        resultsComparisonRefinedText,
        metricOriginalTokens,
        metricOptimizedTokens,
        metricTokensSaved,
        metricReductionPercent
      } = this.elements;

      const { service, originalText, resultText, metrics, responseTimeMs } = this.lastRunData;
      const isGenerate = service === SERVICE_GENERATE;

      // A. Results Header
      if (resultsServiceBadge) {
        resultsServiceBadge.textContent = isGenerate
          ? (this.currentLang === 'fr' ? 'Service Génération' : 'Generate Service')
          : (this.currentLang === 'fr' ? 'Service Optimisation' : 'Optimize Service');
      }

      if (resultsSubtitle) {
        var timeStr = responseTimeMs ? (' (' + (responseTimeMs / 1000).toFixed(1) + 's)') : '';
        resultsSubtitle.textContent = isGenerate
          ? (this.currentLang === 'fr'
              ? 'Votre prompt a été structuré pour une performance IA optimale.' + timeStr
              : 'Your prompt has been structured for optimal AI performance.' + timeStr)
          : (this.currentLang === 'fr'
              ? 'Votre prompt a été compressé et affiné.' + timeStr
              : 'Your prompt has been compressed and refined.' + timeStr);
      }

      // B. Original Prompt & C. Resulting Prompt — use textContent for safe rendering (anti-XSS)
      if (resultsOriginalPromptText) resultsOriginalPromptText.textContent = originalText;
      if (resultsComparisonRefinedText) resultsComparisonRefinedText.textContent = resultText;
      if (resultsFinalPromptText) resultsFinalPromptText.textContent = resultText;

      // D. Token Analysis Metric Cards — strictly distinguish Generate vs. Optimize
      if (metrics) {
        const isFr = this.currentLang === 'fr';

        if (isGenerate) {
          var inTok = metrics.input_tokens || 0;
          var outTok = metrics.output_tokens || 0;
          var ratio = (outTok / Math.max(1, inTok)).toFixed(1);

          // Card 1: Input Tokens
          if (this.elements.labelMetric1) this.elements.labelMetric1.textContent = isFr ? "Tokens d'entrée" : "Input Tokens";
          if (this.elements.subtextMetric1) this.elements.subtextMetric1.textContent = isFr ? "Idée & paramètres" : "Idea & parameters";
          if (metricOriginalTokens) metricOriginalTokens.textContent = inTok;

          // Card 2: Output Tokens
          if (this.elements.labelMetric2) this.elements.labelMetric2.textContent = isFr ? "Tokens de sortie" : "Output Tokens";
          if (this.elements.subtextMetric2) this.elements.subtextMetric2.textContent = isFr ? "Prompt généré" : "Generated prompt";
          if (metricOptimizedTokens) metricOptimizedTokens.textContent = outTok;

          // Card 3: Generated Length
          if (this.elements.labelMetric3) this.elements.labelMetric3.textContent = isFr ? "Tokens du prompt" : "Generated Length";
          if (this.elements.subtextMetric3) this.elements.subtextMetric3.textContent = isFr ? "Longueur finale structurée" : "Final structured prompt";
          if (metricTokensSaved) {
            metricTokensSaved.textContent = outTok;
            metricTokensSaved.className = 'metric-value text-success';
          }

          // Card 4: Expansion Multiplier
          if (this.elements.labelMetric4) this.elements.labelMetric4.textContent = isFr ? "Ratio d'enrichissement" : "Expansion Multiplier";
          if (this.elements.subtextMetric4) this.elements.subtextMetric4.textContent = isFr ? "Facteur de développement" : "Enrichment factor";
          if (metricReductionPercent) {
            metricReductionPercent.textContent = ratio + 'x';
            metricReductionPercent.className = 'metric-value text-violet';
          }
        } else {
          // Optimize — accurately distinguish original vs. optimized prompt tokens
          var origTok = metrics.original_tokens || 0;
          var optTok = metrics.optimized_tokens || 0;
          var saved = metrics.tokens_saved || 0;
          var pct = typeof metrics.reduction_percentage === 'number' ? metrics.reduction_percentage : 0;

          // Card 1: Original Prompt Tokens
          if (this.elements.labelMetric1) this.elements.labelMetric1.textContent = isFr ? "Tokens du prompt initial" : "Original Prompt Tokens";
          if (this.elements.subtextMetric1) this.elements.subtextMetric1.textContent = isFr ? "Longueur initiale" : "Raw input length";
          if (metricOriginalTokens) metricOriginalTokens.textContent = origTok;

          // Card 2: Optimized Prompt Tokens
          if (this.elements.labelMetric2) this.elements.labelMetric2.textContent = isFr ? "Tokens du prompt optimisé" : "Optimized Prompt Tokens";
          if (this.elements.subtextMetric2) this.elements.subtextMetric2.textContent = isFr ? "Longueur optimisée" : "Refined prompt length";
          if (metricOptimizedTokens) metricOptimizedTokens.textContent = optTok;

          // Card 3: Tokens Saved (Honest reporting: never promise reduction when expanded)
          if (saved > 0) {
            if (this.elements.labelMetric3) this.elements.labelMetric3.textContent = isFr ? "Tokens économisés" : "Tokens Saved";
            if (this.elements.subtextMetric3) this.elements.subtextMetric3.textContent = isFr ? "Réduction de tokens" : "Token reduction";
            if (metricTokensSaved) {
              metricTokensSaved.textContent = '+' + saved;
              metricTokensSaved.className = 'metric-value text-success';
            }
          } else if (saved < 0) {
            if (this.elements.labelMetric3) this.elements.labelMetric3.textContent = isFr ? "Différence de tokens" : "Token Difference";
            if (this.elements.subtextMetric3) this.elements.subtextMetric3.textContent = isFr ? "Expansion structurelle" : "Structural expansion";
            if (metricTokensSaved) {
              metricTokensSaved.textContent = String(saved);
              metricTokensSaved.className = 'metric-value text-warning';
            }
          } else {
            if (this.elements.labelMetric3) this.elements.labelMetric3.textContent = isFr ? "Tokens économisés" : "Tokens Saved";
            if (this.elements.subtextMetric3) this.elements.subtextMetric3.textContent = isFr ? "Longueur identique" : "Equal length";
            if (metricTokensSaved) {
              metricTokensSaved.textContent = '0';
              metricTokensSaved.className = 'metric-value';
            }
          }

          // Card 4: Reduction Percentage vs. Token Change
          if (pct > 0) {
            if (this.elements.labelMetric4) this.elements.labelMetric4.textContent = isFr ? "Pourcentage de réduction" : "Reduction Percentage";
            if (this.elements.subtextMetric4) this.elements.subtextMetric4.textContent = isFr ? "Gain d'efficacité" : "Token efficiency gain";
            if (metricReductionPercent) {
              metricReductionPercent.textContent = '-' + pct + '%';
              metricReductionPercent.className = 'metric-value text-violet';
            }
          } else if (pct < 0) {
            if (this.elements.labelMetric4) this.elements.labelMetric4.textContent = isFr ? "Variation de tokens" : "Token Change";
            if (this.elements.subtextMetric4) this.elements.subtextMetric4.textContent = isFr ? "Enrichi pour clarté" : "Expanded for clarity";
            if (metricReductionPercent) {
              metricReductionPercent.textContent = '+' + Math.abs(pct) + '%';
              metricReductionPercent.className = 'metric-value text-warning';
            }
          } else {
            if (this.elements.labelMetric4) this.elements.labelMetric4.textContent = isFr ? "Variation de tokens" : "Token Change";
            if (this.elements.subtextMetric4) this.elements.subtextMetric4.textContent = isFr ? "Aucune variation" : "No change";
            if (metricReductionPercent) {
              metricReductionPercent.textContent = '0.0%';
              metricReductionPercent.className = 'metric-value';
            }
          }
        }
      }
    },

    /**
     * Toggles visibility of the Original Input column in Before/After comparison.
     */
    toggleViewOriginal: function () {
      const { colOriginalPrompt, comparisonGrid, toggleOriginalText } = this.elements;
      if (!colOriginalPrompt || !comparisonGrid) return;

      const isHidden = colOriginalPrompt.hidden;
      colOriginalPrompt.hidden = !isHidden;
      comparisonGrid.classList.toggle('collapsed-original', !isHidden);

      if (toggleOriginalText) {
        toggleOriginalText.textContent = !isHidden
          ? (this.currentLang === 'fr' ? 'Afficher l\'original' : 'View Original')
          : (this.currentLang === 'fr' ? 'Masquer l\'original' : 'Hide Original');
      }
    },

    /**
     * Handles "Generate Prompt" click flow — sends real request to backend.
     */
    handleGenerate: function () {
      if (this.isProcessing) return;

      const { promptMainIdea } = this.elements;
      if (!promptMainIdea) return;

      const ideaText = promptMainIdea.value.trim();

      if (!ideaText) {
        const errorMsg = this.currentLang === 'fr'
          ? 'Veuillez décrire votre idée avant de générer le prompt.'
          : 'Please describe your idea before generating.';
        this.showValidationError(SERVICE_GENERATE, errorMsg);
        return;
      }

      this.clearValidationError(SERVICE_GENERATE);

      // Build payload matching backend GenerateRequest schema
      var payload = {
        user_idea: ideaText,
        mode: this.activeModeGenerate || MODE_QUICK,
        category: (this.elements.promptCategory && this.elements.promptCategory.value) || null
      };

      // Include advanced fields when in advanced mode
      if (this.activeModeGenerate === MODE_ADVANCED) {
        var role = this.elements.advRole ? this.elements.advRole.value.trim() : '';
        var objective = this.elements.advObjective ? this.elements.advObjective.value.trim() : '';
        var context = this.elements.advContext ? this.elements.advContext.value.trim() : '';
        var constraints = this.elements.advConstraints ? this.elements.advConstraints.value.trim() : '';
        var format = this.elements.advFormat ? this.elements.advFormat.value.trim() : '';

        if (role) payload.role = role;
        if (objective) payload.objective = objective;
        if (context) payload.context = context;
        if (constraints) payload.constraints = constraints;
        if (format) payload.output_format = format;
      }

      // Store original text for results comparison
      this.lastRunData.originalText = ideaText;
      this.lastRunData.service = SERVICE_GENERATE;
      this.lastRunData.category = payload.category || '';

      this._sendApiRequest('/api/generate', payload, SERVICE_GENERATE);
    },

    /**
     * Handles "Optimize Prompt" click flow — sends real request to backend.
     */
    handleOptimize: function () {
      if (this.isProcessing) return;

      const { promptOptimizeInput } = this.elements;
      if (!promptOptimizeInput) return;

      const rawText = promptOptimizeInput.value.trim();

      if (!rawText) {
        const errorMsg = this.currentLang === 'fr'
          ? 'Veuillez coller un prompt existant à optimiser.'
          : 'Please paste an existing prompt to optimize.';
        this.showValidationError(SERVICE_OPTIMIZE, errorMsg);
        return;
      }

      this.clearValidationError(SERVICE_OPTIMIZE);

      // Build payload matching backend OptimizeRequest schema
      var optMode = this.activeModeOptimize || MODE_QUICK;
      var payload = {
        original_prompt: rawText,
        mode: optMode
      };

      // Include custom optimization instructions when in advanced mode
      if (optMode === MODE_ADVANCED && this.elements.advOptimizeInstructions) {
        var instructions = this.elements.advOptimizeInstructions.value.trim();
        if (instructions) {
          payload.optimization_instructions = instructions;
        }
      }

      // Store original text for results comparison
      this.lastRunData.originalText = rawText;
      this.lastRunData.service = SERVICE_OPTIMIZE;
      this.lastRunData.category = '';

      this._sendApiRequest('/api/optimize', payload, SERVICE_OPTIMIZE);
    },

    /**
     * Sends an async API request to the FastAPI backend.
     * Handles success, error, and timeout scenarios.
     * @param {string} endpoint - API endpoint path (e.g., '/api/generate')
     * @param {Object} payload - JSON request body
     * @param {string} service - 'generate' | 'optimize'
     */
    _sendApiRequest: function (endpoint, payload, service) {
      var self = this;

      // Dev test simulated error shortcut
      if (this.simulateError) {
        this.transitionToState(STATE_PROCESSING);
        setTimeout(function () {
          self._showApiError('Dev test simulated error: Unable to complete prompt request. (Uncheck the footer checkbox to run real requests)');
        }, 800);
        return;
      }

      // Transition to processing state (disables buttons, shows spinner)
      this.transitionToState(STATE_PROCESSING);

      // Create an AbortController for timeout handling
      var controller = new AbortController();
      var timeoutId = setTimeout(function () {
        controller.abort();
      }, REQUEST_TIMEOUT_MS);

      fetch(API_BASE_URL + endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      })
      .then(function (response) {
        clearTimeout(timeoutId);
        return response.json().then(function (data) {
          return { status: response.status, data: data };
        });
      })
      .then(function (result) {
        var data = result.data;

        if (data.success) {
          // Extract the result text based on service type
          var resultText = '';
          var metrics = {};

          if (service === SERVICE_GENERATE) {
            resultText = data.generated_prompt || '';
            metrics = {
              input_tokens: data.input_tokens || 0,
              output_tokens: data.output_tokens || 0
            };
          } else {
            resultText = data.optimized_prompt || '';
            metrics = {
              original_tokens: data.original_tokens || 0,
              optimized_tokens: data.optimized_tokens || 0,
              tokens_saved: data.tokens_saved || 0,
              reduction_percentage: data.reduction_percentage || 0
            };
          }

          self.lastRunData.resultText = resultText;
          self.lastRunData.metrics = metrics;
          self.lastRunData.responseTimeMs = data.response_time_ms || 0;
          self.transitionToState(STATE_SUCCESS);

          // Update persistence badge counts (e.g. newly recorded history)
          if (typeof window !== 'undefined' && window.PersistenceManager && typeof window.PersistenceManager.refreshBadgeCount === 'function') {
            window.PersistenceManager.refreshBadgeCount();
          }
        } else {
          // Backend returned safe categorized error
          var errorMsg = data.error_message || 'An error occurred while processing your request.';
          self._showApiError(errorMsg);
        }
      })
      .catch(function (err) {
        clearTimeout(timeoutId);
        var errorMsg;

        if (err.name === 'AbortError') {
          errorMsg = self.currentLang === 'fr'
            ? 'La requête a expiré. Le serveur met trop de temps à répondre. Veuillez réessayer.'
            : 'Request timed out. The server is taking too long to respond. Please try again.';
        } else if (err.message && err.message.toLowerCase().includes('failed to fetch')) {
          var isLocal = API_BASE_URL.indexOf('127.0.0.1') !== -1 || API_BASE_URL.indexOf('localhost') !== -1;
          errorMsg = isLocal
            ? (self.currentLang === 'fr'
                ? 'Impossible de se connecter au serveur backend. Vérifiez que le serveur FastAPI est en cours d\'exécution sur le port 8000.'
                : 'Unable to connect to the backend server. Please ensure the FastAPI server is running on http://127.0.0.1:8000.')
            : (self.currentLang === 'fr'
                ? 'Impossible de se connecter au service API backend. Veuillez vérifier votre connexion ou l\'état du service.'
                : 'Unable to connect to the backend API service. Please verify your connection or service status.');
        } else {
          errorMsg = self.currentLang === 'fr'
            ? 'Une erreur réseau s\'est produite. Veuillez vérifier votre connexion et réessayer.'
            : 'A network error occurred. Please check your connection and try again.';
        }

        self._showApiError(errorMsg);
      });
    },

    /**
     * Displays a user-friendly error message in the error view.
     * Never displays raw exception details or secrets.
     * @param {string} message - Safe, user-friendly error message
     */
    _showApiError: function (message) {
      if (this.elements.errorDescription) {
        this.elements.errorDescription.textContent = message;
      }
      this.transitionToState(STATE_ERROR);
    },

    /**
     * Handles "Try Again" action: re-runs current workflow with existing inputs.
     */
    handleTryAgain: function () {
      if (this.lastRunData.service === SERVICE_OPTIMIZE) {
        this.handleOptimize();
      } else {
        this.handleGenerate();
      }
    },

    /**
     * Retries the last executed service submission after error.
     */
    handleRetry: function () {
      if (this.lastRunData.service === SERVICE_OPTIMIZE) {
        this.handleOptimize();
      } else {
        this.handleGenerate();
      }
    },

    /**
     * Clears all inputs in Generate view.
     */
    handleClearGenerate: function () {
      const {
        promptMainIdea,
        promptCategory,
        advRole,
        advObjective,
        advContext,
        advConstraints,
        advFormat
      } = this.elements;

      if (promptMainIdea) promptMainIdea.value = '';
      if (promptCategory) promptCategory.value = '';
      if (advRole) advRole.value = '';
      if (advObjective) advObjective.value = '';
      if (advContext) advContext.value = '';
      if (advConstraints) advConstraints.value = '';
      if (advFormat) advFormat.value = '';

      this.clearValidationError(SERVICE_GENERATE);
      this.updateCharCounters();
      this.transitionToState(STATE_IDLE);
      if (promptMainIdea) promptMainIdea.focus();
    },

    /**
     * Clears all inputs in Optimize view.
     */
    handleClearOptimize: function () {
      const { promptOptimizeInput, advOptimizeInstructions } = this.elements;
      if (promptOptimizeInput) promptOptimizeInput.value = '';
      if (advOptimizeInstructions) advOptimizeInstructions.value = '';

      this.clearValidationError(SERVICE_OPTIMIZE);
      this.updateCharCounters();
      this.transitionToState(STATE_IDLE);
      if (promptOptimizeInput) promptOptimizeInput.focus();
    },

    /**
     * Copies the current prompt result to clipboard with visual feedback on all copy buttons.
     */
    handleCopyCurrentResult: function () {
      const text = this.lastRunData.resultText;
      if (!text) return;

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
          this.showAllCopyFeedback();
        }).catch(() => {
          this.fallbackCopy(text);
        });
      } else {
        this.fallbackCopy(text);
      }
    },

    fallbackCopy: function (text) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        this.showAllCopyFeedback();
      } catch (err) {}
      document.body.removeChild(textarea);
    },

    showAllCopyFeedback: function () {
      const copyLabels = document.querySelectorAll('.copy-label');
      copyLabels.forEach(label => {
        const orig = label.textContent;
        label.textContent = this.currentLang === 'fr' ? 'Copié !' : 'Copied!';
        setTimeout(() => {
          label.textContent = orig;
        }, 2000);
      });
    },

    /**
     * Binds language changes for localized UI labels.
     */
    bindLanguageSelector: function () {
      const { langSelect } = this.elements;
      if (langSelect) {
        langSelect.addEventListener('change', (e) => {
          this.currentLang = e.target.value === 'fr' ? 'fr' : 'en';
          this.updateCharCounters();
          this.updateStatusPill();
          if (this.currentState === STATE_SUCCESS) {
            this.renderResultsView();
          }
        });
      }
    }
  };

  root.WorkspaceManager = WorkspaceManager;

})(typeof window !== 'undefined' ? window : this);
