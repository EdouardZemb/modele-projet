"""Les fichiers semés : donnés une fois par le modèle, puis propres au projet."""

import re

import yaml
from conftest import RACINE, REGISTRE_ENTETE, REPONSES_SERVEUR


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
    for reponses in ({}, REPONSES_SERVEUR):
        rendu = rendre(**reponses)
        rendus |= {p.relative_to(rendu).as_posix() for p in rendu.rglob("*") if p.is_file()}
    assert set(copier_yml["_skip_if_exists"]) <= rendus
