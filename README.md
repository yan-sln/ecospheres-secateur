# Ecosphères Sécateur

Plugin QGIS d'intersection spatiale. Sélectionnez une commune, le plugin intersecte automatiquement toutes les couches WFS visibles du projet et extrait les entités concernées.

## Fonctionnalités

- **Recherche de commune** avec autocomplétion (API geo.api.gouv.fr)
- **Intersection automatique** de toutes les couches WFS visibles du projet avec le contour communal
- **Résultats en couches mémoire** regroupées dans un groupe "Résultats secateur"
- **Export CSV** — un fichier par couche dans un dossier au choix
- **Export PDF** — rapport cartographique multi-pages avec fond de carte IGN Plan IGN v2

## Installation

QGIS 3.28 minimum.

```bash
# macOS
ln -s /chemin/vers/ecospheres-secateur \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/ecospheres-secateur

# Linux
ln -s /chemin/vers/ecospheres-secateur \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/ecospheres-secateur
```

Puis dans QGIS : **Extensions > Gérer/Installer > chercher "Ecosphères Sécateur" > activer**.

## Utilisation

1. Charger un projet QGIS avec des couches WFS (GPU, Géorisques, etc.)
2. Cliquer sur l'icône sécateur dans la toolbar — un panneau latéral s'ouvre
3. Taper un nom de commune, sélectionner dans la liste
4. Cliquer **Interroger**
5. Les résultats apparaissent dans le groupe "Résultats secateur"
6. Cliquer **Exporter CSV** pour sauvegarder les attributs
7. Cliquer **Exporter PDF** pour générer un rapport cartographique

## Développement

```bash
# Cloner et symlinker
git clone <repo> && cd qgis-plugins
ln -s "$(pwd)/ecospheres-secateur" ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/

# Recharger après modif : installer le plugin "Plugin Reloader" et cibler ecospheres-secateur
```

### Qualité du code

Le projet utilise [ruff](https://docs.astral.sh/ruff/) (lint + format) et [pyright](https://github.com/microsoft/pyright) (type checking), exécutés automatiquement via [pre-commit](https://pre-commit.com/).

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

### Structure

```
ecospheres-secateur/
├── __init__.py          # classFactory
├── metadata.txt         # Métadonnées plugin
├── plugin.py            # Toolbar + cycle de vie du panneau
├── ui/
│   └── panel.py         # Panneau dock : recherche commune + boutons + barre de progression
├── core/
│   ├── commune_api.py   # Appels geo.api.gouv.fr
│   ├── intersector.py   # Détection WFS, intersection, couches résultat
│   └── export.py        # Export CSV et PDF
└── resources/
    ├── icon.png
    └── report_page.qpt  # Modèle de mise en page pour l'export PDF
```

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
