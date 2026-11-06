"""Les vingt combinaisons du rendu : cible (cinq) x nature x fusion."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
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


# Un lien en ligne, avec des chevrons ou un titre, son texte sur deux lignes au besoin ; une
# définition de référence, hors d'une note (`[^1]:`) ; un titre, sans ses espaces de fin ni sa
# séquence fermante (`## Titre ##`), comme GitHub les retire avant de calculer l'ancre ; un bloc de
# code clôturé, où GitHub ne rend ni lien ni titre.
LIEN = re.compile(
    r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
REFERENCE = re.compile(r"^ {0,3}\[(?!\^)[^\]]+\]:[ \t]*<?([^\s>]+)>?", re.MULTILINE)
TITRE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", re.MULTILINE)
CLOTURE = re.compile(
    r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[`~]*[ \t]*$", re.MULTILINE | re.DOTALL
)
SCHEMA = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def liens_de(texte: str) -> list[str]:
    """Les cibles des liens que GitHub rend dans un texte : en ligne, puis de référence."""
    texte = CLOTURE.sub("", texte)
    return LIEN.findall(texte) + REFERENCE.findall(texte)


def ancres_de(texte: str) -> set[str]:
    """Les ancres des titres d'un texte, hors des blocs de code clôturés."""
    return {slug_github(titre) for titre in TITRE.findall(CLOTURE.sub("", texte))}


def lien_casse(racine: Path, source: str, lien: str) -> bool:
    """Un lien relatif de `source`, un fichier de la racine, qui ne mène à rien : un chemin absent,
    à la casse près de chaque segment, comme le lit GitHub (sous Windows, `exists()` ne voit pas la
    casse), ou une ancre qui n'est le `slug_github` d'aucun titre du fichier visé. Une ancre seule
    vise `source`, un `/` en tête part de la racine, un `..` en sort."""
    chemin, _, ancre = lien.partition("#")
    chemin = unquote(chemin.partition("?")[0]).lstrip("/") or source
    courant = racine
    for segment in PurePosixPath(chemin).parts:
        if segment == ".." or not courant.is_dir() or segment not in os.listdir(courant):
            return True
        courant = courant / segment
    if not ancre:
        return False
    if not courant.is_file():
        return True
    return unquote(ancre) not in ancres_de(courant.read_text(encoding="utf-8"))


def verifier_readme(rendu: Path, cible: str, nature: str) -> None:
    """Le README rendu : les titres de sa variante, dans l'ordre ; chaque lien relatif (en ligne ou
    de référence, une ancre seule comprise) mène à un fichier ou à un dossier du rendu, et chaque
    ancre à un titre de son fichier ; rien qui se périme. Un compte de liens minimal, pour ne pas
    passer à vide."""
    texte = (rendu / "README.md").read_text(encoding="utf-8")
    titres = re.findall(r"^## (.+)$", CLOTURE.sub("", texte), flags=re.MULTILINE)
    liens = liens_de(texte)
    relatifs = [lien for lien in liens if not SCHEMA.match(lien)]
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
    casses = [lien for lien in relatifs if lien_casse(rendu, "README.md", lien)]
    assert not casses, casses
    perime = PERIMES.search(texte)
    assert perime is None, perime


def test_perimes_et_slug_github():
    """Les aides du README savent mordre : un motif cassé laisserait passer les rendus à vide."""
    perimes = (
        "v1.2.3", "1.2.3", "lot 14", "Lot 14", "les lots 8", "lot 3", "lot\n14",
        "10h30", "03:30", "Actuellement", "bientôt", "PROCHAINEMENT",
    )
    for mot in perimes:
        assert PERIMES.search(f"x {mot} y"), mot
    for sain in ("M-0006", "secrets.ps1", "CLAUDE.md#état", "ce que les lots ont appris", "le lot"):
        assert not PERIMES.search(sain), sain
    assert slug_github("Invariants — ne jamais violer") == "invariants--ne-jamais-violer"
    assert slug_github("État") == "état"
    assert slug_github("Où lire quoi") == "où-lire-quoi"


def test_verification_des_liens_mord(tmp_path):
    """Chaque forme de lien que GitHub rend est vue, et un lien cassé de chaque forme est refusé ;
    un lien ou un titre d'un bloc de code clôturé ne compte pas."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(
        "## État \n## Commandes ##\n```\n# Pas un titre\n```\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("## Démarrer\n", encoding="utf-8")
    bons = (
        '[x](docs/a.md "titre")\n'
        "[y](<./docs/a.md>)\n"
        "[`CLAUDE.md`](CLAUDE.md#état)\n"
        "[les\ncommandes](CLAUDE.md#commandes)\n"
        "[seul](#démarrer)\n"
        "[dossier](docs)\n"
        "[ref]: /docs/a.md\n"
        "[^1]: une note, pas un lien\n"
    )
    vus = liens_de(bons)
    assert len(vus) == 7, vus
    assert [lien for lien in vus if lien_casse(tmp_path, "README.md", lien)] == []
    casses = (
        '[x](docs/absent.md "titre")\n'
        "[y](<docs/absent.md>)\n"
        "[seul](#absent)\n"
        "[casse](claude.md)\n"
        "[ancre](CLAUDE.md#pas-un-titre)\n"
        "[sortie](../README.md)\n"
        "[ref]: docs/absent.md\n"
        "```\n[code](docs/absent.md)\n```\n"
    )
    vus = liens_de(casses)
    assert len(vus) == 7, vus
    assert [lien for lien in vus if not lien_casse(tmp_path, "README.md", lien)] == []


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
