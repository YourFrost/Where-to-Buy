"""
Ajoute distance_gendarmerie_km a data/communes-data.json sans recalculer
tout le reste (reutilise raw_data/gendarmerie.json, deja recupere via
Overpass : amenity=police avec name/operator contenant "gendarmerie").
"""
import json
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


def haversine_km(lat1, lon1, lats2, lons2):
    lat1, lon1 = math.radians(lat1), math.radians(lon1)
    lats2 = np.radians(lats2)
    lons2 = np.radians(lons2)
    dlat = lats2 - lat1
    dlon = lons2 - lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(lat1) * np.cos(lats2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def load_osm_points(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    lats, lons = [], []
    for el in raw["elements"]:
        if el["type"] == "node":
            lats.append(el["lat"])
            lons.append(el["lon"])
        elif "center" in el:
            lats.append(el["center"]["lat"])
            lons.append(el["center"]["lon"])
    return np.array(lats), np.array(lons)


def main():
    lats, lons = load_osm_points("raw_data/gendarmerie.json")
    print(f"{len(lats)} brigades de gendarmerie chargees")
    tree = cKDTree(project(lats, lons))

    with open("data/communes-data.json", encoding="utf-8") as f:
        communes = json.load(f)

    for c in communes:
        pt = project([c["lat"]], [c["lon"]])[0]
        _, idx = tree.query(pt, k=min(5, len(lats)))
        idx = np.atleast_1d(idx)
        d = haversine_km(c["lat"], c["lon"], lats[idx], lons[idx])
        c["distance_gendarmerie_km"] = round(float(d.min()), 1)

    with open("data/communes-data.json", "w", encoding="utf-8") as f:
        json.dump(communes, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(communes)} communes mises a jour avec distance_gendarmerie_km")


if __name__ == "__main__":
    main()
