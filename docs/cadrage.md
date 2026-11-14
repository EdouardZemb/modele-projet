# Modèle de projet — cadrage

- **Date** : 2026-10-16
- **Entrée** : brief du 15/10 (hors dépôt)
- **Statut** : validé à la fusion, puis figé

> **Amendé le 2026-10-18, sans réécriture de ce texte figé.** Là où il diffère, ce sont les ADR
> hérités qui font foi, dans `template/docs/modele/decisions/`, et la méthode,
> `template/docs/modele/methode.md` :
>
> - **`methode.md`** : l'invariant 3 devient « Personne n'écrit sur le serveur après son
>   amorçage : tout y arrive par git. Une session y lit, elle n'y écrit jamais » (§5.2) ;
> - **M-0003** : l'instantané est un dossier qui a la forme de `/donnees`. Il est créé par
>   `SAUVEGARDER <dossier>` et contrôlé par `VERIFIER <dossier>` ; ce ne sont plus des fichiers
>   écrits dans un dossier (§6.1) ;
> - **M-0002, amendé** : qui fusionne se choisit par la réponse `fusion` (`session` ou `edouard`),
>   et les étiquettes et les publications sont à Edouard, dans les deux modes ;
> - **M-0004** : le retour voulu passe par une étiquette, `deployer.sh <env> --retour` restant le
>   secours (§6.3) ; les secrets se refont sur le poste par `scripts/modele/secrets.ps1`, sans
>   `secrets.sh definir` ni rapatriement (§6.4) ; la mise en service ne demande plus aucune étape
>   sur la machine : la sonde du dépôt `serveur` crée les clones, les dossiers et les réseaux,
>   d'après `projets/<nom>.env`, qui porte aussi les heures des sauvegardes (§6.2, §6.5, §6.8).
>
> **Amendé le 2026-10-27, à la clôture du lot 2, de la même façon.** Edouard a validé les écarts
> que le plan du lot 2 a pris sur ce cadrage :
>
> - **§4** : l'image se construit et se publie par deux actions composites gérées,
>   `modele-image-construire` et `modele-image-publier`, entre lesquelles le projet place ses
>   propres tests de bout en bout ; `modele-version.yml` est un workflow complet, déclenché par
>   l'étiquette ;
> - **§6.1** (M-0003) : l'instantané a la forme de `/donnees` ; les archives d'avant l'alignement
>   d'un projet se restaurent par son ancien `restaurer.sh`, procédure écrite dans son
>   `docs/exploitation.md` ;
> - **§6.6** : l'exercice trimestriel commun au parc n'est pas outillé ; chaque projet suit la
>   procédure de son `docs/exploitation.md`. L'outil commun est une piste (`docs/pistes.md`) ;
> - **§6.7** : un changement d'heure des sauvegardes dans `serveur` fait réinstaller les unités du
>   projet par la sonde de `serveur` ; `bloc_ports` reste une réponse Copier du projet, réservée
>   dans `projets/<nom>.env`, et la sonde alerte si les deux diffèrent ;
> - **§8** : au retour en cible `aucune`, Copier retire tout `deploiement/`, **fichiers semés
>   compris**, sans conflit ; git garde ce qui est commité (registre, LE-20 ; `docs/aligner.md`) ;
> - **§9** : `serveur` porte un troisième fichier de secrets, pour l'adresse du contrôle de sa propre
>   sonde ;
> - **§11** : le critère 5, « la sonde n'y crée rien », s'entend pour le projet (ni clone, ni
>   dossier, ni unité) ; le premier passage pose ce que les migrations exigent au niveau de la
>   machine. La migration du tunnel a pris trois versions du projet, N, N+1 et N+2 ; deux
>   suffisaient, puisqu'aucun chemin de retour n'avait besoin du jeton gardé jusqu'à N+2 (LE-19).
>   La bascule d'une route coupe une à deux minutes (LE-18). Les issues héritées sont recréées dans
>   `modele-projet` avec un texte générique, et non transférées ;
> - **§15**, faits établis pendant le lot 2 : `copier update` retire les fichiers d'une cible
>   abandonnée (voir §8) ; `secrets.ps1` passe les valeurs à `sops` par l'entrée standard, sous
>   Windows ; la sonde de `serveur` crée réseaux et conteneurs par le groupe `docker`, sans
>   `sudo`.
>
> **Amendé le 2026-10-27, à la clôture du lot 8, de la même façon.** Le lot 8 n'était pas au §11 :
> il est né de deux motifs du registre arrivés à leur 3e constat (LE-17, LE-23). Il ajoute deux
> garde-fous au §5.5, décrits dans `methode.md` et M-0002 :
>
> - **hook git `pre-commit`** : au commit d'un alignement ou d'une mise à jour, celui qui ajoute ou
>   modifie `.copier-answers.yml`, `scripts/modele/masques.py` refuse un fichier du modèle que le
>   `.gitignore` du projet masque, et nomme la règle et le remède ;
> - **hook Claude `SessionStart`** : au démarrage et à la reprise d'une session,
>   `scripts/modele/signaux.py` affiche ce qui est rouge sur GitHub (exécutions de la branche
>   principale, PR ouvertes, workflows désactivés), sans jamais bloquer. La CI du socle l'exige
>   comme le garde. Rien de ce qu'écrit un fork n'y entre : les exécutions de PR sont écartées, une
>   PR de fork s'affiche sans son texte, un workflow désactivé n'est nommé que si son fichier est
>   dans la copie (LE-26). C'est un écart à la spec du lot, décidé pendant ses revues.
>
> **Amendé le 2026-10-28, à la clôture du lot 9, de la même façon.** Le lot 9 n'était pas au §11 :
> il vient de l'issue #19, jugée importante le 27/10. Il ajoute une étape au §6.3 :
>
> - **après chaque déploiement ou retour arrière réussi**, `deployer.sh` lance
>   `deploiement/nettoyer-images.sh`. Le script retire du serveur les images du projet que ni
>   l'état des deux environnements, ni un conteneur, ni la marge des 3 plus récentes ne gardent.
>   Il ne passe jamais `-f` et ne touche aucune image d'un autre dépôt ; une surprise annule le
>   ménage sans rien retirer (M-0004, amendé). La sonde de `serveur` ne supprime toujours rien
>   (§6.2), et GHCR garde tout ;
> - **deux écarts à la spec du lot**, décidés pendant ses revues : une image qui porte plusieurs
>   étiquettes se retire par ses étiquettes, puisque Docker refuse sans `-f` le retrait par
>   identifiant d'une telle image ; les images se lisent par un gabarit que les CLI 28 et 29 de
>   Docker acceptent (LE-28).
>
> Le hook `SessionStart` du lot 8 a 30 s au lieu de 20 (#45, LE-27).
>
> **Amendé le 2026-10-28, à la clôture du lot 10, de la même façon.** Le lot 10 n'était pas au
> §11 : il vient de l'issue #49, ouverte le 28/10 depuis un projet né du modèle. Il ajoute une
> garde au §6.3, pour les projets qui ont des sauvegardes (§6.6) :
>
> - **avant l'instantané**, quand une version est déployée, `deployer.sh` refuse un déploiement
>   ou un retour arrière si le dossier de données est vide, ou s'il n'est plus celui du dernier
>   succès. Le chemin canonique du dernier succès est dans le fichier d'état `donnees` ; pour un
>   état d'avant la `v0.5.0`, celui de `compose.env` en tient lieu. Le refus alerte, sans rien
>   changer ni marquer la version en échec. Le geste 👤 `--donnees-neuves` lève la garde pour un
>   déploiement (M-0005, amendé) ;
> - **un écart du plan, puis un retour à la spec** : le plan avait pris pour seule référence le
>   chemin écrit dans `compose.env`. La revue finale a montré qu'un lien repointé sur place
>   passait alors, le cas même qui motivait le contrôle (LE-32). Le fichier `donnees` de la spec
>   est rétabli, et `compose.env` reste le repli.
>
> **Amendé le 2026-10-29, à la clôture du lot 11, de la même façon.** Les lots 11 et 12 ne sont
> pas au §11 : ils viennent de M-0006, « Le code et les données », héritée le 29/10 (PR #56).
> M-0006 rejoint les ADR hérités du §5.3, pour toutes les cibles. Elle sépare chaque projet en un
> dépôt de code, toujours publiable, et un dépôt de données privé. Le lot 11 en fait la première
> étape (M-0006, § 1 à 4) ; le lot 12 fera la chaîne à deux dépôts (§ 5 à 7).
>
> - **§5.1** : la question `visibilite` disparaît au profit de `nature` (`code` ou `donnees`, `code`
>   par défaut). À la mise à jour, un projet dont l'ancienne réponse était `prive` passe en
>   `donnees`. `domaine` n'a plus de défaut : le tableau du §5.1 le dit `<domaine>`, il est
>   désormais toujours une réponse. `cible` gagne `donnees`, qui rend le dépôt `<nom>-donnees` et
>   impose la nature `donnees` ;
> - **§5.6** : la porte suit la nature et non plus la visibilité. Dans un dépôt de code, tout
>   constat refuse ; dans un dépôt de données, ce qui identifie avertit et un secret refuse. En CI,
>   un dépôt public est de code, et un dépôt privé prend la nature de sa branche par défaut,
>   jamais celle de la PR. Chaque lundi, elle relit l'historique d'un dépôt de code et écarte les
>   constats de `.github/constats-acceptes.txt` (M-0002, amendé ; LE-33, LE-34) ;
> - **le passage en public** : un dépôt de code né après M-0006 n'a besoin que de sa règle de
>   protection, posée une fois la visibilité changée. Un dépôt d'avant ne passe pas en public : il
>   se scinde (M-0006, § 7) ;
> - **la liste privée** s'étend au domaine, au foyer, aux employeurs, aux lieux, aux courriels et
>   aux téléphones. Le dépôt modèle y passe sa porte : deux valeurs de ce cadrage ont été
>   remplacées par leur rôle, et trois constats anciens de l'historique sont acceptés.
>
> **Amendé le 2026-10-31, à la clôture du lot 12, de la même façon.** Le lot 12 fait la seconde
> étape de M-0006 (§ 5 et 6) : le contrat de `/config` et la chaîne à deux dépôts, en cible
> `serveur`. M-0002 à M-0006, `methode.md` et le runbook sont amendés.
>
> - **§3** : la réponse `compte` (`EdouardZemb` par défaut) donne `ghcr.io/<compte>/<nom>`, en
>   minuscules. `domaine`, `sous_domaine` et `bloc_ports` ne sont posés que là où vit l'instance :
>   un projet `serveur` de nature `donnees`, ou le dépôt de données d'un projet `serveur`, que
>   désigne sa réponse `cible_code`. Les clés du parc sortent de l'arbre du modèle et deviennent
>   les réponses `cle_serveur` et `cle_hors_ligne` ;
> - **§4 et §8** : `.sops.yaml` et `deploiement/cles/*.pub` deviennent semés : un projet à un
>   dépôt garde les siens. Un dépôt de code `serveur` ne reçoit ni `.sops.yaml`, ni
>   `deploiement/env/`, ni clés ; le dépôt de données d'un projet `serveur` reçoit `env/`,
>   `.sops.yaml`, `cles/` et sa CI, `modele-donnees.yml`. Deux fichiers compose gérés,
>   `deploiement/compose.config.yml` et `compose.contenu.yml`, décrivent les montages ;
> - **§5.5 et §5.6** : le garde refuse l'envoi d'une étiquette de données `donnees-…`, à Edouard
>   comme les `vX.Y.Z`. Dans un dépôt de code, la porte refuse l'instance par ses chemins (`*.enc`,
>   `.sops.yaml`, `cles/*.pub`, et un premier segment `instance/`, `config/` ou `contenu/`) et
>   toute clé publique `age` (M-0002, amendé) ;
> - **§6.1** : une application peut lire sa configuration sur `/config` et son contenu sur
>   `/contenu`, en lecture seule. `VERIFIER_CONFIG` et `VERIFIER_CONTENU`, déclarées dans
>   `deploiement/projet.env`, les vérifient, par paires avec leurs dossiers ; la santé gagne le
>   champ `configuration` (`exemple` ou `montee`). Le staging ne monte jamais `/config`. La CI du
>   code lance chaque commande sur son exemple, `exemple/` ou `exemple-contenu/` (M-0003, amendé) ;
> - **§6.2 et §6.3** : la chaîne a deux modes, selon la nature. À deux dépôts, l'instance vit dans
>   `<nom>-donnees`, cloné sur le serveur en `~/<nom>-donnees` et `~/<nom>-donnees-staging` ; le
>   staging en suit la branche que nomme `env/staging.env`, la principale à la création, et la prod
>   la plus haute étiquette `donnees-AAAA.MM.JJ.n`, avec la plus haute `vX.Y.Z` du code. À un
>   dépôt, jusqu'à la scission, l'instance est sous `instance/`, et la prod prend le commit de la
>   plus haute `vX.Y.Z`. L'état déployé est un couple, l'image et le commit de données (`-` sans
>   commande déclarée) : dès qu'une commande est déclarée, un commit de données seul redéploie, et
>   le retour arrière revient à un couple entier. Les données se montent depuis un instantané figé
>   du commit, sous l'état, jamais depuis le clone, et se vérifient sur lui avant tout changement
>   (M-0004, amendé) ;
> - **§6.4** : à deux dépôts, les secrets chiffrés vivent dans le dépôt de données, dont la CI les
>   contrôle contre le `.cles` du dépôt de code ; `secrets.ps1` y lit le `.cles` du clone voisin ;
> - **§6.6** : chaque instantané de `/donnees` note à côté de lui le couple en service, `.couple`
>   en local et `.couple.age` au distant (M-0005, amendé) ;
> - **trois écarts**, décidés pendant les revues du lot. Le ménage des instantanés des données se
>   fait par environnement : chacun garde ceux que nomme son propre état, et non l'état des deux
>   environnements, que disait la spec. Le dépôt de code garde gitleaks et le contrôle de ses
>   `.cles`, quand la spec lui retirait le contrôle des secrets. La mise en service d'un projet à
>   deux dépôts (§6.8) attend le lot 13 : la sonde de `serveur` ne crée pas encore le clone des
>   données ni sa clé de déploiement, et aucun geste 👤 ne s'y substitue ;
> - **un écart, puis un retour à la spec** : à un dépôt, la CI du code ne vérifiait que l'exemple,
>   et non `instance/`. La revue finale l'a trouvé (LE-37) : elle vérifie désormais `instance/`
>   comme le déploiement, qui la revérifie.
>
> **Amendé le 2026-11-01, par la v0.7.1, de la même façon** (#77). **§6.6** : tant que la prod
> d'un projet avec sauvegardes n'a rien déployé, la déclaration du projet dans `serveur` peut dire
> `SAUVEGARDE=non` et `TEST_RESTAURATION=non`, ensemble. Ni la sauvegarde ni son test ne
> s'installent alors, et le staging tourne. « non » refuse dès que la prod a un état déployé, et
> quand sa sonde va y déployer une version : la première version de prod attend les heures. La
> réponse `sauvegardes` dit toujours si le projet a des données à sauvegarder ; qu'une prod
> n'existe pas encore est un état de l'instance (M-0005, amendé ; LE-39).
>
> **Amendé le 2026-11-04, à la clôture du lot 13, de la même façon.** Le lot 13 fait la fin de
> M-0006 (§ 6 et 7) : la naissance d'un projet en deux dépôts par le script du poste, les clones
> des données par la sonde de `serveur`, puis le premier essai réel de la chaîne à deux dépôts, sur
> un projet jetable, `essai-chaine`. M-0006, `methode.md` et le runbook sont amendés ; M-0003 à
> M-0005 sont corrigés, pour dire ce que fait déjà la mécanique.
>
> - **§1** : le troisième livrable, `Nouveau-Projet.ps1`, vit dans `poste/` de `modele-projet`,
>   avec son test, hors de `template/` : il n'est pas distribué aux projets. La copie de
>   `Documents\30-ressources\35-dev\` n'en est plus la source (M-0006 § 7, amendé) ;
> - **une décision d'Edouard, le 03/11** : en cible `serveur`, le dépôt de code est public. La
>   chaîne à deux dépôts le suppose : la CI du dépôt de données le clone sans jeton et tire ses
>   images en anonyme. Le script refuse `-Cible serveur -Visibilite prive` (M-0006 § 1, amendé) ;
> - **§5.5** : le garde ne lit le mode et les contrôles d'une fusion que dans le dossier de la
>   session, et refuse toute fusion qui suit, dans la même commande, un changement de dossier,
>   même vers le sien (`methode.md`, amendé ; LE-45) ;
> - **§5.6** : la porte n'a plus le repli `VISIBILITE`. En CI, un dépôt privé dont la branche par
>   défaut ne porte pas `NATURE` prend la nature `code`, comme toute nature illisible ;
> - **§6.2, §6.6 et §6.7** : le test de restauration tourne chaque semaine, au jour et à l'heure
>   `TEST_RESTAURATION` que déclare `serveur`, et non le dimanche ; son contrôle Healthchecks
>   l'attend ce jour-là (M-0003 et M-0005, corrigés) ;
> - **§6.3** : après un retour par `deployer.sh <env> --retour`, seul le couple quitté est en
>   échec, et la sonde déploie tout couple neuf : un geste qui ne change qu'une moitié de la cible
>   ramène l'autre moitié du couple quitté. `--retour` dit quel geste passe d'abord (M-0004,
>   corrigé ; M-0006, amendé ; LE-46) ;
> - **§6.8** : la mise en service suit les six étapes du `docs/exploitation.md` du projet, et non
>   ce tableau. À deux dépôts, la déclaration dans `serveur` porte `DONNEES=oui` ; la sonde de
>   `serveur` crée la clé de déploiement `depot-<nom>-donnees` et attend ; 👤 Edouard la colle sur
>   `<nom>-donnees`, en lecture seule ; puis la sonde clone les données et installe les unités. La
>   réserve de l'amendement du lot 12, « la mise en service d'un projet à deux dépôts attend le
>   lot 13 », est levée. La cible des 15 minutes n'a pas été chronométrée à l'essai : la session
>   estime les gestes d'Edouard à environ 14 minutes, hors des quatre contrôles Healthchecks
>   qu'elle a créés ;
> - **§15** : la question GHCR est tranchée. Une image publiée par la CI d'un dépôt public est-elle
>   publique d'emblée sur GHCR ? Établi le 03/11 : oui. Le paquet d'`essai-chaine`, premier dépôt
>   de code public en cible `serveur`, est né public, hérité du dépôt, et `:main` se tirait sans
>   jeton. Le geste 👤 « passer le paquet en public » devient une vérification (LE-44).
>
> **Amendé le 2026-11-07, à la clôture du lot 14, de la même façon.** Le lot 14 n'était pas au §11 :
> il donne à chaque projet un README à la forme de sa variante, un `LICENSE` en nature `code`, et
> trois contrôles de sa documentation (#99). `methode.md`, M-0002 et `docs/aligner.md` sont
> amendés ; un texte géré, `docs/modele/documentation.md`, dit la forme du README, les textes d'un
> projet, et comment répondre aux contrôles.
>
> - **§4** : un projet reçoit aussi `LICENSE` [S], le texte MIT au nom du `compte`, en nature
>   `code` hors cible `donnees`, puis `docs/modele/documentation.md` [G] et
>   `scripts/modele/documentation.py` [G]. `README.md` [S] se rend en deux variantes, celle du code
>   et celle des données (cible `donnees`). « Ce qui fait foi », dans `CLAUDE.md` [S] hors cible
>   `donnees`, cite ses fichiers par des liens, le brief et le cadrage compris. Le `.gitignore` [S]
>   exclut `CLAUDE.local.md`. Copier sème un semé absent : un projet de code déjà né reçoit son `LICENSE` à
>   sa mise à jour, non suivi, à indexer ;
> - **§5.5** : la CI de base, à la dernière étape du job `confidentialite`, refuse un dépôt de code
>   sans `LICENSE` suivi, et une racine dont un `.md` n'est lié ni par le README ni par « Ce qui
>   fait foi » ; `CLAUDE.md` se lie depuis le README. La nature s'y lit comme la porte la lit. Le
>   hook `SessionStart` signale, sans bloquer, un gabarit resté vide que le README lie, et un README
>   qui ne lie aucun document du dépôt ;
> - **des écarts à la spec du lot, décidés pendant ses revues** : quand la racine est un dépôt, la
>   licence et la carte interrogent git (`git ls-files`), et ne sont donc plus des fonctions pures de
>   la racine. La licence ne compte qu'un `LICENSE` suivi, puisque la CI lit le commit ; un
>   `LICENSE` présent mais non suivi refuse par sa propre ligne. La carte compte ce que git suit ou
>   suivrait : un `.md` non suivi compte en local, que la CI ne voit pas, et ce que git ignore ne
>   compte pas. Un lien de référence compte par son emploi, une définition seule ne lie rien. Sous
>   Windows, une cible qui porte un deux-points n'est pas locale : elle y nommerait un lecteur.
>
> **Amendé le 2026-11-09, à la clôture du lot 15, de la même façon.** Le lot 15 n'était pas au §11 :
> il écrit les sept portes dues par le registre, chacune au 3e constat de son motif : LE-37, LE-40,
> LE-41, LE-46, LE-53, LE-55 et LE-56 (#114, PR #115 et #117 à #122). `methode.md`,
> `documentation.md`, M-0002 et `docs/aligner.md` sont amendés. `methode.md` dit les trois sections
> d'un plan et sa revue, les écarts à la spec, la tête relue d'une PR qui ferme une issue, et le
> mutant qui éprouve un test.
>
> - **§4** : un projet reçoit aussi `.github/workflows/modele-texte-pr.yml` [G], dans les trois
>   cibles, puis `scripts/modele/texte_pr.py` [G] et `scripts/modele/plan.py` [G]. Le gabarit de PR
>   [G] gagne la section « Écarts à la spec », « Aucun. » par défaut, et la ligne « Tête relue ».
>   `.github/workflows/ci.yml` [S] n'écoute plus `edited` : semé, celui d'un projet déjà né ne
>   change pas à sa mise à jour, et le projet en retire `edited` à la main ;
> - **§5.5** : la ligne de `modele-socle.yml` perd « du texte de la PR ». Le socle garde la
>   confidentialité du diff et des messages de commit, et le format des commits. Le texte de la PR
>   passe au workflow `texte-pr`, seul à écouter `edited` : une retouche du titre ou du corps ne
>   relance plus que lui, dès que le `ci.yml` du projet n'écoute plus `edited`. Son job, `texte-pr`,
>   contrôle la confidentialité et le format du titre et du corps, puis, par `texte_pr.py`, la
>   section « Écarts à la spec » de toute PR, sauf celles de `dependabot[bot]`, et la ligne
>   `Tête relue : <SHA>` d'une PR qui ferme une issue, les issues fermées étant lues par l'API
>   (`closingIssuesReferences`). La règle d'un dépôt public, `ruleset-main.json`, le requiert à côté
>   des deux contrôles du socle ; dans un dépôt privé, sans règle, le garde le lit avec les autres
>   contrôles avant une fusion en mode `session` (`gh pr checks`). Le job `confidentialite` du socle
>   gagne l'étape « Les plans (.claude/plans) », juste avant « La documentation de la racine », qui
>   reste la dernière : `plan.py` y vérifie les trois sections de chaque plan que la PR ajoute ou
>   modifie (« Mécanismes annoncés », « Outils et cas limites », « Revues ») ; sur une base nulle,
>   rien. Le garde à court de budget refuse toujours une fusion, mais le dit : quand ses 20 s de
>   sous-processus n'ont pas laissé finir la lecture du mode ou des contrôles, il répond « budget de
>   20 s épuisé : mode non lu, relancer », ou « … : contrôles non lus, relancer », au lieu du refus
>   du mode `edouard` ou de celui des contrôles. Dans le dépôt modèle, la règle, mise à jour le
>   08/11 et relue par l'API, requiert huit contrôles, `texte-pr` et `menage-cible` compris ;
> - **douze écarts à la spec du lot**, décidés par son plan, qu'Edouard a accepté le 07/11
>   (« ok pour les défauts »), et déclarés chacun dans la section « Écarts à la spec » de sa PR :
>   - le corps d'une PR et un plan se lisent par `sans_bloc_ni_commentaire`, extraite dans
>     `documentation.py` : elle retire les blocs clôturés et les commentaires fermés, et garde le
>     code en ligne. `_sans_code_ni_commentaire`, que nommait la spec, masquerait un SHA entre
>     accents graves et les lieux d'un plan, et garderait les blocs clôturés (§ 2.3 ; #115) ;
>   - `plan.py` refuse un deux-points dans le chemin d'un lieu sur tous les systèmes, et non sous
>     Windows seul : un chemin du dépôt n'en porte jamais (§ 3.1 ; #118) ;
>   - `docs/aligner.md` et le levier du déclencheur `edited`, dans `docs/pistes.md`, changent dans
>     la PR du workflow `texte-pr`, et non dans celle du ménage (§ 7 et § 12 ; #115) ;
>   - le gabarit de PR garde la chaîne « Closes #n », au `n` minuscule qu'exige son test (§ 2.6 ;
>     #115) ;
>   - des refus de plus : la forme stricte d'une section, qui n'admet que des lignes vides,
>     « Aucun. », des puces `-` ou `*` et les lignes indentées qui les continuent, et un commentaire
>     HTML jamais fermé, dans `texte_pr.py` puis dans `plan.py` ; dans `plan.py`, une plage de plus
>     de 40 lignes et un numéro de tâche en double (§ 2.4 et § 3.1 ; #115, #118) ;
>   - `texte-pr` déclare d'emblée la permission `issues: read`. Sa preuve dans un dépôt privé est
>     reportée à la mise à jour de `serveur`, dont le message part le premier ; ceux des autres
>     projets partent après le vert de `texte-pr` sur sa PR (§ 2.5 ; #115). Cette PR ne ferme
>     aucune issue : elle ne prouve que l'absence d'erreur, et la preuve complète viendra de la
>     première PR d'un dépôt privé qui ferme une issue, faite le 12/11/2026 par
>     veille-emploi-donnees#51 ;
>   - l'étape du texte de la PR, déplacée dans `texte-pr`, perd son
>     `if: github.event_name == 'pull_request'`, toujours vrai là (§ 2.2 ; #115) ;
>   - la ligne de durée et l'avertissement des jobs du dépôt modèle nomment le job et son système,
>     les deux jobs `tests` ayant le même identifiant (§ 4.1 ; #119) ;
>   - le plan du lot 15, qui vit hors du dépôt, se revérifie après la fusion de #118 sur les
>     fichiers de `7ccab76`, le commit que décrivent ses mécanismes, puisque le lot a déplacé
>     depuis des lignes qu'ils citent : 74 mécanismes vérifiés (§ 3.2 ; #118) ;
>   - d'un plan que la PR modifie, l'étape « Les plans » vérifie les sections, la forme des lignes
>     et les revues sans ouvrir les fichiers cités, dont les numéros dérivent avec le code ; à la
>     PR, seul un plan ajouté se vérifie en entier (§ 3.2 ; #118) ;
>   - la forme d'une ligne s'élargit : le tiret demi-cadratin comme séparateur, les étiquettes sans
>     égard à la casse, le SHA entre accents graves ou en majuscules ; dans un plan, `Tâche` et
>     `Task` sans égard à la casse (§ 2.4, § 2.5 et § 3.1 ; #115, #118) ;
>   - un lien d'issue posé depuis la barre latérale d'une PR s'écrit comme une limite dans
>     `methode.md`, sans épreuve : aucun type d'événement documenté ne le suit (§ 2.5 ; #115) ;
> - **seize choix des PR du lot**, qu'elles n'ont pas comptés comme écarts et ont soumis à Edouard
>   dans leur section « À relire », acceptés par lui le 09/11 (« ok pour les défauts ») :
>   - les refus de la section des écarts ajoutés en revue (l'ordre de la ligne, un écart vide, une
>     section en double, une sous-liste, une ligne ouverte par un commentaire), lus comme sa forme
>     stricte (#115) ;
>   - dans M-0002, hors des passages que la spec permettait de toucher, deux phrases qui sans ce
>     changement devenaient fausses : « la CI (le socle et `texte-pr`) le seul filet » (#115), et
>     « les hooks et la CI (le socle et `texte-pr`) » (#122), que la relecture de la clôture a
>     relevée et qu'Edouard a acceptée à part, le même jour ;
>   - une relance de `texte-pr` relit le texte de l'événement d'origine : `methode.md` dit de ne
>     jamais la relancer, et lire le titre et le corps par l'API reste une piste (#115) ;
>   - `documentation.md` gagne la sous-section « Réécrire un README » (#117) ;
>   - l'étape « Aucun cache Python » refuse aussi quand `find` échoue, au lieu de passer à vide
>     (#117) ;
>   - `plan.py` refuse deux sections du même titre, et n'en lit aucune (#118) ;
>   - le seuil d'avertissement d'un job vaut les trois quarts exacts de son délai, 33 min 45 s pour
>     45 min, là où la spec dit « 34 min » (#119) ;
>   - un job coupé à son délai se relance seul, par `gh run rerun <id> --job <databaseId>` ; tous
>     les jobs en échec, par `--failed`, seulement quand tous sont tombés sur la panne d'un service
>     tiers (#119, #122) ;
>   - le délai du job `tests` reste à 45 min, et une PR le monte à 50 min, seuil 37 min 30 s, au
>     premier avertissement (LE-40) ;
>   - dans `sonder.bats`, l'aide `sonder_sans_geste` s'ajoute à `apres_un_retour`, et la piste
>     « `echec` ne garde qu'un couple » reste ouverte (#120) ;
>   - `menage-cible` refuse tout magasin `io.containerd.snapshotter`, et sa table compte huit cas
>     de plus que le plan (#121) ;
>   - `menage-cible` dépend du réseau à chaque exécution, sous un délai de 2 min : Docker Hub,
>     `registry:2.8.3` et un `apk add` sans versions épinglées ; une panne de l'un d'eux le rend
>     rouge sans faute du code (#121) ;
>   - la ligne « Tête relue » et les sections se cherchent telles que GitHub les montre, à des
>     écarts près dont la liste n'est pas close, tous bornés par la tête de la PR ; la piste
>     `POST /markdown` les couvrirait (#122) ;
>   - `plan.py` est plus strict que GitHub : il refuse un numéro autre que 1, une sous-puce
>     indentée de quatre colonnes ou plus au-delà du texte de la puce, un commentaire après deux
>     ou trois espaces sous une puce, et deux espaces puis un tiret sous une ligne, que GitHub
>     rend en titre souligné (#122) ;
>   - au push, un plan ajouté se vérifie sans rouvrir ses lieux : un numéro de ligne qui a dérivé
>     entre la CI de la PR et sa fusion n'est plus revu (#122) ;
>   - le geste de la règle d'un projet, dans `docs/aligner.md` § 7, reprend tels quels des
>     paramètres lus que l'écriture n'a pas encore éprouvés : le premier geste réel le dira
>     (#122).
>
> **Amendé le 2026-11-13, à la clôture du lot 16, de la même façon.** Le lot 16 n'était pas au §11 :
> il corrige deux défauts de la `v0.10.0` que `pupitre` a relevés le 12/11, le plan d'un lot
> découpé en tranches, que `plan.py` refusait, et la ligne d'accord d'un écart, qui nommait Edouard,
> avec cinq retouches des mêmes fichiers suggérées au lot 15 (#127, PR #128 à #131). `methode.md`,
> `documentation.md` et `docs/aligner.md` sont amendés ; aucun fichier ne s'ajoute à ce que reçoit
> un projet (§4).
>
> - **§5.2** : un lot peut se découper en tranches. Son plan, le plan maître, n'a pour unités que
>   des titres `### Tranche N`, et chaque tranche qui le demande a son propre plan, à tâches,
>   ajouté par sa propre PR de plan ; les trois sections valent pour chacun. La PR de clôture du
>   lot, et elle seule, supprime le plan maître et les plans de tranche, ferme l'issue et nomme sa
>   tête relue. Un écart à la spec finit par `— accord : JJ/MM/AAAA` ; l'ancienne forme, qui
>   nommait Edouard, reste admise. `methode.md` donne aussi la commande qui éprouve en local le
>   texte d'une PR, avant de l'ouvrir ;
> - **§5.5** : `plan.py` lit les tranches à côté des tâches. Dans un plan maître, « Revues » cite
>   des tranches, chacune avant celle de la clôture ; un plan qui mêle les deux sortes refuse, et
>   les refus de forme disent la forme de leur section. L'étape « Les plans » du socle écrit, hors
>   d'une base nulle, combien de plans la PR ajoute, modifie et supprime. Les messages de
>   `texte_pr.py` et le gabarit de PR ne nomment personne. Le tableau des garde-fous de
>   `methode.md` nomme les écritures par l'API que refuse le garde, les règles et protections de
>   branche comprises ; le garde, lui, ne change pas ;
> - **§13** : le lot d'alignement donne ses commandes `gh` dans des blocs 👤, dont chaque ligne se
>   lance par `!`, seule dans son message (`docs/aligner.md` § 6) ; le secret `MOTIFS_INTERDITS`
>   s'y pose deux fois, pour Actions et pour Dependabot, par Git Bash, jamais par `cmd /c`, que
>   Git Bash réécrit. Une règle déjà en service se met à jour après la fusion d'une mise à jour
>   qui change ses contrôles requis (`docs/aligner.md` § 7) : la session lit la règle et prépare
>   le corps, et Edouard ne lance que la ligne du `PUT`, que le garde refuse à une session.
>   `Nouveau-Projet.ps1`, après un échec, dit que les commandes qu'il affiche sont pour
>   PowerShell, jamais pour `!` ;
> - **le premier geste réel de la règle**, que l'amendement du lot 15 attendait, a eu lieu le
>   12/11/2026, sur les trois dépôts publics, `veille-emploi`, `pupitre` et `ancrage`, après leur
>   mise à jour en `v0.10.0` : le `PUT`, son corps construit depuis la règle en service, a été
>   accepté du premier coup les trois fois. Relue par l'API le 13/11, la règle de `pupitre`
>   requiert toujours `verifier`, `windows` et `mutants`, et `texte-pr` en plus ;
> - **trois écarts à la spec du lot**, décidés par son plan, qu'Edouard a accepté le 12/11
>   (« Ok »), et déclarés chacun dans la section « Écarts à la spec » de sa PR, à la forme
>   « accord : » :
>   - la commande qui éprouve le texte en local commence par `corps='<fichier du corps>'`, et la
>     tête relue s'éprouve à sa troisième ligne, non à la deuxième (§ 4.5 ; #129) ;
>   - le tableau des garde-fous nomme aussi les objets de git (`git/commits`, `git/trees`,
>     `git/tags`) et la mise à jour d'une branche (`…/update-branch`), que la liste de la spec
>     omettait (§ 4.6 ; #129) ;
>   - au § 6 de `docs/aligner.md`, chaque ligne d'un bloc 👤 se lance par `!`, seule dans son
>     message, et non le seul `POST` (§ 4.4 ; #130) ;
> - **seize choix du lot**, que ses PR n'ont pas comptés comme écarts, recueillis dans la section
>   « À relire » de la PR de clôture, et acceptés par Edouard le 13/11 (« ok pour les défauts ») :
>   - le déclencheur de la piste du commentaire jamais fermé n'est pas atteint : #128 change le
>     message de ce refus, pas sa recherche (décidé dès le 12/11) ;
>   - un plan à tâches qui porte aussi un titre `### Tranche N` refuse comme plan mêlé ; aucun des
>     huit plans en cours des projets n'en porte (#128) ;
>   - le cas du faux `wc` de l'étape « Les plans » ne tourne pas sous Windows, la raison écrite
>     dans le test (#128) ;
>   - le mot « tranche » suivi d'un nombre cite une tranche, même quand c'est le verbe ;
>     « trancher 2 » ne cite rien (#128) ;
>   - pour un corps UTF-16, `methode.md` dit que le contrôle « peut passer comme refuser », sans
>     test qui écrive un tel corps : le résultat dépend du shell (#129) ;
>   - la case du secret passe par Git Bash, « jamais par `cmd /c` », case que la spec ne nommait
>     pas (#130) ;
>   - LE-70 et LE-71 gardent le motif « décision appliquée sans en chercher les effets », celui de
>     LE-39 pesé puis écarté (#130) ;
>   - LE-75 va sous « contrôle passé à vide », 8e constat du motif (#131) ;
>   - LE-76 ne propose aucune forme de porte : elle revient à Edouard (#131) ;
>   - un corps UTF-8 avec BOM se règle par le texte de `methode.md`, « sans BOM », sans retirer le
>     BOM dans `texte_pr.py` (#131) ;
>   - deux constats d'avant le lot restent tels quels, car ils refusent du côté sûr : un titre de
>     tranche à espace insécable, et « sous-tranche 2 » (#131) ;
>   - le corps de #131 disait trois constats restés tels quels : la clôture en compte deux, la
>     forme `<details>` allant à la piste du commentaire jamais fermé ;
>   - le message de `pupitre` : la scission de sa Tranche 8 emporte ses renvois, dans le plan
>     maître et dans deux plans de tranche ; sans scission, la dérogation à « une tranche à elles »
>     se dit dans sa PR, non dans son plan ; la décision reste à Edouard, dans la session de
>     `pupitre` ;
>   - la clôture nomme aussi LE-74 et LE-75 dans « Prochain », ajoute deux lignes longues de
>     `methode.md` à la piste du lot 11, amende le §13, dit tenu le premier volet de LE-63, et
>     compte 22 constats à la revue finale, 19 sans leurs doublons, et non 23, comme le disaient le
>     corps de #131 et les notes ;
>   - LE-77 fait de cette erreur de compte une leçon, close, sous un motif neuf, « dénombrement
>     fait à la main, repris sans recompter » ;
>   - LE-40 se clôt en renvoyant au corps de la PR de clôture pour ses exécutions, ses durées
>     mesurées du début du job au départ de l'étape « Durée du job ».
>
> **Amendé le 2026-11-14, à la clôture du lot 17, de la même façon.** Le lot 17 n'était pas au §11 :
> il écrit les deux portes dues par le registre, celle de « décision appliquée sans en chercher les
> effets » (LE-63, LE-70, LE-71 et LE-73), par une section des plans et le relevé des projets, et
> celle d'« étape de clôture oubliée par le plan » (LE-76), par les gestes de clôture et la commande
> des plans du modèle (#134, PR #139 à #143). `methode.md`, `documentation.md`, le gabarit de PR et
> `docs/aligner.md` sont amendés ; aucun fichier ne s'ajoute à ce que reçoit un projet (§4).
>
> - **§1** : `poste/` porte aussi `releve.py`, le relevé des projets nés du modèle, avec son test,
>   hors de `template/` : il n'est pas distribué. Il lit les projets par `gh api`, en lecture
>   seule, dépôts privés compris, lance sur leurs plans et leurs textes de PR les scripts du modèle
>   de leur version et de la tête, et compare leurs règles et leurs fichiers gérés à ceux du modèle.
>   Il tourne sur le poste, par la session, jamais en CI, qui n'a pas de jeton qui lirait tous les
>   dépôts privés : avant une spec ou un plan, à la revue finale et à la clôture ;
> - **§5.2** : le plan d'un lot porte quatre sections : « Effets cherchés » s'ajoute aux trois du
>   lot 15, une ligne par décision du plan qui change une forme, une règle, un geste ou un défaut
>   que reçoit un autre lieu (un projet né du modèle, un autre chemin d'exécution, un autre
>   environnement), que la revue du plan relit là où l'effet arrive. L'unité de clôture d'un plan
>   neuf nomme six gestes : le plan supprimé, `CLAUDE.md` ou un ADR, le README, les leçons du lot,
>   la fermeture de l'issue et la tête relue ; un plan de tranche s'en dispense par la ligne
>   `Plan maître :`, un plan hors lot par la ligne `Hors lot :`. La PR de clôture porte au registre
>   les leçons du lot encore sans ligne, et un dépôt de la cible `donnees`, qui n'a pas de registre
>   à lui, au registre de son dépôt de code. Un plan en cours n'est pas tenu à ces exigences tant
>   qu'il n'est pas vérifié comme neuf et ne porte pas « Effets cherchés » ; la session vérifie son
>   plan comme neuf (`--neuf`) jusqu'à son accord ;
> - **§5.5** : l'étape « Les plans » du socle, et sa copie dans la CI de ce dépôt, vérifient les
>   quatre sections, puis, d'un plan neuf ou qui porte « Effets cherchés », l'unité de clôture et
>   ses gestes, ou la ligne qui l'en dispense. Un plan ajouté, renommé compris, s'y vérifie comme
>   neuf (`--neuf`), à la PR comme au push ; un plan modifié se vérifie toujours sans ouvrir ses
>   lieux, et sans `--neuf`. Le gabarit de PR [G] nomme, dans sa liste de contrôle, les leçons du
>   lot au registre, à la clôture ;
> - **§11** : un projet aligné donne à chaque plan en cours ses trois sections d'avant le lot 17,
>   jamais « Effets cherchés » après coup ; un plan renommé compte pour neuf (`docs/aligner.md`) ;
> - **les plans du modèle**, qui vivent hors du dépôt et que la CI ne voit pas, se vérifient par la
>   commande de « Commandes », dans `CLAUDE.md` : `--neuf` jusqu'à l'accord, un `--depot` par dépôt
>   cité, et les mots `cadrage`, `À relire`, `pistes` et `relevé` en plus des six gestes. Une ligne
>   d'« Effets cherchés » dont le lieu est un projet cite le relevé dans son troisième morceau ; la
>   clôture d'un plan du modèle dit que le plan, hors du dépôt, n'est pas supprimé, et que son
>   en-tête est mis à jour ;
> - **le relevé de la clôture**, sur `3b7ab38`, rend 0 : sept projets lus, rien à lire. Les huit
>   plans en cours gardent à la tête le verdict qu'ils ont à la version de leur projet, et tous
>   refuseraient s'ils étaient neufs ; celui d'`ancrage` pour la seule section « Effets cherchés » :
>   sa clôture nomme déjà les six gestes, « constats » valant « leçons » depuis la question 7 de la
>   spec du lot, acceptée le 14/11, alors que son § 3.1, écrit avant, disait qu'aucune des clôtures
>   en cours ne les nommait ;
> - **aucun écart à la spec du lot** : ses cinq PR déclarent « Aucun. ». Un remède de la revue
>   finale, un relevé sans aucun projet rendant 1, s'écartait du § 5.4 de la spec, qui donne 0 ; la
>   relecture des corrections l'a trouvé, et le code est revenu à 0 avant l'ouverture de #143
>   (LE-83).

Ce cadrage est la partie publique de la spec de conception du modèle, issue d'une séance de questions avec Edouard : 12 questions, puis 5 parties de design validées une à une. La partie qui nomme le serveur est privée et n'est pas reproduite ici.

---

## 1. L'objet

Un modèle d'où naît tout nouveau projet **en une commande**, avec l'organisation d'`ancrage` :
méthode, poste, serveur, domaine. Les projets existants s'y alignent, puis **restent alignés**
quand le modèle évolue.

Trois livrables :

| Livrable | Où | Visibilité |
|---|---|---|
| `EdouardZemb/modele-projet` — le modèle Copier | GitHub, cloné en `C:\src\github.com\EdouardZemb\modele-projet` | public |
| `EdouardZemb/serveur` — notice et registre du serveur, tunnel commun, scripts de mise en service | GitHub, cloné sur le poste et sur le serveur | privé |
| `Nouveau-Projet.ps1` réécrit, et un détecteur de plus au contrôle de dérive | `Documents\30-ressources\35-dev\` | — |

---

## 2. Les décisions

| # | Décision | Pourquoi |
|---|---|---|
| Q1 | **Aucune stack imposée.** Le modèle fixe un **contrat** (§6.1) | C'est le contrat, pas la stack, qui rend le serveur et le domaine génériques. `pupitre` et le site perso n'auront pas la stack d'`ancrage` |
| Q2 | **Copier**, pas un *template* GitHub | Le seul des trois outils envisagés qui sache aligner un projet existant **et** propager une correction ensuite. Un *template* GitHub copie une fois, puis plus aucun lien |
| Q2 bis | **`.copier-answers.yml` est une exception déclarée** à la règle « pas de manifeste machine » (§7 du plan de rangement) | Il ne décrit que son propre dépôt, il est versionné, et `copier update` le relit à chaque fois : faux, il échoue bruyamment. Il ne peut pas mentir en silence |
| Q3 | **le domaine public du projet par défaut**, mais le domaine est une question de Copier. Adresses `<x>` et `<x>-staging` | Domaine personnel « pour le moment ». Le certificat gratuit de Cloudflare ne couvre qu'un niveau de sous-domaine (ADR-0006 d'`ancrage`, §3) |
| Q4 | **Trois cibles** : `aucune`, `statique`, `serveur`. **Changer de cible, c'est changer une réponse** puis lancer `copier update` | Un jeu dans le navigateur est un site statique. Si un tableau des scores ou du multijoueur arrive, le site change de cible sans être refait |
| Q5 | **Dépôts publics par défaut**, protégés par une règle GitHub (*ruleset*). En plus : un hook git et un hook Claude. Un dépôt **privé** reste possible, et n'a alors que les hooks. **Porte de confidentialité obligatoire.** Le modèle lui-même est public | GitHub refuse la protection de branche sur les dépôts privés d'un compte gratuit (HTTP 403). Edouard ne prend pas GitHub Pro |
| Q6 | **Un dépôt privé `serveur`** : notice et registre en Markdown. Il remplace les notes d'exploitation actuelles du serveur | Le seul endroit qui survit à la perte du serveur, que voient toutes les sessions, et qui reste privé. Un tableau Markdown corrigé à la main n'est pas un manifeste machine |
| Q7 | **La méthode d'`ancrage`**, plus `docs/registre.md`, `/consigner` et la règle des 3 retours | `ancrage` organise bien le travail mais n'apprend pas de ses erreurs. Le reste de `creche-planner` (25 portes, DORA, politique documentaire) tient à sa taille |
| Q8 | **Deux clés age pour tout le parc** : la clé serveur (aujourd'hui celle d'`ancrage`) et la clé hors ligne d'`ancrage`, **réutilisée** | Des clés séparées, détenues par le même utilisateur Unix et rangées dans le même coffre, n'isolent rien : elles multiplient le travail |
| Q9 | **Un seul tunnel Cloudflare** pour le serveur, porté par `serveur`. Un réseau Docker par projet et par environnement | Même raisonnement que Q8. La mise en service d'un projet tombe de 40 minutes à quelques-unes |
| Q10 | **Tous les projets s'alignent**, un lot chacun : `ancrage`, site perso, `pupitre`, `partition`, `veille-emploi`, `creche-planner` | Décision d'Edouard |
| Q11 | **`creche-planner` reçoit la méthode et les ressources partagées, pas le déploiement.** Sa cible est `aucune` | Un contrat se généralise sur **deux** cas réels, pas un. Élargir le contrat à 7 services maintenant, c'est laisser `creche-planner` dessiner le modèle |
| Q12 | **Les sessions sont en lecture seule sur le serveur.** Toute écriture passe par git (la sonde) ou par un script que lance Edouard | Le déploiement tiré par le serveur rend l'écriture inutile pour le travail courant. Le classifieur la refuse déjà (deux fois le 15/10) |
| Approche | **La mécanique de déploiement vit dans chaque projet**, rendue par Copier, dans un dossier sans rien de propre au projet | Elle reste versionnée avec l'app : un retour à l'étiquette précédente ramène les scripts qui allaient avec (invariant 8 d'`ancrage`). Les 237 tests bats d'`ancrage` suivent tels quels |

**Porte laissée ouverte, sans rien construire.** La mécanique pourra devenir plus tard une image
`ghcr.io/edouardzemb/modele-projet/mecanique`, épinglée par empreinte dans chaque projet et mise à
jour par Dependabot. Cette image figerait aussi `age`, `sops`, `rclone` et `jq`. Pour que ce
passage se résume à remplacer un dossier par une ligne d'épinglage, **tout ce qui est propre au
projet tient dans `deploiement/projet.env` et `deploiement/compose.projet.yml`**. À rouvrir quand
un quatrième projet passera en cible `serveur`.

---

## 3. Les questions de Copier

| Question | Valeurs | Défaut | Posée si |
|---|---|---|---|
| `nom` | kebab-case ; c'est aussi le nom du dépôt | — | toujours |
| `description` | une phrase | — | toujours |
| `visibilite` | `public`, `prive` | `public` | toujours |
| `cible` | `aucune`, `statique`, `serveur` | `aucune` | toujours |
| `branche_principale` | nom de la branche par défaut | `main` | toujours |
| `domaine` | un domaine de la zone Cloudflare | `<domaine>` | cible ≠ `aucune` |
| `sous_domaine` | vide = racine du domaine, en cible `statique` seulement | `{{ nom }}` | cible ≠ `aucune` |
| `port_app` | port d'écoute **dans** le conteneur | `3000` | `serveur` |
| `chemin_sante` | chemin de la route de santé | `/api/sante` | `serveur` |
| `bloc_ports` | multiple de 10, entre 4310 et 4990, **lu dans `REGISTRE.md`** de `serveur` | — | `serveur` |
| `sauvegardes` | oui ou non | oui | `serveur` |
| `dossier_publie` | dossier produit par la construction | `site` | `statique` |

**Le préfixe des variables** est rendu par Copier : `{{ nom | upper | replace('-', '_') }}_`
donne `ANCRAGE_`. `ancrage` n'a rien à renommer.

---

## 4. Ce que reçoit un projet

`[G]` : **géré** par le modèle, réécrit à chaque mise à jour. `[S]` : **semé** une fois, puis
laissé au projet.

```
CLAUDE.md                                [S] première ligne : @docs/modele/methode.md
README.md                                [S]
.copier-answers.yml                      écrit par Copier
.gitattributes .gitignore .editorconfig  [S] LF partout
.githooks/pre-commit                     [G]
.githooks/commit-msg                     [G]
.githooks/pre-push                       [G]
.claude/settings.json                    mixte (§8) : hook PreToolUse (outils Bash et PowerShell)
.claude/skills/consigner/SKILL.md        [G] une compétence, la forme recommandée des commandes
.claude/plans/                           un plan par lot, supprimé par la PR de clôture
.github/workflows/ci.yml                 [S] le job `verifier` du projet, qui appelle les workflows du modèle
.github/workflows/modele-socle.yml       [G] réutilisable
.github/workflows/modele-image.yml       [G] réutilisable — cible serveur
.github/workflows/modele-version.yml     [G] cibles serveur et statique
.github/workflows/modele-statique.yml    [G] réutilisable — cible statique
.github/actions/construire/action.yml    [S] cible statique
.github/modele/ruleset-main.json         [G]
.github/pull_request_template.md         [G]
.github/ISSUE_TEMPLATE/lot.yml           [G]
.github/dependabot.yml                   [S] github-actions, et docker en cible serveur
scripts/modele/                          [G] confidentialite.py, commits.py, garde_claude.py, pre_push.py,
                                             lancer.sh (trouve un Python qui marche), reglages.py
docs/modele/methode.md                   [G]
docs/modele/decisions/M-NNNN-*.md        [G] ADR hérités (§5.3)
docs/00-brief-initial.md                 [S] gabarit
docs/cadrage.md                          [S] gabarit, figé à sa fusion
docs/decisions/                          [S] ADR du projet, à partir de 0001
docs/pistes.md                           [S]
docs/registre.md                         [S]
docs/exploitation.md                     [S] cibles statique et serveur
.sops.yaml                               [G] cible serveur
deploiement/                             [G] cible serveur, sauf :
deploiement/projet.env                   [S]   commandes sauvegarder et verifier, variables non secrètes de l'app
deploiement/compose.projet.yml           [S]   ce que l'app ajoute au service (volumes, variables)
deploiement/secrets/                     au projet : fichiers chiffrés
tests/deploiement/                       [G] cible serveur
```

Ce qui reste au projet : son code, son `Dockerfile`, ses commandes, le job `verifier` de sa CI.
C'est le contrat.

---

## 5. Le socle (toutes les cibles)

### 5.1 Un `CLAUDE.md` en deux couches

Un `CLAUDE.md` à la fois géré par le modèle et propre au projet ferait un conflit à chaque
`copier update`. Il est donc coupé en deux :

- **`CLAUDE.md` est au projet.** Semé une fois, jamais retouché par Copier. Sections d'`ancrage` :
  présentation, **État**, **Commandes**, **Ce qui fait foi**, **Invariants** (ceux du projet),
  **Exploitation**. Sa première ligne importe la méthode : `@docs/modele/methode.md`.
- **`docs/modele/methode.md` est au modèle**, et Copier le met à jour.

### 5.2 Ce que dit `docs/modele/methode.md`

- **Le cycle d'un lot.**
  1. Une issue, avec une mini-spec : objectif, critères d'acceptation, hors périmètre. Une
     milestone par étape.
  2. Une PR de plan, qui ajoute le plan dans `.claude/plans/`.
  3. Une ou plusieurs PR d'implémentation.
  4. Une PR de revue finale.
  5. Une PR de clôture : elle **supprime le plan** et reporte dans `CLAUDE.md` ou un ADR ce qui
     doit survivre.
  6. L'étiquette `vX.Y.Z`, **avec l'accord d'Edouard**.
- **Les outils.** Les plans s'écrivent et s'exécutent avec les compétences *superpowers*
  (`writing-plans`, `subagent-driven-development`). **Elles ne sont pas déclarées dans
  `.claude/settings.json`** (corrigé le 16/10, à l'écriture du plan du lot 1). D'après la
  documentation de Claude Code, un plugin déclaré par le projet ne s'installe ni dans une session à
  distance ni sur un autre poste, et la déclaration doublerait l'installation du poste.
  `methode.md` dit quoi faire quand *superpowers* manque.
- **Les worktrees.** Un sujet = un worktree, dans `<nom>.worktrees\<sujet>`, jamais à côté du
  dépôt.
- **« Fini »** : tests verts, CI verte, `CLAUDE.md` et ADR à jour, déployé, vérifié là où l'app
  sert (sur un téléphone Android pour une app mobile).
- **Les commits** : Conventional Commits en français, en-tête de 100 caractères au plus, fusion par
  squash. `git add` par chemins explicites.
- **Les questions groupées** : en un seul bloc, numérotées, chacune avec sa réponse par défaut.
  « OK pour les défauts, sauf n » suffit comme réponse.
- **Les invariants communs**, ajoutés à ceux du projet :
  1. Aucun secret ne passe par la conversation. Les étapes 👤 le disent.
  2. Aucune donnée personnelle réelle dans le dépôt, les tests ou le staging. Le jeu de données
     factice est **écrit**, pas dérivé de données réelles (ADR-0010, §3).
  3. Les sessions sont en lecture seule sur le serveur (Q12).
  4. Cible `serveur` : une migration, `compose.yml` et les `env/*.env` doivent laisser fonctionner
     l'image précédente. On ajoute avant d'enlever, et une variable nouvelle ne devient
     obligatoire qu'une version plus tard (invariant 8 d'`ancrage`).
  5. Un fichier géré par le modèle ne se modifie pas dans le projet : on corrige le modèle (§8).

### 5.3 `docs/`

- **`00-brief-initial.md`** : gabarit aux sections du brief d'`ancrage`. D'où l'on part, ce qu'on
  veut obtenir, ce qui existe déjà, la méthode (une phase 0 de cadrage sans code), plus tard,
  points d'attention.
- **`cadrage.md`** : gabarit du livrable de la phase 0. Ce que la lecture change, les réponses
  d'Edouard, les décisions et ce qui serait difficile à changer, le calendrier, le plan par étapes
  et par lots, ce qu'Edouard seul peut faire. **Figé à sa fusion.**
- **`decisions/NNNN-titre.md`** : les ADR du projet, au format d'`ancrage`.
  - Titre : `# ADR-NNNN — <Sujet> : <décision en une phrase>`.
  - En-tête : statut daté, contexte amont.
  - Sections : Contexte, Options, Décision, Conséquences (dont « Difficile à changer »), Révision.
  - Un ADR ne se réécrit pas : un nouveau le remplace.
- **`modele/decisions/M-NNNN-titre.md`** : les ADR **hérités du modèle**, à part pour que leurs
  numéros ne se heurtent pas à ceux du projet.

  | ADR hérité | Cible | Origine |
  |---|---|---|
  | M-0001 Écosystème des applications personnelles | toutes | les cinq règles de l'ADR-0010 de `creche-planner` |
  | M-0002 Garde-fous et confidentialité | toutes | Q5 |
  | M-0003 Contrat de l'image | `serveur` | §6.1 |
  | M-0004 Chaîne de livraison | `serveur`, `statique` | ADR-0006 d'`ancrage`, généralisé |
  | M-0005 Sauvegardes et restauration | `serveur`, avec sauvegardes | partie générique de l'ADR-0007 d'`ancrage` |
  | M-0006 Le code et les données | toutes | l'analyse du 29/10, faite pour `veille-emploi` (amendement du 29/10) |

  M-0001 répond à une faiblesse que l'ADR-0010 avoue lui-même : *« Cet ADR vit dans le dépôt de
  Martha (`creche-planner`) mais gouverne des applications qui n'y sont pas »*. Le modèle devient la maison de ces
  règles.
- **`pistes.md`** : « notées, pas engagées ». Une piste devient une issue le jour où on la
  travaille.
- **`registre.md`** : une ligne par constat.

  | N° | Famille | Date | Constat | Motif | Prévention | Critère de sortie | État |
  |---|---|---|---|---|---|---|---|

  - **AM** : une piste d'amélioration, « il faudrait ».
  - **LE** : une leçon, « on a cru que ».
  - **EM** : un empêchement, « on n'a pas pu ».

  Les numéros ne se réutilisent jamais. **Au 3e constat portant le même motif, on écrit une
  porte** (un test, un hook, une vérification de CI), et la ligne le dit.
- **`exploitation.md`** (cibles `statique` et `serveur`) : le runbook. Ce qui tourne, mettre en
  ligne, revenir en arrière, et pour `serveur` restaurer, les secrets, les échéances, tout arrêter.

### 5.4 `/consigner`

Argument : le constat, en une phrase.

1. Choisir la famille (AM, LE ou EM).
2. Prendre le premier numéro libre et remplir toutes les colonnes. L'origine se déduit de la
   branche.
3. Rattacher la ligne à un motif existant, ou en créer un. Compter ses occurrences : à 3, proposer
   la porte qui l'empêchera.
4. Rendre compte en une ligne.

`/consigner` ne dépend ni du doc 34, ni de `pnpm registre`, ni de Nx : c'est une écriture dans un
fichier Markdown.

### 5.5 Les garde-fous

Ils sont tous écrits en **Python** : c'est le seul langage présent à la fois sur le poste, en CI et
dans les sessions à distance, et il n'impose rien au projet.

| Où | Quoi |
|---|---|
| hook git `pre-commit` | confidentialité du contenu indexé |
| hook git `commit-msg` | format Conventional Commits, confidentialité du message |
| hook git `pre-push` | refus d'envoyer sur `branche_principale` |
| hook Claude `PreToolUse` (outil `Bash`) | bloque `git push` vers `branche_principale`, tout force-push vers elle, et `gh pr merge` tant que `gh pr checks` n'est pas entièrement vert |
| CI, `modele-socle.yml` | gitleaks sur tout l'historique (`fetch-depth: 0`) ; confidentialité du diff et du texte de la PR ; format des commits. Actions épinglées par SHA |
| GitHub, `ruleset-main.json` | PR obligatoire, contrôles requis, ni force-push ni suppression de `main`. Appliqué par `Nouveau-Projet.ps1` aux dépôts publics |
| Dependabot | `github-actions` (et `docker` en cible serveur), le lundi, avec un délai de 3 jours avant de proposer une version neuve, comme `creche-planner`. Le projet ajoute l'écosystème de sa stack |

`core.hooksPath` n'est pas versionné. Il doit valoir `.githooks`, chemin **relatif**, dans
chaque clone et chaque worktree. `Nouveau-Projet.ps1` le pose à la création, l'alignement le pose
dans les clones existants, et le contrôle de dérive le vérifie. Ce chemin relatif évite le piège
de la vague 5, où un `core.hooksPath` absolu dans `config.worktree` avait dû être re-pointé.

### 5.6 La porte de confidentialité

- **Motifs génériques**, écrits dans `scripts/modele/confidentialite.py` : adresses IP privées et
  Tailscale (100.64/10), cibles SSH `utilisateur@machine`, clés age privées, jetons GitHub,
  JWT, adresses de ping Healthchecks.
- **Motifs privés** (le nom du serveur, l'utilisateur, les chemins) : une liste gardée hors dépôt.
  - Sur le poste : `~/.config/modele-projet/motifs-interdits.txt`.
  - En CI : le secret `MOTIFS_INTERDITS`, posé dans chaque dépôt par `Nouveau-Projet.ps1`. GitHub
    n'a pas de secret d'Actions au niveau d'un compte personnel.
- **Une limite connue.** Une session à distance n'a pas la liste privée. Elle n'applique que les
  motifs génériques, et c'est la CI qui rattrape le reste.

---

## 6. La cible `serveur`

### 6.1 Le contrat : ce que le projet fournit

1. Un `Dockerfile` à la racine. L'image :
   - écoute sur `$PORT` (par défaut `port_app`), sur `0.0.0.0` ;
   - tourne en `1000:1000` sur un système de fichiers en lecture seule, avec `/tmp` en mémoire ;
   - porte le label `org.opencontainers.image.revision`, rempli par l'argument de construction
     `REVISION`.
2. Une route de santé à `chemin_sante`. Elle renvoie au moins
   `{statut, environnement, version, revision}`, ou un 503 avec `{statut: "ko"}`. L'environnement
   vaut `dev`, `ci`, `staging` ou `prod`.
3. Ses données dans `/donnees`.
4. Si `sauvegardes` vaut oui, deux commandes dans l'image, déclarées dans `projet.env` :
   - **`sauvegarder <dossier>`** écrit dans le dossier un instantané cohérent, en un ou plusieurs
     fichiers ;
   - **`verifier <dossier>`** répond 0 si l'instantané est conforme, 2 s'il ne l'est pas, 64 en
     cas d'erreur d'usage.

   La mécanique fait le reste : archive `tar`, chiffrement `age` vers la clé hors ligne, envoi
   `rclone`, rétention, test de restauration. Elle ne sait rien de la base de l'app.

### 6.2 Sur le serveur, pour chaque projet

C'est la convention d'`ancrage`, paramétrée par `nom`.

| Quoi | Où |
|---|---|
| clone de prod, placé sur l'étiquette déployée | `~/<nom>` |
| clone de staging, sur `main` | `~/<nom>-staging` |
| données | `~/.local/share/<nom>/<env>/donnees` |
| état de déploiement | `~/.local/state/<nom>/<env>/` |
| sauvegardes locales | `~/backups/<nom>/` (`quotidiennes/`, `pre-deploiement/`, `avant-restauration-*`) |
| unités systemd | `~/.config/systemd/user/<nom>-*`, rendues par `installer-unites.sh` |
| projets Compose | `<nom>` et `<nom>-staging` |
| ports locaux | `bloc_ports` + 0 pour la prod, + 1 pour le staging, + 9 pour le test de restauration, tous sur `127.0.0.1` |
| sauvegardes distantes | `sauvegardes:<nom>-sauvegardes` |

**Le clone.** En HTTPS sans clé pour un dépôt public. Pour un dépôt privé, avec une clé de
déploiement en lecture seule, comme `ancrage`.

**Les images.** Celle d'un dépôt public est publique sur GHCR, et le serveur la télécharge sans
jeton. Pour les images privées, un **seul** jeton GitHub `read:packages` sert à tout le serveur,
rangé dans un fichier de configuration de l'utilisateur du serveur. Son échéance est notée dans `REGISTRE.md`.

**Les unités.** `<nom>-sonde-prod` et `<nom>-sonde-staging` (`.service` et `.timer`, toutes les 5
minutes), `<nom>-alerte@.service` (déclenchée par `OnFailure=`). Si `sauvegardes` vaut oui,
s'ajoutent `<nom>-sauvegarde` (chaque nuit) et `<nom>-test-restauration` (chaque dimanche). Les
heures sont réparties par projet dans `REGISTRE.md`, pour que deux sauvegardes ne se chevauchent
pas.

### 6.3 Le chemin d'une version

C'est celui d'`ancrage`, sans changement.

1. **Une fusion sur `main`.** La CI vérifie, construit l'image, la lance, contrôle la route de
   santé et la révision, passe les tests de bout en bout du projet contre l'image, puis publie
   `:sha-<sha>` et `:main`. La sonde de staging la déploie dans les 5 minutes.
2. **Une étiquette `vX.Y.Z`, avec l'accord d'Edouard.** `modele-version.yml` vérifie que le
   commit est un ancêtre de `main` et que `:sha-<sha>` existe, puis il **réétiquette sans
   reconstruire**. Il refuse de réécrire une version existante dont l'empreinte serait différente,
   et crée la Release GitHub. La sonde de prod suit dans les 5 minutes.
3. **Un déploiement qui échoue** : la version est marquée `echec` et **jamais retentée**, le
   retour à la précédente est automatique, et Healthchecks reçoit `/fail`. Le retour manuel se
   fait par `deployer.sh <env> --retour`.

### 6.4 Les secrets

- **`.sops.yaml`** chiffre `deploiement/secrets/<env>.env.enc` vers les deux clés publiques du
  parc, `serveur.pub` et `hors-ligne.pub`. Ces deux fichiers figurent dans le modèle : une clé
  publique peut être publiée.
- **Le contenu.** En prod : `HC_SONDE`, plus `HC_SAUVEGARDE` et `HC_TEST_RESTAURATION` si
  `sauvegardes` vaut oui. En staging : `HC_SONDE`. **Plus de `TUNNEL_TOKEN`** : le tunnel est
  commun.
- **Le déchiffrement** reste celui d'`ancrage` : un fichier temporaire de mode 600 dans
  `/dev/shm`, détruit par `shred -u`, jamais sourcé.
- **La clé serveur** est un fichier `serveur.txt` dans le dossier des clés age de l'utilisateur du
  serveur : c'est l'actuelle clé d'`ancrage`, renommée au lot 2.
- **Changer une valeur.**
  1. 👤 Sur le serveur, `~/<nom>/deploiement/secrets.sh definir <env> <CLE>`, en saisie masquée.
  2. 🤖 La session rapatrie le fichier chiffré par `scp` (une lecture) et ouvre une PR.

  En prod, la nouvelle valeur n'entre en service qu'avec l'étiquette suivante.

### 6.5 Le tunnel commun

- **Où il vit.** Dans `serveur/tunnel/compose.yml` : un conteneur `cloudflared` épinglé par
  empreinte. Son jeton est chiffré dans `serveur/secrets/tunnel.env.enc`.
- **Comment il atteint une app.** Chaque environnement de projet a son réseau Docker,
  `tunnel-<nom>-<env>`. Il est créé par `mettre-en-service.sh`, puis déclaré `external` à la fois
  dans `compose.yml` du projet et dans celui du tunnel.
  - L'app y porte l'alias `<nom>-<env>`, puisque tous les services s'appellent `app`.
  - Le tunnel la rejoint à chaud (`docker network connect`), sans redémarrage, donc sans coupure
    pour les autres sites. La liste des réseaux dans son `compose.yml` assure qu'il les retrouve
    au prochain démarrage.
- **Les routes**, dans Cloudflare : `<sous_domaine>.<domaine>` vers `http://<nom>-prod:<port_app>`,
  et `<sous_domaine>-staging.<domaine>` vers `http://<nom>-staging:<port_app>`. Elles sont notées
  dans `REGISTRE.md`.
- **Pas de Cloudflare Access devant ces apps**, sauf décision du projet. La sonde tient une
  redirection pour un échec.
- **Pourquoi des réseaux et pas le réseau de l'hôte.** Un tunnel sur le réseau de l'hôte
  atteindrait tous les ports locaux de la machine, y compris ceux d'autres services et d'une
  interface d'administration. Une route mal posée suffirait à les publier. Avec un réseau par projet, le tunnel
  n'atteint que les apps.

### 6.6 Les sauvegardes

- **Chaque nuit** : `sauvegarder.sh prod` lance `sauvegarder` dans l'image et y vérifie
  l'instantané. Il garde une copie en clair 30 jours dans `quotidiennes/`, puis chiffre l'archive
  vers `hors-ligne.pub` et l'envoie avec `rclone`, où elle est gardée 90 jours.
- **L'alias `rclone`.** `sauvegardes:` est un alias du remote rclone actuel. Les nouveaux
  projets ne portent plus son nom, et rien n'est reconfiguré.
- **Chaque dimanche** : `tester-restauration.sh` restaure la dernière sauvegarde dans un conteneur
  jetable, sur `bloc_ports + 9`, puis lance `verifier`.
- **Chaque trimestre** : **un seul** exercice de restauration pour tout le parc, sur le poste, avec
  la clé hors ligne passée par l'entrée standard. Il télécharge la dernière sauvegarde de chaque
  projet, la déchiffre avec la clé commune et lance le `verifier` de ce projet. La clé est éprouvée
  une fois, les données de chaque projet aussi. Sa date et sa durée vont dans `REGISTRE.md`.

### 6.7 La supervision

Healthchecks.io, dans le projet Healthchecks habituel d'Edouard, fuseau `Europe/Zurich` :

| Contrôle | Calendrier | Délai de grâce |
|---|---|---|
| `<nom>-sonde-prod`, `<nom>-sonde-staging` | toutes les 5 minutes | 30 minutes |
| `<nom>-sauvegarde` (si sauvegardes) | l'heure notée au registre | 2 heures |
| `<nom>-test-restauration` (si sauvegardes) | le dimanche, à l'heure notée au registre | 6 heures |

Les adresses de ping ne sont jamais journalisées : elles passent à `curl` par `-K -`.

### 6.8 La mise en service d'un projet

| # | Qui | Quoi |
|---|---|---|
| 1 | 🤖 | Une PR dans `serveur` réserve le bloc de ports, les heures de sauvegarde et les routes dans `REGISTRE.md`, et ajoute les réseaux au `compose.yml` du tunnel |
| 2 | 👤 | Cloudflare : deux routes sur le tunnel commun |
| 3 | 👤 | Healthchecks : deux ou quatre contrôles, adresses rangées dans KeePassXC |
| 4 | 👤 | Sur le serveur, `~/serveur/mettre-en-service.sh <nom>`. Il crée les clones, les dossiers et les réseaux, rattache le tunnel, installe les unités, et demande les adresses Healthchecks en saisie masquée pour produire les fichiers chiffrés |
| 5 | 🤖 | La session rapatrie les secrets chiffrés dans une PR du projet, puis vérifie les deux adresses publiques et la route de santé |
| 6 | 👤 | Une étiquette `v0.1.0`, quand le staging convient |

**Cible : 15 minutes de manipulations pour Edouard**, étapes 2 à 4 et 6 cumulées.

---

## 7. La cible `statique`

- **Qui publie.** La CI du projet, avec `wrangler`, une fois les contrôles du socle verts.
  **Pas** l'intégration GitHub de Cloudflare, qui construit et publie chaque branche sans attendre
  ces contrôles.
- **La construction.** `modele-statique.yml` (géré) appelle l'action `.github/actions/construire/`
  (semée). Par défaut, celle-ci recopie `site/`. Un projet en Vite, en Astro ou en Rust/WASM y
  installe ses outils et lance sa construction. Seule exigence : le résultat est dans
  `dossier_publie`.
- **Le chemin d'une version**, le même qu'en cible `serveur` :

  | Événement | Résultat |
  |---|---|
  | une PR | une adresse de prévisualisation propre à la PR |
  | une fusion sur `main` | l'adresse `main.<nom>.pages.dev`, qui tient lieu de staging |
  | une étiquette `vX.Y.Z`, avec l'accord d'Edouard | la prod, sur `<sous_domaine>.<domaine>` ou la racine du domaine |

  La branche de production du projet Cloudflare **n'est pas `main`**. L'étiquette déclenche
  `modele-version.yml`, qui vérifie que le commit est un ancêtre de `main`, reconstruit le site à
  ce commit et le publie par `--branch production`. Une session qui fusionne seule ne met donc rien
  en prod.
- **Les secrets.** `CLOUDFLARE_API_TOKEN`, un jeton **unique** limité à la publication des sites,
  et `CLOUDFLARE_ACCOUNT_ID`. Ils sont rangés dans KeePassXC et posés dans chaque dépôt par
  `Nouveau-Projet.ps1`.
- **La mise en service.**
  1. 👤 Associer le domaine personnalisé au projet Cloudflare, une fois.
  2. 👤 Poser la première étiquette.
- **L'exploitation.** Pas de Healthchecks, pas de sauvegarde. Le retour arrière consiste à
  republier l'étiquette précédente (relancer `modele-version.yml` sur elle).
- **Passer à la cible `serveur`.** Changer `cible` dans `.copier-answers.yml`, puis lancer
  `copier update`. `deploiement/` arrive, `modele-statique.yml` s'en va, et le projet écrit son
  `Dockerfile`, par exemple un nginx qui sert `dossier_publie`.

---

## 8. Fichiers gérés, fichiers semés

- **Gérés** (`[G]` au §4) : réécrits par chaque `copier update`. **On ne les modifie jamais dans
  le projet.** Une modification locale ressort en conflit à la mise à jour suivante, et c'est
  voulu : le défaut se corrige dans le modèle, pour tous. **Un conflit dans un fichier géré se
  résout toujours en faveur du modèle.** Une seule exception à la règle : les PR Dependabot qui
  montent une version d'action dans un fichier géré se fusionnent normalement.
- **Semés** (`[S]`, `_skip_if_exists` dans Copier) : créés une fois, puis au projet. Un
  `copier update` ne les touche plus.
- **Un cas mixte, `.claude/settings.json`.** Le modèle y pose le hook du garde (*superpowers* n'y est pas
  déclaré, voir §5.2). Le projet y ajoute ses réglages : le plugin Nx et ses permissions pour
  `creche-planner`, par exemple. Le fichier passe par la fusion à trois voies de Copier. C'est le
  point de friction connu : un conflit s'y résout à la main, dans la PR de mise à jour.
- **Changer de cible.** Les fichiers gérés propres à l'ancienne cible disparaissent, ceux de la
  nouvelle arrivent. Les fichiers semés de l'ancienne cible restent : le projet les retire à la
  main dans la même PR.

---

## 9. Le dépôt `serveur`

Volontairement absent de ce document public : son contenu (notice de la machine, registre, tunnel commun) est privé et vit dans le dépôt `serveur`. Le numéro est conservé pour que les renvois tiennent.

---

## 10. Les tests du modèle

Dans la CI de `modele-projet` :

1. **Rendu de toutes les combinaisons** : chaque cible × `public`/`prive` × avec ou sans
   sauvegardes. Chaque projet rendu doit passer ses propres portes, plus `shellcheck` sur
   `deploiement/` et `ruff` sur `scripts/modele/`.
2. **La mécanique serveur.** Les tests bats d'`ancrage`, paramétrés par `nom`, dans l'image de
   test qui contient `age` et `sops` aux sommes vérifiées.
3. **Une fausse app.** Dans `tests/modele/fausse-app/`, quelques lignes de Python qui respectent
   le contrat : la route de santé, `sauvegarder`, `verifier`. Depuis le lot 12, elle lit aussi son
   instance (M-0003, § 6) : `/config` et `/contenu`, chacun avec sa version de schéma, les
   commandes `verifier-config` et `verifier-contenu`, et le champ `configuration` de la santé
   (`exemple` ou `montee`) ; son exemple est dans `exemple/` et `exemple-contenu/`. Le job
   `fausse-app` rend un projet `serveur` de nature `code` qui déclare les deux commandes, et la CI
   d'image tourne sur elle de bout en bout : construction, santé, révision, sauvegarde,
   vérification, l'exemple de l'instance. Puis deux épreuves sur le Docker du job : le ménage des
   images (`tests/modele/epreuve-menage.sh`) et la chaîne à deux dépôts
   (`tests/modele/epreuve-donnees.sh`), de `deployer.sh` aux montages et à la santé.
4. **La mise à jour.** On rend la version précédente du modèle, on la met à jour vers la nouvelle,
   et on vérifie qu'aucun conflit n'apparaît sur un projet resté intact.
5. **Les versions du modèle** : des étiquettes `vX.Y.Z` sur `modele-projet`, avec Release et
   notes. Chaque projet note la sienne dans `.copier-answers.yml`.

---

## 11. L'ordre de construction et d'alignement

Chaque lot a son propre plan (`writing-plans`) et sa propre exécution. **Le premier plan à écrire
est celui du lot 1.**

| Lot | On construit | Ce qui le valide |
|---|---|---|
| 1 | Le socle (cible `aucune`), `Nouveau-Projet.ps1`, le détecteur de dérive | **`ancrage` aligné en cible `aucune`** : la méthode seule, sans toucher à sa mécanique |
| 2 | La cible `serveur` et le dépôt `serveur` | **`ancrage` passe en `serveur`** : test d'acceptation (critère 1) |
| 3 | La cible `statique` | **Le site perso naît**, par `Nouveau-Projet.ps1` |
| 4 | — | `pupitre`, cible `aucune` : **fait le 27/10/2026** (pupitre#7, sur la `v0.2.3`) |
| 5 | — | `partition`, cible `aucune` |
| 6 | — | `veille-emploi`, cible `aucune` |
| 7 | — | `creche-planner`, cible `aucune` |

**Aligner un projet existant** : `copier copy` sur le dépôt, dans un worktree
`<nom>.worktrees\modele-alignement`, relire la différence, puis l'envoyer en PR.

### Lot 1 — le socle

- 👤 Préalable : créer `EdouardZemb/modele-projet`, public.
- 🤖 Installer Copier sur le poste avec `pipx`. Python 3.12 y est.
- **`Nouveau-Projet.ps1`**, enregistré en UTF-8 avec BOM, en paramètres plutôt qu'en `Read-Host` :
  1. vérifier les préalables (`copier`, `gh` connecté, Python) et refuser un dossier qui existe
     déjà ;
  2. `copier copy --vcs-ref <dernière étiquette> gh:EdouardZemb/modele-projet
     C:\src\github.com\EdouardZemb\<nom>` ;
  3. premier commit, puis `gh repo create EdouardZemb/<nom> --public|--private --source . --push` ;
  4. `git config core.hooksPath .githooks` ;
  5. pour un dépôt public, appliquer `ruleset-main.json` par `gh api` ;
  6. poser les secrets de CI : `MOTIFS_INTERDITS`, et pour la cible `statique` les deux secrets
     Cloudflare, en saisie masquée ;
  7. créer `C:\src\github.com\EdouardZemb\<nom>.worktrees\` ;
  8. ajouter la ligne du projet à `Documents\INDEX-PROJETS.md` ;
  9. afficher les étapes de mise en service, si la cible n'est pas `aucune`.
- **Le détecteur de dérive** : pour chaque dépôt de `C:\src\github.com\EdouardZemb\`, hors
  `.PERIME-`, `.worktrees` et quarantaines, il alerte sur l'absence de `.copier-answers.yml` et sur
  un `core.hooksPath` différent de `.githooks`. Les dépôts pas encore alignés sonneront jusqu'à leur
  lot, et c'est attendu. La liste de ces alertes connues va dans la note de ligne de base du
  `CLAUDE.md` du chantier.
- **L'alignement d'`ancrage`.**
  - Son `CLAUDE.md` est semé, donc Copier n'y touche pas : la PR y ajoute à la main la ligne
    d'import, et retire de sa section « Méthode » ce que `methode.md` couvre désormais.
  - Même chose pour son `.github/workflows/ci.yml`, semé lui aussi : la PR y ajoute à la main
    l'appel à `modele-socle.yml`. **C'est la règle de tout alignement** : un fichier semé qui
    existe déjà n'est jamais écrasé, et la PR d'alignement y reporte à la main ce que le modèle y
    aurait mis.
  - Ses ADR 0001 à 0007 restent les siens. Les ADR hérités arrivent dans `docs/modele/decisions/`.

### Lot 2 — la cible `serveur`

- 👤 Préalable : créer `EdouardZemb/serveur`, privé.
- **Ce que la mécanique doit à `ancrage`.** Elle est extraite de `deploiement/` et
  `tests/deploiement/`, avec `ancrage` remplacé par `nom` partout.
- **Les migrations décidées pour `ancrage`.** Ce sont les seules différences admises par le
  critère 1 :
  1. **Le tunnel.** Ses routes passent sur le tunnel commun, ses deux tunnels sont supprimés (👤),
     et `TUNNEL_TOKEN` quitte ses secrets. Le retrait suit l'invariant 4 : d'abord `compose.yml`
     cesse de l'exiger, ensuite on retire la valeur, une version plus tard.
  2. **La clé sops.** Le fichier de la clé serveur d'`ancrage` devient `serveur.txt`.
  3. **Le jeton GHCR.** Son fichier, propre à `ancrage`, devient celui de tout le serveur. Son
     échéance du 16/10/2027 passe dans `REGISTRE.md`.
  4. **La CLI de sauvegarde** travaille sur un dossier : aujourd'hui, un `.sqlite` et un
     `.comptes.json` séparés.
  5. **`rclone`** : l'alias `sauvegardes:`, sans déplacer le dossier existant.
  6. **Les ADR hérités M-0003 à M-0005** s'ajoutent à côté de ses ADR 0006 et 0007, qui restent les
     siens.
- **La dette héritée.** La mécanique extraite emporte les issues #15 (le clone reste sur
  l'étiquette quittée après un retour), #16 (purge des images et des instantanés) et #21
  (`client_id` de `rclone`). Elles se corrigent désormais **dans le modèle**, une fois pour tous,
  et sont transférées comme issues de `modele-projet`.
- **`NOTICE.md`** reprend les notes d'exploitation actuelles du serveur : 👤 Edouard en fournit le
  contenu, puisque les sessions ne l'ont jamais lu.

### Lot 3 — la cible `statique`

- 👤 Un jeton Cloudflare de publication, rangé dans KeePassXC.
- Le site perso naît par `Nouveau-Projet.ps1` : la première vraie naissance.

### Lots 4 à 7

| Projet | Ce que l'alignement contient | Préalable |
|---|---|---|
| `pupitre` | **Fait le 27/10/2026 (pupitre#7, sur la `v0.2.3`).** Le plan de départ était périmé : ses documents étaient déjà dans `docs/` depuis le 11/10, rien à déplacer. L'alignement apporte le `CLAUDE.md` et ramène les commits au format du modèle. Ses deux portes propres, `contenu` et `documentation`, sont gardées à côté du socle ; ses ADR restent dans `docs/adr/`. Le piège de LE-23 est revenu une seconde fois : son `.gitignore` masquait `.claude/` et `secrets.*`, d'où des exceptions nommées (LE-24). Son gabarit de PR, un fichier géré qui différait de celui du modèle, a arrêté `copier copy` et demandé `--skip` ; le modèle sera rétabli à la clôture de son lot B (LE-25) | — |
| `partition` | La méthode. `DECISIONS.md` et `QUESTIONS.md` sont rapprochés de `docs/decisions/` et `pistes.md`. Sa CI propre, qui refuse l'audio et le MIDI, reste | — |
| `veille-emploi` | La méthode. Son dépôt de travail devient un clone dans `C:\src\github.com\EdouardZemb\veille-emploi`. **Sa branche par défaut est `principal`, pas `main`** : la règle de protection, le hook `pre-push` et le hook Claude doivent prendre la branche par défaut comme paramètre, ce que le lot 1 prévoit | 👤 Committer et pousser le correctif du 15/10, toujours dans l'arbre de travail du serveur |
| `creche-planner` | La méthode et les ressources partagées. Ses hooks husky et sa porte de confidentialité en Node doublonnent ceux du modèle : le lot décide lesquels il garde. Son ADR-0010 renvoie à M-0001. Il garde `docs/adr/` et son registre doc 34 | Une décision à part sur ses clés, qui sera l'occasion de le rattacher aux clés du parc |

---

## 12. Les critères de réussite

1. **Au lot 2**, `copier` appliqué à `ancrage` en cible `serveur` ne montre que des différences
   de paramètres et les six migrations listées au §11.
2. **Un projet neuf naît en une commande** (`Nouveau-Projet.ps1`), et sa mise en service demande
   **moins de 15 minutes** de manipulations à Edouard. C'est mesuré au lot 3 pour `statique`, et au
   prochain projet `serveur`.
3. **Une correction du modèle atteint un projet** par `copier update` et une PR, sans conflit sur
   un fichier semé.
4. **À la fin du lot 7**, chaque dépôt actif a son `.copier-answers.yml` et `core.hooksPath` vaut
   `.githooks`. Le contrôle de dérive revient à ses 2 alertes connues.

---

## 13. Ce qui reste à la main d'Edouard

- Créer `modele-projet` (public) et `serveur` (privé) sur GitHub, puis lancer
  `Nouveau-Projet.ps1`. Ce sont des écritures sur GitHub.
- Pour chaque projet **aligné** (pas créé par `Nouveau-Projet.ps1`) : poser le secret
  `MOTIFS_INTERDITS` et, s'il est public, appliquer `ruleset-main.json`. Le lot d'alignement en
  donne les deux commandes `gh`.
- **Toutes les écritures sur le serveur** : `git pull` de `serveur`, `mettre-en-service.sh`,
  `secrets.sh definir`, `installer-outils.sh`, et les migrations du lot 2.
- Dans Cloudflare : les routes du tunnel, le jeton de publication des sites, les domaines
  personnalisés, la suppression des deux anciens tunnels d'`ancrage`.
- Dans Healthchecks : les contrôles.
- Chaque étiquette de prod.
- Avant le lot 6 : committer le correctif de `veille-emploi`.
- Le contenu des notes d'exploitation actuelles du serveur, pour `NOTICE.md`.

---

## 14. Les exceptions déclarées

- **`.copier-answers.yml`**, contre la règle « pas de manifeste machine » du §7 du plan de
  rangement (Q2 bis). L'exception s'inscrit dans `INDEX-PROJETS.md`, section « Exceptions
  déclarées », au lot 1.

---

## 15. Ce qui reste à arbitrer, ce qui reste à vérifier

### Arbitré par Edouard

1. **Le mutation testing — tranché le 16/10 : le défaut proposé est retenu.** L'ADR-0010 de `creche-planner`, §4, en fait une condition d'entrée de
   toute nouvelle application. À la Q7, il a été rangé avec ce qui tient à la taille de
   `creche-planner`. Les deux textes se contredisent.

   **Défaut proposé** : `methode.md` énumère les cinq familles de garde-fous de l'ADR-0010 comme
   une **obligation du projet**. Le modèle en outille quatre : ADR, CI qui refuse, recherche de
   secrets, aucune donnée réelle. La mutation reste au projet, avec l'outil de sa stack, exigée
   dès que le projet a une logique de domaine. Un site sans logique n'est pas concerné.

   **Alternative** : amender l'ADR-0010 pour retirer la mutation de la condition d'entrée.

### À vérifier au moment d'écrire le plan

Ce ne sont pas des décisions : des faits à établir, chacun avec la façon de trancher.

| Fait à établir | Si oui | Si non |
|---|---|---|
| Cloudflare recommande-t-il encore Pages, ou Workers avec fichiers statiques, pour un nouveau site ? | Pages | Workers. `wrangler` publie dans les deux cas, et Workers ouvre la passerelle vers un tableau des scores (piste, §16) |
| Une image publiée par la CI d'un dépôt public est-elle publique d'emblée sur GHCR ? | rien à faire | une étape 👤 à la mise en service : passer le paquet en public |
| `copier update` retire-t-il les fichiers gérés d'une cible abandonnée ? | §8 tient | un `_tasks` de nettoyage, testé au §10 |
| Un hook git en Python s'exécute-t-il sous Git for Windows sans buter sur l'alias `python3` du Microsoft Store ? | hooks en Python direct | **Établi le 16/10 : non.** Dans Git Bash, `python3` est le raccourci du Store. D'où `scripts/modele/lancer.sh`, qui essaie `python3`, `python`, puis `py -3` |
| Un hook Claude Code `PreToolUse` s'exécute-t-il de la même façon sous Windows et dans une session à distance ? | un seul script | **Établi le 16/10 : oui**, en forme « shell » : Git Bash sous Windows, `sh -c` sous Linux, `CLAUDE_PROJECT_DIR` exporté. Le hook doit aussi surveiller l'outil PowerShell (`matcher: "Bash\|PowerShell"`) |
| Les contrôles requis d'un *ruleset* se nomment-ils `<job appelant> / <job appelé>` pour un workflow réutilisable ? | le JSON les nomme ainsi | relever les noms réels sur un premier dépôt |
| Renovate sait-il suivre un modèle Copier ? | une piste : PR de mise à jour automatiques | rien |

---

## 16. Hors périmètre

- **Le tri des 67 dépôts GitHub** (le brief, démarche n° 1).
- **Les trous du serveur** : `analyse-demos`, `test-framework`, `inventaire`.
- **La gestion des clés de `creche-planner`**, décision à part.
- **La mécanique en image versionnée** (approche 3). À rouvrir au quatrième projet `serveur`.
- **Le déploiement de `creche-planner` par le modèle** (option B de la Q11). À rouvrir quand le
  modèle aura tourné sur trois projets.
- **Pistes, pour `pistes.md` de `modele-projet`** :
  - la passerelle Workers et D1 pour un tableau des scores du site perso ;
  - la création des routes et des contrôles par les API Cloudflare et Healthchecks, si la
    mise en service manuelle dépasse ses 15 minutes ;
  - Renovate, pour proposer automatiquement les `copier update`.
