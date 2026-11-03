# modele-projet

Le modèle d'où naît chaque projet d'Edouard : la méthode, les garde-fous (hooks git, garde de Claude,
CI, protection de branche) et, pour la cible `serveur`, le déploiement par étiquette, la sonde et les
sauvegardes chiffrées. C'est un modèle [Copier](https://copier.readthedocs.io/) :
un projet né du modèle peut ensuite recevoir ses corrections par `copier update`.

Le cadrage est dans [`docs/cadrage.md`](docs/cadrage.md). Les pistes non engagées sont dans
[`docs/pistes.md`](docs/pistes.md), les constats dans [`docs/registre.md`](docs/registre.md).

## Créer un projet

Avec le script du poste, `poste/Nouveau-Projet.ps1`, qu'Edouard seul lance pour de vrai :

```powershell
poste\Nouveau-Projet.ps1 -Nom <nom> -Description "<ce que fait le projet>"
poste\Nouveau-Projet.ps1 -Nom <nom> -Description "<…>" -Cible serveur -Domaine <domaine> -CleServeur <age1…> -CleHorsLigne <age1…>
```

`-Nom` et `-Description` sont obligatoires. `-Cible serveur` crée deux dépôts : le code, et ses
données dans `<nom>-donnees`, privé (M-0006) ; la mise en service suit ensuite
`docs/exploitation.md` du projet. `-ABlanc` décrit chaque étape et affiche sa commande, sans rien
créer. L'usage complet est dans l'en-tête du script.

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
dans un fichier géré se résout en faveur du modèle. Ensuite, sous les chemins gérés,
`git status --short --ignored` ne doit montrer en `!!` que des caches (`__pycache__/`) : un fichier
géré que le `.gitignore` du projet masque manquerait au commit (LE-23). Si on oublie ce contrôle,
le `pre-commit` refuse le commit de la mise à jour et nomme le fichier masqué.

## Aligner un projet existant

Un dépôt né avant le modèle le reçoit par `copier copy`, puis quelques reports à la main : la liste
de contrôle est dans [`docs/aligner.md`](docs/aligner.md).

## Contribuer

Le dépôt applique ses propres garde-fous : voir [`CLAUDE.md`](CLAUDE.md). Tests : `python -m pytest -q`,
style : `ruff check .`.
