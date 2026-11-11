"""
Enrichit data/departements-data.json avec :
- le vrai prix median au m2 (DVF 2023) calcule par build_price_data.py
- la distance (km, a vol d'oiseau depuis le centroide du departement)
  au point le plus proche pour 4 criteres reels :
    - distance_hopital_km   (OSM amenity=hospital, via Overpass)
    - distance_gare_km      (OSM railway=station/halt, via Overpass)
    - distance_grande_ville_km (communes >= 50 000 hab., via geo.api.gouv.fr)
    - distance_lac_km       (OSM natural=water + water=lake/reservoir, nommes, via Overpass)

Limites connues :
- Les points OSM sont recuperes sur une bounding box englobant la France
  (avec un peu de marge), donc quelques points frontaliers (UK, Belgique,
  Allemagne, Suisse, Italie, Espagne, Andorre) peuvent s'y trouver. Cela
  n'affecte que les departements frontaliers, de facon marginale.
- La distance est calculee depuis le CENTROIDE du departement, pas depuis
  une commune precise : c'est un indicateur d'ordre de grandeur, pas une
  distance routiere.
"""
import json
import math
import csv

import numpy as np

DATA_PATH = "data/departements-data.json"
PRICE_CSV = "data/prix_m2_departements_2023.csv"


def haversine_km_vec(lat1, lon1, lats2, lons2):
    R = 6371.0
    lat1, lon1 = math.radians(lat1), math.radians(lon1)
    lats2 = np.radians(lats2)
    lons2 = np.radians(lons2)
    dlat = lats2 - lat1
    dlon = lons2 - lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(lat1) * np.cos(lats2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


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
    return np.array(lats), np.array(lons)


def load_grandes_villes(path, min_population=50000):
    with open(path, encoding="utf-8") as f:
        communes = json.load(f)
    lats, lons = [], []
    for c in communes:
        pop = c.get("population")
        centre = c.get("centre")
        if pop and pop >= min_population and centre:
            lon, lat = centre["coordinates"]
            lats.append(lat)
            lons.append(lon)
    return np.array(lats), np.array(lons)


def load_price_data(path):
    prices = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            prices[row["code"]] = {
                "prix_m2_median": float(row["prix_m2_median"]),
                "nb_transactions_dvf": int(row["nb_transactions"]),
            }
    return prices


# departements non couverts par le DVF (regime cadastral local Alsace-Moselle)
NON_COUVERT_DVF = {"57", "67", "68"}


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        depts = json.load(f)

    hosp_lat, hosp_lon = load_osm_points("raw_data/hospitals.json")
    gare_lat, gare_lon = load_osm_points("raw_data/gares.json")
    lac_lat, lac_lon = load_osm_points("raw_data/lacs.json", require_name=True)
    ville_lat, ville_lon = load_grandes_villes("raw_data/communes.json")
    prices = load_price_data(PRICE_CSV)

    print(f"POI charges: {len(hosp_lat)} hopitaux, {len(gare_lat)} gares, "
          f"{len(lac_lat)} lacs nommes, {len(ville_lat)} grandes villes (>=50k hab.)")

    for d in depts:
        lat, lon = d["lat"], d["lon"]
        d["distance_hopital_km"] = round(float(haversine_km_vec(lat, lon, hosp_lat, hosp_lon).min()), 1)
        d["distance_gare_km"] = round(float(haversine_km_vec(lat, lon, gare_lat, gare_lon).min()), 1)
        d["distance_lac_km"] = round(float(haversine_km_vec(lat, lon, lac_lat, lac_lon).min()), 1)

        # distance a la grande ville la plus proche, en excluant le cas
        # trivial ou le departement EST lui-meme celui de la grande ville
        # (on garde quand meme la valeur : une distance ~0 est correcte
        # et utile pour le filtre "proche d'une grande ville").
        d["distance_grande_ville_km"] = round(float(haversine_km_vec(lat, lon, ville_lat, ville_lon).min()), 1)

        price = prices.get(d["code"])
        if price:
            d["prix_m2"] = price["prix_m2_median"]
            d["prix_m2_source"] = "dvf_2023"
            d["nb_transactions_dvf"] = price["nb_transactions_dvf"]
        else:
            # Alsace-Moselle : pas de DVF, on garde l'estimation precedente
            d["prix_m2_source"] = "estimation"
            if d["code"] not in NON_COUVERT_DVF:
                print(f"ATTENTION: pas de prix DVF pour {d['code']} {d['nom']}, hors Alsace-Moselle attendu")

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(depts, f, ensure_ascii=False, indent=1)

    print(f"{len(depts)} departements mis a jour dans {DATA_PATH}")


if __name__ == "__main__":
    main()
