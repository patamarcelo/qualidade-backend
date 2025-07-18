document.addEventListener('DOMContentLoaded', function () {
    function updateRowHighlight(checkbox) {
        const row = checkbox.closest('tr');
        if (checkbox.checked) {
            row.classList.add('inline-row-deleted');
        } else {
            row.classList.remove('inline-row-deleted');
        }
    }

    document.querySelectorAll('input[name$="-DELETE"]').forEach(function (checkbox) {
        updateRowHighlight(checkbox);  // já marca se necessário
        checkbox.addEventListener('change', function () {
            updateRowHighlight(checkbox);
        });
    });

    const observer = new MutationObserver(function () {
        document.querySelectorAll('input[name$="-DELETE"]').forEach(function (checkbox) {
            if (!checkbox.dataset.listenerAttached) {
                checkbox.dataset.listenerAttached = 'true';
                checkbox.addEventListener('change', function () {
                    updateRowHighlight(checkbox);
                });
            }
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
});