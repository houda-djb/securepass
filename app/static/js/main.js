// Small progressive enhancements for the search form.
// Server-side validation (Phase 2) is the real control; this only helps the user (SR3).
(function () {
  "use strict";

  var origin = document.getElementById("origin");
  var destination = document.getElementById("destination");
  var departure = document.getElementById("departure");
  var returnDate = document.getElementById("return");
  if (!origin || !departure) { return; }

  function upper(el) {
    el.addEventListener("input", function () {
      el.value = el.value.replace(/[^a-zA-Z]/g, "").toUpperCase();
    });
  }
  upper(origin);
  upper(destination);

  var today = new Date();
  today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
  var todayStr = today.toISOString().slice(0, 10);
  departure.min = todayStr;
  returnDate.min = todayStr;

  departure.addEventListener("change", function () {
    returnDate.min = departure.value || todayStr;
    if (returnDate.value && returnDate.value < returnDate.min) { returnDate.value = ""; }
  });

  // Pre-fill from the query string (used by the featured-destination links).
  var params = new URLSearchParams(window.location.search);
  var code = params.get("destination");
  if (code && /^[A-Za-z]{3}$/.test(code)) { destination.value = code.toUpperCase(); }
})();