/**
 * AutoPrompt — Interactive Prototype
 * Theme Management Module (theme.js)
 * 
 * Handles complete Light and Dark theme lifecycle:
 * - Default Light Mode for first-time visitors
 * - Theme toggling via Vanilla JavaScript
 * - localStorage persistence and restoration on refresh
 * - Accessible ARIA attributes, tooltips, and keyboard triggers
 * - Seamless integration with AutoPrompt design tokens
 */

(function (root) {
  'use strict';

  const STORAGE_KEY = 'autoprompt_theme';
  const THEME_LIGHT = 'light';
  const THEME_DARK = 'dark';

  const ThemeManager = {
    currentTheme: THEME_LIGHT,

    /**
     * Initializes theme system.
     * Requirement 4: Light Mode must be the default for first-time visitors.
     */
    init: function () {
      const storedTheme = this.getStoredTheme();

      if (storedTheme === THEME_DARK || storedTheme === THEME_LIGHT) {
        this.setTheme(storedTheme);
      } else {
        // Default initial theme is Light mode
        this.setTheme(THEME_LIGHT);
      }

      this.bindEvents();
    },

    /**
     * Retrieves stored theme safely from localStorage.
     * @returns {string|null}
     */
    getStoredTheme: function () {
      try {
        return localStorage.getItem(STORAGE_KEY);
      } catch (err) {
        return null;
      }
    },

    /**
     * Sets theme, updates data-theme attribute, saves to storage, and updates toggle button.
     * @param {string} theme - 'light' | 'dark'
     */
    setTheme: function (theme) {
      this.currentTheme = theme === THEME_DARK ? THEME_DARK : THEME_LIGHT;
      document.documentElement.setAttribute('data-theme', this.currentTheme);

      try {
        localStorage.setItem(STORAGE_KEY, this.currentTheme);
      } catch (err) {
        // LocalStorage may be restricted in some environments
      }

      this.updateToggleButton();
    },

    /**
     * Toggles between light and dark themes.
     */
    toggleTheme: function () {
      const nextTheme = this.currentTheme === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
      this.setTheme(nextTheme);
    },

    /**
     * Returns the active theme identifier.
     * @returns {string} 'light' | 'dark'
     */
    getTheme: function () {
      return this.currentTheme;
    },

    /**
     * Updates accessible ARIA labels, titles, and pressed state on the theme toggle button.
     */
    updateToggleButton: function () {
      const toggleBtn = document.getElementById('theme-toggle');
      if (!toggleBtn) return;

      const isDark = this.currentTheme === THEME_DARK;
      const label = isDark ? 'Switch to light theme' : 'Switch to dark theme';

      toggleBtn.setAttribute('aria-label', label);
      toggleBtn.setAttribute('title', label);
      toggleBtn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
    },

    /**
     * Binds click and accessible keyboard events to theme toggle button.
     */
    bindEvents: function () {
      const toggleBtn = document.getElementById('theme-toggle');
      if (toggleBtn) {
        toggleBtn.addEventListener('click', () => this.toggleTheme());
        toggleBtn.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.toggleTheme();
          }
        });
      }
    }
  };

  root.ThemeManager = ThemeManager;

})(typeof window !== 'undefined' ? window : this);
