/* AIR site — progressive enhancement only.
   Core content works with this file absent. No external requests besides
   same-origin /assets/data/crash.json (fetched once, only if the scrubber
   exists). No storage, no analytics, no tracking. */
(function () {
  "use strict";
  document.documentElement.className =
    document.documentElement.className.replace("no-js", "js");

  /* ---------- timeline scrubber ---------- */
  var scrub = document.getElementById("scrubber");
  var readout = document.getElementById("scrub-readout");
  if (scrub && readout && window.fetch) {
    fetch("/assets/data/crash.json")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        var DUR = d.flight.duration_s;
        var alt = d.series.alt_local_m.points;
        var batr = d.series.batt_remaining.points;
        var batv = d.series.batt_v.points;
        var events = d.events;
        // chart geometry constants — must match render_charts.py
        var ML = 58, W = 960, MR = 16;
        function at(pts, t) {
          var v = pts[0][1];
          for (var i = 0; i < pts.length; i++) {
            if (pts[i][0] <= t) v = pts[i][1]; else break;
          }
          return v;
        }
        function lastEvent(t) {
          var m = null;
          for (var i = 0; i < events.length; i++) {
            if (events[i].t <= t) m = events[i]; else break;
          }
          return m;
        }
        var cursors = document.querySelectorAll(".chart .cursor line");
        function update() {
          var t = parseFloat(scrub.value);
          var x = ML + (t / DUR) * (W - ML - MR);
          cursors.forEach(function (c) {
            c.setAttribute("x1", x); c.setAttribute("x2", x);
            c.setAttribute("opacity", "0.55");
          });
          var ev = lastEvent(t);
          readout.textContent =
            "T+" + t.toFixed(1) + "s · EKF altitude " + at(alt, t).toFixed(1) +
            " m · battery " + at(batr, t).toFixed(0) + "% (" +
            at(batv, t).toFixed(1) + " V)" +
            (ev ? " · last event: " + ev.message + " (T+" + ev.t.toFixed(1) + "s)" : "");
        }
        scrub.addEventListener("input", update);
        update();
      })
      .catch(function () { /* chart stays static — acceptable */ });
  }

  /* ---------- design-partner mailto composer ---------- */
  var form = document.getElementById("demo-form");
  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      function v(id) { var el = document.getElementById(id); return el ? el.value.trim() : ""; }
      var org = v("f-org");
      var subject = "AIR design-partner conversation" + (org ? " — " + org : "");
      var body =
        "Name: " + v("f-name") + "\n" +
        "Work email: " + v("f-email") + "\n" +
        "Organization: " + org + "\n" +
        "Role: " + v("f-role") + "\n" +
        "Fleet/autopilot type: " + v("f-fleet") + "\n" +
        "Approx. aircraft count: " + v("f-count") + "\n" +
        "Incident investigated in last 12 months: " + v("f-incident") + "\n" +
        "Message: " + v("f-msg") + "\n";
      window.location.href = "mailto:hello@findanything.dev?subject=" +
        encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
    });
  }
})();
