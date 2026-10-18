"""La cible `serveur` : questions, arborescence de départ, secrets exigés."""

import importlib.util
import re

import pytest
import yaml
from conftest import REPONSES_SERVEUR, fichiers_texte

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
