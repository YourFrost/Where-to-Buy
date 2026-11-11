# Où acheter ? — Prototype

Carte interactive de France (par **commune**, ~34 700 communes) pour filtrer les zones où chercher un bien immobilier.

## Lancer en local

```bash
python -m http.server 5173
```

Puis ouvrir http://localhost:5173

## Filtres disponibles

- **Proximité d'une ville** : recherche réelle via l'API officielle `api-adresse.data.gouv.fr` (gratuite, sans clé), rayon en km.
- **Région / département** : sélection directe.
- **Distance à la mer / un hôpital / une gare / un lac / une grande ville (>50 000 hab.) / une brigade de gendarmerie** : réelles, à vol d'oiseau depuis le centre de chaque commune (OpenStreetMap pour hôpitaux/gares/lacs/littoral/gendarmerie, geo.api.gouv.fr pour les grandes villes). **Pas une distance routière** (voir Limites).
- **Prix moyen au m²** : ✅ **données réelles DVF 2023**, propres à la commune quand il y a assez de transactions (sinon repli sur la médiane du département).
- **Score "bien-vivre"** : ✅ composite réel (sécurité, accès aux soins, commerces/services, démographie, fiscalité locale) — voir Méthodologie ci-dessous. Le détail par axe est visible dans l'infobulle au survol d'une commune.

La carte affiche toutes les communes correspondantes sous forme de points (rendu canvas, fluide même avec les ~34 700 communes affichées en même temps). Le panneau de résultats liste séparément les 30 mieux notées ("bien-vivre").

Note d'implémentation : une première version plafonnait l'affichage aux 4 000 communes les mieux notées au-delà d'un certain nombre de résultats, par souci de performance. Ce plafond a été retiré : trier par score puis couper au Nᵉ résultat crée un biais géographique (les communes bien notées ne sont pas réparties uniformément sur le territoire), ce qui vidait des régions entières de la carte par défaut. Le rendu canvas tient très bien la charge sans plafond, donc ce n'était pas nécessaire.

## Données

