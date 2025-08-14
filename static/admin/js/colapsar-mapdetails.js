document.addEventListener("DOMContentLoaded", function () {
    const cardHeaders = document.querySelectorAll('.card-info .card-header.bg-primary');

    const listToCheck = ["Programa", "Display Map", "Cronograma Previsto"];
    cardHeaders.forEach(cardHeader => {
        const titleEl = cardHeader.querySelector('.card-title');
        if (!titleEl) return;

        const titleText = titleEl.textContent.trim(); // remove espaços extras

        if (listToCheck.includes(titleText)) {
            const btn = cardHeader.querySelector('[data-card-widget="collapse"]');
            if (btn) btn.click(); // dispara o colapso
        }
    });
});