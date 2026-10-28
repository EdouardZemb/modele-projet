#!/usr/bin/env bash
# L'épreuve du ménage des images, sur un vrai Docker (lot 9, #19).
#
#   bash tests/modele/epreuve-menage.sh <rendu>
#
# <rendu> est un projet de la cible serveur rendu par le modèle, avec le préfixe FAUSSE_APP_. Les
# tests bats lancent le ménage contre un double de docker ; ici, le vrai Docker confirme ce que le
# double ne peut pas : qu'il accepte les retraits que le script lui demande (sans -f, il refuse
# `docker image rm <identifiant>` pour une image à plusieurs étiquettes), et que les images
# gardées sont encore là.
#
# Déroulé : un registre local, onze images du dépôt localhost:5000/edouardzemb/fausse-app (m0 à
# m10, de la plus ancienne à la plus récente), des images hors du dépôt, un conteneur jamais lancé,
# un état de prod et de staging. Puis trois lancements de deploiement/nettoyer-images.sh staging :
#   1. verrou de la prod tenu : le ménage est sauté (code 0), rien ne part ;
#   2. verrou libre : m0 (une étiquette et son empreinte, retirée par son identifiant), m1 (deux
#      étiquettes, 0.0.1 et 0.0.2, retirée par ses étiquettes : construite sous trois, elle a perdu
#      :main au profit de m2) et m5 (une ancienne :main sans nom) partent ;
#   3. un second ménage ne retire rien.
#
# Le magasin d'images : le classique garde une image dont l'étiquette bouge, sans nom, avec son
# empreinte ; celui de containerd la supprime. Sous GITHUB_ACTIONS=true, l'épreuve exige le
# magasin classique, et s'arrête (code 1) sur un Docker en magasin containerd : la CI ne prouverait
# plus ce cas. Ailleurs, elle le dit par une ligne AVERTISSEMENT et rattrape ces images en les
# tirant par leur empreinte.
#
# Code de sortie : 0 si tout est comme attendu, 1 sinon, en disant quoi. À la fin, l'épreuve retire
# son registre, son conteneur et ses images, et rien d'autre (ni prune, ni -f hors d'elle).
set -euo pipefail

[ "$#" -eq 1 ] && [ -d "$1" ] || {
  echo "usage : bash tests/modele/epreuve-menage.sh <rendu>" >&2
  exit 64
}
RENDU="$(cd "$1" && pwd)"
SCRIPT="$RENDU/deploiement/nettoyer-images.sh"
[ -f "$SCRIPT" ] || {
  echo "épreuve : $SCRIPT absent" >&2
  exit 64
}

REGISTRE_IMAGE='registry:2.8.3@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373'
REGISTRE=epreuve-registre
CONTENEUR=epreuve-conteneur
DEPOT=localhost:5000/edouardzemb/fausse-app
TRAVAIL="$(mktemp -d)"
ECHECS=0
CODE=0
declare -A ID=()
declare -A EMPREINTE=()

nettoyer() {
  exec 7>&-
  docker rm -f -v "$CONTENEUR" >/dev/null 2>&1 || true
  docker rm -f -v "$REGISTRE" >/dev/null 2>&1 || true
  # Les images de l'épreuve : par leurs références d'abord (une image à plusieurs étiquettes ne se
  # retire que par elles), puis par leur identifiant.
  local ref
  for ref in "$DEPOT" localhost:5000/edouardzemb/fausse-app-autre localhost:5000/autre/projet; do
    docker image ls --format '{{.Repository}}:{{.Tag}}' "$ref" 2>/dev/null \
      | xargs -r docker image rm >/dev/null 2>&1 || true
  done
  for ref in "${ID[@]}"; do
    docker image rm "$ref" >/dev/null 2>&1 || true
  done
  rm -rf "$TRAVAIL"
}
trap nettoyer EXIT

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
present() { docker image inspect "${ID[$1]}" >/dev/null 2>&1; }
absente() { ! present "$1"; }
journal_dit() { grep -q -- "$2" "$TRAVAIL/journal-$1"; }
journal_tait() { ! grep -q -- "$2" "$TRAVAIL/journal-$1"; }
code_vaut() { [ "$CODE" -eq "$1" ]; }

