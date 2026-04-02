(function () {
    let drawerMap = null;
    let drawerLayerGroup = null;
    let formMap = null;
    let formLayerGroup = null;

    function formatArea(areaM2) {
        if (!areaM2) return "-";
        const ha = areaM2 / 10000;
        return `${ha.toFixed(2)} ha`;
    }

    function formatPerimeter(perimeterM) {
        if (!perimeterM) return "-";
        return `${Number(perimeterM).toFixed(2)} m`;
    }

    function normalizePoints(points) {
        if (!Array.isArray(points)) return [];

        return points
            .map((p) => {
                const lat = p.lat ?? p.latitude;
                const lng = p.lng ?? p.longitude ?? p.lon;
                if (lat == null || lng == null) return null;
                return [Number(lat), Number(lng)];
            })
            .filter(Boolean);
    }

    function initSatelliteMap(el) {
        const map = L.map(el, {
            zoomControl: true,
            attributionControl: true,
        });

        L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            {
                maxZoom: 19,
                attribution: "Tiles © Esri",
            }
        ).addTo(map);

        return map;
    }

    function drawPolygonOnMap(map, layerGroup, data) {
        const latlngs = normalizePoints(data.points);

        layerGroup.clearLayers();

        if (!latlngs.length) {
            map.setView([-14.235, -51.9253], 4);
            return;
        }

        if (data.is_closed && latlngs.length >= 3) {
            const polygon = L.polygon(latlngs, {
                color: "#2563eb",
                weight: 2.5,
                fillColor: "#3b82f6",
                fillOpacity: 0.22,
            }).addTo(layerGroup);

            latlngs.forEach((latlng, index) => {
                L.circleMarker(latlng, {
                    radius: 4,
                    color: "#0f172a",
                    weight: 1,
                    fillColor: "#ffffff",
                    fillOpacity: 1,
                }).addTo(layerGroup).bindTooltip(`Ponto ${index + 1}`);
            });

            map.fitBounds(polygon.getBounds(), { padding: [24, 24] });
        } else {
            const polyline = L.polyline(latlngs, {
                color: "#2563eb",
                weight: 3,
            }).addTo(layerGroup);

            latlngs.forEach((latlng, index) => {
                L.circleMarker(latlng, {
                    radius: 4,
                    color: "#0f172a",
                    weight: 1,
                    fillColor: "#ffffff",
                    fillOpacity: 1,
                }).addTo(layerGroup).bindTooltip(`Ponto ${index + 1}`);
            });

            map.fitBounds(polyline.getBounds(), { padding: [24, 24] });
        }
    }

    function openDrawer() {
        const drawer = document.getElementById("fpDrawer");
        const backdrop = document.getElementById("fpDrawerBackdrop");
        if (!drawer || !backdrop) return;

        drawer.classList.add("open");
        backdrop.classList.add("open");
        drawer.setAttribute("aria-hidden", "false");

        setTimeout(() => {
            if (drawerMap) drawerMap.invalidateSize();
        }, 280);
    }

    function closeDrawer() {
        const drawer = document.getElementById("fpDrawer");
        const backdrop = document.getElementById("fpDrawerBackdrop");
        if (!drawer || !backdrop) return;

        drawer.classList.remove("open");
        backdrop.classList.remove("open");
        drawer.setAttribute("aria-hidden", "true");
    }

    function fillDrawerInfo(data) {
        const title = document.getElementById("fpDrawerTitle");
        const subtitle = document.getElementById("fpDrawerSubtitle");

        const area = document.getElementById("fpInfoArea");
        const perimeter = document.getElementById("fpInfoPerimeter");
        const points = document.getElementById("fpInfoPoints");
        const mode = document.getElementById("fpInfoMode");
        const closed = document.getElementById("fpInfoClosed");
        const active = document.getElementById("fpInfoActive");

        const obsWrap = document.getElementById("fpObservationWrap");
        const obsText = document.getElementById("fpObservationText");

        if (title) title.textContent = data.name || "Preview";
        if (subtitle) subtitle.textContent = data.farm_name || "Sem fazenda";

        if (area) area.textContent = formatArea(data.area_m2);
        if (perimeter) perimeter.textContent = formatPerimeter(data.perimeter_m);
        if (points) points.textContent = Array.isArray(data.points) ? data.points.length : "-";
        if (mode) mode.textContent = data.mode || "-";
        if (closed) closed.textContent = data.is_closed ? "Fechado" : "Aberto";
        if (active) active.textContent = data.is_active ? "Ativo" : "Inativo";

        if (data.observation) {
            obsWrap.style.display = "block";
            obsText.textContent = data.observation;
        } else {
            obsWrap.style.display = "none";
            obsText.textContent = "";
        }
    }

    async function handlePreviewClick(url) {
        try {
            const response = await fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            if (!response.ok) {
                throw new Error("Falha ao carregar preview");
            }

            const data = await response.json();

            fillDrawerInfo(data);

            const mapEl = document.getElementById("fpDrawerMap");
            if (!mapEl) return;

            if (!drawerMap) {
                drawerMap = initSatelliteMap(mapEl);
                drawerLayerGroup = L.layerGroup().addTo(drawerMap);
            }

            drawPolygonOnMap(drawerMap, drawerLayerGroup, data);
            openDrawer();
        } catch (error) {
            console.error(error);
            alert("Não foi possível carregar o preview do polígono.");
        }
    }

    async function initFormPreview() {
        const formMapEl = document.getElementById("fp-form-map");
        if (!formMapEl) return;

        const previewUrl = formMapEl.dataset.previewUrl;
        if (!previewUrl) return;

        try {
            const response = await fetch(previewUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            if (!response.ok) return;

            const data = await response.json();

            if (!formMap) {
                formMap = initSatelliteMap(formMapEl);
                formLayerGroup = L.layerGroup().addTo(formMap);
            }

            drawPolygonOnMap(formMap, formLayerGroup, data);

            setTimeout(() => {
                if (formMap) formMap.invalidateSize();
            }, 100);
        } catch (error) {
            console.error("Erro ao carregar preview no form:", error);
        }
    }

    document.addEventListener("click", function (event) {
        const previewBtn = event.target.closest(".fp-preview-btn");
        if (previewBtn) {
            event.preventDefault();
            const url = previewBtn.dataset.previewUrl;
            if (url) handlePreviewClick(url);
        }

        if (
            event.target.id === "fpDrawerClose" ||
            event.target.id === "fpDrawerBackdrop"
        ) {
            closeDrawer();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeDrawer();
        }
    });

    document.addEventListener("DOMContentLoaded", function () {
        initFormPreview();
    });
})();