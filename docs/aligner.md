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
    --data nature=<code|donnees> --data cible=aucune --data branche_principale=<branche> \
    gh:EdouardZemb/modele-projet .
  ```

- [ ] **La nature est choisie** (`--data nature=<code|donnees>`) : un dépôt qui nomme son serveur ou
      son instance prend `donnees` jusqu'à sa scission (M-0006, § 7) ; tout autre prend `code`. La
      nature n'est pas la cible : elle ne change pas les fichiers rendus, seulement le régime de la
      porte de confidentialité.
- [ ] **Rien d'existant n'a bougé** : `git diff --name-only` est vide, et `git status --short` ne
      montre que des fichiers nouveaux (`??`). Copier ignore les fichiers semés déjà présents
      (`README.md`, `CLAUDE.md`, `.gitignore`…) : il les signale en conflit, sans les toucher. Si un
      fichier existant a changé, s'arrêter.
- [ ] **Aucun fichier géré n'est masqué** : sous un chemin géré (`.githooks/`, `scripts/modele/`,
      `docs/modele/`, `.github/modele/`, `.github/workflows/modele-*.yml`,
      `.claude/skills/consigner/`), `git status --short --ignored` ne montre en `!!` que des caches
      (`__pycache__/`). Copier écrit un fichier
      que le `.gitignore` du projet ignore sans rien en dire : la règle `*secret*` de
      `veille-emploi` masquait `scripts/modele/verifier_secrets.py` (LE-23). `git check-ignore -v
      <chemin>` nomme la règle ; ajouter au `.gitignore` une exception nommée (`!<chemin>`). Cette
      vérification reste à faire à la main : si on l'oublie, le `pre-commit` refuse le commit qui
      modifie `.copier-answers.yml` et nomme le fichier masqué.

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

## Passer en cible `serveur`

Pour un projet déjà aligné qui se déploie sur le serveur. Changer de cible, c'est changer une
réponse puis lancer `copier update` (`methode.md`, « Les fichiers gérés par le modèle ») ; la mise
en service elle-même suit `docs/exploitation.md` du projet, une fois rendu. Mêmes préparatifs
qu'au §1, dans un worktree `<dépôt>.worktrees\modele-serveur`.

- [ ] **La PR qui apporte `fusion` se fusionne à la main.** Un projet aligné avant l'option la
      reçoit au premier `copier update` vers une étiquette qui la connaît, souvent celui qui le
      passe en cible `serveur`. Tant que la branche principale n'a pas la réponse, le garde la lit
      comme `edouard` et refuse toute fusion : 👤 Edouard fusionne cette PR.
- [ ] **Rendre**, sur un arbre propre, avec le bloc de ports que `projets/<nom>.env` réserve dans
      `serveur` :

  ```sh
  copier update --defaults --vcs-ref <étiquette> --data cible=serveur --data bloc_ports=<bloc> \
    --data sauvegardes=<true|false> --data fusion=<session|edouard>
  ```

  `--data fusion=…` est nécessaire tant que le projet n'a pas la réponse : `--defaults` lui
  donnerait en silence `fusion=session`, alors que le mode se choisit (M-0002). Ajouter
  `--data domaine=…`, `sous_domaine=…`, `port_app=…` ou `chemin_sante=…` si le projet
  diffère des valeurs par défaut. `branche_principale` reste la réponse du projet : le staging suit
  cette branche, et l'image `:main` que la CI publie à chaque fusion sur elle. Un conflit dans un
  fichier géré se résout en faveur du modèle.
- [ ] **Les reports à la main de `ci.yml`**, que `copier update` ne touche plus. Rendre le modèle à
      côté, avec les mêmes réponses :

  ```sh
  copier copy --defaults --vcs-ref <étiquette> --data <les réponses du projet> \
    gh:EdouardZemb/modele-projet <dossier temporaire>
  ```

  puis en reporter dans le `ci.yml` du projet :
  - le commentaire et le bloc `concurrency`, qui n'annule jamais une publication en cours ;
  - le job `verifier`, où vont les vérifications du projet (son lint, ses tests, sa construction) :
    renommer en `verifier` le job qui les porte déjà ;
  - le job `deploiement` (`sh tests/deploiement/lancer.sh`, `needs: verifier`) ;
  - le job `image` (`needs: [socle, verifier, deploiement]`, `packages: write`) : l'action
    `modele-image-construire`, puis les tests de bout en bout du projet contre l'image, puis
    `modele-image-publier`, au push sur la branche principale seulement, et ses deux étapes de fin.
- [ ] **Les reports à la main des autres fichiers semés**, que `copier update` ne touche pas non
      plus quand le projet les a déjà. Depuis le même rendu à côté, reporter :
  - les deux blocs `package-ecosystem: docker` de `.github/dependabot.yml` (`/` et
    `/tests/deploiement`) ;
  - si le projet a déjà un `docs/exploitation.md`, les sections du modèle qui lui manquent. Les
    fusionner avec les siennes, sans rien retirer de ce qui est propre à l'app.
- [ ] **Retirer l'ancien workflow de version**, s'il existe (un `version.yml` qui publie l'image à
      l'étiquette), et toute publication d'image de l'ancien `ci.yml`, dans la même PR. Avec
      `modele-version.yml`, deux workflows tourneraient sur la même étiquette.
- [ ] **Le `Dockerfile` à la racine, à fournir ou à adapter**, que le modèle ne sème pas : il tient
      le contrat de M-0003, dont `/donnees` à l'uid 1000.
- [ ] **Les fichiers semés de la cible**, à remplir : `deploiement/projet.env` (les commandes
      `SAUVEGARDER` et `VERIFIER`) ; `deploiement/compose.projet.yml` ; les secrets de l'app dans
      `deploiement/secrets/<env>.cles` ; `docs/exploitation.md`, avec ce qui est propre à l'app.
- [ ] **Un état qu'une restauration ne doit pas défaire** (un registre de suppressions, par
      exemple) : le projet déclare `REPORTER` et `REPORTER_SECTION` dans `deploiement/projet.env`,
      et écrit cette section dans `docs/exploitation.md` (M-0003, M-0005).
- [ ] **Un projet qui avait déjà ses scripts de déploiement** : ils cèdent la place à ceux de
      `deploiement/`. Chaque déploiement prend son instantané avec la commande de la version qui
      arrive, dans l'image de celle qui part (M-0003). La version qui précède l'alignement connaît
      donc déjà la commande `SAUVEGARDER` du modèle, et la version alignée garde l'ancienne forme
      une version au moins : sans cela, ni l'alignement ni le retour à la version d'avant ne
      passent (invariant 4).
- [ ] **Un projet qui a déjà son propre tunnel** (un `cloudflared` dans son compose) : au premier
      déploiement, le `--remove-orphans` de `deployer.sh` retire tout service que les fichiers
      compose ne déclarent plus, et l'adresse publique tomberait. À la version alignée, garder
      l'ancien `cloudflared` dans `deploiement/compose.projet.yml`, sans profil, avec son jeton dans
      les secrets : l'app rejoint aussi le tunnel commun, et les deux chemins servent. 👤 Passer
      ensuite les routes, staging puis prod, par la procédure du dépôt `serveur`,
      « Faire passer une route d'un tunnel à un autre » : Cloudflare impose une à deux minutes de
      coupure par route (`docs/registre.md`, LE-18). À la version suivante, retirer le service et
      son jeton (LE-19), puis 👤 les anciens tunnels dans Cloudflare.
- [ ] **Les instantanés d'avant l'alignement** gardent leur ancienne forme, que le `restaurer.sh`
      du modèle ne lit pas. `docs/exploitation.md` du projet dit comment les restaurer par l'ancien
      script, et jusqu'à quand : leur rétention. On tire **tout** l'ancien `deploiement/`, par le
      commit d'avant l'alignement, dans un dossier temporaire et sans toucher au clone
      (`git -C <clone> archive <commit> deploiement | tar -x -C <dossier temporaire>`) : l'ancien
      script charge sa `lib.sh` à côté de lui, et lit les secrets, `env/` et le compose de son
      propre arbre. D'abord le plan, sans `--oui`.
- [ ] **Les secrets avant `serveur`.** 👤 `secrets.ps1 refaire` pour chaque environnement, puis 🤖
      la PR des deux `.enc`, fusionnée **avant** la PR de `serveur` qui déclare le projet : la
      sonde d'un projet sans ses secrets alerte (code 3). L'ordre complet est celui de
      `docs/exploitation.md`, « La mise en service ». Pour un projet déjà en service,
      `projets/<nom>.env` déclare ce qui existe, et la sonde de `serveur` n'y crée rien.
- [ ] `gh pr checks` entièrement vert : `socle`, `verifier`, `deploiement` et `image`.

### Activer les sauvegardes sur un projet en service

Pour un projet `serveur` en service, rendu avec `sauvegardes=false` : `copier update --defaults
--vcs-ref <étiquette> --data sauvegardes=true`. La mise à jour apporte les scripts, les unités et
le montage `/sauvegardes`, mais elle ne remplit pas les fichiers semés.

- [ ] **`deploiement/projet.env`**, semé : y déclarer les deux commandes de l'image,
      `SAUVEGARDER=<mots>` et `VERIFIER=<mots>` (M-0003). Sans elles, le job `image` refuse
      l'image (`deploiement/ci/verifier-image.sh`).
- [ ] **`deploiement/secrets/prod.cles`**, semé : y ajouter `HC_SAUVEGARDE` et
      `HC_TEST_RESTAURATION`, que le contrôle des secrets de la CI exige (`SECRETS_EXIGES`, dans
      `scripts/modele/reglages.py`). Puis 👤 les deux contrôles Healthchecks, et `secrets.ps1
      refaire` pour la prod, avec leurs adresses.
- [ ] **Avant l'étiquette**, une PR dans `serveur` qui ajoute les heures `SAUVEGARDE` et
      `TEST_RESTAURATION` à `projets/<nom>.env` : sans elles, `installer-unites.sh` refuse, et la
      sonde de prod ne déploie pas la version.
- [ ] **Le premier déploiement ne prend pas d'instantané** : la version qu'il remplace ne monte pas
      `/sauvegardes`. `deployer.sh` le dit au journal (« la version en service ne monte pas
      /sauvegardes : pas d'instantané ») et continue. Les déploiements suivants prennent le leur.
- [ ] Ensuite, 👤 une fois, sur le serveur, la première sauvegarde et le test de restauration,
      comme à l'étape 6 de la mise en service (`docs/exploitation.md`).

### Revenir en cible `aucune`

`copier update --data cible=aucune` retire `deploiement/`, `tests/deploiement/`, `.sops.yaml` et
`docs/exploitation.md`, **fichiers semés compris** (`projet.env`, `compose.projet.yml`, les `.cles`),
même retouchés par le projet. Copier ne garde pas un semé dont le gabarit disparaît, et la
suppression est silencieuse : ni `.rej`, ni conflit. Le §8 de la spec disait que ces semés
restaient. `CLAUDE.md` et `docs/registre.md`, eux, survivent.

- [ ] **Avant** : noter le commit d'avant (`git rev-parse HEAD`) et mettre à l'abri ce que le projet
      y a écrit, au moins `deploiement/projet.env` et `deploiement/compose.projet.yml` (commandes
      `SAUVEGARDER` et `VERIFIER`, services propres à l'app), puis les `.cles` et
      `docs/exploitation.md`.
- [ ] **Après** : récupérer ce qui est utile, par `git show <commit>:deploiement/projet.env` ou
      `git checkout <commit> -- deploiement/`.

## Passer un dépôt en public

Deux cas, selon la nature du dépôt (M-0006).

- [ ] **Un dépôt de code né après M-0006** n'a pas de travail préalable : la porte a refusé tout
      constat dès son premier commit, et relit son historique chaque semaine
      (`modele-historique.yml`). Il ne lui faut que sa règle de protection (`ruleset-main.json`),
      puis, 👤, le changement de visibilité.
- [ ] **Un dépôt d'avant M-0006 ne passe pas en public** : son historique a pu recevoir des
      constats que la porte ne faisait qu'avertir. Il se scinde : la scission (M-0006, § 7) fait de
      lui le dépôt de données, et un nouveau dépôt de code naît d'un seul commit propre. Jusque-là,
      sa nature est `donnees`.
