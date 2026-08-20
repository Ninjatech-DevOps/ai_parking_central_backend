/* Shared helpers for the vehicle counter pages.
   Classic script (not an ES module) defining a single VC global. */

var VC = (function () {
  /* Derive the module's base path from where this page is served, so the
     URL prefix lives only in routes.py and can be changed there alone. */
  var BASE = location.pathname.replace(/\/+$/, "");
  var API = BASE + "/api";

  /* --- Capabilities from URL params ---------------------------------- */
  /* Bare valueless params: ?edit, ?delete, ?edit&delete.
     URLSearchParams.has() is true for a valueless key.
     NOTE: a UI affordance only, never a security boundary -- the API is
     unauthenticated and these endpoints are reachable directly. */
  var params = new URLSearchParams(location.search);
  // "del" / "exp" rather than the reserved words delete/export.
  var caps = {
    edit: params.has("edit"),
    del: params.has("delete"),
    exp: params.has("export"),
  };

  /* --- Token ----------------------------------------------------------- */
  /* Keyed by the module's base path so two deployments on one host cannot
     overwrite each other's token. */

  var TOKEN_KEY = "vc_token:" + BASE;
  var onAuthFailure = null;

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }

  function setToken(value) {
    try { localStorage.setItem(TOKEN_KEY, value); } catch (e) { /* private mode */ }
  }

  function clearToken() {
    try { localStorage.removeItem(TOKEN_KEY); } catch (e) { /* private mode */ }
  }

  /* --- Fetch wrapper -------------------------------------------------- */

  async function api(path, opts) {
    opts = opts || {};
    var headers = Object.assign({ "Content-Type": "application/json" },
                                opts.headers || {});

    // Single choke point: every call site inherits the token and the 401
    // handling below without any change of its own.
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    var res = await fetch(API + path, Object.assign({}, opts, { headers: headers }));

    if (res.status === 401) {
      clearToken();
      if (onAuthFailure) onAuthFailure();
      throw new Error("Session expired");
    }

    if (!res.ok) {
      var msg = "Request failed (" + res.status + ")";
      try {
        var body = await res.json();
        // Matches the global AppException handler: {success:false, detail:...}
        if (body && body.detail) {
          msg = typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
        }
      } catch (e) { /* non-JSON error body; keep the status message */ }
      throw new Error(msg);
    }
    return res.status === 204 ? null : res.json();
  }

  /* --- Escaping ------------------------------------------------------- */
  /* number_plate is free text rendered into the DOM on an unauthenticated
     page. Without escaping this is a stored-XSS hole. */

  var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/[&<>"']/g, function (c) { return ESC[c]; });
  }

  /* --- Timestamps ----------------------------------------------------- */
  /* SQLite does not persist tzinfo, so values come back naive. Treat a
     zone-less string as UTC, then render and edit in browser local time. */

  function parseTs(value) {
    if (!value) return null;
    var hasZone = /[Zz]|[+-]\d\d:?\d\d$/.test(value);
    return new Date(hasZone ? value : value + "Z");
  }

  // Indian standard presentation: DD/MM/YYYY with 12-hour AM/PM.
  // en-IN pins day-before-month regardless of the device locale, and
  // hour12 forces AM/PM even where the locale would default to 24-hour.
  function fmtTs(date) {
    if (!date || isNaN(date.getTime())) return "—";
    return date.toLocaleString("en-IN", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: true,
    }).toUpperCase();   // "am"/"pm" -> "AM"/"PM"
  }

  // Same format without seconds, for the edit-mode read-back label.
  function fmtTsShort(date) {
    if (!date || isNaN(date.getTime())) return "—";
    return date.toLocaleString("en-IN", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
      hour12: true,
    }).toUpperCase();
  }

  // datetime-local wants local wall-clock "YYYY-MM-DDTHH:mm" -- no zone.
  function toLocalInput(date) {
    if (!date || isNaN(date.getTime())) return "";
    var shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return shifted.toISOString().slice(0, 16);
  }

  function fromLocalInput(value) {
    var d = new Date(value); // parsed as local time
    return isNaN(d.getTime()) ? null : d.toISOString();
  }

  /* --- Toast ---------------------------------------------------------- */

  function toast(message, kind) {
    var host = document.getElementById("toasts");
    if (!host) return;
    var el = document.createElement("div");
    el.className = "toast toast-" + (kind || "error");
    el.textContent = message;
    host.appendChild(el);
    setTimeout(function () {
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 200);
    }, 3200);
  }

  /* --- Shared bits of markup ------------------------------------------ */

  function pill(direction) {
    var cls = direction === "IN" ? "pill-in" : "pill-out";
    return '<span class="pill ' + cls + '">' + esc(direction) + "</span>";
  }

  return {
    API: API,
    caps: caps,
    api: api,
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    // Registered by app.js so an expired token swaps back to the login card.
    setAuthFailureHandler: function (fn) { onAuthFailure = fn; },
    esc: esc,
    parseTs: parseTs,
    fmtTs: fmtTs,
    fmtTsShort: fmtTsShort,
    toLocalInput: toLocalInput,
    fromLocalInput: fromLocalInput,
    toast: toast,
    pill: pill,
  };
})();
