# modele-projet

Le modèle d'où naît chaque projet d'Edouard : la méthode, les garde-fous (hooks git, garde de Claude,
CI, protection de branche) et, plus tard, le déploiement. C'est un modèle [Copier](https://copier.readthedocs.io/) :
un projet né du modèle peut ensuite recevoir ses corrections par `copier update`.

Le cadrage est dans [`docs/cadrage.md`](docs/cadrage.md). Les pistes non engagées sont dans
[`docs/pistes.md`](docs/pistes.md), les constats dans [`docs/registre.md`](docs/registre.md).

## Créer un projet

Avec le script du poste :

```powershell
Nouveau-Projet.ps1
```

Ou directement avec Copier, sur une étiquette publiée :

```sh
copier copy --vcs-ref <étiquette> gh:EdouardZemb/modele-projet <dossier>
```

Puis, dans le dépôt créé : `git config core.hooksPath .githooks`.

## Mettre à jour un projet

Dans le projet, sur une branche :

```sh
copier update --vcs-ref <étiquette>
```

Les fichiers gérés par le modèle sont réécrits, les fichiers semés ne sont pas touchés. Un conflit
dans un fichier géré se résout en faveur du modèle.

## Contribuer

Le dépôt applique ses propres garde-fous : voir [`CLAUDE.md`](CLAUDE.md). Tests : `python -m pytest -q`,
style : `ruff check .`.
