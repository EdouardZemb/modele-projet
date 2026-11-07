"""Les fichiers semés : donnés une fois par le modèle, puis propres au projet."""

import hashlib
import re
import subprocess
import sys

import pytest
import yaml
from conftest import (
    RACINE,
    REGISTRE_ENTETE,
    REPONSES_DONNEES_SERVEUR,
    REPONSES_SERVEUR,
    REPONSES_SERVEUR_CODE,
    git,
)


def lire(rendu, chemin):
    return (rendu / chemin).read_text(encoding="utf-8")


def titres(texte, niveau):
    return re.findall(rf"^{'#' * niveau} (.+)$", texte, flags=re.MULTILINE)


def test_claude_md_importe_la_methode(rendre):
    texte = lire(rendre(), "CLAUDE.md")
    assert texte.splitlines()[0] == "@docs/modele/methode.md"
    assert "# essai" in texte
    assert "Projet d'essai" in texte
    assert titres(texte, 2) == [
        "État",
        "Commandes",
        "Ce qui fait foi",
        "Invariants — ne jamais violer",
    ]
    assert "## Exploitation" not in texte


# « Ce qui fait foi » cite ses chemins par des liens, jamais entre accents graves : la carte de la
# racine ne compte que les liens. Le brief et le cadrage y sont, puisque le README ne les lie plus.
def test_ce_qui_fait_foi_cite_par_des_liens(rendre):
    rendu = rendre()
    texte = (rendu / "CLAUDE.md").read_text(encoding="utf-8")
    section = texte.split("## Ce qui fait foi\n", 1)[1].split("\n## ", 1)[0]
    assert "Un fichier de la racine s'y cite par un lien." in section
    assert "[le brief](docs/00-brief-initial.md)" in section
    assert "[le cadrage](docs/cadrage.md)" in section
    assert "`docs/" not in section
    for cible in re.findall(r"\]\(([^)]+)\)", section):
        assert (rendu / cible).exists(), cible


def test_registre_entete(rendre):
    lignes = lire(rendre(), "docs/registre.md").splitlines()
    i = lignes.index(REGISTRE_ENTETE)
    assert re.fullmatch(r"\|(-{3,}\|){8}", lignes[i + 1])


def test_gabarits_docs(rendre):
    rendu = rendre()
    brief = lire(rendu, "docs/00-brief-initial.md")
    assert titres(brief, 2) == [
        "1. D'où l'on part",
        "2. Ce qu'on veut obtenir",
        "3. Ce qui existe déjà",
        "4. Méthode : la phase 0",
        "5. Plus tard",
        "6. Points d'attention",
    ]
    cadrage = lire(rendu, "docs/cadrage.md")
    assert "- **Statut** : validé à la fusion, puis figé" in cadrage
    assert [t.split(".")[0] for t in titres(cadrage, 2)] == [str(n) for n in range(1, 8)]


def test_semes_declares(rendre):
    copier_yml = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))
    rendus = set()
    for reponses in (
        {},
        REPONSES_SERVEUR,
        {"nom": "essai-donnees", "cible": "donnees"},
        REPONSES_DONNEES_SERVEUR,
    ):
        rendu = rendre(**reponses)
        rendus |= {p.relative_to(rendu).as_posix() for p in rendu.rglob("*") if p.is_file()}
    assert set(copier_yml["_skip_if_exists"]) <= rendus


# Lot 14 : un LICENSE MIT, semé dans tout dépôt de code, au titulaire de la réponse `compte`. Ni un
# dépôt de nature `donnees`, ni la cible `donnees`, même avec une `nature` passée par `--data`.
@pytest.mark.parametrize(
    ("reponses", "titulaire"),
    [
        ({}, "EdouardZemb"),
        ({"compte": "Autre-Compte"}, "Autre-Compte"),
        (REPONSES_SERVEUR_CODE, "EdouardZemb"),
        ({"nature": "donnees"}, None),
        (REPONSES_SERVEUR, None),
        ({"nom": "essai-donnees", "cible": "donnees", "nature": "code"}, None),  # la garde de cible
        (REPONSES_DONNEES_SERVEUR, None),
    ],
)
def test_licence_selon_la_nature(rendre, reponses, titulaire):
    licence = rendre(**reponses) / "LICENSE"
    if titulaire is None:
        assert not licence.exists()
    else:
        texte = licence.read_text(encoding="utf-8")
        assert texte.startswith("MIT License\n\nCopyright (c) 2026 " + titulaire + "\n")
        assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in texte
        # Le texte archivé fait foi, à l'octet près : son empreinte, titulaire remis en variable.
        # Une empreinte, pour qu'un échec n'imprime pas les deux textes.
        gabarit = texte.replace(
            f"Copyright (c) 2026 {titulaire}\n", "Copyright (c) 2026 {{ compte }}\n", 1
        )
        assert hashlib.sha256(gabarit.encode("utf-8")).hexdigest() == (
            "80459fc9ced0428542d09320c70850954d5ef46f1d1ba2dd0ceb02da27634db8"
        )


# `CLAUDE.local.md`, les notes de Claude Code propres au poste, n'entre jamais dans le dépôt : le
# .gitignore semé l'exclut, dans toutes les cibles, et la carte de la racine ne le compte donc pas.
@pytest.mark.parametrize(
    "reponses", [{}, {"nom": "essai-donnees", "cible": "donnees"}], ids=["aucune", "donnees"]
)
def test_claude_local_md_ignore(rendre, env_isole, reponses):
    rendu = rendre(**reponses)
    assert "CLAUDE.local.md" in lire(rendu, ".gitignore").splitlines()
    env = env_isole()
    git(rendu, env, "init", "-q", "-b", "main")
    (rendu / "CLAUDE.local.md").write_text("# Notes du poste\n", encoding="utf-8")
    if (rendu / "LICENSE").exists():
        git(rendu, env, "add", "--", "LICENSE")  # la licence ne compte qu'un LICENSE suivi
    r = subprocess.run(
        [sys.executable, "-B", "scripts/modele/documentation.py"],
        cwd=rendu,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "documentation : carte : 1 fichier .md à la racine, lié" in r.stdout.splitlines()


# Le README semé fait foi à l'octet près : le texte archivé le 05/11, essayé sur un téléphone et
# accepté, est celui du gabarit. Une empreinte, pour qu'un échec n'imprime pas les deux textes.
def test_readme_seme_est_le_gabarit_archive():
    empreinte = hashlib.sha256((RACINE / "template/README.md.jinja").read_bytes()).hexdigest()
    assert empreinte == "570f96113f97683a610e45be092c54c75836feeb5034589f1f4047a5f83ae2c1"


# Lot 12 (M-0006, § 9) : les fichiers de l'instance sont semés. Un projet à un dépôt garde ses clés,
# son .sops.yaml et ses env/ à chaque mise à jour, et le dépôt de données les siens.
def test_instance_semee():
    semes = set(
        yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))["_skip_if_exists"]
    )
    assert {
        ".sops.yaml",
        "deploiement/cles/serveur.pub",
        "deploiement/cles/hors-ligne.pub",
        "cles/serveur.pub",
        "cles/hors-ligne.pub",
        "env/prod.env",
        "env/staging.env",
    } <= semes
