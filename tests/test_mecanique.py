"""La mécanique de la cible `serveur` : les tests bats d'un projet rendu, dans leur image Docker.

Le projet est rendu dans les deux modes des données (M-0006, § 6 : un dépôt de code, à deux dépôts ;
un dépôt de nature `donnees`, à un dépôt), avec et sans sauvegardes, puis
`sh tests/deploiement/lancer.sh` construit l'image de test (age et sops aux versions du serveur) et
y lance bats, comme le fera la CI du projet. Il faut Docker avec un serveur Linux : sans lui, le test saute, sauf si
MODELE_TESTS_SANS_SAUT nomme docker (LE-16).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import REPONSES_SERVEUR, REPONSES_SERVEUR_CODE, exiger, manque

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


# Les réponses de chaque mode : `code`, deux dépôts ; `donnees`, un dépôt.
REPONSES_PAR_NATURE = {"code": REPONSES_SERVEUR_CODE, "donnees": REPONSES_SERVEUR}
NATURES = pytest.mark.parametrize("nature", ["code", "donnees"], ids=["deux-depots", "un-depot"])


@NATURES
@pytest.mark.parametrize("sauvegardes", [True, False], ids=["avec-sauvegardes", "sans-sauvegardes"])
def test_bats_de_la_mecanique(rendre, sauvegardes, nature):
    rendu = rendre(**{**REPONSES_PAR_NATURE[nature], "sauvegardes": sauvegardes})
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


@NATURES
def test_banc_gere_ne_lit_pas_les_valeurs_du_projet_env_seme(rendre, nature):
    """C1 : un projet met ses propres commandes (REPORTER, v0.2.1 ; VERIFIER_CONFIG et
    VERIFIER_CONTENU, v0.7.0) dans son projet.env semé.

    Le banc géré (lib.bats) ne doit pas en dépendre : ses tests écrivent le projet.env dont ils ont
    besoin. Ici, le projet.env rendu est remplacé par un fichier qui déclare toutes les clés, avec
    d'autres mots que les valeurs semées, et lib.bats doit rester vert en entier.
    """
    rendu = rendre(**REPONSES_PAR_NATURE[nature])
    exiger_docker_linux()
    if SH is None:
        manque("sh", "sh absent")
    (rendu / "deploiement/projet.env").write_text(
        "SAUVEGARDER=node dist/cli.js sauvegarder\n"
        "VERIFIER=node dist/cli.js verifier\n"
        "REPORTER=outil reporter\n"
        "REPORTER_SECTION=Reporter à la main\n"
        "VERIFIER_CONFIG=node dist/cli.js verifier-config\n"
        "VERIFIER_CONTENU=node dist/cli.js verifier-contenu\n",
        encoding="utf-8",
        newline="\n",
    )
    attendus = len(
        re.findall(
            r"^@test ",
            (rendu / "tests/deploiement/lib.bats").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    r = subprocess.run(
        [SH, "tests/deploiement/lancer.sh", "tests/deploiement/lib.bats"],
        cwd=rendu,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=1800,
    )
    sortie = r.stdout + r.stderr
    echecs = re.findall(r"^not ok .*$", r.stdout, flags=re.MULTILINE)
    assert not echecs, "\n".join(echecs)
    assert r.returncode == 0, sortie[-8000:]
    assert re.search(rf"^1\.\.{attendus}$", r.stdout, flags=re.MULTILINE), sortie[-8000:]
