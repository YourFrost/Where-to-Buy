(function () {
  "use strict";

  // Rendu canvas : ~35 000 marqueurs restent fluides, donc pas de plafond en
  // pratique. Gardé comme garde-fou si le jeu de données grossissait un jour
  // (un plafond par score créerait un biais géographique, voir historique).
  const MAX_MARKERS = 50000;

  const state = {
    communes: [],         // toutes les communes (data/communes-data.json)
    deptNameByCode: {},   // "01" -> "Ain" (depuis departements.geojson)
    deptToRegion: {},     // "01" -> "84"
    map: null,
    markersLayer: null,
    canvasRenderer: null,
    selectedCity: null,   // { label, lat, lon }
    filters: {
      regionCode: "",
      deptCode: "",
      seaMaxKm: 450,
      hopitalMaxKm: 40,
      gareMaxKm: 60,
      grandeVilleMaxKm: 140,
      lacMaxKm: 65,
      gendarmerieMaxKm: 25,
      priceMin: 0,
      priceMax: 11500,
      qolMin: 0,
      cityRadiusKm: 150,
    },
  };

  function haversineKm(lat1, lon1, lat2, lon2) {
    const toRad = (d) => (d * Math.PI) / 180;
    const R = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  async function loadJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Échec chargement ${url}: ${res.status}`);
    return res.json();
  }

  function initMap() {
    const map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([46.6, 2.4], 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      subdomains: "abc",
      maxZoom: 19,
    }).addTo(map);
    state.map = map;
    state.canvasRenderer = L.canvas({ padding: 0.5 });
    state.markersLayer = L.layerGroup().addTo(map);
  }

  function addDeptBackgroundLayer(geojson) {
    L.geoJSON(geojson, {
      style: {
        fillOpacity: 0,
        color: "#3a4150",
        weight: 1,
        interactive: false,
      },
    }).addTo(state.map);
  }

  function matchesFilters(d) {
    const f = state.filters;
    if (f.regionCode && d.code_region !== f.regionCode) return false;
    if (f.deptCode && d.code_departement !== f.deptCode) return false;
    if (d.distance_mer_km > f.seaMaxKm) return false;
    if (d.distance_hopital_km > f.hopitalMaxKm) return false;
    if (d.distance_gare_km > f.gareMaxKm) return false;
    if (d.distance_grande_ville_km > f.grandeVilleMaxKm) return false;
    if (d.distance_lac_km > f.lacMaxKm) return false;
    if (d.distance_gendarmerie_km > f.gendarmerieMaxKm) return false;
    if (d.prix_m2 == null || d.prix_m2 < f.priceMin || d.prix_m2 > f.priceMax) return false;
    if (d.score_bien_vivre == null || d.score_bien_vivre < f.qolMin) return false;
    if (state.selectedCity) {
      const dist = haversineKm(d.lat, d.lon, state.selectedCity.lat, state.selectedCity.lon);
      if (dist > f.cityRadiusKm) return false;
    }
    return true;
  }

  function computeMatches() {
    return state.communes.filter(matchesFilters);
  }

  function fmtEuro(n) {
    return new Intl.NumberFormat("fr-FR").format(Math.round(n));
  }

  function fmtInt(n) {
    return new Intl.NumberFormat("fr-FR").format(n);
  }

  function updateResultsPanel(matches) {
    const countEl = document.getElementById("results-count");
    if (matches.length > MAX_MARKERS) {
      countEl.textContent = `${fmtInt(matches.length)} communes correspondantes — carte limitée aux ${fmtInt(MAX_MARKERS)} meilleures (affinez les filtres pour voir le reste)`;
    } else {
      countEl.textContent = `${fmtInt(matches.length)} commune${matches.length > 1 ? "s" : ""} correspondante${matches.length > 1 ? "s" : ""}`;
    }

    const list = document.getElementById("results-list");
    list.innerHTML = "";
    matches
      .slice()
      .sort((a, b) => (b.score_bien_vivre ?? -1) - (a.score_bien_vivre ?? -1))
      .slice(0, 30)
      .forEach((d) => {
        const row = document.createElement("div");
        row.className = "result-item";
        row.innerHTML = `<span>${d.nom} (${d.code_departement})</span><span>${fmtEuro(d.prix_m2)} €/m² · ${d.score_bien_vivre}/100</span>`;
        row.addEventListener("click", () => flyToCommune(d));
        list.appendChild(row);
      });
  }

  function flyToCommune(d) {
    state.map.flyTo([d.lat, d.lon], 11, { duration: 0.6 });
  }

  const BIEN_VIVRE_AXIS_LABELS = {
    securite: "Sécurité",
    acces_soins: "Accès aux soins",
    commerces: "Commerces/services",
    demographie: "Démographie",
    fiscalite: "Fiscalité",
  };

  function bienVivreDetailHTML(d) {
    const details = d.score_bien_vivre_details || {};
    const axes = Object.keys(BIEN_VIVRE_AXIS_LABELS);
    const rows = axes
      .map((axe) => {
        const val = details[axe];
        return `<div class="row sub"><span>${BIEN_VIVRE_AXIS_LABELS[axe]}</span><span>${val != null ? val + "/100" : "n/d"}</span></div>`;
      })
      .join("");
    return rows;
  }

  function communeTooltipHTML(d) {
    const priceLabelMap = {
      dvf_2023_commune: "Prix moyen (DVF 2023, commune)",
      dvf_2023_departement: "Prix moyen (DVF 2023, département)",
      estimation_departement: "Prix moyen (estimation département)",
    };
    const priceLabel = priceLabelMap[d.prix_m2_source] || "Prix moyen";
    const deptNom = state.deptNameByCode[d.code_departement] || d.code_departement;
    return `
      <strong>${d.nom}</strong>
      <div class="row"><span>Département</span><span>${deptNom} (${d.code_departement})</span></div>
      <div class="row"><span>Population</span><span>${fmtInt(d.population)}</span></div>
      <div class="row"><span>${priceLabel}</span><span>${d.prix_m2 != null ? fmtEuro(d.prix_m2) + " €/m²" : "n/d"}</span></div>
      <div class="row"><span>Bien-vivre</span><span>${d.score_bien_vivre != null ? d.score_bien_vivre + "/100" : "n/d"}</span></div>
      ${bienVivreDetailHTML(d)}
      <div class="row"><span>Distance mer</span><span>${d.distance_mer_km} km</span></div>
      <div class="row"><span>Distance hôpital</span><span>${d.distance_hopital_km} km</span></div>
      <div class="row"><span>Distance gare</span><span>${d.distance_gare_km} km</span></div>
      <div class="row"><span>Distance grande ville</span><span>${d.distance_grande_ville_km} km</span></div>
      <div class="row"><span>Distance lac</span><span>${d.distance_lac_km} km</span></div>
      <div class="row"><span>Distance gendarmerie</span><span>${d.distance_gendarmerie_km} km</span></div>
    `;
  }

  function updateMapMarkers(matches) {
    state.markersLayer.clearLayers();

    const sorted = matches.length > MAX_MARKERS
      ? matches.slice().sort((a, b) => (b.score_bien_vivre ?? -1) - (a.score_bien_vivre ?? -1)).slice(0, MAX_MARKERS)
      : matches;

    const tooltip = document.getElementById("dept-tooltip");

    sorted.forEach((d) => {
      const marker = L.circleMarker([d.lat, d.lon], {
        renderer: state.canvasRenderer,
        radius: 3.5,
        fillColor: "#4f8cff",
        fillOpacity: 0.75,
        color: "#8ab4ff",
        weight: 0.5,
      });
      marker.on("mouseover", (e) => {
        marker.setStyle({ radius: 6, weight: 1.5 });
        tooltip.hidden = false;
        tooltip.innerHTML = communeTooltipHTML(d);
        const pt = state.map.latLngToContainerPoint(e.latlng);
        tooltip.style.left = pt.x + 14 + "px";
        tooltip.style.top = pt.y + 14 + "px";
      });
      marker.on("mouseout", () => {
        marker.setStyle({ radius: 3.5, weight: 0.5 });
        tooltip.hidden = true;
      });
      marker.on("click", () => flyToCommune(d));
      state.markersLayer.addLayer(marker);
    });
  }

  function debounce(fn, wait) {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), wait);
    };
  }

  const debouncedUpdateMap = debounce((matches) => updateMapMarkers(matches), 150);

  function refreshAll() {
    const matches = computeMatches();
    updateResultsPanel(matches);
    debouncedUpdateMap(matches);
  }

  function populateRegionSelect() {
    const select = document.getElementById("region-select");
    const regions = [...new Map(state.communes.map((d) => [d.code_region, d.region_nom])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    regions.forEach(([code, nom]) => {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = nom;
      select.appendChild(opt);
    });
  }

  function populateDeptSelect(regionCode) {
    const select = document.getElementById("dept-select");
    select.innerHTML = '<option value="">Tous les départements</option>';
    Object.entries(state.deptNameByCode)
      .filter(([code]) => !regionCode || state.deptToRegion[code] === regionCode)
      .sort((a, b) => a[1].localeCompare(b[1]))
      .forEach(([code, nom]) => {
        const opt = document.createElement("option");
        opt.value = code;
        opt.textContent = `${nom} (${code})`;
        select.appendChild(opt);
      });
  }

  function setupFilterEvents() {
    document.getElementById("region-select").addEventListener("change", (e) => {
      state.filters.regionCode = e.target.value;
      state.filters.deptCode = "";
      populateDeptSelect(e.target.value);
      document.getElementById("dept-select").value = "";
      refreshAll();
    });

    document.getElementById("dept-select").addEventListener("change", (e) => {
      state.filters.deptCode = e.target.value;
      refreshAll();
    });

    const seaSlider = document.getElementById("sea-dist");
    seaSlider.addEventListener("input", (e) => {
      state.filters.seaMaxKm = Number(e.target.value);
      document.getElementById("sea-dist-val").textContent = e.target.value;
      refreshAll();
    });

    const hopitalDist = document.getElementById("hopital-dist");
    hopitalDist.addEventListener("input", (e) => {
      state.filters.hopitalMaxKm = Number(e.target.value);
      document.getElementById("hopital-dist-val").textContent = e.target.value;
      refreshAll();
    });

    const gareDist = document.getElementById("gare-dist");
    gareDist.addEventListener("input", (e) => {
      state.filters.gareMaxKm = Number(e.target.value);
      document.getElementById("gare-dist-val").textContent = e.target.value;
      refreshAll();
    });

    const grandeVilleDist = document.getElementById("grandeville-dist");
    grandeVilleDist.addEventListener("input", (e) => {
      state.filters.grandeVilleMaxKm = Number(e.target.value);
      document.getElementById("grandeville-dist-val").textContent = e.target.value;
      refreshAll();
    });

    const lacDist = document.getElementById("lac-dist");
    lacDist.addEventListener("input", (e) => {
      state.filters.lacMaxKm = Number(e.target.value);
      document.getElementById("lac-dist-val").textContent = e.target.value;
      refreshAll();
    });

    const gendarmerieDist = document.getElementById("gendarmerie-dist");
    gendarmerieDist.addEventListener("input", (e) => {
      state.filters.gendarmerieMaxKm = Number(e.target.value);
      document.getElementById("gendarmerie-dist-val").textContent = e.target.value;
      refreshAll();
    });

    const priceMin = document.getElementById("price-min");
    const priceMax = document.getElementById("price-max");
    function syncPrice() {
      let min = Number(priceMin.value);
      let max = Number(priceMax.value);
      if (min > max) [min, max] = [max, min];
      state.filters.priceMin = min;
      state.filters.priceMax = max;
      document.getElementById("price-min-val").textContent = fmtEuro(min);
      document.getElementById("price-max-val").textContent = fmtEuro(max);
      refreshAll();
    }
    priceMin.addEventListener("input", syncPrice);
    priceMax.addEventListener("input", syncPrice);

    const qolMin = document.getElementById("qol-min");
    qolMin.addEventListener("input", (e) => {
      state.filters.qolMin = Number(e.target.value);
      document.getElementById("qol-val").textContent = e.target.value;
      refreshAll();
    });

    const cityRadius = document.getElementById("city-radius");
    cityRadius.addEventListener("input", (e) => {
      state.filters.cityRadiusKm = Number(e.target.value);
      document.getElementById("city-radius-val").textContent = e.target.value;
      refreshAll();
    });

    document.getElementById("reset-btn").addEventListener("click", resetFilters);
  }

  function resetFilters() {
    state.filters = {
      regionCode: "",
      deptCode: "",
      seaMaxKm: 450,
      hopitalMaxKm: 40,
      gareMaxKm: 60,
      grandeVilleMaxKm: 140,
      lacMaxKm: 65,
      gendarmerieMaxKm: 25,
      priceMin: 0,
      priceMax: 11500,
      qolMin: 0,
      cityRadiusKm: 150,
    };
    state.selectedCity = null;

    document.getElementById("region-select").value = "";
    populateDeptSelect("");
    document.getElementById("dept-select").value = "";
    document.getElementById("sea-dist").value = 450;
    document.getElementById("sea-dist-val").textContent = "450";
    document.getElementById("hopital-dist").value = 40;
    document.getElementById("hopital-dist-val").textContent = "40";
    document.getElementById("gare-dist").value = 60;
    document.getElementById("gare-dist-val").textContent = "60";
    document.getElementById("grandeville-dist").value = 140;
    document.getElementById("grandeville-dist-val").textContent = "140";
    document.getElementById("lac-dist").value = 65;
    document.getElementById("lac-dist-val").textContent = "65";
    document.getElementById("gendarmerie-dist").value = 25;
    document.getElementById("gendarmerie-dist-val").textContent = "25";
    document.getElementById("price-min").value = 0;
    document.getElementById("price-max").value = 11500;
    document.getElementById("price-min-val").textContent = "0";
    document.getElementById("price-max-val").textContent = fmtEuro(11500);
    document.getElementById("qol-min").value = 0;
    document.getElementById("qol-val").textContent = "0";
    document.getElementById("city-search").value = "";
    document.getElementById("city-selected").hidden = true;
    document.getElementById("city-radius-row").hidden = true;
    document.getElementById("city-suggestions").innerHTML = "";

    refreshAll();
  }

  // --- Recherche de ville via l'API officielle adresse.data.gouv.fr (gratuite, sans clé) ---
  let searchDebounce = null;
  function setupCitySearch() {
    const input = document.getElementById("city-search");
    const suggestionsBox = document.getElementById("city-suggestions");

    input.addEventListener("input", () => {
      const q = input.value.trim();
      clearTimeout(searchDebounce);
      if (q.length < 2) {
        suggestionsBox.innerHTML = "";
        return;
      }
      searchDebounce = setTimeout(() => runCitySearch(q), 300);
    });

    async function runCitySearch(q) {
      try {
        const url = `https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&type=municipality&limit=5`;
        const data = await loadJSON(url);
        suggestionsBox.innerHTML = "";
        (data.features || []).forEach((f) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.textContent = f.properties.label;
          btn.addEventListener("click", () => selectCity(f));
          suggestionsBox.appendChild(btn);
        });
      } catch (err) {
        console.error("Recherche ville échouée", err);
      }
    }

    function selectCity(feature) {
      const [lon, lat] = feature.geometry.coordinates;
      state.selectedCity = { label: feature.properties.label, lat, lon };
      input.value = "";
      suggestionsBox.innerHTML = "";

      const chip = document.getElementById("city-selected");
      chip.hidden = false;
      chip.innerHTML = `<span>📍 ${feature.properties.label}</span>`;
      const clearBtn = document.createElement("button");
      clearBtn.textContent = "✕";
      clearBtn.addEventListener("click", () => {
        state.selectedCity = null;
        chip.hidden = true;
        document.getElementById("city-radius-row").hidden = true;
        refreshAll();
      });
      chip.appendChild(clearBtn);

      document.getElementById("city-radius-row").hidden = false;
      refreshAll();
    }
  }

  async function main() {
    initMap();

    const [geojson, communes] = await Promise.all([
      loadJSON("data/departements.geojson"),
      loadJSON("data/communes-data.json"),
    ]);

    state.communes = communes;
    addDeptBackgroundLayer(geojson);

    state.deptNameByCode = Object.fromEntries(
      geojson.features.map((f) => [f.properties.code, f.properties.nom])
    );
    state.deptToRegion = {};
    communes.forEach((c) => {
      if (!(c.code_departement in state.deptToRegion)) {
        state.deptToRegion[c.code_departement] = c.code_region;
      }
    });

    populateRegionSelect();
    populateDeptSelect("");
    setupFilterEvents();
    setupCitySearch();

    refreshAll();

    window.addEventListener("resize", () => state.map.invalidateSize());
    setTimeout(() => state.map.invalidateSize(), 100);
  }

  main().catch((err) => {
    console.error(err);
    document.getElementById("map").innerHTML =
      `<div style="color:#fff;padding:20px">Erreur de chargement : ${err.message}</div>`;
  });
})();
