# Aligner un projet existant sur le modèle

La liste de contrôle des lots d'alignement : un dépôt qui existait avant le modèle reçoit le socle
par `copier copy`, puis quelques reports à la main. Elle est tirée de l'alignement d'`ancrage`
(lot 1) et de la revue finale du lot 1, puis corrigée par celui de `veille-emploi` (lot 6). Les
étapes 👤 sont à Edouard.

Chaque case se coche dans la PR d'alignement. Une case qui ne s'applique pas au projet le dit.

## 1. Préparer

- [ ] Aucune PR ouverte ne touche `CLAUDE.md` ni `.github/workflows/ci.yml` (`gh pr list --state open`).
      Sinon, s'arrêter : une autre session travaille sur le dépôt.
- [ ] La CI de la branche principale est verte (`gh run list --branch <branche principale> --limit 5`).
      Sinon, comprendre le rouge avant d'aligner : il serait pris pour un effet de l'alignement
      (LE-14).
- [ ] Un worktree neuf, `<dépôt>.worktrees\modele-alignement`, sur une branche partie de
      `origin/<branche principale>`.

## 2. Rendre le modèle

- [ ] Dans le worktree, sur une étiquette publiée :

  ```sh
  copier copy --defaults --vcs-ref <étiquette> --data nom=<nom> --data "description=<une phrase>" \
    --data visibilite=<public|prive> --data cible=aucune --data branche_principale=<branche> \
    gh:EdouardZemb/modele-projet .
  ```

- [ ] **Rien d'existant n'a bougé** : `git diff --name-only` est vide, et `git status --short` ne
      montre que des fichiers nouveaux (`??`). Copier ignore les fichiers semés déjà présents
      (`README.md`, `CLAUDE.md`, `.gitignore`…) : il les signale en conflit, sans les toucher. Si un
      fichier existant a changé, s'arrêter.

## 3. Les reports à la main

- [ ] **`CLAUDE.md`** : la ligne 1 devient `@docs/modele/methode.md`, suivie d'une ligne vide. Retirer
      ce que `methode.md` couvre désormais (le cycle d'un lot, « Fini », les commits, les questions
      groupées) ; garder ce qui est propre au projet.
- [ ] **`.github/workflows/ci.yml`** :
  - ajouter le job `socle` : `uses: ./.github/workflows/modele-socle.yml`, `secrets: inherit`,
    `permissions: {contents: read, pull-requests: read}` ;
  - retirer l'ancien job qu'il remplace (un gitleaks, par exemple) et renommer en `socle` chaque
    `needs:` qui le citait ;
  - `pull_request: types: [opened, synchronize, reopened, edited]`, pour qu'un titre ou un corps de
    PR modifié soit réexaminé.
- [ ] **`.gitignore`** : `.claude/settings.local.json` et `__pycache__/`, s'ils n'y sont pas.
- [ ] **`.dockerignore`**, s'il existe : `.githooks` et `scripts/modele`, pour qu'un `COPY` ne les
      embarque pas dans l'image.
- [ ] **Les formateurs et les linters du projet** (Prettier, biome, ruff…) excluent les chemins
      gérés : `.githooks/`, `scripts/modele/`, `docs/modele/`, `.github/modele/`,
      `.github/workflows/modele-*.yml`, `.claude/skills/consigner/` (`methode.md`, « Les fichiers
      gérés par le modèle »).

## 4. Brancher les hooks

