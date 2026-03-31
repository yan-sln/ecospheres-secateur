# Ecosphères Sécateur

Plugin QGIS d'intersection spatiale. Sélectionnez une commune, le plugin intersecte automatiquement toutes les couches WFS visibles du projet et extrait les entités concernées.

## Fonctionnalités
- **Recherche** avec autocomplétion via le module `geoselector`.
- **Intersection automatique** de toutes les couches WFS visibles du projet avec le contour de la parcelle.
- **Résultats en couches mémoire** regroupées dans un groupe "Résultats secateur".
- **Export CSV** — un fichier par couche dans un dossier au choix.
- **Export PDF** — rapport cartographique multi-pages avec fond de carte IGN Plan IGN v2.

## Installation
```bash
# macOS
ln -s /chemin/vers/ecospheres-secateur \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/ecospheres-secateur

# Linux
ln -s /chemin/vers/ecospheres-secateur \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/ecospheres-secateur
```
Puis dans QGIS : **Extensions > Gérer/Installer > chercher "Ecosphères Sécateur" > activer**.

## Configuration requise
| Élément | Description | Valeur par défaut |
|---------|-------------|-------------------|
| QGIS | ≥ 3.28 (supporte Python 3.9) | – |
| Python | ≥ 3.9 (pour `str.removesuffix`) | – |
| Services WFS | Accessible depuis le projet QGIS | – |
| Ressources | `resources/icon.png`, `resources/report_page.qpt` | fournis dans le dépôt |

## Utilisation du plugin
1. Activer le plugin depuis le menu **Extensions → Gérer/Installer → Ecosphères Sécateur**.
2. Un icône apparaît dans la barre d’outils ; cliquer dessus pour ouvrir le panneau latéral.
3. Taper le nom d’une commune (au moins 2 caractères) et choisir dans la liste proposée.
4. Sélectionner la section puis la parcelle souhaitées.
5. Cliquer **Interroger** : le plugin récupère la géométrie, trouve les couches WFS visibles et crée des calques mémoire contenant les entités intersectées.
6. Les résultats apparaissent dans le groupe "Résultats secateur" du projet.
7. **Exporter CSV** : choisir un répertoire, chaque couche résultat devient un fichier `nom_couche.csv`.
8. **Exporter PDF** : choisir un fichier, le rapport comprend une page d’overview + une page par couche résultat avec le fond de carte IGN.

## Développement & tests
```bash
# Cloner et symlinker
git clone <repo> && cd qgis-plugins
ln -s "$(pwd)/ecospheres-secateur" ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/
```

### Qualité du code

Le projet utilise [ruff](https://docs.astral.sh/ruff/) (lint + format) et [pyright](https://github.com/microsoft/pyright) (type checking), exécutés automatiquement via [pre-commit](https://pre-commit.com/). Prérequis : [uv](https://docs.astral.sh/uv/#installation).

```bash
# Installer les dépendances de dev et activer les hooks pre-commit
uv sync
uv run pre-commit install

# Lancer manuellement sur tous les fichiers
uv run pre-commit run --all-files

# Ou individuellement
uv run ruff check --fix .
uv run ruff format .
uv run pyright
```

- **Structure du code** :
  - `core/` : logique métier (recherche, intersection, export).
  - `ui/` : interface utilisateur (`ui/panel.py`).
  - `plugin.py` : point d’entrée du plugin.
- **Tests manuels** : lancer le plugin, sélectionner des entités, vérifier que les calques mémoire apparaissent et que les exports s’ouvrent sans erreur.
- **Future** : ajouter une suite de tests unitaires (pytest) et CI (GitHub Actions).

### Personnaliser le modèle PDF

Le rapport PDF utilise le modèle `resources/report_page.qpt`. Pour le modifier :

1. Dans QGIS, ouvrir **Projet > Gestionnaire de mises en page**
2. Créer une nouvelle mise en page vide (**Mise en page vide > Créer…**)
3. Dans le composeur, **Mise en page > Ajouter des éléments depuis un modèle…** et sélectionner `report_page.qpt`
4. Modifier librement : polices, positions, ajouter un logo, une barre d'échelle, une flèche nord, etc.
5. Sauvegarder avec **Mise en page > Sauvegarder comme modèle…** en écrasant `report_page.qpt`

Les deux éléments que le code utilise ont un **ID d'élément** (visible dans Propriétés de l'élément) qu'il faut conserver :
- `title` — le libellé texte du titre (nom de commune ou de couche)
- `map` — l'élément carte qui affiche les résultats