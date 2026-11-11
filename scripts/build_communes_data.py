"""
Construit data/communes-data.json : le jeu de donnees principal de l'app,
a la granularite COMMUNE (~34 700 communes metropolitaines) au lieu du
departement.

Pour chaque commune :
- code, nom, codeDepartement, codeRegion (+ noms), population, lat/lon
  (source : geo.api.gouv.fr)
- prix_m2 : mediane DVF 2023 propre a la commune si >= 3 transactions,
  sinon mediane du departement (source marquee dans prix_m2_source)
- distance_mer_km, distance_hopital_km, distance_gare_km, distance_lac_km,
  distance_grande_ville_km : distance a vol d'oiseau (haversine) au point
  le plus proche, calculee efficacement via un arbre KD (scipy cKDTree)
  sur une projection plane locale (assez precise a l'echelle de la France).

Sources POI reutilisees de l'etape precedente (raw_data/*.json, deja
recuperees via Overpass API / geo.api.gouv.fr) + raw_data/coastline.json
(trace reel du littoral, OSM natural=coastline) pour une vraie distance
a la mer (auparavant approximee via une liste de departements cotiers).
"""
import json
import csv
import math

import numpy as np
from scipy.spatial import cKDTree

MEAN_LAT = 46.5
KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LON = 111.32 * math.cos(math.radians(MEAN_LAT))


def project(lats, lons):
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    return np.column_stack([lons * KM_PER_DEG_LON, lats * KM_PER_DEG_LAT])


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


class NearestFinder:
    """KD-tree sur projection plane pour trouver vite des candidats, puis
    distance haversine exacte sur les k candidats retenus."""

    def __init__(self, lats, lons, k=5):
        self.lats = np.asarray(lats, dtype=float)
        self.lons = np.asarray(lons, dtype=float)
        self.tree = cKDTree(project(self.lats, self.lons))
        self.k = min(k, len(self.lats))

    def nearest_km(self, lat, lon):
        pt = project([lat], [lon])[0]
        _, idx = self.tree.query(pt, k=self.k)
        idx = np.atleast_1d(idx)
        d = haversine_km(lat, lon, self.lats[idx], self.lons[idx])
        return float(d.min())


def load_osm_points(path, require_name=False):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    lats, lons = [], []
    for el in raw["elements"]:
        if require_name and not el.get("tags", {}).get("name"):
            continue
        if el["type"] == "node":
            lats.append(el["lat"])
            lons.append(el["lon"])
        elif "center" in el:
            lats.append(el["center"]["lat"])
            lons.append(el["center"]["lon"])
    return lats, lons


def load_coastline_points(path, stride=15):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    lats, lons = [], []
    for el in raw["elements"]:
        geom = el.get("geometry") or []
        for pt in geom[::stride]:
            lats.append(pt["lat"])
            lons.append(pt["lon"])
    return lats, lons


def load_region_names(path):
    with open(path, encoding="utf-8") as f:
        regions = json.load(f)
    return {r["code"]: r["nom"] for r in regions}


def load_price_csv(path, code_field="code"):
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row[code_field]] = row
    return out


def main():
    with open("raw_data/communes.json", encoding="utf-8") as f:
        communes = json.load(f)
    communes = [c for c in communes if not c["code"].startswith(("97", "98")) and c.get("centre")]
    print(f"{len(communes)} communes metropolitaines")

    region_names = load_region_names("raw_data/regions_api.json")
    dept_prices = load_price_csv("data/prix_m2_departements_2023.csv")
    commune_prices = load_price_csv("data/prix_m2_communes_2023.csv")

    # Bas-Rhin/Haut-Rhin/Moselle : hors DVF (regime du Livre foncier), on
    # reprend l'estimation deja calculee au niveau departement (voir
    # scripts/build_data.py) comme filet de secours.
    with open("data/departements-data.json", encoding="utf-8") as f:
        dept_fallback = {d["code"]: d["prix_m2"] for d in json.load(f)}

    print("Chargement des POI...")
    hosp = NearestFinder(*load_osm_points("raw_data/hospitals.json"))
    gare = NearestFinder(*load_osm_points("raw_data/gares.json"))
    lac = NearestFinder(*load_osm_points("raw_data/lacs.json", require_name=True))
    coast = NearestFinder(*load_coastline_points("raw_data/coastline.json"))

    grandes_villes = [c for c in communes if c.get("population") and c["population"] >= 50000]
    ville = NearestFinder(
        [c["centre"]["coordinates"][1] for c in grandes_villes],
        [c["centre"]["coordinates"][0] for c in grandes_villes],
    )
    print(f"{len(grandes_villes)} grandes villes (>=50k hab.) comme reference")

    NON_COUVERT_DVF = {"57", "67", "68"}

    out = []
    for i, c in enumerate(communes):
        lon, lat = c["centre"]["coordinates"]
        code_dept = c["codeDepartement"]

        cp = commune_prices.get(c["code"])
        dp = dept_prices.get(code_dept)
        if cp:
            prix_m2 = float(cp["prix_m2_median"])
            prix_source = "dvf_2023_commune"
            nb_trans = int(cp["nb_transactions"])
        elif dp:
            prix_m2 = float(dp["prix_m2_median"])
            prix_source = "dvf_2023_departement"
            nb_trans = 0
        elif code_dept in dept_fallback:
            prix_m2 = float(dept_fallback[code_dept])
            prix_source = "estimation_departement"
            nb_trans = 0
        else:
            prix_m2 = None
            prix_source = "indisponible"
            nb_trans = 0

        distance_mer_km = round(coast.nearest_km(lat, lon), 1)

        out.append({
            "code": c["code"],
            "nom": c["nom"],
            "code_departement": code_dept,
            "code_region": c["codeRegion"],
            "region_nom": region_names.get(c["codeRegion"], "?"),
            "population": c.get("population") or 0,
            "lat": lat,
            "lon": lon,
            "prix_m2": prix_m2,
            "prix_m2_source": prix_source,
            "nb_transactions_dvf": nb_trans,
            "score_bien_vivre": None,  # rempli par scripts/build_bien_vivre_score.py
            "distance_mer_km": distance_mer_km,
            "distance_hopital_km": round(hosp.nearest_km(lat, lon), 1),
            "distance_gare_km": round(gare.nearest_km(lat, lon), 1),
            "distance_lac_km": round(lac.nearest_km(lat, lon), 1),
            "distance_grande_ville_km": round(ville.nearest_km(lat, lon), 1),
        })
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1}/{len(communes)}")

    with open("data/communes-data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    have_price = sum(1 for c in out if c["prix_m2"] is not None)
    print(f"{len(out)} communes ecrites dans data/communes-data.json ({have_price} avec un prix)")


if __name__ == "__main__":
    main()
