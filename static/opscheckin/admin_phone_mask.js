// static/opscheckin/admin_phone_mask.js
(function () {
  function onlyDigits(v) {
    return String(v || "").replace(/\D+/g, "");
  }

  function formatPhoneLocalBR(digits) {
    digits = onlyDigits(digits).slice(0, 9); // máximo 9 dígitos

    if (digits.length <= 4) return digits;

    if (digits.length <= 8) {
      return digits.replace(/^(\d{4})(\d+)$/, "$1-$2");
    }

    return digits.replace(/^(\d{5})(\d+)$/, "$1-$2");
  }

  function countDigitsBeforeCursor(value, cursorPos) {
    return onlyDigits(value.slice(0, cursorPos)).length;
  }

  function findCursorFromDigitIndex(formattedValue, digitIndex) {
    let count = 0;
    for (let i = 0; i < formattedValue.length; i++) {
      if (/\d/.test(formattedValue[i])) {
        count++;
        if (count === digitIndex) {
          return i + 1;
        }
      }
    }
    return formattedValue.length;
  }

  document.addEventListener("DOMContentLoaded", function () {
    const inp = document.getElementById("id_number");
    if (!inp) return;

    inp.addEventListener("input", function (e) {
      const raw = inp.value;
      const cursor = inp.selectionStart;

      const digitIndex = countDigitsBeforeCursor(raw, cursor);

      const digits = onlyDigits(raw);
      const formatted = formatPhoneLocalBR(digits);

      inp.value = formatted;

      const newCursor = findCursorFromDigitIndex(formatted, digitIndex);
      inp.setSelectionRange(newCursor, newCursor);
    });
  });
})();