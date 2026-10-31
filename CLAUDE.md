@template/docs/modele/methode.md

# modele-projet

Le modèle Copier d'où naissent les projets d'Edouard. Dépôt **public**. Il applique à lui-même les
garde-fous qu'il distribue : hooks git, garde de Claude, CI, règle de protection.

## État

Lot 1 fait le 17/10/2026 : le socle (cible `aucune`), étiqueté `v0.1.1`. Lot 6 fait le même jour :
`veille-emploi`, premier projet dont la branche principale n'est pas `main`.

Lot 2 fait le 27/10/2026 : la cible `serveur` (image publiée par étiquette, sonde, sauvegardes
chiffrées, tunnel commun), l'option `fusion` et les secrets refaits sur le poste, étiquetés
`v0.2.3` après la revue finale. Le dépôt privé `serveur` est né du modèle en cible `aucune` : il
porte la sonde de la machine. `ancrage` est passé en cible `serveur`, puis a retiré son ancien
tunnel en trois versions ; il lui reste un geste daté, noté dans son propre `CLAUDE.md`.

Lot 4 fait le 27/10/2026 : `pupitre` aligné en cible `aucune` (pupitre#7, sur la `v0.2.3`).

Lot 8 fait le 27/10/2026 : deux portes, étiquetées `v0.3.0`. Les signaux (#27) : au démarrage et
à la reprise d'une session, un hook `SessionStart` affiche ce qui est rouge sur GitHub, sans rien
de ce qu'écrit un fork ; la CI du socle l'exige. Les masqués (#36) : le `pre-commit` d'un
alignement ou d'une mise à jour refuse un fichier du modèle que le `.gitignore` du projet masque.

Lot 9 fait le 28/10/2026 : le ménage des images (#19), étiqueté `v0.4.0`. En cible `serveur`,
`deployer.sh` lance `deploiement/nettoyer-images.sh` après chaque déploiement ou retour arrière
réussi. Le script retire les images du projet que ni l'état des deux environnements, ni un
conteneur, ni la marge des 3 plus récentes ne gardent, sans jamais `-f` ; une surprise annule
tout. Une épreuve sur un vrai Docker, dans la CI, le prouve. Le hook `SessionStart` a 30 s (#45).

Lot 10 fait le 28/10/2026 : la garde du dossier de données (#49), étiquetée `v0.5.0`. En cible
`serveur` avec sauvegardes, `deployer.sh` refuse un déploiement ou un retour arrière quand une
version est déployée et que le dossier de données est vide, ou n'est plus celui du dernier succès.
Ce chemin, sous sa forme canonique, est dans le fichier d'état `donnees` ; pour un état d'avant la
`v0.5.0`, celui de `compose.env` en tient lieu. Le refus alerte sans rien changer ; le geste 👤
`--donnees-neuves` lève la garde pour un déploiement.

Lot 11 fait le 29/10/2026 : la porte par nature et le gabarit de données (#55), première étape de
M-0006 (« Le code et les données »), étiquetée `v0.6.0`.
- **La réponse `nature`** (`code` ou `donnees`) remplace `visibilite`. Dans un dépôt de code, tout
  constat de la porte refuse, quelle que soit sa visibilité ; dans un dépôt de données, elle avertit
  sur ce qui identifie et refuse les secrets.
- **En CI**, un dépôt public est toujours de code. Un dépôt privé prend la nature écrite sur sa
  branche par défaut (`refs/remotes/origin/<branche>`), jamais celle de la PR.
- **Chaque lundi**, `modele-historique.yml` relit tout l'historique d'un dépôt de code avec la porte
  (`--historique`), et écarte les couples (commit, chemin) de `.github/constats-acceptes.txt`. La
  visibilité et la branche par défaut s'y lisent par l'API : un déclenchement planifié peut ne pas
  porter `github.event.repository` (LE-33).
- **La cible `donnees`** rend le dépôt privé `<nom>-donnees` : le socle, la méthode, `config/` et
  `contenu/` documentés, rien de l'application.
- **Le domaine n'a plus de défaut.** Edouard a étendu sa liste privée ; le dépôt modèle passe sa
  porte dessus, avec trois constats anciens acceptés.

Lot 12 fait le 31/10/2026 : le contrat de `/config` et la chaîne à deux dépôts (#64), seconde étape
de M-0006 (§ 5 et 6), étiquetée `v0.7.0`. En cible `serveur` :
- **Les deux modes de la chaîne** suivent la nature, sans réponse de plus. À deux dépôts, pour un
  dépôt de code né après M-0006, l'instance vit à la racine du dépôt de données `<nom>-donnees`
  (`env/`, `secrets/`, `.sops.yaml`, `cles/`, `config/`, `contenu/`) ; le staging suit une branche
  des données, la prod leur plus haute étiquette. À un dépôt, pour un dépôt de nature `donnees`
  jusqu'à sa scission, tout reste dans le même dépôt, l'instance sous `instance/config/` et
  `instance/contenu/`, et la prod prend le commit de la plus haute `vX.Y.Z`.
- **L'état déployé est un couple**, l'image et le commit de données (`-` sans données montées) :
  `deploye` et `precedent` gagnent un troisième champ, `echec` devient `<image> <commit>`. Un état
  d'avant se relit, et les scripts d'avant relisent le nouveau. Le retour arrière revient à un
  couple entier, et l'instantané de `/donnees` note à côté de lui le couple en service (`.couple`).
- **L'instantané des données**, extrait du commit sous l'état et figé, est monté en lecture seule
  sur `/config` et `/contenu`, jamais le clone ; le staging ne monte jamais `/config`. Le ménage
  retire, par environnement, ceux que ni l'état ni la marge des 3 plus récents ne gardent.
- **`VERIFIER_CONFIG` et `VERIFIER_CONTENU`**, déclarées dans `deploiement/projet.env`, vérifient
  les données dans un conteneur jetable de l'image visée, avant tout changement, par paires avec
  leurs dossiers ; la santé dit `configuration` (`exemple` ou `montee`). La CI du code les lance
  sur `exemple/` et `exemple-contenu/`, et, à un dépôt, sur `instance/` (LE-37). Un projet qui
  n'en déclare aucune ne voit aucun changement.
- **Les étiquettes de données** `donnees-AAAA.MM.JJ.n` sont à Edouard, comme les `vX.Y.Z` : le
  garde refuse leur envoi.
- **La CI des données**, `modele-donnees.yml`, rendue pour `cible: donnees` avec
  `cible_code: serveur`, contrôle les secrets contre le `.cles` du dépôt de code, et les données
  contre l'image de la prod et `:main`.
- **La réponse `compte`** (`EdouardZemb` par défaut) donne `ghcr.io/<compte>/<nom>`. L'instance
  n'est posée que là où elle vit : un dépôt de code n'a ni domaine, ni bloc de ports, ni clé du
  parc, et la porte y refuse l'instance par ses chemins. Les clés sortent de l'arbre du modèle.
- **Une épreuve sur un vrai Docker**, dans la CI du modèle, déploie un couple, change son seul
  commit de données, fait refuser une configuration, revient en arrière et fait le ménage.

Versions des projets au 31/10, inchangées depuis le 29/10 : `ancrage`, `serveur` et
`veille-emploi` en `v0.3.0` (`veille-emploi` en cible `serveur`, avec `fusion=session`), `pupitre`
en `v0.2.3`. Chacun monte directement en `v0.7.0` par `copier update`, au choix d'Edouard, après
le 01/11 pour le quota d'Actions : le message de la `v0.7.0` remplace celui de la `v0.6.0`. Tous
sont privés : leur nature se déduit seule en `donnees`, sans `--data`, et `ancrage` comme
`veille-emploi` déploient à un dépôt jusqu'à leur scission. Après la mise à jour, un
`gh workflow run modele-historique.yml` doit dire « historique relu par gitleaks seul ». `ancrage`
fait l'essai du ménage (lot 9). Avant la mise à jour d'`ancrage` et de `veille-emploi`, une lecture
sur le serveur vérifie que leur dossier de données n'est vide dans aucun des deux environnements.
`veille-emploi` ne déclare `VERIFIER_CONFIG`, et n'étiquette la prod de veille-emploi#22, qu'une
fois la `v0.7.0` en service dans ses deux environnements.

Prochain, au choix d'Edouard :
- le lot 13 : la naissance d'un projet en deux dépôts, par le script de création du poste (geste
  👤) ; dans `serveur`, la déclaration des deux dépôts d'un projet et la création des clones des
  données par sa sonde, avec la clé de déploiement du dépôt de données ; puis le premier essai réel
  sur le serveur (spec du lot 12, § 12) ;
- la scission de `veille-emploi`, puis celle d'`ancrage`, chacune dans son propre lot ;
- le lot 3 (la cible `statique`) ;
- la porte due par LE-37, au 3e constat du motif « écart à la spec mal pesé » : sa forme revient à
  Edouard, et le registre en propose une ;
- le retrait du repli `VISIBILITE = "prive"` de la porte, qui reste tant que la branche par défaut
  de chaque projet ne porte pas `NATURE`. La `v0.7.0` le garde : `pupitre` y saute depuis la
  `v0.2.3`, et la PR de sa mise à jour est lue en `donnees`.

Le cadrage est dans `docs/cadrage.md` ; ce que les lots ont appris, dans `docs/registre.md`.

## Commandes

- `python -m pytest -q` : les tests (environ 5 minutes sous Windows). `tests/test_mecanique.py`
  lance les tests bats d'un projet rendu dans une image Docker : il lui faut Docker avec un serveur
  Linux, et il saute sans lui.
- `ruff check .` : le style.
- `copier copy --vcs-ref <étiquette> gh:EdouardZemb/modele-projet <dossier>` : créer un projet.
- `copier update` : mettre à jour un projet né du modèle (à lancer dans ce projet, pas ici).
- `git config core.hooksPath .githooks` : à poser dans chaque clone et chaque worktree.

## Ce qui fait foi

- `docs/cadrage.md` : les décisions, le contrat, les cibles, les lots.
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
