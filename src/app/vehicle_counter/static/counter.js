/* Counter page.

   Read-only by construction: this file never reads VC.caps, so no URL param
   can turn on editing here. Recording a tap is the only write it performs. */

(function () {
  var POLL_MS = 15000;

  var btnIn = document.getElementById("btn-in");
  var btnOut = document.getElementById("btn-out");
  var recentBody = document.getElementById("recent");

  var busy = false;

  function setStat(id, value) {
    document.getElementById(id).textContent = value;
  }

  function pulse(direction) {
    var tile = document.getElementById(direction === "IN" ? "tile-in" : "tile-out");
    tile.classList.remove("pulse");
    void tile.offsetWidth; // restart the animation
    tile.classList.add("pulse");
  }

  function renderRecent(rows) {
    if (!rows.length) {
      recentBody.innerHTML =
        '<tr><td colspan="4" class="empty">No entries yet — tap + or − to start.</td></tr>';
      return;
    }
    // Plain text cells only: no inputs, no buttons, nothing actionable.
    recentBody.innerHTML = rows.map(function (r) {
      var plate = r.number_plate
        ? '<span class="plate">' + VC.esc(r.number_plate) + "</span>"
        : '<span class="muted">—</span>';
      return (
        '<tr>' +
        '<td data-label="#" class="num">' + r.id + "</td>" +
        '<td data-label="Direction">' + VC.pill(r.direction) + "</td>" +
        '<td data-label="Plate">' + plate + "</td>" +
        '<td data-label="Time" class="ts">' + VC.esc(VC.fmtTs(VC.parseTs(r.timestamp))) + "</td>" +
        "</tr>"
      );
    }).join("");
  }

  async function refresh() {
    try {
      var data = await VC.api("/summary?recent_limit=10");
      setStat("stat-in", data.stats.total_in);
      setStat("stat-out", data.stats.total_out);
      setStat("stat-inside", data.stats.currently_inside);
      renderRecent(data.recent);
    } catch (err) {
      VC.toast(err.message);
    }
  }

  async function record(direction) {
    // Guard against an impatient double-tap logging two vehicles.
    if (busy) return;
    busy = true;
    btnIn.disabled = true;
    btnOut.disabled = true;
    try {
      await VC.api("/events", {
        method: "POST",
        body: JSON.stringify({ direction: direction }),
      });
      if (navigator.vibrate) navigator.vibrate(30);
      pulse(direction);
      await refresh();
    } catch (err) {
      VC.toast(err.message);
    } finally {
      busy = false;
      btnIn.disabled = false;
      btnOut.disabled = false;
    }
  }

  btnIn.addEventListener("click", function () { record("IN"); });
  btnOut.addEventListener("click", function () { record("OUT"); });

  // Poll so a second device's taps show up, but never while backgrounded --
  // a forgotten kiosk tab should not hammer the API overnight.
  setInterval(function () {
    if (!document.hidden) refresh();
  }, POLL_MS);

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refresh();
  });

  refresh();
})();
