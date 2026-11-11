"""
Génère data/departements-data.json à partir de data/departements.geojson.
Calcule un centroïde approximatif (centre de bbox) par département,
associe la région (mapping officiel post-réforme 2016), marque les
départements côtiers, et génère des indicateurs de démonstration
(prix moyen au m², score "bien-vivre") -- CES DEUX DERNIERS SONT FICTIFS,
à remplacer par de vraies sources (DVF, INSEE...) dans une V2.
"""
import json
import random

DEPT_TO_REGION = {
    # Auvergne-Rhône-Alpes
    "01": "84", "03": "84", "07": "84", "15": "84", "26": "84", "38": "84",
    "42": "84", "43": "84", "63": "84", "69": "84", "73": "84", "74": "84",
    # Bourgogne-Franche-Comté
    "21": "27", "25": "27", "39": "27", "58": "27", "70": "27", "71": "27", "89": "27", "90": "27",
    # Bretagne
    "22": "53", "29": "53", "35": "53", "56": "53",
    # Centre-Val de Loire
    "18": "24", "28": "24", "36": "24", "37": "24", "41": "24", "45": "24",
    # Corse
    "2A": "94", "2B": "94",
    # Grand Est
    "08": "44", "10": "44", "51": "44", "52": "44", "54": "44", "55": "44",
    "57": "44", "67": "44", "68": "44", "88": "44",
    # Hauts-de-France
    "02": "32", "59": "32", "60": "32", "62": "32", "80": "32",
    # Ile-de-France
    "75": "11", "77": "11", "78": "11", "91": "11", "92": "11", "93": "11", "94": "11", "95": "11",
    # Normandie
    "14": "28", "27": "28", "50": "28", "61": "28", "76": "28",
    # Nouvelle-Aquitaine
    "16": "75", "17": "75", "19": "75", "23": "75", "24": "75", "33": "75",
    "40": "75", "47": "75", "64": "75", "79": "75", "86": "75", "87": "75",
    # Occitanie
    "09": "76", "11r": "76",  # fixed below
    "12": "76", "30": "76", "31": "76", "32": "76", "34": "76", "46": "76",
    "48": "76", "65": "76", "66": "76", "81": "76", "82": "76",
    # Pays de la Loire
    "44": "52", "49": "52", "53": "52", "72": "52", "85": "52",
    # PACA
    "04": "93", "05": "93", "06": "93", "13": "93", "83": "93", "84": "93",
}
# fix collision: department code "11" (Aude) vs region code "11" (IDF) used as dict key clash risk avoided via distinct var above
DEPT_TO_REGION["11"] = "76"
del DEPT_TO_REGION["11r"]

REGION_NAMES = {
    "84": "Auvergne-Rhône-Alpes", "27": "Bourgogne-Franche-Comté", "53": "Bretagne",
    "24": "Centre-Val de Loire", "94": "Corse", "44": "Grand Est", "32": "Hauts-de-France",
    "11": "Île-de-France", "28": "Normandie", "75": "Nouvelle-Aquitaine", "76": "Occitanie",
    "52": "Pays de la Loire", "93": "Provence-Alpes-Côte d'Azur",
}

COASTAL = {
    "62", "80", "76", "14", "50", "35", "22", "29", "56", "44", "85", "17",
    "33", "40", "64", "66", "11", "34", "30", "13", "83", "06", "2A", "2B",
}

# Départements où le marché est notoirement plus cher (pour crédibiliser la démo)
EXPENSIVE_BUMP = {
    "75": 3.4, "92": 2.6, "06": 1.9, "83": 1.7, "13": 1.6, "74": 1.8, "33": 1.55,
    "94": 1.7, "78": 1.9, "91": 1.6, "77": 1.55, "93": 1.5, "69": 1.6, "35": 1.4,
    "44": 1.45, "31": 1.5, "2A": 1.6, "2B": 1.5, "38": 1.35, "67": 1.3, "34": 1.4,
    "30": 1.25, "29": 1.15, "56": 1.2, "22": 1.05,
}
CHEAP_BUMP = {
    "23": 0.55, "58": 0.55, "52": 0.55, "55": 0.6, "03": 0.6, "36": 0.6, "18": 0.65,
    "15": 0.6, "48": 0.6, "08": 0.6, "10": 0.65, "70": 0.6, "89": 0.65, "43": 0.65,
    "19": 0.65, "63": 0.7, "90": 0.7, "39": 0.7, "02": 0.7, "60": 0.75, "80": 0.75,
}

def bbox_center(geom):
    coords = []
    def walk(c):
        if isinstance(c[0], (float, int)):
            coords.append(c)
        else:
            for sub in c:
                walk(sub)
    walk(geom["coordinates"])
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (sum(lons) / len(lons), sum(lats) / len(lats))

def haversine(lon1, lat1, lon2, lat2):
    from math import radians, sin, cos, asin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2 * 6371 * asin(sqrt(a))

def main():
    with open("data/departements.geojson", encoding="utf-8") as f:
        gj = json.load(f)

    depts = []
    for feat in gj["features"]:
        code = feat["properties"]["code"]
        nom = feat["properties"]["nom"]
        lon, lat = bbox_center(feat["geometry"])
        region_code = DEPT_TO_REGION.get(code)
        depts.append({
            "code": code,
            "nom": nom,
            "region_code": region_code,
            "region_nom": REGION_NAMES.get(region_code, "?"),
            "lon": round(lon, 4),
            "lat": round(lat, 4),
            "coastal": code in COASTAL,
        })

    missing = [d["code"] for d in depts if d["region_code"] is None]
    if missing:
        raise SystemExit(f"Départements sans région mappée: {missing}")

    coastal_points = [(d["lon"], d["lat"]) for d in depts if d["coastal"]]

    random.seed(42)
    for d in depts:
        if d["coastal"]:
            d["distance_mer_km"] = round(random.uniform(0, 15), 1)
        else:
            dmin = min(haversine(d["lon"], d["lat"], clon, clat) for clon, clat in coastal_points)
            d["distance_mer_km"] = round(dmin, 1)

        base_price = random.uniform(1300, 2600)
        mult = EXPENSIVE_BUMP.get(d["code"], CHEAP_BUMP.get(d["code"], 1.0))
        d["prix_m2"] = round(base_price * mult, -1)

        # score bien-vivre fictif: mélange d'un tirage aléatoire et de quelques biais
        # (climat sud/côte, faible densité urbaine perçue positivement, mais dégressif avec le prix extrême)
        base_score = random.uniform(35, 85)
        if d["coastal"]:
            base_score += 8
        if d["region_code"] == "93":  # PACA
            base_score += 5
        if d["prix_m2"] > 4000:
            base_score -= 6
        d["score_bien_vivre"] = round(max(0, min(100, base_score)), 1)

    with open("data/departements-data.json", "w", encoding="utf-8") as f:
        json.dump(depts, f, ensure_ascii=False, indent=1)

    print(f"{len(depts)} départements écrits dans data/departements-data.json")

if __name__ == "__main__":
    main()
