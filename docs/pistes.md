# Pistes

Notées, pas engagées. Une piste devient une issue le jour où on la travaille, et sort alors de ce fichier.

*Une piste par puce : l'idée en une phrase, d'où elle vient, ce qui la déclencherait.*

- **Workers et D1 pour un tableau des scores.** Une passerelle Workers et D1 donnerait au site personnel un tableau des scores sans passer en cible `serveur`. Vient du cadrage (§16). Déclencheur : un jeu du site qui veut des scores partagés.
- **Routes et contrôles par API.** Créer les routes du tunnel et les contrôles de supervision par les API de Cloudflare et de Healthchecks, au lieu de les poser à la main. Vient du cadrage (§16). Déclencheur : la mise en service manuelle dépasse ses 15 minutes.
- **Renovate pour `copier update`.** Faire proposer automatiquement les mises à jour du modèle par une PR, si Renovate sait suivre un modèle Copier. Vient du cadrage (§15 et §16). Déclencheur : plus de trois projets alignés.
- **La mécanique en image versionnée.** Publier la mécanique de déploiement comme image `ghcr.io/edouardzemb/modele-projet/mecanique`, épinglée par empreinte dans chaque projet. Vient du cadrage (§2, « Approche »). Déclencheur : un quatrième projet en cible `serveur`.
