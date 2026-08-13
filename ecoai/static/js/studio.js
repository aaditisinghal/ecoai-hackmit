// Prompt Studio.
//
// Submits to POST /api/v1/optimize and renders what the server returns.
// The previous version optimized in the browser behind a fake setTimeout and
// never contacted the server, so nothing it displayed was real or recorded.
(function () {
  "use strict";

  var form = document.getElementById("optimize-form");
  if (!form) return;

  var button = document.getElementById("optimize-btn");
  var errorBox = document.getElementById("studio-error");
  var output = document.getElementById("optimized-output");
  var promptField = form.querySelector("[name='prompt']");
  var charCount = document.getElementById("char-count");

  var metrics = {
    before: document.getElementById("m-before"),
    after: document.getElementById("m-after"),
    reduction: document.getElementById("m-reduction"),
    co2: document.getElementById("m-co2"),
    kwh: document.getElementById("m-kwh"),
    retention: document.getElementById("m-retention"),
  };

  var transformationsCard = document.getElementById("transformations-card");
  var transformationsList = document.getElementById("transformations");
  var warningsCard = document.getElementById("warnings-card");
  var warningsList = document.getElementById("warnings");

  function csrfToken() {
    var meta = document.querySelector("meta[name='csrf-token']");
    return meta ? meta.getAttribute("content") : "";
  }

  function formatGrams(grams) {
    if (grams >= 1000) return (grams / 1000).toFixed(3) + " kg";
    if (grams >= 1) return grams.toFixed(3) + " g";
    return (grams * 1000).toFixed(3) + " mg";
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  function clearError() {
    errorBox.textContent = "";
    errorBox.classList.add("hidden");
  }

  function updateCharCount() {
    if (charCount && promptField) {
      charCount.textContent = promptField.value.length.toLocaleString();
    }
  }

  if (promptField) {
    promptField.addEventListener("input", updateCharCount);
    updateCharCount();
  }

  function render(result) {
    output.textContent = result.optimized;

    metrics.before.textContent = result.tokens_before.toLocaleString();
    metrics.after.textContent = result.tokens_after.toLocaleString();
    metrics.reduction.textContent =
      result.tokens_saved.toLocaleString() +
      " (" +
      (result.reduction_ratio * 100).toFixed(1) +
      "%)";
    metrics.co2.textContent = formatGrams(result.carbon.co2_g_saved);
    metrics.kwh.textContent = result.carbon.kwh_saved.toExponential(3) + " kWh";
    metrics.retention.textContent = (result.retention_score * 100).toFixed(1) + "%";

    transformationsList.innerHTML = "";
    if (result.transformations && result.transformations.length) {
      result.transformations.forEach(function (transformation) {
        var item = document.createElement("li");
        item.className = "badge";
        item.textContent =
          transformation.name + (transformation.count > 1 ? " ×" + transformation.count : "");
        if (transformation.detail) item.title = transformation.detail;
        transformationsList.appendChild(item);
      });
      transformationsCard.classList.remove("hidden");
    } else {
      transformationsCard.classList.add("hidden");
    }

    warningsList.innerHTML = "";
    if (result.warnings && result.warnings.length) {
      result.warnings.forEach(function (warning) {
        var item = document.createElement("li");
        item.textContent = warning;
        warningsList.appendChild(item);
      });
      warningsCard.classList.remove("hidden");
    } else {
      warningsCard.classList.add("hidden");
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearError();

    var prompt = promptField.value;
    if (!prompt.trim()) {
      showError("Enter a prompt to optimize.");
      return;
    }

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    var originalLabel = button.textContent;
    button.textContent = "Optimizing…";

    fetch("/api/v1/optimize", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        prompt: prompt,
        strategy: form.querySelector("[name='strategy']").value,
        model: form.querySelector("[name='model']").value || null,
        region: form.querySelector("[name='region']").value || null,
      }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            throw new Error(body.message || "Request failed (" + response.status + ").");
          }
          return body;
        });
      })
      .then(render)
      .catch(function (error) {
        showError(error.message || "Could not reach the server.");
      })
      .finally(function () {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.textContent = originalLabel;
      });
  });
})();
