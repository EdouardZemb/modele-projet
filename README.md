# modele-projet

Le modèle [Copier](https://copier.readthedocs.io/) d'où naissent les projets d'Edouard, pour lui et
pour les sessions de Claude qui y travaillent.

## Pourquoi

Chaque projet d'Edouard part de la même méthode et des mêmes garde-fous, au lieu de les recopier et
de les voir diverger : hooks git, garde de Claude, CI, protection de branche et, en cible `serveur`,
le déploiement par étiquette, la sonde et les sauvegardes chiffrées. Le modèle les rend à la
naissance d'un projet, puis les corrige dans chaque projet par `copier update`. Il applique à
lui-même les garde-fous qu'il distribue. Il ne porte aucune application, et aucun de ses fichiers ne
nomme un serveur ni une adresse.

L'état du modèle est dans [CLAUDE.md](CLAUDE.md#état), les versions dans [les publications](https://github.com/EdouardZemb/modele-projet/releases).

## Démarrer

Les commandes de ce dépôt, ses tests compris, sont dans [CLAUDE.md](CLAUDE.md#commandes).

### Créer un projet

Avec le script du poste, `poste/Nouveau-Projet.ps1`, qu'Edouard seul lance pour de vrai :

```powershell
poste\Nouveau-Projet.ps1 -Nom <nom> -Description "<ce qu'est le projet, et pour qui>"
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

Les réponses à choix, que Copier enregistre dans `.copier-answers.yml` :

- `cible` : ce que le modèle rend, `aucune` (le socle seul), `serveur` (le socle, le déploiement, la sonde et les sauvegardes) ou `donnees` (le dépôt de données `<nom>-donnees` d'un projet) ;
- `cible_code` : en cible `donnees`, la cible du dépôt de code dont il porte les données, `aucune` ou `serveur` (il porte alors aussi l'instance) ;
- `nature` : `code` pour tout projet né après M-0006, `donnees` pour un dépôt de données, ou pour un dépôt d'avant M-0006 jusqu'à sa scission ;
- `fusion` : qui fusionne une PR une fois tous ses contrôles verts, `session` (la session) ou `edouard` (Edouard).

### Mettre à jour un projet

Dans le projet, sur une branche :

```sh
copier update --vcs-ref <étiquette>
```

Les fichiers gérés par le modèle sont réécrits, les fichiers semés ne sont pas touchés. Un conflit
dans un fichier géré se résout en faveur du modèle. Ensuite, sous les chemins gérés,
`git status --short --ignored` ne doit montrer en `!!` que des caches (`__pycache__/`) : un fichier
géré que le `.gitignore` du projet masque manquerait au commit (LE-23). Si on oublie ce contrôle,
le `pre-commit` refuse le commit de la mise à jour et nomme le fichier masqué.

### Aligner un projet existant

Un dépôt né avant le modèle le reçoit par `copier copy`, puis quelques reports à la main : la liste
de contrôle est dans [`docs/aligner.md`](docs/aligner.md).

## Où lire quoi

| Document | À lire quand |
|---|---|
| [CLAUDE.md](CLAUDE.md) | avant de travailler ici |
| [Le cadrage](docs/cadrage.md) | pour les décisions, le contrat, les cibles |
| [La méthode](template/docs/modele/methode.md) | pour la façon de travailler, distribuée aux projets |
| [Les décisions héritées](template/docs/modele/decisions/) | pour ce que les projets héritent du modèle, et pourquoi |
| [Documenter un projet](template/docs/modele/documentation.md) | pour écrire ou relire le README d'un projet |
| [Aligner un projet](docs/aligner.md) | pour aligner un projet existant, case par case |
| [Les pistes](docs/pistes.md) | pour ce qui est noté sans être engagé |
| [Le registre](docs/registre.md) | pour ce que les lots ont appris |

## Contribuer

Projet personnel : aucune contribution n'est attendue.

## Licence

[MIT](LICENSE)
