"""Le rendu du modèle : réponses, validation, gabarits résiduels, fins de ligne."""

import re

import pytest
import yaml
from conftest import fichiers_texte


def test_reponses_enregistrees(rendre):
    rendu = rendre()
    reponses = yaml.safe_load((rendu / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["nom"] == "essai"
    assert reponses["description"] == "Projet d'essai"
    assert reponses["visibilite"] == "public"
    assert reponses["cible"] == "aucune"
    assert reponses["branche_principale"] == "main"
    assert "_commit" in reponses
    assert "_src_path" in reponses


@pytest.mark.parametrize("nom", ["Ancrage", "1projet", "mon_projet", "a b"])
def test_nom_invalide_refuse(rendre, nom):
    with pytest.raises(Exception, match="minuscules"):
        rendre(nom=nom)


def test_aucun_reste_de_gabarit(rendre):
    rendu = rendre()
    fichiers = fichiers_texte(rendu)
    assert fichiers, "aucun fichier rendu : le test passerait à vide"
    for chemin in fichiers:
        assert not chemin.name.endswith(".jinja"), chemin
        texte = chemin.read_text(encoding="utf-8")
        assert "{%" not in texte, chemin
        assert not re.search(r"(?<!\$)\{\{", texte), chemin


def test_fins_de_ligne_lf(rendre):
    rendu = rendre()
    fichiers = fichiers_texte(rendu)
    assert fichiers, "aucun fichier rendu : le test passerait à vide"
    for chemin in fichiers:
        assert b"\r" not in chemin.read_bytes(), chemin
