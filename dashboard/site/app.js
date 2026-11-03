/* Fleet compliance dashboard, live demo. The page polls /api/state every few seconds with the access code and the
   last ETag; the server answers 304 until a document changes a cab's record. Nothing is kept in the browser except
   the access code for this tab (sessionStorage), so a reload does not ask again. */
(function () {
  "use strict";
  var POLL_MS = 4000, CODE_KEY = "fleet_demo_code", IST = "Asia/Kolkata";
  var state = { code: null, etag: null, data: null, timer: null, open: null, marks: {} };
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var esc = function (v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  // ---------------------------------------------------------------- formatting
  function when(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString("en-IN", { timeZone: IST, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) + " IST";
  }
  function clock(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleTimeString("en-IN", { timeZone: IST, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }
  function day(iso) {
    if (!iso) return "-";
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return iso;
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return d.toLocaleDateString("en-IN", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" });
  }
  var inr = function (n) { return n == null ? "" : "₹" + Number(n).toLocaleString("en-IN"); };
  var kms = function (n) { return n == null ? "-" : Number(n).toLocaleString("en-IN") + " km"; };
  var secs = function (n) { return n == null ? "" : n + " s"; };

  // ---------------------------------------------------------------- badges
  var OUT = { accepted: "b-green", accepted_with_notes: "b-green", more_proof_needed: "b-amber", rejected: "b-red", pending_review: "b-blue" };
  function outBadge(x) { return '<span class="badge ' + (OUT[x.outcome] || "b-grey") + '">' + esc(x.outcome_label) + "</span>"; }
  var ST = { GOOD: "b-green", WATCH: "b-amber", ACTION: "b-red", NONE: "b-grey" };
  function statusBadge(c) { return '<span class="badge ' + (ST[c.status.code] || "b-grey") + '" title="' + esc(c.status.headline) + '">' + esc(c.status.label) + "</span>"; }
  function consentBadge(c) {
    if (!c.consent) return '<span class="badge b-grey">Pending</span>';
    if (c.consent.status === "withdrawn") return '<span class="badge b-red">Withdrawn</span>';
    return '<span class="badge b-green" title="' + esc(when(c.consent.at)) + '">Given</span>';
  }
  var VAL = { OK: "b-green", DUE: "b-amber", EXPIRED: "b-red", UNKNOWN: "b-grey" };
  function valBadge(v) {
    var t = v.state === "EXPIRED" ? "Expired " + day(v.till) : v.state === "DUE" ? "Due " + day(v.till) : v.till ? "Till " + day(v.till) : "No date";
    return '<span class="badge ' + (VAL[v.state] || "b-grey") + '">' + esc(t) + "</span>";
  }
  var SEV = { reject: ["b-red", "Rejected"], more_proof: ["b-amber", "More proof"], review: ["b-blue", "Review"], info: ["b-grey", "Noted"] };
  function flagLine(f) {
    var s = SEV[f.severity] || ["b-grey", f.severity];
    return '<li><span class="badge ' + s[0] + '">' + esc(s[1]) + "</span> " + esc(f.detail) + ' <span class="hint">' + esc(f.code) + "</span></li>";
  }

  // ---------------------------------------------------------------- fetching
  function AuthError() { this.name = "AuthError"; }
  async function fetchState() {
    var h = { "Authorization": "Bearer " + state.code };
    if (state.etag) h["If-None-Match"] = state.etag;
    var r = await fetch("api/state", { headers: h, cache: "no-store" });
    if (r.status === 304) return null;
    if (r.status === 401) throw new AuthError();
    if (!r.ok) throw new Error("HTTP " + r.status);
    state.etag = r.headers.get("ETag");
    return r.json();
  }
  function setLive(ok, text) {
    $("#live-dot").className = "dot" + (ok ? " on" : " off");
    $("#live-text").textContent = text || (ok ? "Live" : "Reconnecting");
  }
  function schedule() {
    clearTimeout(state.timer);
    state.timer = setTimeout(poll, POLL_MS);
  }
  async function poll() {
    try {
      var d = await fetchState();
      if (d) apply(d);
      setLive(true, "Live · last change " + clock(state.data && state.data.as_of));
    } catch (e) {
      if (e instanceof AuthError) return lock("The access code stopped working. Please enter it again.");
      setLive(false);
    }
    schedule();
  }

  // ---------------------------------------------------------------- lock and unlock
  function lock(message) {
    clearTimeout(state.timer);
    try { sessionStorage.removeItem(CODE_KEY); } catch (e) { /* private window */ }
    state.code = null; state.etag = null; state.data = null;
    $("#app").hidden = true; $("#lock").hidden = false; $("#drawer").hidden = true;
    $("#lock-err").textContent = message || "";
  }
  async function unlock(code) {
    state.code = code; state.etag = null;
    var d = await fetchState();
    try { sessionStorage.setItem(CODE_KEY, code); } catch (e) { /* private window */ }
    apply(d);
    $("#lock").hidden = true; $("#app").hidden = false;
    setLive(true, "Live · last change " + clock(d.as_of));
    schedule();
  }
  $("#unlock-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var btn = $("#unlock-btn"), err = $("#lock-err");
    err.textContent = ""; btn.disabled = true; btn.textContent = "Opening...";
    try {
      await unlock($("#pw").value.trim());
      $("#pw").value = "";
    } catch (ex) {
      state.code = null;
      err.textContent = ex instanceof AuthError ? "That access code did not open the dashboard. Please check it and try again." : "Could not reach the dashboard service. Please try again.";
    } finally { btn.disabled = false; btn.textContent = "Open dashboard"; }
  });
  $("#lock-btn").addEventListener("click", function () { lock(); });
  (function autoUnlock() {
    var saved = null;
    try { saved = sessionStorage.getItem(CODE_KEY); } catch (e) { /* private window */ }
    if (saved) unlock(saved).catch(function () { lock(); });
  })();

  // ---------------------------------------------------------------- apply new state
  function mark(c) { return c.counts.documents + "|" + c.status.code + "|" + c.status.label + "|" + (c.consent ? c.consent.status : "none") + "|" + c.open_actions.length; }
  function apply(d) {
    var changed = [];
    d.cabs.forEach(function (c) {
      var m = mark(c);
      if (state.data && state.marks[c.vn] !== undefined && state.marks[c.vn] !== m) changed.push(c.vn);
      state.marks[c.vn] = m;
    });
    state.data = d;
    render();
    changed.forEach(function (vn) {
      document.querySelectorAll('[data-vn="' + vn + '"]').forEach(function (el) {
        el.classList.add("flash");
        setTimeout(function () { el.classList.remove("flash"); }, 2600);
      });
    });
    if (state.open && (changed.indexOf(state.open) >= 0 || !$("#drawer").hidden && changed.length)) openCab(state.open, true);
  }

  // ---------------------------------------------------------------- render
  function render() {
    var d = state.data, k = d.kpis;
    $("#client").textContent = d.client;
    $("#foot-asof").textContent = when(d.as_of);
    var kp = [
      ["navy", k.cabs, "Cabs registered"],
      [k.consented === k.cabs ? "green" : "amber", k.consented + "/" + k.cabs, "Drivers who replied YES"],
      ["navy", k.documents, "Documents received"],
      ["green", k.accepted, "Accepted as proof"],
      [k.rejected + k.needs_more ? "amber" : "green", k.rejected + k.needs_more, "Rejected or more proof asked"],
      [k.open_actions ? "red" : "green", k.open_actions, "Safety actions open"],
      [k.papers_due ? "red" : "green", k.papers_due, "Papers expired or due in 30 days"],
      ["navy", k.median_seconds == null ? "-" : k.median_seconds + " s", "Median photo-to-reply time"]
    ];
    $("#kpis").innerHTML = kp.map(function (x) {
      return '<div class="kpi ' + x[0] + '"><div class="v">' + esc(x[1]) + '</div><div class="l">' + esc(x[2]) + "</div></div>";
    }).join("");
    renderActivity(); renderTable(); renderTrain();
  }

  function renderActivity() {
    var a = state.data.activity;
    $("#activity-body").innerHTML = a.length ? '<div class="table-wrap"><table class="grid acts"><thead><tr><th>When</th><th>Cab</th><th>Document</th><th>Result</th><th>What the rules found</th><th>Time</th></tr></thead><tbody>' +
      a.map(function (x) {
        var cab = state.data.cabs.find(function (c) { return c.cab_id === x.cab_id; });
        return '<tr data-vn="' + esc(cab ? cab.vn : "") + '"><td class="nowrap">' + esc(when(x.at)) + '</td><td class="veh">' + esc(x.cab_id) + ' <span class="hint">' + esc(x.vehicle) + "</span></td><td>" + esc(x.label) +
          "</td><td>" + outBadge(x) + '</td><td class="why">' + esc(x.headline) + '</td><td class="nowrap">' + esc(secs(x.seconds)) + "</td></tr>";
      }).join("") + "</tbody></table></div>" :
      '<div class="empty">No documents yet. When a driver sends the first bill, it appears here within seconds.</div>';
    document.querySelectorAll("#activity-body tr[data-vn]").forEach(function (tr) { tr.addEventListener("click", function () { openCab(tr.dataset.vn); }); });
  }

  function renderTable() {
    var q = ($("#q").value || "").toLowerCase().replace(/[^a-z0-9 ]/g, ""), f = $("#f").value;
    var rows = state.data.cabs.filter(function (c) {
      var hay = (c.cab_id + " " + c.vn + " " + c.vehicle + " " + c.driver).toLowerCase().replace(/[^a-z0-9 ]/g, "");
      if (q && hay.indexOf(q) < 0 && hay.indexOf(q.replace(/ /g, "")) < 0) return false;
      return f === "all" || c.status.code === f;
    });
    $("#cab-table tbody").innerHTML = rows.map(function (c) {
      var lb = c.last_bill;
      return '<tr data-vn="' + esc(c.vn) + '"><td class="veh">' + esc(c.cab_id) + '</td><td class="veh">' + esc(c.vehicle) + "</td><td>" + esc(c.driver || "-") + "</td><td>" + esc(c.language) +
        "</td><td>" + consentBadge(c) + "</td><td>" + statusBadge(c) + '</td><td class="nowrap">' + (lb ? esc(day(lb.date)) + '<div class="hint">' + esc(lb.workshop || "") + "</div>" : "-") +
        "</td><td>" + esc(kms(c.last_odometer)) + "</td><td>" + (c.open_actions.length ? c.open_actions.map(function (o) { return '<span class="badge b-red">' + esc(o.label) + "</span>"; }).join(" ") : '<span class="badge b-green">None</span>') +
        "</td><td>" + c.counts.documents + (c.counts.rejected ? ' <span class="hint">(' + c.counts.rejected + " rejected)</span>" : "") +
        "</td><td>" + (c.training ? '<span class="badge b-blue">' + esc(c.training.title || "Sent") + "</span>" : '<span class="hint">With the next accepted bill</span>') + "</td></tr>";
    }).join("") || '<tr><td colspan="11" class="hint">No cabs match.</td></tr>';
    document.querySelectorAll("#cab-table tbody tr[data-vn]").forEach(function (tr) { tr.addEventListener("click", function () { openCab(tr.dataset.vn); }); });
  }
  $("#q").addEventListener("input", renderTable);
  $("#f").addEventListener("change", renderTable);

  function renderTrain() {
    var cabs = state.data.cabs, sent = cabs.filter(function (c) { return c.training; });
    var tile = function (cls, v, l) { return '<div class="' + cls + '"><div class="v">' + esc(v) + '</div><div class="l">' + esc(l) + "</div></div>"; };
    $("#train-body").innerHTML =
      '<div class="train-summary">' + tile("", cabs.length, "Drivers on the programme") + tile("", sent.length, "Module links sent on WhatsApp") +
      tile("", "6", "Languages: Telugu, Hindi, Kannada, Marathi, Tamil, English") + tile("", "10", "Driver modules: rules, signs, defensive driving, vehicle care, risk, emergency, customer, first aid, POSH") + "</div>" +
      '<div class="table-wrap"><table class="grid train"><thead><tr><th>Driver</th><th>Cab</th><th>Language</th><th>Module sent</th><th>Sent with</th></tr></thead><tbody>' +
      cabs.map(function (c) {
        var t = c.training;
        return '<tr data-vn="' + esc(c.vn) + '"><td>' + esc(c.driver) + '</td><td class="veh">' + esc(c.cab_id) + "</td><td>" + esc(c.language) + "</td><td>" +
          (t ? '<span class="badge b-blue">' + esc(t.title || t.module) + "</span>" : '<span class="hint">Goes out with the first accepted bill</span>') + "</td><td>" + (t ? esc(when(t.sent_at)) + (t.reason ? ' <span class="hint">' + esc(t.reason) + "</span>" : "") : "-") + "</td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<p class="hint">Each driver gets their own module link, in their language, with the reply that accepts a bill. A workshop advisory picks the vehicle-care module; a clean bill picks the next module in the sequence.</p>';
    document.querySelectorAll("#train-body tr[data-vn]").forEach(function (tr) { tr.addEventListener("click", function () { openCab(tr.dataset.vn); }); });
  }

  // ---------------------------------------------------------------- cab drawer
  function kv(pairs) {
    return '<dl class="kv">' + pairs.map(function (p) { return "<dt>" + esc(p[0]) + "</dt><dd>" + (p[2] ? p[1] : esc(p[1] || "-")) + "</dd>"; }).join("") + "</dl>";
  }
  function docCard(x) {
    var cls = x.outcome === "rejected" ? " rejected" : (x.outcome === "more_proof_needed" ? " partly" : "");
    var meta = [x.doc_date ? day(x.doc_date) : "", x.workshop, x.invoice_no ? "No. " + x.invoice_no : "", x.odometer_km != null ? kms(x.odometer_km) : "", x.amount != null ? inr(x.amount) : ""].filter(Boolean).map(esc).join(" · ");
    var timing = [x.seconds != null ? "photo to reply " + x.seconds + " s" : "", x.read_ms != null ? "find and read " + (x.read_ms / 1000).toFixed(1) + " s" : "", x.confidence != null ? "confidence " + Math.round(x.confidence * 100) + "%" : ""].filter(Boolean).join(" · ");
    var ph = x.photo, photoLine = "";
    if (ph && ph.error) photoLine = "Photo step failed, the original photo was read.";
    else if (ph && ph.called === false) photoLine = "Paper fills the frame; read as sent.";
    else if (ph && (ph.cropped || Math.abs(ph.angle_deg || 0) >= 0.6)) photoLine = "Paper found by SAM 3.1" + (ph.cover != null ? " (" + Math.round(ph.cover * 100) + "% of the frame)" : "") + (ph.cropped ? ", cropped" : "") + (Math.abs(ph.angle_deg || 0) >= 0.6 ? ", straightened by " + Math.abs(ph.angle_deg).toFixed(1) + "°" : "") + " before reading.";
    else if (ph) photoLine = "Photo checked by SAM 3.1: paper fills the frame, read as sent.";
    return '<div class="svc-card' + cls + '"><div class="svc-head"><div><strong>' + esc(when(x.received_at)) + "</strong> &middot; " + esc(x.label) + '<div class="hint">' + meta + "</div></div>" + outBadge(x) + "</div>" +
      (x.summary ? '<div class="svc-work">' + esc(x.summary) + "</div>" : "") +
      (photoLine ? '<div class="svc-note">' + esc(photoLine) + "</div>" : "") +
      (x.work_done.length ? '<div class="svc-note"><strong>Work done:</strong> ' + esc(x.work_done.join("; ")) + "</div>" : "") +
      (x.advisories.length ? '<div class="svc-note"><strong>Workshop advised:</strong> ' + esc(x.advisories.join("; ")) + "</div>" : "") +
      (x.flags.length ? '<ul class="flags">' + x.flags.map(flagLine).join("") + "</ul>" : '<div class="svc-note">No rule raised a flag.</div>') +
      (x.opened.length ? '<div class="svc-note">Opened safety action: ' + esc(x.opened.join(", ")) + "</div>" : "") +
      (x.closed.length ? '<div class="svc-note">Closed safety action: ' + esc(x.closed.join(", ")) + "</div>" : "") +
      (x.training ? '<div class="svc-note">Module sent with the reply: ' + esc(x.training.title || x.training.module) + "</div>" : "") +
      '<div class="hint timing">' + esc(timing) + (x.ref ? " · file " + esc(x.ref) : "") + "</div></div>";
  }
  function cabSections(c) {
    var s = '<div class="sec"><h4>Status</h4><div class="svc-top">' + statusBadge(c) + '</div><p class="svc-sum">' + esc(c.status.headline) + "</p></div>";
    s += '<div class="sec"><h4>Driver and consent</h4>' + kv([
      ["Driver", c.driver], ["Language", c.language], ["Consent", consentBadge(c) + (c.consent && c.consent.at ? ' <span class="hint">' + esc(when(c.consent.at)) + "</span>" : ""), true],
      ["Documents received", String(c.counts.documents)], ["Last odometer", kms(c.last_odometer)]
    ]) + "</div>";
    s += '<div class="sec"><h4>Vehicle papers</h4>' + (c.validity.length ? kv(c.validity.map(function (v) { return [v.label.charAt(0).toUpperCase() + v.label.slice(1), valBadge(v), true]; })) : '<div class="empty">No insurance, PUC, permit, fitness, road tax or RC received yet.</div>') + "</div>";
    s += '<div class="sec"><h4>Open safety actions</h4>' + (c.open_actions.length ? '<ul class="gaps">' + c.open_actions.map(function (o) {
      return "<li><strong>" + esc(o.label.charAt(0).toUpperCase() + o.label.slice(1)) + "</strong>: flagged by the workshop on " + esc(when(o.opened)) + ". Stays open until a bill shows the fix.</li>";
    }).join("") + "</ul>" : '<div class="empty">None open.</div>') + "</div>";
    s += '<div class="sec"><h4>Training</h4>' + (c.training ? kv([["Module", c.training.title || c.training.module], ["Sent", when(c.training.sent_at)], ["Why this one", c.training.reason || ""]]) : '<div class="empty">The module link goes out with the first accepted bill, in ' + esc(c.language) + ".</div>") + "</div>";
    s += '<div class="sec svc"><h4>Documents</h4>' + (c.documents.length ? c.documents.map(docCard).join("") : '<div class="empty">Nothing received from this driver yet.</div>') + "</div>";
    return s;
  }
  function openCab(vn, keepScroll) {
    var c = state.data.cabs.find(function (x) { return x.vn === vn; });
    if (!c) return;
    var body = $("#d-body"), top = keepScroll ? body.scrollTop : 0;
    state.open = vn;
    $("#d-title").textContent = c.cab_id + " · " + c.vehicle;
    $("#d-sub").textContent = [c.driver, c.language, "last change " + when(state.data.as_of)].filter(Boolean).join(" · ");
    body.innerHTML = cabSections(c);
    body.scrollTop = top;
    $("#drawer").hidden = false;
  }
  function closeDrawer() { $("#drawer").hidden = true; state.open = null; }
  document.querySelectorAll("[data-close]").forEach(function (el) { el.addEventListener("click", closeDrawer); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
})();
