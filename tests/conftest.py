"""Banc d'essai : rend le modèle Copier dans un dossier temporaire."""

import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import copier
import pytest

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = RACINE / "template/scripts/modele"

# Les scripts du modèle sont importés directement par les tests.
sys.path.insert(0, str(SCRIPTS))

REGISTRE_ENTETE = "| N° | Famille | Date | Constat | Motif | Prévention | Critère de sortie | État |"

REPONSES_PAR_DEFAUT = {
    "nom": "essai",
    "description": "Projet d'essai",
    "visibilite": "public",
    "cible": "aucune",
    "branche_principale": "main",
    "fusion": "session",
}


@pytest.fixture
def rendre(tmp_path):
    """Donne rendre(**reponses) -> Path, un rendu neuf du modèle depuis HEAD."""
    compteur = {"n": 0}

    def _rendre(**reponses):
        compteur["n"] += 1
        destination = tmp_path / f"rendu-{compteur['n']}"
        donnees = {**REPONSES_PAR_DEFAUT, **reponses}
        with warnings.catch_warnings():
            # Copier signale un dépôt local « sale » : c'est voulu, on teste le travail en cours.
            warnings.filterwarnings("ignore", message=".*dirty.*", category=Warning)
            warnings.filterwarnings("ignore", category=copier.errors.DirtyLocalWarning)
            copier.run_copy(
                str(RACINE),
                destination,
                data=donnees,
                vcs_ref="HEAD",
                defaults=True,
                unsafe=True,
                quiet=True,
            )
        return destination

    return _rendre


def fichiers_texte(racine: Path) -> list[Path]:
    """Tous les fichiers hors .git/, binaires exclus (octet nul dans les 8 premiers Kio)."""
    resultat = []
    for chemin in sorted(racine.rglob("*")):
        if not chemin.is_file() or ".git" in chemin.relative_to(racine).parts:
            continue
        with chemin.open("rb") as f:
            if b"\0" in f.read(8192):
                continue
        resultat.append(chemin)
    return resultat


@pytest.fixture
def env_isole(tmp_path):
    """Donne env_isole() -> dict : environnement sans HOME réel ni motifs privés."""

    def _env():
        home = tmp_path / "home-vide"
        home.mkdir(exist_ok=True)
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env.pop("MOTIFS_INTERDITS", None)
        env.pop("DEPOT_PRIVE", None)  # en CI, la visibilité réelle ; ici, celle des réglages
        env.update(
            GIT_AUTHOR_NAME="Essai",
            GIT_AUTHOR_EMAIL="essai@example.com",
            GIT_COMMITTER_NAME="Essai",
            GIT_COMMITTER_EMAIL="essai@example.com",
        )
        return env

    return _env


def git(cwd, env, *args):
    r = subprocess.run(
        ["git", *args],
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def depot(tmp_path, env):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, env, "init", "-q", "-b", "main")
    git(d, env, "config", "core.autocrlf", "false")
    return d


def exiger(*dependances):
    """Saute le test si une dépendance du système manque, sauf si MODELE_TESTS_SANS_SAUT la nomme.

    MODELE_TESTS_SANS_SAUT est une liste séparée par des virgules ; « 1 » les vaut toutes.
    Une dépendance nommée qui manque fait échouer le test au lieu de le sauter (LE-16).
    """
    liste = {d.strip() for d in os.environ.get("MODELE_TESTS_SANS_SAUT", "").split(",") if d.strip()}
    for dependance in dependances:
        if shutil.which(dependance):
            continue
        if "1" in liste or dependance in liste:
            pytest.fail(f"{dependance} manque et MODELE_TESTS_SANS_SAUT l'exige")
        pytest.skip(f"{dependance} absent")
