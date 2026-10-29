"""Le rendu du modèle : réponses, validation, gabarits résiduels, fins de ligne."""

import json
import re

import garde_claude
import pytest
import yaml
from conftest import RACINE, REPONSES_SERVEUR, fichiers_texte


def test_reponses_enregistrees(rendre):
    rendu = rendre()
    reponses = yaml.safe_load((rendu / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["nom"] == "essai"
    assert reponses["description"] == "Projet d'essai"
    assert reponses["nature"] == "code"
    assert "visibilite" not in reponses
    assert reponses["cible"] == "aucune"
    assert reponses["branche_principale"] == "main"
    assert reponses["fusion"] == "session"
    assert "_commit" in reponses
    assert "_src_path" in reponses


def test_nature_par_defaut_code(rendre):
    rendu = rendre()
    reglages = (rendu / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "code"' in reglages
    assert "VISIBILITE" not in reglages


def test_visibilite_passee_en_donnee_ne_fait_pas_un_depot_de_donnees(rendre):
    """`--data visibilite=prive` (le script du poste) n'est pas une ancienne réponse : un projet
    neuf naît de code (M-0006 § 1). Seule une mise à jour lit l'ancienne réponse."""
    rendu = rendre(visibilite="prive")
    reglages = (rendu / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "code"' in reglages
    reponses = yaml.safe_load((rendu / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["nature"] == "code"


def test_domaine_sans_defaut():
    copier_yml = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))
    assert "default" not in copier_yml["domaine"]


def test_exploitation_sans_visibilite():
    gabarit = RACINE / "template/docs/{% if cible == 'serveur' %}exploitation.md{% endif %}.jinja"
    assert "visibilite" not in gabarit.read_text(encoding="utf-8")


def test_fusion_edouard_enregistree(rendre):
    rendu = rendre(fusion="edouard")
    reponses = yaml.safe_load((rendu / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["fusion"] == "edouard"


@pytest.mark.parametrize(("fusion", "attendu"), [("session", True), ("edouard", False)])
def test_fusion_rendue_lue_par_le_garde(rendre, fusion, attendu):
    # Le garde lit `.copier-answers.yml` tel qu'écrit, octet pour octet : si Copier y mettait un
    # jour des guillemets, tous les projets passeraient en `edouard` sans bruit.
    rendu = rendre(fusion=fusion)
    texte = (rendu / ".copier-answers.yml").read_bytes().decode("utf-8", errors="replace")
    assert bool(garde_claude.REPONSE_SESSION.search(texte)) is attendu, texte


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
    # le format de `docker image inspect` du ménage des images (lot 9)
    assert not RESTE_DE_JINJA.search('{{range .RepoTags}}{{.}} {{end}}')
    assert RESTE_DE_JINJA.search("{{ joindre }}")
    assert not RESTE_DE_JINJA.search("${{ secrets.X }}")


@pytest.mark.parametrize("cible", ["aucune", "serveur"])
def test_settings_porte_garde_et_signaux(rendre, cible):
    reponses = REPONSES_SERVEUR if cible == "serveur" else {}
    doc = json.loads((rendre(**reponses) / ".claude/settings.json").read_text(encoding="utf-8"))
    (groupe,) = doc["hooks"]["SessionStart"]
    assert groupe["matcher"] == "startup|resume"
    (crochet,) = groupe["hooks"]
    assert crochet["type"] == "command" and crochet["timeout"] == 30
    assert (
        crochet["command"]
        == 'sh "$CLAUDE_PROJECT_DIR/scripts/modele/lancer.sh" "$CLAUDE_PROJECT_DIR/scripts/modele/signaux.py"'
    )
    assert "garde_claude.py" in doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


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
