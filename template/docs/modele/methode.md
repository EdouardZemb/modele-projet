# La méthode des projets nés du modèle

Ce fichier est **géré par le modèle** : il est réécrit par chaque `copier update`, et on ne le
modifie pas dans le projet. Un défaut se corrige dans `modele-projet`, pour tous les projets.

## Le cycle d'un lot

1. Une issue, avec une mini-spec : objectif, critères d'acceptation, hors périmètre. Le formulaire
   « Lot » la pose. Une milestone par étape.
2. Une PR de plan, qui ajoute le plan dans `.claude/plans/`.
3. Une ou plusieurs PR d'implémentation.
4. Une PR de revue finale.
5. Une PR de clôture : elle **supprime le plan** et reporte dans `CLAUDE.md` ou dans un ADR ce qui
   doit survivre.
6. L'étiquette `vX.Y.Z`, **avec l'accord d'Edouard**.

## Les outils

Les plans s'écrivent avec la compétence *superpowers* `writing-plans` et s'exécutent avec
`subagent-driven-development`.

Ces compétences **ne sont pas déclarées dans `.claude/settings.json`**. D'après la documentation de
Claude Code, un plugin déclaré par le projet ne s'installe ni dans une session à distance ni sur un
autre poste, et la déclaration doublerait l'installation du poste.

**Si *superpowers* manque** (c'est le cas dans une session à distance), la méthode ne change pas, seul
l'outillage disparaît :

- le plan s'écrit à la main dans `.claude/plans/`, avec les mêmes sections qu'un plan ordinaire :
  objectif, tâches, vérification de chaque tâche ;
- une seule tâche à la fois ;
- le test d'abord : il est écrit, il échoue, puis le code le fait passer ;
- une revue avant la fusion, par une autre session ou par Edouard.

## Les worktrees

Un sujet = un worktree, dans `<nom>.worktrees\<sujet>`, jamais à côté du dépôt.

## « Fini »

Tests verts, CI verte, `CLAUDE.md` et ADR à jour, déployé, vérifié là où l'application sert (sur un
téléphone Android pour une application mobile).

## Les commits

Conventional Commits, en français, avec un en-tête de 100 caractères au plus. Fusion par squash.
`git add` par chemins explicites, jamais `git add .` ni `git add -A`.

## Les questions groupées

Quand une session a plusieurs questions, elle les pose **en un seul bloc**, numérotées, chacune avec
sa réponse par défaut. « OK pour les défauts, sauf n » suffit comme réponse.

## Les invariants communs

Ils s'ajoutent à ceux du projet.

1. Aucun secret ne passe par la conversation. Les étapes 👤 le disent.
2. Aucune donnée personnelle réelle dans le dépôt, les tests ou le staging. Le jeu de données
   factice est **écrit**, pas dérivé de données réelles (M-0001).
3. Les sessions sont en lecture seule sur le serveur. Toute écriture passe par git ou par un script
   que lance Edouard.
4. Cible `serveur` : une migration, `compose.yml` et les `env/*.env` doivent laisser fonctionner
   l'image précédente. On ajoute avant d'enlever, et une variable nouvelle ne devient obligatoire
   qu'une version plus tard.
5. Un fichier géré par le modèle ne se modifie pas dans le projet : on corrige le modèle.

## Les garde-fous

Ils sont tous écrits en Python, le seul langage présent à la fois sur le poste, en CI et dans les
sessions à distance.

| Où | Quoi |
|---|---|
| hook git `pre-commit` | confidentialité du contenu indexé |
| hook git `commit-msg` | format Conventional Commits, confidentialité du message |
| hook git `pre-push` | refus d'envoyer sur la branche principale |
| hook Claude `PreToolUse` (outils `Bash` et `PowerShell`) | bloque `git push` vers la branche principale, tout force-push vers elle, `--no-verify`, toute modification de `core.hooksPath`, `gh pr merge` tant que les contrôles ne sont pas tous verts, et `gh pr merge --admin` |
| CI de base | gitleaks sur tout l'historique ; confidentialité du diff et du texte de la PR ; format des commits ; actions épinglées par SHA |
| règle de protection GitHub | PR obligatoire, contrôles requis, ni force-push ni suppression de la branche principale. Posée sur les dépôts publics |

Le secret `MOTIFS_INTERDITS` (la liste privée) est posé **deux fois** par dépôt : comme secret
Actions et comme secret Dependabot (`gh secret set MOTIFS_INTERDITS --app dependabot`). Les
exécutions lancées par Dependabot ne reçoivent pas les secrets Actions : sans le second, la
confidentialité échouerait sur chacune de ses PR. Une PR venue d'un fork ne peut pas passer ce
contrôle, faute de secret ; aucun fork n'est attendu, et une telle PR se rouvre depuis une branche
du dépôt.

`core.hooksPath` n'est pas versionné : il doit valoir `.githooks`, chemin **relatif**, dans chaque
clone et chaque worktree.

**Un refus se corrige, il ne se contourne jamais** : pas de `--no-verify`, pas de `core.hooksPath`
modifié.

## Les fichiers gérés par le modèle

- Les fichiers **gérés** sont réécrits par chaque `copier update`. On ne les modifie jamais dans le
  projet : une modification locale ressort en conflit à la mise à jour suivante, et c'est voulu.
- Les fichiers **semés** sont créés une fois, puis appartiennent au projet. `copier update` ne les
  touche plus.
- Un cas mixte, `.claude/settings.json` : le modèle y pose ses hooks, le projet y ajoute ses
  réglages. Un conflit s'y résout à la main, dans la PR de mise à jour.
- Changer de cible, c'est changer une réponse puis lancer `copier update`. Les fichiers gérés de
  l'ancienne cible disparaissent, ceux de la nouvelle arrivent. Les fichiers semés de l'ancienne
  cible restent : le projet les retire à la main dans la même PR.

Dans un fichier géré, un conflit de `copier update` se résout toujours en faveur du modèle. Les PR
Dependabot qui y montent une version d'action se fusionnent normalement.

## Le registre

`docs/registre.md` porte une ligne par constat :

| N° | Famille | Date | Constat | Motif | Prévention | Critère de sortie | État |
|---|---|---|---|---|---|---|---|

- **AM** : une piste d'amélioration, « il faudrait ».
- **LE** : une leçon, « on a cru que ».
- **EM** : un empêchement, « on n'a pas pu ».

Les numéros ne se réutilisent jamais. **Au 3e constat portant le même motif, on écrit une porte** (un
test, un hook, une vérification de CI), et la ligne le dit. La compétence `/consigner`
(`.claude/skills/consigner/SKILL.md`) écrit la ligne.

## Les familles de garde-fous de l'écosystème

Toute application de l'écosystème est tenue à cinq familles de garde-fous (M-0001, d'après
l'ADR-0010 de `creche-planner`, §4) :

1. les décisions écrites en ADR ;
2. une CI qui refuse de passer ;
3. le mutation testing des tests du domaine ;
4. la recherche de secrets ;
5. aucune donnée réelle dans le dépôt.

Arbitrage du 16/10 : le modèle outille **quatre** familles (ADR, CI qui refuse, recherche de
secrets, aucune donnée réelle). **La mutation reste une obligation du projet**, avec l'outil de sa
stack, dès que le projet a une logique de domaine. Un site sans logique de domaine n'est pas
concerné.
