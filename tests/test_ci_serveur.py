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
    """R11 : les commandes viennent de lire_projet_env, jamais d'un `source` de projet.env."""
    avec = lire(rendre(**REPONSES_SERVEUR), VERIFIER_IMAGE)
    assert "lire_projet_env SAUVEGARDER" in avec
    assert "lire_projet_env VERIFIER" in avec
    sans = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": False}), VERIFIER_IMAGE)
    assert "lire_projet_env" not in sans
    for texte in (avec, sans):
        assert not re.search(r"^\s*(?:\.|source)\s+\S*projet\.env", texte, re.MULTILINE)
        assert texte.rstrip().endswith('main "$@"; exit $?')


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
        r"^COPY --chmod=0755 sauvegarder verifier /usr/local/bin/$", texte, re.MULTILINE
    )
    fichiers = {p.name for p in FAUSSE_APP.iterdir()}
    assert fichiers == {"Dockerfile", "app.py", "sauvegarder", "verifier"}
    for script in ("sauvegarder", "verifier"):
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


def test_fausse_app_sante(tmp_path):
    donnees = tmp_path / "donnees"
    semer(donnees)
    port = port_libre()
    env = {
        **os.environ,
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "FAUSSE_APP_DONNEES": str(donnees),
        "FAUSSE_APP_ENV": "ci",
        "FAUSSE_APP_VERSION": "1.2.3",
        "FAUSSE_APP_REVISION": SHA,
    }
    app = subprocess.Popen(
        [sys.executable, str(FAUSSE_APP / "app.py")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        adresse = f"http://127.0.0.1:{port}/api/sante"
        limite = time.monotonic() + 15
        while True:
            try:
                code, corps = obtenir(adresse)
                break
            except OSError:
                assert app.poll() is None, "la fausse app s'est arrêtée"
                assert time.monotonic() < limite, "la fausse app ne répond pas"
                time.sleep(0.1)
        assert code == 200
        assert json.loads(corps) == {
            "statut": "ok",
            "environnement": "ci",
            "version": "1.2.3",
            "revision": SHA,
        }
        # sans ses données, la santé dit ko, en 503
        (donnees / "MARQUE").unlink()
        code, corps = obtenir(adresse)
        assert code == 503
        assert json.loads(corps) == {"statut": "ko"}
        code, _ = obtenir(f"http://127.0.0.1:{port}/ailleurs")
        assert code == 404
    finally:
        app.terminate()
        app.wait(timeout=10)
