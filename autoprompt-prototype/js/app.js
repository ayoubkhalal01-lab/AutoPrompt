/**
 * AutoPrompt — Interactive Prototype
 * Application Entry Point (app.js)
 * 
 * Orchestrates application startup, module initialization,
 * and high-level lifecycle events.
 */

(function (root) {
  'use strict';

  const AutoPromptApp = {
    version: '0.1.0',
    isInitialized: false,

    /**
     * Initializes all application modules in correct sequence.
     */
    init: function () {
      if (this.isInitialized) return;

      try {
        // Initialize Theme Manager
        if (root.ThemeManager && typeof root.ThemeManager.init === 'function') {
          root.ThemeManager.init();
        }

        // Initialize Workspace Manager (Placeholder)
        if (root.WorkspaceManager && typeof root.WorkspaceManager.init === 'function') {
          root.WorkspaceManager.init();
        }

        this.isInitialized = true;
        console.log(`[AutoPrompt] Platform prototype v${this.version} initialized successfully.`);
      } catch (error) {
        console.error('[AutoPrompt] Error during application initialization:', error);
      }
    }
  };

  root.AutoPromptApp = AutoPromptApp;

  // Wait for DOM readiness before boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AutoPromptApp.init());
  } else {
    AutoPromptApp.init();
  }

})(typeof window !== 'undefined' ? window : this);
