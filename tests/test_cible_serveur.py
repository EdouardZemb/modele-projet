"""La cible `serveur` : questions, arborescence de départ, secrets exigés."""

import importlib.util
import re

import pytest
import yaml
from conftest import RACINE, REPONSES_SERVEUR, fichiers_texte

CLE_SERVEUR = "age1a6ksgqxdj66j5h4f4t6wnhzzghnwc9mdy3q0lresn20sgamnyqus9ksnyg"
CLE_HORS_LIGNE = "age1km9nay02cl0lxfex0qw3al6aa6zqqelg9cv0k39j90lux0h82ysqzjc0ue"


def lire(rendu, chemin):
    return (rendu / chemin).read_text(encoding="utf-8")


def test_questions_serveur_enregistrees(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    reponses = yaml.safe_load(lire(rendu, ".copier-answers.yml"))
    assert reponses["cible"] == "serveur"
    assert reponses["domaine"] == "testlens.dev"
    assert reponses["sous_domaine"] == "essai"
    assert reponses["port_app"] == 3000
    assert reponses["chemin_sante"] == "/api/sante"
    assert reponses["bloc_ports"] == 4310
    assert reponses["sauvegardes"] is True
    assert "prefixe" not in reponses


def test_questions_absentes_en_cible_aucune(rendre):
    reponses = yaml.safe_load(lire(rendre(), ".copier-answers.yml"))
    for question in ("domaine", "sous_domaine", "port_app", "chemin_sante", "bloc_ports", "sauvegardes", "prefixe"):
        assert question not in reponses


@pytest.mark.parametrize("bloc", [4300, 4315, 5000])
def test_bloc_ports_invalide_refuse(rendre, bloc):
    with pytest.raises(Exception, match="bloc"):
        rendre(**{**REPONSES_SERVEUR, "bloc_ports": bloc})


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_arborescence(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    assert (rendu / ".sops.yaml").is_file()
    for chemin in (
        "cles/serveur.pub",
        "cles/hors-ligne.pub",
        "env/prod.env",
        "env/staging.env",
        "compose.yml",
        "projet.env",
        "compose.projet.yml",
        "secrets/prod.cles",
        "secrets/staging.cles",
    ):
        assert (rendu / "deploiement" / chemin).is_file(), chemin
    assert lire(rendu, "deploiement/cles/hors-ligne.pub").strip() == CLE_HORS_LIGNE


def test_pas_de_deploiement_en_cible_aucune(rendre):
    rendu = rendre()
    assert not (rendu / "deploiement").exists()
    assert not (rendu / ".sops.yaml").exists()
    assert not (rendu / "docs/exploitation.md").exists()


def cles(rendu, chemin):
    lignes = lire(rendu, chemin).splitlines()
    return [ligne for ligne in lignes if ligne and not ligne.startswith("#")]


def test_cles_seme(rendre):
    avec = rendre(**REPONSES_SERVEUR)
    assert cles(avec, "deploiement/secrets/prod.cles") == ["HC_SONDE", "HC_SAUVEGARDE", "HC_TEST_RESTAURATION"]
    assert cles(avec, "deploiement/secrets/staging.cles") == ["HC_SONDE"]
    sans = rendre(**{**REPONSES_SERVEUR, "sauvegardes": False})
    assert cles(sans, "deploiement/secrets/prod.cles") == ["HC_SONDE"]
    assert cles(sans, "deploiement/secrets/staging.cles") == ["HC_SONDE"]


def test_projet_env(rendre):
    avec = lire(rendre(**REPONSES_SERVEUR), "deploiement/projet.env")
    assert "SAUVEGARDER=sauvegarder\n" in avec
    assert "VERIFIER=verifier\n" in avec
    sans = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": False}), "deploiement/projet.env")
    assert "SAUVEGARDER" not in sans
    assert "VERIFIER" not in sans


def test_compose_projet(rendre):
    texte = lire(rendre(**REPONSES_SERVEUR), "deploiement/compose.projet.yml")
    assert yaml.safe_load(texte) == {"services": {"app": {}}}
    assert "mem_limit" in texte


def test_env_prod_et_staging(rendre):
    rendu = rendre(**{**REPONSES_SERVEUR, "bloc_ports": 4330})
    assert lire(rendu, "deploiement/env/prod.env").splitlines() == [
        "ESSAI_ENV=prod",
        "ESSAI_PROJET=essai",
        "ESSAI_PORT=4330",
        "ESSAI_URL_PUBLIQUE=https://essai.testlens.dev",
        "ESSAI_CANAL=etiquette",
    ]
    assert lire(rendu, "deploiement/env/staging.env").splitlines() == [
        "ESSAI_ENV=staging",
        "ESSAI_PROJET=essai-staging",
        "ESSAI_PORT=4331",
        "ESSAI_URL_PUBLIQUE=https://essai-staging.testlens.dev",
        "ESSAI_CANAL=main",
    ]


def test_prefixe_avec_tirets(rendre):
    rendu = rendre(**{**REPONSES_SERVEUR, "nom": "mon-projet", "sous_domaine": "mon-projet"})
    assert "MON_PROJET_ENV=prod" in lire(rendu, "deploiement/env/prod.env")


def test_reseau_du_tunnel(rendre):
    doc = yaml.safe_load(lire(rendre(**REPONSES_SERVEUR), "deploiement/compose.yml"))
    assert doc["networks"]["tunnel"] == {"external": True, "name": "tunnel-essai-${ESSAI_ENV}"}
    reseaux = doc["services"]["app"]["networks"]
    assert reseaux["tunnel"]["aliases"] == ["essai-${ESSAI_ENV}"]
    assert "default" in reseaux


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_compose_app(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes, "port_app": 8080})
    doc = yaml.safe_load(lire(rendu, "deploiement/compose.yml"))
    app = doc["services"]["app"]
    assert list(doc["services"]) == ["app"]
    assert app["image"] == "${ESSAI_IMAGE:?}"
    assert app["ports"] == ["127.0.0.1:${ESSAI_PORT:?}:8080"]
    assert ("${ESSAI_SAUVEGARDES:?}:/sauvegardes" in app["volumes"]) is sauvegardes
    assert "${ESSAI_DONNEES:?}:/donnees" in app["volumes"]


def test_sonde_suit_la_branche_principale(rendre):
    """R22 : le canal `main` du staging suit la branche principale ; l'image reste `:main`."""
    rendu = rendre(**{**REPONSES_SERVEUR, "branche_principale": "principal"})
    sonde = lire(rendu, "deploiement/sonder.sh")
    assert 'git -C "$clone" fetch origin principal 9>&-' in sonde
    assert 'git -C "$clone" merge --ff-only origin/principal' in sonde
    assert 'anomalie "git fetch origin principal impossible"' in sonde
    assert 'anomalie "git merge --ff-only origin/principal impossible"' in sonde
    assert "`git fetch origin principal`, `git merge --ff-only origin/principal`" in sonde
    assert "origin/main" not in sonde
    assert "origin main" not in sonde
    # le canal et l'étiquette d'image ne changent pas : la CI publie toujours :main
    assert lire(rendu, "deploiement/env/staging.env").splitlines()[-1] == "ESSAI_CANAL=main"
    assert "    main)\n" in sonde
    assert "image :main" in sonde
    # le banc bats du rendu attend les appels sur cette branche
    bats = lire(rendu, "tests/deploiement/sonder.bats")
    assert '"git -C $CLONE fetch origin principal"' in bats
    assert '"git -C $CLONE merge --ff-only origin/principal"' in bats


def test_pas_de_cloudflared(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    for chemin in fichiers_texte(rendu):
        texte = chemin.read_text(encoding="utf-8")
        assert "cloudflared" not in texte, chemin
        assert "TUNNEL_TOKEN" not in texte, chemin


def test_sops_yaml_destinataires(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    texte = lire(rendu, ".sops.yaml")
    cles_pub = {lire(rendu, f"deploiement/cles/{n}.pub").strip() for n in ("serveur", "hors-ligne")}
    assert cles_pub == {CLE_SERVEUR, CLE_HORS_LIGNE}
    assert set(re.findall(r"age1[0-9a-z]{58}", texte)) == cles_pub
    (regle,) = yaml.safe_load(texte)["creation_rules"]
    assert regle["path_regex"] == r"^deploiement[\\/]secrets[\\/][a-z]+\.env\.enc$"
    assert re.search(regle["path_regex"], "deploiement/secrets/prod.env.enc")
    assert re.search(regle["path_regex"], "deploiement\\secrets\\prod.env.enc")
    assert not re.search(regle["path_regex"], "deploiement/secrets/x/prod.env.enc")
    assert r"[\\/]" in texte.split("creation_rules")[0], "le commentaire doit dire pourquoi [\\/]"


def charger_reglages(rendu):
    spec = importlib.util.spec_from_file_location("reglages_rendu", rendu / "scripts/modele/reglages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_secrets_exiges_rendus(rendre):
    avec = charger_reglages(rendre(**REPONSES_SERVEUR))
    assert avec.SECRETS_EXIGES == {
        "deploiement/secrets/prod.cles": ["HC_SONDE", "HC_SAUVEGARDE", "HC_TEST_RESTAURATION"],
        "deploiement/secrets/staging.cles": ["HC_SONDE"],
    }
    sans = charger_reglages(rendre(**{**REPONSES_SERVEUR, "sauvegardes": False}))
    assert sans.SECRETS_EXIGES == {
        "deploiement/secrets/prod.cles": ["HC_SONDE"],
        "deploiement/secrets/staging.cles": ["HC_SONDE"],
    }
    assert charger_reglages(rendre()).SECRETS_EXIGES == {}


# Le runbook (semé) : les sections génériques de celui d'`ancrage`. Sans sauvegardes, il n'y a
# rien à restaurer ni d'exercice trimestriel.
SECTIONS_EXPLOITATION = [
    "Ce qui tourne",
    "La mise en service",
    "Mettre en ligne",
    "Revenir en arrière",
    "Restaurer",
    "Exercice trimestriel",
    "Secrets",
    "Échéances",
    "Unités",
    "Tout arrêter",
]
SECTIONS_DES_SAUVEGARDES = ("Restaurer", "Exercice trimestriel")


def section(texte, titre):
    return texte.split(f"\n## {titre}\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.parametrize("visibilite", ["public", "prive"])
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_sections(rendre, sauvegardes, visibilite):
    copier_yml = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))
    assert "docs/exploitation.md" in copier_yml["_skip_if_exists"]
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes, "visibilite": visibilite})
    texte = lire(rendu, "docs/exploitation.md")
    assert texte.splitlines()[0] == "# Exploitation"
    attendues = [
        s for s in SECTIONS_EXPLOITATION if sauvegardes or s not in SECTIONS_DES_SAUVEGARDES
    ]
    assert re.findall(r"^## (.+)$", texte, flags=re.MULTILINE) == attendues

    # Le rendu nomme le projet, ses ports et ses unités ; jamais un serveur.
    for fragment in (
        "~/essai/deploiement/",
        "127.0.0.1:4310",
        "127.0.0.1:4311",
        "essai-sonde-prod",
    ):
        assert fragment in texte, fragment
    assert ("essai-sauvegarde" in texte) is sauvegardes
    assert set(re.findall(r"\bssh (\S+ \S+)", texte)) <= {"<le serveur>"}

    # La mise en service : les six étapes, l'étape du paquet GHCR pour un dépôt public.
    mise_en_service = section(texte, "La mise en service")
    assert re.findall(r"^\| (\d) \|", mise_en_service, flags=re.MULTILINE) == list("123456")
    assert ("Change visibility" in mise_en_service) is (visibilite == "public")
    assert ("clé de déploiement" in mise_en_service) is (visibilite == "prive")

    # Revenir en arrière : par étiquette d'abord, `--retour` en secours.
    retour = section(texte, "Revenir en arrière")
    assert retour.index("git tag -a") < retour.index("deployer.sh prod --retour")

    # R23 : avec sauvegardes, la mise en service lance une fois le test de restauration, seul à
    # prouver la clause de l'ENTRYPOINT (M-0003).
    assert ("~/essai/deploiement/tester-restauration.sh prod" in mise_en_service) is sauvegardes
    # R24 : l'instantané d'avant déploiement du staging, où il vit et ce qui le purge
    pre_staging = "~/.local/share/essai/staging/sauvegardes/pre-deploiement/"
    assert (pre_staging in texte) is sauvegardes
    # R24 : l'archive rapatriée se retire après usage ; rien ne prétend qu'aucun fichier n'est posé
    assert "aucune n'y pose de fichier" not in texte
    if sauvegardes:
        assert "rm ~/backups/essai/essai-<horodatage>.tar.age" in section(texte, "Restaurer")

    secrets = section(texte, "Secrets")
    assert "scripts/modele/secrets.ps1 refaire" in secrets
    assert "KeePassXC" in secrets
