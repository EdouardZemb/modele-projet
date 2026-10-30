"""La cible `donnees` : un dépôt de données, le socle et la méthode, rien de l'application (M-0006)."""

import importlib.util
import re

import pytest
import yaml
from conftest import CLE_HORS_LIGNE_DE_TEST, CLE_SERVEUR_DE_TEST, REPONSES_DONNEES_SERVEUR

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
        "env",
        "cles",
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


def lire(rendu, chemin):
    return (rendu / chemin).read_text(encoding="utf-8")


# Lot 12 : le dépôt de données d'un projet `serveur` porte son instance (M-0006, § 2), rendue depuis
# ses réponses, au nom du projet (`nom` sans `-donnees`) : env/, .sops.yaml et les clés du parc.
def test_depot_de_donnees_d_un_projet_serveur(rendre):
    rendu = rendre(**REPONSES_DONNEES_SERVEUR)
    assert lire(rendu, "env/prod.env").splitlines() == [
        "ESSAI_ENV=prod",
        "ESSAI_PROJET=essai",
        "ESSAI_PORT=4310",
        "ESSAI_URL_PUBLIQUE=https://essai.exemple.org",
        "ESSAI_CANAL=etiquette",
    ]
    assert lire(rendu, "env/staging.env").splitlines() == [
        "ESSAI_ENV=staging",
        "ESSAI_PROJET=essai-staging",
        "ESSAI_PORT=4311",
        "ESSAI_URL_PUBLIQUE=https://essai-staging.exemple.org",
        "ESSAI_CANAL=main",
        "ESSAI_BRANCHE_DONNEES=main",
    ]
    assert lire(rendu, "cles/serveur.pub") == CLE_SERVEUR_DE_TEST + "\n"
    assert lire(rendu, "cles/hors-ligne.pub") == CLE_HORS_LIGNE_DE_TEST + "\n"
    texte = lire(rendu, ".sops.yaml")
    assert re.findall(r"age1[0-9a-z]{58}", texte) == [CLE_SERVEUR_DE_TEST, CLE_HORS_LIGNE_DE_TEST]
    (regle,) = yaml.safe_load(texte)["creation_rules"]
    assert regle["path_regex"] == r"^secrets[\\/][a-z]+\.env\.enc$"
    assert re.search(regle["path_regex"], "secrets/prod.env.enc")
    assert re.search(regle["path_regex"], "secrets\\staging.env.enc")
    assert not re.search(regle["path_regex"], "deploiement/secrets/prod.env.enc")
    assert "deploiement/" not in texte
    assert not (rendu / "deploiement").exists()
    spec = importlib.util.spec_from_file_location(
        "reglages_donnees", rendu / "scripts/modele/reglages.py"
    )
    reglages = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reglages)
    assert reglages.DEPOT_CODE == "essai"
    assert reglages.NATURE == "donnees"
    reponses = yaml.safe_load(lire(rendu, ".copier-answers.yml"))
    assert reponses["cible_code"] == "serveur"
    assert reponses["sous_domaine"] == "essai"
    assert reponses["bloc_ports"] == 4310
    assert reponses["cle_serveur"] == CLE_SERVEUR_DE_TEST
    assert "prefixe" not in reponses


# P5 : le staging suit la branche principale du dépôt de données, celle de ses réponses.
def test_depot_de_donnees_suit_sa_branche(rendre):
    rendu = rendre(**{**REPONSES_DONNEES_SERVEUR, "branche_principale": "principal"})
    assert lire(rendu, "env/staging.env").splitlines()[-1] == "ESSAI_BRANCHE_DONNEES=principal"


# Sans ses clés, le dépôt de données d'un projet `serveur` ne naît pas.
@pytest.mark.parametrize("question", ["cle_serveur", "cle_hors_ligne"])
@pytest.mark.parametrize("valeur", [None, ""])
def test_depot_de_donnees_sans_cle_refuse(rendre, question, valeur):
    reponses = {cle: v for cle, v in REPONSES_DONNEES_SERVEUR.items() if cle != question}
    if valeur is not None:
        reponses[question] = valeur
    with pytest.raises(Exception, match="clé publique age"):
        rendre(**reponses)


# Sans `cible_code`, un dépôt de données n'a rien de l'instance à donner ; il connaît son code.
def test_depot_de_donnees_sans_cible_code(rendre):
    rendu = rendre(**DONNEES)
    reponses = yaml.safe_load(lire(rendu, ".copier-answers.yml"))
    assert reponses["cible_code"] == "aucune"
    for question in ("domaine", "sous_domaine", "bloc_ports", "cle_serveur", "cle_hors_ligne"):
        assert question not in reponses, question
    assert 'DEPOT_CODE = "essai"' in lire(rendu, "scripts/modele/reglages.py")


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
            "À partir du lot 12 du modèle, ce dossier est monté",
            "à partir du lot 12 du modèle, la chaîne refuse un dossier sans sa commande",
        ],
        "contenu/README.md": [
            "monté en lecture seule sur `/contenu`",
            "en staging comme en prod",
            "version de schéma",
            "À partir du lot 12 du modèle, ce dossier est monté",
            "à partir du lot 12 du modèle, la chaîne refuse un dossier sans sa commande",
        ],
    }
    for fichier, phrases in attendus.items():
        texte = aplati(rendu / fichier)
        for phrase in phrases:
            assert phrase in texte, (fichier, phrase)
        assert "{%" not in texte and "{{" not in texte, fichier


def test_claude_md_du_depot_de_donnees_dit_la_fusion_reelle(rendre):
    session = aplati(rendre(**DONNEES) / "CLAUDE.md")
    assert "Il est en mode `session` par défaut" in session
    assert "mode `edouard`" not in session
    edouard = aplati(rendre(**DONNEES, fusion="edouard") / "CLAUDE.md")
    assert "Il est en mode `edouard` : la session ouvre la PR" in edouard
    assert "Edouard fusionne" in edouard
    assert "mode `session`" not in edouard


def test_ci_du_depot_de_donnees(rendre):
    rendu = rendre(**DONNEES)
    ci = yaml.safe_load((rendu / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert set(ci["jobs"]) == {"socle"}
    assert ci["jobs"]["socle"]["uses"] == "./.github/workflows/modele-socle.yml"
    dependabot = yaml.safe_load((rendu / ".github/dependabot.yml").read_text(encoding="utf-8"))
    assert [u["package-ecosystem"] for u in dependabot["updates"]] == ["github-actions"]


@pytest.mark.parametrize(
    "reponses",
    [{}, {"nom": "essai", "cible": "serveur", "bloc_ports": 4310, "domaine": "exemple.org"}],
)
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
