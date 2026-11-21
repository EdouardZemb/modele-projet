@template/docs/modele/methode.md

# modele-projet

Le modèle Copier d'où naissent les projets d'Edouard. Dépôt **public**. Il applique à lui-même les
garde-fous qu'il distribue : hooks git, garde de Claude, CI, règle de protection.

## État

Lot 1 fait le 17/10/2026 : le socle (cible `aucune`), étiqueté `v0.1.1`. Lot 6 fait le même jour :
`veille-emploi`, premier projet dont la branche principale n'est pas `main`.

Lot 2 fait le 27/10/2026 : la cible `serveur` (image publiée par étiquette, sonde, sauvegardes
chiffrées, tunnel commun), l'option `fusion` et les secrets refaits sur le poste, étiquetés
`v0.2.3` après la revue finale. Le dépôt privé `serveur` est né du modèle en cible `aucune` : il
porte la sonde de la machine. `ancrage` est passé en cible `serveur`, puis a retiré son ancien
tunnel en trois versions ; il lui reste un geste daté, noté dans son propre `CLAUDE.md`.

Lot 4 fait le 27/10/2026 : `pupitre` aligné en cible `aucune` (pupitre#7, sur la `v0.2.3`).

Lot 8 fait le 27/10/2026 : deux portes, étiquetées `v0.3.0`. Les signaux (#27) : au démarrage et
à la reprise d'une session, un hook `SessionStart` affiche ce qui est rouge sur GitHub, sans rien
de ce qu'écrit un fork ; la CI du socle l'exige. Les masqués (#36) : le `pre-commit` d'un
alignement ou d'une mise à jour refuse un fichier du modèle que le `.gitignore` du projet masque.

Lot 9 fait le 28/10/2026 : le ménage des images (#19), étiqueté `v0.4.0`. En cible `serveur`,
`deployer.sh` lance `deploiement/nettoyer-images.sh` après chaque déploiement ou retour arrière
réussi. Le script retire les images du projet que ni l'état des deux environnements, ni un
conteneur, ni la marge des 3 plus récentes ne gardent, sans jamais `-f` ; une surprise annule
tout. Une épreuve sur un vrai Docker, dans la CI, le prouve, sur le moteur 28 du runner (LE-41) ;
l'essai sur le serveur, par `ancrage`, est tenu en `v0.7.2`. Le hook `SessionStart` a 30 s (#45).

Lot 10 fait le 28/10/2026 : la garde du dossier de données (#49), étiquetée `v0.5.0`. En cible
`serveur` avec sauvegardes, `deployer.sh` refuse un déploiement ou un retour arrière quand une
version est déployée et que le dossier de données est vide, ou n'est plus celui du dernier succès.
Ce chemin, sous sa forme canonique, est dans le fichier d'état `donnees` ; pour un état d'avant la
`v0.5.0`, celui de `compose.env` en tient lieu. Le refus alerte sans rien changer ; le geste 👤
`--donnees-neuves` lève la garde pour un déploiement.

Lot 11 fait le 29/10/2026 : la porte par nature et le gabarit de données (#55), première étape de
M-0006 (« Le code et les données »), étiquetée `v0.6.0`.
- **La réponse `nature`** (`code` ou `donnees`) remplace `visibilite`. Dans un dépôt de code, tout
  constat de la porte refuse, quelle que soit sa visibilité ; dans un dépôt de données, elle avertit
  sur ce qui identifie et refuse les secrets.
- **En CI**, un dépôt public est toujours de code. Un dépôt privé prend la nature écrite sur sa
  branche par défaut (`refs/remotes/origin/<branche>`), jamais celle de la PR.
- **Chaque lundi**, `modele-historique.yml` relit tout l'historique d'un dépôt de code avec la porte
  (`--historique`), et écarte les couples (commit, chemin) de `.github/constats-acceptes.txt`. La
  visibilité et la branche par défaut s'y lisent par l'API : un déclenchement planifié peut ne pas
  porter `github.event.repository` (LE-33).
- **La cible `donnees`** rend le dépôt privé `<nom>-donnees` : le socle, la méthode, `config/` et
  `contenu/` documentés, rien de l'application.
- **Le domaine n'a plus de défaut.** Edouard a étendu sa liste privée ; le dépôt modèle passe sa
  porte dessus, avec trois constats anciens acceptés.

Lot 12 fait le 31/10/2026 : le contrat de `/config` et la chaîne à deux dépôts (#64), seconde étape
de M-0006 (§ 5 et 6), étiquetée `v0.7.0`. En cible `serveur` :
- **Les deux modes de la chaîne** suivent la nature, sans réponse de plus. À deux dépôts, pour un
  dépôt de code né après M-0006, l'instance vit à la racine du dépôt de données `<nom>-donnees`
  (`env/`, `secrets/`, `.sops.yaml`, `cles/`, `config/`, `contenu/`) ; le staging suit une branche
  des données, la prod leur plus haute étiquette. À un dépôt, pour un dépôt de nature `donnees`
  jusqu'à sa scission, tout reste dans le même dépôt, l'instance sous `instance/config/` et
  `instance/contenu/`, et la prod prend le commit de la plus haute `vX.Y.Z`.
- **L'état déployé est un couple**, l'image et le commit de données (`-` sans données montées) :
  `deploye` et `precedent` gagnent un troisième champ, `echec` devient `<image> <commit>`. Un état
  d'avant se relit, et les scripts d'avant relisent le nouveau. Le retour arrière revient à un
  couple entier, et l'instantané de `/donnees` note à côté de lui le couple en service (`.couple`).
- **L'instantané des données**, extrait du commit sous l'état et figé, est monté en lecture seule
  sur `/config` et `/contenu`, jamais le clone ; le staging ne monte jamais `/config`. Le ménage
  retire, par environnement, ceux que ni l'état ni la marge des 3 plus récents ne gardent.
- **`VERIFIER_CONFIG` et `VERIFIER_CONTENU`**, déclarées dans `deploiement/projet.env`, vérifient
  les données dans un conteneur jetable de l'image visée, avant tout changement, par paires avec
  leurs dossiers ; la santé dit `configuration` (`exemple` ou `montee`). La CI du code les lance
  sur `exemple/` et `exemple-contenu/`, et, à un dépôt, sur `instance/` (LE-37). Un projet qui
  n'en déclare aucune ne voit aucun changement.
- **Les étiquettes de données** `donnees-AAAA.MM.JJ.n` sont à Edouard, comme les `vX.Y.Z` : le
  garde refuse leur envoi.
- **La CI des données**, `modele-donnees.yml`, rendue pour `cible: donnees` avec
  `cible_code: serveur`, contrôle les secrets contre le `.cles` du dépôt de code, et les données
  contre l'image de la prod et `:main`.
- **La réponse `compte`** (`EdouardZemb` par défaut) donne `ghcr.io/<compte>/<nom>`. L'instance
  n'est posée que là où elle vit : un dépôt de code n'a ni domaine, ni bloc de ports, ni clé du
  parc, et la porte y refuse l'instance par ses chemins. Les clés sortent de l'arbre du modèle.
- **Une épreuve sur un vrai Docker**, dans la CI du modèle, déploie un couple, change son seul
  commit de données, fait refuser une configuration, revient en arrière et fait le ménage.

Correctif du 01/11 : « non » aux sauvegardes tant que la prod n'a rien déployé (#77), étiqueté
`v0.7.1`. En cible `serveur` avec sauvegardes, la déclaration du projet dans `serveur` peut dire
`SAUVEGARDE=non` et `TEST_RESTAURATION=non`, ensemble : ni la sauvegarde ni son test ne
s'installent, et le staging tourne. « non » refuse dès que la prod a un état déployé, et quand la
sonde de prod va y déployer une version (`…AVANT_DEPLOIEMENT=1`, une variable, que l'installeur
d'une version plus ancienne ignore). En `--verifier`, l'installeur n'écrit que des écarts et leur
résumé : la sonde de `serveur` lit cette sortie strictement. Né de serveur#22, qui déclarait ainsi
`veille-emploi` : son staging n'avait aucune unité (LE-39).

Second correctif du 01/11 : le ménage voit les images sans étiquette (#80), étiqueté `v0.7.2`. Sous
un Docker 29 récent (constaté en 29.5.3, magasin classique, celui du serveur ; un 29.0.0 les liste
encore), `docker image ls` cache sans `--all` les images sans étiquette, dont les anciennes `:main`
que la sonde de staging tire par empreinte : `nettoyer-images.sh` ne les voyait pas, et retirait
moins qu'il ne devait. Il liste désormais par `--all`, et le double de `docker` du banc fait comme
ce Docker. `ancrage` l'a relevé à l'essai du ménage du lot 9 ; le runner de la CI, en moteur 28,
ne le montrait pas (LE-41).

Versions des projets au 02/11 : `ancrage`, `veille-emploi` et `serveur` en `v0.7.2` (ancrage#150,
veille-emploi#28, serveur#26) ; `pupitre` et `pupitre-donnees` en `v0.7.1`, que la `v0.7.2`, sans
effet en cible `aucune`, ne fait pas monter. Les dépôts d'avant M-0006 sont privés et de nature
`donnees` ; `ancrage` comme `veille-emploi` déploient à un dépôt jusqu'à leur scission. L'essai du
ménage du lot 9 est tenu. Au premier déploiement du staging d'`ancrage` en `v0.7.2`, le ménage dit
« 12 retirées, 7 gardées (4 par l'état, 0 par un conteneur, 3 en marge) » : son `precedent`, sans
étiquette, est compté par l'état (LE-41). `veille-emploi`, redéclaré par serveur#24, tourne en
staging depuis le 01/11, sans sauvegarde, et déclare `VERIFIER_CONFIG` (veille-emploi#30). À un
dépôt, le commit de données d'un couple est la révision de l'image, `-` sans commande déclarée :
cette déclaration a redéployé une fois l'image en service, sous un nouveau couple. Sa prod n'a
jamais rien déployé : sa première étiquette porte son lot #22 et la commande, juste après la
déclaration des heures de ses sauvegardes dans `serveur`. `pupitre` s'est scindé le 01/11, dans
son propre lot et avec l'accord d'Edouard : l'ancien dépôt est devenu `pupitre-donnees`, privé, et
le dépôt public `pupitre` est né du modèle en `v0.7.1`, en nature `code`.

Lot 13 fait le 04/11/2026 : la naissance en deux dépôts et le premier essai réel (#84), fin de
M-0006 § 6 et 7, étiquetée `v0.8.0`.
- **La naissance en deux dépôts.** `poste/Nouveau-Projet.ps1` entre dans le modèle, hors de
  `template/`, avec son test (#85). En `-Cible serveur`, il crée le dépôt de code `<nom>` et le
  dépôt de données `<nom>-donnees`, privé, qui porte les réponses de l'instance ; tout le local des
  deux dépôts se fait avant tout geste sur GitHub (#86). Edouard seul le lance pour de vrai : sous
  Claude Code (`CLAUDECODE` posé), un lancement sans `-ABlanc` est refusé. En cible `serveur`, le
  code est public : le script refuse `-Visibilite prive`, et M-0006 § 1 le dit, puisque la CI du
  dépôt de données le clone et tire ses images sans jeton (#90, #91). La naissance d'`essai-chaine`,
  le 03/11, est la naissance réelle que demande LE-1 ; #90 a changé le script depuis, et Edouard
  l'a relancé le 04/11 sur `essai-naissance`, jetable, en cible `serveur`, avec le modèle `v0.7.2` :
  21 étapes sur 21, les deux dépôts réglés, les 18 scripts du modèle exécutables au premier commit
  du code, les deux lignes de l'index, et la CI rouge des deux côtés, faute de `Dockerfile` dans le
  code et donc d'image pour les données, comme le dit désormais `exploitation.md` (`v0.8.0`).
- **La mise en service à deux dépôts** (`exploitation.md`, semé ; #87). La déclaration dans
  `serveur` porte `DONNEES=oui`. La sonde de `serveur` crée la clé de déploiement
  `depot-<nom>-donnees`, une pour les deux clones, et attend ; 👤 Edouard la pose sur
  `<nom>-donnees`, en lecture seule ; la sonde clone alors les données, puis installe les unités
  (serveur#28). Le paquet GHCR d'un dépôt de code public naît public : une vérification remplace
  le geste 👤 (LE-44).
- **La porte n'a plus le repli `VISIBILITE`** (#88). En CI, un dépôt privé dont la branche par
  défaut ne porte pas `NATURE` prend la nature `code`, la plus stricte, et la porte le dit : « pas
  de NATURE sur la branche par défaut : régime code ».
- **Le garde refuse une fusion après un changement de dossier** (#89). Il lisait le mode dans le
  dossier suivi par les `cd`, mais les contrôles dans celui de la session : les fusions
  d'`essai-chaine` et d'`essai-chaine-donnees` n° 2 à 7 sont passées ainsi, aucune rouge (LE-45).
  Il ne lit plus le mode et les contrôles que du dossier de la session, et refuse toute fusion qui
  suit, dans la même commande, un `cd`, un `Set-Location`, un `env -C`…, même vers le sien. Depuis
  le 03/11, les fusions des autres dépôts reviennent à Edouard, ou à une session ouverte dans ces
  dépôts.
- **`deployer.sh --retour`** nomme le couple marqué en échec. Il dit, selon ce que le retour a
  quitté (l'image, le commit de données, les deux), quel geste ramènerait une moitié quittée et
  lequel passe d'abord : seul le couple quitté est en échec, et la sonde déploie tout couple neuf
  (#91, LE-46).
- **L'essai réel**, les 03 et 04/11, sur `essai-chaine` et `essai-chaine-donnees`, nés du script :
  les scénarios 1 à 7 sont tenus, chacun par sa ligne de journal (l'attente de la clé, le staging,
  un commit de données seul, la prod, une configuration refusée, le retour arrière, le ménage).
  Les gestes d'Edouard n'ont pas été chronométrés : la session les estime à environ 14 min, hors
  des quatre contrôles Healthchecks qu'elle a créés (environ 18 min avec eux), pour une cible de
  15. L'essai a fait corriger la fausse application, son préfixe et le semis de `/donnees`, et les
  textes de la chaîne (#91, LE-42, LE-43).
  Le scénario 8 est tenu le 04/11 : la sauvegarde de 03:30 a noté le couple en service en prod et
  envoyé au distant son archive et son couple, chiffrés ; `rclone lsl` y montre que `copy` garde la
  date du fichier et que les `--include` répétés se combinent en OU, ce que seul le double prouvait.
  Le test de restauration du mercredi 05:30 a réussi sur cet instantané, avec l'image en service,
  celle du couple noté ce jour-là : le test prend toujours la première colonne de `deploye`, jamais
  le `.couple` (M-0005 § 5, LE-54), et ne lit pas la configuration de la prod (une piste).
  Le retrait d'`essai-chaine`, le 04/11, suit la notice de `serveur` (serveur#32). Sur la
  machine, unités, conteneurs, réseaux, clones et dossiers sont retirés sans erreur, les
  instantanés figés compris (serveur#31) ; ses 7 images aussi, dont 4 sans étiquette, sur le
  magasin classique de la cible (LE-50). La vérification en lecture seule n'a rien trouvé du projet,
  et le tunnel commun n'a pas été recréé ; elle ne cherchait pas les horodatages des deux minuteries
  persistantes, qui restent (serveur#34, une piste). Les quatre contrôles Healthchecks sont
  supprimés, et les deux routes Cloudflare aussi, leurs CNAME avec elles ; `essai-chaine` est
  archivé, et `essai-chaine-donnees` aussi, sans sa clé de déploiement. Restent à Edouard : les deux
  horodatages (geste 👤 de serveur#34), le paquet GHCR `essai-chaine` et l'effacement des
  sauvegardes distantes. `essai-naissance` et `essai-naissance-donnees` sont archivés le 07/11, avec
  le oui d'Edouard. À l'arrêt, l'application d'essai a mis 10 s : elle ignore SIGTERM (une piste).
  Le complément de la revue finale, sur les tâches 10 et 11, n'a tourné qu'après la fusion de #92 ;
  ses constats ont fait corriger ces textes (LE-54, LE-55).

Correctif du 04/11 : la scission d'un projet à un dépôt en dépôt de données (#94), étiqueté
`v0.8.1`. Né de la préparation de la scission de `veille-emploi`, par des essais de Copier 9.19.1
sur la `v0.8.0`. En cible `donnees`, la porte des masqués examine aussi `config/README.md` et
`contenu/README.md`, et, sauf `cible_code: aucune`, l'instance : `.sops.yaml`, `env/prod.env`,
`env/staging.env`, `cles/*.pub` et `secrets/*.env.enc`, ses motifs au premier niveau. Un
`.gitignore` qui masque `*.env` ou `*secret*`, comme celui de `veille-emploi`, fait donc refuser le
commit de la mise à jour. Le principe de la porte, partout : le remède n'admet que ce que la porte
examine, toujours par des lignes ancrées. Un dossier mixte, comme `secrets/`, `cles/` ou
`deploiement/`, se lève, en exclut le contenu, puis n'admet que ce qu'elle y examine ; sous un
`.gitignore` imbriqué, ces lignes partent de son dossier (M-0002, amendé). Ce qu'elle n'examine pas
reste masqué, sans refus, un semé sous un ancêtre levé compris ; sous un dossier du modèle, tout est
du modèle, sauf un dossier de secrets ou de clés imbriqué, quelle que soit sa casse, ou un cache
Python. Un test en matrice le prouve, sur 75 cas, trois cibles (`donnees`, et `serveur` en nature
`donnees` comme en nature `code`) et 25 `.gitignore`, avec des clés privées, des secrets en clair,
des fichiers locaux et des noms piégés plantés à côté des fichiers examinés : appliqués à la lettre,
les remèdes font taire la porte en un tour, deux quand deux règles masquent le même fichier ou sous
`**`, trois sous `*`, et rien de planté ne paraît. Le `.gitignore` semé d'un dépôt de données
n'admet sous `secrets/` que les `*.env.enc`. « Changer de cible », dans `methode.md`, dit enfin ce
que fait Copier : les semés que la nouvelle cible ne rend pas partent, même retouchés ; ceux que les
deux rendent gardent leur contenu d'avant, six pour une scission, qu'un `git rm` avant la mise à
jour fait semer à neuf, sauf `.gitignore`, qui se refait à la main par les trois lignes du remède de
`secrets/`, que la porte ne demande pas pour un secret déjà suivi ; ce que le modèle ne connaît pas
se déplace par `git mv` ; `--data cible_code=serveur` est obligatoire. M-0006, § 6, amendé, dit que
`.sops.yaml` se refait à la scission. Un test fait cette scission sur un projet comme
`veille-emploi`, seule et préparée, celle-ci sous `*.env` et `*secret*`. `ancrage` l'attend avant sa
scission ; `veille-emploi` la prendra si elle paraît avant la PR des données de sa V2. Hors de la
cible `donnees`, la porte corrige le remède d'une règle `<dossier>/*`, et nomme « secret chiffré »
un `.enc` de la chaîne ; en cible `serveur`, elle n'examine sous `deploiement/` que ce que le modèle
y écrit, ses fichiers de premier niveau par leur nom, et l'instance et ses secrets chiffrés qu'à un
dépôt, en nature `donnees` : un fichier local, ou le `.sops.yaml` d'un dépôt de code, restent
masqués sans refus. Les textes de `methode.md`, de M-0002 et de M-0006 changent.

Versions des projets au 05/11 : `ancrage`, `serveur`, `pupitre` et `pupitre-donnees` en `v0.8.1`
(ancrage#195, serveur#40, pupitre#19, pupitre-donnees#18), sans refus de la porte des masqués ; le
staging d'`ancrage` sert le commit de sa fusion. `veille-emploi` reste en `v0.8.0` : la `v0.8.1`
est arrivée pendant la scission de sa V2 (veille-emploi#39), qui la prendra, comme Edouard l'a
décidé le 04/11. `pupitre` portait ses trois hooks en 100644 depuis sa naissance par scission, faite
sous Windows : un clone sous Linux ou macOS les aurait ignorés. pupitre#19 les a rendus
exécutables ; un relevé par l'API, le 05/11, trouve les 18 exécutables du modèle en 100755 dans les
autres dépôts nés de lui.

Lot 14 fait le 07/11/2026 : le README des projets (#99), premier temps du travail sur la
documentation, étiqueté `v0.9.0`.
- **Le README semé a deux variantes.** Celle du code, en cibles `aucune` et `serveur` : « Pourquoi »,
  « Démarrer », « Où lire quoi », « Contribuer », et « Licence » en nature `code`. Celle des
  données, en cible `donnees` : une « Carte » de ses dossiers, sans lien, puisque `config/` et
  `contenu/` naissent avec leur seul README et que `secrets/` n'existe pas encore. Hors cible
  `donnees`, « Ce qui fait foi », dans le `CLAUDE.md` semé, cite ses fichiers par des liens, le brief
  et le cadrage compris ; celui d'un dépôt de données les nomme entre accents graves. Le
  `.gitignore` semé exclut `CLAUDE.local.md`.
- **Un `LICENSE` MIT** est semé en nature `code`, hors cible `donnees`, au nom du `compte` ; le
  modèle porte le même. Copier sème un semé absent : un projet de code déjà né le reçoit à sa mise à
  jour, non suivi, à indexer.
- **`docs/modele/documentation.md`**, géré, dit la forme du README, les textes d'un projet, comment
  retirer chacun, et les trois contrôles de `scripts/modele/documentation.py`. La licence et la
  carte de la racine refusent en CI, à la dernière étape du job `confidentialite` du socle : un
  dépôt de code sans `LICENSE` suivi par git ; un `.md` de la racine que ni le README ni « Ce qui
  fait foi » ne lient, `CLAUDE.md` devant l'être depuis le README. Le gabarit resté vide avertit au
  `SessionStart`, sans bloquer : un document ou un dossier que le README lie, et qui n'a que son
  gabarit. Un lien est un lien Markdown que GitHub rend ; les écarts connus au rendu de GitHub sont
  écrits dans `documentation.md` et dans la docstring. Deux ont un test à leur nom, le bloc
  clôturé dans une citation et le commentaire fermé par `--->` ; celui de la barre oblique
  inverse est tenu par le test du refus avant `resolve`.
- **Le README du modèle** nomme chaque réponse à choix de `copier.yml`, et un test l'y tient.
- **La revue finale** a retenu 27 constats : 25 confirmés par leur contre-vérification, et 2 de sa
  lecture de complétude ; 22 sont corrigés dans #112, 5 à la clôture. Elle a mesuré à `b1cc47c` les
  six projets nés du modèle : 3 refus (`pupitre` et `veille-emploi` : `LICENSE` absent et
  `CLAUDE.md` non lié ; `pupitre-donnees` : `CLAUDE.md` non lié) et 2 avertissements, tous vrais.
  Les messages de mise à jour de ces trois projets disent d'aligner le README dans sa propre PR,
  avant la mise à jour.

Versions des projets au 07/11 : les six projets nés du modèle sont en `v0.8.1`. `veille-emploi`
s'est scindé le 06/11, dans son propre lot : l'ancien dépôt est devenu `veille-emploi-donnees`,
privé, en cible `donnees` avec `cible_code: serveur`, et le dépôt public `veille-emploi` est né à
la main, en nature `code` (veille-emploi#1, veille-emploi-donnees#41). Son staging tourne à deux
dépôts depuis le 06/11.

Lot 15 fait le 09/11/2026 : les portes dues (#114), étiqueté `v0.10.0`. Il écrit les portes dues
par LE-37, LE-40, LE-41, LE-46, LE-53, LE-55 et LE-56, sous les formes que propose le registre et
avec les écarts que déclarent la spec et le plan, acceptés par Edouard le 07/11, puis fait le
ménage des notes du lot 14 (PR #115 et #117 à #122).
- **Le texte de la PR, dans son propre workflow** (AM-2, LE-37, LE-55 ; #115). Le workflow
  `texte-pr` (`modele-texte-pr.yml`, géré, dans les trois cibles ; `texte-pr.yml` ici) est seul à
  écouter `edited` : une retouche du titre ou du corps ne relance que lui. Il porte la
  confidentialité et le format du titre et du corps, retirés du socle et de `ci.yml`, puis lance
  `scripts/modele/texte_pr.py`, géré. Le corps de toute PR, sauf celles de `dependabot[bot]`, porte
  une section « Écarts à la spec » : « Aucun. », ou une ligne par écart, avec la promesse qu'il
  touche et la date de l'accord d'Edouard. Une PR qui ferme une issue, d'après l'API
  (`closingIssuesReferences`), porte `Tête relue : <SHA>`, égal à sa tête. Le gabarit de PR, géré,
  porte la section et la ligne, et ne met « Closes #N » que dans la PR de clôture. La règle de ce
  dépôt et celle du gabarit requièrent `texte-pr` ; un projet déjà né retire `edited` de son
  `ci.yml`, semé, à la main. Une relance de `texte-pr` relit le texte d'origine, éprouvé le 07/11 :
  on retouche le texte.
- **Le contrôle des plans** (LE-53, LE-55, LE-56 ; #118, #122). `scripts/modele/plan.py`, géré,
  vérifie les trois sections d'un plan : « Mécanismes annoncés », dont chaque extrait se cherche
  sur la ligne citée, un lieu d'un autre dépôt restant « non vérifié » sans `--depot` ; « Outils et
  cas limites » ; « Revues », qui citent des tâches d'avant la clôture. L'étape « Les plans
  (.claude/plans) » du socle, juste avant la dernière, le lance sur chaque plan qu'une PR ajoute,
  en entier, ou modifie, par `--sans-lieux` ; au push, un plan ajouté se lit aussi par
  `--sans-lieux` (#122). `methode.md` dit la revue du plan, chaque temps de revue en tâche du plan,
  le test au cas limite d'un outil, et le mutant qui éprouve un test qui garde une valeur (LE-62).
  Les plans du modèle restent hors du dépôt : la session les vérifie par la commande de
  « Commandes ».
- **La durée des jobs** (LE-40 ; #119, #121). Les jobs `tests` (les deux systèmes), `mecanique` et
  `menage-cible` de ce dépôt finissent par l'étape « Durée du job », lancée même après un échec :
  elle écrit leur durée au résumé du job, et avertit au-delà des trois quarts de leur délai,
  `DELAI_MIN`, qu'un test tient égal à `timeout-minutes`. Le job `tests` passe de 40 à 45 min, son
  seuil à 33 min 45 s ; sous Windows, il est resté à 22 s sous ce seuil, au plus près, sur #121. La
  revue finale de chaque lot relève ces avertissements, tentative par tentative (« Commandes »).
  LE-40 reste ouverte jusqu'à la fin du lot qui suit.
- **Le budget du garde** (LE-52 ; #119). À court de temps, le garde refuse une fusion en disant
  « budget de 20 s épuisé : mode non lu, relancer », ou « … : contrôles non lus, relancer », au
  lieu de « mode fusion : edouard » ou de « fusion avant que tous les contrôles soient verts ». Il
  reste fermé.
- **Le ménage dans le Docker de la cible** (LE-41 ; #121). Le job `menage-cible` lance l'épreuve du
  ménage des images dans un `docker:29.5.3-dind`, épinglé par empreinte, magasin containerd coupé.
  Avant l'épreuve, il vérifie que son client et son moteur sont à la version de
  `tests/modele/docker-cible.env`, 29.5.3, celle du serveur relevée par `serveur` le 07/11, au
  pilote `overlay2` et sans le magasin containerd. Son délai, 2 min, vaut environ deux fois la plus
  longue de trois exécutions mesurées. La règle de ce dépôt le requiert depuis sa mise à jour du
  08/11, relue par l'API le 09/11 : huit contextes requis.
- **La table des retours** (LE-46 ; #120). Dans `tests/deploiement/sonder.bats`, géré, en cible
  `serveur` et nature `code`, 14 tests font jouer la vraie sonde après le vrai
  `deployer.sh --retour`, pour chacun des trois retours (l'image, le commit de données, les deux),
  en prod et en staging. Chacun lit le conseil du retour, vérifie que la sonde attend tant que rien
  ne change, joue un geste, puis compare le couple déployé à celui qu'annonce le conseil. Le gabarit
  passe de 49 à 63 tests.
- **Les scripts sous `python -I`, et les tests sans cache** (AM-1, AM-3 ; #117, #118). Les huit
  scripts gérés qui importent un voisin posent eux-mêmes `sys.dont_write_bytecode`, puis ajoutent
  leur dossier en fin de chemin d'import : sous `python -I`, ils trouvent leurs voisins et les
  réglages du projet, sans écrire de cache, ce que `tests/test_scripts_isoles.py` éprouve dans un
  projet rendu. `tests/conftest.py` coupe le cache des tests, et le job `tests` échoue sur tout
  `__pycache__` sous `template/scripts/modele/`. `documentation.md` dit trois gestes avant de
  réécrire un README.
- **La revue finale** a lu `7ccab76..d9b5f0c` en cinq lentilles (la spec, les textes, les contrôles
  à vide, les rendus, les mesures), chaque constat contre-vérifié, puis par une lecture de
  complétude. Sur ses 27 constats, 25 sont confirmés par leur contre-vérification ; la lecture de
  complétude en ajoute 4. 21 sont corrigés dans #122, dont le seul critique : le geste de la règle
  de `docs/aligner.md` aurait retiré à `pupitre` trois de ses contrôles requis, et il part désormais
  de la règle en service. 8 reviennent à la clôture. La relecture des corrections a demandé cinq
  rondes, puis une relecture ciblée sans constat, à `abb8b6d` : trois rondes de suite trouvaient
  chacune une forme HTML de plus que GitHub cache, et la liste des écarts au rendu de GitHub est
  désormais dite non close (LE-57). La revue a mesuré aussi : aucun avertissement de durée dans les
  29 exécutions de `ci.yml` des 07 et 08/11, toutes tentatives lues ; sept projets nés du modèle,
  et non six ; leurs sept `ci.yml` écoutent encore `edited`, et leurs quatre plans en cours sont
  refusés par `plan.py`.

Versions des projets au 09/11/2026, relevées par l'API : sept projets sont nés du modèle.
`serveur`, `pupitre`, `pupitre-donnees`, `veille-emploi` et `veille-emploi-donnees` sont en
`v0.9.0` depuis le 07/11 (serveur#53, pupitre#21, pupitre-donnees#20, veille-emploi#7,
veille-emploi-donnees#45). `ancrage` s'est scindé le 07/11 : l'ancien dépôt est devenu
`ancrage-donnees`, privé, en cible `donnees` avec `cible_code: serveur` (ancrage-donnees#207), et
le dépôt public `ancrage` est né d'un seul commit, en cible `serveur` et nature `code`. Tous deux
sont en `v0.8.1`. Trois dépôts sont publics, chacun avec sa règle de protection : `ancrage`,
`pupitre` et `veille-emploi`.

Versions des projets au 12/11/2026, relevées par l'API : les sept projets nés du modèle sont en
`v0.10.0` (serveur#68, pupitre-donnees#21, veille-emploi-donnees#52, veille-emploi#20, pupitre#31,
ancrage#13, ancrage-donnees#213). Le message de `serveur`, dépôt privé, est parti le premier, et les
six autres après le vert de `texte-pr` sur sa PR. Dans chacun des trois dépôts publics, après la
fusion de la mise à jour et avant toute autre fusion, Edouard a ajouté `texte-pr` à la règle de
protection par le geste de `docs/aligner.md` (§ 7), lancé par `!` : le PUT, dont le corps reprend la
règle en service, a été accepté du premier coup les trois fois ; `pupitre` a ensuite aligné son
`CONVENTIONS.md` sur la règle (pupitre#33). La lecture des fermetures par `texte-pr` dans un dépôt
privé est prouvée : sur veille-emploi-donnees#51, qui porte « Closes #12 », `texte-pr` a refusé
trois fois un corps sans la section des écarts ni la ligne `Tête relue`, puis a dit « ferme une
issue : tête relue égale à la tête » (LE-69).

Correctif du 09/11 : le délai du job `tests` de ce dépôt passe de 45 à 50 min, seuil 37 min 30 s
(LE-40). La porte du lot 15 a donné son premier avertissement de durée sur la PR de clôture,
#123 : 34 min 36 s sous Windows, 51 s au-delà du seuil de 33 min 45 s. Edouard avait décidé le
même jour qu'une PR monterait alors le délai à 50 min. Rien ne change sous `template/`.

Correctif du 12/11 : le Docker du runner de `fausse-app` en magasin classique (LE-41).
`ubuntu-latest` est passé d'Ubuntu 24.04 (Docker 28.0.4, magasin classique) à Ubuntu 26.04 (Docker
29.4.2, magasin containerd) : sur #125, l'épreuve du ménage s'y est arrêtée, comme elle le doit sur
un autre magasin que celui de la cible, et `fausse-app`, requis, a bloqué toute fusion. Avant tout
usage de Docker, le job coupe désormais le magasin containerd dans le `daemon.json` du runner, sans
en perdre les réglages (`tests/modele/daemon_classique.py`), redémarre Docker, puis vérifie le
pilote `overlay2` et l'absence du magasin containerd : ses deux épreuves tournent sur un Docker 29
en magasin classique, comme la cible. Rien ne change sous `template/`.

Lot 16 fait le 13/11/2026 : les plans par tranches et l'accord sans prénom (#127), étiqueté
`v0.11.0`. Il corrige deux défauts de la `v0.10.0` que `pupitre` a relevés le 12/11, et fait cinq
retouches des mêmes fichiers suggérées au lot 15 (PR #128 à #131) ; ses trois écarts à la spec,
acceptés par Edouard le 12/11, sont déclarés chacun dans sa PR (#129, #130).
- **Les plans par tranches** (LE-70 ; #128). `plan.py` lit deux sortes d'unités, `### Tâche N` (ou
  `### Task N`) et `### Tranche N`. Un plan qui n'a que des tranches est un plan maître : « Revues »
  y cite des tranches, la clôture restant la première unité dont le titre dit « clôture ». Un plan
  qui mêle les deux sortes refuse. Les refus de forme disent la forme de leur section, et le `<!--`
  jamais fermé a son propre message. L'étape « Les plans » du socle, et sa copie ici, écrit hors
  d'une base nulle « Plans ajoutés : N, modifiés : M, supprimés : S. ». `methode.md` dit le lot en
  tranches : seule la PR de clôture du lot supprime le plan maître et les plans de tranche.
- **L'accord sans prénom** (LE-71 ; #129). Un écart finit par `— accord : JJ/MM/AAAA` ; l'ancienne
  forme, `— accord d'Edouard : JJ/MM/AAAA`, reste admise. Les messages de `texte_pr.py` et le
  gabarit de PR ne nomment personne, et le commentaire « Tête relue » du gabarit dit qu'une PR qui
  ne ferme aucune issue laisse la ligne vide, ou la retire.
- **Le texte d'une PR s'éprouve en local** (#129). `methode.md` donne la commande qui lance
  `texte_pr.py` sur le corps, un fichier UTF-8 hors du dépôt, avant d'ouvrir la PR, et #131 y
  ajoute « sans BOM » ; ce dépôt la lance par sa variante de « Commandes », qu'un test tient. Elle
  commence par `corps='<fichier du corps>'`, et sa variante à la troisième ligne éprouve la tête
  relue : un écart à la spec (§ 4.5). Elle n'éprouve ni le format du titre ni la confidentialité.
  Le tableau des garde-fous nomme les écritures par l'API que refuse le garde, dont les objets de
  git et `…/update-branch`, que la spec omettait : un autre écart (§ 4.6).
- **Le geste de la règle, partagé** (#130). Au § 7 de `docs/aligner.md`, la session lit la règle en
  service et prépare `avant.txt` et `regle.json` ; Edouard lance la seule ligne du PUT, par `!`,
  que le garde refuse à une session. Au § 6, chaque ligne d'un bloc 👤 se lance par `!`, seule dans
  son message, et non le seul POST : le troisième écart (§ 4.4) ; la liste privée s'y pose par Git
  Bash, jamais par `cmd /c` (LE-73). Le PUT a réussi du premier coup le 12/11 sur les trois dépôts
  publics.
- **La revue finale** a lu `ad8f11b..54f4fe4` en quatre lentilles (la spec, les textes, les cas
  limites, les mesures), chacune contre-vérifiée, puis par une lecture de complétude : 22 constats,
  19 sans leurs doublons d'une lentille à l'autre, aucun critique et un important, les leçons du lot
  sans ligne au registre (LE-76). #131 corrige les onze qui reviennent au lot. Cinq vont à la
  clôture, dont un constat d'avant le lot, deux formes HTML que nomme désormais la piste du
  commentaire jamais fermé ; un va au message de `pupitre` ; deux d'avant le lot restent tels
  quels, car ils refusent du côté sûr : un titre de tranche à espace insécable, et
  « sous-tranche 2 ». Les huit plans en cours des sept projets donnent la même sortie qu'en
  `v0.10.0`, aucun des 184 corps de PR relevés dans les projets qui passait en `v0.10.0` ne
  refuse, et les sept fichiers gérés que le lot change ont dans chaque projet le même blob qu'en
  `v0.10.0`. Aucun job `tests` n'a été coupé ni n'a averti depuis le lot 15 : sous Windows, il a
  duré au plus 34 min 55 s, sous le seuil de 37 min 30 s. LE-40 est close.
- **Le registre** gagne LE-70 à LE-77. LE-70, LE-71 et LE-73 rejoignent LE-63 sous « décision
  appliquée sans en chercher les effets », qui compte désormais sept constats ; LE-76 est le 3e de
  « étape de clôture oubliée par le plan ». Deux portes sont dues, et leur forme revient à Edouard.
  LE-77, close, est le compte de la revue finale, 23 dans le corps de #131 pour 22.
- **Vers `pupitre`**, la `v0.11.0` part seule, après l'étiquette ; les six autres projets la
  prendront à leur prochaine mise à jour. Son message lui fait donner au plan maître ses trois
  sections, scinder sa Tranche 8 en la revue finale et la clôture si Edouard l'accepte dans sa
  session, écrire ses écarts à la forme « accord : », et dire à Edouard que sa règle sans prénom
  contredit les fichiers gérés qui le nomment.

Versions des projets au 13/11/2026, relevées par l'API : `pupitre` est en `v0.11.0` depuis
pupitre#35, fusionnée le 13/11 ; les six autres restent en `v0.10.0`. Le plan maître de `pupitre`
passe `plan.py`, lieux ouverts comme par `--sans-lieux` (81 mécanismes, 43 outils, 3 revues) : sa
Tranche 8 est scindée en la revue finale et la clôture, la Tranche 9, sur l'accord d'Edouard dans
la session de `pupitre`. Une session neuve y a relu les trois sections, qu'aucune revue du plan
n'avait relues. pupitre#36, fusionnée le même jour, excepte de sa règle sans prénom les fichiers
gérés par le modèle et le nom du compte.

Correctif du 14/11 : l'horloge du banc de la cible `serveur` ne vieillit plus (#136), étiqueté
`v0.11.1`. Elle datait les instantanés des tests du 15/10/2026, et la purge de 30 jours, qui lit
la vraie date, les a retirés à partir du 14/11 à 00:00 UTC : le banc était rouge dans `ancrage`,
dans `veille-emploi` et dans le job `mecanique` de ce dépôt (LE-78). Elle tombe désormais la veille
de la vraie date, et un test bats la place dans la fenêtre de la purge. Les projets en cible
`serveur` le reçoivent par leur mise à jour.

Second correctif du 14/11 : le délai du job `tests` de ce dépôt passe de 50 à 60 min, seuil 45 min.
Sur #135, qui ne changeait que `CLAUDE.md` et `docs/registre.md`, il a pris 45 min 52 s sous
Windows, au-delà du seuil de 37 min 30 s et à 4 min de son délai : la suite y a duré 45 min 19 s,
contre 32 min 25 s au push de la clôture du lot 16, pour les mêmes tests. Le lot 17 ajoute des
tests ; Edouard a décidé le 14/11 de monter le délai avant sa première tâche, et de porter
l'avertissement au registre à sa clôture. Rien ne change sous `template/`.

Lot 17 fait le 14/11/2026 : les effets cherchés et les gestes de clôture (#134), étiqueté
`v0.12.0`. Il écrit les deux portes dues du registre : celle de « décision appliquée sans en
chercher les effets » (LE-63, LE-70, LE-71, LE-73), par une section des plans et le relevé des
projets, et celle d'« étape de clôture oubliée par le plan » (LE-76), par les gestes de clôture et
la commande des plans du modèle (PR #139 à #143). Aucune de ses PR ne déclare d'écart à la spec ;
les questions 7 à 9, nées de la revue du plan, et la question 10, posée le 14/11 après #135, ont
reçu le oui d'Edouard le 14/11.
- **« Effets cherchés » et `--neuf`** (#139). `plan.py` lit une quatrième section,
  `## Effets cherchés` : une ligne par décision du plan qui change ce que reçoit un autre lieu,
  `- <décision> — <où elle arrive> — <comment c'est vérifié>`, ou « Aucun. ». L'option `--neuf`,
  distincte de `--sans-lieux`, l'exige d'un plan neuf ; sans elle, son absence ne refuse pas, mais
  la section présente se vérifie, et le résumé compte les effets. L'étape « Les plans » du socle,
  et sa copie ici, passe `--neuf` à un plan ajouté, renommé compris, à la PR comme au push ; un
  plan modifié reste vérifié par `--sans-lieux`. `methode.md` dit les quatre sections, les trois
  sortes de lieux en exemples, et la revue du plan, qui relit chaque effet là où il arrive.
- **Les gestes de clôture** (#140). Un plan neuf, ou qui porte « Effets cherchés », a une unité de
  clôture qui nomme six gestes, chacun reconnu à son expression : le plan supprimé, `CLAUDE.md` ou
  un ADR, le README, les leçons du lot (« leçon » ou « constat »), la fermeture de l'issue, la tête
  relue ; « retire » et « se ferme » ne valent pas (questions 7 et 8). `--cloture MOT` ajoute un
  mot. Un plan de tranche s'en dispense par la ligne
  `` Plan maître : `.claude/plans/<fichier>.md` ``, un plan hors lot par `Hors lot : <raison>` ;
  sans unité de clôture ni l'une de ces lignes, un plan neuf refuse. Le point 5 du cycle porte au
  registre les leçons du lot, le gabarit de PR les nomme dans sa liste de contrôle, et
  `documentation.md` nomme les écarts au rendu de GitHub du texte de l'unité de clôture et des deux
  lignes.
- **Le relevé des projets** (#141). `poste/releve.py` lit par `gh api`, en lecture seule, les
  projets nés du modèle, dépôts privés compris ; il lance sur leurs plans et leurs textes de PR les
  scripts du modèle de leur version et de la tête, et compare leurs règles et leurs fichiers
  gérés. Ses deux rôles, l'inventaire et la mesure de l'effet, ses trois moments, avant une spec ou
  un plan, à la revue finale et à la clôture, et ses codes, 0, 1 et 64, sont dans « Commandes ». Il
  tourne sur le poste, par la session ; `tests/test_releve.py` l'éprouve contre un faux `gh`.
- **Les textes de ce dépôt** (#142). `docs/aligner.md` : un plan en cours garde ses trois sections
  d'avant le lot, jamais « Effets cherchés » après coup, et un plan renommé compte pour neuf.
  « Commandes » donne la commande des plans du modèle, par `--neuf` et les mots `cadrage`,
  `À relire`, `pistes` et `relevé`. LE-63, LE-70, LE-71, LE-73 et LE-76 sont closes : `pupitre`,
  relu par l'API, est en `v0.11.0` et son plan maître passe `plan.py`, et sa règle, relue le 13/11
  puis par le relevé, requiert toujours ses contrôles propres.
- **La revue finale** a lu `cbda229..1bbd98b` en cinq lentilles (la spec, les textes, les cas
  limites, le relevé, les mesures), chaque constat contre-vérifié, puis par une lecture de
  complétude : 29 constats, 25 sans leurs doublons, aucun critique, 3 importants et 22 mineurs. La
  PR #143 en corrige 20, dont les trois importants : le point 5 du cycle, qui disait par une
  relative entre virgules qu'aucun dépôt de données n'a de registre, quand seul un dépôt de la cible
  `donnees` n'en a pas ; un `gh` jamais connecté, qui sort par 4 et faisait rendre 1 au relevé, au
  lieu de 64 ; le test de l'entrée fermée de `gh`, que la capture de pytest rendait vain. Quatre
  vont à la clôture, et un reste tel quel, la case du gabarit de PR, à 107 caractères. La relecture
  des corrections a ramené au code de la spec, avant l'ouverture de #143, un remède de
  contre-vérification : un relevé sans aucun projet rend 0, et le dit (§ 5.4). Aucun job coupé ni
  avertissement de durée dans le lot : sous Windows, le job `tests` a duré au plus 34 min 36 s
  (#139), sous le seuil de 45 min, et 33 min 17 s sur #143.
- **Le relevé de la clôture**, sur `3b7ab38`, rend 0 : 75 dépôts examinés, 7 projets, 7 lus,
  0 non relevé, 0 à lire. Les huit plans en cours gardent à la tête le verdict qu'ils ont à la
  version de leur projet, sept qui passent et un qui refuse déjà ; tous refuseraient s'ils étaient
  neufs, celui d'`ancrage` pour la seule section « Effets cherchés », sa clôture nommant déjà les
  six gestes. Aucun des 249 textes de PR lus ne change de verdict, aucune règle ne perd un contrôle
  géré, aucun fichier géré n'est modifié dans un projet. Deux PR sont ouvertes, et aucune n'ajoute
  un plan ; pupitre#38, un brouillon, en modifie un, que le relevé ne lit pas : relu à la main à la
  revue finale, ce plan passait les `plan.py` de la `v0.11.0` et de la tête.
- **Le registre** gagne LE-79 à LE-89, AM-5 et AM-6, et LE-69 sa seconde preuve. L'avertissement
  de #135 est LE-79, 5e constat de « délai mesuré à vide », que sa porte a vu. Les leçons de
  `pupitre` (LE-80, AM-5), de #138, le correctif de #136 (LE-81, LE-82), de la revue finale (LE-83
  à LE-87) et des revues de tâche (LE-88, LE-89) rejoignent chacune un motif dont la porte est
  écrite, et disent ce qui lui échappe : la troisième pièce d'une ligne de plan, ce qu'une clôture
  livre de plus que ses gestes, une recherche trop étroite, un double installé deux fois, un écart
  que son auteur ne voit pas, un cas limite inconnu de `gh` et du rendu de GitHub, des tests que
  leur environnement rendait vains, le remède d'une revue de tâche appliqué sans relire le code,
  des changements qu'aucun test ne tenait, un échec lu comme un résultat. AM-6, le garde qui
  refuse la simple lecture de la clé des hooks, ouvre un motif neuf. Aucune porte n'est due. Les
  cinq lignes closes par le lot nomment leurs PR (#139, #141 et #142 ; #140 et #142 pour LE-76) et
  la forme de la porte choisie par Edouard le 13/11.
- **Vers les projets**, la `v0.12.0` part vers les sept projets après l'étiquette, chacun avec son
  message, `serveur` d'abord : `ancrage` et `veille-emploi` depuis la `v0.11.1`, `pupitre` depuis
  la `v0.11.0`, les quatre autres depuis la `v0.10.0`, avec ce qu'ont apporté les versions
  d'entre-deux.

Versions des projets au 14/11/2026, relevées par l'API : `ancrage` et `veille-emploi` sont en
`v0.11.1` depuis le 14/11 (ancrage#39, veille-emploi#25). La `v0.11.1`, sans effet hors de la
cible `serveur`, ne fait pas monter les cinq autres : `pupitre` reste en `v0.11.0`, et `serveur`,
`pupitre-donnees`, `ancrage-donnees` et `veille-emploi-donnees` en `v0.10.0`. Une seconde preuve
de la lecture des fermetures par `texte-pr` dans un dépôt privé : serveur#70, PR de clôture d'un
lot, qui ferme une issue, a eu `texte-pr` vert sur « ferme une issue : tête relue égale à la
tête » (LE-69).

Versions des projets au 15/11/2026, relevées par l'API : les sept projets nés du modèle sont en
`v0.12.0` (serveur#73, veille-emploi-donnees#53, ancrage-donnees#217, veille-emploi#29,
pupitre#40, ancrage#42, pupitre-donnees#22), chacun sans conflit ni fichier en trop, sa CI verte à
la fusion. Le message de `serveur` est parti le premier, les six autres après sa fusion, chacun
après une relecture de son projet : quatre avaient changé depuis le relevé de la clôture, et leur
message a été repris. `pupitre` a aligné sa ligne de `CONVENTIONS.md` sur la phrase que proposait
son message, qui omet trois cas de la règle (LE-90). Le plan du lot 3 de `veille-emploi`, dans sa
PR 28, encore en brouillon, est le premier plan que la porte du lot 17 arrête : le `plan.py` de la
`v0.12.0` le refuse par `--neuf`, faute d'« Effets cherchés » et des leçons du lot dans sa clôture,
deux retouches que sa session ajoute avec la correction du plan. Le même jour, sa session a
corrigé ce plan, que le `plan.py` de la `v0.12.0` passe désormais par `--neuf` (87 mécanismes, 24
outils, 16 effets, 10 revues), revérifié par l'API avec `--sans-lieux` ; veille-emploi#28 est
fusionnée.

Lot 18 fait le 16/11/2026 : le journal d'une application survit à son déploiement (#133),
étiqueté `v0.13.0`. Il est né du signal de `veille-emploi`, qui a constaté le 13/11 que la ligne
qui aurait expliqué un défaut de sa prod était partie avec un conteneur remplacé (PR #146 à #148).
Aucune de ses PR ne déclare d'écart à la spec. Edouard a accepté le 16/11 les huit choix de la
section « À relire » de sa PR de clôture, dont deux lectures de la spec (LE-92, LE-93).
- **La copie du journal** (#146). En cible `serveur`, `lancer`, seul geste de `deployer.sh` qui
  remplace le conteneur, copie d'abord le journal de chaque conteneur `app` du projet, en service
  ou arrêté (`dc ps --all --quiet app`) : au déploiement d'un couple neuf, au retour arrière
  automatique d'`echouer`, qui copie la version en échec, et au `--retour`. Tout ce que rend
  `docker logs --timestamps`, les deux sorties, va sous `~/.local/state/<nom>/<env>/journaux/`, en
  700, dans un fichier en 600 nommé `<AAAAMMJJTHHMMSSZ>-<version>-<id12>.log` ; la version se lit
  par un format d'inspection qui n'extrait que `<PREFIXE>VERSION`, jamais tout l'environnement du
  conteneur, qui porte des secrets (`inconnue` sinon). Les 5 copies les plus récentes restent par
  environnement : 75 Mo au plus avec le plafond du compose géré, 90 Mo avec le journal en service.
  Une copie qui échoue est notée au journal du déploiement, son `.partiel` retiré, et n'arrête
  rien : le code de `lancer` reste celui du `dc up`. Sa limite : les lignes écrites entre la copie
  et l'arrêt du conteneur, pendant le tirage d'une image absente puis le délai d'arrêt, jusqu'à
  10 s.
- **`exploitation.md`**, semé (#147, #148) : le journal en service, jusqu'à 15 Mo ; les copies,
  combien chaque déploiement en fait, et qu'aucune durée n'est garantie ; où se lit la cause d'une
  copie manquée ; `2>&1` pour filtrer ; la ligne « Copies du journal » du tableau « Ce qui
  tourne » ; et, dans « Tout arrêter », que `down` retire les conteneurs sans copie. Un projet qui
  naît le reçoit ; un projet déjà né, par son message.
- **Le banc** (#146, #148). Le double de `docker` connaît trois états du conteneur, son
  identifiant, `logs` et l'inspection de la version ; `deployer.bats` gagne 27 tests (26 sans
  sauvegardes), et les deux horloges d'`aide.bash` refusent un second double de `date` au lieu de
  boucler, ce qui clôt LE-82.
- **L'épreuve sur un vrai Docker** (#146, #148), dans le job `fausse-app` : le plafond de
  `json-file` réduit, le journal de la prod tourne, et la copie garde la ligne de démarrage, écrite
  dans un fichier déjà tourné ; un conteneur arrêté par `docker stop` est copié par le `--retour`
  qui suit ; le nom de chaque copie se lit en entier, version comprise. C'est prouvé sur le moteur
  29.4.2 du runner, en magasin classique, et non sur le 29.5.3 de la cible, où `menage-cible` ne
  lance que l'épreuve du ménage : les premières copies des projets sur la cible n'en prouveront
  que le cas ordinaire, ni la rotation ni le conteneur arrêté (S-5).
- **Le test de `2>&1`** (#147, #148), dans `tests/test_depot_modele.py` : sur chaque fichier texte
  suivi de `template/`, il refuse un `docker logs` qu'un tube suit sans `2>&1` ni `|&`. Il cherche
  `docker`, ses options globales, puis `logs`, n'importe où sur la ligne, la lit par segments (les
  citations, les substitutions, Jinja), suit une commande citée que lance `ssh` ou un shell par
  `-c`, et lit une ligne finie par `\` jointe à la suivante, puis seule ; `docker compose logs`
  reste hors de la règle, et un second test borne son temps. Sa docstring nomme ses limites
  connues, sans que leur liste soit close : d'abord une commande construite à l'exécution (une
  variable, une fonction, un alias), qu'aucune lecture du texte ne voit. La session a lu le § 5 de
  la spec comme une recherche dans le texte, sans déclarer d'écart ; la relecture des corrections
  le voulait déclaré (LE-92).
- **La revue finale** a lu `609f70f..1910b1d` en cinq lentilles (la spec, le shell, le banc, le
  relevé, les mesures), chaque constat contre-vérifié, puis par une lecture de complétude :
  24 constats, aucun critique, un important (S-1, la règle de `2>&1`) et 23 mineurs. 13 sont
  corrigés dans #148, 8 vont aux messages, 4 à la clôture et 3 restent tels quels, un constat
  pouvant avoir deux lieux. La phrase « un déploiement en échec en fait deux », que la spec écrit
  au § 3.1 et reprend au § 5, contredisait le premier déploiement en échec que décident ses § 3.1,
  § 3.2 et § 8 : le texte suit le comportement, sans écart déclaré (LE-93). La relecture des
  corrections a pris quatre temps, une relecture puis trois relectures ciblées : les deux
  premières trouvaient des formes que la règle de `2>&1` ne voyait pas, la troisième seulement
  des phrases de sa docstring, la quatrième rien (LE-99). #148 compte 42
  mutants, tous tués, et deux mutants équivalents restés vivants. Aucun job coupé ni avertissement
  de durée dans le lot : sous Windows, le job `tests` a duré au plus 35 min 44 s, sous le seuil de
  45 min, ce qui clôt LE-79 ; `mecanique`, au plus 11 min 14 s, sous 15 min.
- **Le relevé**, sur `2f28161`, rend 1 : 75 dépôts examinés, 7 projets, tous lus, tous en
  `v0.12.0`, et une PR ouverte d'un dépôt privé qui ajoute un plan. Sa ligne « fichiers gérés » ne
  couvre ni `deploiement/` ni `tests/deploiement/`, où sont les quatre fichiers gérés du lot
  (R-4) : la préparation des messages les a rendus avec les réponses d'`ancrage` et de
  `veille-emploi`, identiques à la `v0.12.0` dans les deux projets, et a simulé leur mise à jour
  vers `2f28161` : seuls `.copier-answers.yml` et ces quatre fichiers changent, sans conflit. La
  piste « Comparer les fichiers reçus à l'étiquette » s'étend aux gabarits.
- **Le registre** gagne LE-91 à LE-100 ; LE-79 et LE-82 sont closes. Aucune porte n'est
  due : chaque leçon va sous un motif dont la porte est écrite, ou qui n'a pas son 3e constat.
  LE-91 est le premier constat de « décision appliquée sans en chercher les effets » depuis la
  porte du lot 17, un chemin d'exécution qu'« Effets cherchés » n'a pas nommé ; LE-95 ouvre un
  motif neuf, « renvoi d'une tâche à l'autre perdu en route ». LE-89 reste ouverte : la revue de
  la tâche 1 a trouvé une horloge en échec lue comme un horodatage, corrigée avant la fusion de
  #146 (LE-100).
- **Vers les projets**, la `v0.13.0` part vers `ancrage` et `veille-emploi` seuls, après
  l'étiquette, chacun avec son message ; les cinq autres la prendront à leur prochaine mise à jour,
  sans effet. La copie commence au premier déploiement d'une version qui la porte : en staging dès
  la fusion de la mise à jour, en prod à la prochaine étiquette de chaque projet, sans date. Les
  copies se constatent par un geste 👤 d'Edouard, en lecture seule, dont le message donne les
  commandes : la session du projet, qui ne lit pas le serveur, note ce qu'il rapporte (S-6). Après
  la première étiquette qui porte la mise à jour, un retour arrière par étiquette vers un commit
  d'avant elle lance encore l'ancien `deployer.sh`, qui ne copie pas (LE-91).

Versions des projets au 17/11/2026, relevées par l'API : `ancrage` et `veille-emploi` sont en
`v0.13.0` depuis le 17/11 (ancrage#54, veille-emploi#32). Chaque mise à jour ne change que
`.copier-answers.yml`, les quatre fichiers gérés du lot et `docs/exploitation.md`, qui reçoit le
texte proposé par son message ; la CI de chaque fusion est verte. Les cinq autres projets restent en
`v0.12.0`, que la `v0.13.0`, sans effet hors de la cible `serveur`, ne fait pas monter. Les deux
messages sont partis le 17/11, chacun après un relevé neuf de son projet : la branche principale
d'`ancrage` avait avancé depuis leur préparation, et son message a été repris, ses lieux relus et sa
simulation refaite sur l'étiquette. Les copies se constatent par le geste 👤 d'Edouard, en lecture
seule, la session du projet notant ce qu'il rapporte (S-6).
- **`ancrage`**, en staging le 17/11, après sa fusion : une copie en 600, dans un dossier en 700, la
  ligne « journal du conteneur … copié » au journal de la sonde, et un premier horodatage antérieur
  au déploiement. En prod le même jour, après son étiquette `v0.18.0` puis une étiquette de
  données : deux déploiements, deux copies. La première est celle de l'ancien conteneur, en
  `0.17.0`, faite par le nouveau `deployer.sh` ; la seconde, celle du conteneur qu'un commit de
  données seul a remplacé. Le dossier des copies n'existait pas avant le premier.
- **`veille-emploi`**, en staging, relevé le 18/11 par les commandes écrites avec le client `ssh`
  de Windows : deux copies du 17/11, en 600, dans un dossier en 700, chacune au nom attendu et avec
  sa ligne au journal de la sonde. La première est celle du conteneur qui servait avant la mise à
  jour, faite par le nouveau `deployer.sh` au déploiement de sa fusion ; la seconde, celle du
  conteneur que ce déploiement a démarré, remplacé par la fusion suivante (veille-emploi#33) : son
  premier horodatage suit de 3 s la première copie. En prod, relevé le même jour, après son
  étiquette `v0.4.0`, la première qui porte sa mise à jour : une copie, en 600, dans un dossier en
  700, avec sa ligne au journal de la sonde. C'est celle du conteneur en `0.3.0`, dont elle porte
  la version dans son nom, et non celle qu'on déploie ; son premier horodatage est celui du
  déploiement de la `v0.3.0`, quatre jours plus tôt : elle couvre toute la vie du conteneur.
- **Non constatés sur la cible** : la limite des 5 copies, un retour arrière, un conteneur arrêté
  (S-5), et le contenu des copies, que personne n'a lu.
- **Le geste lui-même** : les messages disaient de passer les commandes à `ssh` sous Git Bash comme
  sous PowerShell 5.1. Lancée par `!`, une commande passe par le `ssh` de Git Bash, qui ne voit pas
  l'agent de Windows : la première d'Edouard a été refusée. Le client de Windows, nommé en entier,
  passe ; un complément l'a dit à `veille-emploi` avant sa constatation (LE-101).

Lot 19 fait le 20/11/2026 : distinguer d'un coup d'œil le staging de la prod (#151), étiqueté
`v0.14.0`. Il vient d'une idée d'Edouard du 21/10, devenue l'issue #151 le 18/11 : en cible
`serveur`, un relais du modèle, placé devant le staging seul, y pose trois marques, un bandeau
orange « TEST », « test » devant le titre et le nom de l'application installée, des icônes
recolorées, et la prod n'en porte jamais aucune (PR #152, #153 et #154). Les PR #152
et #153 déclarent onze écarts à la spec, tous accordés par Edouard : quatre le 18/11, avec le
plan, sept le 19/11.
- **Le relais** (#152). `scripts/modele/marque.py`, géré, rendu en cible `serveur` seulement, en
  bibliothèque standard de Python, transmet tout à `app`, sauf trois retouches : la page (le lien de
  la feuille du bandeau, le titre), le manifeste (`name`, `short_name`, ses icônes vers
  `/.marque/icone?de=`) et les icônes PNG ou SVG, recolorées sur une rampe orange, l'icône générique
  pour ce qu'il ne sait pas lire. Il répond lui-même sous `/.marque/` (la feuille, l'icône, sa
  santé) : aucune cible sous ce chemin ne parvient à l'application, telle qu'elle arrive, décodée ou
  normalisée. Son journal n'écrit jamais un chemin, une requête, un en-tête ni une adresse. Il ne
  passe jamais une requête pour deux : un cadrage de corps illisible ou des en-têtes mal formés
  rendent 400 et ferment la connexion. Ses bornes : la page et le manifeste à 5 Mio, une icône à
  4 Mio de pixels et 5 Mio lus, deux icônes en mémoire, une recoloration à la fois, un cache de
  32 icônes et 16 Mio. Sa docstring nomme ses limites connues, sans que leur liste soit close ;
  `tests/test_marque.py` porte 107 tests.
- **Le branchement** (#152). `deploiement/compose.marque.yml`, géré : le service `marque` prend à
  `app` le port de la boucle locale et l'alias du tunnel (`ports: !reset []`,
  `networks: !override`), sur `python:3.12-alpine` épinglée par empreinte, avec `init: true` et
  `mem_limit: 128m`, le script monté en lecture seule (`create_host_path: false`). `dc` ne l'ajoute,
  en dernier, que quand `compose.env` porte `<PREFIXE>RELAIS`, l'empreinte du script, que
  `deployer.sh` n'écrit qu'en staging, `--retour` compris. Juste après le verrou, `deployer.sh`
  refuse en staging un script absent, illisible ou non lisible par tous, sans rien changer ;
  `refuser_image_heritee` refuse la ligne posée dans le shell. La santé du staging passe par le
  relais. `!reset` et `!override` demandent Compose 2.24.4 : la cible a `2.26.1-4`, et le geste 👤
  d'Edouard, en lecture seule, y a rendu le 18/11 la même configuration que Compose 2.26.1 amont.
- **Le banc et l'épreuve** (#152). Six tests `relais_*` dans `deployer.bats`, dont « jamais en
  prod » et le retour depuis un précédent sans la ligne ; trois cas de `dc` et le refus du shell
  dans `lib.bats`. Le job `fausse-app` installe Compose 2.26.1, celui de la cible, d'après sa
  version et son empreinte (`tests/modele/installer_compose.py`, `tests/modele/docker-cible.env`),
  puis le point 6 de l'épreuve des données passe par les chemins des projets déjà nés, en cinq
  étapes : le staging sans marque ; un échec forcé, dont le retour revient sans marque ; un
  déploiement marqué (la page, le manifeste, l'icône recolorée, la santé, puis un script changé qui
  recrée le relais) ; un second échec, qui garde le relais ; « Tout arrêter ». En prod ensuite,
  aucun relais. C'est prouvé sur le moteur 29.4.2 du runner, sous le binaire amont : sur la cible,
  la construction `2.26.1-4` n'est éprouvée que sur sa configuration, et `docker-init` jamais
  (B-6, C-10, une piste).
- **Les textes** (#153). `methode.md`, géré, gagne « La marque du staging » : les trois marques, ce
  que le relais lit des icônes du projet, `/.marque/`, ce que `compose.marque.yml` retire à `app` en
  staging, tout port et tout réseau que le projet lui ajoute, le nom `marque` réservé, et la
  politique de sécurité du contenu, qui doit admettre une feuille de la même origine.
  `exploitation.md`, semé, gagne sa section, ses limites en liste non close, la ligne « Marque » du
  tableau, le refus du script dans « Débloquer un déploiement », `--remove-orphans` au `down` du
  staging de « Tout arrêter », et « la marque d'échec » là où « la marque » prêtait à confusion.
  M-0003 et M-0004 sont amendés : en staging, le relais tient le port et l'alias, et le ménage ne
  retire jamais son image. Un projet déjà né reçoit `methode.md` et les ADR par sa mise à jour,
  `exploitation.md` par son message.
- **Les écarts à la spec.** #152 en déclare dix, #153 un. Quatre lectures du plan (P11), accordées
  le 18/11 : le plafond de 4 Mio compte les pixels ; le 400 couvre aussi un octet de la cible hors
  de 0x21-0x7E et une cible qui ne commence pas par une seule `/` ; l'ordre de l'épreuve (LE-103) ;
  la lecture d'une icône bornée à 5 Mio. Sept accordés le 19/11 : un cadrage de corps illisible,
  des en-têtes mal formés et une méthode qu'`http.client` refuse rendent 400, nés de l'exécution ;
  l'alias lu depuis le réseau du tunnel, et non par `docker network inspect`, qui ne montre pas les
  alias ; un manifeste de plus de 5 Mio passé sans marque, et une réponse précoce suivie d'une
  fermeture, qui rend 502, de la revue finale (LE-105) ; dans #153, la limite du service worker :
  accepter la mise à jour ne suffit pas toujours, un précache ne retéléchargeant que ce dont la
  révision change (LE-104).
- **La revue finale** a lu `7ece86d..0851c4c` en cinq lentilles (la spec et les textes, le
  relais, le branchement et l'épreuve, par des agents, chaque constat contre-vérifié ; le relevé et
  les mesures, par la session), puis par une lecture de complétude : 41 constats, aucun critique,
  trois importants (S-1, quatre écarts que #152 taisait ; S-2, deux écarts mal décrits ; C-2, une
  mesure des fichiers gérés que le plan n'écrivait pas) et 38 mineurs. Les contre-vérifications
  n'ont réfuté aucun des 30 constats des lentilles ; elles ont ramené R-1 et B-1 d'important à
  mineur, et laissé B-6 plausible. Les corrections ont rejoint les deux PR, au lieu d'une PR de
  corrections : celles du relais dans #152 (`d928bda` à `5298c55`), relues en trois rondes,
  celles des textes dans #153, en deux ; chaque fois, la session elle-même, et non un relecteur
  neuf, a relu la dernière ronde, sans rien demander. La CI de #152 a refusé `5298c55` : le `ruff`
  du projet rendu voyait ce que le `ruff check .` du modèle ne lit pas, et `e675bbe`, que la
  session a écrit, l'a corrigé ; il n'est tenu que par la CI et un mutant (LE-108). Puis la
  relecture fraîche des messages a trouvé la limite du service worker fausse pour un précache, et
  le gabarit est corrigé avant l'étiquette (M-1, M-2, LE-104). Deux lignes du plan prêtaient à
  l'épreuve, au banc et au test du rendu ce qu'ils ne font pas : le geste qui arrête l'`app` d'un
  environnement bloqué et le cas limite de `create_host_path: false` ne sont prouvés que par deux
  essais de la lentille du branchement, sous Compose 2.26.1 amont, hors de la CI (B-7, C-9,
  LE-106).
- **La précaution de l'effacement** (#154), une PR `fix` décidée après la revue
  finale. La relecture fraîche des messages a vu que l'effacement des données du site du staging,
  que la limite du service worker d'`exploitation.md` donnait sans précaution, peut effacer aussi
  celles de la prod, sous le même domaine (M-3). La limite dit désormais de faire d'abord
  synchroniser ce que la prod garde hors ligne, et de ne pas confirmer si l'écran d'effacement
  nomme le domaine commun ou la prod. La portée réelle de l'effacement sous Chrome pour Android
  n'est pas éprouvée : la constatation d'`ancrage` la dira (LE-113, une piste).
- **Les durées** : aucun job coupé ni avertissement de durée dans les six exécutions de `ci.yml`
  des trois PR, une tentative chacune, ni aux push de leurs fusions, `b499b36`, `3442607` et
  `6b65791`. Sous Windows, le job `tests` a duré au plus 37 min 44 s (#153), sous le seuil de
  45 min ; `mecanique`, au plus 11 min 30 s sur les PR et 11 min 33 s au push de `b499b36`, sous
  15 min ; `fausse-app`, qui n'a pas l'étape « Durée du job », de 3 min 45 s à 4 min 32 s par ses
  horodatages, contre 1 min 19 s au push de `7ece86d`, avant le lot, sous son délai de 15 min.
  Seule `5298c55` a été rouge, sur `tests`, sous les deux systèmes (LE-108).
- **Le relevé de la clôture**, sur `6b65791`, le 19/11, rend 0 : 76 dépôts examinés, 7 projets,
  7 lus, 0 non relevé, 0 à lire ; `ancrage` et `veille-emploi` sont en `v0.13.0`. Sa ligne
  « fichiers gérés » ne compare que 2 des 12 fichiers gérés du lot (LE-107) : la préparation des
  messages a simulé la mise à jour des deux projets vers `3442607`, depuis leurs têtes du 19/11 ;
  seuls `.copier-answers.yml` et les 12 fichiers gérés du lot changent, sans conflit, et
  `docs/exploitation.md`, semé, reste inchangé ; #154 ne change que ce fichier semé et son test.
- **Le registre** gagne LE-102 à LE-113 ; LE-107 se clôt dans le lot. Aucune porte n'est due :
  chaque leçon va sous un motif dont la porte est écrite, ou qui n'a pas son 3e constat. Cinq
  rejoignent « mécanisme décrit sans relire son code », qui compte désormais quinze constats : des
  phrases et une décision de la spec qui résument mal un comportement, dont la limite du service
  worker, passée dans un gabarit (LE-102 à LE-104), la troisième pièce de trois lignes du plan
  (LE-106), un remède écrit dans une consigne sans essai (LE-109). LE-105 rejoint « écart à la spec
  mal pesé », LE-108 et LE-112 « contrôle passé à vide », LE-111 et LE-113 « comportement d'un
  outil supposé », et LE-107 « renvoi d'une tâche à l'autre perdu en route », dont c'est le 2e
  constat ; LE-110, la sortie d'une suite coupée par `| tail` avant d'être lue, ouvre un motif
  neuf. Les critères de sortie de LE-97 et de LE-100, qui visaient ce lot, ne sont pas tenus.
- **Vers les projets**, la `v0.14.0` part vers `ancrage` et `veille-emploi` seuls, après
  l'étiquette, chacun avec son message ; les cinq autres la prendront à leur prochaine mise à jour,
  sans effet. La marque paraît en staging au premier déploiement qui suit la fusion de la mise à
  jour, jamais en prod. Edouard la constate sur son Android, dans un onglet puis installée, et
  constate son absence en prod ; chez `ancrage`, dont le précache garde le manifeste d'avant le
  relais, il efface les données du site du staging, après avoir fait synchroniser ce que la prod
  garde hors ligne, et s'arrête si l'écran d'effacement nomme le domaine commun ou la prod
  (#154, LE-113). La session du projet note ce qu'il rapporte, sans lire le serveur.
  Le premier déploiement marqué tire l'image du relais de Docker Hub : un tirage en échec met le
  couple en échec, et la sonde ne le retente pas (une piste). Si ce déploiement échoue pour une
  autre cause, le retour automatique sert le staging sans marque, jusqu'au déploiement suivant.
- **Les « À relire » de la clôture** : Edouard a accepté le 20/11, tels quels, les 17 choix de la
  section « À relire » de sa PR de clôture, dont l'accord de l'écart de #153, que la session avait
  déduit de sa réponse au message qui le décrivait.

Versions des projets au 21/11/2026, relevées par l'API : `ancrage` et `veille-emploi` sont en
`v0.14.0` depuis le 21/11 (ancrage#79, veille-emploi#37). Chaque mise à jour ne change que
`.copier-answers.yml`, les 12 fichiers gérés du lot et `docs/exploitation.md`, qui reçoit le texte
proposé par son message et ce qui est propre au projet ; la CI de chaque fusion est verte. Les cinq
autres projets restent en `v0.12.0`, que la `v0.13.0` et la `v0.14.0`, sans effet hors de la cible
`serveur`, ne font pas monter. Les deux messages sont partis le 20/11, après la publication, chacun
après un relevé neuf de son projet : `ancrage` a avancé trois fois pendant leur préparation (la
clôture de son lot M7, puis le plan et la clôture de son lot M8), et son message a été repris trois
fois, ses lieux relus et sa simulation refaite sur sa nouvelle tête. Les premiers déploiements
marqués des deux projets ont réussi sur la cible, sous sa construction `2.26.1-4` de Compose : le
relais y tourne, `init: true` compris. La marque est constatée sur le staging par les commandes de
la session de chaque projet, puis par Edouard sur son Android, dans un onglet puis installée, avec
son absence en prod ; chaque fois, sa réponse vaut pour les cinq étapes du message, sans détail
étape par étape.
- **`ancrage`**, le 21/11 : en staging, le relais répond sous `/.marque/sante`, le titre et le
  manifeste disent « test · ancrage », et la page lie la feuille du bandeau. Sa prod, en `v0.20.0`,
  n'en porte rien ; sous `/.marque/`, elle sert la page de l'application, comme à toute adresse
  inconnue, ce que disait son message. Edouard a fait d'abord synchroniser la prod, puis effacé les
  données du site du staging par le chemin que donnait le message, depuis un onglet du staging (le
  menu ⋮, « Site controls », « Cookies », puis « Delete ») : l'écran nommait l'adresse du staging
  seule, et la prod n'a rien perdu (LE-113). L'application du staging, réinstallée, porte le nom
  « test ancrage » et l'icône orange : le précache ne garde plus l'ancien manifeste.
- **`veille-emploi`**, le 21/11 : en staging, le relais répond, la page de connexion a « test · »
  devant son titre et lie la feuille, et le manifeste dit « test Veille ». Sa prod, en `0.4.0`, n'en
  porte rien, et `/.marque/sante` y rend 404. Son service worker ne garde aucune page : un
  rechargement suffit, sans effacement. Le relais réécrit le manifeste avec une espace après chaque
  deux-points, que la console sert sans : une vérification qui le lit admet les deux formes, comme
  celle du message.
- **Non constatés sur la cible** : un tirage en échec de l'image du relais, le retour d'un
  déploiement marqué en échec, le retrait de ses orphelins, et les limites d'`exploitation.md`.

Prochain, au choix d'Edouard :
- le second temps du travail sur la documentation, un lot « documentation » avec sa spec : l'« État »
  réduit du `CLAUDE.md` semé et le journal des versions du modèle ; dans le README, le refus d'une
  copie qui se périme (un arbre de fichiers, une heure, une version) et le signal d'une issue citée
  au futur mais fermée ; la ligne « Confirmation » et le régime des ADR ; les blocs engendrés. La
  piste « Le second temps de la documentation » y ajoute trois relevés des projets, et une
  contradiction d'avant le lot 17 ;
- le lot 3 (la cible `statique`) ;
- le lot 5 (`partition` aligné en cible `aucune`) ;
- le lot 7 (`creche-planner` aligné en cible `aucune`) ;
- le workflow `publier`, qui ferait publier Edouard depuis son téléphone : sa piste a pour
  déclencheur un lot choisi par Edouard ;
- les constats que les portes du lot 15 laissent ouverts, dont un lot suivant pèse les motifs :
  LE-49 (un écart que son auteur ne reconnaît pas), LE-50 (le retrait des images, dans `serveur`),
  LE-54 et LE-61 (des textes que la section du plan ne couvre pas : une piste, un texte de clôture,
  une docstring, `documentation.md`), LE-57 (un cas limite inconnu), LE-65 et LE-66 (une commande
  que `CLAUDE.md` prescrit à une session), LE-74 (un comportement d'outil annoncé hors de la section
  du plan), LE-58 et LE-75 (un contrôle local qui diffère de celui de la CI) ; LE-64, né de la
  revue finale, avec la porte que propose le registre ; et LE-69 (une épreuve renvoyée après le
  lot, qui n'exerce pas le cas), né de la relecture de la clôture ;
- ceux que le lot 17 laisse ouverts, de même : LE-83, avec LE-49 (un écart que son auteur ne
  reconnaît pas) ; LE-80 et LE-86 (un texte que « Mécanismes annoncés » ne couvre pas : la
  troisième pièce d'une ligne de plan, le remède d'une revue de tâche) ; LE-84 et LE-87 (un
  comportement d'outil supposé, hors de ce que le plan nommait : un `gh` jamais connecté, quatre
  formes du rendu de GitHub) ; LE-81, LE-85, LE-88 et LE-89 (un contrôle qui passe sans voir ce
  qu'il doit voir : une recherche trop étroite, des tests que leur environnement rendait vains, des
  changements qu'aucun test ne tenait, un échec lu comme un résultat) ; AM-5 (ce qu'une clôture
  livre de plus que ses gestes, avec sa piste) et AM-6 (le garde et la simple lecture de la clé des
  hooks) ;
- ceux que le lot 18 laisse ouverts, de même : LE-92, avec LE-49 et LE-83 (un écart que son auteur
  ne reconnaît pas : une liste du plan qui rend une promesse de la spec) ; LE-91 (un chemin
  d'exécution qu'« Effets cherchés » n'a pas nommé, le premier constat du motif depuis sa porte) ;
  LE-93 et LE-96, avec LE-86 et LE-90 (un texte que « Mécanismes annoncés » ne couvre pas : une
  phrase de la spec qui résume un comportement, un Ruling écrit sans essayer le cas) ; LE-99, avec
  LE-57, LE-84 et LE-87 (un cas limite inconnu : la grammaire du shell, lue par le texte) ; LE-97
  et LE-100, avec LE-88 et LE-89 (un contrôle qui passe sans voir ce qu'il doit voir : des gardes
  qu'aucun test ne tenait, une horloge en échec lue comme un horodatage, deux mécanismes revenus
  d'un lot à l'autre) ; LE-101, avec LE-57, LE-84, LE-87 et LE-99 (un comportement d'outil supposé
  dans un geste qu'un message donne à lancer : le `ssh` de Git Bash, sans l'agent de Windows) ;
- ceux que le lot 19 laisse ouverts, de même : LE-102, LE-103 et LE-104, avec LE-86, LE-90 et
  LE-93 (un texte que « Mécanismes annoncés » ne couvre pas : des phrases de la spec qui résument
  un comportement, dont la limite du service worker passée dans un gabarit, et l'ordre de son
  épreuve) ; LE-106, avec LE-80 (la troisième pièce d'une ligne de plan : deux tests et le relevé
  auxquels le plan prêtait ce qu'ils ne font pas) ; LE-109, avec LE-86 et LE-96 (un remède écrit
  dans une consigne sans essayer le cas) ; LE-105, avec LE-49, LE-83 et LE-92 (un écart que son
  auteur ne reconnaît pas : quatre écarts tus, deux mal décrits) ; LE-108, avec LE-58 et LE-75 (un
  contrôle local plus étroit que celui de la CI : le `ruff` du projet rendu) ; LE-112, avec LE-88
  et LE-97 (des valeurs et des gardes qu'aucun test ne tenait, revenues au lot suivant) ; LE-111,
  avec LE-57, LE-84, LE-87 et LE-99 (un cas limite inconnu : le chemin réservé et les balises
  HTML, lus par le texte) ; LE-110, le premier constat d'un motif neuf (la sortie d'un contrôle
  coupée avant d'être lue).

Le cadrage est dans `docs/cadrage.md` ; ce que les lots ont appris, dans `docs/registre.md`.

## Commandes

- `python -m pytest -q` : les tests, environ 6 à 8 minutes sous Ubuntu et 20 à 33 sous Windows,
  mesurées en CI, sans `tests/test_mecanique.py`, sur la PR #118, mais 45 sous Windows sur #135. `tests/test_mecanique.py` lance
  les tests bats d'un projet rendu dans une image Docker : il lui faut Docker avec un serveur Linux,
  et il saute sans lui.
- `ruff check .` : le style.
- `gh run rerun <id> --job <databaseId>` : relancer le seul job de la CI coupé à son délai
  (`timeout-minutes`), le `databaseId` lu par `gh run view <id> --json jobs` (le numéro de l'URL du
  job ne convient pas, dit `gh run rerun --help`), après avoir vérifié que l'étape coupée est
  « cancelled », et non en échec : un échec se lit et se corrige, il ne se relance pas. La
  documentation de GitHub dit seulement qu'il annule un job à son délai ; l'étape coupée était
  « cancelled » sur le job coupé du 31/10 (LE-40). Une exception à « un échec ne se relance pas »,
  la panne d'un service tiers : l'échec est lu dans le journal, sa cause est hors du dépôt (un 504
  ou un 503 de GitHub Releases, au lot 15), et le service répond de nouveau (la même adresse rend
  200 depuis le poste) ; on relance alors le seul job par `--job`, ou `--failed` quand tous les
  jobs en échec de l'exécution ont cette cause. Jamais pour `texte-pr`, qui se relit par une
  retouche du texte de la PR (`methode.md`, « Ne jamais relancer `texte-pr` »).
- `gh run view <id> --attempt <n>` : la revue finale de chaque lot relève les avertissements de
  durée des exécutions du lot, dans les annotations de chaque tentative, n allant de 1 au champ
  `attempt` de l'exécution (`gh run view <id> --json attempt`). Sans `--attempt`, `gh run view` ne
  montre que celles de la dernière tentative : un job qu'elle n'a pas relancé n'y porte aucune
  annotation (éprouvé le 08/11 avec gh 2.93.0, sur l'exécution 42467400054, à trois tentatives).
  Chaque job qui porte l'étape « Durée du job » avertit au-delà des trois quarts de son délai, et
  personne d'autre ne lit un avertissement sur une exécution verte (`SessionStart` n'affiche que
  le rouge).
- `poste\Tester-Nouveau-Projet.ps1 -SansPoste -SourceModele <ce clone>` : le test du script de
  création, sans `gh`, sans la liste privée ni l'index réel. Il rend le modèle au `HEAD` du clone,
  changements non validés et fichiers non suivis compris : Copier les ajoute, avec un
  `DirtyLocalWarning`. Valider avant, pour éprouver la tête qui part. Sans `-SansPoste`, il lance
  aussi le script à blanc, sur le poste d'Edouard. `tests/test_poste.py` le lance, et compare les
  bits d'exécution du premier commit à ceux du modèle : sous Windows seulement ; ailleurs, seul le
  contrôle du BOM tourne.
- `python -B template/scripts/modele/plan.py` : le contrôle d'un plan neuf, ses sections et sa
  clôture (`methode.md`, « Les outils »), par cette commande, sur une seule ligne :

  ```sh
  python -B template/scripts/modele/plan.py --racine . --depot serveur=../serveur --neuf --cloture cadrage --cloture "À relire" --cloture pistes --cloture relevé <plan>
  ```

  Il faut une option `--depot <dépôt>=../<dépôt>` par dépôt que le plan cite ; un plan accepté se
  revérifie sans `--neuf`. Les plans du modèle vivent dans `Documents\00-boite-de-reception\`,
  hors du dépôt : l'étape « Les plans » de la CI n'en trouve aucun ici. La session lance cette
  commande depuis le clone principal, avant de soumettre un plan à Edouard et après chaque
  correction. Dans ce dépôt, une ligne d'« Effets cherchés » dont le lieu est un projet cite le
  relevé (`poste/releve.py`) dans son troisième morceau. La clôture d'un plan du modèle ne
  supprime aucun plan, et le dit (« le plan, hors du dépôt, n'est pas supprimé : son en-tête est
  mis à jour ») : le geste « le plan supprimé » y trouve le mot qu'il cherche.
- `python -B template/scripts/modele/texte_pr.py --fermetures "$fermetures"` : le contrôle du texte
  d'une PR avant de l'ouvrir (`methode.md`, « Éprouver le texte avant d'ouvrir la PR »). Ce dépôt
  n'a pas de `scripts/` à sa racine : le bloc de la méthode s'y lance avec ce chemin, depuis la
  racine du clone ou du worktree, sous Git Bash, une fois la branche envoyée, le corps dans un
  fichier UTF-8 sans BOM, hors du dépôt :

  ```sh
  corps='<fichier du corps>'
  fermetures="$(mktemp)"
  printf '%s' '{"data":{"repository":{"pullRequest":{"closingIssuesReferences":{"totalCount":0,"nodes":[]}}}}}' > "$fermetures"
  CORPS="$(cat "$corps")" AUTEUR="$(gh api user --jq .login)" TETE="$(git rev-parse HEAD)" \
    python -B template/scripts/modele/texte_pr.py --fermetures "$fermetures"
  ```

  Avec `"totalCount":1` à la troisième ligne, elle éprouve la tête relue de la PR de clôture. Elle
  n'éprouve ni le format du titre ni la confidentialité, que `texte-pr` contrôle aussi.
- `python -B poste/releve.py [--depuis <étiquette>] [--prs N]` : le relevé des projets nés du
  modèle, depuis la racine du clone, sous Git Bash, `gh` connecté. Il lit GitHub par `gh api`, en
  lecture seule, dépôts privés compris, ce que la CI ne peut pas : il tourne sur le poste, par la
  session. Il lance sur ce qu'il lit les scripts du modèle de deux versions, celle de chaque projet
  et la tête du clone (son `HEAD`). Ses deux rôles : l'inventaire, avant une spec ou un plan,
  quand la tête ne porte pas encore le changement (les règles des projets, leurs plans en cours,
  leurs fichiers gérés modifiés) ; la mesure de l'effet de ce que la tête change. Ses trois
  moments : avant de soumettre une spec ou un plan, pour en écrire les « Effets cherchés » ; à la
  revue finale, dont il est une lentille ; à la clôture, dont la PR cite sa sortie. Une PR n'en
  cite que des comptes et des noms de dépôts publics, après la porte de confidentialité : ni les
  noms des plans ni les numéros de PR des dépôts privés. Il rend 1 quand quelque chose est à lire
  (un verdict qui change, une PR ouverte qui ajoute un plan, un contrôle géré absent d'une règle,
  un fichier géré modifié dans un projet), ou que quelque chose n'est pas relevé (une erreur de
  l'API, une version absente du clone : `git fetch --tags`, un script du modèle qui plante, le
  dossier temporaire non retiré), 0 sinon. Il rend 64 pour une erreur d'usage : `gh` absent ou sans
  accès (un 401, ou `gh` qui sort par 4, jamais connecté), un dossier qui n'est pas un clone du
  modèle qu'il sait lire. Les plans en cours qui « refuseraient s'ils étaient neufs » sont une
  information : ils ne rendent pas le code 1, comme les contrôles propres d'une règle, et comme la
  ligne « aucun projet né du modèle relevé », d'un relevé qui n'en trouve aucun, par exemple sous un
  `--compte` qui n'est pas celui de `gh` : il rend alors 0. Parmi les fichiers gérés, seuls les
  dossiers exclus des formateurs sont comparés, pas le gabarit de PR ni les autres fichiers gérés
  hors d'eux. Par défaut, il compare ceux que le modèle change entre la version de chaque projet et
  la tête, et un projet à la version de la tête n'en montre aucun. `--depuis <ancienne étiquette>`
  ouvre cet intervalle pour tous les projets, chacun comparé au modèle à sa version : il compare les
  fichiers gérés que le modèle a changés depuis cette étiquette, et un fichier géré que le modèle
  n'a pas changé depuis elle n'est pas comparé, quelle que soit l'étiquette. Ce n'est donc pas un
  inventaire complet des fichiers gérés. `--prs N`, de 1 à 100, dit combien de PR récentes passent
  par les deux `texte_pr.py` (50 par défaut). `tests/test_releve.py` l'éprouve contre un faux `gh`.
- `copier copy --vcs-ref <étiquette> gh:EdouardZemb/modele-projet <dossier>` : créer un projet.
- `copier update` : mettre à jour un projet né du modèle (à lancer dans ce projet, pas ici).
- `git config core.hooksPath .githooks` : à poser dans chaque clone et chaque worktree.

## Ce qui fait foi

- `docs/cadrage.md` : les décisions, le contrat, les cibles, les lots.
- Les ADR hérités, dans `template/docs/modele/decisions/`.
- `template/docs/modele/methode.md` : la méthode distribuée aux projets.
- `docs/aligner.md` : la liste de contrôle « Aligner un projet existant », à suivre case par case
  dans chaque lot d'alignement.

## Invariants

1. Aucun fichier ne nomme le serveur, son utilisateur ni une adresse.
2. Toute modification de `template/` vient avec son test.
3. Un fichier qui contient `${{` n'est pas `.jinja`, sauf si chaque expression y est enveloppée
   dans `{% raw %}`.
4. `template/docs/modele/methode.md` ne contient aucune syntaxe Jinja.

## Exploitation

Les versions du modèle sont des étiquettes `vX.Y.Z`, posées avec l'accord d'Edouard.
