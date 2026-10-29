"""Les douze combinaisons du rendu : cible x visibilité x fusion."""

import shutil
import subprocess
import sys

import pytest
from conftest import REPONSES_SERVEUR, exiger, fichiers_texte
from test_rendu import RESTE_DE_JINJA

CIBLES = {
    "aucune": {},
    "serveur-avec-sauvegardes": REPONSES_SERVEUR,
    "serveur-sans-sauvegardes": {**REPONSES_SERVEUR, "sauvegardes": False},
}


def lancer(commande, rendu, env=None):
    return subprocess.run(
        commande,
        cwd=rendu,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize("fusion", ["session", "edouard"])
@pytest.mark.parametrize("nature", ["code", "donnees"])
@pytest.mark.parametrize("cible", list(CIBLES))
def test_combinaison(rendre, env_isole, cible, nature, fusion):
    rendu = rendre(**{**CIBLES[cible], "nature": nature, "fusion": fusion})
    fichiers = fichiers_texte(rendu)
    assert fichiers
    for chemin in fichiers:
        assert not chemin.name.endswith(".jinja"), chemin
        octets = chemin.read_bytes()
        assert b"\r" not in octets, chemin
        texte = octets.decode("utf-8")
        assert "{%" not in texte, chemin
        assert not RESTE_DE_JINJA.search(texte), chemin

    env = env_isole()
    commande = [sys.executable, "scripts/modele/confidentialite.py", "--fichiers", *[str(f) for f in fichiers]]
    if nature == "code":
        commande.append("--public")
    r = lancer(commande, rendu, env)
    assert r.returncode == 0, r.stderr

    r = lancer([sys.executable, "-m", "ruff", "check", "scripts/modele"], rendu)
    assert r.returncode == 0, r.stdout + r.stderr

    r = lancer([sys.executable, "scripts/modele/verifier_secrets.py"], rendu, env)
    assert r.returncode == 0, r.stdout + r.stderr


def scripts_shell(rendu):
    """Les scripts shell de la mécanique rendue : deploiement/ et son banc bats."""
    scripts = []
    deploiement = rendu / "deploiement"
    if deploiement.is_dir():
        scripts += sorted(deploiement.glob("**/*.sh"))
    banc = rendu / "tests/deploiement"
    if banc.is_dir():
        scripts += sorted(banc.glob("*.sh")) + sorted(banc.glob("*.bash")) + sorted(banc.glob("*.bats"))
        scripts += sorted(p for p in (banc / "doubles").iterdir() if p.is_file())
    return scripts


# Seul ce contrôle demande shellcheck : sans lui, les autres contrôles de la combinaison ne sautent
# pas (R7).
@pytest.mark.parametrize("fusion", ["session", "edouard"])
@pytest.mark.parametrize("nature", ["code", "donnees"])
@pytest.mark.parametrize("cible", list(CIBLES))
def test_combinaison_shellcheck(rendre, cible, nature, fusion):
    rendu = rendre(**{**CIBLES[cible], "nature": nature, "fusion": fusion})
    scripts = scripts_shell(rendu)
    assert bool(scripts) == (cible != "aucune"), scripts
    if not scripts:
        return
    exiger("shellcheck")
    r = lancer([shutil.which("shellcheck"), *[str(s) for s in scripts]], rendu)
    assert r.returncode == 0, r.stdout + r.stderr
