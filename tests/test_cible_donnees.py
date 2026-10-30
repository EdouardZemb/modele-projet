"""La cible `donnees` : un dépôt de données, le socle et la méthode, rien de l'application (M-0006)."""

import importlib.util
import re
import subprocess

import pytest
import yaml
from conftest import (
    CLE_HORS_LIGNE_DE_TEST,
    CLE_SERVEUR_DE_TEST,
    RACINE,
    REPONSES_DONNEES_SERVEUR,
    trouver_bash,
)

DONNEES = {"nom": "essai-donnees", "cible": "donnees"}
MODELE_DONNEES = ".github/workflows/modele-donnees.yml"


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


def actions_du_socle():
    """{action: sha} des actions qu'épingle modele-socle.yml : la référence des autres workflows."""
    texte = (RACINE / "template/.github/workflows/modele-socle.yml").read_text(encoding="utf-8")
    return dict(re.findall(r"uses:\s*([^@\s]+)@([0-9a-f]{40})", texte))


# M-0006, § 8 : le dépôt de données d'un projet `serveur` vérifie ses secrets contre le .cles du
# dépôt de code, et ses données contre les images du code.
def test_modele_donnees_yml(rendre):
    (gabarit,) = (RACINE / "template/.github/workflows").glob("*modele-donnees.yml*")
    # il porte des expressions de GitHub : il n'est pas un gabarit Jinja (seul son nom l'est)
    assert gabarit.name.endswith("modele-donnees.yml{% endif %}"), gabarit.name
    texte_gabarit = gabarit.read_text(encoding="utf-8")
    assert "${{" in texte_gabarit
    assert "{%" not in texte_gabarit and "{#" not in texte_gabarit

    rendu = rendre(**REPONSES_DONNEES_SERVEUR)
    texte = (rendu / MODELE_DONNEES).read_text(encoding="utf-8")
    assert texte == texte_gabarit
    assert texte.startswith("# Géré par le modèle — ne pas modifier ici (docs/modele/methode.md).")
    doc = yaml.safe_load(texte)
    assert set(doc.get("on", doc.get(True))) == {"workflow_call"}
    assert doc["permissions"] == {"contents": "read"}
    (job,) = doc["jobs"].values()
    assert job["name"] == "donnees"
    assert job["runs-on"] == "ubuntu-latest"

    # chaque action épinglée par SHA, celui du socle
    socle = actions_du_socle()
    for uses in re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", texte, re.MULTILINE):
        action, _, sha = uses.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", sha), uses
        assert socle.get(action) == sha, uses

    donnees, python, depot, code, secrets, verification = job["steps"]
    assert donnees["uses"].startswith("actions/checkout@")
    assert donnees["with"] == {"fetch-depth": 0, "persist-credentials": False}
    assert python["uses"].startswith("actions/setup-python@")
    assert depot["id"] == "code"
    # le dépôt de code : public, cloné sans jeton gardé, avec ses étiquettes, dans code/
    assert code["uses"].startswith("actions/checkout@")
    assert code["with"] == {
        "repository": "${{ github.repository_owner }}/${{ steps.code.outputs.depot }}",
        "path": "code",
        "fetch-depth": 0,
        "persist-credentials": False,
    }
    assert (
        secrets["run"]
        == "python scripts/modele/verifier_secrets.py --cles code/deploiement/secrets"
    )
    assert verification["run"] == "python scripts/modele/verifier_donnees.py --code code"

    # ci.yml l'appelle, à côté du socle
    ci = yaml.safe_load((rendu / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert set(ci["jobs"]) == {"socle", "donnees"}
    assert ci["jobs"]["donnees"] == {"uses": "./.github/workflows/modele-donnees.yml"}

    # le dépôt de données d'un projet sans serveur ne l'a pas
    sans = rendre(**DONNEES)
    assert not (sans / MODELE_DONNEES).exists()
    ci = yaml.safe_load((sans / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert set(ci["jobs"]) == {"socle"}


def test_modele_donnees_lit_le_depot_de_code_dans_les_reglages(rendre, env_isole, tmp_path):
    """Le nom du dépôt de code n'a qu'une source, DEPOT_CODE de scripts/modele/reglages.py : l'étape
    l'y lit, et refuse un nom qui n'en est pas un."""
    rendu = rendre(**REPONSES_DONNEES_SERVEUR)
    doc = yaml.safe_load((rendu / MODELE_DONNEES).read_text(encoding="utf-8"))
    (job,) = doc["jobs"].values()
    etape = next(e for e in job["steps"] if e.get("id") == "code")
    sortie = tmp_path / "github-output"

    def lancer():
        sortie.write_text("", encoding="utf-8")
        return subprocess.run(
            [trouver_bash(), "--noprofile", "--norc", "-e", "-c", etape["run"]],
            cwd=rendu,
            env={**env_isole(), "GITHUB_OUTPUT": str(sortie).replace("\\", "/")},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    r = lancer()
    assert r.returncode == 0, r.stdout + r.stderr
    assert sortie.read_text(encoding="utf-8").splitlines() == ["depot=essai"]
    reglages = rendu / "scripts/modele/reglages.py"
    for invalide in ('DEPOT_CODE = "../autre"', 'DEPOT_CODE = "essai x"', "DEPOT_CODE = None"):
        texte = re.sub(
            r"^DEPOT_CODE = .*$", invalide, reglages.read_text(encoding="utf-8"), flags=re.MULTILINE
        )
        reglages.write_text(texte, encoding="utf-8")
        r = lancer()
        assert r.returncode != 0, invalide
        assert "DEPOT_CODE" in r.stdout + r.stderr, invalide
        assert sortie.read_text(encoding="utf-8") == "", invalide


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
