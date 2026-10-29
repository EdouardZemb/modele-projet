# contenu/

Le contenu de l'instance : ce que l'application montre et qui ne peut pas être public (M-0006,
§ 2). Ce n'est ni une donnée personnelle, ni du code.

- Un contenu protégé par le droit d'auteur, ou réservé à des personnes autorisées.
- Les mentions que la loi oblige l'instance à afficher : le contact du responsable du traitement,
  son lieu, les durées de conservation.

Ce dossier est monté en lecture seule sur `/contenu`, en staging comme en prod : le contenu de
l'instance n'est pas une donnée personnelle (M-0006, § 5).

- Il porte sa version de schéma. L'application la lit et refuse une version qu'elle ne connaît pas :
  la commande `VERIFIER_CONTENU` rend alors 2.
- Il va avec sa commande `VERIFIER_CONTENU`, déclarée dans le dépôt de code : la chaîne refuse un
  dossier sans sa commande, et une commande sans son dossier.
