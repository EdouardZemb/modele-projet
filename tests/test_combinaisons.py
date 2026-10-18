"""Les douze combinaisons du rendu : cible x visibilité x fusion."""

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
@pytest.mark.parametrize("visibilite", ["public", "prive"])
@pytest.mark.parametrize("cible", list(CIBLES))
def test_combinaison(rendre, env_isole, cible, visibilite, fusion):
    rendu = rendre(**{**CIBLES[cible], "visibilite": visibilite, "fusion": fusion})
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
    if visibilite == "public":
        commande.append("--public")
    r = lancer(commande, rendu, env)
    assert r.returncode == 0, r.stderr

    r = lancer([sys.executable, "-m", "ruff", "check", "scripts/modele"], rendu)
    assert r.returncode == 0, r.stdout + r.stderr

    dossier = rendu / "deploiement"
    scripts_sh = sorted(dossier.glob("**/*.sh")) if dossier.is_dir() else []
    if scripts_sh:
        exiger("shellcheck")
        r = lancer(["shellcheck", *[str(s) for s in scripts_sh]], rendu)
        assert r.returncode == 0, r.stdout + r.stderr

    r = lancer([sys.executable, "scripts/modele/verifier_secrets.py"], rendu, env)
    assert r.returncode == 0, r.stdout + r.stderr
