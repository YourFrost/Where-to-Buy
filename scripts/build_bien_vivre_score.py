"""
Remplace le score "bien-vivre" fictif par un score composite calcule a
partir de 5 sources de donnees publiques reelles, choisies par l'utilisateur
du projet :

1. Securite         -> SSMSI, taux de delinquance par commune (2025)
2. Acces aux soins  -> DREES, indicateur APL aux medecins generalistes (2024)
3. Commerces/services -> INSEE BPE 2025, comptage d'equipements de proximite
4. Dynamisme demographique -> INSEE, evolution de la population 2013-2023
5. Fiscalite locale -> DGFiP, taux global de taxe fonciere sur le bati (2025)

Methode : chaque source donne un indicateur brut par commune, qu'on
normalise en score 0-100 (apres ecretage des valeurs extremes p2/p98,
min-max scaling), en orientant toujours "100 = plutot favorable". Le
score final est une moyenne ponderee des 5 sous-scores disponibles pour
la commune (les sous-scores manquants sont simplement exclus de la
moyenne, pas remplaces par une valeur neutre arbitraire).

Ponderation par defaut (modifiable ci-dessous) :
  securite 25%, acces_soins 20%, commerces 25%, demographie 10%, fiscalite 20%
"""
import json
import csv
import gzip

import numpy as np
import pandas as pd

# Paris/Lyon/Marseille : plusieurs sources (APL, population historique)
# publient leurs donnees par ARRONDISSEMENT, pas par commune globale (meme
# probleme que rencontre avec le DVF, voir scripts/build_commune_price_data.py).
ARRONDISSEMENT_TO_PARENT = {}
for i in range(1, 21):
    ARRONDISSEMENT_TO_PARENT[f"751{i:02d}"] = "75056"
for i in range(1, 17):
    ARRONDISSEMENT_TO_PARENT[f"132{i:02d}"] = "13055"
for i in range(1, 10):
    ARRONDISSEMENT_TO_PARENT[f"6938{i}"] = "69123"

WEIGHTS = {
    "securite": 0.25,
    "acces_soins": 0.20,
    "commerces": 0.25,
    "demographie": 0.10,
    "fiscalite": 0.20,
}

# --- 1. Securite (SSMSI) ---------------------------------------------------

CRIME_INDICATEURS = [
    "Cambriolages de logement",
    "Vols avec armes",
    "Vols violents sans arme",
    "Violences physiques hors cadre familial",
    "Destructions et dégradations volontaires",
]


def load_securite():
    totals = {}
    with gzip.open("raw_data/delinquance_communes.csv.gz", "rt", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter=";")
        for row in r:
            if row["annee"] != "2025" or row["indicateur"] not in CRIME_INDICATEURS:
                continue
            taux = row["taux_pour_mille"]
            # "ndiff" = secret statistique (trop peu de faits pour publier),
            # ce qui correspond quasi toujours a une zone tres peu touchee -> 0
            val = float(taux.replace(",", ".")) if taux and taux != "NA" else 0.0
            code = row["CODGEO_2026"]
            totals[code] = totals.get(code, 0.0) + val
    return totals


# --- 2. Acces aux soins (DREES APL medecins generalistes) ------------------

def load_acces_soins():
    raw = pd.read_excel("raw_data/apl_medecins.xlsx", sheet_name="APL 2024", header=8)
    raw = raw.iloc[1:]  # ligne d'unites
    raw.columns = [
        "code", "commune", "apl_tous_ages", "apl_65", "apl_62", "apl_60", "pop_std", "pop_totale",
    ]
    raw = raw[["code", "apl_tous_ages", "pop_totale"]].dropna()
    raw["apl_tous_ages"] = pd.to_numeric(raw["apl_tous_ages"], errors="coerce")
    raw["pop_totale"] = pd.to_numeric(raw["pop_totale"], errors="coerce")
    raw["code"] = raw["code"].astype(str).replace(ARRONDISSEMENT_TO_PARENT)

    # moyenne ponderee par population pour les codes regroupes (Paris/Lyon/Marseille)
    raw["poids"] = raw["apl_tous_ages"] * raw["pop_totale"]
    agg = raw.groupby("code").agg(poids=("poids", "sum"), pop=("pop_totale", "sum"))
    agg["apl"] = agg["poids"] / agg["pop"]
    return agg["apl"].to_dict()


# --- 3. Commerces / services de proximite (INSEE BPE 2025) -----------------

PROXIMITE_TYPES = {
    "B105",  # supermarche / multi-commerce
    "B201",  # superette
    "B202",  # epicerie
    "B204",  # boucherie charcuterie
    "B207",  # boulangerie-patisserie
    "D307",  # pharmacie
    "A206", "A207", "A208",  # poste (bureau / relais / agence)
    "A203",  # banque
    "C107", "C108", "C109",  # ecole maternelle / primaire / elementaire
    "C201",  # college
    "D265",  # medecin generaliste
    "D277",  # chirurgien dentiste
    "D502",  # accueil du jeune enfant (creche)
}


