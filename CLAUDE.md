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

Versions des projets au 28/10 : `ancrage`, `serveur` et `veille-emploi` en `v0.3.0`
(`veille-emploi` en cible `serveur`, avec `fusion=session`), `pupitre` en `v0.2.3`. Chacun monte
par `copier update`, au choix d'Edouard ; `ancrage` passe directement en `v0.5.0`, avec l'essai
du ménage (lot 9), une fois le quota d'Actions remis à zéro. Avant, une lecture sur le serveur
vérifie que son dossier de données n'est vide dans aucun des deux environnements. Prochain, au
choix d'Edouard : le lot 3 (la cible `statique`) ou un autre lot. Le cadrage est dans `docs/cadrage.md` ; ce que les lots ont
appris, dans `docs/registre.md`.

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
