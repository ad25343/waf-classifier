/**
 * Shared dispute-modal helper.
 *
 * Auto-injected into every page by routes/pages.py so any view can call:
 *
 *   openDisputeModal({
 *     story_title:        "...",     // REQUIRED
 *     story_description:  "...",
 *     ai_category:        "...",
 *     ai_color:           "...",
 *     ai_confidence:      "...",
 *     ai_reasoning:       "...",
 *     team:               "...",
 *     epic:               "...",
 *     story_id:           "...",
 *     pi_number:          "...",
 *     onSuccess:          fn,        // optional callback
 *   });
 *
 * The modal is built lazily on first use and reused on subsequent calls.
 * Posts to /api/disputes (matches the existing single-classify form on /).
 */
(function() {
  if (window.openDisputeModal) return;  // idempotent

  var MIN_CHARS = 30;

  // Default WAF categories — overridden by /api/status if available.
  var DEFAULT_CATS = [
    "KTLO (Keep the Lights On)", "Business Maintenance", "Technical Maintenance",
    "Regulatory (Operational)", "Regulatory Mandated Change",
    "Enterprise Strategic Priority", "Top Divisional Priority", "Other Block Priority"
  ];
  var _cats = null;

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function _ensureModal() {
    var m = document.getElementById("dispute-modal");
    if (m) return m;

    var style = document.createElement("style");
    style.textContent = `
      #dispute-modal { display:none; position:fixed; inset:0; z-index:9999;
        background:rgba(0,0,0,0.55); align-items:center; justify-content:center; }
      #dispute-modal.open { display:flex; }
      #dispute-modal .dm-card { background:var(--bg-primary,#fff);
        border:1px solid var(--border,#ddd); border-radius:10px;
        padding:22px 24px; width:min(560px,92vw); max-height:88vh; overflow-y:auto;
        color:var(--text-primary,#222); }
      #dispute-modal h3 { margin:0 0 8px; font-size:17px; }
      #dispute-modal .dm-sub { font-size:12px; color:var(--text-muted,#888); margin-bottom:14px; }
      #dispute-modal .dm-ai {
        background:rgba(244,63,94,0.08); border:1px solid rgba(244,63,94,0.25);
        padding:10px 12px; border-radius:6px; font-size:13px; margin-bottom:14px; }
      #dispute-modal .dm-ai b { color:#f43f5e; }
      #dispute-modal label { display:block; font-size:12px; font-weight:600;
        text-transform:uppercase; letter-spacing:0.4px;
        color:var(--text-muted,#888); margin-bottom:6px; margin-top:10px; }
      #dispute-modal textarea, #dispute-modal select {
        width:100%; box-sizing:border-box; padding:8px 10px; border-radius:6px;
        border:1px solid var(--border,#ddd); background:var(--bg-secondary,#fafafa);
        color:var(--text-primary,#222); font-size:13px; font-family:inherit; }
      #dispute-modal textarea { min-height:80px; resize:vertical; }
      #dispute-modal .dm-hint { font-size:11px; color:var(--text-muted,#888); margin:4px 0 0; }
      #dispute-modal .dm-err { font-size:12px; color:#f43f5e; display:none; margin-top:4px; }
      #dispute-modal .dm-err.show { display:block; }
      #dispute-modal .dm-actions { display:flex; gap:10px; justify-content:flex-end; margin-top:18px; }
      #dispute-modal button {
        padding:8px 14px; border-radius:6px; font-size:13px;
        cursor:pointer; border:1px solid transparent; }
      #dispute-modal .dm-cancel {
        background:transparent; border-color:var(--border,#ddd);
        color:var(--text-muted,#888); }
      #dispute-modal .dm-submit {
        background:#f43f5e; color:white; font-weight:600; }
      #dispute-modal .dm-submit:disabled { opacity:0.6; cursor:wait; }
      #dispute-modal .dm-success { color:#22c55e; font-size:13px; display:none;
        margin-right:auto; align-self:center; font-weight:600; }
      #dispute-modal .dm-success.show { display:inline; }
    `;
    document.head.appendChild(style);

    m = document.createElement("div");
    m.id = "dispute-modal";
    m.innerHTML =
      '<div class="dm-card">' +
      '  <h3>&#128681; Flag this classification</h3>' +
      '  <div class="dm-sub" id="dm-story-line"></div>' +
      '  <div class="dm-ai" id="dm-ai-summary"></div>' +
      '  <label>Why is this classification incorrect? <span style="color:#f43f5e">*</span></label>' +
      '  <div class="dm-hint">Be specific — what about this story does not fit? Min ' + MIN_CHARS + ' chars.</div>' +
      '  <textarea id="dm-comment" placeholder="e.g. This is a net-new revenue stream, not maintenance. The AI may be anchoring on the word \'pipeline\'."></textarea>' +
      '  <div class="dm-err" id="dm-comment-err">Please explain (at least ' + MIN_CHARS + ' characters).</div>' +
      '  <label>What should the correct WAF category be? <span style="color:#f43f5e">*</span></label>' +
      '  <select id="dm-suggested"><option value="">— select a category —</option></select>' +
      '  <div class="dm-err" id="dm-cat-err">Please select the correct category.</div>' +
      '  <div class="dm-actions">' +
      '    <span class="dm-success" id="dm-success">&#10003; Flagged for review</span>' +
      '    <button class="dm-cancel" type="button">Cancel</button>' +
      '    <button class="dm-submit" type="button">Submit Flag</button>' +
      '  </div>' +
      '</div>';
    m.addEventListener("click", function(e) { if (e.target === m) _close(); });
    document.body.appendChild(m);

    m.querySelector(".dm-cancel").addEventListener("click", _close);
    m.querySelector(".dm-submit").addEventListener("click", _submit);
    document.addEventListener("keydown", function(e) {
      if (e.key === "Escape" && m.classList.contains("open")) _close();
    });
    return m;
  }

  function _close() {
    var m = document.getElementById("dispute-modal");
    if (m) m.classList.remove("open");
  }

  // Cache for the active story payload
  var _ctx = null;

  function _populateCats(selectEl) {
    function fill(cats) {
      cats.forEach(function(cat) {
        var opt = document.createElement("option");
        opt.value = cat; opt.textContent = cat;
        selectEl.appendChild(opt);
      });
    }
    if (_cats) { fill(_cats); return; }
    fetch("/api/status").then(function(r) { return r.json(); }).then(function(d) {
      _cats = (d && d.waf_categories && d.waf_categories.length) ? d.waf_categories : DEFAULT_CATS;
      fill(_cats);
    }).catch(function() {
      _cats = DEFAULT_CATS;
      fill(DEFAULT_CATS);
    });
  }

  function _submit() {
    if (!_ctx) return;
    var commentEl = document.getElementById("dm-comment");
    var selectEl  = document.getElementById("dm-suggested");
    var cErr = document.getElementById("dm-comment-err");
    var sErr = document.getElementById("dm-cat-err");
    var btn  = document.querySelector("#dispute-modal .dm-submit");
    var ok   = document.getElementById("dm-success");

    var comment = (commentEl.value || "").trim();
    var valid = true;
    if (comment.length < MIN_CHARS) { cErr.classList.add("show"); valid = false; }
    else cErr.classList.remove("show");
    if (!selectEl.value) { sErr.classList.add("show"); valid = false; }
    else sErr.classList.remove("show");
    if (!valid) return;

    btn.disabled = true; btn.textContent = "Flagging…";
    var payload = Object.assign({}, _ctx, {
      user_comment:       comment,
      suggested_category: selectEl.value,
    });
    delete payload.onSuccess;

    fetch("/api/disputes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function(r) {
      if (!r.ok) return r.json().then(function(j) { throw new Error(j.error || "Server error"); });
      return r.json();
    }).then(function(resp) {
      ok.classList.add("show");
      btn.textContent = "Submit Flag";
      btn.disabled = false;
      var cb = _ctx && _ctx.onSuccess;
      setTimeout(function() {
        _close();
        ok.classList.remove("show");
        if (typeof cb === "function") cb(resp);
      }, 900);
    }).catch(function(err) {
      btn.disabled = false; btn.textContent = "Submit Flag";
      alert("Could not flag this story: " + err.message);
    });
  }

  window.openDisputeModal = function(opts) {
    opts = opts || {};
    if (!opts.story_title) {
      console.warn("openDisputeModal: story_title required");
      return;
    }
    _ctx = opts;
    var m = _ensureModal();
    document.getElementById("dm-comment").value = "";
    document.getElementById("dm-comment-err").classList.remove("show");
    document.getElementById("dm-cat-err").classList.remove("show");
    document.getElementById("dm-success").classList.remove("show");
    var sel = document.getElementById("dm-suggested");
    sel.innerHTML = '<option value="">— select a category —</option>';
    _populateCats(sel);
    document.getElementById("dm-story-line").textContent =
      opts.story_id ? (opts.story_id + " · " + opts.story_title) : opts.story_title;
    var aiHtml = '<div><span style="color:var(--text-muted)">Disputing AI classification:</span> <b>' +
      _esc(opts.ai_category || "Unknown") + '</b>';
    if (opts.ai_color)      aiHtml += ' <span style="opacity:0.85">(' + _esc(opts.ai_color) + ')</span>';
    if (opts.ai_confidence) aiHtml += ' <span style="opacity:0.7;font-size:11px;margin-left:6px;">conf: ' + _esc(opts.ai_confidence) + '</span>';
    aiHtml += '</div>';
    document.getElementById("dm-ai-summary").innerHTML = aiHtml;
    m.classList.add("open");
    setTimeout(function() { document.getElementById("dm-comment").focus(); }, 50);
  };
})();