# construire <nom> [référence…] : une image FROM scratch au contenu unique, sous ces références ;
# son identifiant dans ID[<nom>]. Une seconde d'écart entre deux constructions : leur ordre de
# création est alors sans ambiguïté.
construire() {
  local nom="$1" dossier="$TRAVAIL/ctx-$1" ref
  shift
  mkdir -p "$dossier"
  printf 'FROM scratch\nCOPY n.txt /\n' >"$dossier/Dockerfile"
  printf '%s\n' "$nom" >"$dossier/n.txt"
  local -a etiquettes=()
  for ref in "$@"; do etiquettes+=(-t "$ref"); done
  ID[$nom]="$(docker build -q "${etiquettes[@]}" "$dossier")"
  sleep 1
}
pousser() {
  local ref
  for ref in "$@"; do docker push -q "$ref" >/dev/null; done
}
# empreinte <nom> : <dépôt>@sha256:… de cette image.
empreinte() {
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "${ID[$1]}" \
    | grep "^$DEPOT@" | head -n 1
}
# lancer <n> : le ménage du staging ; son code dans CODE, son journal dans journal-<n>.
lancer() {
  CODE=0
  FAUSSE_APP_DEPOT_IMAGE="$DEPOT" \
    FAUSSE_APP_RACINE_ETAT="$TRAVAIL/etat" \
    FAUSSE_APP_RACINE_DONNEES="$TRAVAIL/donnees" \
    FAUSSE_APP_RACINE_SAUVEGARDES="$TRAVAIL/sauvegardes" \
    FAUSSE_APP_DOCKER_CONFIG="$TRAVAIL/docker" \
    bash "$SCRIPT" staging 2>"$TRAVAIL/journal-$1" || CODE=$?
  echo "--- lancement $1 : code $CODE"
  sed 's/^/    /' "$TRAVAIL/journal-$1"
}

echo "épreuve : moteur $(docker version --format '{{.Server.Version}}'), magasin $(docker info --format '{{.Driver}}')"
# Le magasin containerd se reconnaît à son pilote de clichés, dans DriverStatus.
MAGASIN="$(docker info --format '{{json .DriverStatus}}')"
if [[ "$MAGASIN" == *io.containerd.snapshotter* ]]; then
  if [ "${GITHUB_ACTIONS:-}" = true ]; then
    echo "épreuve : le Docker de la CI garde ses images dans le magasin containerd ($MAGASIN) ; la CI ne prouve plus le cas du magasin classique, celui que le ménage suppose. Arrêt." >&2
    exit 1
  fi
  echo "AVERTISSEMENT : magasin containerd ($MAGASIN) ; les anciennes :main, qu'il supprime, seront rattrapées par leur empreinte : le cas du magasin classique n'est pas éprouvé ici"
fi
echo "== le registre et les images"
mkdir -p "$TRAVAIL/docker"
docker rm -f -v "$REGISTRE" >/dev/null 2>&1 || true
docker run -d -p 5000:5000 --name "$REGISTRE" "$REGISTRE_IMAGE" >/dev/null

# m0 : seule sous son étiquette 0.0.0, avec son empreinte (retirée par son identifiant). Son envoi
# attend que le registre réponde.
construire m0 "$DEPOT:0.0.0"
poussee=0
for _ in $(seq 1 30); do
  if docker push -q "$DEPOT:0.0.0" >/dev/null 2>&1; then
    poussee=1
    break
  fi
  sleep 1
done
[ "$poussee" -eq 1 ] || {
  echo "épreuve : le registre ne répond pas sur localhost:5000" >&2
  exit 1
}
# m1 : construite sous trois étiquettes. m2 lui prend :main : au moment du ménage, il lui en reste
# deux, 0.0.1 et 0.0.2 (retirée par ses étiquettes, une par appel).
construire m1 "$DEPOT:main" "$DEPOT:0.0.1" "$DEPOT:0.0.2"
pousser "$DEPOT:main" "$DEPOT:0.0.1" "$DEPOT:0.0.2"
# m2 à m10 : chacune prend :main, la précédente reste sans nom, avec son empreinte. m3 reçoit aussi
# une référence hors du dépôt, m6 l'étiquette 0.1.0.
for n in 2 3 4 5 6 7 8 9 10; do
  construire "m$n" "$DEPOT:main"
  pousser "$DEPOT:main"
  case "$n" in
    3)
      docker tag "$DEPOT:main" localhost:5000/autre/projet:1
      pousser localhost:5000/autre/projet:1
      ;;
    6)
      docker tag "$DEPOT:main" "$DEPOT:0.1.0"
      pousser "$DEPOT:0.1.0"
      ;;
  esac
  EMPREINTE[m$n]="$(empreinte "m$n" || true)"
  [ -n "${EMPREINTE[m$n]}" ] || {
    echo "épreuve : pas d'empreinte pour m$n après le push" >&2
    exit 1
  }
