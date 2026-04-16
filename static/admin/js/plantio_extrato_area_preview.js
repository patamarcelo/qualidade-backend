(function () {
    function normalizePoints(points) {
        if (!Array.isArray(points)) return [];
        return points
            .map((p) => {
                const lat = p.lat ?? p.latitude;
                const lng = p.lng ?? p.longitude ?? p.lon;
                if (lat == null || lng == null) return null;
                return {
                    lat: Number(lat),
                    lng: Number(lng),
                };
            })
            .filter(Boolean);
    }

    function initMap(el) {
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

    function drawGeometry(map, data) {
        const pts = normalizePoints(data.points);
        const latlngs = pts.map((p) => [p.lat, p.lng]);

        if (!latlngs.length) {
            map.setView([-14.235, -51.9253], 4);
            return;
        }

        let layer;

        if (data.is_closed && latlngs.length >= 3) {
            layer = L.polygon(latlngs, {
                color: "#2563eb",
                weight: 2.5,
                fillColor: "#3b82f6",
                fillOpacity: 0.22,
            }).addTo(map);
        } else {
            layer = L.polyline(latlngs, {
                color: "#2563eb",
                weight: 3,
            }).addTo(map);
        }

        latlngs.forEach((latlng, index) => {
            L.circleMarker(latlng, {
                radius: 4,
                color: "#0f172a",
                weight: 1,
                fillColor: "#ffffff",
                fillOpacity: 1,
            }).addTo(map).bindTooltip(`P${index + 1}`);
        });

        map.fitBounds(layer.getBounds(), { padding: [24, 24] });
    }

    async function bootFormPreview() {
        const el = document.getElementById("fp-form-map");
        if (!el || typeof L === "undefined") return;

        const previewUrl = el.dataset.previewUrl;
        if (!previewUrl) return;

        try {
            const response = await fetch(previewUrl, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });

            if (!response.ok) return;

            const data = await response.json();
            const map = initMap(el);
            drawGeometry(map, data);

            setTimeout(() => map.invalidateSize(), 250);
        } catch (err) {
            console.error("Falha ao carregar preview do KML:", err);
        }
    }

    document.addEventListener("DOMContentLoaded", bootFormPreview);
})();

document.addEventListener("DOMContentLoaded", function () {
    const cards = document.querySelectorAll(".card");

    cards.forEach((card) => {
        const titleEl = card.querySelector(".card-title");
        if (!titleEl) return;

        const title = (titleEl.textContent || "").trim().toLowerCase();

        if (title === "kml / geometria") {
            const collapseBtn = card.querySelector('[data-card-widget="collapse"]');
            const body = card.querySelector(".card-body");

            if (!collapseBtn || !body) return;

            // se ainda estiver aberto, fecha ao carregar
            const isVisible = body.offsetParent !== null;
            if (isVisible) {
                collapseBtn.click();
            }
        }
    });
});