def load_commerces():
    counts = {}
    chunks = pd.read_csv(
        "raw_data/bpe_extracted/DS_BPE_2025_data.csv",
        sep=";",
        usecols=["GEO", "GEO_OBJECT", "FACILITY_TYPE", "OBS_VALUE"],
        dtype={"GEO": "string"},
        chunksize=500_000,
    )
    for chunk in chunks:
        chunk = chunk[(chunk["GEO_OBJECT"] == "COM") & (chunk["FACILITY_TYPE"].isin(PROXIMITE_TYPES))]
        for code, val in chunk.groupby("GEO")["OBS_VALUE"].sum().items():
            counts[code] = counts.get(code, 0) + float(val)
    return counts


# --- 4. Dynamisme demographique (INSEE, evolution 2013-2023) ---------------

def load_demographie():
    df = pd.read_excel(
        "raw_data/population_historique.xlsx", sheet_name="pop_1876_2023", header=5,
        usecols=["CODGEO", "PMUN2023", "PMUN2013"],
    )
    df = df.dropna(subset=["PMUN2023", "PMUN2013"])
    df["CODGEO"] = df["CODGEO"].astype(str).replace(ARRONDISSEMENT_TO_PARENT)
    agg = df.groupby("CODGEO")[["PMUN2023", "PMUN2013"]].sum()
    agg = agg[agg["PMUN2013"] > 0]
    croissance = (agg["PMUN2023"] - agg["PMUN2013"]) / agg["PMUN2013"]
    return croissance.to_dict()


# --- 5. Fiscalite locale (DGFiP, taxe fonciere batie 2025) -----------------

def load_fiscalite():
    df = pd.read_csv(
        "raw_data/fiscalite_locale.csv", sep=";",
        usecols=["EXERCICE", "INSEE COM", "Taux_Global_TFB"],
        dtype={"INSEE COM": "string"},
    )
    df = df[df["EXERCICE"] == 2025].dropna(subset=["Taux_Global_TFB"])
    df["code"] = df["INSEE COM"].str.zfill(5)
    return dict(zip(df["code"], df["Taux_Global_TFB"]))


# --- normalisation -----------------------------------------------------

def normalize_to_100(values_by_code, invert=False, p_low=2, p_high=98):
    codes = list(values_by_code.keys())
    vals = np.array([values_by_code[c] for c in codes], dtype=float)
    lo, hi = np.percentile(vals, [p_low, p_high])
    if hi <= lo:
        hi = lo + 1
    clipped = np.clip(vals, lo, hi)
    scaled = (clipped - lo) / (hi - lo) * 100
    if invert:
        scaled = 100 - scaled
    return {c: round(float(s), 1) for c, s in zip(codes, scaled)}


def main():
    print("Chargement securite (SSMSI)...")
    securite_raw = load_securite()
    print(f"  {len(securite_raw)} communes")

    print("Chargement acces aux soins (DREES APL)...")
    soins_raw = load_acces_soins()
    print(f"  {len(soins_raw)} communes")

    print("Chargement commerces/services (INSEE BPE)...")
    commerces_raw = load_commerces()
    print(f"  {len(commerces_raw)} communes")

    print("Chargement demographie (INSEE)...")
    demo_raw = load_demographie()
    print(f"  {len(demo_raw)} communes")

    print("Chargement fiscalite (DGFiP)...")
    fiscal_raw = load_fiscalite()
    print(f"  {len(fiscal_raw)} communes")

    scores = {
        "securite": normalize_to_100(securite_raw, invert=True),
        "acces_soins": normalize_to_100(soins_raw, invert=False),
        "commerces": normalize_to_100({c: np.log1p(v) for c, v in commerces_raw.items()}, invert=False),
        "demographie": normalize_to_100(demo_raw, invert=False),
        "fiscalite": normalize_to_100(fiscal_raw, invert=True),
    }

    with open("data/communes-data.json", encoding="utf-8") as f:
        communes = json.load(f)

    n_full, n_partial = 0, 0
    for c in communes:
        code = c["code"]
        sous_scores = {}
        weighted_sum = 0.0
        weight_total = 0.0
        for axe, weight in WEIGHTS.items():
            val = scores[axe].get(code)
            if val is not None:
                sous_scores[axe] = val
                weighted_sum += val * weight
                weight_total += weight
        if weight_total > 0:
            c["score_bien_vivre"] = round(weighted_sum / weight_total, 1)
            c["score_bien_vivre_details"] = sous_scores
            c["score_bien_vivre_couverture"] = round(weight_total / sum(WEIGHTS.values()), 2)
            if weight_total >= sum(WEIGHTS.values()) - 1e-9:
                n_full += 1
            else:
                n_partial += 1
        else:
            c["score_bien_vivre"] = None
            c["score_bien_vivre_details"] = {}
            c["score_bien_vivre_couverture"] = 0.0

    with open("data/communes-data.json", "w", encoding="utf-8") as f:
        json.dump(communes, f, ensure_ascii=False, separators=(",", ":"))

    n_none = sum(1 for c in communes if c["score_bien_vivre"] is None)
    print(f"\n{len(communes)} communes : {n_full} avec les 5 axes, {n_partial} avec une partie, {n_none} sans aucune donnee")


if __name__ == "__main__":
    main()
