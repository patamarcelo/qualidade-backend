document.addEventListener("DOMContentLoaded", function () {
    const cardHeaders = document.querySelectorAll('.card-info .card-header.bg-primary');

    cardHeaders.forEach(cardHeader => {
        if (cardHeader.textContent.includes('Observações')) {
            const btn = cardHeader.querySelector('[data-card-widget="collapse"]');
            if (btn) btn.click(); // dispara o colapso
        }
    });
});