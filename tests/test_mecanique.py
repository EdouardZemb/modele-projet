"""La mécanique de la cible `serveur` : les tests bats d'un projet rendu, dans leur image Docker.

Le projet est rendu avec et sans sauvegardes, puis `sh tests/deploiement/lancer.sh` construit
l'image de test (age et sops aux versions du serveur) et y lance bats, comme le fera la CI du
projet. Il faut Docker avec un serveur Linux : sans lui, le test saute, sauf si
MODELE_TESTS_SANS_SAUT nomme docker (LE-16).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import REPONSES_SERVEUR, exiger, manque

SH = shutil.which("sh") or (
    r"C:\Program Files\Git\bin\sh.exe" if Path(r"C:\Program Files\Git\bin\sh.exe").exists() else None
)


def exiger_docker_linux():
    """Docker, et un serveur qui lance des conteneurs Linux : l'image de test est une Debian.

    Sous Windows, Docker sert des conteneurs Windows (les exécuteurs de GitHub), ou n'est pas lancé.
    """
    exiger("docker")
    r = subprocess.run(
        ["docker", "info", "--format", "{{.OSType}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if r.returncode != 0 or r.stdout.strip() != "linux":
        manque("docker", "pas de serveur Docker Linux")


def nombre_de_tests(rendu):
    """Les `@test` des fichiers bats rendus : ce que bats doit annoncer, ni plus ni moins."""
    return sum(
        len(re.findall(r"^@test ", chemin.read_text(encoding="utf-8"), flags=re.MULTILINE))
        for chemin in (rendu / "tests/deploiement").glob("*.bats")
    )


@pytest.mark.parametrize("sauvegardes", [True, False], ids=["avec-sauvegardes", "sans-sauvegardes"])
def test_bats_de_la_mecanique(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    lanceur = rendu / "tests/deploiement/lancer.sh"
    assert lanceur.is_file(), "tests/deploiement/lancer.sh absent du rendu"
    attendus = nombre_de_tests(rendu)
    assert attendus > 0, "aucun test bats rendu"
    exiger_docker_linux()
    if SH is None:
        manque("sh", "sh absent")

    r = subprocess.run(
        [SH, "tests/deploiement/lancer.sh"],
        cwd=rendu,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=1800,
    )
    sortie = r.stdout + r.stderr
    assert r.returncode == 0, sortie[-8000:]
    # Le plan TAP de bats : tous les tests rendus ont tourné, aucun n'a échoué ni sauté.
    assert re.search(rf"^1\.\.{attendus}$", r.stdout, flags=re.MULTILINE), sortie[-8000:]
    assert not re.search(r"^not ok ", r.stdout, flags=re.MULTILINE), sortie[-8000:]
    assert not re.search(r"^ok .* # skip", r.stdout, flags=re.MULTILINE), sortie[-8000:]
