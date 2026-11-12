/**
 * AutoPrompt — Interactive Prototype
 * Mock Data Module (mock-data.js)
 * 
 * Provides mock data structures for categories, templates, client-side
 * prompt formatting templates, and demonstrative token metrics.
 * 
 * IMPORTANT:
 * - All token metrics and prompt transformations are demonstrative mock values.
 * - No real AI model or production tokenizer is connected.
 */

(function (root) {
  'use strict';

  const mockData = {
    // Official categories as defined in Step 3 requirements
    categories: [
      'Education',
      'Programming',
      'Data Science',
      'Graphic Design',
      'Content Creation',
      'Business',
      'Research',
      'Daily Productivity',
      'Other'
    ],

    workspaces: [
      {
        id: 'ws-default',
        name: 'Default Workspace',
        description: 'Personal prompts and prompt engineering experiments',
        promptCount: 12,
        createdAt: '2026-10-15T10:00:00Z'
      }
    ],

    // Client-side prompt generator for Generate service
    formatMockPrompt: function (inputs) {
      const { idea, category, mode, role, objective, context, constraints, format } = inputs;
      const categoryLine = category ? `[Category: ${category}]\n` : '';

      if (mode === 'advanced') {
        const lines = [
          `# ${category ? category + ' Prompt' : 'Optimized System Prompt'}`,
          categoryLine.trim(),
          '',
          `## Core Task / Instruction`,
          idea.trim(),
          ''
        ];

        if (role) {
          lines.push(`## Role & Persona`, role.trim(), '');
        }
        if (objective) {
          lines.push(`## Explicit Objective`, objective.trim(), '');
        }
        if (context) {
          lines.push(`## Context & Background`, context.trim(), '');
        }
        if (constraints) {
          lines.push(`## Behavioral Constraints`, constraints.trim(), '');
        }
        if (format) {
          lines.push(`## Desired Output Format`, format.trim(), '');
        }

        lines.push(
          `## Guardrails`,
          `- Provide direct, high-value answers without filler or preambles.`,
          `- Ask clarifying questions only if critical requirements are ambiguous.`
        );

        return lines.filter(Boolean).join('\n');
      } else {
        // Quick Mode prompt format
        return [
          `# Task Instruction`,
          categoryLine.trim(),
          idea.trim(),
          '',
          `## Execution Guidelines:`,
          `- Prioritize depth, clarity, and logical organization.`,
          `- Avoid boilerplate or repetitive explanations.`,
          `- Provide step-by-step reasoning where applicable.`
        ].filter(Boolean).join('\n');
      }
    },

    // Client-side prompt optimizer for Optimize service
    formatMockOptimizePrompt: function (rawPrompt) {
      return [
        `# Optimized Prompt (Token-Efficient Architecture)`,
        ``,
        `## Objective & Core Intent`,
        rawPrompt.trim(),
        ``,
        `## Refined Directives (Token-Optimized):`,
        `- Deliver direct, dense output adhering strictly to constraints.`,
        `- Omit conversational filler, polite preambles, and meta-commentary.`,
        `- Use hierarchical bullet points and concise syntax for optimal comprehension.`,
        `- Ensure zero hallucination by verifying assumptions before output generation.`
      ].join('\n');
    },

    /**
     * Calculates illustrative demonstrative token metrics based on character heuristics.
     * Clearly marked as demo data. Does not pretend to be a real tokenizer.
     * @param {string} originalText
     * @param {string} resultText
     * @param {string} service - 'generate' | 'optimize'
     * @returns {Object}
     */
    calculateDemoTokenMetrics: function (originalText, resultText, service) {
      if (!originalText || !originalText.trim() || !resultText || !resultText.trim()) {
        return {
          originalTokens: 'Not measured',
          optimizedTokens: 'Not measured',
          tokensSaved: 'Not measured',
          reductionPercent: 'Not measured',
          isDemo: true
        };
      }

      const origLen = originalText.trim().length;
      // Heuristic: ~4 English characters per token average
      const estOrigTokens = Math.max(16, Math.round(origLen / 4));

      if (service === 'optimize') {
        // Optimization demonstrates token reduction (~35% to 45% reduction)
        const estOptimized = Math.max(10, Math.round(estOrigTokens * 0.62));
        const saved = Math.max(0, estOrigTokens - estOptimized);
        const percent = estOrigTokens > 0 ? Math.round((saved / estOrigTokens) * 100) : 0;

        return {
          originalTokens: `~${estOrigTokens}`,
          optimizedTokens: `~${estOptimized}`,
          tokensSaved: `~${saved}`,
          reductionPercent: `-${percent}%`,
          isDemo: true
        };
      } else {
        // Generate structures an idea into a complete template
        const estGenerated = Math.max(25, Math.round(resultText.trim().length / 4));
        // Demonstrative comparison against uncompressed wordy prompts
        const uncompressedBaseline = Math.round(estGenerated * 1.45);
        const saved = Math.max(0, uncompressedBaseline - estGenerated);
        const percent = Math.round((saved / uncompressedBaseline) * 100);

        return {
          originalTokens: `~${estOrigTokens}`,
          optimizedTokens: `~${estGenerated}`,
          tokensSaved: `~${saved}`,
          reductionPercent: `-${percent}%`,
          isDemo: true
        };
      }
    }
  };

  root.AutoPromptMockData = Object.freeze(mockData);

})(typeof window !== 'undefined' ? window : this);
