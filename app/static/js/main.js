// SecurePass front-end enhancements.
//
// Everything here is optional polish: every page works without JavaScript, and the server
// re-checks every value (SR3). The script is loaded from a file, never inline, so the
// Content-Security-Policy (SR9) can stay strict.
(function () {
  "use strict";

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }

  var SVG_NS = "http://www.w3.org/2000/svg";
  function icon(paths) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    paths.forEach(function (d) {
      var path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  // ------------------------------------------------------------------ search form
  function initSearchForm() {
    var origin = $("#origin");
    var destination = $("#destination");
    var departure = $("#departure");
    var returnDate = $("#return");
    if (!origin || !destination || !departure || !returnDate) { return; }

    // Airport codes: letters only, always upper case.
    [origin, destination].forEach(function (el) {
      el.addEventListener("input", function () {
        el.value = el.value.replace(/[^a-zA-Z]/g, "").toUpperCase();
      });
    });

    // No dates in the past; the return date can't be before the departure date.
    var today = new Date();
    today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
    var todayStr = today.toISOString().slice(0, 10);
    departure.min = todayStr;
    returnDate.min = todayStr;
    departure.addEventListener("change", function () {
      returnDate.min = departure.value || todayStr;
      if (returnDate.value && returnDate.value < returnDate.min) { returnDate.value = ""; }
    });

    // Pre-fill from the query string (used by the destination cards).
    var params = new URLSearchParams(window.location.search);
    var code = params.get("destination");
    if (code && /^[A-Za-z]{3}$/.test(code)) { destination.value = code.toUpperCase(); }

    // One way / Round trip tabs. One way hides and disables the return date, and a
    // disabled field is not sent, so the server sees an ordinary search without a return.
    var tabs = $("[data-trip-tabs]");
    var fields = $("[data-search-fields]");
    var returnField = $("[data-return-field]");
    if (tabs && fields && returnField) {
      var buttons = $$("[data-trip]", tabs);
      var setTrip = function (kind) {
        var oneWay = kind === "oneway";
        returnField.hidden = oneWay;
        returnDate.disabled = oneWay;
        if (oneWay) { returnDate.value = ""; }
        fields.classList.toggle("is-oneway", oneWay);
        buttons.forEach(function (button) {
          button.setAttribute("aria-pressed", String(button.getAttribute("data-trip") === kind));
        });
      };
      buttons.forEach(function (button) {
        button.addEventListener("click", function () { setTrip(button.getAttribute("data-trip")); });
      });
      tabs.hidden = false;
      // A search that was sent without a return date comes back showing "One way".
      setTrip(params.has("search") && !params.get("return") ? "oneway" : "round");
    }

    var swap = $("[data-swap]");
    if (swap) {
      swap.hidden = false;
      swap.addEventListener("click", function () {
        var held = origin.value;
        origin.value = destination.value;
        destination.value = held;
      });
    }
  }

  // ------------------------------------------------------------------ passwords
  function initPasswords() {
    $$('input[type="password"]').forEach(function (input) {
      var wrap = document.createElement("div");
      wrap.className = "pw-wrap";
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);

      var eye = icon(["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"]);
      var eyeOff = icon(["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M4 4l16 16"]);
      var toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "pw-toggle";
      toggle.setAttribute("aria-label", "Show password");
      toggle.setAttribute("aria-pressed", "false");
      toggle.appendChild(eye);
      toggle.addEventListener("click", function () {
        var reveal = input.type === "password";
        input.type = reveal ? "text" : "password";
        toggle.setAttribute("aria-pressed", String(reveal));
        toggle.setAttribute("aria-label", reveal ? "Hide password" : "Show password");
        toggle.replaceChild(reveal ? eyeOff : eye, toggle.firstChild);
      });
      wrap.appendChild(toggle);

      // Strength hints only where a new password is being chosen. The server rules decide.
      if ((input.id === "password" || input.id === "new_password") && input.getAttribute("autocomplete") === "new-password") {
        addStrengthMeter(input, wrap);
      }
    });
  }

  function addStrengthMeter(input, wrap) {
    var meter = document.createElement("div");
    meter.className = "pw-meter";
    meter.setAttribute("aria-hidden", "true");
    meter.setAttribute("data-level", "0");
    for (var i = 0; i < 4; i++) { meter.appendChild(document.createElement("span")); }
    var label = document.createElement("p");
    label.className = "pw-meter-label";
    label.setAttribute("aria-live", "polite");
    wrap.parentNode.insertBefore(meter, wrap.nextSibling);
    wrap.parentNode.insertBefore(label, meter.nextSibling);

    input.addEventListener("input", function () {
      var value = input.value;
      var level = 0;
      var text = "";
      if (value) {
        if (value.length < 10) {
          level = 1; text = "Too short: use at least 10 characters";
        } else if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
          level = 1; text = "Add a letter and a number";
        } else {
          level = 2;
          if (value.length >= 14) { level++; }
          if (/[A-Z]/.test(value) && /[a-z]/.test(value) && /[^A-Za-z0-9]/.test(value)) { level++; }
          text = ["", "", "Fair", "Good", "Strong"][level];
        }
      }
      meter.setAttribute("data-level", String(level));
      label.textContent = text;
    });
  }

  // ------------------------------------------------------------------ flash messages
  function initFlash() {
    $$(".flash").forEach(function (message) {
      var close = document.createElement("button");
      close.type = "button";
      close.className = "flash-close";
      close.setAttribute("aria-label", "Dismiss message");
      close.textContent = "×";
      close.addEventListener("click", function () { message.remove(); });
      message.appendChild(close);
    });
  }

  // ------------------------------------------------------------------ results filters
  function initFilters() {
    var panel = $("[data-filters]");
    var layout = $(".results-layout");
    var lists = $$("[data-leg]");
    if (!panel || !layout || !lists.length) { return; }

    var sortBy = $("[data-sort]", panel);
    var priceMax = $("[data-price-max]", panel);
    var priceOut = $("[data-price-out]", panel);
    var bands = $$("[data-band]", panel);
    var reset = $("[data-reset]", panel);
    var count = $("[data-count]", panel);

    var groups = lists.map(function (list) {
      var empty = document.createElement("p");
      empty.className = "filter-empty";
      empty.textContent = "No flights match these filters. Try widening them.";
      empty.hidden = true;
      list.parentNode.insertBefore(empty, list.nextSibling);
      return { list: list, cards: $$(".flight-card", list), empty: empty };
    });

    function bandOf(hour) {
      if (hour >= 5 && hour < 12) { return "morning"; }
      if (hour >= 12 && hour < 18) { return "afternoon"; }
      if (hour >= 18 && hour < 22) { return "evening"; }
      return "night";
    }
    function num(card, name) { return Number(card.getAttribute("data-" + name)); }

    function apply() {
      var maxCents = priceMax ? Number(priceMax.value) * 100 : Infinity;
      var allowed = {};
      bands.forEach(function (box) { allowed[box.value] = box.checked; });
      var order = sortBy ? sortBy.value : "time";
      var key = order === "price" ? "price" : (order === "duration" ? "duration" : "depart");
      var shown = 0;
      var total = 0;

      groups.forEach(function (group) {
        var visible = 0;
        group.cards.forEach(function (card) {
          var hour = Math.floor(num(card, "depart") / 100);
          var show = num(card, "price") <= maxCents && allowed[bandOf(hour)];
          card.hidden = !show;
          if (show) { visible++; }
        });
        group.cards.slice().sort(function (a, b) {
          return (num(a, key) - num(b, key)) || (num(a, "depart") - num(b, "depart"));
        }).forEach(function (card) { group.list.appendChild(card); });
        group.empty.hidden = visible !== 0;
        shown += visible;
        total += group.cards.length;
      });

      if (priceMax && priceOut) { priceOut.textContent = "$" + priceMax.value; }
      if (count) { count.textContent = "Showing " + shown + " of " + total + " flight" + (total === 1 ? "" : "s"); }
    }

    if (sortBy) { sortBy.addEventListener("change", apply); }
    if (priceMax) { priceMax.addEventListener("input", apply); }
    bands.forEach(function (box) { box.addEventListener("change", apply); });
    if (reset) {
      reset.addEventListener("click", function () {
        if (sortBy) { sortBy.value = "time"; }
        if (priceMax) { priceMax.value = priceMax.max; }
        bands.forEach(function (box) { box.checked = true; });
        apply();
      });
    }

    panel.hidden = false;
    layout.classList.add("filters-on");
    apply();
  }

  // ------------------------------------------------------------------ seat map
  // The lists next to the map are the real form fields; the map is a faster way to fill them.
  function initSeatMap() {
    var map = $("[data-seatmap]");
    if (!map) { return; }
    var selects = $$("[data-seat-select]");
    var seatButtons = $$("[data-seat]", map);
    var rows = $$(".seat-passenger");
    var fallback = $("[data-seatmap-fallback]");
    if (!selects.length || !seatButtons.length) { return; }

    var active = selects[0].getAttribute("data-seat-select");

    function seatOf(position) {
      var select = $('[data-seat-select="' + position + '"]');
      return select ? select.value : "";
    }
    function paint() {
      var holders = {};
      selects.forEach(function (select) {
        if (select.value) { holders[select.value] = select.getAttribute("data-seat-select"); }
      });
      seatButtons.forEach(function (button) {
        var label = button.getAttribute("data-seat");
        var holder = holders[label];
        button.classList.toggle("is-selected", Boolean(holder));
        button.setAttribute("aria-pressed", String(Boolean(holder)));
        button.textContent = holder || "";
      });
      rows.forEach(function (row) {
        row.classList.toggle("is-active", row.getAttribute("data-passenger") === active);
      });
    }
    function setSeat(position, label) {
      selects.forEach(function (select) {   // one seat, one passenger
        if (label && select.value === label) { select.value = ""; }
      });
      var select = $('[data-seat-select="' + position + '"]');
      if (select) { select.value = label; }
    }

    seatButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        var label = button.getAttribute("data-seat");
        setSeat(active, seatOf(active) === label ? "" : label);
        // Move on to the next passenger who has no seat yet.
        var next = selects.filter(function (select) { return !select.value; })[0];
        if (next) { active = next.getAttribute("data-seat-select"); }
        paint();
      });
    });
    selects.forEach(function (select) {
      select.addEventListener("change", function () {
        var position = select.getAttribute("data-seat-select");
        var label = select.value;
        active = position;
        setSeat(position, label);
        paint();
      });
      select.addEventListener("focus", function () { active = select.getAttribute("data-seat-select"); paint(); });
    });
    rows.forEach(function (row) {
      row.addEventListener("click", function (event) {
        if (event.target.tagName === "SELECT") { return; }
        active = row.getAttribute("data-passenger");
        paint();
      });
    });

    map.hidden = false;
    if (fallback) { fallback.hidden = true; }
    paint();
  }

  // ------------------------------------------------------------------ header shadow
  function initHeader() {
    var header = $(".site-header");
    if (!header) { return; }
    function onScroll() { header.classList.toggle("is-scrolled", window.scrollY > 4); }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  [initSearchForm, initPasswords, initFlash, initFilters, initSeatMap, initHeader].forEach(function (setup) {
    try { setup(); } catch (error) {
      // One failing enhancement must never take the others (or the page) down with it.
      if (window.console) { console.error(error); }
    }
  });
})();
