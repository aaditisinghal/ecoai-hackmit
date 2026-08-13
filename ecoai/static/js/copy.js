// Copy-to-clipboard for any button carrying data-copy-target="<element id>".
(function () {
  "use strict";

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // Fallback for plain-HTTP local development, where the async clipboard
    // API is unavailable because the context is not secure.
    return new Promise(function (resolve, reject) {
      var scratch = document.createElement("textarea");
      scratch.value = text;
      scratch.setAttribute("readonly", "");
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.appendChild(scratch);
      scratch.select();
      try {
        document.execCommand("copy") ? resolve() : reject(new Error("copy rejected"));
      } catch (error) {
        reject(error);
      } finally {
        document.body.removeChild(scratch);
      }
    });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-target]");
    if (!button) return;

    var source = document.getElementById(button.dataset.copyTarget);
    if (!source) return;

    var text = "value" in source ? source.value : source.textContent;
    var original = button.textContent;

    copy(text.trim()).then(
      function () {
        button.textContent = "Copied";
        setTimeout(function () {
          button.textContent = original;
        }, 1800);
      },
      function () {
        button.textContent = "Press Ctrl+C";
        setTimeout(function () {
          button.textContent = original;
        }, 2500);
      }
    );
  });
})();
