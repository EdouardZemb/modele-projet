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
| hook git `pre-commit` | confidentialité du contenu indexé, fichiers UTF-16 compris ; un autre binaire est signalé « non examiné ». La porte refuse dans un dépôt public et avertit sans refuser dans un dépôt privé (voir plus bas), au hook comme en CI |
| hook git `commit-msg` | format Conventional Commits, confidentialité du message |
| hook git `pre-push` | refus d'envoyer sur la branche principale |
| hook Claude `PreToolUse` (outils `Bash`, `PowerShell`, `Monitor`, et tout outil MCP qui porte une commande) | bloque `git push` vers la branche principale, tout force-push vers elle, `--no-verify`, toute modification de `core.hooksPath` sauf la réparation `git config core.hooksPath .githooks` (variables `GIT_CONFIG_*` comprises), `gh pr merge` tant que les contrôles ne sont pas tous verts, `gh pr merge --admin`, les alias et extensions de `gh`, ce qui affiche le jeton de `gh` (`gh auth token`, `gh auth status --show-token`), et l'effacement, le déplacement ou le renommage de `.githooks` et de `scripts/modele` (`rm`, `mv`, `Remove-Item`, `git rm`…). Il lit aussi les substitutions `$(…)`, même entre guillemets, et les enveloppes (`timeout`, `Start-Process`, `Invoke-Expression`…) |
| CI de base | gitleaks examine les commits de chaque PR et de chaque envoi, et tout l'historique chaque semaine et à la demande (`modele-historique.yml`) ; confidentialité du diff, des messages de commit et du texte de la PR ; format des commits ; le garde de Claude toujours branché dans `.claude/settings.json` ; actions épinglées par SHA |
| Dependabot | chaque lundi, les versions des actions épinglées (`.github/dependabot.yml`), après trois jours de recul |
| règle de protection GitHub | tout commit qui arrive sur la branche principale est la tête d'une PR dont les contrôles requis sont verts ; un envoi direct de cette tête est accepté et marque la PR fusionnée, sans squash. Côté agent, c'est le refus de pousser vers la branche principale par le garde qui ferme ce chemin. Ni force-push ni suppression de la branche principale. Posée sur les dépôts publics |

**Dépôt public, dépôt privé.** La visibilité est une réponse du modèle (`visibilite` dans
`.copier-answers.yml`, `VISIBILITE` dans `scripts/modele/reglages.py`). Dans un dépôt **public**, un
constat de la porte de confidentialité refuse, à chaque hook comme en CI. Dans un dépôt **privé**,
qui peut nommer son propre serveur, elle **avertit sans refuser** : chaque constat s'affiche, avec
son emplacement et le nom du motif, jamais la valeur, et le code de retour vaut 0. Les erreurs
d'usage et l'absence de la liste privée exigée refusent toujours ; gitleaks bloque toujours les
secrets. Un dépôt privé n'a pas de règle de protection : le garde de Claude y est la seule serrure
côté agent, et la CI du socle le seul filet.

**Avant de passer un dépôt privé en public**, trois étapes obligatoires, dans cet ordre :

1. `python scripts/modele/confidentialite.py --exiger-prives --fichiers <la liste de git ls-files>`
   est propre ;
2. un passage complet de `modele-historique.yml` est vert ;
3. `copier update` avec `visibilite=public`, puis la règle de protection.

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
- **Les chemins gérés sont exclus des formateurs et des linters du projet** (Prettier, biome,
  ruff…) : `.githooks/`, `scripts/modele/`, `docs/modele/`, `.github/modele/`,
  `.github/workflows/modele-*.yml`, `.claude/skills/consigner/`. Un formateur qui les réécrirait
  ferait d'une modification locale un conflit à chaque `copier update`.
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
