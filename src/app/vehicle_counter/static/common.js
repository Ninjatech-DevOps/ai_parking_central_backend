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
  var REFRESH_KEY = "vc_refresh:" + BASE;
  var EXPIRY_KEY = "vc_expiry:" + BASE;

  // Refresh this far ahead of expiry, so a request is never sent with a token
  // that dies in flight.
  var REFRESH_SKEW_MS = 60000;

  var onAuthFailure = null;
  var refreshInFlight = null;

  function read(key) {
    try { return localStorage.getItem(key) || ""; } catch (e) { return ""; }
  }

  function write(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }

  function drop(key) {
    try { localStorage.removeItem(key); } catch (e) { /* private mode */ }
  }

  function getToken() { return read(TOKEN_KEY); }
  function getRefreshToken() { return read(REFRESH_KEY); }

  function expiresAt() {
    return parseInt(read(EXPIRY_KEY) || "0", 10) || 0;
  }

  /** Store a login/refresh response. */
  function setSession(data) {
    write(TOKEN_KEY, data.access_token || "");
    write(REFRESH_KEY, data.refresh_token || "");
    // expires_in is seconds; keep an absolute timestamp so a reload can still
    // tell how much life the token has left.
    var ttl = (parseInt(data.expires_in, 10) || 0) * 1000;
    write(EXPIRY_KEY, String(Date.now() + ttl));
  }

  function clearToken() {
    drop(TOKEN_KEY);
    drop(REFRESH_KEY);
    drop(EXPIRY_KEY);
  }

  function tokenExpiringSoon() {
    var at = expiresAt();
    return at > 0 && Date.now() >= at - REFRESH_SKEW_MS;
  }

  /**
   * Exchange the refresh token for a new pair.
   *
   * Single-flight: concurrent callers share one in-flight request. Without
   * this, several requests hitting expiry together would each fire a refresh
   * and the later ones would race on already-rotated tokens.
   */
  function refreshTokens() {
    if (refreshInFlight) return refreshInFlight;

    var token = getRefreshToken();
    if (!token) return Promise.reject(new Error("No refresh token"));

    refreshInFlight = fetch(API + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: token }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Refresh failed");
        return res.json();
      })
      .then(function (data) {
        setSession(data);
        return data;
      })
      .finally(function () {
        refreshInFlight = null;
      });

    return refreshInFlight;
  }

  /* --- Fetch wrapper -------------------------------------------------- */

  function send(path, opts) {
    var headers = Object.assign({ "Content-Type": "application/json" },
                                (opts && opts.headers) || {});
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetch(API + path, Object.assign({}, opts || {}, { headers: headers }));
  }

  async function api(path, opts) {
    opts = opts || {};

    // Proactive: renew before the token dies, so the operator never sees a
    // failed request in the first place.
    if (getRefreshToken() && tokenExpiringSoon()) {
      try {
        await refreshTokens();
      } catch (e) { /* fall through; the reactive path below still applies */ }
    }

    // Single choke point: every call site inherits the token and the 401
    // handling below without any change of its own.
    var res = await send(path, opts);

    // Reactive: a 401 despite the check above (clock skew, or a token
    // invalidated server-side). Try once more with a fresh token.
    if (res.status === 401 && getRefreshToken()) {
      try {
        await refreshTokens();
        res = await send(path, opts);
      } catch (e) { /* refresh failed; handled just below */ }
    }

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

  /**
   * Same auth handling as api(), but returns the raw Response so a caller can
   * read a binary body (e.g. an .xlsx download).
   *
   * Downloads must not hand-roll their own fetch: doing so skips the token and
   * the refresh retry, which is exactly how the export ended up unauthorised.
   */
  async function apiRaw(path, opts) {
    opts = opts || {};

    if (getRefreshToken() && tokenExpiringSoon()) {
      try {
        await refreshTokens();
      } catch (e) { /* fall through to the reactive path */ }
    }

    var res = await send(path, opts);

    if (res.status === 401 && getRefreshToken()) {
      try {
        await refreshTokens();
        res = await send(path, opts);
      } catch (e) { /* handled below */ }
    }

    if (res.status === 401) {
      clearToken();
      if (onAuthFailure) onAuthFailure();
      throw new Error("Session expired");
    }

    return res;
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
    apiRaw: apiRaw,
    getToken: getToken,
    getRefreshToken: getRefreshToken,
    setSession: setSession,
    clearToken: clearToken,
    refreshTokens: refreshTokens,
    tokenExpiringSoon: tokenExpiringSoon,
    expiresAt: expiresAt,
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