- `data/departements.geojson` : contours de département (fond de carte, source [gregoiredavid/france-geojson](https://github.com/gregoiredavid/france-geojson)).
- `data/communes-data.json` : fichier principal utilisé par l'app (une entrée par commune : prix réel, distances réelles, score bien-vivre composite réel).
- `data/prix_m2_communes_2023.csv`, `data/prix_m2_departements_2023.csv` : prix médian au m² par commune / département, calculés depuis le DVF.
- `data/departements-data.json` : conservé comme filet de secours (prix estimé pour l'Alsace-Moselle, voir plus bas) et pour le nom des départements.

### Pipeline de génération (dans l'ordre)

```bash
python scripts/build_data.py            # centroïdes/régions départements + valeurs par défaut (fictives)
python scripts/build_price_data.py      # DVF 2023 -> prix réel au m² par département
python scripts/build_poi_data.py        # fusionne prix + distances réelles par département (legacy, plus utilisé par l'app)
python scripts/build_commune_price_data.py  # DVF 2023 -> prix réel au m² par commune
python scripts/build_communes_data.py   # fichier final data/communes-data.json (prix + 5 distances) par commune
python scripts/add_gendarmerie_distance.py  # ajoute distance_gendarmerie_km (incrémental, ne recalcule pas le reste)
python scripts/build_bien_vivre_score.py    # calcule le score bien-vivre composite réel (incrémental)
```

Ces scripts dépendent de fichiers sources dans `raw_data/` (téléchargés une fois, pas re-générés automatiquement) :

| Fichier | Source | Comment l'obtenir |
|---|---|---|
| `raw_data/dvf_2023_full.csv.gz` (~100 Mo) | [geo-dvf (Etalab/cquest)](https://files.data.gouv.fr/geo-dvf/latest/csv/2023/full.csv.gz) | `curl -L -o raw_data/dvf_2023_full.csv.gz https://files.data.gouv.fr/geo-dvf/latest/csv/2023/full.csv.gz` |
| `raw_data/hospitals.json`, `gares.json`, `lacs.json`, `coastline.json`, `gendarmerie.json` | [Overpass API](https://overpass-api.de/api/interpreter) (OpenStreetMap) | requêtes dans `raw_data/overpass_*.query`, à poster sur `https://overpass-api.de/api/interpreter` (2-4 min chacune) |
| `raw_data/communes.json` | [geo.api.gouv.fr](https://geo.api.gouv.fr/communes) | `curl -o raw_data/communes.json "https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,codeRegion,centre,population,surface&format=json&geometry=centre"` |
| `raw_data/regions_api.json`, `departements_api.json` | geo.api.gouv.fr | `curl -o raw_data/regions_api.json https://geo.api.gouv.fr/regions?format=json` |
| `raw_data/delinquance_communes.csv.gz` (~40 Mo) | [SSMSI](https://www.data.gouv.fr/datasets/bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales) | données communales de délinquance |
| `raw_data/apl_medecins.xlsx` | [DREES](https://data.drees.solidarites-sante.gouv.fr/explore/dataset/530_l-accessibilite-potentielle-localisee-apl/) | indicateur APL aux médecins généralistes par commune |
| `raw_data/bpe.zip` → `raw_data/bpe_extracted/` (~150 Mo décompressé) | [INSEE BPE 2025](https://www.insee.fr/fr/statistiques/8217527) | dénombrement des équipements par commune |
| `raw_data/fiscalite_locale.csv` (~40 Mo) | [DGFiP, data.gouv.fr](https://www.data.gouv.fr/datasets/fiscalite-locale-des-particuliers) | taux de taxe foncière par commune |
| `raw_data/population_historique.xlsx` | [INSEE](https://www.insee.fr/fr/statistiques/3698339) | séries historiques de population communale (1876-2023) |

Ces fichiers sont volumineux (~200 Mo au total avec le littoral) : conservés en local pour relancer les scripts sans re-télécharger, mais pas indispensables si `data/communes-data.json` est déjà à jour. Nécessite `pandas` et `scipy` (`pip install pandas scipy`).

## Méthodologie et limites connues

- **Prix DVF** : mutations "Vente" uniquement, biens Maison/Appartement, mutations multi-lots exclues (une valeur foncière DVF peut être partagée entre plusieurs lignes), valeurs aberrantes exclues (<300 €/m² ou >15000 €/m²). Médiane par commune si ≥ 3 transactions en 2023, sinon repli sur la médiane du département.
- **Paris/Lyon/Marseille** : le DVF encode ces 3 villes par arrondissement (75101-75120, 69381-69389, 13201-13216), pas par commune globale — les scripts regroupent ces arrondissements vers le code commune parent pour obtenir un prix propre à la ville plutôt qu'un repli sur le département.
- **Alsace-Moselle (57/67/68)** : pas de DVF du tout (régime du Livre foncier) → prix estimé (mock), marqué comme tel (`prix_m2_source: "estimation_departement"`).
- **Distances** : à vol d'oiseau (haversine) depuis le centre de la commune, pas une distance routière — une commune séparée d'un hôpital par une montagne ou un fleuve sans pont proche aura une distance affichée trompeusement courte. Les points OSM sont récupérés sur une zone englobant largement la France (quelques points frontaliers UK/Belgique/Allemagne/Suisse/Italie/Espagne peuvent apparaître, impact marginal).
- **Littoral** : distance calculée depuis le tracé réel du littoral OSM (`natural=coastline`), sous-échantillonné (1 point sur 15) pour rester performant — précision largement suffisante à l'échelle kilométrique visée ici.
- **Lacs** : seuls les plans d'eau nommés (`natural=water` + `water=lake|reservoir` avec un tag `name`) sont retenus, pour exclure les petites mares non pertinentes.
- **Grandes villes** : communes de plus de 50 000 habitants (123 communes).
- **Gendarmerie** : brigades identifiées via OSM (`amenity=police` avec `name` ou `operator` contenant "gendarmerie"), pour ne pas mélanger avec les commissariats de police nationale/municipale (3 529 brigades).

### Score "bien-vivre"

Composite de 5 axes, chacun normalisé en sous-score 0-100 (écrêtage aux percentiles 2/98 puis min-max, orienté "100 = plutôt favorable"), combinés en moyenne pondérée (`scripts/build_bien_vivre_score.py`) :

| Axe | Poids | Source | Donnée brute |
|---|---|---|---|
| Sécurité | 25% | SSMSI 2025 | somme des taux pour mille de 5 indicateurs (cambriolages, vols avec armes, vols violents, violences hors cadre familial, dégradations) — inversé (moins de délinquance = mieux) |
| Accès aux soins | 20% | DREES APL 2024 | indicateur d'accessibilité potentielle localisée aux médecins généralistes |
| Commerces/services | 25% | INSEE BPE 2025 | nombre d'équipements de proximité dans la commune (supermarché, boulangerie, pharmacie, poste, banque, écoles, collège, médecin, dentiste, crèche) |
| Démographie | 10% | INSEE, séries historiques | évolution de la population 2013→2023 |
| Fiscalité locale | 20% | DGFiP 2025 | taux global de taxe foncière sur le bâti — inversé (taux plus bas = mieux) |

Limites à connaître :
- **Paris/Lyon/Marseille** : comme pour le DVF, l'APL et la population historique sont publiées par arrondissement (75101-75120, etc.) — regroupées vers la commune parente (moyenne pondérée par la population pour l'APL, somme pour la population).
- Les sous-scores manquants pour une commune (ex. pas de comptage BPE si aucun équipement recensé du tout, ce qui peut aussi signifier une donnée non couverte) sont simplement exclus de la moyenne plutôt que remplacés par une valeur neutre arbitraire — `score_bien_vivre_couverture` dans les données indique la part des 5 axes effectivement disponibles pour cette commune.
- Le sous-score "Commerces/services" ne compte que les équipements **dans la commune elle-même**, pas dans les communes voisines : une petite commune juste à côté d'une ville bien équipée sera sous-notée sur cet axe (partiellement compensé par le critère de distance à une grande ville, séparé).
- "Démographie" traite la croissance comme positive, ce qui est discutable selon le profil recherché (dynamisme vs calme/authenticité) — poids volontairement faible (10%) pour cette raison.
- Pondération fixe pour l'instant, pas encore ajustable par l'utilisateur (voir V2).

## Prochaines étapes (V2)

- **Distance routière réelle** : nécessiterait un moteur de routage auto-hébergé (OSRM + extrait OSM France ~4 Go) ou une API payante à l'échelle commune — hors de portée d'un prototype léger, voir la discussion dans l'historique du projet.
- **Pondération du score bien-vivre ajustable** par l'utilisateur (sliders par axe plutôt que poids fixes dans le script).
- **Frontières communales réelles** (polygones) plutôt que des points, si la performance de rendu le permet (nécessiterait un fond de carte communal, plus lourd que les centroïdes actuels).
