/* Vehicle counter -- single page.

   Section 1: two counter columns (Car, 2W). The column decides vehicle_type,
   the button decides direction. Tapping is never gated by URL params.

   Section 2: the listing -- filters, pagination, inline edit, delete, export.
   Edit / delete / export are gated on ?edit, ?delete, ?export. */

(function () {
  var PAGE_SIZE = 10;
  var REFRESH_MS = 15000;
  // How often to check whether the access token needs renewing. Independent
  // of the data poll, and runs even while the tab is hidden.
  var TOKEN_CHECK_MS = 30000;

  var tbody = document.getElementById("rows");
  var pager = document.getElementById("pager");
  var pagerInfo = document.getElementById("pager-info");
  var prevBtn = document.getElementById("prev");
  var nextBtn = document.getElementById("next");
  var thActions = document.getElementById("th-actions");
  var refreshBtn = document.getElementById("refresh");

  var fType = document.getElementById("f-type");
  var fFrom = document.getElementById("f-from");
  var fTo = document.getElementById("f-to");

  var page = readPageFromHash();
  var totalPages = 1;
  var colCount = VC.caps.del ? 8 : 7;
  var timer = null;
  var tokenTimer = null;
  var busy = false;

  var TYPE_LABELS = { CAR: "Car", TWO_WHEELER: "2W" };

  /* --- Chrome driven by capabilities ---------------------------------- */

  if (VC.caps.edit) document.body.classList.add("cap-edit");
  if (VC.caps.del) document.body.classList.add("cap-delete");

  if (VC.caps.del) {
    thActions.hidden = false;
    thActions.textContent = "Actions";
  }

  (function renderBanner() {
    if (!VC.caps.edit && !VC.caps.del && !VC.caps.exp) return;
    var parts = [];
    if (VC.caps.edit) parts.push("Editing on — changes save when you click away");
    if (VC.caps.del) parts.push("delete enabled");
    if (VC.caps.exp) parts.push("export enabled");
    document.getElementById("banner").innerHTML =
      '<div class="banner banner-edit">' + VC.esc(parts.join(" · ")) + "</div>";
  })();

  function readPageFromHash() {
    var m = /(?:^|[#&])page=(\d+)/.exec(location.hash);
    var n = m ? parseInt(m[1], 10) : 1;
    return n > 0 ? n : 1;
  }

  function writePageToHash(n) {
    // Only the hash changes -- ?edit&delete&export stays intact.
    history.replaceState(null, "", location.pathname + location.search + "#page=" + n);
  }

  /* --- Counter --------------------------------------------------------- */

  function setStats(stats) {
    document.getElementById("car-in").textContent = stats.car.total_in;
    document.getElementById("car-out").textContent = stats.car.total_out;
    document.getElementById("car-inside").textContent = stats.car.currently_inside;
    document.getElementById("tw-in").textContent = stats.two_wheeler.total_in;
    document.getElementById("tw-out").textContent = stats.two_wheeler.total_out;
    document.getElementById("tw-inside").textContent =
      stats.two_wheeler.currently_inside;

    // Taken straight from the server rather than adding the two columns here,
    // so the strip can never drift from the per-type figures.
    document.getElementById("total-in").textContent = stats.overall.total_in;
    document.getElementById("total-out").textContent = stats.overall.total_out;
    document.getElementById("total-inside").textContent =
      stats.overall.currently_inside;
  }

  function flashTile(tile) {
    if (!tile) return;
    tile.classList.remove("pulse");
    void tile.offsetWidth; // restart the animation
    tile.classList.add("pulse");
  }

  function pulse(vehicleType, direction) {
    var cls = direction === "IN" ? ".cstat-in" : ".cstat-out";

    var col = document.querySelector('[data-col="' + vehicleType + '"]');
    if (col) flashTile(col.querySelector(cls));

    // The combined figure moves too, so flash it alongside the per-type one.
    flashTile(document.querySelector('.totals [data-total="' + direction + '"]'));
  }

  async function record(vehicleType, direction) {
    // Guard against an impatient double-tap logging two vehicles.
    if (busy) return;
    busy = true;
    setTapsDisabled(true);
    try {
      await VC.api("/events", {
        method: "POST",
        body: JSON.stringify({ direction: direction, vehicle_type: vehicleType }),
      });
      if (navigator.vibrate) navigator.vibrate(30);
      pulse(vehicleType, direction);
      // Back to page 1 so the row just recorded is visible.
      await Promise.all([loadStats(), load(1)]);
      scheduleRefresh();          // a tap counts as activity
    } catch (err) {
      VC.toast(err.message);
    } finally {
      busy = false;
      setTapsDisabled(false);
    }
  }

  function setTapsDisabled(disabled) {
    document.querySelectorAll(".tap").forEach(function (b) {
      b.disabled = disabled;
    });
  }

  document.querySelector(".counters").addEventListener("click", function (e) {
    var btn = e.target.closest(".tap");
    if (!btn) return;
    record(btn.dataset.vehicleType, btn.dataset.direction);
  });

  /* --- Cell rendering -------------------------------------------------- */

  function typeCell(row) {
    var label = TYPE_LABELS[row.vehicle_type] || row.vehicle_type;
    if (!VC.caps.edit) {
      return '<td data-label="Type"><span class="type-pill type-' +
        VC.esc(row.vehicle_type) + '">' + VC.esc(label) + "</span></td>";
    }
    return '<td data-label="Type" class="editable">' +
      '<select data-field="vehicle_type" data-original="' +
      VC.esc(row.vehicle_type) + '">' +
      '<option value="CAR"' +
      (row.vehicle_type === "CAR" ? " selected" : "") + ">Car</option>" +
      '<option value="TWO_WHEELER"' +
      (row.vehicle_type === "TWO_WHEELER" ? " selected" : "") + ">2 Wheeler</option>" +
      "</select></td>";
  }

  function plateCell(row) {
    var value = row.number_plate || "";
    if (!VC.caps.edit) {
      return '<td data-label="Plate">' + (value
        ? '<span class="plate">' + VC.esc(value) + "</span>"
        : '<span class="muted">—</span>') + "</td>";
    }
    return '<td data-label="Plate" class="editable">' +
      '<input type="text" data-field="number_plate" maxlength="30" ' +
      'placeholder="Add plate" spellcheck="false" autocomplete="off" ' +
      'data-original="' + VC.esc(value) + '" value="' + VC.esc(value) + '"></td>';
  }

  function timeCell(row) {
    var date = VC.parseTs(row.timestamp);
    if (!VC.caps.edit) {
      return '<td data-label="Time" class="ts">' + VC.esc(VC.fmtTs(date)) + "</td>";
    }
    var local = VC.toLocalInput(date);
    return '<td data-label="Time" class="editable">' +
      '<div class="ts-edit">' +
      '<input type="datetime-local" step="1" data-field="timestamp" ' +
      'data-original="' + VC.esc(local) + '" value="' + VC.esc(local) + '">' +
      '<span class="ts-read" data-ts-read>' + VC.esc(VC.fmtTsShort(date)) + '</span>' +
      '</div></td>';
  }

  function directionCell(row) {
    if (!VC.caps.edit) {
      return '<td data-label="Direction">' + VC.pill(row.direction) + "</td>";
    }
    return '<td data-label="Direction" class="editable">' +
      '<select data-field="direction" data-original="' + VC.esc(row.direction) + '">' +
      '<option value="IN"' + (row.direction === "IN" ? " selected" : "") + ">IN</option>" +
      '<option value="OUT"' + (row.direction === "OUT" ? " selected" : "") + ">OUT</option>" +
      "</select></td>";
  }

  function rowHtml(row) {
    var html =
      '<tr data-id="' + row.id + '">' +
      '<td data-label="#" class="num">' + row.id + "</td>" +
      typeCell(row) +
      directionCell(row) +
      '<td data-label="In" class="num" data-cell="in_count">' + row.in_count + "</td>" +
      '<td data-label="Out" class="num" data-cell="out_count">' + row.out_count + "</td>" +
      plateCell(row) +
      timeCell(row);

    if (VC.caps.del) {
      html += '<td data-label="Actions">' +
        '<button class="btn btn-danger" data-del type="button">Delete</button></td>';
    }
    return html + "</tr>";
  }

  /* --- Filters --------------------------------------------------------- */

  function filterParams() {
    var params = new URLSearchParams();
    if (fType.value) params.set("vehicle_type", fType.value);
    if (fFrom.value) params.set("start_date", fFrom.value);
    if (fTo.value) params.set("end_date", fTo.value);
    return params;
  }

  [fType, fFrom, fTo].forEach(function (el) {
    el.addEventListener("change", function () {
      load(1);          // any filter change resets to the first page
    });
  });

  document.getElementById("f-clear").addEventListener("click", function () {
    fType.value = "";
    fFrom.value = "";
    fTo.value = "";
    load(1);
  });

  /* --- Loading --------------------------------------------------------- */

  async function loadStats() {
    try {
      setStats(await VC.api("/stats"));
    } catch (err) {
      VC.toast(err.message);
    }
  }

  async function load(targetPage) {
    page = targetPage;
    writePageToHash(page);

    var params = filterParams();
    params.set("page", page);
    params.set("page_size", PAGE_SIZE);

    try {
      var data = await VC.api("/events?" + params.toString());

      // A delete can empty the last page; step back rather than showing nothing.
      if (!data.items.length && page > 1) return load(page - 1);

      totalPages = data.total_pages || 1;

      tbody.innerHTML = data.items.length
        ? data.items.map(rowHtml).join("")
        : '<tr><td colspan="' + colCount +
          '" class="empty">No entries match these filters.</td></tr>';

      pager.hidden = totalPages <= 1;
      pagerInfo.textContent = "Page " + page + " of " + totalPages + " · " +
        data.total + " total";
      prevBtn.disabled = page <= 1;
      nextBtn.disabled = page >= totalPages;
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="' + colCount +
        '" class="empty">Could not load records.</td></tr>';
      VC.toast(err.message);
    }
  }

  /* --- Refresh: one timer, restarted by the manual button -------------- */

  function editingInProgress() {
    var active = document.activeElement;
    return !!(active && active.closest && active.closest("[data-field]"));
  }

  async function refreshAll(force) {
    // An auto tick must never discard a half-typed cell. An explicit click may.
    if (!force && editingInProgress()) {
      await loadStats();
      return;
    }
    await Promise.all([loadStats(), load(page)]);
  }

  function scheduleRefresh() {
    // clearInterval before setInterval -- otherwise repeated clicks stack
    // timers and multiply the request rate.
    clearInterval(timer);
    timer = setInterval(function () {
      if (!document.hidden) refreshAll(false);
    }, REFRESH_MS);
  }

  refreshBtn.addEventListener("click", async function () {
    refreshBtn.classList.add("spinning");
    refreshBtn.disabled = true;
    try {
      await refreshAll(true);
      scheduleRefresh();          // countdown restarts from zero
    } finally {
      refreshBtn.classList.remove("spinning");
      refreshBtn.disabled = false;
    }
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refreshAll(false);
  });

  /* --- Inline edit: commit on focus out -------------------------------- */

  /* Adopt server truth after a PATCH: the normalised plate, the derived
     in/out counts, and fresh data-original values for every editable cell. */
  function applyServerRow(tr, row) {
    var inCell = tr.querySelector('[data-cell="in_count"]');
    var outCell = tr.querySelector('[data-cell="out_count"]');
    if (inCell) inCell.textContent = row.in_count;
    if (outCell) outCell.textContent = row.out_count;

    var plate = tr.querySelector('[data-field="number_plate"]');
    if (plate) {
      plate.value = row.number_plate || "";
      plate.dataset.original = plate.value;
    }

    var direction = tr.querySelector('[data-field="direction"]');
    if (direction) {
      direction.value = row.direction;
      direction.dataset.original = row.direction;
    }

    var vtype = tr.querySelector('[data-field="vehicle_type"]');
    if (vtype) {
      vtype.value = row.vehicle_type;
      vtype.dataset.original = row.vehicle_type;
    }

    var ts = tr.querySelector('[data-field="timestamp"]');
    if (ts) {
      var parsed = VC.parseTs(row.timestamp);
      ts.value = VC.toLocalInput(parsed);
      ts.dataset.original = ts.value;
      var readback = tr.querySelector("[data-ts-read]");
      if (readback) readback.textContent = VC.fmtTsShort(parsed);
    }
  }

  function flash(el, cls) {
    el.classList.add(cls);
    setTimeout(function () { el.classList.remove(cls); }, cls === "saved" ? 900 : 1500);
  }

  async function commit(el) {
    var tr = el.closest("tr");
    var field = el.dataset.field;
    var original = el.dataset.original;
    var raw = el.value;

    if (raw === original) return;          // nothing changed
    if (el.dataset.saving === "1") return; // change + focusout double-fire

    var payload;
    if (field === "number_plate") {
      var plate = raw.trim().toUpperCase();
      payload = { number_plate: plate === "" ? null : plate };
    } else if (field === "timestamp") {
      var iso = VC.fromLocalInput(raw);
      if (!iso) {                          // cleared or invalid: required field
        el.value = original;
        return;
      }
      payload = { timestamp: iso };
    } else if (field === "direction") {
      // Only the direction is sent; the server derives in_count/out_count.
      payload = { direction: raw };
    } else if (field === "vehicle_type") {
      payload = { vehicle_type: raw };
    } else {
      return;
    }

    el.dataset.saving = "1";
    el.classList.add("saving");
    try {
      var updated = await VC.api("/events/" + tr.dataset.id, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      el.classList.remove("saving");
      applyServerRow(tr, updated);
      flash(el, "saved");
      // Both of these move the per-type totals.
      if (field === "direction" || field === "vehicle_type") loadStats();
    } catch (err) {
      el.value = original;                 // revert
      el.classList.remove("saving");
      flash(el, "failed");
      VC.toast(err.message);
    } finally {
      el.dataset.saving = "0";
    }
  }

  /* Delegated listeners on tbody, so re-rendering rows cannot leak handlers. */

  tbody.addEventListener("keydown", function (e) {
    if (!e.target.matches("[data-field]")) return;
    if (e.key === "Enter") {
      e.preventDefault();
      e.target.blur();                     // blur commits
    } else if (e.key === "Escape") {
      e.target.value = e.target.dataset.original;
      e.target.blur();                     // abandon without saving
    }
  });

  // focusout, not blur -- blur does not bubble.
  tbody.addEventListener("focusout", function (e) {
    if (e.target.matches("input[data-field], select[data-field]")) commit(e.target);
  });

  // Selects also commit on change so a mouse pick saves without a second click.
  tbody.addEventListener("change", function (e) {
    if (e.target.matches("select[data-field]")) commit(e.target);
  });

  /* --- Delete ---------------------------------------------------------- */

  tbody.addEventListener("click", async function (e) {
    var btn = e.target.closest("button[data-del]");
    if (!btn || !VC.caps.del) return;

    var tr = btn.closest("tr");
    if (!confirm("Delete entry #" + tr.dataset.id + "? This cannot be undone.")) return;

    btn.disabled = true;
    try {
      await VC.api("/events/" + tr.dataset.id, { method: "DELETE" });
      // Reload rather than dropping the row: deleting shifts every later page
      // and changes the totals.
      await Promise.all([load(page), loadStats()]);
    } catch (err) {
      btn.disabled = false;
      VC.toast(err.message);
    }
  });

  /* --- Export ---------------------------------------------------------- */

  var modal = document.getElementById("export-modal");
  var fromInput = document.getElementById("export-from");
  var toInput = document.getElementById("export-to");
  var typeInput = document.getElementById("export-type");
  var exportBtn = document.getElementById("do-export");
  var openBtn = document.getElementById("open-export");

  function openExport() {
    // Prefill from the table filters so what you see is what you export.
    fromInput.value = fFrom.value;
    toInput.value = fTo.value;
    typeInput.value = fType.value;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeExport() {
    modal.hidden = true;
    document.body.style.overflow = "";
  }

  if (VC.caps.exp) {
    openBtn.hidden = false;
    openBtn.addEventListener("click", openExport);
  } else {
    // Remove rather than hide. A hidden attribute can be defeated by any CSS
    // display rule (and by a stale cached stylesheet), so the gate must not
    // depend on CSS at all -- if the capability is absent, the control and its
    // modal simply do not exist in the DOM.
    if (openBtn.parentNode) openBtn.parentNode.removeChild(openBtn);
    if (modal.parentNode) modal.parentNode.removeChild(modal);
  }

  modal.addEventListener("click", function (e) {
    if (e.target.closest("[data-close-export]")) closeExport();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeExport();
  });

  modal.addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (!chip) return;

    modal.querySelectorAll(".chip").forEach(function (c) {
      c.classList.remove("active");
    });
    chip.classList.add("active");

    var range = chip.dataset.range;
    if (range === "all") {
      fromInput.value = "";
      toInput.value = "";
      return;
    }

    var end = new Date();
    var start = new Date();
    if (range === "today") {
      start.setHours(0, 0, 0, 0);
    } else {
      start.setDate(start.getDate() - parseInt(range, 10));
      start.setHours(0, 0, 0, 0);
    }
    fromInput.value = VC.toLocalInput(start);
    toInput.value = VC.toLocalInput(end);
  });

  [fromInput, toInput].forEach(function (input) {
    input.addEventListener("input", function () {
      modal.querySelectorAll(".chip").forEach(function (c) {
        c.classList.remove("active");
      });
    });
  });

  exportBtn.addEventListener("click", async function () {
    var from = fromInput.value;
    var to = toInput.value;

    if (from && to && new Date(from) > new Date(to)) {
      VC.toast("“From” must be before “To”");
      return;
    }

    var params = new URLSearchParams();
    if (from) params.set("start_date", from);
    if (to) params.set("end_date", to);
    if (typeInput.value) params.set("vehicle_type", typeInput.value);

    var label = exportBtn.textContent;
    exportBtn.disabled = true;
    exportBtn.textContent = "Preparing…";

    try {
      // apiRaw, not a bare fetch: the download needs the same auth token and
      // refresh handling as every other call, but a binary body back.
      var res = await VC.apiRaw(
        "/events/export" + (params.toString() ? "?" + params : "")
      );
      if (!res.ok) {
        var msg = "Export failed (" + res.status + ")";
        try {
          var body = await res.json();
          if (body && body.detail) msg = body.detail;
        } catch (e) { /* binary or empty body */ }
        throw new Error(msg);
      }

      var blob = await res.blob();

      var name = "vehicle_log.xlsx";
      var disp = res.headers.get("Content-Disposition") || "";
      var match = /filename="?([^";]+)"?/.exec(disp);
      if (match) name = match[1];

      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      closeExport();
      VC.toast("Export downloaded", "ok");
    } catch (err) {
      VC.toast(err.message);
    } finally {
      exportBtn.disabled = false;
      exportBtn.textContent = label;
    }
  });

  /* --- Pagination ------------------------------------------------------ */

  prevBtn.addEventListener("click", function () { if (page > 1) load(page - 1); });
  nextBtn.addEventListener("click", function () { if (page < totalPages) load(page + 1); });

  /* --- Auth and boot --------------------------------------------------- */

  var loginView = document.getElementById("login-view");
  var appView = document.getElementById("app-view");
  var loginForm = document.getElementById("login-form");
  var passwordInput = document.getElementById("login-password");
  var loginError = document.getElementById("login-error");
  var loginSubmit = document.getElementById("login-submit");
  var started = false;

  function showLogin(message) {
    clearInterval(timer);            // stop polling while signed out
    clearInterval(tokenTimer);       // and stop renewing the session
    appView.hidden = true;
    loginView.hidden = false;
    started = false;

    if (message) {
      loginError.textContent = message;
      loginError.hidden = false;
    } else {
      loginError.hidden = true;
    }
    passwordInput.value = "";
    passwordInput.focus();
  }

  function startApp() {
    loginView.hidden = true;
    appView.hidden = false;

    // Guard against double-booting (e.g. login while already started), which
    // would otherwise leave two refresh timers running.
    if (started) return;
    started = true;

    loadStats();
    load(page);
    scheduleRefresh();
    scheduleTokenRenewal();
  }

  /* Keep the session alive independently of the data poll.

     The data poll deliberately pauses while the tab is hidden, but the token
     must not: a tablet left on a backgrounded tab should still be signed in
     when the operator returns. */
  function scheduleTokenRenewal() {
    clearInterval(tokenTimer);
    tokenTimer = setInterval(function () {
      if (!VC.getRefreshToken()) return;
      if (!VC.tokenExpiringSoon()) return;
      VC.refreshTokens().catch(function () {
        // Refresh token itself is dead -- the next API call surfaces it.
      });
    }, TOKEN_CHECK_MS);
  }

  // Any 401 from any call site lands here.
  VC.setAuthFailureHandler(function () {
    showLogin("Session expired, please sign in again.");
  });

  loginForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    var password = passwordInput.value;
    if (!password) {
      loginError.textContent = "Enter the password.";
      loginError.hidden = false;
      return;
    }

    loginSubmit.disabled = true;
    loginSubmit.textContent = "Signing in…";
    loginError.hidden = true;
    try {
      // Not via VC.api: a 401 here means "wrong password", not "session
      // expired", and must not trigger the auth-failure handler.
      var res = await fetch(VC.API + "/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: password }),
      });
      var body = await res.json().catch(function () { return {}; });
      if (!res.ok) {
        throw new Error(body.detail || "Sign in failed (" + res.status + ")");
      }
      VC.setSession(body);
      startApp();
    } catch (err) {
      loginError.textContent = err.message;
      loginError.hidden = false;
      passwordInput.select();
    } finally {
      loginSubmit.disabled = false;
      loginSubmit.textContent = "Sign in";
    }
  });

  (async function boot() {
    // No stored token: show the login card without firing any API call, so an
    // unauthenticated load produces zero 401s.
    if (!VC.getToken()) {
      showLogin();
      return;
    }
    try {
      await VC.api("/auth/me");
      startApp();
    } catch (err) {
      // VC.api already cleared the token and invoked the failure handler.
      if (!loginView.hidden) return;
      showLogin();
    }
  })();
})();
