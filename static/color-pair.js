/**
 * Shared User → AI color-comparison renderer.
 *
 * Auto-injected into every page by routes/pages.py so any view that shows
 * both User WAF and AI WAF can also surface the matching User → AI color
 * comparison without duplicating the helper.
 *
 * Usage:
 *   renderColorPair(userColorKey, aiColorKey) → "🟣 PURPLE → 🟢 GREEN"
 *                                               (when they differ)
 *                                            → "🟢 GREEN"
 *                                               (when they match — show AI only)
 *                                            → "—"
 *                                               (when both absent)
 *
 * Color keys are the canonical WAF colors (uppercase): GRAY, BLACK, RED,
 * ORANGE, YELLOW, GREEN, BLUE, PURPLE.
 */
(function() {
  if (window.renderColorPair) return;  // idempotent

  const HEX = {
    GRAY:   '#6b7280',
    BLACK:  '#1f2937',
    RED:    '#dc2626',
    ORANGE: '#ea580c',
    YELLOW: '#ca8a04',
    GREEN:  '#16a34a',
    BLUE:   '#2563eb',
    PURPLE: '#9333ea',
    TEAL:   '#0d9488',
  };
  window.WAF_COLOR_HEX_MAP = HEX;

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function _norm(c) {
    return (c == null ? "" : String(c)).trim().toUpperCase();
  }

  function _pill(colorKey) {
    if (!colorKey) return '<span style="color:var(--text-muted);font-size:12px;">—</span>';
    const hex = HEX[colorKey] || '#9ca3af';
    const border = colorKey === 'BLACK' ? 'border:1px solid #6b7280;' : '';
    return `<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;white-space:nowrap;">` +
           `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${hex};${border}flex-shrink:0;"></span>` +
           `${_esc(colorKey)}</span>`;
  }

  /**
   * @param {string} userColor — color the source data carried (or expected from user's category)
   * @param {string} aiColor — color the AI assigned
   * @returns {string} HTML
   */
  window.renderColorPair = function(userColor, aiColor) {
    const u = _norm(userColor);
    const a = _norm(aiColor);
    if (!u && !a) return '<span style="color:var(--text-muted);font-size:12px;">—</span>';
    if (!u || u === a) return _pill(a || u);
    return _pill(u) +
           ' <span style="color:var(--text-muted);font-size:11px;">→</span> ' +
           _pill(a);
  };

  // Convenience: just the color pill (for places that only render one color).
  window.renderColorPill = _pill;
})();
