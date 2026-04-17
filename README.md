# Ecosphères Cadreur

Plugin QGIS de sélection géographique. Sélectionnez une commune, le plugin interroge automatiquement toutes les couches WFS visibles du projet et extrait les entités concernées.

## Flux de travail

Le plugin permet aux utilisateurs de :

- Sélectionner une commune à partir de la liste déroulante de recherche
- Choisir une section au sein de cette commune
- Récupérer automatiquement toutes les parcelles de cette section
- Créer des couches mémoire pour les résultats groupées sous "Résultats cadreur"

## Fonctionnalités
- **Recherche** avec autocomplétion via le module `geoselector`.
- **Sélection géographique** de toutes les parcelles dans une section.
- **Résultats en couches mémoire** regroupées dans un groupe "Résultats cadreur".
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
1. Activer le plugin depuis le menu **Extensions → Gérer/Installer → Ecosphères Cadreur**.
2. Un icône apparaît dans la barre d’outils ; cliquer dessus pour ouvrir le panneau latéral.
3. Taper le nom d’une commune (au moins 2 caractères) et choisir dans la liste proposée.
4. Sélectionner la section puis cliquer **Interroger** : le plugin récupère les géométries des parcelles et crée des calques mémoire contenant toutes les parcelles de la section.
5. Les résultats apparaissent dans le groupe "Résultats cadreur" du projet.

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


# Dev
* Ne fonctionne pas encore sur la ville de Paris
* Mettre à jour metadata.tx