done
# Hors du dépôt : une image d'un dépôt voisin, et une image sans aucune référence.
construire autre localhost:5000/edouardzemb/fausse-app-autre:1
pousser localhost:5000/edouardzemb/fausse-app-autre:1
construire sans-nom
# Le magasin classique garde une image dont l'étiquette bouge, sans nom, avec son empreinte ; celui
# de containerd la supprime. L'épreuve rétablit cet état en tirant l'image par son empreinte.
for n in 2 3 4 5 6 7 8 9 10; do
  if ! docker image inspect "${ID[m$n]}" >/dev/null 2>&1; then
    ID[m$n]="$(docker pull -q "${EMPREINTE[m$n]}" >/dev/null 2>&1       && docker image inspect --format '{{.Id}}' "${EMPREINTE[m$n]}" 2>/dev/null)" || {
      echo "épreuve : m$n manquante et non récupérable par son empreinte" >&2
      exit 1
    }
  fi
done
# Un conteneur jamais lancé sur m2 (une commande est requise pour une image sans CMD).
docker create --name "$CONTENEUR" "${ID[m2]}" /n.txt >/dev/null

echo "== l'état"
for n in m4 m6 m10; do
  [ -n "$(empreinte "$n")" ] || {
    echo "épreuve : l'image $n n'a pas d'empreinte dans $DEPOT" >&2
    exit 1
  }
done
mkdir -p "$TRAVAIL/etat/prod" "$TRAVAIL/etat/staging"
printf '%s 0.1.0\n' "$(empreinte m6)" >"$TRAVAIL/etat/prod/deploye"
printf '%s 0.0.9\n' "$(empreinte m4)" >"$TRAVAIL/etat/prod/precedent"
printf '%s main\n' "$(empreinte m10)" >"$TRAVAIL/etat/staging/deploye"

echo "== 1. le verrou de la prod est tenu : le ménage est sauté"
exec 7>"$TRAVAIL/etat/prod/verrou"
flock -n 7 || {
  echo "épreuve : le verrou de la prod ne se prend pas" >&2
  exit 1
}
lancer 1
verifier "code 0" code_vaut 0
verifier "le journal dit « sauté »" journal_dit 1 'sauté'
for n in m0 m1 m5; do verifier "$n est encore là" present "$n"; done
exec 7>&-

echo "== 2. le verrou est libre : le ménage a lieu"
lancer 2
verifier "code 0" code_vaut 0
verifier "le journal dit « 3 retirées »" journal_dit 2 'ménage des images : 3 retirées'
verifier "le journal ne dit pas « retrait impossible »" journal_tait 2 'retrait impossible'
verifier "le journal ne dit pas « annulé »" journal_tait 2 'annulé'
for n in m0 m1 m5; do verifier "$n est partie" absente "$n"; done
for n in m2 m3 m4 m6 m7 m8 m9 m10 autre sans-nom; do verifier "$n est encore là" present "$n"; done

echo "== 3. un second ménage ne retire rien"
lancer 3
verifier "code 0" code_vaut 0
verifier "le journal dit « 0 retirée »" journal_dit 3 'ménage des images : 0 retirée'
for n in m2 m3 m4 m6 m7 m8 m9 m10 autre sans-nom; do verifier "$n est encore là" present "$n"; done

if [ "$ECHECS" -ne 0 ]; then
  echo "épreuve : $ECHECS vérification(s) en échec" >&2
  exit 1
fi
echo "épreuve : tout est comme attendu"
