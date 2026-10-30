#!/usr/bin/env bash
# L'épreuve des données, sur un vrai Docker (lot 12, #64) : la chaîne à deux dépôts (M-0006, §§ 5
# et 6), de deployer.sh à la santé de l'app.
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
# la santé que sert l'app.
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
#   - une copie du code, d'où deployer.sh est lancé ; les données de l'app (/donnees), semées comme
#     le fait l'image ; HOME, un dossier de l'épreuve ;
#   - la racine de l'état passe par un lien symbolique, lien-etat -> etat-reel, pendant toute
#     l'épreuve (Ruling 32) : deployer.sh compare les montages sans résoudre les liens.
#
# Déroulé, chaque point constaté par docker inspect ou par la santé :
#   1. le premier couple, l'image et le commit 1, se déploie en prod : /config et /contenu montés en
#      lecture seule depuis instantanes/<commit 1>, sources sans « // », santé « montee » ;
#   2. seul le commit change (commit 2) : le conteneur est recréé sur instantanes/<commit 2>, même
#      image ;
#   3. un troisième commit porte une configuration que verifier-config refuse (une version de schéma
#      inconnue) : code 1, echec porte le couple, le conteneur en service n'a pas bougé ;
#   4. --retour remet le couple 1 ;
#   5. le ménage qui suit ce retour retire un instantané qui n'est plus gardé : deux instantanés
#      laissés par d'anciens déploiements, datés de trois et de deux jours, sont posés juste avant ;
#      avec ceux des commits 2 et 3, ils dépassent la marge (les 3 plus récents) : le plus ancien
#      part, le reste demeure ;
#   6. le staging se déploie sur la tête de la branche des données, le commit 3, dont il ne lit
#      jamais config/ : il tourne sans /config, /contenu monté, santé « exemple ».
#
# L'uid. Sur le serveur, le compte qui déploie a l'uid 1000, celui du conteneur. Le runner de GitHub
# a un autre uid : le compose.projet.yml de la copie du code aligne l'app sur le compte qui lance
# l'épreuve, pour que la commande SAUVEGARDER écrive l'instantané d'avant déploiement dans le
# dossier des sauvegardes, que deployer.sh restreint à 700. Les commandes de vérification gardent
# l'uid 1000 des conteneurs jetables : les instantanés leur sont lisibles.
#
# Code de sortie : 0 si tout est comme attendu, 1 sinon, en disant quoi ; 64 usage. À la fin,
# l'épreuve retire ses conteneurs, ses réseaux, son registre, l'étiquette qu'elle a posée sur
# l'image et son dossier de travail, et rien d'autre ; en cas d'échec, elle montre d'abord le
# journal de ses conteneurs.
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
VERSION=0.1.0

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
export HOME="$TRAVAIL/home"
ECHECS=0
CODE=0
POINT=0
REGISTRE_LANCE=0
ETIQUETTE_POSEE=0
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
  # L'étiquette et l'empreinte du registre local, et elles seules : fausse-app:ci reste.
  if [ "$ETIQUETTE_POSEE" -eq 1 ]; then
    docker image rm "$DEPOT:epreuve" >/dev/null 2>&1 || true
    [ -z "${IMAGE:-}" ] || docker image rm "$IMAGE" >/dev/null 2>&1 || true
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
egaux() { [ "$1" = "$2" ]; }
differents() { [ "$1" != "$2" ]; }
journal_dit() { grep -qF -- "$2" "$TRAVAIL/journal-$1"; }
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
demarre_le() { docker container inspect --format '{{.State.StartedAt}}' "$1"; }
image_de() { docker container inspect --format '{{.Image}} {{.Config.Image}}' "$1"; }

