"""
Calcule le prix moyen (médian) au m2 par departement a partir des vraies
donnees DVF (Demandes de Valeurs Foncieres) 2023, source officielle
data.gouv.fr / geo-dvf (cquest), fichier France entiere.

Methodologie (limitations connues du format DVF) :
- On ne garde que les mutations de type "Vente".
- On ne garde que les lots "Maison" ou "Appartement" avec surface et
  valeur foncieres renseignees.
- Une mutation DVF peut comporter plusieurs lignes (dependances, plusieurs
  biens) qui partagent la MEME valeur_fonciere totale : pour ne pas
  fausser le prix/m2 en comptant plusieurs fois la meme valeur, on ne
  garde que les mutations ne comportant qu'UNE seule ligne
  Maison/Appartement.
- On exclut les prix/m2 aberrants (<300 EUR ou >15000 EUR) qui sont
  presque toujours des erreurs de saisie DVF.
- On calcule la MEDIANE (plus robuste que la moyenne face aux valeurs
  extremes) par departement.

C'est une estimation raisonnable pour un prototype, pas un indicateur
officiel garanti a l'euro pres.
"""
import pandas as pd

SRC = "raw_data/dvf_2023_full.csv.gz"
OUT = "data/prix_m2_departements_2023.csv"

USECOLS = ["id_mutation", "nature_mutation", "valeur_fonciere", "code_departement", "type_local", "surface_reelle_bati"]

def main():
    df = pd.read_csv(SRC, usecols=USECOLS, dtype={"code_departement": "string"}, compression="gzip")
    print(f"Lignes brutes: {len(df):,}")

    df = df[df["nature_mutation"] == "Vente"]
    df = df[df["type_local"].isin(["Maison", "Appartement"])]
    df = df[(df["valeur_fonciere"] > 0) & (df["surface_reelle_bati"] > 0)]
    print(f"Apres filtre type/valeur/surface: {len(df):,}")

    # une mutation ne doit contenir qu'une seule ligne residentielle
    # (evite de compter la meme valeur_fonciere plusieurs fois)
    df["grp_size"] = df.groupby("id_mutation")["id_mutation"].transform("size")
    df = df[df["grp_size"] == 1]
    print(f"Apres filtre mutation mono-bien: {len(df):,}")

    df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
    df = df[(df["prix_m2"] >= 300) & (df["prix_m2"] <= 15000)]
    print(f"Apres filtre outliers prix/m2: {len(df):,}")

    agg = (
        df.groupby("code_departement")["prix_m2"]
        .agg(prix_m2_median="median", prix_m2_moyen="mean", nb_transactions="count")
        .reset_index()
        .rename(columns={"code_departement": "code"})
    )
    agg["prix_m2_median"] = agg["prix_m2_median"].round(0)
    agg["prix_m2_moyen"] = agg["prix_m2_moyen"].round(0)
    agg = agg.sort_values("code")
    agg.to_csv(OUT, index=False)
    print(f"{len(agg)} departements ecrits dans {OUT}")
    print(agg.head(10))

if __name__ == "__main__":
    main()
