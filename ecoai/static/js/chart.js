// Minimal SVG line chart.
//
// Hand-rolled rather than pulled from a charting library so the
// Content-Security-Policy can stay locked to 'self' with no CDN allowance,
// and so the page ships no third-party JavaScript at all.
(function () {
  "use strict";

  var dataNode = document.getElementById("chart-data");
  var svg = document.getElementById("tokens-chart");
  if (!dataNode || !svg) return;

  var data;
  try {
    data = JSON.parse(dataNode.textContent);
  } catch (error) {
    return;
  }

  var values = data.tokens || [];
  var labels = data.labels || [];
  if (!values.length) return;

  var W = 800;
  var H = 260;
  var PAD = { top: 16, right: 12, bottom: 30, left: 52 };
  var plotW = W - PAD.left - PAD.right;
  var plotH = H - PAD.top - PAD.bottom;

  var max = Math.max.apply(null, values);
  // A flat all-zero series would divide by zero; give it a nominal ceiling.
  var ceiling = max > 0 ? max : 1;

  function x(index) {
    return values.length === 1
      ? PAD.left + plotW / 2
      : PAD.left + (index / (values.length - 1)) * plotW;
  }

  function y(value) {
    return PAD.top + plotH - (value / ceiling) * plotH;
  }

  var NS = "http://www.w3.org/2000/svg";

  function el(name, attrs, text) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function niceTick(value) {
    if (value >= 1000000) return (value / 1000000).toFixed(1) + "M";
    if (value >= 1000) return (value / 1000).toFixed(1) + "k";
    return String(Math.round(value));
  }

  // Horizontal gridlines and y-axis labels.
  for (var step = 0; step <= 4; step++) {
    var value = (ceiling / 4) * step;
    var gy = y(value);
    svg.appendChild(
      el("line", { x1: PAD.left, y1: gy, x2: W - PAD.right, y2: gy, class: "chart__grid" })
    );
    svg.appendChild(
      el(
        "text",
        { x: PAD.left - 8, y: gy + 4, "text-anchor": "end", class: "chart__axis-label" },
        niceTick(value)
      )
    );
  }

  // Filled area beneath the line.
  var area = values
    .map(function (value, index) {
      return (index === 0 ? "M" : "L") + x(index) + "," + y(value);
    })
    .join(" ");
  area += " L" + x(values.length - 1) + "," + y(0) + " L" + x(0) + "," + y(0) + " Z";
  svg.appendChild(el("path", { d: area, class: "chart__area" }));

  // The line itself.
  var line = values
    .map(function (value, index) {
      return (index === 0 ? "M" : "L") + x(index) + "," + y(value);
    })
    .join(" ");
  svg.appendChild(el("path", { d: line, class: "chart__line" }));

  // Dots, with a native tooltip per point.
  values.forEach(function (value, index) {
    var dot = el("circle", { cx: x(index), cy: y(value), r: 3, class: "chart__dot" });
    dot.appendChild(
      el("title", {}, (labels[index] || "") + ": " + value.toLocaleString() + " tokens saved")
    );
    svg.appendChild(dot);
  });

  // X labels, thinned so they never overlap on narrow screens.
  var every = Math.max(1, Math.ceil(values.length / 8));
  var last = labels.length - 1;
  // Always show the final label, but drop the preceding tick when it would
  // land on top of it - otherwise the last two collide whenever the series
  // length is not an exact multiple of the step.
  var minGap = Math.ceil(every / 2);

  labels.forEach(function (label, index) {
    var isRegularTick = index % every === 0;
    if (!isRegularTick && index !== last) return;
    if (isRegularTick && index !== last && last - index < minGap) return;

    svg.appendChild(
      el(
        "text",
        { x: x(index), y: H - 8, "text-anchor": "middle", class: "chart__axis-label" },
        label
      )
    );
  });
})();