# lire_montages <conteneur> : ses montages, une ligne « <point> <RW> <source> » chacun, dans
# MONTAGES, d'après docker container inspect.
lire_montages() {
  MONTAGES="$(docker container inspect --format '{{json .Mounts}}' "$1" \
    | jq -r '.[] | "\(.Destination) \(.RW) \(.Source)"')" || MONTAGES=""
}
champ_du_montage() { awk -v p="$1" -v c="$2" '$1 == p { print $c }' <<<"$MONTAGES"; }
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
# lecture seule, depuis instantanes/<commit>/<dossier> de l'état de <env>, sans « // » (Ruling 32).
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
docker run -d -p 5001:5000 --name "$REGISTRE" "$REGISTRE_IMAGE" >/dev/null
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
IMAGE="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$DEPOT:epreuve" \
  | grep "^$DEPOT@sha256:" | head -n 1)"
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
printf 'services:\n  app:\n    user: "%s:%s"\n' "$(id -u)" "$(id -g)" \
  >"$CODE_CLONE/deploiement/compose.projet.yml"
for nom_env in prod staging; do
  mkdir -p "$TRAVAIL/donnees/$nom_env/donnees/notes"
  printf 'fausse-app\n' >"$TRAVAIL/donnees/$nom_env/donnees/MARQUE"
  printf 'une note\n' >"$TRAVAIL/donnees/$nom_env/donnees/notes/premiere.txt"
done
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
deployer 1 prod "$IMAGE" "$VERSION" --commit-donnees "$C1"
exiger "code 0 (la racine de l'état passe par un lien, deployer.sh ne le refuse pas)" code_vaut 0
verifier "deploye porte le couple 1" fichier_vaut "$ETAT_PROD/deploye" "$IMAGE $VERSION $C1"
APP1="$(conteneur_app fausse-app)"
exiger "un conteneur app en prod" un_seul "$APP1"
verifier "il tourne" en_marche "$APP1"
constater_montage "$APP1" /config prod "$C1" config
constater_montage "$APP1" /contenu prod "$C1" contenu
verifier "santé : ok, configuration montee, version $VERSION, révision de l'image" sante_dit "$PORT_PROD" \
  ".statut == \"ok\" and .environnement == \"prod\" and .configuration == \"montee\" and .version == \"$VERSION\" and .revision == \$revision"
fin_du_point 1

POINT=2
echo "== 2. seul le commit change"
IMAGE_APP1="$(image_de "$APP1")"
deployer 2 prod "$IMAGE" "$VERSION" --commit-donnees "$C2"
exiger "code 0" code_vaut 0
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
fin_du_point 2

POINT=3
echo "== 3. une configuration que verifier-config refuse"
donnees_du_commit 3 99
C3="$COMMIT"
DEMARRE2="$(demarre_le "$APP2")"
deployer 3 prod "$IMAGE" "$VERSION" --commit-donnees "$C3"
exiger "code 1" code_vaut 1
verifier "le journal dit la configuration non conforme" journal_dit 3 'configuration non conforme (VERIFIER_CONFIG : code 2)'
verifier "echec porte le couple 3" fichier_vaut "$ETAT_PROD/echec" "$IMAGE $C3"
verifier "deploye porte encore le couple 2" fichier_vaut "$ETAT_PROD/deploye" "$IMAGE $VERSION $C2"
verifier "le conteneur en service est le même" egaux "$(conteneur_app fausse-app)" "$APP2"
verifier "il n'a pas redémarré" egaux "$(demarre_le "$APP2")" "$DEMARRE2"
verifier "il tourne" en_marche "$APP2"
constater_montage "$APP2" /config prod "$C2" config
verifier "santé : ok, configuration montee" sante_dit "$PORT_PROD" \
  '.statut == "ok" and .configuration == "montee"'
fin_du_point 3

POINT=4
echo "== 4. le retour arrière remet le couple 1"
# Pour le point 5 : deux instantanés laissés par d'anciens déploiements, hors de l'état.
ANCIEN1="$(printf 'ancien commit 1' | git hash-object --stdin)"
ANCIEN2="$(printf 'ancien commit 2' | git hash-object --stdin)"
planter_instantane "$ANCIEN1" '3 days ago'
planter_instantane "$ANCIEN2" '2 days ago'
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

POINT=6
echo "== 6. le staging, sans /config"
TETE="$(git_donnees rev-parse main)"
verifier "la tête de la branche des données est le commit 3" egaux "$TETE" "$C3"
deployer 6 staging "$IMAGE" main --commit-donnees "$TETE"
exiger "code 0" code_vaut 0
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
fin_du_point 6

echo "épreuve : tout est comme attendu"
