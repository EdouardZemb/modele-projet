#!/usr/bin/env bash
# L'épreuve des données, sur un vrai Docker (lot 12, #64 ; la copie du journal, lot 18, #133 ; le
# relais du staging, lot 19, #151) : la chaîne à deux dépôts (M-0006, §§ 5 et 6), de deployer.sh à
# la santé de l'app, la copie du journal de l'app avant le remplacement de son conteneur, et le
# relais qui marque le staging, jamais la prod (scripts/modele/marque.py, compose.marque.yml).
#
#   bash tests/modele/epreuve-donnees.sh <rendu>
#
# <rendu> est un projet de la cible serveur rendu par le modèle en nature code (deux dépôts), avec
# le préfixe FAUSSE_APP_, la fausse app posée dedans et un deploiement/projet.env qui déclare
# VERIFIER_CONFIG et VERIFIER_CONTENU. L'image fausse-app:ci, celle de l'action
# modele-image-construire, est déjà construite, et sa révision est un SHA de commit. Les tests bats
# lancent deployer.sh contre des doubles ; ici, le vrai Docker montre ce que les doubles ne peuvent
# pas : les montages que docker compose fait vraiment de l'instantané (leur source, leur lecture
# seule), la recréation du conteneur, les commandes de vérification dans leur conteneur jetable, et
# la santé que sert l'app ; et, pour la copie du journal, un journal tourné par un plafond réduit,
# dont la copie garde la ligne écrite avant la rotation (`docker logs` lit les fichiers tournés de
# json-file), la copie d'un conteneur arrêté, que `docker compose ps --all` liste, le nom entier de
# la copie, avec la version lue dans l'environnement du conteneur par FORMAT_VERSION, et `2>&1` : la
# fausse app écrit ses lignes sur sa sortie d'erreur, que la copie doit garder ; et, pour le relais
# du staging, ce que fait Compose : `!reset` et `!override`, qui retirent à app son port et son
# alias, depends_on, qui ne règle que l'ordre des démarrages (aucune étape ne le vérifie),
# --remove-orphans, le chemin relatif d'un montage dans un fichier ajouté par -f, et l'étiquette
# qui recrée le relais quand son script change. Compose recrée le relais dès qu'il recrée app, dont
# il dépend, que l'étiquette ait changé ou non : l'étiquette ne sert que quand app n'est pas
# recréé, et une étape isolée le prouve (6.3 ter).
# Le job fausse-app installe avant l'épreuve le Compose de la cible, 2.26.1, celui du binaire amont
# (tests/modele/docker-cible.env) : la ligne qui ouvre l'épreuve dit la version qu'elle a trouvée.
#
# Préparation, tout dans un dossier de travail :
#   - age, par apt s'il manque (le runner ne l'a pas), et sops, à la version épinglée, téléchargé de
#     sa publication, son empreinte vérifiée avant usage ;
#   - un registre local, où l'image est poussée : deployer.sh la prend par son empreinte ;
#   - les réseaux du tunnel, tunnel-fausse-app-prod et -staging, que compose.yml déclare externes ;
#   - une identité age jetable, et un faux dépôt de données, git local : env/, .sops.yaml, cles/, les
#     secrets chiffrés pour cette identité, config/ et contenu/ ; deux commits, et l'étiquette
#     donnees-<AAAA.MM.JJ>.1 sur le premier (deployer.sh ne lit pas les étiquettes : il reçoit le
#     commit) ;
#   - une copie du code, d'où deployer.sh est lancé ; son compose.projet.yml réduit le plafond du
#     journal de l'app (json-file, max-size 2k, max-file 5), pour qu'il tourne pendant l'épreuve ;
#     les dossiers de données de l'app (/donnees), vides, comme ceux que la sonde de serveur crée :
#     sur le serveur, le dossier de l'hôte cache le /donnees de l'image, et l'app sème le sien au
#     premier démarrage ; HOME, un dossier de l'épreuve ;
#   - la racine de l'état passe par un lien symbolique, lien-etat -> etat-reel, pendant toute
#     l'épreuve : deployer.sh compare les montages sans résoudre les liens.
#
# Déroulé, chaque point constaté par docker inspect, par la santé ou par le journal de deployer.sh :
#   1. le premier couple, l'image et le commit 1, se déploie en prod : VERIFIER_CONTENU a tourné
#      (code 0), sans contenu en service ; /config et /contenu montés en lecture seule depuis
#      instantanes/<commit 1>, sources sans « // », santé « montee » ; le dossier de données, vide
#      avant, porte MARQUE après : l'app l'a semé ; puis 30 requêtes à la santé et une à
#      /derniere-requete, qui rend 404 : le journal de l'app a tourné (<LogPath>.1 existe, lu en
#      root) ;
#   2. seul le commit change (commit 2) : VERIFIER_CONTENU a tourné (code 0) avec /en-service, le
#      contenu du couple 1 ; le conteneur est recréé sur instantanes/<commit 2>, même image ; avant
#      son `up`, deployer.sh a copié le journal du conteneur du couple 1 dans journaux/ de l'état,
#      sous la racine en lien : une copie, en 600, nommée <horodatage>-<version>-<12 premiers
#      caractères du conteneur>.log, qui porte la ligne de démarrage de l'app, écrite dans un
#      fichier déjà tourné, et la dernière requête : `docker logs` lit les fichiers tournés, et la
#      version se lit dans l'environnement du conteneur, seule ;
#   3. un troisième commit porte une configuration que verifier-config refuse, et le journal en dit
#      la cause, la version de schéma 99, inconnue : code 1, echec porte le couple, le conteneur en
#      service n'a pas bougé, /config et /contenu toujours sur le commit 2 ; aucune copie de plus ;
#   4. le conteneur du couple 2 est arrêté (`docker stop`), puis --retour remet le couple 1 : une
#      seconde copie, celle du conteneur arrêté, que `docker compose ps --all` liste, nommée de
#      même, porte sa ligne de démarrage ;
#   5. le ménage qui suit ce retour retire un instantané qui n'est plus gardé : deux instantanés
#      laissés par d'anciens déploiements, datés de trois et de deux jours, sont posés juste avant ;
#      avec ceux des commits 2 et 3, ils dépassent la marge (les 3 plus récents) : le plus ancien
#      part, le reste demeure ;
#   6. le staging, puis le relais qui le marque, en cinq étapes :
#      6.1 sans marque. Le staging se déploie sur la tête de la branche des données, le commit 3,
#          dont il ne lit jamais config/ : il tourne sans /config, /contenu monté, santé
#          « exemple » ; son dossier de données, vide avant, porte MARQUE après ; deployer.sh l'a
#          marqué (FAUSSE_APP_RELAIS, l'empreinte du script, dans compose.env). Puis compose.env
#          est réécrit sans cette ligne, comme l'écrivait la v0.13.0, et `docker compose up
#          --remove-orphans` est lancé sur les fichiers de `dc` sans compose.marque.yml : app tient
#          le port de la boucle locale et l'alias du tunnel, et aucun conteneur marque n'existe ;
#      6.2 un échec forcé, depuis le staging sans marque : une image dérivée, poussée au registre
#          local, dont l'étiquette de révision diffère de ce qu'annonce sa santé. Son `up` passe le
#          port et l'alias au relais sans erreur de port (Compose crée tous les conteneurs, retire
#          l'ancien `app`, puis démarre ; depends_on ne règle que l'ordre), la santé lue par le
#          relais échoue, et le journal en dit la cause : la révision attendue, celle de l'image
#          dérivée, et celle de la dernière réponse, celle de l'image du couple ; le retour d'echouer
#          recopie le compose.env sans marque : app reprend le port et l'alias, et
#          --remove-orphans retire le relais ;
#      6.3 un déploiement réussi, marqué, d'un couple neuf (le commit 4) : le relais tient le port
#          et l'alias ; la page porte la feuille et le titre préfixé, le manifeste ses noms
#          préfixés et ses icônes vers /.marque/icone, l'icône rendue est un PNG valide de 16 x 16
#          dont aucun pixel ne vaut #0b7f8f, et la santé, lue par ce port, dit le couple. Puis
#          (6.3 bis) le script du relais de la copie change, et le déploiement d'un couple neuf (le
#          commit 5) écrit la nouvelle empreinte, que porte l'étiquette modele.marque.empreinte du
#          relais ; ce déploiement recrée app, et avec lui le relais, que l'étiquette ait changé ou
#          non. Enfin (6.3 ter), l'étiquette seule : un `up` sur les fichiers de `dc`, sans aucun
#          changement, laisse app et le relais en place (le témoin) ; le script change de nouveau,
#          seule la ligne FAUSSE_APP_RELAIS de compose.env suit, et le même `up` recrée le relais,
#          sous la nouvelle empreinte, sans recréer app ; puis le script et compose.env de 6.3 bis
#          reviennent, et un dernier `up` recrée le relais sous l'empreinte de 6.3 bis, toujours
#          sans recréer app : 6.4 part de cet état ;
#      6.4 un second échec forcé, depuis le staging marqué, la cause dite de même : le retour
#          garde le relais, qui tient le port et l'alias ;
#      6.5 « Tout arrêter » : le `down` du staging, sur compose.yml et compose.projet.yml, avec
#          --remove-orphans, retire aussi le relais.
#      À chaque étape, l'épreuve dit qui tient le port et l'alias : /.marque/sante rend 200 par le
#      relais, 404 par l'app, qui ne connaît pas ce chemin ; le port se lit par la boucle locale,
#      l'alias depuis le réseau du tunnel, par un conteneur jetable de l'image de la fausse app,
#      comme le ferait cloudflared (`docker network inspect` ne montre pas les alias). Marqué, app
#      n'est plus sur le réseau du tunnel, d'après `docker container inspect` : sous un alias porté
#      par deux conteneurs, le DNS de Docker rendrait les deux adresses, dans un ordre variable, et
#      une requête seule ne prouverait rien. L'ordre des étapes suit le déploiement : il range
#      d'abord le compose.env en service comme précédent, que le retour d'un échec recopie ; le
#      premier échec suit donc le staging sans marque, pour que son retour revienne sans relais ;
#   7. la prod n'a jamais de relais : aucun conteneur marque dans son projet, ni la ligne
#      FAUSSE_APP_RELAIS dans son compose.env ; la page, le manifeste et l'icône lus par son port
#      sont ceux de l'application, et l'alias fausse-app-prod répond par app.
#
# L'uid. Sur le serveur, le compte qui déploie a l'uid 1000, celui du conteneur. Le runner de GitHub
# a un autre uid : le compose.projet.yml de la copie du code aligne l'app sur le compte qui lance
# l'épreuve, pour que la commande SAUVEGARDER écrive l'instantané d'avant déploiement dans le
# dossier des sauvegardes, que deployer.sh restreint à 700. Les commandes de vérification gardent
# l'uid 1000 des conteneurs jetables : les instantanés leur sont lisibles.
#
# Code de sortie : 0 si tout est comme attendu, 1 sinon, en disant quoi ; 64 usage. À la fin,
# l'épreuve retire ses conteneurs, le relais compris, ses réseaux, son registre, l'étiquette
# qu'elle a posée sur l'image, l'image dérivée qu'elle a construite et son dossier de travail, et
# rien d'autre : l'image du relais, que compose tire, reste, comme celle du registre, et le cache
# de construction de l'image dérivée aussi. En cas d'échec, elle montre d'abord le journal de ses
# conteneurs.
set -Eeuo pipefail

