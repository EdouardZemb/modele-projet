"""Les vingt combinaisons du rendu : cible (cinq) x nature x fusion."""

import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest
from conftest import (
    INSTANCE_DE_TEST,
    PERIMES,
    REPONSES_DONNEES_SERVEUR,
    exiger,
    fichiers_texte,
    slug_github,
)
from test_rendu import RESTE_DE_JINJA

CIBLES = {
    "aucune": {},
    "serveur-avec-sauvegardes": {"cible": "serveur", "sauvegardes": True},
    "serveur-sans-sauvegardes": {"cible": "serveur", "sauvegardes": False},
    "donnees": {"nom": "essai-donnees", "cible": "donnees"},
    "donnees-serveur": REPONSES_DONNEES_SERVEUR,
}


def reponses(cible, nature, fusion):
    """Les réponses d'une combinaison. En `serveur`, l'instance n'est donnée qu'au mode à un dépôt
    (nature `donnees`) : un dépôt de code naît sans elle (M-0006, § 4). Un dépôt de données est
    toujours de nature `donnees`, quoi qu'on passe."""
    resultat = {**CIBLES[cible], "nature": nature, "fusion": fusion}
    if cible.startswith("serveur") and nature == "donnees":
        resultat.update(INSTANCE_DE_TEST)
    return resultat


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


LIEN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TITRE = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)


def verifier_readme(rendu: Path, cible: str, nature: str) -> None:
    """Le README rendu : les titres de sa variante, dans l'ordre ; chaque lien relatif mène à un
    fichier ou à un dossier du rendu, et chaque ancre à un titre de son fichier ; rien qui se périme.
    Un compte de liens minimal, pour ne pas passer à vide."""
    texte = (rendu / "README.md").read_text(encoding="utf-8")
    titres = re.findall(r"^## (.+)$", texte, flags=re.MULTILINE)
    liens = LIEN.findall(texte)
    relatifs = [
        lien for lien in liens if not re.match(r"[a-z][a-z0-9+.-]*:", lien) and lien[0] != "#"
    ]
    if cible.startswith("donnees"):
        assert titres == ["Carte", "Ce qui n'y va jamais"]
        assert "[CLAUDE.md](CLAUDE.md)" in texte
        assert "https://github.com/EdouardZemb/essai" in liens
        # Les dossiers ne portent pas de lien : à la naissance, ils sont vides ou absents.
        for dossier in ("config/", "contenu/", "env/", "cles/", "secrets/"):
            assert f"]({dossier}" not in texte, dossier
        carte = [
            ligne.split("|")[1].strip() for ligne in texte.splitlines() if ligne.startswith("| `")
        ]
        for dossier in ("`env/`", "`cles/`", "`secrets/`"):
            assert (dossier in carte) == (cible == "donnees-serveur"), dossier
        assert len(relatifs) >= 1, relatifs
    else:
        attendus = ["Pourquoi", "Démarrer", "Où lire quoi", "Contribuer"]
        if nature == "code":
            attendus.append("Licence")
        assert titres == attendus
        assert ("](docs/exploitation.md)" in texte) == cible.startswith("serveur")
        assert "https://github.com/EdouardZemb/essai/releases" in liens
        assert len(relatifs) >= 6, relatifs
        assert sum("#" in lien for lien in relatifs) >= 2, relatifs
    assert (rendu / "LICENSE").exists() == ("Licence" in titres)
    for lien in relatifs:
        chemin, _, ancre = lien.partition("#")
        assert (rendu / chemin).exists(), lien
        if ancre:
            vise = (rendu / chemin).read_text(encoding="utf-8")
            assert unquote(ancre) in {slug_github(t) for t in TITRE.findall(vise)}, lien
    perime = PERIMES.search(texte)
    assert perime is None, perime


@pytest.mark.parametrize("fusion", ["session", "edouard"])
@pytest.mark.parametrize("nature", ["code", "donnees"])
@pytest.mark.parametrize("cible", list(CIBLES))
def test_combinaison(rendre, env_isole, cible, nature, fusion):
    rendu = rendre(**reponses(cible, nature, fusion))
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
    # Des chemins relatifs au rendu, en `/`, comme les donne git : la règle des chemins de
    # l'instance lit le premier et le dernier segment (M-0006, § 3).
    relatifs = [f.relative_to(rendu).as_posix() for f in fichiers]
    commande = [sys.executable, "scripts/modele/confidentialite.py", "--fichiers", *relatifs]
    # --public force le régime `code`, celui d'un dépôt de code ; un dépôt de données n'en est jamais un.
    if nature == "code" and not cible.startswith("donnees"):
        commande.append("--public")
    r = lancer(commande, rendu, env)
    assert r.returncode == 0, r.stderr

    r = lancer([sys.executable, "-m", "ruff", "check", "scripts/modele"], rendu)
    assert r.returncode == 0, r.stdout + r.stderr

    r = lancer([sys.executable, "scripts/modele/verifier_secrets.py"], rendu, env)
    assert r.returncode == 0, r.stdout + r.stderr

    verifier_readme(rendu, cible, nature)


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
    rendu = rendre(**reponses(cible, nature, fusion))
    scripts = scripts_shell(rendu)
    assert bool(scripts) == cible.startswith("serveur"), scripts
    if not scripts:
        return
    exiger("shellcheck")
    r = lancer([shutil.which("shellcheck"), *[str(s) for s in scripts]], rendu)
    assert r.returncode == 0, r.stdout + r.stderr
