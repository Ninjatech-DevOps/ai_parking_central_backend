/* Records page.

   Capabilities come from bare URL params: ?edit, ?delete, ?edit&delete.
   With neither, the page is view-only.

   No polling here on purpose -- an auto-refresh would wipe a half-typed cell.
   The table re-renders only on an explicit user action. */

(function () {
  var PAGE_SIZE = 20;

  var tbody = document.getElementById("rows");
  var pager = document.getElementById("pager");
  var pagerInfo = document.getElementById("pager-info");
  var prevBtn = document.getElementById("prev");
  var nextBtn = document.getElementById("next");
  var thActions = document.getElementById("th-actions");

  var page = readPageFromHash();
  var totalPages = 1;
  var colCount = VC.caps.del ? 7 : 6;

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
    // Only the hash changes -- ?edit&delete stays intact.
    history.replaceState(null, "", location.pathname + location.search + "#page=" + n);
  }

  /* --- Cell rendering -------------------------------------------------- */

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

  /* --- Loading --------------------------------------------------------- */

  async function loadStats() {
    try {
      var s = await VC.api("/stats");
      document.getElementById("stat-in").textContent = s.total_in;
      document.getElementById("stat-out").textContent = s.total_out;
      document.getElementById("stat-inside").textContent = s.currently_inside;
    } catch (err) {
      VC.toast(err.message);
    }
  }

  async function load(targetPage) {
    page = targetPage;
    writePageToHash(page);
    try {
      var data = await VC.api("/events?page=" + page + "&page_size=" + PAGE_SIZE);

      // A delete can empty the last page; step back rather than showing nothing.
      if (!data.items.length && page > 1) return load(page - 1);

      totalPages = data.total_pages || 1;

      tbody.innerHTML = data.items.length
        ? data.items.map(rowHtml).join("")
        : '<tr><td colspan="' + colCount + '" class="empty">No entries yet.</td></tr>';

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
      if (!iso) {                          // cleared or invalid: timestamp is required
        el.value = original;
        return;
      }
      payload = { timestamp: iso };
    } else if (field === "direction") {
      // Only the direction is sent; the server derives in_count/out_count.
      payload = { direction: raw };
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
      if (field === "direction") loadStats(); // totals moved
    } catch (err) {
      el.value = original;                 // revert, matching the app's edit pattern
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
  var exportBtn = document.getElementById("do-export");
  var openBtn = document.getElementById("open-export");

  function openExport() {
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
  }

  modal.addEventListener("click", function (e) {
    if (e.target.closest("[data-close-export]")) closeExport();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeExport();
  });

  // Quick range chips fill the two inputs.
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

  // Clearing a chip selection when the user edits a field by hand.
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
      VC.toast("\u201cFrom\u201d must be before \u201cTo\u201d");
      return;
    }

    var params = new URLSearchParams();
    if (from) params.set("start_date", from);
    if (to) params.set("end_date", to);

    var label = exportBtn.textContent;
    exportBtn.disabled = true;
    exportBtn.textContent = "Preparing…";

    try {
      // Binary response, so fetch a blob rather than going through VC.api.
      var res = await fetch(
        VC.API + "/events/export" + (params.toString() ? "?" + params : "")
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

      // Prefer the filename the server set in Content-Disposition.
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

  load(page);
  loadStats();
})();