USAGE="usage : bash tests/modele/epreuve-donnees.sh <rendu>"
if [ "$#" -ne 1 ] || [ ! -d "$1" ]; then
  echo "$USAGE" >&2
  exit 64
fi
RENDU="$(cd "$1" && pwd)"
for fichier in deploiement/deployer.sh deploiement/lib.sh deploiement/projet.env; do
  [ -f "$RENDU/$fichier" ] || {
    echo "épreuve : $RENDU/$fichier absent" >&2
    exit 64
  }
done
grep -qx 'MODE_DONNEES="deux"' "$RENDU/deploiement/lib.sh" || {
  echo "épreuve : $RENDU n'est pas rendu à deux dépôts (nature code)" >&2
  exit 64
}
for cle in VERIFIER_CONFIG VERIFIER_CONTENU; do
  grep -q "^$cle=" "$RENDU/deploiement/projet.env" || {
    echo "épreuve : deploiement/projet.env ne déclare pas $cle" >&2
    exit 64
  }
done

IMAGE_CI=fausse-app:ci
REGISTRE_IMAGE='registry:2.8.3@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373'
REGISTRE=epreuve-donnees-registre
DEPOT=localhost:5001/edouardzemb/fausse-app
# sops, linux amd64 : l'empreinte est celle du fichier sops-v3.13.3.checksums.txt de la publication,
# recalculée sur le binaire téléchargé (la même que dans le job tests de la CI).
SOPS_VERSION=3.13.3
SOPS_EMPREINTE=e5bec3346a873ae91d871550f3e698c1aad962aff462a080e40f25fde17fef6b
PROJETS=(fausse-app fausse-app-staging)
PORT_PROD=4310
PORT_STAGING=4311
# port_app, le défaut de copier.yml, que le job rend : le port de la fausse app et du relais dans
# leur conteneur, celui de l'alias du tunnel.
PORT_APP=3000
VERSION=0.1.0
# Ce que la fausse app sert, et que le relais marque en staging (tests/modele/fausse-app/app.py).
TITRE_APP='<title>fausse app</title>'
LIEN_ICONE_APP='<link rel="icon" href="/icone.png">'

# Rien de ce que l'épreuve nommera ne doit exister avant elle : le nettoyage retire tout ce qui
# porte ces noms.
for projet in "${PROJETS[@]}"; do
  if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$projet")" ] \
    || docker network inspect "${projet}_default" >/dev/null 2>&1; then
    echo "épreuve : le projet compose $projet existe déjà sur ce Docker ; l'épreuve ne touche pas à ce qu'elle n'a pas créé" >&2
    exit 1
  fi
done
if docker container inspect "$REGISTRE" >/dev/null 2>&1; then
  echo "épreuve : le conteneur $REGISTRE existe déjà" >&2
  exit 1
fi
REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE_CI" 2>/dev/null)" || {
  echo "épreuve : l'image $IMAGE_CI est absente (l'action modele-image-construire la construit)" >&2
  exit 1
}
[[ "$REVISION" =~ ^[0-9a-f]{40}$ ]] || {
  echo "épreuve : la révision de $IMAGE_CI n'est pas un SHA de commit : '$REVISION'" >&2
  exit 1
}
[ "$(uname -m)" = x86_64 ] || {
  echo "épreuve : sops est pris pour linux amd64, pas pour $(uname -m)" >&2
  exit 1
}

TRAVAIL="$(mktemp -d)"
OUTILS="$TRAVAIL/outils"
CODE_CLONE="$TRAVAIL/code"
DEPOT_DONNEES="$TRAVAIL/depot-donnees"
IDENTITE="$TRAVAIL/cles/serveur.txt"
ETAT_REEL="$TRAVAIL/etat-reel"
RACINE_ETAT="$TRAVAIL/lien-etat"
ETAT_PROD="$RACINE_ETAT/prod"
ETAT_STAGING="$RACINE_ETAT/staging"
DONNEES_PROD="$TRAVAIL/donnees/prod/donnees"
DONNEES_STAGING="$TRAVAIL/donnees/staging/donnees"
export HOME="$TRAVAIL/home"
ECHECS=0
CODE=0
POINT=0
REGISTRE_LANCE=0
ETIQUETTE_POSEE=0
DERIVEE_POSEE=0
declare -a RESEAUX_CREES=()

# journal_des_conteneurs : le journal de chaque conteneur de l'épreuve, pour le diagnostic.
journal_des_conteneurs() {
  local projet id
  for projet in "${PROJETS[@]}"; do
    for id in $(docker ps -aq --filter "label=com.docker.compose.project=$projet" 2>/dev/null); do
      echo "--- journal du conteneur $id ($projet)"
      docker logs --tail 50 "$id" 2>&1 | sed 's/^/    /' || true
    done
  done
}

nettoyer() {
  local code=$? projet reseau
  if [ "$code" -ne 0 ] || [ "$ECHECS" -ne 0 ]; then
    journal_des_conteneurs
  fi
  for projet in "${PROJETS[@]}"; do
    docker ps -aq --filter "label=com.docker.compose.project=$projet" 2>/dev/null \
      | xargs -r docker rm -f -v >/dev/null 2>&1 || true
    docker network rm "${projet}_default" >/dev/null 2>&1 || true
  done
  for reseau in "${RESEAUX_CREES[@]}"; do
    docker network rm "$reseau" >/dev/null 2>&1 || true
  done
  [ "$REGISTRE_LANCE" -eq 0 ] || docker rm -f -v "$REGISTRE" >/dev/null 2>&1 || true
  # L'étiquette et l'empreinte du registre local, et elles seules : fausse-app:ci reste. De même
  # pour l'image dérivée du point 6 : son étiquette et son empreinte, qui la retirent.
  if [ "$ETIQUETTE_POSEE" -eq 1 ]; then
    docker image rm "$DEPOT:epreuve" >/dev/null 2>&1 || true
    [ -z "${IMAGE:-}" ] || docker image rm "$IMAGE" >/dev/null 2>&1 || true
  fi
  if [ "$DERIVEE_POSEE" -eq 1 ]; then
    docker image rm "$DEPOT:derivee" >/dev/null 2>&1 || true
    [ -z "${IMAGE_DERIVEE:-}" ] || docker image rm "$IMAGE_DERIVEE" >/dev/null 2>&1 || true
  fi
  # Les instantanés sont figés en lecture seule : les droits d'abord.
  chmod -R u+w "$TRAVAIL" 2>/dev/null || true
  rm -rf "$TRAVAIL"
}
trap nettoyer EXIT
trap 'echo "épreuve : commande en échec, ligne $LINENO : $BASH_COMMAND" >&2' ERR

# verifier <ce qui est attendu> <commande…> : l'épreuve constate, et dit ce qui manque.
verifier() {
  local texte="$1"
  shift
  if "$@"; then
    echo "ok     : $texte"
  else
    echo "ECHEC  : $texte" >&2
    ECHECS=$((ECHECS + 1))
  fi
}
# exiger <ce qui est attendu> <commande…> : comme verifier, mais la suite en dépend ; en échec,
# l'épreuve s'arrête là.
exiger() {
  verifier "$@"
  fin_du_point "$POINT"
}
# fin_du_point <n> : chaque point part de l'état que le précédent a laissé ; s'il y a un échec,
# l'épreuve s'arrête là.
fin_du_point() {
  [ "$ECHECS" -eq 0 ] && return 0
  echo "épreuve : $ECHECS vérification(s) en échec au point $1 ; la suite en dépend : arrêt" >&2
  exit 1
}
code_vaut() { [ "$CODE" -eq "$1" ]; }
fichier_vaut() { [ -f "$1" ] && [ "$(cat -- "$1")" = "$2" ]; }
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
dossier_present() { [ -d "$1" ] && [ ! -L "$1" ]; }
vide() { [ -d "$1" ] && [ -z "$(ls -A -- "$1")" ]; }
egaux() { [ "$1" = "$2" ]; }
differents() { [ "$1" != "$2" ]; }
journal_dit() { grep -qF -- "$2" "$TRAVAIL/journal-$1"; }
journal_tait() { ! grep -qF -- "$2" "$TRAVAIL/journal-$1"; }
lien_en_place() { [ -L "$RACINE_ETAT" ] && [ "$(readlink -- "$RACINE_ETAT")" = "$ETAT_REEL" ]; }

# git_donnees <args…> : git dans le faux dépôt de données, avec une identité d'épreuve.
git_donnees() {
  git -C "$DEPOT_DONNEES" -c user.name=Epreuve -c user.email=epreuve@exemple.org \
    -c commit.gpgsign=false -c tag.gpgsign=false "$@"
}

# donnees_du_commit <n> <version de la configuration> : config/ et contenu/ du commit <n>, écrits
# dans le faux dépôt de données, puis le commit ; son sha dans COMMIT.
donnees_du_commit() {
  rm -rf "${DEPOT_DONNEES:?}/config" "${DEPOT_DONNEES:?}/contenu"
  mkdir -p "$DEPOT_DONNEES/config" "$DEPOT_DONNEES/contenu/pages"
  printf '%s\n' "$2" >"$DEPOT_DONNEES/config/version"
  printf "Instance d'épreuve, commit %s\n" "$1" >"$DEPOT_DONNEES/config/titre"
  printf '1\n' >"$DEPOT_DONNEES/contenu/version"
  printf "Accueil de l'instance d'épreuve, commit %s\n" "$1" >"$DEPOT_DONNEES/contenu/pages/accueil.txt"
  git_donnees add -A
  git_donnees commit -q -m "données de l'épreuve, commit $1"
  COMMIT="$(git_donnees rev-parse HEAD)"
}

