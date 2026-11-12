
(function plantioAutocompleteRichBoot() {
    const $ = window.django?.jQuery || window.jQuery;

    if (typeof $ !== "function") {
        setTimeout(plantioAutocompleteRichBoot, 100);
        return;
    }

    if (window.__plantioAutocompleteRichLoaded) {
        return;
    }

    window.__plantioAutocompleteRichLoaded = true;

    const CULTURE_ICON_BASE = "/static/images/icons/";

    const CULTURE_PRESETS = {
        Arroz: {
            className: "culture-rice",
            icon: "rice.png",
            color: "#FBBF70",
            border: "#D97706",
        },
        Soja: {
            className: "culture-soy",
            icon: "soy.png",
            color: "#35B637",
            border: "#15803D",
        },
        Milho: {
            className: "culture-corn",
            icon: "corn.png",
            color: "#EAB308",
            border: "#CA8A04",
        },
        Feijão: {
            className: "culture-beans",
            icon: "beans2.png",
            color: "#8B4513",
            border: "#5F2D12",
        },
        Algodão: {
            className: "culture-cotton",
            icon: "cotton.png",
            color: "#F8FAFC",
            border: "#CBD5E1",
        },
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function parsePlantioText(text) {
        const parts = String(text || "")
            .split("|")
            .map((part) => part.trim());

        return {
            talhao: parts[0] || "",
            projeto: parts[1] || "",
            cultura: parts[2] || "",
            variedade: parts[3] || "",
            safraCiclo: parts[4] || "",
            area: parts[5] || "",
            status: parts[6] || "",
            flags: parts.slice(7),
        };
    }

    function getCulturePreset(cultura, variedade) {
        if (variedade === "Mungo Preto") {
            return {
                className: "culture-beans-dark",
                icon: "beans2.png",
            };
        }

        if (variedade === "Mungo Verde") {
            return {
                className: "culture-beans-green",
                icon: "beans.png",
            };
        }

        if (variedade === "Caupi") {
            return {
                className: "culture-caupi",
                icon: "beans.png",
            };
        }

        return (
            CULTURE_PRESETS[cultura] || {
                className: "culture-default",
                icon: "x.png",
            }
        );
    }

    function badge(label, className) {
        return `
            <span class="plantio-ac-badge ${className}">
                ${escapeHtml(label)}
            </span>
        `;
    }

    function getStatusBadges(parsed) {
        const badges = [];
        const status = parsed.status;
        const flags = parsed.flags || [];

        if (status === "DESCONTINUADO") {
            badges.push(
                badge("Descontinuado", "is-danger")
            );
            return badges.join("");
        }

        if (status === "FINALIZADO_COLHEITA") {
            badges.push(
                badge("Colheita finalizada", "is-dark")
            );
        }

        if (status === "FINALIZADO_PLANTIO") {
            badges.push(
                badge("Plantio finalizado", "is-success")
            );
        } else if (status === "INICIALIZADO_PLANTIO") {
            badges.push(
                badge("Plantio iniciado", "is-info")
            );
        } else if (status === "NAO_INICIADO") {
            badges.push(
                badge("Não iniciado", "is-muted")
            );
        }

        if (flags.includes("AREA_AFERIDA")) {
            badges.push(
                badge("Área aferida", "is-purple")
            );
        }

        if (flags.includes("REPLANTIO")) {
            badges.push(
                badge("Replantio", "is-warning")
            );
        }

        return badges.join("");
    }

    function renderPlantioOptionHtml(text) {
        const parsed = parsePlantioText(text);

        const preset = getCulturePreset(
            parsed.cultura,
            parsed.variedade
        );

        const iconUrl = `${CULTURE_ICON_BASE}${preset.icon}`;
        const badges = getStatusBadges(parsed);

        return `
            <div class="plantio-ac-option">

                <div
                    class="plantio-ac-icon-container"
                    style="
                        width: 32px;
                        height: 32px;
                        min-width: 32px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        flex-shrink: 0;
                        background: transparent;
                        border: none;
                    "
                    title="${escapeHtml(parsed.cultura || "Cultura")}"
                >
                    <img
                        src="${escapeHtml(iconUrl)}"
                        alt="${escapeHtml(parsed.cultura || "Cultura")}"
                        style="
                            width: 28px;
                            height: 28px;
                            object-fit: contain;
                            display: block;
                            background: transparent;
                            border: none;
                            filter: none;
                        "
                    />
                </div>

                <div class="plantio-ac-main">

                    <div class="plantio-ac-line1">

                        <div class="plantio-ac-primary-info">

                            <strong>
                                ${escapeHtml(parsed.talhao || "-")}
                            </strong>

                            <span class="plantio-ac-project">
                                ${escapeHtml(parsed.projeto || "-")}
                            </span>

                            ${
                                parsed.variedade
                                    ? `<span class="plantio-ac-variedade">
                                        ${escapeHtml(parsed.variedade)}
                                       </span>`
                                    : ""
                            }

                        </div>

                        <span class="plantio-ac-badges-inline">
                            ${badges}
                        </span>

                    </div>

                    <div class="plantio-ac-line2">

                        ${
                            parsed.safraCiclo
                                ? `<span>${escapeHtml(parsed.safraCiclo)}</span>`
                                : ""
                        }

                        ${
                            parsed.area
                                ? `<span>${escapeHtml(parsed.area)}</span>`
                                : ""
                        }

                    </div>

                </div>

            </div>
        `;
    }

    function forceMarkField() {
        const $field = $("#id_plantio");

        if (!$field.length) {
            return;
        }

        $field.data("plantio-rich-applied", true);
        $field.attr(
            "data-plantio-rich-applied",
            "true"
        );
    }

    function enhanceDropdownOptions() {
        $(".select2-results__option").each(function () {
            const $option = $(this);

            if (
                $option.data(
                    "plantio-rich-option-applied"
                )
            ) {
                return;
            }

            const text = $option.text().trim();

            if (!text || !text.includes("|")) {
                return;
            }

            $option.data(
                "plantio-rich-option-applied",
                true
            );

            $option.attr(
                "data-original-text",
                text
            );

            $option.html(
                renderPlantioOptionHtml(text)
            );
        });
    }

    function observeSelect2Results() {
        const target = document.body;

        if (
            target.dataset.plantioRichObserver === "true"
        ) {
            return;
        }

        target.dataset.plantioRichObserver = "true";

        const observer = new MutationObserver(function () {
            enhanceDropdownOptions();
        });

        observer.observe(target, {
            childList: true,
            subtree: true,
        });
    }

    function bootPlantioRich() {
        forceMarkField();
        observeSelect2Results();

        setTimeout(forceMarkField, 300);
        setTimeout(forceMarkField, 800);
        setTimeout(forceMarkField, 1500);

        setTimeout(enhanceDropdownOptions, 300);
        setTimeout(enhanceDropdownOptions, 800);
        setTimeout(enhanceDropdownOptions, 1500);
    }

    window.forcePlantioRich = function () {
        forceMarkField();
        observeSelect2Results();
        enhanceDropdownOptions();
    };

    $(document).ready(function () {
        bootPlantioRich();
    });

    $(window).on("load", function () {
        bootPlantioRich();
    });

    $(document).on(
        "select2:open",
        "#id_plantio",
        function () {
            forceMarkField();

            setTimeout(enhanceDropdownOptions, 50);
            setTimeout(enhanceDropdownOptions, 200);
            setTimeout(enhanceDropdownOptions, 600);
        }
    );

    $(document).on(
        "keyup input",
        ".select2-search__field",
        function () {
            setTimeout(enhanceDropdownOptions, 100);
            setTimeout(enhanceDropdownOptions, 300);
        }
    );
})();
