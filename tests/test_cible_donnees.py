"""La cible `donnees` : un dépôt de données, le socle et la méthode, rien de l'application (M-0006)."""

import pytest
import yaml

DONNEES = {"nom": "essai-donnees", "cible": "donnees"}


def aplati(chemin):
    return " ".join(chemin.read_text(encoding="utf-8").split())


def test_rend_le_socle_et_les_dossiers(rendre):
    rendu = rendre(**DONNEES)
    for chemin in (
        ".githooks/pre-commit",
        "scripts/modele/confidentialite.py",
        ".claude/settings.json",
        ".github/workflows/modele-socle.yml",
        ".github/workflows/modele-historique.yml",
        ".github/workflows/ci.yml",
        ".github/pull_request_template.md",
        "docs/modele/methode.md",
        "docs/modele/decisions/M-0001-ecosysteme-des-applications-personnelles.md",
        "docs/modele/decisions/M-0002-garde-fous-et-confidentialite.md",
        "docs/modele/decisions/M-0006-code-et-donnees.md",
        "config/README.md",
        "contenu/README.md",
        "CLAUDE.md",
        "README.md",
    ):
        assert (rendu / chemin).is_file(), chemin
    reglages = (rendu / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "donnees"' in reglages


def test_la_cible_impose_la_nature(rendre):
    rendu = rendre(nom="essai-donnees", cible="donnees", nature="code")
    reglages = (rendu / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "donnees"' in reglages


def test_ne_rend_rien_de_l_application(rendre):
    rendu = rendre(**DONNEES)
    for chemin in (
        "deploiement",
        "tests",
        "Dockerfile",
        ".sops.yaml",
        "docs/cadrage.md",
        "docs/00-brief-initial.md",
        "docs/pistes.md",
        "docs/registre.md",
        "docs/decisions",
        ".github/ISSUE_TEMPLATE",
        ".claude/skills/consigner",
        ".github/modele/ruleset-main.json",
        "docs/modele/decisions/M-0003-contrat-de-l-image.md",
        "docs/modele/decisions/M-0004-chaine-de-livraison.md",
        "docs/modele/decisions/M-0005-sauvegardes-et-restauration.md",
    ):
        assert not (rendu / chemin).exists(), chemin
    # Git ne suit pas un dossier vide : ce qui compte est qu'aucun fichier de skill n'y soit.
    assert not [p for p in (rendu / ".claude").rglob("SKILL.md")]


def test_nom_sans_suffixe_refuse(rendre):
    with pytest.raises(Exception, match="-donnees"):
        rendre(nom="essai", cible="donnees")


def test_textes_du_depot_de_donnees(rendre):
    rendu = rendre(**DONNEES)
    attendus = {
        "README.md": ["Ce dépôt est le dépôt de données de `essai` : il ne porte aucun code."],
        "CLAUDE.md": [
            "Les leçons de ce dépôt vont au registre du dépôt de code.",
            "Le contenu d'un secret est un geste 👤 d'Edouard.",
            "mode `session` par défaut",
            "avertit sur ce qui identifie",
            "refuse les secrets",
            "(`env/`, secrets, clés) arrive au lot 12",
        ],
        "config/README.md": [
            "monté en lecture seule sur `/config`",
            "jamais en staging",
            "version de schéma",
        ],
        "contenu/README.md": [
            "monté en lecture seule sur `/contenu`",
            "en staging comme en prod",
            "version de schéma",
        ],
    }
    for fichier, phrases in attendus.items():
        texte = aplati(rendu / fichier)
        for phrase in phrases:
            assert phrase in texte, (fichier, phrase)
        assert "{%" not in texte and "{{" not in texte, fichier


def test_ci_du_depot_de_donnees(rendre):
    rendu = rendre(**DONNEES)
    ci = yaml.safe_load((rendu / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert set(ci["jobs"]) == {"socle"}
    assert ci["jobs"]["socle"]["uses"] == "./.github/workflows/modele-socle.yml"
    dependabot = yaml.safe_load((rendu / ".github/dependabot.yml").read_text(encoding="utf-8"))
    assert [u["package-ecosystem"] for u in dependabot["updates"]] == ["github-actions"]


@pytest.mark.parametrize("reponses", [{}, {"nom": "essai", "cible": "serveur", "bloc_ports": 4310, "domaine": "exemple.org"}])
def test_un_autre_rendu_n_a_pas_les_dossiers_de_donnees(rendre, reponses):
    rendu = rendre(**reponses)
    assert not (rendu / "config/README.md").exists()
    assert not (rendu / "contenu/README.md").exists()
    for chemin in (
        "docs/cadrage.md",
        "docs/registre.md",
        "docs/decisions/README.md",
        ".github/ISSUE_TEMPLATE/lot.yml",
        ".claude/skills/consigner/SKILL.md",
    ):
        assert (rendu / chemin).is_file(), chemin
