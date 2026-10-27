# M-0002 — Garde-fous et confidentialité : dépôts publics protégés par une règle, hooks locaux en renfort

- **Statut** : accepté le 2026-10-16
- **Amendé** le 2026-10-17, après la revue finale du lot 1 : dans un dépôt privé, la porte de
  confidentialité avertit sur ce qui identifie et refuse toujours les secrets (décision d'Edouard)
- **Amendé** le 2026-10-18, avec la cible `serveur` : qui fusionne se choisit par la réponse
  `fusion`, et les étiquettes et les publications sont à Edouard (décision d'Edouard)
- **Amendé** le 2026-10-27, avec le lot 8 : le `pre-commit` refuse un fichier du modèle que le
  `.gitignore` du projet masque (LE-23), et un hook `SessionStart` affiche ce qui est rouge sur
  GitHub
- **Contexte amont** : M-0001 (les garde-fous de qualité comme condition d'entrée)

## Contexte

Un projet né du modèle doit pouvoir refuser, sans surveillance, ce qu'une session fatiguée ou un
agent trop zélé ferait : pousser sur la branche principale, envoyer un secret ou une adresse interne
dans l'historique, fusionner avec des contrôles rouges.

GitHub refuse la protection de branche sur les dépôts **privés** d'un compte gratuit (erreur HTTP
403). Edouard ne prend pas GitHub Pro. La question est donc : où poser la protection qui ne dépend
pas de la discipline de celui qui travaille ?

## Options

| Option | Verdict | Raison |
|---|---|---|
| A. Prendre GitHub Pro | Écartée | Un coût mensuel pour une protection que les dépôts publics ont gratuitement |
| B. Dépôts publics par défaut, protégés par une règle GitHub (*ruleset*) | **Retenue** | Gratuite, appliquée côté serveur, hors de portée d'une session |
| C. Hooks locaux seulement (hook git et hook Claude) | **Retenue en complément** | Seule protection d'un dépôt privé ; en plus de la règle pour un dépôt public |

## Décision

- **Les dépôts sont publics par défaut**, protégés par une règle GitHub : tout commit qui arrive sur
  la branche principale est la tête d'une PR dont les contrôles requis sont verts ; un envoi direct
  de cette tête est accepté et marque la PR fusionnée, sans squash. Côté agent, c'est le refus de
  pousser vers la branche principale par le garde qui ferme ce chemin. Ni force-push ni suppression
  de la branche principale.
- **En plus**, dans tous les cas : des hooks git (`pre-commit`, `commit-msg`, `pre-push`) et un hook
  Claude `PreToolUse` sur les outils `Bash`, `PowerShell` et `Monitor`, et sur tout outil MCP qui
  porte une commande. Le garde refuse toute modification de `core.hooksPath`, sauf la réparation
  `git config core.hooksPath .githooks`.
- Un dépôt **privé** reste possible. Il n'a alors que les hooks, et la CI de base.
- **La porte de confidentialité est obligatoire**, dans tous les projets. Ses motifs génériques sont
  versionnés ; ses motifs privés (noms de machines, d'utilisateurs, chemins) sont gardés hors dépôt,
  sur le poste et dans un secret de la CI. Une session à distance n'a pas la liste privée : la CI
  rattrape le reste. Ce secret est posé deux fois par dépôt, comme secret Actions et comme secret Dependabot,
  car les exécutions de Dependabot ne reçoivent pas les secrets Actions.
- **Dans un dépôt public, la porte refuse ; dans un dépôt privé, elle avertit sur ce qui identifie
  et refuse toujours les secrets** (amendement du 2026-10-17). Un dépôt privé peut ainsi nommer son
  propre serveur. Ce qui identifie (adresses privées et Tailscale, cibles SSH et scp, noms MagicDNS,
  motifs de la liste privée) s'affiche, avec son emplacement et le nom du motif, jamais la valeur, et
  ne refuse pas. Un secret (clé privée age ou PEM, jeton GitHub, JWT, jeton de tunnel, adresse de
  ping) refuse partout, au `pre-commit` comme en CI : une clé ne part jamais sur le dépôt distant
  avec un simple avertissement. gitleaks les cherche aussi, en CI, donc après l'envoi. Les erreurs
  d'usage et l'absence de la liste privée exigée refusent toujours. En CI, la visibilité réelle du dépôt (`github.event.repository.private`) l'emporte sur celle que
  déclare `reglages.py` : un dépôt passé public sans `copier update`, ou une PR qui réécrit
  `VISIBILITE`, refuse comme tout dépôt public.
- **Avant de passer un dépôt privé en public**, quatre étapes obligatoires, la porte en mode
  `--public` : elle est propre sur `git ls-files` (`--exiger-prives --public --fichiers`) ; elle est
  propre sur tout l'historique (`git log -p --all --no-textconv --no-ext-diff --format='%H%n%B'`
  écrit dans un fichier, puis `--exiger-prives --public --texte`), sans quoi on réécrit
  l'historique ou l'on publie un nouveau dépôt depuis un commit unique propre ; un passage complet
  de `modele-historique.yml` est vert ; `copier update` avec `visibilite=public`, puis la règle de
  protection. Les binaires de l'historique ne sont pas examinés.
- **Qui fusionne : la réponse `fusion`** (amendement du 2026-10-18), choisie à la création du
  projet. En mode `session`, la session fusionne sa PR une fois tous les contrôles verts. En mode
  `edouard`, elle ouvre la PR, attend le vert, le dit et s'arrête : le garde refuse toute fusion,
  par `gh pr merge` (`--auto` et `--admin` compris), par l'API ou par GraphQL. Le mode lui-même se
  lit sur GitHub, par l'API (`gh api`), dans le `.copier-answers.yml` de la branche principale, et
  non dans celui de la copie locale ni dans `origin/<branche>`, qu'une session peut réécrire. Tout
  ce qui est illisible vaut `edouard`. Deux entrées restent locales : le nom de la branche passée
  en `ref=` vient des réglages de la copie (`BRANCHE_PRINCIPALE`, dans
  `scripts/modele/reglages.py`, ou l'option `--branche` du garde) ; et l'option `--fusion` du
  garde, posée sur la commande du hook dans un `settings.json` de la copie, l'emporte sur cette
  lecture.
- **Les étiquettes et les publications sont à Edouard**, dans les deux modes (amendement du
  2026-10-18) : une étiquette `vX.Y.Z` met un projet `serveur` en production. Le garde refuse
  l'envoi d'une étiquette et toute écriture de publication (`gh release` en écriture, l'API
  `…/releases`) ; une session peut préparer l'étiquette en local.
- **Un fichier du modèle que le `.gitignore` du projet masque fait refuser le commit** (amendement
  du 2026-10-27). Copier écrit sur le disque un fichier géré que le `.gitignore` ignore, sans rien
  en dire : il n'entre alors dans aucun commit, et le projet n'a pas ce que le modèle lui a donné
  (LE-23). La porte `masques.py` tourne dans le `pre-commit`, avant la confidentialité, et ne
  s'applique qu'au commit qui modifie `.copier-answers.yml` : celui d'un alignement ou d'une mise à
  jour. Elle nomme chaque fichier et la règle qui le masque ; le remède est une exception nommée
  au `.gitignore`, `!<chemin>`, ou `!<dossier>/` quand un dossier parent est exclu, car git ne
  regarde pas dans un dossier exclu. Un fichier local se sort du dossier, et le masque d'un
  fichier de secrets ne se lève jamais. Le hook est le bon endroit : c'est le seul moment où le
  fichier manquant se voit encore, avant le commit, et il vaut pour une session comme pour
  Edouard. La vérification à la main de `docs/aligner.md` reste, la porte refuse si on l'oublie.
- **Un hook `SessionStart` affiche ce qui est rouge sur GitHub** (amendement du 2026-10-27). Au
  démarrage et à la reprise, `signaux.py` lit les exécutions de la branche principale, les PR
  ouvertes et les workflows désactivés, et les montre à la session. Il ne bloque jamais : il sort
  toujours 0, et un `gh` absent ou illisible ne dit rien de faux. Sur un dépôt public, n'importe
  qui écrit depuis un fork, et ce texte entrerait dans le contexte de Claude : les exécutions de PR
  (`pull_request…`) sont écartées, car elles prennent le fichier de workflow du fork, et une
  PR ou un workflow venus d'ailleurs que le dépôt s'affichent sans le texte qu'ils portent. Une PR
  d'un fork paraît ainsi sans titre ni nom de contrôle, un workflow absent de la copie, sans son
  nom. La CI du socle exige ce hook comme elle exige le garde : sans lui, un rouge passerait
  inaperçu jusqu'à la prochaine PR.
- **Le modèle lui-même est public.** Rien de ce qu'il contient ne nomme le serveur, son utilisateur
  ou son réseau.
- **Un refus se corrige, il ne se contourne jamais.**

## Conséquences

- Un dépôt public expose son code et son historique : la porte de confidentialité n'est pas une
  option, et un secret poussé est à considérer comme compromis, même supprimé ensuite.
- Un dépôt privé est moins bien protégé qu'un dépôt public : rien ne retient un contournement des
  hooks. C'est un risque accepté : le garde de Claude est alors la seule serrure côté agent, et la
  CI du socle le seul filet.
- Dans un dépôt privé, la porte n'empêche plus un nom de serveur ou une adresse d'entrer dans
  l'historique : elle le signale. Elle y refuse toujours les secrets. L'historique d'un dépôt privé n'est donc pas prêt à être publié ;
  son passage en public demande l'examen complet décrit plus haut, et un dépôt passé public sans
  lui exposerait tout ce qui a été averti.
- Les journaux d'Actions d'un dépôt public sont publics : la porte n'y affiche jamais la valeur
  trouvée, seulement l'emplacement et le nom du motif.
- En mode `edouard`, chaque fusion attend Edouard : c'est le prix d'un dépôt dont une fusion
  touche une machine partagée. La PR qui apporte l'option `fusion` à un projet existant se fusionne
  à la main : tant que la branche principale n'a pas la réponse, le garde la lit comme `edouard`.
- Une mise en production attend toujours Edouard, quel que soit le mode : la session prépare
  l'étiquette, il l'envoie.
- **Difficile à changer** : la visibilité d'un dépôt, une fois son historique publié.

## Révision

Cet ADR doit être rouvert si :

- GitHub étend la protection de branche aux dépôts privés des comptes gratuits ;
- Edouard prend un abonnement qui l'autorise ;
- un contournement des hooks est constaté dans un projet : la règle correspondante devient alors une
  porte côté serveur ;
- une fusion en mode `edouard`, une étiquette ou une publication passe sans Edouard.
