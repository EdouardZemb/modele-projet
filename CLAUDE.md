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

Les messages de mise à jour vers la `v0.9.0` partent sur le oui d'Edouard, une fois l'étiquette
publiée.

Prochain, au choix d'Edouard :
- la scission d'`ancrage`, dans son propre lot : la piste « Les pièges d'une scission » en donne
  cinq ;
- le second temps du travail sur la documentation, un lot « documentation » avec sa spec : l'« État »
  réduit du `CLAUDE.md` semé et le journal des versions du modèle ; dans le README, le refus d'une
  copie qui se périme (un arbre de fichiers, une heure, une version) et le signal d'une issue citée
  au futur mais fermée ; la ligne « Confirmation » et le régime des ADR ; les blocs engendrés ;
- le lot 3 (la cible `statique`) ;
- le lot 5 (`partition` aligné en cible `aucune`) ;
- le lot 7 (`creche-planner` aligné en cible `aucune`) ;
- la porte due par LE-37, au 3e constat du motif « écart à la spec mal pesé », dont LE-49 est le
  4e : sa forme revient à Edouard, et le registre en propose une. À peser avec la piste du workflow
  `publier`, qui ferait publier Edouard depuis son téléphone ;
- la porte due par LE-40, au 3e constat du motif « délai mesuré à vide », dont LE-52 est le 4e : sa
  forme revient à Edouard, et le registre en propose une ;
- la porte due par LE-41, au 3e constat du motif « version d'outil du poste différente de la
  cible », dont LE-50 est le 4e : sa forme revient à Edouard, et le registre en propose une ;
- la porte due par LE-46, au 3e constat du motif « décision appliquée sans en chercher les
  effets » : sa forme revient à Edouard, et le registre en propose une ;
- la porte due par LE-53, au 3e constat du motif « mécanisme décrit sans relire son code », dont
  LE-54 et LE-61 sont les 4e et 5e : sa forme revient à Edouard, et le registre en propose une ;
- la porte due par LE-55, au 3e constat du motif « contrôle passé à vide », dont LE-58 et LE-62
  sont les 4e et 5e : sa forme revient à Edouard, et le registre en propose une ;
- la porte due par LE-56, au 3e constat du motif « comportement d'un outil supposé », dont LE-57 est
  le 4e : sa forme revient à Edouard, et le registre en propose une.

Le cadrage est dans `docs/cadrage.md` ; ce que les lots ont appris, dans `docs/registre.md`.

## Commandes

- `python -m pytest -q` : les tests, environ 6 à 8 minutes sous Ubuntu et 20 à 33 sous Windows,
  mesurées en CI, sans `tests/test_mecanique.py`, sur la PR #118. `tests/test_mecanique.py` lance
  les tests bats d'un projet rendu dans une image Docker : il lui faut Docker avec un serveur Linux,
  et il saute sans lui.
- `ruff check .` : le style.
- `gh run rerun <id> --job <databaseId>` : relancer le seul job de la CI coupé à son délai
  (`timeout-minutes`), le `databaseId` lu par `gh run view <id> --json jobs` (le numéro de l'URL du
  job ne convient pas, dit `gh run rerun --help`), après avoir vérifié que l'étape coupée est
  « cancelled », et non en échec : un échec se lit et se corrige, il ne se relance pas. La
  documentation de GitHub dit seulement qu'il annule un job à son délai ; l'étape coupée était
  « cancelled » sur le job coupé du 31/10 (LE-40). Jamais pour `texte-pr`, qui se relit par une
  retouche du texte de la PR (`methode.md`, « Ne jamais relancer `texte-pr` »).
- `gh run view <id>` : la revue finale de chaque lot relève les avertissements de durée des
  exécutions du lot, dans leurs annotations : chaque job qui porte l'étape « Durée du job » avertit
  au-delà des trois quarts de son délai, et personne d'autre ne lit un avertissement sur une
  exécution verte (`SessionStart` n'affiche que le rouge).
- `poste\Tester-Nouveau-Projet.ps1 -SansPoste -SourceModele <ce clone>` : le test du script de
  création, sans `gh`, sans la liste privée ni l'index réel. Il rend le modèle au `HEAD` du clone,
  changements non validés et fichiers non suivis compris : Copier les ajoute, avec un
  `DirtyLocalWarning`. Valider avant, pour éprouver la tête qui part. Sans `-SansPoste`, il lance
  aussi le script à blanc, sur le poste d'Edouard. `tests/test_poste.py` le lance, et compare les
  bits d'exécution du premier commit à ceux du modèle : sous Windows seulement ; ailleurs, seul le
  contrôle du BOM tourne.
- `python -B template/scripts/modele/plan.py --racine . --depot serveur=C:\src\github.com\EdouardZemb\serveur <plan>` :
  le contrôle d'un plan, ses trois sections (`methode.md`, « Les outils »). Les plans du modèle
  vivent dans `Documents\00-boite-de-reception\`, hors du dépôt : l'étape « Les plans » de la CI
  n'en trouve aucun ici. La session lance cette commande depuis le clone principal, avant de
  soumettre un plan à Edouard et après chaque correction.
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
