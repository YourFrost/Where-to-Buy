"""
Calcule le prix median au m2 par COMMUNE a partir du DVF 2023 (meme fichier
que scripts/build_price_data.py, deja telecharge dans raw_data/).

Une commune n'a un prix "propre" que si elle a au moins MIN_TRANSACTIONS
ventes residentielles valides sur l'annee (sinon la mediane n'a pas de sens
statistique). En dessous de ce seuil, on retombe sur la mediane du
departement (data/prix_m2_departements_2023.csv), avec la source marquee.
"""
import pandas as pd

SRC = "raw_data/dvf_2023_full.csv.gz"
OUT = "data/prix_m2_communes_2023.csv"
MIN_TRANSACTIONS = 3

USECOLS = ["id_mutation", "nature_mutation", "valeur_fonciere", "code_commune", "code_departement", "type_local", "surface_reelle_bati"]


def main():
    df = pd.read_csv(SRC, usecols=USECOLS, dtype={"code_commune": "string", "code_departement": "string"}, compression="gzip")
    print(f"Lignes brutes: {len(df):,}")

    df = df[df["nature_mutation"] == "Vente"]
    df = df[df["type_local"].isin(["Maison", "Appartement"])]
    df = df[(df["valeur_fonciere"] > 0) & (df["surface_reelle_bati"] > 0)]

    df["grp_size"] = df.groupby("id_mutation")["id_mutation"].transform("size")
    df = df[df["grp_size"] == 1]

    # Paris/Lyon/Marseille : le DVF code par arrondissement, pas par
    # commune globale. On regroupe vers le code commune parent pour avoir
    # un prix "propre" a ces 3 villes plutot que de retomber sur le
    # departement (moins precis pour Lyon/Marseille).
    ARRONDISSEMENT_TO_PARENT = {}
    for i in range(1, 21):
        ARRONDISSEMENT_TO_PARENT[f"751{i:02d}"] = "75056"
    for i in range(1, 17):
        ARRONDISSEMENT_TO_PARENT[f"132{i:02d}"] = "13055"
    for i in range(1, 10):
        ARRONDISSEMENT_TO_PARENT[f"6938{i}"] = "69123"
    df["code_commune"] = df["code_commune"].replace(ARRONDISSEMENT_TO_PARENT)

    df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
    df = df[(df["prix_m2"] >= 300) & (df["prix_m2"] <= 15000)]
    print(f"Lignes exploitables: {len(df):,}")

    agg = (
        df.groupby("code_commune")["prix_m2"]
        .agg(prix_m2_median="median", nb_transactions="count")
        .reset_index()
        .rename(columns={"code_commune": "code"})
    )
    agg["prix_m2_median"] = agg["prix_m2_median"].round(0)
    agg = agg[agg["nb_transactions"] >= MIN_TRANSACTIONS]
    agg = agg.sort_values("code")
    agg.to_csv(OUT, index=False)
    print(f"{len(agg)} communes avec prix propre (>= {MIN_TRANSACTIONS} transactions) ecrites dans {OUT}")


if __name__ == "__main__":
    main()