- [ ] `git update-index --add --chmod=+x .githooks/pre-commit .githooks/commit-msg .githooks/pre-push`
      (sous Windows, `git add` enregistre `100644`, et Linux n'exécuterait pas les hooks).
- [ ] `git config core.hooksPath .githooks` dans le clone principal.
- [ ] Si `git config --get extensions.worktreeConfig` vaut `true` : `git config --worktree
      core.hooksPath .githooks` dans **chaque** worktree, chemin relatif.

## 5. Vérifier, puis commiter

- [ ] Indexer par chemins explicites (`git add -- <chemins>`) les fichiers nouveaux que
      `git status --short` a listés au §2, et ceux retouchés au §3. Jamais tout d'un coup
      (`methode.md`, « Les commits ») : un cache ou un dossier de travail non ignoré entrerait dans
      le commit (LE-7). Puis `python scripts/modele/confidentialite.py --exiger-prives --index` rend
      0 (dans un dépôt privé : aucun avertissement qui ne soit pas attendu). C'est le mode du hook
      `pre-commit`, sur ce qui est indexé. Pas `--diff` avant le commit : il compare
      `<base>...HEAD`, n'examine encore rien, et la porte se tait quand elle ne trouve rien (LE-15).
- [ ] Le lint, les types et les tests du projet passent.
- [ ] Commit `chore: aligne <nom> sur le socle de modele-projet <étiquette>`. Les hooks tournent sur
      ce commit : c'est leur premier passage réel. Jamais `--no-verify`.

## 6. Les réglages du dépôt (👤)

- [ ] 👤 **Le secret, posé deux fois**, pour Actions et pour Dependabot (sous Windows, par
      `cmd /c`, dont la redirection transmet les octets tels quels) :

  ```sh
  gh secret set MOTIFS_INTERDITS --repo <dépôt> < <liste privée>
  gh secret set MOTIFS_INTERDITS --repo <dépôt> --app dependabot < <liste privée>
  ```

- [ ] 👤 **Les réglages de fusion** : squash seul, branche supprimée après fusion, et un commit de
      squash fait du titre et du corps de la PR (que la CI examine), pas des messages des commits :

  ```sh
  gh repo edit <dépôt> --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false --delete-branch-on-merge
  gh api -X PATCH repos/<dépôt> -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY
  ```

- [ ] 👤 **La règle de protection**, si le dépôt est public, après le premier envoi :
      `gh api -X POST repos/<dépôt>/rulesets --input .github/modele/ruleset-main.json`.
      Un dépôt privé n'en a pas : le garde de Claude y est la seule serrure côté agent.

## 7. PR et CI

- [ ] Envoyer la branche, ouvrir la PR avec le modèle de PR.
- [ ] `gh pr checks` entièrement vert : `socle / secrets`, `socle / confidentialite`, et les
      contrôles propres au projet.
- [ ] Fusion en squash, puis le déploiement éventuel vérifié là où l'application sert.
- [ ] **L'historique complet**, une fois après la fusion : lancer `modele-historique.yml` à la main
      (`gh workflow run modele-historique.yml`, ou l'onglet Actions). gitleaks n'examine sinon que
      les commits de chaque PR et de chaque envoi, et l'historique antérieur à l'alignement
      attendrait le passage du lundi. Un faux positif ancien s'écarte par `.gitleaksignore`, avec
      son empreinte (`<commit>:<fichier>:<règle>:<ligne>`) et un commentaire qui dit pourquoi,
      jamais en réécrivant l'historique.

## 8. Les sondes négatives, isolées

Une sonde ne prouve rien si un autre mécanisme refuse à la place de celui qu'elle vise.

- [ ] **`pre-push`** : depuis une branche **en avance rapide** sur la branche principale,
      `git push --dry-run origin HEAD:<branche principale>` doit être refusé par `pre-push`. Sans
      avance rapide, git refuse lui-même, avant d'appeler le hook.
- [ ] **`commit-msg`** : `git commit --allow-empty -m "sonde"` est refusé.
- [ ] **Le garde de Claude**, par le tube du hook : une entrée
      `{"tool_name":"Bash","tool_input":{"command":"git push origin <branche principale>"}}` rend 2,
      le témoin `git status` rend 0.
- [ ] 👤 **La règle GitHub**, si le dépôt est public : un envoi direct d'un commit **qui n'appartient à
      aucune PR** est refusé (GH013). Pas la tête d'une PR aux contrôles verts : GitHub accepte cet
      envoi et le tient pour la fusion de la PR.
- [ ] Le contrôle de dérive du poste (détecteur 9) ne cite plus le dépôt.

## 9. Nettoyer

- [ ] Retirer le worktree d'alignement et sa branche, locale et distante. Un `node_modules` de pnpm
      se retire sans suivre ses jonctions.

## Avant de passer un dépôt privé en public

Dans un dépôt privé, la porte de confidentialité avertit sur ce qui identifie (elle ne refuse que
les secrets) : des constats ont pu entrer dans l'historique. Avant de changer la visibilité, quatre
étapes, obligatoires et dans cet ordre. `--public` fait refuser la porte comme dans un dépôt
public, puisque le dépôt est encore privé.

1. [ ] **L'arbre** : `python scripts/modele/confidentialite.py --exiger-prives --public --fichiers
       <la liste de git ls-files>` est propre : aucun constat.
2. [ ] **Tout l'historique** :

   ```sh
   git log -p --all --no-textconv --no-ext-diff --format='%H%n%B' > "$TMP/historique.txt"
   python scripts/modele/confidentialite.py --exiger-prives --public --texte "$TMP/historique.txt"
   ```

   est propre : aucun constat, aucune ligne « non examiné ». Les lignes ajoutées et retirées et les
   messages sont examinés ; les binaires de l'historique ne le sont pas. Si un constat apparaît :
   réécrire l'historique, ou publier un nouveau dépôt depuis un commit unique propre.
3. [ ] Un passage complet de `modele-historique.yml` est vert.
4. [ ] `copier update` avec `visibilite=public`, fusionné ; puis, 👤, la visibilité du dépôt et la
       règle de protection.
