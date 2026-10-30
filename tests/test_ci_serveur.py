"""La CI d'un projet `serveur` : ses jobs, ses deux actions composites, modele-version.yml, et la
fausse app qui en fait la preuve dans la CI du modèle (spec §10.3)."""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml
from conftest import RACINE, REPONSES_SERVEUR, git, trouver_bash

CI = ".github/workflows/ci.yml"
VERSION = ".github/workflows/modele-version.yml"
CONSTRUIRE = ".github/actions/modele-image-construire/action.yml"
PUBLIER = ".github/actions/modele-image-publier/action.yml"
VERIFIER_IMAGE = "deploiement/ci/verifier-image.sh"
CI_BATS = "tests/deploiement/ci.bats"
FAUSSE_APP = RACINE / "tests/modele/fausse-app"

CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SHA = "0123456789abcdef0123456789abcdef01234567"
AUTRE_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def lire(rendu, chemin):
    return (rendu / chemin).read_text(encoding="utf-8")


def charger(rendu, chemin):
    return yaml.safe_load(lire(rendu, chemin))


def declencheurs(doc):
    # PyYAML lit la clé `on` comme True.
    return doc.get("on", doc.get(True))


def etape(etapes, nom):
    (trouvee,) = [e for e in etapes if e.get("name", "").startswith(nom)]
    return trouvee


# --- Lancer une étape comme GitHub, avec un faux docker ----------------------------------------


# Faux docker : chaque appel est une ligne de $FAUX_JOURNAL, les arguments séparés par des
# tabulations. Le registre est un dossier, une étiquette par fichier (son manifeste brut).
FAUX_DOCKER = r"""#!/usr/bin/env bash
{ printf docker; for a in "$@"; do printf '\t%s' "$a"; done; printf '\n'; } >>"$FAUX_JOURNAL"
case "$1" in
  login) cat >"$FAUX_JOURNAL.stdin" ;;
  push) [ -z "${FAUX_PUSH_ECHEC:-}" ] || { echo "denied" >&2; exit 1; } ;;
  buildx)
    case "$3" in
      inspect)
        ref="${!#}"
        if [ -f "$FAUX_REGISTRE/${ref##*:}" ]; then
          [ "$4" != --raw ] || cat "$FAUX_REGISTRE/${ref##*:}"
          exit 0
        fi
        if [ -n "${FAUX_REGISTRE_PANNE:-}" ]; then
          echo "ERROR: $FAUX_REGISTRE_PANNE" >&2
          exit 1
        fi
        echo "ERROR: ${FAUX_REGISTRE_ABSENT:-$ref: not found}" >&2
        exit 1
        ;;
      create)
        [ "$4" = --prefer-index=false ] && [ "$5" = -t ] || exit 125
        cp "$FAUX_REGISTRE/${7##*:}" "$FAUX_REGISTRE/${6##*:}"
        ;;
    esac
    ;;
esac
exit 0
"""