# deployer <n> <arguments…> : deployer.sh de la copie du code, dans l'environnement de l'épreuve ;
# son code dans CODE, son journal dans journal-<n>, puis répété.
deployer() {
  local n="$1"
  shift
  CODE=0
  SOPS_AGE_KEY_FILE="$IDENTITE" \
    FAUSSE_APP_CLONE_DONNEES="$DEPOT_DONNEES" \
    FAUSSE_APP_RACINE_ETAT="$RACINE_ETAT" \
    FAUSSE_APP_RACINE_DONNEES="$TRAVAIL/donnees" \
    FAUSSE_APP_RACINE_SAUVEGARDES="$TRAVAIL/sauvegardes" \
    FAUSSE_APP_DOCKER_CONFIG="$TRAVAIL/docker" \
    FAUSSE_APP_DEPOT_IMAGE="$DEPOT" \
    FAUSSE_APP_SANTE_DELAI=2 \
    bash "$CODE_CLONE/deploiement/deployer.sh" "$@" 2>"$TRAVAIL/journal-$n" || CODE=$?
  echo "--- $n : deployer.sh $* : code $CODE"
  sed 's/^/    /' "$TRAVAIL/journal-$n"
}

# conteneur_app <projet> : l'identifiant du conteneur app de ce projet compose.
conteneur_app() {
  docker ps -aq --no-trunc --filter "label=com.docker.compose.project=$1" \
    --filter label=com.docker.compose.service=app
}
un_seul() { [ -n "$1" ] && [ "$(printf '%s\n' "$1" | wc -l)" -eq 1 ]; }
en_marche() { [ "$(docker container inspect --format '{{.State.Running}}' "$1")" = true ]; }
arrete() { [ "$(docker container inspect --format '{{.State.Running}}' "$1")" = false ]; }
demarre_le() { docker container inspect --format '{{.State.StartedAt}}' "$1"; }
image_de() { docker container inspect --format '{{.Image}} {{.Config.Image}}' "$1"; }

# lire_montages <conteneur> : ses montages, une ligne « <point> <RW> <source> » chacun, dans
# MONTAGES, d'après docker container inspect.
lire_montages() {
  MONTAGES="$(docker container inspect --format '{{json .Mounts}}' "$1" \
    | jq -r '.[] | "\(.Destination) \(.RW) \(.Source)"')" || MONTAGES=""
}
champ_du_montage() { awk -v p="$1" -v c="$2" '$1 == p { print $c }' <<<"$MONTAGES"; }

