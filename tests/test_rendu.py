"""Le rendu du modèle : réponses, validation, gabarits résiduels, fins de ligne."""

import re

import pytest
import yaml
from conftest import REPONSES_SERVEUR, fichiers_texte


def test_reponses_enregistrees(rendre):
    rendu = rendre()
    reponses = yaml.safe_load((rendu / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["nom"] == "essai"
    assert reponses["description"] == "Projet d'essai"
    assert reponses["visibilite"] == "public"
    assert reponses["cible"] == "aucune"
    assert reponses["branche_principale"] == "main"
    assert reponses["fusion"] == "session"
    assert "_commit" in reponses
    assert "_src_path" in reponses


def test_fusion_edouard_enregistree(rendre):
    rendu = rendre(fusion="edouard")
    reponses = yaml.safe_load((rendu / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["fusion"] == "edouard"


@pytest.mark.parametrize("nom", ["Ancrage", "1projet", "mon_projet", "a b"])
def test_nom_invalide_refuse(rendre, nom):
    with pytest.raises(Exception, match="minuscules"):
        rendre(nom=nom)


# Un reste de Jinja : `{{` qui n'ouvre ni un `${{` de GitHub ni une action de gabarit Go.
RESTE_DE_JINJA = re.compile(r"(?<!\$)\{\{(?!-?\s*(?:\.|index\b|json\b|range\b|end\b|if\b))")


def test_regex_reste_de_jinja():
    assert RESTE_DE_JINJA.search("image: {{ nom }}")
    assert RESTE_DE_JINJA.search("{{nom}}")
    assert not RESTE_DE_JINJA.search("{{index .RepoDigests 0}}")
    assert not RESTE_DE_JINJA.search("{{ json .State.Health }}")
    assert not RESTE_DE_JINJA.search("${{ secrets.X }}")


@pytest.mark.parametrize("reponses", [{}, REPONSES_SERVEUR], ids=["aucune", "serveur"])
def test_aucun_reste_de_gabarit(rendre, reponses):
    rendu = rendre(**reponses)
    fichiers = fichiers_texte(rendu)
    assert fichiers, "aucun fichier rendu : le test passerait à vide"
    for chemin in fichiers:
        assert not chemin.name.endswith(".jinja"), chemin
        texte = chemin.read_text(encoding="utf-8")
        assert "{%" not in texte, chemin
        assert not RESTE_DE_JINJA.search(texte), chemin


def test_fins_de_ligne_lf(rendre):
    rendu = rendre()
    fichiers = fichiers_texte(rendu)
    assert fichiers, "aucun fichier rendu : le test passerait à vide"
    for chemin in fichiers:
        assert b"\r" not in chemin.read_bytes(), chemin
