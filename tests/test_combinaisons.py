"""Les vingt combinaisons du rendu : cible (cinq) x nature x fusion."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import documentation
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


# Les liens se lisent par `documentation.liens`, le script que lance la CI des projets : un seul
# analyseur. Ici, un titre, sans ses espaces de fin ni sa séquence fermante (`## Titre ##`), comme
# GitHub les retire avant de calculer l'ancre ; un bloc de code clôturé, où GitHub ne rend aucun
# titre.
TITRE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", re.MULTILINE)
CLOTURE = re.compile(
    r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[`~]*[ \t]*$", re.MULTILINE | re.DOTALL
)
SCHEMA = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def ancres_de(texte: str) -> set[str]:
    """Les ancres des titres d'un texte, hors des blocs de code clôturés."""
    return {slug_github(titre) for titre in TITRE.findall(CLOTURE.sub("", texte))}


def lien_casse(racine: Path, source: str, lien: str) -> bool:
    """Un lien relatif de `source`, un fichier de la racine, qui ne mène à rien : une cible qui sort
    de la racine, que `documentation.cible_locale` refuse ; un chemin absent, à la casse près de
    chaque segment, comme le lit GitHub (sous Windows, `exists()` ne voit pas la casse) ; ou une
    ancre qui n'est le `slug_github` d'aucun titre du fichier visé. Une ancre seule vise `source`."""
    avant, _, ancre = lien.partition("#")
    if avant.partition("?")[0]:
        chemin = documentation.cible_locale(lien, racine)
        if chemin is None:
            return True
    else:
        chemin = source
    courant = racine
    for segment in PurePosixPath(chemin).parts:
        if not courant.is_dir() or segment not in os.listdir(courant):
            return True
        courant = courant / segment
    if not ancre:
        return False
    if not courant.is_file():
        return True
    return unquote(ancre) not in ancres_de(courant.read_text(encoding="utf-8"))


def verifier_readme(rendu: Path, cible: str, nature: str) -> None:
    """Le README rendu : les titres de sa variante, dans l'ordre ; chaque lien relatif que lit
    `documentation.liens` (une ancre seule comprise) mène à un fichier ou à un dossier du rendu, et
    chaque ancre à un titre de son fichier ; rien qui se périme. Un compte de liens minimal, pour ne
    pas passer à vide."""
    texte = (rendu / "README.md").read_text(encoding="utf-8")
    titres = re.findall(r"^## (.+)$", CLOTURE.sub("", texte), flags=re.MULTILINE)
    liens = documentation.liens(texte)
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
        "v1.2.3", "1.2.3", "lot 14", "Lot 14", "les lots 8", "lot 3", "lot\n14", "lot #22",
        "lot n° 3", "lot nº3", "10h30", "03:30", "Actuellement", "bientôt", "PROCHAINEMENT",
    )
    for mot in perimes:
        assert PERIMES.search(f"x {mot} y"), mot
    sains = (
        "M-0006", "secrets.ps1", "CLAUDE.md#état", "ce que les lots ont appris", "le lot",
        "## Le cycle d'un lot\n\n1. Une issue",
    )
    for sain in sains:
        assert not PERIMES.search(sain), sain
    assert slug_github("Invariants — ne jamais violer") == "invariants--ne-jamais-violer"
    assert slug_github("État") == "état"
    assert slug_github("Où lire quoi") == "où-lire-quoi"


