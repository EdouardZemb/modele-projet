# M-0002 — Garde-fous et confidentialité : dépôts publics protégés par une règle, hooks locaux en renfort

- **Statut** : accepté le 2026-10-16
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

- **Les dépôts sont publics par défaut**, protégés par une règle GitHub : PR obligatoire, contrôles
  requis, ni force-push ni suppression de la branche principale.
- **En plus**, dans tous les cas : des hooks git (`pre-commit`, `commit-msg`, `pre-push`) et un hook
  Claude `PreToolUse` sur les outils `Bash` et `PowerShell`.
- Un dépôt **privé** reste possible. Il n'a alors que les hooks, et la CI de base.
- **La porte de confidentialité est obligatoire**, dans tous les projets. Ses motifs génériques sont
  versionnés ; ses motifs privés (noms de machines, d'utilisateurs, chemins) sont gardés hors dépôt,
  sur le poste et dans un secret de la CI. Une session à distance n'a pas la liste privée : la CI
  rattrape le reste. Ce secret est posé deux fois par dépôt, comme secret Actions et comme secret Dependabot,
  car les exécutions de Dependabot ne reçoivent pas les secrets Actions.
- **Le modèle lui-même est public.** Rien de ce qu'il contient ne nomme le serveur, son utilisateur
  ou son réseau.
- **Un refus se corrige, il ne se contourne jamais.**

## Conséquences

- Un dépôt public expose son code et son historique : la porte de confidentialité n'est pas une
  option, et un secret poussé est à considérer comme compromis, même supprimé ensuite.
- Un dépôt privé est moins bien protégé qu'un dépôt public : rien ne retient un contournement des
  hooks. C'est un risque accepté, et le contrôle de dérive en tient compte.
- Les journaux d'Actions d'un dépôt public sont publics : la porte n'y affiche jamais la valeur
  trouvée, seulement l'emplacement et le nom du motif.
- **Difficile à changer** : la visibilité d'un dépôt, une fois son historique publié.

## Révision

Cet ADR doit être rouvert si :

- GitHub étend la protection de branche aux dépôts privés des comptes gratuits ;
- Edouard prend un abonnement qui l'autorise ;
- un contournement des hooks est constaté dans un projet : la règle correspondante devient alors une
  porte côté serveur.