class Banc:
    """Un faux docker en tête du PATH, son journal et son registre, et bash pour lancer une étape."""

    def __init__(self, tmp_path, env):
        self.bash = trouver_bash()
        self.dossier = tmp_path / "banc"
        binaires = self.dossier / "bin"
        binaires.mkdir(parents=True)
        (binaires / "docker").write_text(FAUX_DOCKER, encoding="utf-8", newline="\n")
        (binaires / "docker").chmod(0o755)
        self.registre = self.dossier / "registre"
        self.registre.mkdir()
        self.journal = self.dossier / "journal"
        self.journal.write_text("", encoding="utf-8")
        self.env = {
            **env,
            "PATH": str(binaires) + os.pathsep + env["PATH"],
            "FAUX_JOURNAL": self.posix(self.journal),
            "FAUX_REGISTRE": self.posix(self.registre),
            "GITHUB_ENV": self.posix(self.dossier / "github-env"),
        }

    @staticmethod
    def posix(chemin):
        return str(chemin).replace("\\", "/")

    def lancer(self, run, cwd, options=("-e",), **env):
        """L'étape comme GitHub la lance : `bash -e {0}`, ou les options données."""
        return subprocess.run(
            [self.bash, "--noprofile", "--norc", *options, "-c", run],
            check=False,
            cwd=cwd,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def appels(self):
        lignes = self.journal.read_text(encoding="utf-8").splitlines()
        return [ligne.split("\t")[1:] for ligne in lignes]

    def github_env(self):
        fichier = self.dossier / "github-env"
        if not fichier.exists():
            return {}
        return dict(
            ligne.split("=", 1) for ligne in fichier.read_text(encoding="utf-8").splitlines()
        )


# --- Les actions et les workflows rendus ------------------------------------------------------


def test_actions_composites_epinglees_et_brutes(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    fichiers = sorted((rendu / ".github/actions").glob("*/action.yml"))
    fichiers += sorted((rendu / ".github/workflows").glob("*.yml"))
    noms = {f.relative_to(rendu).as_posix() for f in fichiers}
    assert {CONSTRUIRE, PUBLIER, VERSION, CI} <= noms
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8")
        for uses in re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", texte, re.MULTILINE):
            if not uses.startswith("./"):
                assert re.search(r"@[0-9a-f]{40}$", uses), f"{chemin.name}: {uses}"
            if uses.startswith("actions/checkout@"):
                assert uses == CHECKOUT, f"{chemin.name}: {uses}"
        assert "{%" not in texte, chemin.name

    # Docker se pilote en ligne de commande : une action composite n'appelle aucune action.
    for chemin in (CONSTRUIRE, PUBLIER):
        doc = charger(rendu, chemin)
        assert doc["runs"]["using"] == "composite", chemin
        for e in doc["runs"]["steps"]:
            assert "uses" not in e, (chemin, e)
            assert e["shell"] == "bash", (chemin, e)

    # Les expressions de GitHub survivent au rendu de Jinja.
    attendues = {
        CONSTRUIRE: ["${{ inputs.dossier }}", "${{ inputs.variables }}"],
        PUBLIER: ["${{ github.token }}"],
        VERSION: ["${{ github.ref }}", "${{ secrets.GITHUB_TOKEN }}", "${{ github.token }}"],
        CI: ["${{ github.ref }}", "${{ github.event_name == 'pull_request' }}"],
    }
    for chemin, expressions in attendues.items():
        texte = lire(rendu, chemin)
        for expression in expressions:
            assert expression in texte, (chemin, expression)


def test_image_attend_socle_verifier_deploiement(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    doc = charger(rendu, CI)
    jobs = doc["jobs"]
    assert set(jobs) == {"socle", "verifier", "deploiement", "image"}
    assert jobs["socle"]["uses"] == "./.github/workflows/modele-socle.yml"
    for nom in ("verifier", "deploiement", "image"):
        assert jobs[nom]["name"] == nom
        assert jobs[nom]["runs-on"] == "ubuntu-latest"
        assert jobs[nom]["steps"][0]["uses"] == CHECKOUT, nom

    deploiement = jobs["deploiement"]
    assert deploiement["needs"] == "verifier"
    assert [e["run"] for e in deploiement["steps"] if "run" in e] == [
        "sh tests/deploiement/lancer.sh"
    ]

    image = jobs["image"]
    assert sorted(image["needs"]) == ["deploiement", "socle", "verifier"]
    assert image["permissions"] == {"contents": "read", "packages": "write"}
    checkout, construire, publier, journal, suppression = image["steps"]
    assert checkout["uses"] == CHECKOUT
    assert construire == {"uses": "./.github/actions/modele-image-construire"}
    assert publier["uses"] == "./.github/actions/modele-image-publier"
    assert journal["if"] == "failure()"
    assert journal["run"] == "docker logs essai || true"
    assert suppression["if"] == "always()"
    assert suppression["run"] == "docker rm -f -v essai"

    # Les tests de bout en bout du projet passent entre la construction et la publication.
    texte = lire(rendu, CI)
    i_construire = texte.index("uses: ./.github/actions/modele-image-construire")
    i_bout = texte.index("# Les tests de bout en bout du projet contre l'image s'ajoutent ici.")
    i_publier = texte.index("uses: ./.github/actions/modele-image-publier")
    assert i_construire < i_bout < i_publier


def test_publication_seulement_sur_la_branche_principale(rendre, env_isole, tmp_path):
    rendu = rendre(**{**REPONSES_SERVEUR, "branche_principale": "principal"})
    doc = charger(rendu, CI)
    assert declencheurs(doc)["push"]["branches"] == ["principal"]
    publications = [
        (nom, e)
        for nom, job in doc["jobs"].items()
        for e in job.get("steps", [])
        if e.get("uses") == "./.github/actions/modele-image-publier"
    ]
    assert len(publications) == 1
    nom, publier = publications[0]
    assert nom == "image"
    assert publier["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/principal'"
    for job in doc["jobs"].values():
        for e in job.get("steps", []):
            assert "docker push" not in e.get("run", ""), e
            assert "docker login" not in e.get("run", ""), e

    # L'action publie :sha-<sha> d'abord, puis :main, sur ghcr.io/edouardzemb/<nom>, et le jeton
    # passe par l'entrée standard, jamais en argument.
    action = charger(rendu, PUBLIER)
    connexion, publication = action["runs"]["steps"]
    assert connexion["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    banc = Banc(tmp_path, env_isole())
    env = {"GITHUB_SHA": SHA, "GITHUB_ACTOR": "acteur", "GITHUB_TOKEN": "jeton-de-test"}
    for e in (connexion, publication):
        r = banc.lancer(e["run"], rendu, ("-e", "-o", "pipefail"), **env)
        assert r.returncode == 0, r.stderr
    image = "ghcr.io/edouardzemb/essai"
    assert banc.appels() == [
        ["login", "ghcr.io", "-u", "acteur", "--password-stdin"],
        ["tag", "essai:ci", f"{image}:sha-{SHA}"],
        ["tag", "essai:ci", f"{image}:main"],
        ["push", f"{image}:sha-{SHA}"],
        ["push", f"{image}:main"],
    ]
    assert (
        banc.journal.with_name("journal.stdin").read_text(encoding="utf-8").strip()
        == "jeton-de-test"
    )
    assert "jeton-de-test" not in banc.journal.read_text(encoding="utf-8")

    # Si :sha-<sha> ne part pas, :main n'avance pas.
    banc.journal.write_text("", encoding="utf-8")
    r = banc.lancer(publication["run"], rendu, ("-e", "-o", "pipefail"), FAUX_PUSH_ECHEC="1", **env)
    assert r.returncode != 0
    assert [a for a in banc.appels() if a[0] == "push"] == [["push", f"{image}:sha-{SHA}"]]


def test_construire_lance_l_image_comme_en_production(rendre, env_isole, tmp_path):
    rendu = rendre(**{**REPONSES_SERVEUR, "port_app": 8080})
    action = charger(rendu, CONSTRUIRE)
    assert action["inputs"]["dossier"] == {
        "description": action["inputs"]["dossier"]["description"],
        "required": False,
        "default": ".",
    }
    assert action["inputs"]["variables"]["required"] is False
    assert action["inputs"]["variables"]["default"] == ""
    construction, lancement, verification = action["runs"]["steps"]
    for e in (construction, lancement, verification):
        assert e["working-directory"] == "${{ inputs.dossier }}", e["name"]
    assert lancement["env"] == {"VARIABLES": "${{ inputs.variables }}"}
    assert (
        verification["run"].strip() == 'bash deploiement/ci/verifier-image.sh essai "$GITHUB_SHA"'
    )

    banc = Banc(tmp_path, env_isole())
    options = ("-e", "-o", "pipefail")
    r = banc.lancer(construction["run"], rendu, options, GITHUB_SHA=SHA)
    assert r.returncode == 0, r.stderr
    variables = "APP_JETON=valeur-du-projet\n\nAPP_PHRASE=deux mots\n"
    r = banc.lancer(lancement["run"], rendu, options, VARIABLES=variables)
    assert r.returncode == 0, r.stderr
    assert banc.appels() == [
        ["build", "--build-arg", f"REVISION={SHA}", "-t", "essai:ci", "."],
        [
            "run", "-d", "--name", "essai", "-p", "127.0.0.1:8080:8080",
            "-e", "ESSAI_ENV=ci", "-e", "ESSAI_URL_PUBLIQUE=http://localhost:8080",
            "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp", "-v", "/donnees",
            "-e", "APP_JETON=valeur-du-projet", "-e", "APP_PHRASE=deux mots",
            "essai:ci",
        ],
    ]  # fmt: skip

    # Sans variables : les seules options du modèle.
    banc.journal.write_text("", encoding="utf-8")
    r = banc.lancer(lancement["run"], rendu, options, VARIABLES="")
    assert r.returncode == 0, r.stderr
    (appel,) = banc.appels()
    assert appel[-1] == "essai:ci"
    assert appel.count("-e") == 2

    # Une ligne invalide arrête tout, sans être répétée : elle peut porter un secret.
    for invalide in ("pas une variable cachee-1", "minuscule=cachee-1", "=cachee-1"):
        banc.journal.write_text("", encoding="utf-8")
        r = banc.lancer(lancement["run"], rendu, options, VARIABLES=f"APP_A=1\n{invalide}\n")
        assert r.returncode == 1, invalide
        assert "ligne 2" in r.stdout + r.stderr
        assert "cachee-1" not in r.stdout + r.stderr
        assert banc.appels() == []


def test_version_controle_l_ancetre_et_ne_reecrit_pas(rendre, env_isole, tmp_path):
    rendu = rendre(**{**REPONSES_SERVEUR, "branche_principale": "principal"})
    doc = charger(rendu, VERSION)
    assert declencheurs(doc) == {"push": {"tags": ["v[0-9]+.[0-9]+.[0-9]+"]}}
    assert doc["concurrency"] == {"group": "version-${{ github.ref }}", "cancel-in-progress": False}
    assert set(doc["jobs"]) == {"publier"}
    job = doc["jobs"]["publier"]
    assert job["name"] == "publier"
    assert job["permissions"] == {"contents": "write", "packages": "write"}
    assert job["env"] == {"IMAGE": "ghcr.io/edouardzemb/essai"}
    etapes = job["steps"]
    assert etapes[0]["uses"] == CHECKOUT
    assert etapes[0]["with"] == {"fetch-depth": 0, "persist-credentials": False}
    noms = [e.get("name") for e in etapes[1:]]
    assert noms == [
        "Déterminer la version et le commit",
        "Vérifier que le commit est sur principal",
        "Se connecter à GHCR",
        "Vérifier que l'image du commit existe",
        "Étiqueter l'image (sans réécrire une version existante)",
        "Créer la Release",
    ]
    # Aucune reconstruction : l'image versionnée est celle que la CI a testée.
    assert not re.search(r"docker build(?!x)", lire(rendu, VERSION))
    release = etape(etapes, "Créer la Release")
    assert 'gh release create "$GITHUB_REF_NAME" --generate-notes --verify-tag' in release["run"]
    assert release["env"] == {"GH_TOKEN": "${{ github.token }}"}

    env = env_isole()
    banc = Banc(tmp_path, env)

    # L'ancêtre : le commit de l'étiquette doit être sur origin/principal.
    depot = tmp_path / "depot"
    depot.mkdir()
    git(depot, env, "init", "-q", "-b", "principal")
    git(depot, env, "config", "core.autocrlf", "false")
    git(depot, env, "commit", "-q", "--allow-empty", "-m", "feat: fusionné")
    fusionne = git(depot, env, "rev-parse", "HEAD").strip()
    git(depot, env, "update-ref", "refs/remotes/origin/principal", fusionne)
    git(depot, env, "checkout", "-q", "-b", "a-cote")
    git(depot, env, "commit", "-q", "--allow-empty", "-m", "feat: hors de principal")
    git(depot, env, "tag", "-a", "-m", "v1.0.0", "v1.0.0", fusionne)
    git(depot, env, "tag", "v1.1.0", "HEAD")
    git(depot, env, "tag", "v1.2", fusionne)
    determiner = etape(etapes, "Déterminer la version et le commit")["run"]
    ancetre = etape(etapes, "Vérifier que le commit est sur")["run"]

    def versionner(etiquette):
        (banc.dossier / "github-env").write_text("", encoding="utf-8")
        r = banc.lancer(determiner, depot, GITHUB_REF_NAME=etiquette)
        if r.returncode != 0:
            return r
        return banc.lancer(ancetre, depot, GITHUB_REF_NAME=etiquette, **banc.github_env())

    r = versionner("v1.0.0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert banc.github_env() == {"VERSION": "1.0.0", "SHA": fusionne}  # l'étiquette annotée suivie
    r = versionner("v1.1.0")
    assert r.returncode == 1
    assert "n'est pas un ancêtre de origin/principal" in r.stdout
    r = versionner("v1.2")
    assert r.returncode == 1
    assert "n'a pas la forme vX.Y.Z" in r.stdout

    # Une version publiée ne se réécrit pas.
    etiqueter = etape(etapes, "Étiqueter l'image")["run"]
    image = "ghcr.io/edouardzemb/essai"
    env_etape = {"IMAGE": image, "VERSION": "1.0.0", "SHA": SHA}
    (banc.registre / f"sha-{SHA}").write_text('{"manifeste":"du commit"}', encoding="utf-8")
    (banc.registre / f"sha-{AUTRE_SHA}").write_text('{"manifeste":"autre"}', encoding="utf-8")

    def creations():
        return [a for a in banc.appels() if a[:3] == ["buildx", "imagetools", "create"]]

    # absente : posée, sans reconstruire, en copiant le manifeste tel quel
    r = banc.lancer(etiqueter, rendu, **env_etape)
    assert r.returncode == 0, r.stdout + r.stderr
    assert creations() == [
        [
            "buildx",
            "imagetools",
            "create",
            "--prefer-index=false",
            "-t",
            f"{image}:1.0.0",
            f"{image}:sha-{SHA}",
        ]
    ]
    assert (banc.registre / "1.0.0").read_bytes() == (banc.registre / f"sha-{SHA}").read_bytes()
    # présente, même contenu : rien à faire (relance)
    banc.journal.write_text("", encoding="utf-8")
    r = banc.lancer(etiqueter, rendu, **env_etape)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "même contenu" in r.stdout
    assert creations() == []
    # présente, autre contenu : refus, et la version publiée ne bouge pas
    banc.journal.write_text("", encoding="utf-8")
    r = banc.lancer(etiqueter, rendu, **{**env_etape, "SHA": AUTRE_SHA})
    assert r.returncode == 1
    assert "une version publiée ne se réécrit pas" in r.stdout
    assert creations() == []
    assert (banc.registre / "1.0.0").read_bytes() == (banc.registre / f"sha-{SHA}").read_bytes()
    # registre illisible : refus plutôt que le risque d'écraser ; une panne qui dit « unknown » ou
    # « 404 » sans dire que le manifeste manque n'est pas une version absente
    for panne in ("failed to do request: connection refused", "unknown host registry (404 from proxy)"):
        banc.journal.write_text("", encoding="utf-8")
        r = banc.lancer(etiqueter, rendu, FAUX_REGISTRE_PANNE=panne, **{**env_etape, "VERSION": "2.0.0"})
        assert r.returncode == 1, panne
        assert "lecture du registre en échec" in r.stdout, panne
        assert creations() == [], panne
        assert not (banc.registre / "2.0.0").exists(), panne
    # absente, dite par le code d'erreur du registre plutôt que par « not found » : posée
    banc.journal.write_text("", encoding="utf-8")
    absente = "ghcr.io/edouardzemb/essai:3.0.0: MANIFEST_UNKNOWN: manifest unknown"
    r = banc.lancer(etiqueter, rendu, FAUX_REGISTRE_ABSENT=absente, **{**env_etape, "VERSION": "3.0.0"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(creations()) == 1
    assert (banc.registre / "3.0.0").read_bytes() == (banc.registre / f"sha-{SHA}").read_bytes()


def test_aucune_cible_sans_fichiers_serveur(rendre):
    rendu = rendre()
    assert not (rendu / ".github/actions").exists()
    assert not (rendu / VERSION).exists()
    assert not (rendu / "deploiement").exists()
    assert not (rendu / "tests").exists()
    doc = charger(rendu, CI)
    assert set(doc["jobs"]) == {"socle"}
    for sauvegardes in (True, False):
        serveur = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
        for chemin in (CONSTRUIRE, PUBLIER, VERSION, VERIFIER_IMAGE, CI_BATS):
            assert (serveur / chemin).is_file(), (sauvegardes, chemin)


def test_verifier_image_lit_projet_env_sans_le_sourcer(rendre):
    """R11 : les commandes viennent de lire_projet_env, jamais d'un `source` de projet.env. Celles
    de l'instance, sur l'exemple, passent par les fonctions du serveur (lib.sh), avec ou sans
    sauvegardes : donnees_declarees, puis _verifier_par."""
    avec = lire(rendre(**REPONSES_SERVEUR), VERIFIER_IMAGE)
    assert "lire_projet_env SAUVEGARDER" in avec
    assert "lire_projet_env VERIFIER" in avec
    sans = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": False}), VERIFIER_IMAGE)
    assert "lire_projet_env" not in sans
    for texte in (avec, sans):
        assert not re.search(r"^\s*(?:\.|source)\s+\S*projet\.env", texte, re.MULTILINE)
        assert texte.rstrip().endswith('main "$@"; exit $?')
        assert "donnees_declarees ||" in texte
        assert '_verifier_par "$cle"' in texte
        # aucun `docker run` à lui : celui de lib.sh, que le serveur lance sur un instantané
        assert not re.search(r"^[^#\n]*docker run", texte, re.MULTILINE)


def test_l_exemple_se_verifie_sur_l_image_construite(rendre):
    """verifier-image.sh lance les commandes de l'exemple sur l'image que l'action vient de
    construire et de lancer : le même nom des deux côtés."""
    rendu = rendre(**{**REPONSES_SERVEUR, "nom": "autre-nom"})
    construire = charger(rendu, CONSTRUIRE)["runs"]["steps"]
    construction = 'docker build --build-arg REVISION="$GITHUB_SHA" -t autre-nom:ci .'
    assert construire[0]["run"] == construction
    assert "autre-nom:ci" in construire[1]["run"]
    assert re.search(r"^IMAGE=autre-nom:ci$", lire(rendu, VERIFIER_IMAGE), re.MULTILINE)


# --- La fausse app ------------------------------------------------------------------------------


def lancer_python(script, *arguments, env=None):
    # Sous Windows, la sortie d'un Python enfant n'est pas en UTF-8 sans PYTHONUTF8.
    return subprocess.run(
        [sys.executable, str(FAUSSE_APP / script), *arguments],
        check=False,
        env={**(env or os.environ), "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def semer(donnees):
    """Les données que le Dockerfile sème dans /donnees."""
    (donnees / "notes").mkdir(parents=True)
    (donnees / "MARQUE").write_text("fausse-app\n", encoding="utf-8", newline="\n")
    (donnees / "notes/premiere.txt").write_text("une note\n", encoding="utf-8", newline="\n")
    (donnees / ".cachee").write_text("un fichier caché\n", encoding="utf-8", newline="\n")


def arbre(dossier):
    return {
        p.relative_to(dossier).as_posix(): p.read_bytes() if p.is_file() else None
        for p in sorted(dossier.rglob("*"))
    }


def test_fausse_app_dockerfile():
    texte = (FAUSSE_APP / "Dockerfile").read_text(encoding="utf-8")
    (base,) = re.findall(r"^FROM\s+(\S+)", texte, re.MULTILINE)
    assert re.fullmatch(r"python:[0-9.]+-slim@sha256:[0-9a-f]{64}", base), base
    assert re.search(r"^ARG REVISION=local$", texte, re.MULTILINE)
    assert "FAUSSE_APP_REVISION=$REVISION" in texte
    assert "PORT=3000" in texte
    assert re.search(
        r"^LABEL org\.opencontainers\.image\.revision=\$REVISION$", texte, re.MULTILINE
    )
    assert re.search(r"^USER 1000:1000$", texte, re.MULTILINE)
    assert "printf 'fausse-app\\n' >/donnees/MARQUE" in texte  # ce que verifier attend
    assert "chown -R 1000:1000 /donnees" in texte
    assert re.search(
        r"^COPY --chmod=0755 sauvegarder verifier verifier-config verifier-contenu /usr/local/bin/$",
        texte,
        re.MULTILINE,
    )
    # L'image embarque son exemple (M-0006, § 5), qu'elle sert quand /config ou /contenu manque.
    assert re.search(r"^COPY exemple /app/exemple$", texte, re.MULTILINE)
    assert re.search(r"^COPY exemple-contenu /app/exemple-contenu$", texte, re.MULTILINE)
    fichiers = {p.name for p in FAUSSE_APP.iterdir()}
    assert fichiers == {
        "Dockerfile",
        "app.py",
        "sauvegarder",
        "verifier",
        "verifier-config",
        "verifier-contenu",
        "exemple",
        "exemple-contenu",
    }
    for script in ("sauvegarder", "verifier", "verifier-config", "verifier-contenu"):
        assert (
            (FAUSSE_APP / script).read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
        )


def test_fausse_app_sauvegarder_et_verifier(tmp_path):
    donnees = tmp_path / "donnees"
    semer(donnees)
    env = {**os.environ, "FAUSSE_APP_DONNEES": str(donnees)}

    # sauvegarder crée exactement le dossier donné, quel que soit son nom, avec la forme de /donnees
    instantane = tmp_path / "sauvegardes" / "essai-20261018T024500Z.partiel"
    instantane.parent.mkdir()
    r = lancer_python("sauvegarder", str(instantane), env=env)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in instantane.parent.iterdir()) == [instantane.name]
    assert arbre(instantane) == arbre(donnees)
    # une destination qui existe déjà n'est jamais écrasée
    (instantane / "MARQUE").write_text("témoin\n", encoding="utf-8")
    r = lancer_python("sauvegarder", str(instantane), env=env)
    assert r.returncode == 1
    assert "existe déjà" in r.stderr
    assert (instantane / "MARQUE").read_text(encoding="utf-8") == "témoin\n"
    # usage
    assert lancer_python("sauvegarder", env=env).returncode == 64
    assert lancer_python("sauvegarder", "a", "b", env=env).returncode == 64

    # verifier : 0 conforme, 2 non conforme, 64 usage
    copie = tmp_path / "copie"
    assert lancer_python("sauvegarder", str(copie), env=env).returncode == 0
    r = lancer_python("verifier", str(copie))
    assert r.returncode == 0, r.stdout + r.stderr
    (copie / "MARQUE").write_text("autre chose\n", encoding="utf-8")
    assert lancer_python("verifier", str(copie)).returncode == 2
    (copie / "MARQUE").unlink()
    r = lancer_python("verifier", str(copie))
    assert r.returncode == 2
    assert "non conforme" in r.stdout
    (copie / "MARQUE").mkdir()
    assert lancer_python("verifier", str(copie)).returncode == 2
    assert lancer_python("verifier", str(tmp_path / "absent")).returncode == 2
    assert lancer_python("verifier", str(donnees / "MARQUE")).returncode == 2
    assert lancer_python("verifier").returncode == 64
    assert lancer_python("verifier", "a", "b").returncode == 64


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def obtenir(adresse):
    try:
        with urllib.request.urlopen(adresse, timeout=2) as reponse:
            return reponse.status, reponse.read()
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read()


def env_de_l_app(tmp_path, **variables):
    """L'environnement de la fausse app : ses données semées, /config et /contenu redirigés vers
    deux chemins de tmp_path (absents tant que le test ne les crée pas), puis ces variables."""
    donnees = tmp_path / "donnees"
    if not donnees.exists():
        semer(donnees)
    return {
        **os.environ,
        "HOST": "127.0.0.1",
        "FAUSSE_APP_DONNEES": str(donnees),
        "FAUSSE_APP_CONFIG": str(tmp_path / "config"),
        "FAUSSE_APP_CONTENU": str(tmp_path / "contenu"),
        "FAUSSE_APP_ENV": "ci",
        "FAUSSE_APP_VERSION": "1.2.3",
        "FAUSSE_APP_REVISION": SHA,
        **variables,
    }


class AppLancee:
    """La fausse app, lancée sur un port libre, jusqu'à la sortie du bloc `with`."""

    def __init__(self, env):
        self.port = port_libre()
        self.env = {**env, "PORT": str(self.port)}

    def __enter__(self):
        self.app = subprocess.Popen(
            [sys.executable, str(FAUSSE_APP / "app.py")],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Une attente qui échoue n'atteint pas __exit__ : l'app est arrêtée ici, avant que l'erreur
        # ne remonte.
        try:
            self.attendre()
        except BaseException:
            self.__exit__()
            raise
        return self

    def attendre(self):
        limite = time.monotonic() + 15
        while True:
            try:
                obtenir(self.adresse())
                return
            except OSError:
                assert self.app.poll() is None, "la fausse app s'est arrêtée"
                assert time.monotonic() < limite, "la fausse app ne répond pas"
                time.sleep(0.1)

    def __exit__(self, *_):
        self.app.terminate()
        self.app.wait(timeout=10)

    def adresse(self, chemin="/api/sante"):
        return f"http://127.0.0.1:{self.port}{chemin}"

    def sante(self):
        code, corps = obtenir(self.adresse())
        return code, json.loads(corps)


def demarrage_refuse(env):
    """La fausse app refuse de démarrer : elle sort d'elle-même, code 1 ; son message d'erreur."""
    r = subprocess.run(
        [sys.executable, str(FAUSSE_APP / "app.py")],
        env={**env, "PORT": str(port_libre()), "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    return r.stderr


def ecrire_config(dossier, version="1\n", titre="Une instance d'essai\n"):
    """Une configuration de la fausse app : sa version de schéma et son titre (None : absent)."""
    dossier.mkdir(parents=True)
    for nom, texte in (("version", version), ("titre", titre)):
        if texte is not None:
            (dossier / nom).write_text(texte, encoding="utf-8", newline="\n")


def ecrire_contenu(dossier, version="1\n", pages=None):
    """Un contenu de la fausse app : sa version de schéma et ses pages, pages/<identifiant>.txt."""
    dossier.mkdir(parents=True)
    if version is not None:
        (dossier / "version").write_text(version, encoding="utf-8", newline="\n")
    (dossier / "pages").mkdir()
    for identifiant, texte in (pages if pages is not None else {"accueil": "Bienvenue\n"}).items():
        (dossier / "pages" / f"{identifiant}.txt").write_text(texte, encoding="utf-8", newline="\n")


def test_fausse_app_sante(tmp_path):
    """Sans /config ni /contenu, hors prod, l'app sert son exemple, et le dit."""
    with AppLancee(env_de_l_app(tmp_path)) as app:
        code, document = app.sante()
        assert code == 200
        assert document == {
            "statut": "ok",
            "environnement": "ci",
            "version": "1.2.3",
            "revision": SHA,
            "configuration": "exemple",
        }
        # sans ses données, la santé dit ko, en 503
        (tmp_path / "donnees/MARQUE").unlink()
        assert app.sante() == (503, {"statut": "ko"})
        code, _ = obtenir(app.adresse("/ailleurs"))
        assert code == 404


def test_fausse_app_configuration_montee(tmp_path):
    """/config monté et non vide : `montee`, en prod comme ailleurs ; vide, c'est l'exemple."""
    (tmp_path / "config").mkdir()
    with AppLancee(env_de_l_app(tmp_path)) as app:
        assert app.sante()[1]["configuration"] == "exemple"
    (tmp_path / "config").rmdir()
    ecrire_config(tmp_path / "config")
    with AppLancee(env_de_l_app(tmp_path, FAUSSE_APP_ENV="staging")) as app:
        assert app.sante()[1]["configuration"] == "montee"
    ecrire_contenu(tmp_path / "contenu")
    with AppLancee(env_de_l_app(tmp_path, FAUSSE_APP_ENV="prod")) as app:
        code, document = app.sante()
        assert code == 200
        assert document["environnement"] == "prod"
        assert document["configuration"] == "montee"


def test_fausse_app_refuse_la_prod_sans_ses_donnees(tmp_path):
    """M-0006, § 5 : pas de repli sur l'exemple en prod, ni sans /config ni sans /contenu."""
    assert "/config" in demarrage_refuse(env_de_l_app(tmp_path, FAUSSE_APP_ENV="prod"))
    ecrire_config(tmp_path / "config")
    assert "/contenu" in demarrage_refuse(env_de_l_app(tmp_path, FAUSSE_APP_ENV="prod"))
    (tmp_path / "contenu").mkdir()
    assert "/contenu" in demarrage_refuse(env_de_l_app(tmp_path, FAUSSE_APP_ENV="prod"))


def test_fausse_app_refuse_une_version_inconnue(tmp_path):
    """La configuration et le contenu portent leur version de schéma : une inconnue, l'app refuse."""
    ecrire_config(tmp_path / "config", version="2\n")
    assert "version de configuration inconnue" in demarrage_refuse(env_de_l_app(tmp_path))
    ecrire_config(tmp_path / "autre-config")
    ecrire_contenu(tmp_path / "contenu", version="2\n")
    env = env_de_l_app(tmp_path, FAUSSE_APP_CONFIG=str(tmp_path / "autre-config"))
    assert "version de contenu inconnue" in demarrage_refuse(env)


def test_fausse_app_exemple_conforme():
    """L'exemple que l'image embarque, et que la CI vérifie (verifier-image.sh), est conforme."""
    r = lancer_python("verifier-config", str(FAUSSE_APP / "exemple"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "conforme" in r.stdout
    r = lancer_python("verifier-contenu", str(FAUSSE_APP / "exemple-contenu"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "conforme" in r.stdout


def test_fausse_app_verifier_config(tmp_path):
    """verifier-config <dossier> : 0 conforme, 2 non conforme, 64 usage."""

    def code(dossier):
        return lancer_python("verifier-config", str(dossier)).returncode

    ecrire_config(tmp_path / "bonne")
    assert code(tmp_path / "bonne") == 0
    ecrire_config(tmp_path / "version-inconnue", version="99\n")
    r = lancer_python("verifier-config", str(tmp_path / "version-inconnue"))
    assert r.returncode == 2
    assert "non conforme" in r.stdout
    assert "99" in r.stdout
    ecrire_config(tmp_path / "sans-version", version=None)
    assert code(tmp_path / "sans-version") == 2
    ecrire_config(tmp_path / "sans-titre", titre=None)
    assert code(tmp_path / "sans-titre") == 2
    ecrire_config(tmp_path / "titre-vide", titre="\n")
    assert code(tmp_path / "titre-vide") == 2
    assert code(tmp_path / "absent") == 2
    assert code(tmp_path / "bonne/titre") == 2
    assert lancer_python("verifier-config").returncode == 64
    assert lancer_python("verifier-config", "a", "b").returncode == 64


def test_fausse_app_verifier_contenu(tmp_path):
    """verifier-contenu <dossier> [<en service>] : 0, 2, 64. Le contenu en service sert à refuser
    un changement qui défait un identifiant définitif : une page en service ne disparaît pas."""

    def lancer(*dossiers):
        return lancer_python("verifier-contenu", *(str(d) for d in dossiers))

    ecrire_contenu(tmp_path / "en-service", pages={"accueil": "Bienvenue\n", "aide": "Aide\n"})
    ecrire_contenu(
        tmp_path / "plus",
        pages={"accueil": "Bonjour\n", "aide": "Aide\n", "nouvelle": "Nouvelle page\n"},
    )
    r = lancer(tmp_path / "plus")
    assert r.returncode == 0
    assert "contenu en service" not in r.stdout
    r = lancer(tmp_path / "plus", tmp_path / "en-service")
    assert r.returncode == 0
    # La sortie, que deployer.sh relaie au journal, dit que le contenu en service a été comparé.
    assert r.stdout.strip() == "conforme, contenu en service comparé : 2 pages, aucune disparue"
    ecrire_contenu(tmp_path / "moins", pages={"accueil": "Bienvenue\n"})
    assert lancer(tmp_path / "moins").returncode == 0
    r = lancer(tmp_path / "moins", tmp_path / "en-service")
    assert r.returncode == 2
    assert "aide" in r.stdout
    ecrire_contenu(tmp_path / "version-inconnue", version="99\n")
    assert lancer(tmp_path / "version-inconnue").returncode == 2
    ecrire_contenu(tmp_path / "sans-version", version=None)
    assert lancer(tmp_path / "sans-version").returncode == 2
    ecrire_contenu(tmp_path / "sans-page", pages={})
    assert lancer(tmp_path / "sans-page").returncode == 2
    ecrire_contenu(tmp_path / "page-vide", pages={"accueil": ""})
    assert lancer(tmp_path / "page-vide").returncode == 2
    assert lancer(tmp_path / "absent").returncode == 2
    # usage : le contenu en service est un dossier que la mécanique monte, sinon rien
    assert lancer(tmp_path / "plus", tmp_path / "absent").returncode == 64
    assert lancer_python("verifier-contenu").returncode == 64
    assert lancer(tmp_path / "plus", tmp_path / "en-service", tmp_path / "moins").returncode == 64
