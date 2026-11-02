"""Le script de création du poste (`poste/`) : son test PowerShell et son encodage."""

import re
import subprocess
import sys

import pytest
from conftest import RACINE

POSTE = RACINE / "poste"
SCRIPTS = ("Nouveau-Projet.ps1", "Tester-Nouveau-Projet.ps1")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 seulement")
def test_le_script_du_poste_passe_ses_tests():
    # copier rend le HEAD validé du dépôt : un changement non validé n'y est pas.
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
    # Le script écrit en page de code OEM : on ne compare pas les accents.
    assert "Mode -SansPoste" in sortie, sortie
    assert re.search(r"(?<![0-9])0 .checs", sortie), sortie


@pytest.mark.parametrize("nom", SCRIPTS)
def test_les_scripts_du_poste_sont_en_utf8_avec_bom(nom):
    assert (POSTE / nom).read_bytes()[:3] == b"\xef\xbb\xbf"
