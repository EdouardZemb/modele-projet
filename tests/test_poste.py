"""Le script de création du poste (`poste/`) : son test PowerShell et son encodage."""

import os
import re
import subprocess
import sys

import jinja2
import pytest
from conftest import (
    RACINE,
    REPONSES_DONNEES_SERVEUR,
    REPONSES_PAR_DEFAUT,
    REPONSES_SERVEUR_CODE,
)

POSTE = RACINE / "poste"
SCRIPTS = ("Nouveau-Projet.ps1", "Tester-Nouveau-Projet.ps1")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 seulement")
def test_le_script_du_poste_passe_ses_tests():
    # copier rend le HEAD du dépôt local, changements non validés et fichiers non suivis compris
    # (DirtyLocalWarning) : valider avant, pour éprouver la tête qui part.
    resultat = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(POSTE / "Tester-Nouveau-Projet.ps1"),
            "-SansPoste",
            "-SourceModele",
            str(RACINE),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=900,
    )
    sortie = resultat.stdout + resultat.stderr
    assert resultat.returncode == 0, sortie
    # Le script écrit en page de code OEM : on ne compare pas les accents. Des cas ont réussi : un
    # testeur qui ne vérifierait rien ne passe pas.
    assert "Mode -SansPoste" in sortie, sortie
    assert re.search(r"(?<![0-9])[1-9][0-9]* r.ussis, 0 .checs", sortie), sortie


@pytest.mark.parametrize("nom", SCRIPTS)
def test_les_scripts_du_poste_sont_en_utf8_avec_bom(nom):
    assert (POSTE / nom).read_bytes()[:3] == b"\xef\xbb\xbf"


def executables_du_modele(reponses: dict) -> list[str]:
    """Les chemins rendus que le modèle porte en 100755 (`git ls-files -s template`), aux noms
    Jinja rendus comme Copier les rend : chaque segment rendu, le suffixe `.jinja` ôté, un
    segment vide écarte le fichier."""
    sortie = subprocess.run(
        ["git", "ls-files", "-s", "-z", "template"],
        cwd=RACINE,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    env = jinja2.Environment()
    chemins = []
    for entree in filter(None, sortie.split("\0")):
        meta, chemin = entree.split("\t", 1)
        if not meta.startswith("100755 "):
            continue
        segments = [env.from_string(s).render(**reponses) for s in chemin.split("/")[1:]]
        segments[-1] = segments[-1].removesuffix(".jinja")
        if all(segments):
            chemins.append("/".join(segments))
    return sorted(chemins)


def executables_du_script(cible: str, sauvegardes: bool) -> list[str]:
    """Ce que le premier commit du script rend exécutable, pour une cible."""
    commande = (
        ". $env:POSTE_NOUVEAU_PROJET -Nom essai -Description essai; "
        f"(Get-Executables -Cible {cible} -Sauvegardes ${str(sauvegardes).lower()}) -join [char]10"
    )
    resultat = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", commande],
        env={**os.environ, "POSTE_NOUVEAU_PROJET": str(POSTE / "Nouveau-Projet.ps1")},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    return sorted(ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip())


# Né sous Windows, un projet n'a de bit d'exécution que celui que son premier commit pose : le script
# le pose sur chaque chemin que le modèle porte en 100755, dans les quatre formes de dépôt qu'il crée.
@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 seulement")
@pytest.mark.parametrize(
    ("cible", "sauvegardes", "reponses"),
    [
        ("serveur", True, REPONSES_SERVEUR_CODE),
        ("serveur", False, {**REPONSES_SERVEUR_CODE, "sauvegardes": False}),
        ("aucune", False, {"nature": "code"}),
        ("donnees", False, REPONSES_DONNEES_SERVEUR),
    ],
    ids=["serveur", "serveur-sans-sauvegardes", "aucune", "donnees"],
)
def test_le_premier_commit_rend_executables_les_chemins_du_modele_en_100755(
    rendre, cible, sauvegardes, reponses
):
    attendus = executables_du_modele({**REPONSES_PAR_DEFAUT, **reponses})
    rendu = rendre(**reponses)
    assert [c for c in attendus if not (rendu / c).is_file()] == []
    assert ".githooks/pre-commit" in attendus
    assert executables_du_script(cible, sauvegardes) == attendus
