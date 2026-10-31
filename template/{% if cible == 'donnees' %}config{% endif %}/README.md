# config/

La configuration personnelle de l'application : identité, employeur, lieu, salaire, choix de
recherche, noms des personnes du foyer. Rien de cela ne va dans un dépôt de code (M-0006, § 2).
Ce qui se règle au téléphone vit en base, pas ici : ce dossier n'en porte que la graine.

Pour une application en cible `serveur` :

- Ce dossier est monté en lecture seule sur `/config`, en prod seulement : l'application y lit sa
  configuration réelle (M-0006, § 5). Le staging ne le monte jamais : il tourne sur l'exemple
  (`exemple/`) et le jeu factice du dépôt de code.
- La prod monte celui de la plus haute étiquette de données, `donnees-AAAA.MM.JJ.n`, que pose
  Edouard 👤 : une modification n'entre en service qu'avec l'étiquette suivante.
- Il porte sa version de schéma. L'application la lit et refuse une version qu'elle ne connaît pas :
  la commande `VERIFIER_CONFIG` rend alors 2.
- Il va avec sa commande `VERIFIER_CONFIG`, déclarée dans le dépôt de code : la chaîne refuse un
  dossier présent sans sa commande, et une commande sans son dossier. Le dossier est présent quand
  il porte au moins un fichier autre que ce `README.md` : seul, ce fichier ne compte pas.
- La CI de ce dépôt, `modele-donnees.yml`, le vérifie à chaque PR, contre les images du code.
