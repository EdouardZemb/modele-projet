# M-0002 — Garde-fous et confidentialité : dépôts publics protégés par une règle, hooks locaux en renfort

- **Statut** : accepté le 2026-10-16
- **Amendé** le 2026-10-17, après la revue finale du lot 1 : dans un dépôt privé, la porte de
  confidentialité avertit sans refuser (décision d'Edouard)
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
- **Dans un dépôt public, la porte refuse ; dans un dépôt privé, elle avertit sans refuser**
  (amendement du 2026-10-17). Un dépôt privé peut ainsi nommer son propre serveur : chaque constat
  s'affiche, avec son emplacement et le nom du motif, jamais la valeur, et le code de retour vaut 0.
  La règle vaut pour tous les motifs, génériques et privés. Les erreurs d'usage et l'absence de la
  liste privée exigée refusent toujours. gitleaks n'est pas concerné : les secrets bloquent toujours.
- **Avant de passer un dépôt privé en public**, trois étapes obligatoires : la porte
  `--exiger-prives --fichiers` sur `git ls-files` est propre ; un passage complet de
  `modele-historique.yml` est vert ; `copier update` avec `visibilite=public`, puis la règle de
  protection.
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
  l'historique : elle le signale. L'historique d'un dépôt privé n'est donc pas prêt à être publié ;
  son passage en public demande l'examen complet décrit plus haut, et un dépôt passé public sans
  lui exposerait tout ce qui a été averti.
- Les journaux d'Actions d'un dépôt public sont publics : la porte n'y affiche jamais la valeur
  trouvée, seulement l'emplacement et le nom du motif.
- **Difficile à changer** : la visibilité d'un dépôt, une fois son historique publié.

## Révision

Cet ADR doit être rouvert si :

- GitHub étend la protection de branche aux dépôts privés des comptes gratuits ;
- Edouard prend un abonnement qui l'autorise ;
- un contournement des hooks est constaté dans un projet : la règle correspondante devient alors une
  porte côté serveur.