# Les copies du journal de la prod, dans journaux/ de son état, sous la racine en lien.
# nombre_de_copies : les fichiers .log de journaux/ ; copie_du_conteneur <conteneur> : le nom de la
# copie de ce conteneur, d'après les 12 premiers caractères de son identifiant, vide sans elle ;
# nom_de_copie <nom> <conteneur> : <horodatage>-<version>-<12 caractères>.log, la version du couple
# 1 ; copie_dit <nom> <texte> : la copie porte ce texte. Sans journaux/, les deux premières
# rendent 0 copie et un nom vide, sans arrêter l'épreuve : les `verifier` nomment le manque.
nombre_de_copies() {
  [ -d "$ETAT_PROD/journaux" ] || { echo 0; return 0; }
  find "$ETAT_PROD/journaux" -mindepth 1 -maxdepth 1 -type f -name '*.log' 2>/dev/null | wc -l
}
copie_du_conteneur() {
  [ -d "$ETAT_PROD/journaux" ] || return 0
  find "$ETAT_PROD/journaux" -mindepth 1 -maxdepth 1 -type f -name "*-${1:0:12}.log" \
    -printf '%f\n' 2>/dev/null
}
nom_de_copie() {
  local motif="^[0-9]{8}T[0-9]{6}Z-${VERSION//./[.]}-${2:0:12}[.]log$"
  [[ "$1" =~ $motif ]]
}
copie_dit() { [ -n "$1" ] && grep -qF -- "$2" "$ETAT_PROD/journaux/$1"; }
droits_de() { stat -c %a -- "$1" 2>/dev/null; }
monte_une_fois() { [ "$(awk -v p="$1" '$1 == p' <<<"$MONTAGES" | wc -l)" -eq 1 ]; }
non_monte() { [ -z "$(champ_du_montage "$1" 1)" ]; }
sans_double_barre() { [ -n "$1" ] && [[ "$1" != *//* ]]; }
# meme_instantane <source> <commit> <dossier> <dossier d'état réel> : la source désigne
# instantanes/<commit>/<dossier>, sous la racine de l'état, par le lien ou sous son nom réel.
meme_instantane() {
  [[ "$1" == */instantanes/"$2"/"$3" ]] && [ -d "$1" ] \
    && [ "$(realpath -e -- "$1")" = "$(realpath -e -- "$4/instantanes/$2/$3")" ]
}

# constater_montage <conteneur> <point> <env> <commit> <dossier> : <point> est monté une fois, en
# lecture seule, depuis instantanes/<commit>/<dossier> de l'état de <env>, sans « // ».
constater_montage() {
  local source
  lire_montages "$1"
  source="$(champ_du_montage "$2" 3)"
  case "$source" in
    "$RACINE_ETAT"/*) echo "       $2 : source $source (le lien de la racine de l'état, gardé)" ;;
    "$ETAT_REEL"/*) echo "       $2 : source $source (le lien de la racine de l'état, résolu)" ;;
    *) echo "       $2 : source ${source:-aucune}" ;;
  esac
  verifier "$2 monté une fois" monte_une_fois "$2"
  verifier "$2 en lecture seule (RW false)" egaux "$(champ_du_montage "$2" 2)" false
  verifier "$2 : source sans « // »" sans_double_barre "$source"
  verifier "$2 : source = instantanes/$4/$5 ($3)" meme_instantane "$source" "$4" "$5" "$ETAT_REEL/$3"
}

# sante_dit <port> <filtre jq> : la santé de l'app sur ce port répond, et le filtre y vaut true.
sante_dit() {
  local reponse
  reponse="$(curl -fsS -m 5 "http://127.0.0.1:$1/api/sante")" || return 1
  echo "       santé sur $1 : $reponse"
  [ "$(jq -r --arg revision "$REVISION" "$2" <<<"$reponse")" = true ]
}

# planter_instantane <nom> <date> : un instantané laissé par un ancien déploiement, comme
# preparer_instantane les fait (config/ et contenu/, figés en lecture seule), daté de <date>.
planter_instantane() {
  local chemin="$ETAT_PROD/instantanes/$1"
  mkdir -p "$chemin/config" "$chemin/contenu/pages"
  printf '1\n' >"$chemin/config/version"
  printf "Ancienne instance d'épreuve\n" >"$chemin/config/titre"
  printf '1\n' >"$chemin/contenu/version"
  printf 'Ancien accueil\n' >"$chemin/contenu/pages/accueil.txt"
  chmod -R a-w "$chemin"
  touch -d "$2" "$chemin"
}

# en_root <commande…> : la commande, par sudo si l'épreuve n'est pas root (le runner).
en_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

# --- Le relais du staging (point 6) -------------------------------------------------------------

# conteneur_marque <projet> : l'identifiant du conteneur marque de ce projet compose, le relais.
conteneur_marque() {
  docker ps -aq --no-trunc --filter "label=com.docker.compose.project=$1" \
    --filter label=com.docker.compose.service=marque
}
un_seul_en_marche() { un_seul "$1" && en_marche "$1"; }
retire() { ! docker container inspect "$1" >/dev/null 2>&1; }
# empreinte_du_relais : l'empreinte SHA-256 du script du relais de la copie du code, celle que
# deployer.sh écrit dans compose.env en staging.
empreinte_du_relais() { sha256sum <"$CODE_CLONE/scripts/modele/marque.py" | cut -c1-64; }
# relais_vaut <état> <valeur> : le compose.env de cet état existe, et sa ligne FAUSSE_APP_RELAIS
# vaut <valeur> ; une valeur vide : il n'a pas cette ligne. Un compose.env absent échoue, quelle
# que soit la valeur attendue ; un écart dit la valeur lue.
relais_vaut() {
  local lue
  if [ ! -f "$1/compose.env" ]; then
    echo "       $1/compose.env absent" >&2
    return 1
  fi
  lue="$(sed -n 's/^FAUSSE_APP_RELAIS=//p' "$1/compose.env")"
  [ "$lue" = "$2" ] && return 0
  echo "       FAUSSE_APP_RELAIS de $1/compose.env : ${lue:-absente}" >&2
  return 1
}
# etiquette_du_relais <conteneur> : son étiquette modele.marque.empreinte.
etiquette_du_relais() {
  docker container inspect --format '{{index .Config.Labels "modele.marque.empreinte"}}' "$1" \
    2>/dev/null || true
}
# reseaux_de <conteneur> : les réseaux du conteneur, d'après `docker container inspect`, séparés
# par une espace ; vide s'il n'y a pas de conteneur.
reseaux_de() {
  [ -n "$1" ] || return 0
  docker container inspect --format '{{json .NetworkSettings.Networks}}' "$1" 2>/dev/null \
    | jq -r 'keys | join(" ")' 2>/dev/null || true
}
sur_le_reseau() { [[ " $1 " == *" $2 "* ]]; }
hors_du_reseau() { [ -n "$1" ] && ! sur_le_reseau "$1" "$2"; }

# code_par_le_port <port> : le code HTTP de /.marque/sante lu par la boucle locale : 200 quand le
# relais tient le port, 404 quand c'est l'app, qui ne connaît pas ce chemin ; un autre code tel
# quel, « injoignable » sans réponse.
code_par_le_port() {
  local code
  code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1/.marque/sante" \
    2>/dev/null)" || code=injoignable
  printf '%s\n' "$code"
}
# code_par_l_alias <env> : la même requête, vers http://fausse-app-<env>:<port_app>, depuis le
# réseau tunnel-fausse-app-<env>, par un conteneur jetable de l'image de la fausse app, comme le
# ferait cloudflared : `docker network inspect` ne montre pas les alias.
SONDE_ALIAS='import sys, urllib.error, urllib.request
try:
    print(urllib.request.urlopen(sys.argv[1], timeout=5).status)
except urllib.error.HTTPError as erreur:
    print(erreur.code)
except OSError:
    print("injoignable")'
code_par_l_alias() {
  local code
  code="$(docker run --rm --pull never --network "tunnel-fausse-app-$1" --entrypoint python3 \
    "$IMAGE_CI" -c "$SONDE_ALIAS" "http://fausse-app-$1:$PORT_APP/.marque/sante" 2>/dev/null)" \
    || code=injoignable
  printf '%s\n' "$code"
}

# constater_tenants <env> <relais|app> : qui tient le port de la boucle locale de cet environnement
# et l'alias fausse-app-<env> de son réseau du tunnel. Marqué, un seul conteneur marque tourne, et
# app n'est plus sur le réseau du tunnel, mais sur le réseau default du projet : sous un alias
# porté par deux conteneurs, le DNS de Docker rendrait les deux adresses. Sans marque, aucun
# conteneur marque, et app est sur le réseau du tunnel.
constater_tenants() {
  local env="$1" tenant="$2" projet=fausse-app port="$PORT_PROD" attendu=404
  local par_port par_alias app reseaux marque
  if [ "$env" = staging ]; then
    projet=fausse-app-staging port="$PORT_STAGING"
  fi
  [ "$tenant" = app ] || attendu=200
  par_port="$(code_par_le_port "$port")"
  par_alias="$(code_par_l_alias "$env")"
  app="$(conteneur_app "$projet")"
  reseaux="$(reseaux_de "$app")"
  marque="$(conteneur_marque "$projet")"
  echo "       /.marque/sante : $par_port par le port $port, $par_alias par l'alias fausse-app-$env ;" \
    "réseaux d'app : ${reseaux:-aucun} ; relais : ${marque:0:12}"
  verifier "$tenant tient le port $port (/.marque/sante : $attendu)" egaux "$par_port" "$attendu"
  verifier "$tenant tient l'alias fausse-app-$env, lu depuis tunnel-fausse-app-$env (/.marque/sante : $attendu)" \
    egaux "$par_alias" "$attendu"
  if [ "$tenant" = relais ]; then
    verifier "un seul conteneur marque, en marche" un_seul_en_marche "$marque"
    verifier "app n'est pas sur le réseau tunnel-fausse-app-$env" \
      hors_du_reseau "$reseaux" "tunnel-fausse-app-$env"
    verifier "app est sur le réseau ${projet}_default" sur_le_reseau "$reseaux" "${projet}_default"
  else
    verifier "aucun conteneur marque dans le projet $projet" egaux "$marque" ""
    verifier "app est sur le réseau tunnel-fausse-app-$env" \
      sur_le_reseau "$reseaux" "tunnel-fausse-app-$env"
  fi
}

# lire <port> <chemin> <fichier> : le corps de la réponse dans <fichier>, son type dans TYPE_LU ;
# échec sans réponse 2xx.
lire() {
  TYPE_LU="$(curl -fsS -m 10 -o "$3" -w '%{content_type}' "http://127.0.0.1:$1$2")" || {
    TYPE_LU=""
    return 1
  }
}
contient() { [ -f "$1" ] && grep -qF -- "$2" "$1"; }
ne_contient_pas() { [ -f "$1" ] && ! grep -qF -- "$2" "$1"; }
# json_dit <fichier> <filtre jq> : le filtre, appliqué au fichier, vaut true.
json_dit() { [ -f "$1" ] && [ "$(jq -r "$2" "$1" 2>/dev/null)" = true ]; }
# montrer <fichier> : le fichier, ligne à ligne, la dernière finie même sans saut de ligne (le
# manifeste n'en a pas).
montrer() { [ ! -f "$1" ] || awk '{ print "       | " $0 }' "$1"; }

# png_conforme <fichier> <largeur> <hauteur> <toutes|aucune> : un PNG valide (sa signature, le CRC
# de chaque bloc, IHDR d'abord et IEND à la fin, profondeur 8, non entrelacé, les IDAT décompressés
# à la bonne taille, chaque ligne défiltrée), de cette taille ; « toutes » : chaque pixel vaut
# #0b7f8f, la couleur de l'icône de la fausse app ; « aucune » : aucun ne la vaut. Il dit ce qu'il a
# lu, ou pourquoi il refuse.
png_conforme() {
  python3 -I - "$@" <<'PY'
import struct
import sys
import zlib

chemin, largeur, hauteur, quoi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
COULEUR = (0x0B, 0x7F, 0x8F)
CANAUX = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def refus(raison):
    print(f"       PNG refusé : {raison}")
    sys.exit(1)


try:
    with open(chemin, "rb") as fichier:
        donnees = fichier.read()
except OSError as erreur:
    refus(f"illisible ({erreur.strerror})")
if donnees[:8] != b"\x89PNG\r\n\x1a\n":
    refus("signature absente")
blocs, pos = [], 8
while pos < len(donnees):
    if pos + 12 > len(donnees):
        refus("bloc tronqué")
    (taille,) = struct.unpack_from(">I", donnees, pos)
    nom, corps = donnees[pos + 4 : pos + 8], donnees[pos + 8 : pos + 8 + taille]
    if pos + 12 + taille > len(donnees):
        refus(f"bloc {nom!r} tronqué")
    (crc,) = struct.unpack_from(">I", donnees, pos + 8 + taille)
    if zlib.crc32(nom + corps) & 0xFFFFFFFF != crc:
        refus(f"CRC faux sur le bloc {nom!r}")
    blocs.append((nom, corps))
    pos += 12 + taille
if not blocs or blocs[0][0] != b"IHDR" or len(blocs[0][1]) != 13 or blocs[-1][0] != b"IEND":
    refus("IHDR ou IEND absent")
l, h, profondeur, type_couleur, compression, filtrage, entrelace = struct.unpack(
    ">IIBBBBB", blocs[0][1]
)
if (profondeur, compression, filtrage, entrelace) != (8, 0, 0, 0) or type_couleur not in CANAUX:
    refus(f"profondeur {profondeur}, type {type_couleur}, entrelacement {entrelace}")
canaux = CANAUX[type_couleur]
try:
    brut = zlib.decompress(b"".join(corps for nom, corps in blocs if nom == b"IDAT"))
except zlib.error:
    refus("IDAT illisible")
pas = l * canaux + 1
if len(brut) != h * pas:
    refus(f"IDAT de {len(brut)} octets, attendu {h * pas}")
palette = next((corps for nom, corps in blocs if nom == b"PLTE"), b"")
pixels = []
precedente = bytearray(pas - 1)
for y in range(h):
    filtre = brut[y * pas]
    ligne = bytearray(brut[y * pas + 1 : (y + 1) * pas])
    if filtre > 4:
        refus(f"filtre {filtre}, ligne {y}")
    for i in range(len(ligne)):
        a = ligne[i - canaux] if i >= canaux else 0
        b = precedente[i]
        c = precedente[i - canaux] if i >= canaux else 0
        if filtre == 1:
            ligne[i] = (ligne[i] + a) & 255
        elif filtre == 2:
            ligne[i] = (ligne[i] + b) & 255
        elif filtre == 3:
            ligne[i] = (ligne[i] + ((a + b) >> 1)) & 255
        elif filtre == 4:
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            prediction = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            ligne[i] = (ligne[i] + prediction) & 255
    for x in range(l):
        pixel = ligne[x * canaux : (x + 1) * canaux]
        if type_couleur in (2, 6):
            pixels.append(tuple(pixel[:3]))
        elif type_couleur in (0, 4):
            pixels.append((pixel[0],) * 3)
        elif 3 * pixel[0] + 3 <= len(palette):
            pixels.append(tuple(palette[3 * pixel[0] : 3 * pixel[0] + 3]))
        else:
            refus(f"index {pixel[0]} hors de la palette")
    precedente = ligne
egaux = sum(1 for pixel in pixels if pixel == COULEUR)
print(f"       PNG de {l} x {h}, type {type_couleur} : {egaux} pixel(s) #0b7f8f sur {len(pixels)}")
if (l, h) != (largeur, hauteur):
    refus(f"{l} x {h}, attendu {largeur} x {hauteur}")
if (quoi == "toutes" and egaux != len(pixels)) or (quoi == "aucune" and egaux):
    sys.exit(1)
PY
}

# compose_staging <comme-dc|sans-marque> <n> <arguments…> : docker compose sur le staging, sous le
# DOCKER_CONFIG de l'épreuve, avec les fichiers que prend `dc` d'après compose.env : comme-dc,
# compose.marque.yml en dernier quand compose.env porte FAUSSE_APP_RELAIS ; sans-marque, ceux que
# `dc` prenait avant le lot 19, sans compose.marque.yml. Son code dans CODE, sa sortie dans
# journal-<n>, puis répétée.
compose_staging() {
  local mode="$1" n="$2"
  shift 2
  local -a fichiers=(-f "$CODE_CLONE/deploiement/compose.yml"
    -f "$CODE_CLONE/deploiement/compose.projet.yml")
  if grep -q '^FAUSSE_APP_CONFIG=' "$ETAT_STAGING/compose.env"; then
    fichiers+=(-f "$CODE_CLONE/deploiement/compose.config.yml")
  fi
  if grep -q '^FAUSSE_APP_CONTENU=' "$ETAT_STAGING/compose.env"; then
    fichiers+=(-f "$CODE_CLONE/deploiement/compose.contenu.yml")
  fi
  if [ "$mode" = comme-dc ] && grep -q '^FAUSSE_APP_RELAIS=' "$ETAT_STAGING/compose.env"; then
    fichiers+=(-f "$CODE_CLONE/deploiement/compose.marque.yml")
  fi
  CODE=0
  DOCKER_CONFIG="$TRAVAIL/docker" docker compose -p fausse-app-staging "${fichiers[@]}" \
    --env-file "$ETAT_STAGING/compose.env" "$@" >"$TRAVAIL/journal-$n" 2>&1 || CODE=$?
  echo "--- $n : docker compose ${fichiers[*]##*/} $* : code $CODE"
  sed 's/^/    /' "$TRAVAIL/journal-$n"
}
# sante_attendait <n> <révision attendue> <révision lue> : la dernière ligne « santé non conforme »
# de journal-<n> attend la première révision, et sa dernière réponse, du JSON lu par jq, porte la
# seconde : la cause de l'échec, et non une autre différence.
sante_attendait() {
  local ligne attendu reponse
  [ -n "$2" ] && [ -n "$3" ] || return 1
  ligne="$(grep -F -- 'santé non conforme après' "$TRAVAIL/journal-$1" | tail -n 1)"
  [[ "$ligne" == *' ; dernière réponse : '* ]] || return 1
  attendu="${ligne%% ; dernière réponse : *}"
  reponse="${ligne#* ; dernière réponse : }"
  [[ "$attendu" == *"révision $2,"* || "$attendu" == *"révision $2)"* ]] &&
    [ "$(jq -r '.revision' <<<"$reponse" 2>/dev/null)" = "$3" ]
}
# journal_avant <n> <texte> <texte> : le journal-<n> dit le premier texte avant le second.
journal_avant() {
  local premier second
  premier="$(grep -nF -- "$2" "$TRAVAIL/journal-$1" | head -n 1 | cut -d: -f1)"
  second="$(grep -nF -- "$3" "$TRAVAIL/journal-$1" | head -n 1 | cut -d: -f1)"
  [ -n "$premier" ] && [ -n "$second" ] && [ "$premier" -lt "$second" ]
}

echo "épreuve : moteur $(docker version --format '{{.Server.Version}}'), $(docker compose version --short 2>/dev/null || echo 'compose ?'), uid $(id -u)"

echo "== les outils"
mkdir -p "$OUTILS" "$HOME" "$TRAVAIL/cles" "$TRAVAIL/docker"
if ! command -v age >/dev/null 2>&1 || ! command -v age-keygen >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || {
    echo "épreuve : age est absent, et apt-get n'est pas là pour l'installer" >&2
    exit 1
  }
  echo "age, par apt"
  en_root apt-get update -qq
  en_root apt-get install -y -qq age >/dev/null
fi
curl -fsSL -o "$OUTILS/sops" \
  "https://github.com/getsops/sops/releases/download/v$SOPS_VERSION/sops-v$SOPS_VERSION.linux.amd64"
(cd "$OUTILS" && printf '%s  sops\n' "$SOPS_EMPREINTE" | sha256sum -c -) || {
  echo "épreuve : l'empreinte de sops $SOPS_VERSION n'est pas celle de sa publication ; il n'est pas lancé" >&2
  exit 1
}
chmod +x "$OUTILS/sops"
export PATH="$OUTILS:$PATH"
echo "$(age --version 2>&1 | head -n 1), $(sops --version 2>/dev/null | head -n 1)"

echo "== le registre, l'image et les réseaux du tunnel"
docker run -d -p 127.0.0.1:5001:5000 --name "$REGISTRE" "$REGISTRE_IMAGE" >/dev/null
REGISTRE_LANCE=1
docker tag "$IMAGE_CI" "$DEPOT:epreuve"
ETIQUETTE_POSEE=1
poussee=0
for _ in $(seq 1 30); do
  if docker push -q "$DEPOT:epreuve" >/dev/null 2>&1; then
    poussee=1
    break
  fi
  sleep 1
done
[ "$poussee" -eq 1 ] || {
  echo "épreuve : le registre ne répond pas sur localhost:5001" >&2
  exit 1
}
# Sous pipefail, un grep sans ligne fait échouer l'affectation : IMAGE reste alors vide, et le
# message ci-dessous dit pourquoi.
IMAGE="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$DEPOT:epreuve" \
  | grep "^$DEPOT@sha256:" | head -n 1)" || IMAGE=""
[[ "$IMAGE" =~ ^$DEPOT@sha256:[0-9a-f]{64}$ ]] || {
  echo "épreuve : pas d'empreinte pour $DEPOT:epreuve après le push" >&2
  exit 1
}
echo "image : $IMAGE (révision $REVISION)"
for reseau in tunnel-fausse-app-prod tunnel-fausse-app-staging; do
  if ! docker network inspect "$reseau" >/dev/null 2>&1; then
    docker network create "$reseau" >/dev/null
    RESEAUX_CREES+=("$reseau")
  fi
done

echo "== le code, les données de l'app et l'état"
mkdir -p "$CODE_CLONE"
cp -R "$RENDU/." "$CODE_CLONE/"
# Le journal de l'app tourne tous les 2 Ko, 5 fichiers gardés : quelques requêtes le font
# tourner, et la copie de deployer.sh doit lire les fichiers déjà tournés.
printf '%s\n' services: '  app:' "    user: \"$(id -u):$(id -g)\"" '    logging:' '      options:' \
  '        max-size: 2k' '        max-file: "5"' >"$CODE_CLONE/deploiement/compose.projet.yml"
# Les dossiers de données, vides, comme la sonde de serveur les crée : l'épreuve ne les sème pas.
mkdir -p "$DONNEES_PROD" "$DONNEES_STAGING"
mkdir -p "$ETAT_REEL"
ln -s "$ETAT_REEL" "$RACINE_ETAT"

echo "== le faux dépôt de données"
mkdir -p "$DEPOT_DONNEES/env" "$DEPOT_DONNEES/cles" "$DEPOT_DONNEES/secrets"
git init -q -b main "$DEPOT_DONNEES"
printf '%s\n' FAUSSE_APP_ENV=prod FAUSSE_APP_PROJET=fausse-app "FAUSSE_APP_PORT=$PORT_PROD" \
  FAUSSE_APP_URL_PUBLIQUE=https://fausse-app.exemple.org FAUSSE_APP_CANAL=etiquette \
  >"$DEPOT_DONNEES/env/prod.env"
printf '%s\n' FAUSSE_APP_ENV=staging FAUSSE_APP_PROJET=fausse-app-staging \
  "FAUSSE_APP_PORT=$PORT_STAGING" FAUSSE_APP_URL_PUBLIQUE=https://fausse-app-staging.exemple.org \
  FAUSSE_APP_CANAL=main FAUSSE_APP_BRANCHE_DONNEES=main >"$DEPOT_DONNEES/env/staging.env"
# L'identité age jetable : elle ne vit que dans le dossier de travail.
age-keygen -o "$IDENTITE" 2>/dev/null
age-keygen -y "$IDENTITE" >"$DEPOT_DONNEES/cles/serveur.pub"
printf 'creation_rules:\n  - path_regex: secrets/.*\\.env\\.enc$\n    age: %s\n' \
  "$(cat "$DEPOT_DONNEES/cles/serveur.pub")" >"$DEPOT_DONNEES/.sops.yaml"
for nom_env in prod staging; do
  printf 'EPREUVE_SECRET=valeur-factice-%s\n' "$nom_env" >"$TRAVAIL/clair.env"
  (
    cd "$DEPOT_DONNEES"
    # shellcheck disable=SC2094  # le chemin n'est qu'un nom pour la règle sops, pas un fichier lu
    sops encrypt --filename-override "secrets/$nom_env.env.enc" --input-type dotenv \
      --output-type dotenv "$TRAVAIL/clair.env" >"secrets/$nom_env.env.enc"
  )
  rm -f "$TRAVAIL/clair.env"
done
donnees_du_commit 1 1
C1="$COMMIT"
git_donnees tag "donnees-$(date -u +%Y.%m.%d).1" "$C1"
donnees_du_commit 2 1
C2="$COMMIT"
echo "commit 1 : $C1 ($(git_donnees tag --points-at "$C1")), commit 2 : $C2"

POINT=1
echo "== 1. le premier couple en prod"
verifier "le dossier de données de prod est vide avant le premier déploiement" vide "$DONNEES_PROD"
deployer 1 prod "$IMAGE" "$VERSION" --commit-donnees "$C1"
exiger "code 0 (la racine de l'état passe par un lien, deployer.sh ne le refuse pas)" code_vaut 0
verifier "MARQUE semée par l'app dans le dossier de données de prod" \
  fichier_vaut "$DONNEES_PROD/MARQUE" fausse-app
verifier "VERIFIER_CONTENU a tourné, code 0" journal_dit 1 \
  "contenu conforme (VERIFIER_CONTENU : code 0) : conforme"
verifier "sans contenu en service à comparer (rien n'est en service)" journal_tait 1 \
  "contenu en service comparé"
verifier "deploye porte le couple 1" fichier_vaut "$ETAT_PROD/deploye" "$IMAGE $VERSION $C1"
APP1="$(conteneur_app fausse-app)"
exiger "un conteneur app en prod" un_seul "$APP1"
verifier "il tourne" en_marche "$APP1"
constater_montage "$APP1" /config prod "$C1" config
constater_montage "$APP1" /contenu prod "$C1" contenu
verifier "santé : ok, configuration montee, version $VERSION, révision de l'image" sante_dit "$PORT_PROD" \
  ".statut == \"ok\" and .environnement == \"prod\" and .configuration == \"montee\" and .version == \"$VERSION\" and .revision == \$revision"
echo "== 1 bis. le journal de la prod tourne"
# Chaque requête écrit une ligne au journal de l'app : 30 requêtes dépassent ses 2 Ko.
for _ in $(seq 1 30); do
  curl -fsS -m 5 -o /dev/null "http://127.0.0.1:$PORT_PROD/api/sante"
done
STATUT_HTTP="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' \
  "http://127.0.0.1:$PORT_PROD/derniere-requete")" || STATUT_HTTP=""
verifier "/derniere-requete rend 404, et s'écrit au journal de l'app" egaux "$STATUT_HTTP" 404
# Les fichiers du journal de Docker ne se lisent qu'en root.
JOURNAL_APP1="$(docker container inspect --format '{{.LogPath}}' "$APP1")"
verifier "le journal de l'app a tourné : ${JOURNAL_APP1##*/}.1 existe" \
  en_root test -e "$JOURNAL_APP1.1"
fin_du_point 1

POINT=2
echo "== 2. seul le commit change"
IMAGE_APP1="$(image_de "$APP1")"
deployer 2 prod "$IMAGE" "$VERSION" --commit-donnees "$C2"
exiger "code 0" code_vaut 0
verifier "VERIFIER_CONTENU a tourné, code 0, avec /en-service, le contenu du couple 1" journal_dit 2 \
  "contenu conforme (VERIFIER_CONTENU : code 0) : conforme, contenu en service comparé : 1 page, aucune disparue"
verifier "deploye porte le couple 2" fichier_vaut "$ETAT_PROD/deploye" "$IMAGE $VERSION $C2"
verifier "precedent porte le couple 1" fichier_vaut "$ETAT_PROD/precedent" "$IMAGE $VERSION $C1"
APP2="$(conteneur_app fausse-app)"
exiger "un conteneur app en prod" un_seul "$APP2"
verifier "le conteneur est recréé" differents "$APP2" "$APP1"
verifier "même image ($IMAGE)" egaux "$(image_de "$APP2")" "$IMAGE_APP1"
verifier "l'image du conteneur est la référence du couple" egaux "$(image_de "$APP2" | cut -d' ' -f2)" "$IMAGE"
constater_montage "$APP2" /config prod "$C2" config
constater_montage "$APP2" /contenu prod "$C2" contenu
verifier "santé : ok, configuration montee" sante_dit "$PORT_PROD" \
  '.statut == "ok" and .configuration == "montee"'
# La copie du journal du conteneur remplacé, faite avant le `up`, sous la racine de l'état en lien.
COPIE1="$(copie_du_conteneur "$APP1")"
echo "       copie : ${COPIE1:-aucune} ($ETAT_PROD/journaux)"
verifier "une copie du journal en prod" egaux "$(nombre_de_copies)" 1
verifier "son nom : <horodatage>-$VERSION-${APP1:0:12}.log" nom_de_copie "$COPIE1" "$APP1"
verifier "journaux/ en 700" egaux "$(droits_de "$ETAT_PROD/journaux")" 700
verifier "la copie en 600" egaux "$(droits_de "$ETAT_PROD/journaux/$COPIE1")" 600
verifier "elle porte la ligne de démarrage de l'app, écrite dans un fichier déjà tourné" \
  copie_dit "$COPIE1" "fausse app : http://"
verifier "… avec sa configuration montee" copie_dit "$COPIE1" "configuration montee"
verifier "elle porte la dernière requête" copie_dit "$COPIE1" "/derniere-requete"
verifier "le journal de deployer.sh dit la copie" journal_dit 2 \
  "journal du conteneur ${APP1:0:12} ($VERSION) copié : journaux/$COPIE1"
fin_du_point 2

POINT=3
echo "== 3. une configuration que verifier-config refuse"
donnees_du_commit 3 99
C3="$COMMIT"
DEMARRE2="$(demarre_le "$APP2")"
deployer 3 prod "$IMAGE" "$VERSION" --commit-donnees "$C3"
exiger "code 1" code_vaut 1
verifier "le journal dit la configuration non conforme" journal_dit 3 'configuration non conforme (VERIFIER_CONFIG : code 2)'
verifier "la cause : la version de schéma 99, inconnue de l'image" journal_dit 3 \
  "configuration non conforme (VERIFIER_CONFIG : code 2) : non conforme : version de schéma inconnue : '99'"
verifier "echec porte le couple 3" fichier_vaut "$ETAT_PROD/echec" "$IMAGE $C3"
verifier "deploye porte encore le couple 2" fichier_vaut "$ETAT_PROD/deploye" "$IMAGE $VERSION $C2"
verifier "le conteneur en service est le même" egaux "$(conteneur_app fausse-app)" "$APP2"
verifier "il n'a pas redémarré" egaux "$(demarre_le "$APP2")" "$DEMARRE2"
verifier "il tourne" en_marche "$APP2"
constater_montage "$APP2" /config prod "$C2" config
constater_montage "$APP2" /contenu prod "$C2" contenu
verifier "santé : ok, configuration montee" sante_dit "$PORT_PROD" \
  '.statut == "ok" and .configuration == "montee"'
verifier "toujours une seule copie du journal : un refus ne copie rien" \
  egaux "$(nombre_de_copies)" 1
fin_du_point 3

POINT=4
echo "== 4. le retour arrière remet le couple 1"
# Pour le point 5 : deux instantanés laissés par d'anciens déploiements, hors de l'état.
ANCIEN1="$(printf 'ancien commit 1' | git hash-object --stdin)"
ANCIEN2="$(printf 'ancien commit 2' | git hash-object --stdin)"
planter_instantane "$ANCIEN1" '3 days ago'
planter_instantane "$ANCIEN2" '2 days ago'
# Le conteneur du couple 2 arrêté : `docker compose ps` ne le liste plus, `ps --all` encore.
docker stop "$APP2" >/dev/null
exiger "le conteneur du couple 2 est arrêté" arrete "$APP2"
deployer 4 prod --retour
exiger "code 0" code_vaut 0
verifier "deploye porte le couple 1" fichier_vaut "$ETAT_PROD/deploye" "$IMAGE $VERSION $C1"
verifier "precedent est consommé" absent "$ETAT_PROD/precedent"
verifier "echec porte le couple quitté, le 2" fichier_vaut "$ETAT_PROD/echec" "$IMAGE $C2"
APP4="$(conteneur_app fausse-app)"
exiger "un conteneur app en prod" un_seul "$APP4"
verifier "le conteneur est recréé" differents "$APP4" "$APP2"
constater_montage "$APP4" /config prod "$C1" config
constater_montage "$APP4" /contenu prod "$C1" contenu
verifier "santé : ok, configuration montee, version $VERSION" sante_dit "$PORT_PROD" \
  ".statut == \"ok\" and .configuration == \"montee\" and .version == \"$VERSION\""
COPIE2="$(copie_du_conteneur "$APP2")"
echo "       copie : ${COPIE2:-aucune} ($ETAT_PROD/journaux)"
verifier "deux copies du journal en prod" egaux "$(nombre_de_copies)" 2
verifier "la seconde, du conteneur arrêté : <horodatage>-$VERSION-${APP2:0:12}.log" \
  nom_de_copie "$COPIE2" "$APP2"
verifier "elle porte la ligne de démarrage de son app" copie_dit "$COPIE2" "fausse app : http://"
fin_du_point 4

POINT=5
echo "== 5. le ménage qui a suivi le retour"
verifier "le journal dit l'instantané le plus ancien retiré" journal_dit 4 "instantané retiré : $ANCIEN1"
verifier "le journal dit « 1 retiré »" journal_dit 4 'ménage des instantanés : 1 retiré'
verifier "l'instantané le plus ancien est parti" absent "$ETAT_PROD/instantanes/$ANCIEN1"
verifier "l'autre ancien reste, en marge" dossier_present "$ETAT_PROD/instantanes/$ANCIEN2"
for commit in "$C1" "$C2" "$C3"; do
  verifier "l'instantané de $commit reste" dossier_present "$ETAT_PROD/instantanes/$commit"
done
fin_du_point 5

POINT=6.1
echo "== 6. le staging, sans /config, puis le relais qui le marque"
echo "== 6.1 sans marque : le premier déploiement, puis le compose.env de la v0.13.0"
TETE="$(git_donnees rev-parse main)"
verifier "la tête de la branche des données est le commit 3" egaux "$TETE" "$C3"
verifier "le dossier de données de staging est vide avant le premier déploiement" vide "$DONNEES_STAGING"
deployer 6 staging "$IMAGE" main --commit-donnees "$TETE"
exiger "code 0" code_vaut 0
verifier "MARQUE semée par l'app dans le dossier de données de staging" \
  fichier_vaut "$DONNEES_STAGING/MARQUE" fausse-app
verifier "deploye du staging porte le couple" fichier_vaut "$ETAT_STAGING/deploye" "$IMAGE main $TETE"
verifier "le journal dit que VERIFIER_CONFIG n'est pas lancée" journal_dit 6 "staging : VERIFIER_CONFIG n'est pas lancée"
APP6="$(conteneur_app fausse-app-staging)"
exiger "un conteneur app en staging" un_seul "$APP6"
lire_montages "$APP6"
verifier "/config n'est pas monté" non_monte /config
constater_montage "$APP6" /contenu staging "$TETE" contenu
verifier "l'instantané du staging n'a pas de config/" absent "$ETAT_STAGING/instantanes/$TETE/config"
# shellcheck disable=SC2016  # $revision est une variable de jq (--arg, dans sante_dit)
verifier "santé : ok, configuration exemple, version main" sante_dit "$PORT_STAGING" \
  '.statut == "ok" and .environnement == "staging" and .configuration == "exemple" and .version == "main" and .revision == $revision'
verifier "la prod n'a pas bougé" egaux "$(conteneur_app fausse-app)" "$APP4"
verifier "la racine de l'état est restée un lien" lien_en_place
# deployer.sh marque le staging : compose.env porte l'empreinte du script de la copie, et `dc`
# ajoute alors compose.marque.yml.
EMPREINTE1="$(empreinte_du_relais)"
echo "       empreinte du script du relais : $EMPREINTE1"
verifier "compose.env du staging porte FAUSSE_APP_RELAIS, l'empreinte du script de la copie" \
  relais_vaut "$ETAT_STAGING" "$EMPREINTE1"
constater_tenants staging relais
fin_du_point 6.1
# Le compose.env que la v0.13.0 aurait écrit : le même, sans la ligne du relais ; puis le `up` de
# `dc` sur ses fichiers d'alors, sans compose.marque.yml. Le relais, qu'aucun fichier ne déclare
# plus, est un orphelin : --remove-orphans le retire.
SANS_RELAIS="$(grep -v '^FAUSSE_APP_RELAIS=' "$ETAT_STAGING/compose.env")" || SANS_RELAIS=""
exiger "compose.env garde ses autres lignes sans celle du relais" differents "$SANS_RELAIS" ""
printf '%s\n' "$SANS_RELAIS" >"$ETAT_STAGING/compose.env"
compose_staging sans-marque 6.1 up -d --wait --wait-timeout 120 --remove-orphans
exiger "code 0" code_vaut 0
verifier "compose.env ne porte plus FAUSSE_APP_RELAIS" relais_vaut "$ETAT_STAGING" ""
constater_tenants staging app
verifier "santé : ok, servie par app" sante_dit "$PORT_STAGING" \
  '.statut == "ok" and .environnement == "staging" and .version == "main"'
fin_du_point 6.1

POINT=6.2
echo "== 6.2 un échec forcé, depuis le staging sans marque"
# L'image dérivée : fausse-app:ci, dont l'étiquette de révision diffère de la révision que sa
# santé annonce (FAUSSE_APP_REVISION, posée à la construction de fausse-app:ci) ; poussée au
# registre local, prise par son empreinte, comme toute image que deployer.sh reçoit.
AUTRE_REVISION="$(printf "révision de l'image dérivée" | git hash-object --stdin)"
DERIVEE_POSEE=1
printf 'FROM %s\nLABEL org.opencontainers.image.revision=%s\n' "$IMAGE_CI" "$AUTRE_REVISION" \
  | docker build -q -t "$DEPOT:derivee" - >/dev/null || {
  echo "épreuve : l'image dérivée de $IMAGE_CI ne se construit pas" >&2
  exit 1
}
docker push -q "$DEPOT:derivee" >/dev/null || {
  echo "épreuve : l'image dérivée ne se pousse pas au registre local" >&2
  exit 1
}
IMAGE_DERIVEE="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' \
  "$DEPOT:derivee" | grep "^$DEPOT@sha256:" | head -n 1)" || IMAGE_DERIVEE=""
[[ "$IMAGE_DERIVEE" =~ ^$DEPOT@sha256:[0-9a-f]{64}$ ]] || {
  echo "épreuve : pas d'empreinte pour $DEPOT:derivee après le push" >&2
  exit 1
}
echo "image dérivée : $IMAGE_DERIVEE (révision de son étiquette : $AUTRE_REVISION)"
exiger "l'image dérivée n'est pas celle du couple" differents "$IMAGE_DERIVEE" "$IMAGE"
deployer 6.2 staging "$IMAGE_DERIVEE" main --commit-donnees "$TETE"
exiger "code 1" code_vaut 1
verifier "le journal dit l'échec par la santé" journal_dit 6.2 \
  "échec du déploiement de main (santé non conforme)"
verifier "… sa cause : la révision attendue, de l'image dérivée ; celle lue, de l'image du couple" \
  sante_attendait 6.2 "$AUTRE_REVISION" "$REVISION"
verifier "… et non par le up de l'aller" journal_tait 6.2 "docker compose up en échec"
verifier "aucun conflit de port" journal_tait 6.2 "port is already allocated"
verifier "aucune adresse déjà prise" journal_tait 6.2 "address already in use"
verifier "le up de l'aller a démarré le relais" journal_dit 6.2 \
  "Container fausse-app-staging-marque-1  Started"
verifier "le up du retour l'a retiré ensuite (--remove-orphans)" journal_avant 6.2 \
  "Container fausse-app-staging-marque-1  Started" "Container fausse-app-staging-marque-1  Removed"
verifier "le retour a réussi" journal_dit 6.2 "retour à main réussi"
verifier "echec porte le couple de l'image dérivée" \
  fichier_vaut "$ETAT_STAGING/echec" "$IMAGE_DERIVEE $TETE"
verifier "deploye porte encore le couple d'avant" \
  fichier_vaut "$ETAT_STAGING/deploye" "$IMAGE main $TETE"
verifier "compose.env, recopié du précédent, ne porte pas FAUSSE_APP_RELAIS" \
  relais_vaut "$ETAT_STAGING" ""
constater_tenants staging app
APP62="$(conteneur_app fausse-app-staging)"
exiger "un conteneur app en staging" un_seul "$APP62"
verifier "app tourne sur l'image du couple, non sur la dérivée" \
  egaux "$(image_de "$APP62" | cut -d' ' -f2)" "$IMAGE"
# shellcheck disable=SC2016  # $revision est une variable de jq (--arg, dans sante_dit)
verifier "santé : ok, révision de l'image du couple" sante_dit "$PORT_STAGING" \
  '.statut == "ok" and .revision == $revision'
fin_du_point 6.2

POINT=6.3
echo "== 6.3 un déploiement réussi, marqué, d'un couple neuf"
donnees_du_commit 4 1
C4="$COMMIT"
deployer 6.3 staging "$IMAGE" main --commit-donnees "$C4"
exiger "code 0" code_vaut 0
verifier "deploye du staging porte le couple neuf" fichier_vaut "$ETAT_STAGING/deploye" "$IMAGE main $C4"
verifier "compose.env porte FAUSSE_APP_RELAIS, l'empreinte du script de la copie" \
  relais_vaut "$ETAT_STAGING" "$EMPREINTE1"
verifier "la santé, lue par le relais, a été conforme au déploiement" journal_dit 6.3 "santé conforme"
constater_tenants staging relais
MARQUE63="$(conteneur_marque fausse-app-staging)"
exiger "un conteneur marque en staging" un_seul "$MARQUE63"
verifier "son étiquette modele.marque.empreinte vaut l'empreinte du script" \
  egaux "$(etiquette_du_relais "$MARQUE63")" "$EMPREINTE1"
# Les trois marques, lues par le port de la boucle locale, que tient le relais.
verifier "la page se lit par le port $PORT_STAGING" lire "$PORT_STAGING" / "$TRAVAIL/page-staging"
montrer "$TRAVAIL/page-staging"
verifier "elle porte le lien de la feuille du relais" contient "$TRAVAIL/page-staging" \
  '<link rel="stylesheet" href="/.marque/marque.css">'
verifier "son titre est préfixé : test &middot; fausse app" contient "$TRAVAIL/page-staging" \
  '<title>test &middot; fausse app</title>'
verifier "son lien d'icône vise l'icône recolorée" contient "$TRAVAIL/page-staging" \
  '<link rel="icon" href="/.marque/icone?de=/icone.png">'
verifier "la feuille se lit par le port" lire "$PORT_STAGING" /.marque/marque.css "$TRAVAIL/feuille"
verifier "… en text/css" egaux "$TYPE_LU" "text/css; charset=utf-8"
verifier "… elle pose le bandeau « TEST » (le relais tourne sur le script monté)" \
  contient "$TRAVAIL/feuille" 'html::before { content: "TEST";'
verifier "le manifeste se lit par le port" \
  lire "$PORT_STAGING" /manifest.webmanifest "$TRAVAIL/manifeste-staging"
montrer "$TRAVAIL/manifeste-staging"
verifier "… en application/manifest+json" egaux "$TYPE_LU" application/manifest+json
verifier "ses noms sont préfixés : « test · fausse app », « test fausse »" \
  json_dit "$TRAVAIL/manifeste-staging" '.name == "test · fausse app" and .short_name == "test fausse"'
verifier "ses icônes visent /.marque/icone?de=" \
  json_dit "$TRAVAIL/manifeste-staging" '[.icons[].src] == ["/.marque/icone?de=/icone.png"]'
verifier "l'icône recolorée se lit par le port" \
  lire "$PORT_STAGING" "/.marque/icone?de=/icone.png" "$TRAVAIL/icone-staging.png"
verifier "… en image/png" egaux "$TYPE_LU" image/png
verifier "… un PNG valide de 16 x 16, dont aucun pixel ne vaut #0b7f8f" \
  png_conforme "$TRAVAIL/icone-staging.png" 16 16 aucune
# shellcheck disable=SC2016  # $revision est une variable de jq (--arg, dans sante_dit)
verifier "santé, lue par le relais : version main, révision de l'image, configuration exemple" \
  sante_dit "$PORT_STAGING" \
  '.statut == "ok" and .environnement == "staging" and .configuration == "exemple" and .version == "main" and .revision == $revision'
fin_du_point 6.3
echo "== 6.3 bis. le script du relais change"
# Le déploiement d'un couple neuf écrit la nouvelle empreinte dans compose.env, et l'étiquette du
# relais la porte. Il recrée app, et Compose recrée alors le relais, qui en dépend, que l'étiquette
# ait changé ou non : cette étape ne prouve pas l'étiquette, que 6.3 ter éprouve seule.
printf '# épreuve : le script du relais change\n' >>"$CODE_CLONE/scripts/modele/marque.py"
EMPREINTE2="$(empreinte_du_relais)"
echo "       empreinte du script du relais : $EMPREINTE2"
exiger "l'empreinte du script a changé" differents "$EMPREINTE2" "$EMPREINTE1"
donnees_du_commit 5 1
C5="$COMMIT"
deployer 6.3bis staging "$IMAGE" main --commit-donnees "$C5"
exiger "code 0" code_vaut 0
verifier "deploye du staging porte le couple neuf" fichier_vaut "$ETAT_STAGING/deploye" "$IMAGE main $C5"
verifier "compose.env porte la nouvelle empreinte" relais_vaut "$ETAT_STAGING" "$EMPREINTE2"
MARQUE63B="$(conteneur_marque fausse-app-staging)"
exiger "un conteneur marque en staging" un_seul "$MARQUE63B"
verifier "son étiquette modele.marque.empreinte vaut la nouvelle empreinte" \
  egaux "$(etiquette_du_relais "$MARQUE63B")" "$EMPREINTE2"
verifier "le relais est recréé : son identifiant a changé" differents "$MARQUE63B" "$MARQUE63"
constater_tenants staging relais
verifier "la page se lit par le port $PORT_STAGING" lire "$PORT_STAGING" / "$TRAVAIL/page-staging"
verifier "son titre est toujours préfixé" contient "$TRAVAIL/page-staging" \
  '<title>test &middot; fausse app</title>'
fin_du_point 6.3

POINT="6.3 ter"
echo "== 6.3 ter. l'étiquette seule recrée le relais"
# 6.3 bis recrée app, donc le relais : il ne prouve pas l'étiquette. Ici, app n'est jamais recréé.
# D'abord le témoin : le `up` de `dc`, sur ses fichiers d'après compose.env, compose.marque.yml
# compris, sans aucun changement, laisse app et le relais en place ; une recréation viendrait alors
# d'ailleurs que l'étiquette. Puis le script change de nouveau, seule la ligne FAUSSE_APP_RELAIS de
# compose.env suit, et le même `up` recrée le relais, sous la nouvelle empreinte, sans recréer app :
# sans l'étiquette, rien ne changerait dans la configuration du relais, qui garderait l'ancien
# script, lu à son démarrage. Enfin le script et compose.env de 6.3 bis reviennent, et un dernier
# `up` remet le relais sous leur empreinte, celle que 6.4 attend, toujours sans recréer app.
APP_TEMOIN="$(conteneur_app fausse-app-staging)"
MARQUE_TEMOIN="$(conteneur_marque fausse-app-staging)"
exiger "un conteneur app en staging, en marche" un_seul_en_marche "$APP_TEMOIN"
exiger "un conteneur marque en staging, en marche" un_seul_en_marche "$MARQUE_TEMOIN"
compose_staging comme-dc 6.3ter-temoin up -d --wait --wait-timeout 120 --remove-orphans
exiger "témoin : code 0" code_vaut 0
verifier "témoin : app reste en marche, sans être recréé" journal_dit 6.3ter-temoin \
  "Container fausse-app-staging-app-1  Running"
verifier "témoin : le relais aussi : le up a pris compose.marque.yml" journal_dit 6.3ter-temoin \
  "Container fausse-app-staging-marque-1  Running"
verifier "témoin : le journal ne recrée rien" journal_tait 6.3ter-temoin "Recreate"
verifier "témoin : app garde son identifiant" \
  egaux "$(conteneur_app fausse-app-staging)" "$APP_TEMOIN"
verifier "témoin : le relais garde son identifiant" \
  egaux "$(conteneur_marque fausse-app-staging)" "$MARQUE_TEMOIN"
fin_du_point "$POINT"
cp "$ETAT_STAGING/compose.env" "$TRAVAIL/compose.env-6.3bis"
cp "$CODE_CLONE/scripts/modele/marque.py" "$TRAVAIL/marque.py-6.3bis"
printf '# épreuve : le script du relais change de nouveau\n' >>"$CODE_CLONE/scripts/modele/marque.py"
EMPREINTE3="$(empreinte_du_relais)"
echo "       empreinte du script du relais : $EMPREINTE3"
exiger "l'empreinte du script a changé de nouveau" differents "$EMPREINTE3" "$EMPREINTE2"
AVEC_EMPREINTE3="$(sed "s/^FAUSSE_APP_RELAIS=.*/FAUSSE_APP_RELAIS=$EMPREINTE3/" "$TRAVAIL/compose.env-6.3bis")"
printf '%s\n' "$AVEC_EMPREINTE3" >"$ETAT_STAGING/compose.env"
exiger "compose.env porte la nouvelle empreinte" relais_vaut "$ETAT_STAGING" "$EMPREINTE3"
verifier "… et ses autres lignes n'ont pas changé" egaux \
  "$(grep -v '^FAUSSE_APP_RELAIS=' "$ETAT_STAGING/compose.env")" \
  "$(grep -v '^FAUSSE_APP_RELAIS=' "$TRAVAIL/compose.env-6.3bis")"
compose_staging comme-dc 6.3ter up -d --wait --wait-timeout 120 --remove-orphans
exiger "code 0" code_vaut 0
verifier "le journal recrée le relais" journal_dit 6.3ter \
  "Container fausse-app-staging-marque-1  Recreated"
verifier "… et ne recrée pas app" journal_tait 6.3ter "Container fausse-app-staging-app-1  Recreate"
verifier "app garde l'identifiant du témoin" egaux "$(conteneur_app fausse-app-staging)" "$APP_TEMOIN"
MARQUE63T="$(conteneur_marque fausse-app-staging)"
exiger "un conteneur marque en staging, en marche" un_seul_en_marche "$MARQUE63T"
verifier "le relais est recréé : son identifiant est neuf" differents "$MARQUE63T" "$MARQUE_TEMOIN"
verifier "son étiquette modele.marque.empreinte vaut la nouvelle empreinte" \
  egaux "$(etiquette_du_relais "$MARQUE63T")" "$EMPREINTE3"
constater_tenants staging relais
fin_du_point "$POINT"
echo "       remise en état : le script du relais et compose.env de 6.3 bis"
cp "$TRAVAIL/marque.py-6.3bis" "$CODE_CLONE/scripts/modele/marque.py"
cp "$TRAVAIL/compose.env-6.3bis" "$ETAT_STAGING/compose.env"
exiger "le script a de nouveau l'empreinte de 6.3 bis" egaux "$(empreinte_du_relais)" "$EMPREINTE2"
exiger "compose.env porte de nouveau l'empreinte de 6.3 bis" relais_vaut "$ETAT_STAGING" "$EMPREINTE2"
compose_staging comme-dc 6.3ter-retour up -d --wait --wait-timeout 120 --remove-orphans
exiger "code 0" code_vaut 0
verifier "app garde toujours l'identifiant du témoin" \
  egaux "$(conteneur_app fausse-app-staging)" "$APP_TEMOIN"
MARQUE63R="$(conteneur_marque fausse-app-staging)"
exiger "un conteneur marque en staging, en marche" un_seul_en_marche "$MARQUE63R"
verifier "le relais est recréé de nouveau" differents "$MARQUE63R" "$MARQUE63T"
verifier "son étiquette vaut de nouveau l'empreinte de 6.3 bis" \
  egaux "$(etiquette_du_relais "$MARQUE63R")" "$EMPREINTE2"
constater_tenants staging relais
fin_du_point "$POINT"

POINT=6.4
echo "== 6.4 un second échec forcé, depuis le staging marqué"
deployer 6.4 staging "$IMAGE_DERIVEE" main --commit-donnees "$C5"
exiger "code 1" code_vaut 1
verifier "le journal dit l'échec par la santé" journal_dit 6.4 \
  "échec du déploiement de main (santé non conforme)"
verifier "… sa cause : la révision attendue, de l'image dérivée ; celle lue, de l'image du couple" \
  sante_attendait 6.4 "$AUTRE_REVISION" "$REVISION"
verifier "… et non par le up de l'aller" journal_tait 6.4 "docker compose up en échec"
verifier "le retour a réussi" journal_dit 6.4 "retour à main réussi"
verifier "echec porte le couple de l'image dérivée" \
  fichier_vaut "$ETAT_STAGING/echec" "$IMAGE_DERIVEE $C5"
verifier "deploye porte encore le couple d'avant" fichier_vaut "$ETAT_STAGING/deploye" "$IMAGE main $C5"
verifier "compose.env, recopié du précédent, porte l'empreinte du script" \
  relais_vaut "$ETAT_STAGING" "$EMPREINTE2"
constater_tenants staging relais
MARQUE64="$(conteneur_marque fausse-app-staging)"
exiger "un conteneur marque en staging" un_seul "$MARQUE64"
verifier "son étiquette modele.marque.empreinte vaut l'empreinte du script" \
  egaux "$(etiquette_du_relais "$MARQUE64")" "$EMPREINTE2"
APP64="$(conteneur_app fausse-app-staging)"
exiger "un conteneur app en staging" un_seul "$APP64"
verifier "app tourne sur l'image du couple, non sur la dérivée" \
  egaux "$(image_de "$APP64" | cut -d' ' -f2)" "$IMAGE"
# shellcheck disable=SC2016  # $revision est une variable de jq (--arg, dans sante_dit)
verifier "santé, lue par le relais : ok, révision de l'image du couple" sante_dit "$PORT_STAGING" \
  '.statut == "ok" and .revision == $revision'
verifier "la page se lit par le port $PORT_STAGING" lire "$PORT_STAGING" / "$TRAVAIL/page-staging"
verifier "son titre est toujours préfixé : le retour garde la marque" \
  contient "$TRAVAIL/page-staging" '<title>test &middot; fausse app</title>'
fin_du_point 6.4

POINT=6.5
echo "== 6.5 « Tout arrêter » : le down du staging, avec --remove-orphans"
MARQUE65="$(conteneur_marque fausse-app-staging)"
APP65="$(conteneur_app fausse-app-staging)"
exiger "le relais tourne avant le down" un_seul_en_marche "$MARQUE65"
exiger "app tourne avant le down" un_seul_en_marche "$APP65"
# Le `down` de « Tout arrêter » (docs/exploitation.md), sur compose.yml et compose.projet.yml : sans
# compose.marque.yml, le relais est un orphelin, que seul --remove-orphans retire.
CODE=0
docker compose -p fausse-app-staging -f "$CODE_CLONE/deploiement/compose.yml" \
  -f "$CODE_CLONE/deploiement/compose.projet.yml" --env-file "$ETAT_STAGING/compose.env" \
  down --remove-orphans >"$TRAVAIL/journal-6.5" 2>&1 || CODE=$?
echo "--- 6.5 : docker compose -f compose.yml -f compose.projet.yml down --remove-orphans : code $CODE"
sed 's/^/    /' "$TRAVAIL/journal-6.5"
exiger "code 0" code_vaut 0
verifier "le relais est retiré" retire "$MARQUE65"
verifier "app est retirée" retire "$APP65"
verifier "aucun conteneur ne reste dans le projet fausse-app-staging" \
  egaux "$(docker ps -aq --filter label=com.docker.compose.project=fausse-app-staging)" ""
fin_du_point 6.5

POINT=7
echo "== 7. la prod, jamais marquée"
verifier "aucun conteneur marque dans le projet fausse-app" egaux "$(conteneur_marque fausse-app)" ""
verifier "compose.env de la prod ne porte pas FAUSSE_APP_RELAIS" relais_vaut "$ETAT_PROD" ""
constater_tenants prod app
verifier "la page de la prod se lit par le port $PORT_PROD" lire "$PORT_PROD" / "$TRAVAIL/page-prod"
montrer "$TRAVAIL/page-prod"
verifier "elle porte le titre de l'app, sans préfixe" contient "$TRAVAIL/page-prod" "$TITRE_APP"
verifier "son lien d'icône est celui de l'app" contient "$TRAVAIL/page-prod" "$LIEN_ICONE_APP"
verifier "elle ne porte rien du relais (/.marque/)" ne_contient_pas "$TRAVAIL/page-prod" /.marque/
verifier "le manifeste de la prod se lit par le port" \
  lire "$PORT_PROD" /manifest.webmanifest "$TRAVAIL/manifeste-prod"
montrer "$TRAVAIL/manifeste-prod"
verifier "ses noms et son icône sont ceux de l'app" json_dit "$TRAVAIL/manifeste-prod" \
  '.name == "fausse app" and .short_name == "fausse" and [.icons[].src] == ["/icone.png"]'
verifier "l'icône de la prod se lit par le port" lire "$PORT_PROD" /icone.png "$TRAVAIL/icone-prod.png"
verifier "… celle de l'app : un PNG de 16 x 16, tout #0b7f8f" \
  png_conforme "$TRAVAIL/icone-prod.png" 16 16 toutes
verifier "la prod n'a pas bougé" egaux "$(conteneur_app fausse-app)" "$APP4"
verifier "la racine de l'état est restée un lien" lien_en_place
fin_du_point 7

echo "épreuve : tout est comme attendu"
