(function () {
    const weekdayOptions = [
        { value: "0", label: "Segunda-feira" },
        { value: "1", label: "Terça-feira" },
        { value: "2", label: "Quarta-feira" },
        { value: "3", label: "Quinta-feira" },
        { value: "4", label: "Sexta-feira" },
        { value: "5", label: "Sábado" },
        { value: "6", label: "Domingo" },
    ];

    function getFieldContainer(id) {
        const input = document.getElementById(id);
        if (!input) return null;
        return input.closest(".form-row") || input.closest(".fieldBox") || input.parentElement;
    }

    function ensureWeekdaySelect() {
        const weekdayInput = document.getElementById("id_weekday");
        if (!weekdayInput) return;

        const container = getFieldContainer("id_weekday");
        if (!container) return;

        let select = document.getElementById("id_weekday_display");
        if (select) return;

        weekdayInput.style.display = "none";

        select = document.createElement("select");
        select.id = "id_weekday_display";
        select.className = weekdayInput.className || "";
        select.setAttribute("data-sync-target", "id_weekday");

        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Selecione o dia da semana";
        select.appendChild(empty);

        weekdayOptions.forEach((opt) => {
            const option = document.createElement("option");
            option.value = opt.value;
            option.textContent = opt.label;
            select.appendChild(option);
        });

        select.value = weekdayInput.value || "";

        select.addEventListener("change", function () {
            weekdayInput.value = select.value;
            updateSummary();
        });

        weekdayInput.addEventListener("change", function () {
            select.value = weekdayInput.value || "";
        });

        weekdayInput.insertAdjacentElement("afterend", select);
    }

    function toggleConditionalFields() {
        const scheduleType = document.getElementById("id_schedule_type");
        const weekdayRow = getFieldContainer("id_weekday");
        const dayOfMonthRow = getFieldContainer("id_day_of_month");

        if (!scheduleType) return;

        const value = scheduleType.value;

        if (weekdayRow) {
            weekdayRow.style.display = value === "weekly" ? "" : "none";
        }

        const weekdayDisplay = document.getElementById("id_weekday_display");
        if (weekdayDisplay) {
            weekdayDisplay.style.display = value === "weekly" ? "" : "none";
        }

        if (dayOfMonthRow) {
            dayOfMonthRow.style.display = value === "monthly" ? "" : "none";
        }
    }

    function formatWeekdayLabel(value) {
        const found = weekdayOptions.find((item) => item.value === String(value));
        return found ? found.label.toLowerCase() : "semana";
    }

    function getEffectiveTemplateLabel(responseMode) {
        if (responseMode === "button") {
            return "manager_personal_reminder_confirm";
        }
        return "manager_personal_reminder_text";
    }

    function updateSummary() {
        const scheduleType = document.getElementById("id_schedule_type")?.value || "";
        const timeOfDay = document.getElementById("id_time_of_day")?.value || "--:--";
        const weekday = document.getElementById("id_weekday")?.value || "";
        const dayOfMonth = document.getElementById("id_day_of_month")?.value || "--";
        const responseMode = document.getElementById("id_response_mode")?.value || "none";
        const summary = document.getElementById("id_resumo_operacional");

        if (!summary) return;

        let freq = "Periodicidade não definida";

        if (scheduleType === "daily") {
            freq = `Todo dia às ${timeOfDay}`;
        } else if (scheduleType === "weekly") {
            freq = `Toda ${formatWeekdayLabel(weekday)} às ${timeOfDay}`;
        } else if (scheduleType === "monthly") {
            freq = `Todo dia ${dayOfMonth} do mês às ${timeOfDay}`;
        }

        let responseLabel = "Não exige resposta";
        if (responseMode === "text") {
            responseLabel = "Espera resposta por texto";
        } else if (responseMode === "button") {
            responseLabel = "Exige confirmação por botão";
        }

        const templateLabel = getEffectiveTemplateLabel(responseMode);

        summary.value =
            `Frequência: ${freq}\n` +
            `Retorno esperado: ${responseLabel}\n` +
            `Template aplicado automaticamente: ${templateLabel}`;
    }

    function bindSummaryEvents() {
        [
            "id_schedule_type",
            "id_time_of_day",
            "id_weekday",
            "id_day_of_month",
            "id_response_mode",
        ].forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener("change", updateSummary);
            el.addEventListener("input", updateSummary);
        });

        const scheduleType = document.getElementById("id_schedule_type");
        if (scheduleType) {
            scheduleType.addEventListener("change", toggleConditionalFields);
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        ensureWeekdaySelect();
        toggleConditionalFields();
        bindSummaryEvents();
        updateSummary();
    });
})();