def test_verification_des_liens_mord(tmp_path):
    """Les formes de lien de ce test sont vues (un titre, des chevrons, une ancre seule, un texte
    sur deux lignes, entre accents graves ou entre crochets, une image cliquable et ses deux cibles,
    une référence employée, sa définition sur deux lignes comprise), et un lien cassé de chaque
    forme est refusé ; un lien en code en ligne, une définition qui coupe un paragraphe, ou un lien
    ou un titre d'un bloc de code clôturé, ne compte pas."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "docs/c.png").write_bytes(b"\x89PNG")
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
        "[![capture](docs/c.png)](docs/a.md)\n"
        "[a [b] c](docs/a.md)\n"
        "Un exemple : `[x](NOTICE.md)`.\n"
        "Voir [la référence][ref] et [ref2][].\n"
        "[colle]: NOTICE.md\n"
        "\n"
        "[ref]: /docs/a.md\n"
        "[ref2]:\n  docs/a.md\n"
        "\n"
        "[^1]: une note, pas un lien\n"
    )
    vus = documentation.liens(bons)
    assert len(vus) == 11, vus
    assert "NOTICE.md" not in vus
    assert [lien for lien in vus if lien_casse(tmp_path, "README.md", lien)] == []
    casses = (
        '[x](docs/absent.md "titre")\n'
        "[y](<docs/absent.md>)\n"
        "[seul](#absent)\n"
        "[casse](claude.md)\n"
        "[ancre](CLAUDE.md#pas-un-titre)\n"
        "[sortie](../README.md)\n"
        "[![capture](docs/absent.png)](docs/absent.md)\n"
        "[a [b] c](docs/absent.md)\n"
        "Un exemple : `[x](docs/a.md)`.\n"
        "Voir [la référence][ref] et [ref2][].\n"
        "\n"
        "[ref]: docs/absent.md\n"
        "[ref2]:\n  docs/absent.md\n"
        "```\n[code](docs/absent.md)\n```\n"
    )
    vus = documentation.liens(casses)
    assert len(vus) == 11, vus
    assert [lien for lien in vus if not lien_casse(tmp_path, "README.md", lien)] == []


@pytest.mark.parametrize("fusion", ["session", "edouard"])
@pytest.mark.parametrize("nature", ["code", "donnees"])
@pytest.mark.parametrize("cible", list(CIBLES))
def test_combinaison(rendre, env_isole, cible, nature, fusion):
    rendu = rendre(**reponses(cible, nature, fusion))
    fichiers = fichiers_texte(rendu)
    assert fichiers
    # Le texte de la documentation est géré, et rendu dans toutes les cibles.
    assert (rendu / "docs/modele/documentation.md").is_file()
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

    # La licence et la carte, comme en CI : elles passent, et disent ce qu'elles ont vu.
    r = lancer([sys.executable, "scripts/modele/documentation.py"], rendu, env)
    assert r.returncode == 0, r.stdout + r.stderr
    sortie = r.stdout.splitlines()
    assert "documentation : carte : 1 fichier .md à la racine, lié" in sortie, sortie
    if nature == "code" and not cible.startswith("donnees"):
        assert "documentation : licence : LICENSE présent (nature code)" in sortie, sortie
    else:
        assert "documentation : licence : non exigée (nature donnees)" in sortie, sortie

    # Le gabarit resté vide : un projet qui vient de naître ne donne rien. Pour ne pas passer à
    # vide, un document vide que le README lie donne ensuite son constat.
    gabarits_vides = [sys.executable, "scripts/modele/documentation.py", "--gabarits-vides"]
    r = lancer(gabarits_vides, rendu, env)
    assert (r.returncode, r.stdout) == (0, ""), r.stdout + r.stderr
    (rendu / "docs").mkdir(exist_ok=True)
    (rendu / "docs/vide.md").write_bytes(b"")
    with (rendu / "README.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write("\nUn [document vide](docs/vide.md).\n")
    r = lancer(gabarits_vides, rendu, env)
    assert r.returncode == 0, r.stdout + r.stderr
    vide = "documentation : docs/vide.md : corps vide (titres et consignes seulement)"
    assert r.stdout.splitlines() == [vide], r.stdout
    if not cible.startswith("donnees"):
        # Les vrais gabarits du modèle, laissés tels quels et liés par le README, donnent chacun
        # leur constat, dans l'ordre des liens : si leurs consignes changeaient de forme, le
        # contrôle cesserait de les voir.
        with (rendu / "README.md").open("a", encoding="utf-8", newline="\n") as f:
            f.write("[b](docs/00-brief-initial.md) [c](docs/cadrage.md) [d](docs/decisions/)\n")
        r = lancer(gabarits_vides, rendu, env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.splitlines() == [
            vide,
            "documentation : docs/00-brief-initial.md : corps vide (titres et consignes seulement)",
            "documentation : docs/cadrage.md : garde le marqueur *AAAA-MM-JJ* du gabarit",
            "documentation : docs/decisions/ : dossier sans autre fichier que README.md",
        ], r.stdout


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
