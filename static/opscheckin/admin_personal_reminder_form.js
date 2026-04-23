(function () {
    function toggleFields() {
        const scheduleType = document.getElementById("id_schedule_type");
        const weekdayRow = document.getElementById("id_weekday")?.closest(".form-row") || document.getElementById("id_weekday")?.closest(".fieldBox");
        const dayOfMonthRow = document.getElementById("id_day_of_month")?.closest(".form-row") || document.getElementById("id_day_of_month")?.closest(".fieldBox");

        if (!scheduleType) return;

        const value = scheduleType.value;

        if (weekdayRow) {
            weekdayRow.style.display = value === "weekly" ? "" : "none";
        }

        if (dayOfMonthRow) {
            dayOfMonthRow.style.display = value === "monthly" ? "" : "none";
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        const scheduleType = document.getElementById("id_schedule_type");
        toggleFields();

        if (scheduleType) {
            scheduleType.addEventListener("change", toggleFields);
        }
    });
})();