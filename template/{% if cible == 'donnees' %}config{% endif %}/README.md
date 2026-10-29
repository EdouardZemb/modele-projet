# config/

La configuration personnelle de l'application : identité, employeur, lieu, salaire, choix de
recherche, noms des personnes du foyer. Rien de cela ne va dans un dépôt de code (M-0006, § 2).

- Ce dossier est monté en lecture seule sur `/config` : l'application y lit sa configuration réelle
  (M-0006, § 5).
- Il n'est monté que sur la prod, jamais en staging : le staging tourne sur l'exemple (`exemple/`) et
  le jeu factice du dépôt de code.
- Il porte sa version de schéma. L'application la lit et refuse une version qu'elle ne connaît pas :
  la commande `VERIFIER_CONFIG` rend alors 2.
- Il va avec sa commande `VERIFIER_CONFIG`, déclarée dans le dépôt de code : la chaîne refuse un
  dossier sans sa commande, et une commande sans son dossier.
- Ce qui se règle au téléphone vit en base, pas ici : ce dossier n'en porte que la graine.
