@template/docs/modele/methode.md

# modele-projet

Le modèle Copier d'où naissent les projets d'Edouard. Dépôt **public**. Il applique à lui-même les
garde-fous qu'il distribue : hooks git, garde de Claude, CI, règle de protection.

## État

Version en service : `v0.14.0`, publiée le 20/11/2026. Lot en cours : le lot 20, le second temps
de la documentation (#157).

Les projets nés du modèle, d'après le relevé du 22/11/2026 :

| Projet | Version | Cible | Nature |
|---|---|---|---|
| `ancrage` | `v0.14.0` | `serveur` | code |
| `ancrage-donnees` | `v0.12.0` | `donnees`, avec `cible_code: serveur` | données |
| `pilote` | `v0.14.0` | `aucune` | code |
| `pupitre` | `v0.12.0` | `aucune` | code |
| `pupitre-donnees` | `v0.12.0` | `aucune` | données |
| `serveur` | `v0.12.0` | `aucune` | données |
| `veille-emploi` | `v0.14.0` | `serveur` | code |
| `veille-emploi-donnees` | `v0.12.0` | `donnees`, avec `cible_code: serveur` | données |

L'histoire du modèle, lot par lot et version par version, est dans
[le journal des versions](CHANGELOG.md). À la clôture d'un lot, son paragraphe y va, sous sa
version, en tête, avec celui des versions des projets quand il vient ; l'« État » se réécrit au
présent, en 40 lignes non vides au plus, que le démarrage d'une session tient.

Prochain, au choix d'Edouard :
- le lot 3 (la cible `statique`) ;
- le lot 5 (`partition` aligné en cible `aucune`) ;
- le lot 7 (`creche-planner` aligné en cible `aucune`) ;
- le workflow `publier`, qui ferait publier Edouard depuis son téléphone : sa piste a pour
  déclencheur un lot choisi par Edouard ;
- un lot sur les motifs des constats que les portes laissent ouverts : la piste « Les constats
  que les portes laissent ouverts ».

Le cadrage est dans `docs/cadrage.md` ; ce que les lots ont appris, dans `docs/registre.md`.

## Commandes

- `python -m pytest -q` : les tests, environ 6 à 8 minutes sous Ubuntu et 20 à 33 sous Windows,
  mesurées en CI, sans `tests/test_mecanique.py`, sur la PR #118, mais 45 sous Windows sur #135. `tests/test_mecanique.py` lance
  les tests bats d'un projet rendu dans une image Docker : il lui faut Docker avec un serveur Linux,
  et il saute sans lui.
- `ruff check .` : le style.
- `gh run rerun <id> --job <databaseId>` : relancer le seul job de la CI coupé à son délai
  (`timeout-minutes`), le `databaseId` lu par `gh run view <id> --json jobs` (le numéro de l'URL du
  job ne convient pas, dit `gh run rerun --help`), après avoir vérifié que l'étape coupée est
  « cancelled », et non en échec : un échec se lit et se corrige, il ne se relance pas. La
  documentation de GitHub dit seulement qu'il annule un job à son délai ; l'étape coupée était
  « cancelled » sur le job coupé du 31/10 (LE-40). Une exception à « un échec ne se relance pas »,
  la panne d'un service tiers : l'échec est lu dans le journal, sa cause est hors du dépôt (un 504
  ou un 503 de GitHub Releases, au lot 15), et le service répond de nouveau (la même adresse rend
  200 depuis le poste) ; on relance alors le seul job par `--job`, ou `--failed` quand tous les
  jobs en échec de l'exécution ont cette cause. Jamais pour `texte-pr`, qui se relit par une
  retouche du texte de la PR (`methode.md`, « Ne jamais relancer `texte-pr` »).
- `gh run view <id> --attempt <n>` : la revue finale de chaque lot relève les avertissements de
  durée des exécutions du lot, dans les annotations de chaque tentative, n allant de 1 au champ
  `attempt` de l'exécution (`gh run view <id> --json attempt`). Sans `--attempt`, `gh run view` ne
  montre que celles de la dernière tentative : un job qu'elle n'a pas relancé n'y porte aucune
  annotation (éprouvé le 08/11 avec gh 2.93.0, sur l'exécution 42467400054, à trois tentatives).
  Chaque job qui porte l'étape « Durée du job » avertit au-delà des trois quarts de son délai, et
  personne d'autre ne lit un avertissement sur une exécution verte (`SessionStart` n'affiche que
  le rouge).
- `poste\Tester-Nouveau-Projet.ps1 -SansPoste -SourceModele <ce clone>` : le test du script de
  création, sans `gh`, sans la liste privée ni l'index réel. Il rend le modèle au `HEAD` du clone,
  changements non validés et fichiers non suivis compris : Copier les ajoute, avec un
  `DirtyLocalWarning`. Valider avant, pour éprouver la tête qui part. Sans `-SansPoste`, il lance
  aussi le script à blanc, sur le poste d'Edouard. `tests/test_poste.py` le lance, et compare les
  bits d'exécution du premier commit à ceux du modèle : sous Windows seulement ; ailleurs, seul le
  contrôle du BOM tourne.
- `python -B template/scripts/modele/plan.py` : le contrôle d'un plan neuf, ses sections et sa
  clôture (`methode.md`, « Les outils »), par cette commande, sur une seule ligne :

  ```sh
  python -B template/scripts/modele/plan.py --racine . --depot serveur=../serveur --neuf --cloture cadrage --cloture "À relire" --cloture pistes --cloture relevé <plan>
  ```

  Il faut une option `--depot <dépôt>=../<dépôt>` par dépôt que le plan cite ; un plan accepté se
  revérifie sans `--neuf`. Les plans du modèle vivent dans `Documents\00-boite-de-reception\`,
  hors du dépôt : l'étape « Les plans » de la CI n'en trouve aucun ici. La session lance cette
  commande depuis le clone principal, avant de soumettre un plan à Edouard et après chaque
  correction. Dans ce dépôt, une ligne d'« Effets cherchés » dont le lieu est un projet cite le
  relevé (`poste/releve.py`) dans son troisième morceau. La clôture d'un plan du modèle ne
  supprime aucun plan, et le dit (« le plan, hors du dépôt, n'est pas supprimé : son en-tête est
  mis à jour ») : le geste « le plan supprimé » y trouve le mot qu'il cherche.
- `python -B template/scripts/modele/texte_pr.py --fermetures "$fermetures"` : le contrôle du texte
  d'une PR avant de l'ouvrir (`methode.md`, « Éprouver le texte avant d'ouvrir la PR »). Ce dépôt
  n'a pas de `scripts/` à sa racine : le bloc de la méthode s'y lance avec ce chemin, depuis la
  racine du clone ou du worktree, sous Git Bash, une fois la branche envoyée, le corps dans un
  fichier UTF-8 sans BOM, hors du dépôt :

  ```sh
  corps='<fichier du corps>'
  fermetures="$(mktemp)"
  printf '%s' '{"data":{"repository":{"pullRequest":{"closingIssuesReferences":{"totalCount":0,"nodes":[]}}}}}' > "$fermetures"
  CORPS="$(cat "$corps")" AUTEUR="$(gh api user --jq .login)" TETE="$(git rev-parse HEAD)" \
    python -B template/scripts/modele/texte_pr.py --fermetures "$fermetures"
  ```

  Avec `"totalCount":1` à la troisième ligne, elle éprouve la tête relue de la PR de clôture. Elle
  n'éprouve ni le format du titre ni la confidentialité, que `texte-pr` contrôle aussi.
- `python -B poste/releve.py [--depuis <étiquette>] [--prs N]` : le relevé des projets nés du
  modèle, depuis la racine du clone, sous Git Bash, `gh` connecté. Il lit GitHub par `gh api`, en
  lecture seule, dépôts privés compris, ce que la CI ne peut pas : il tourne sur le poste, par la
  session. Il lance sur ce qu'il lit les scripts du modèle de deux versions, celle de chaque projet
  et la tête du clone (son `HEAD`). Ses deux rôles : l'inventaire, avant une spec ou un plan,
  quand la tête ne porte pas encore le changement (les règles des projets, leurs plans en cours,
  leurs fichiers gérés modifiés) ; la mesure de l'effet de ce que la tête change. Ses trois
  moments : avant de soumettre une spec ou un plan, pour en écrire les « Effets cherchés » ; à la
  revue finale, dont il est une lentille ; à la clôture, dont la PR cite sa sortie. Une PR n'en
  cite que des comptes et des noms de dépôts publics, après la porte de confidentialité : ni les
  noms des plans ni les numéros de PR des dépôts privés. Il rend 1 quand quelque chose est à lire
  (un verdict qui change, une PR ouverte qui ajoute un plan, un contrôle géré absent d'une règle,
  un fichier géré modifié dans un projet), ou que quelque chose n'est pas relevé (une erreur de
  l'API, une version absente du clone : `git fetch --tags`, un script du modèle qui plante, le
  dossier temporaire non retiré), 0 sinon. Il rend 64 pour une erreur d'usage : `gh` absent ou sans
  accès (un 401, ou `gh` qui sort par 4, jamais connecté), un dossier qui n'est pas un clone du
  modèle qu'il sait lire. Les plans en cours qui « refuseraient s'ils étaient neufs » sont une
  information : ils ne rendent pas le code 1, comme les contrôles propres d'une règle, et comme la
  ligne « aucun projet né du modèle relevé », d'un relevé qui n'en trouve aucun, par exemple sous un
  `--compte` qui n'est pas celui de `gh` : il rend alors 0. Parmi les fichiers gérés, seuls les
  dossiers exclus des formateurs sont comparés, pas le gabarit de PR ni les autres fichiers gérés
  hors d'eux. Par défaut, il compare ceux que le modèle change entre la version de chaque projet et
  la tête, et un projet à la version de la tête n'en montre aucun. `--depuis <ancienne étiquette>`
  ouvre cet intervalle pour tous les projets, chacun comparé au modèle à sa version : il compare les
  fichiers gérés que le modèle a changés depuis cette étiquette, et un fichier géré que le modèle
  n'a pas changé depuis elle n'est pas comparé, quelle que soit l'étiquette. Ce n'est donc pas un
  inventaire complet des fichiers gérés. `--prs N`, de 1 à 100, dit combien de PR récentes passent
  par les deux `texte_pr.py` (50 par défaut). `tests/test_releve.py` l'éprouve contre un faux `gh`.
- `copier copy --vcs-ref <étiquette> gh:EdouardZemb/modele-projet <dossier>` : créer un projet.
- `copier update` : mettre à jour un projet né du modèle (à lancer dans ce projet, pas ici).
- `git config core.hooksPath .githooks` : à poser dans chaque clone et chaque worktree.

## Ce qui fait foi

- `docs/cadrage.md` : les décisions, le contrat, les cibles, les lots.
- [Le journal des versions](CHANGELOG.md) : l'histoire du modèle, version par version.
- Les ADR hérités, dans `template/docs/modele/decisions/`.
- `template/docs/modele/methode.md` : la méthode distribuée aux projets.
- `docs/aligner.md` : la liste de contrôle « Aligner un projet existant », à suivre case par case
  dans chaque lot d'alignement.

## Invariants

1. Aucun fichier ne nomme le serveur, son utilisateur ni une adresse.
2. Toute modification de `template/` vient avec son test.
3. Un fichier qui contient `${{` n'est pas `.jinja`, sauf si chaque expression y est enveloppée
   dans `{% raw %}`.
4. `template/docs/modele/methode.md` ne contient aucune syntaxe Jinja.

## Exploitation

Les versions du modèle sont des étiquettes `vX.Y.Z`, posées avec l'accord d'Edouard.
