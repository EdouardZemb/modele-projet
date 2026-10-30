"""La cible `serveur` : questions, arborescence de départ, secrets exigés."""

import importlib.util
import itertools
import re
import subprocess
import warnings

import copier
import pytest
import yaml
from conftest import (
    CLE_HORS_LIGNE_DE_TEST,
    CLE_SERVEUR_DE_TEST,
    RACINE,
    REPONSES_SERVEUR,
    REPONSES_SERVEUR_CODE,
    fichiers_texte,
    trouver_bash,
)

# La forme d'une clé publique age : aucun rendu d'un dépôt de code n'en porte (M-0006, § 9).
CLE_AGE = re.compile(r"age1[0-9a-z]{58}")
QUESTIONS_DE_L_INSTANCE = ("domaine", "sous_domaine", "bloc_ports", "cle_serveur", "cle_hors_ligne")


def lire(rendu, chemin):
    return (rendu / chemin).read_text(encoding="utf-8")


def test_questions_serveur_enregistrees(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    reponses = yaml.safe_load(lire(rendu, ".copier-answers.yml"))
    assert reponses["cible"] == "serveur"
    assert reponses["domaine"] == "exemple.org"
    assert reponses["sous_domaine"] == "essai"
    assert reponses["port_app"] == 3000
    assert reponses["chemin_sante"] == "/api/sante"
    assert reponses["bloc_ports"] == 4310
    assert reponses["sauvegardes"] is True
    assert reponses["cle_serveur"] == CLE_SERVEUR_DE_TEST
    assert reponses["cle_hors_ligne"] == CLE_HORS_LIGNE_DE_TEST
    assert "prefixe" not in reponses
    assert "cible_code" not in reponses


def test_questions_absentes_en_cible_aucune(rendre):
    reponses = yaml.safe_load(lire(rendre(), ".copier-answers.yml"))
    for question in (
        "domaine",
        "sous_domaine",
        "port_app",
        "chemin_sante",
        "bloc_ports",
        "sauvegardes",
        "prefixe",
        "cible_code",
        "cle_serveur",
        "cle_hors_ligne",
    ):
        assert question not in reponses


# Lot 12 (M-0006, § 4 et 9) : un dépôt de code `serveur` ne porte rien de l'instance. Ses tests et
# ses scripts gérés sont rendus avec des valeurs d'exemple, qui n'entrent pas dans ses réponses ;
# des clés passées par erreur n'y entrent pas non plus, ni dans aucun fichier.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_depot_de_code_serveur_sans_instance(rendre, sauvegardes):
    rendu = rendre(
        **{
            **REPONSES_SERVEUR_CODE,
            "sauvegardes": sauvegardes,
            "cle_serveur": CLE_SERVEUR_DE_TEST,
            "cle_hors_ligne": CLE_HORS_LIGNE_DE_TEST,
        }
    )
    reponses = yaml.safe_load(lire(rendu, ".copier-answers.yml"))
    assert reponses["nature"] == "code"
    for question in (*QUESTIONS_DE_L_INSTANCE, "cible_code", "prefixe"):
        assert question not in reponses, question
    for chemin in ("deploiement/env", ".sops.yaml", "deploiement/cles"):
        assert not (rendu / chemin).exists(), chemin
    assert (rendu / "deploiement/lib.sh").is_file()
    assert re.findall(r"^MODE_DONNEES=.*$", lire(rendu, "deploiement/lib.sh"), re.MULTILINE) == [
        'MODE_DONNEES="deux"'
    ]
    # Les valeurs d'exemple du rendu : le domaine, le sous-domaine et le bloc de ports.
    banc = lire(rendu, "tests/deploiement/lib.bats")
    assert "https://essai.exemple.org" in banc
    assert '"4310"' in banc
    porteurs = [
        chemin.relative_to(rendu).as_posix()
        for chemin in fichiers_texte(rendu)
        if CLE_AGE.search(chemin.read_bytes().decode("utf-8", errors="replace"))
    ]
    assert porteurs == []


# Le mode à un dépôt : un projet de nature `donnees` garde son instance, rendue depuis ses réponses.
def test_depot_a_un_depot_garde_son_instance(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    assert lire(rendu, "deploiement/env/prod.env").splitlines() == [
        "ESSAI_ENV=prod",
        "ESSAI_PROJET=essai",
        "ESSAI_PORT=4310",
        "ESSAI_URL_PUBLIQUE=https://essai.exemple.org",
        "ESSAI_CANAL=etiquette",
    ]
    assert "ESSAI_PORT=4311" in lire(rendu, "deploiement/env/staging.env").splitlines()
    assert lire(rendu, "deploiement/cles/serveur.pub") == CLE_SERVEUR_DE_TEST + "\n"
    assert lire(rendu, "deploiement/cles/hors-ligne.pub") == CLE_HORS_LIGNE_DE_TEST + "\n"
    assert CLE_AGE.findall(lire(rendu, ".sops.yaml")) == [
        CLE_SERVEUR_DE_TEST,
        CLE_HORS_LIGNE_DE_TEST,
    ]
    assert re.findall(r"^MODE_DONNEES=.*$", lire(rendu, "deploiement/lib.sh"), re.MULTILINE) == [
        'MODE_DONNEES="un"'
    ]


# Les clés du parc d'un projet à un dépôt : une clé publique age, ou rien (le projet garde alors les
# siennes, semées). Une autre forme est refusée.
@pytest.mark.parametrize("question", ["cle_serveur", "cle_hors_ligne"])
@pytest.mark.parametrize(
    "cle", ["age1abc", "AGE1" + "q" * 58, "age1" + "q" * 59, "ssh-ed25519 AAAA"]
)
def test_cle_du_parc_invalide_refusee(rendre, question, cle):
    with pytest.raises(Exception, match="clé publique age"):
        rendre(**{**REPONSES_SERVEUR, question: cle})


def test_cles_du_parc_vides_permises_a_un_depot(rendre):
    rendu = rendre(**{**REPONSES_SERVEUR, "cle_serveur": "", "cle_hors_ligne": ""})
    reponses = yaml.safe_load(lire(rendu, ".copier-answers.yml"))
    assert reponses["cle_serveur"] == "" and reponses["cle_hors_ligne"] == ""
    assert (rendu / ".sops.yaml").is_file()
    assert (rendu / "deploiement/cles/serveur.pub").is_file()


# Le test de restauration lit le port de la prod dans son env : un dépôt de code le rend sans bloc.
def test_test_de_restauration_sans_bloc_rendu(rendre):
    script = lire(rendre(**REPONSES_SERVEUR_CODE), "deploiement/tester-restauration.sh")
    assert "4310" not in script
    assert "4319" not in script
    gabarit = RACINE / (
        "template/{% if cible == 'serveur' %}deploiement{% endif %}"
        "/{% if sauvegardes %}tester-restauration.sh{% endif %}.jinja"
    )
    assert "bloc_ports" not in gabarit.read_text(encoding="utf-8")


@pytest.mark.parametrize("bloc", [4300, 4315, 5000])
def test_bloc_ports_invalide_refuse(rendre, bloc):
    with pytest.raises(Exception, match="bloc"):
        rendre(**{**REPONSES_SERVEUR, "bloc_ports": bloc})


# chemin_sante est interpolé entre guillemets dans lib.sh et dans les motifs de `case` du faux
# curl : un `$`, un `"`, un accent grave ou un `;` y serait du shell.
@pytest.mark.parametrize("chemin", ["/a$b", '/a"b', "/a`b", "/a;b", "/a b", "sante", ""])
def test_chemin_sante_invalide_refuse(rendre, chemin):
    with pytest.raises(Exception, match="chemin"):
        rendre(**{**REPONSES_SERVEUR, "chemin_sante": chemin})


@pytest.mark.parametrize("chemin", ["/api/sante", "/sante-1.2", "/a_b/C9"])
def test_chemin_sante_admis(rendre, chemin):
    rendu = rendre(**{**REPONSES_SERVEUR, "chemin_sante": chemin})
    assert yaml.safe_load(lire(rendu, ".copier-answers.yml"))["chemin_sante"] == chemin


def test_sous_domaine_vide_refuse(rendre):
    with pytest.raises(Exception, match="sous-domaine"):
        rendre(**{**REPONSES_SERVEUR, "sous_domaine": ""})


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
    assert lire(rendu, "deploiement/cles/hors-ligne.pub").strip() == CLE_HORS_LIGNE_DE_TEST


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
    # C0 : les deux clés du report sont facultatives : en commentaire, avec un exemple
    assert "#REPORTER=reporter\n" in avec
    assert "#REPORTER_SECTION=Reporter à la main\n" in avec
    assert not re.search(r"^REPORTER", avec, flags=re.MULTILINE)
    sans = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": False}), "deploiement/projet.env")
    assert "SAUVEGARDER" not in sans
    assert not re.search(r"^#?VERIFIER=", sans, flags=re.MULTILINE)
    assert "REPORTER" not in sans


# Lot 12 (M-0006, § 5) : les deux commandes de l'instance, en commentaire, avec leur contrat et le
# dossier qui va avec chacune, dans chaque mode, avec ou sans sauvegardes.
@pytest.mark.parametrize("sauvegardes", [True, False])
@pytest.mark.parametrize(
    "reponses, config, contenu",
    [
        (REPONSES_SERVEUR_CODE, "`config/`", "`contenu/`"),
        (REPONSES_SERVEUR, "`instance/config/`", "`instance/contenu/`"),
    ],
    ids=["deux-depots", "un-depot"],
)
def test_projet_env_dit_les_commandes_de_l_instance(rendre, reponses, config, contenu, sauvegardes):
    texte = lire(rendre(**{**reponses, "sauvegardes": sauvegardes}), "deploiement/projet.env")
    assert "#VERIFIER_CONFIG=verifier-config\n" in texte
    assert "#VERIFIER_CONTENU=verifier-contenu\n" in texte
    assert not re.search(r"^VERIFIER_CON", texte, flags=re.MULTILINE)
    plat = a_plat(" ".join(ligne.lstrip("#") for ligne in texte.splitlines()))
    for fragment in (
        config,
        contenu,
        "`<VERIFIER_CONFIG…> /config`",
        "jamais en staging",
        "`<VERIFIER_CONTENU…> /contenu`",
        "/en-service",
        "sans réseau",
        "lecture seule",
        "0 conforme, 2 non conforme, 64 usage, tout autre code refuse",
        "refuse le déploiement",
        "Un dossier qui ne porte que son README.md compte comme absent",
    ):
        assert fragment in plat, fragment


# C0 : le crochet de restauration reste générique. Ni la base d'un projet, ni un projet, ni son
# registre dans la mécanique : seuls les exemples des docs parlent d'un registre de suppressions.
def test_crochet_reporter_generique(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    for chemin in (
        "deploiement/restaurer.sh",
        "deploiement/tester-restauration.sh",
        "deploiement/lib.sh",
        "deploiement/projet.env",
        "tests/deploiement/sauvegarde.bats",
        "tests/deploiement/doubles/docker",
    ):
        texte = lire(rendu, chemin)
        assert "REPORTER" in texte or chemin == "deploiement/lib.sh", chemin
        assert not re.search(r"sqlite|\bregistre\b|ancrage", texte, flags=re.IGNORECASE), chemin


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
        "ESSAI_URL_PUBLIQUE=https://essai.exemple.org",
        "ESSAI_CANAL=etiquette",
    ]
    assert lire(rendu, "deploiement/env/staging.env").splitlines() == [
        "ESSAI_ENV=staging",
        "ESSAI_PROJET=essai-staging",
        "ESSAI_PORT=4331",
        "ESSAI_URL_PUBLIQUE=https://essai-staging.exemple.org",
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


def test_en_tete_du_compose_decrit_l_appel_de_dc(rendre):
    # L'en-tête donne l'appel que fait `dc` (lib.sh) : les deux fichiers, et le compose.env écrit
    # par le déploiement, pas un fichier de deploiement/env/.
    texte = lire(rendre(**REPONSES_SERVEUR), "deploiement/compose.yml")
    commentaires = itertools.takewhile(lambda ligne: ligne.startswith("#"), texte.splitlines())
    # Sans les « # » ni les « \ » de fin de ligne : l'appel peut tenir sur plusieurs lignes.
    entete = a_plat(" ".join(ligne.lstrip("#").rstrip("\\ ") for ligne in commentaires))
    appel = (
        "docker compose -p <projet> -f <clone>/deploiement/compose.yml"
        " -f <clone>/deploiement/compose.projet.yml --env-file <état>/compose.env"
    )
    assert appel in entete, entete
    assert "~/.local/state/essai/<env>" in entete
    assert "--env-file deploiement/env/" not in entete
    # Lot 12 : les montages de l'instantané, que `dc` ajoute d'après compose.env.
    assert "`dc` ajoute après eux -f <clone>/deploiement/compose.config.yml" in entete, entete
    assert "-f <clone>/deploiement/compose.contenu.yml" in entete, entete


# Lot 12 (M-0006, § 5) : les montages de l'instantané, gérés, chacun en lecture seule sur son point
# de montage, d'après le chemin que compose.env leur donne.
@pytest.mark.parametrize(
    "reponses", [REPONSES_SERVEUR_CODE, REPONSES_SERVEUR], ids=["deux-depots", "un-depot"]
)
def test_compose_de_montage(rendre, reponses):
    rendu = rendre(**reponses)
    for nom in ("config", "contenu"):
        doc = yaml.safe_load(lire(rendu, f"deploiement/compose.{nom}.yml"))
        assert doc == {"services": {"app": {"volumes": [f"${{ESSAI_{nom.upper()}:?}}:/{nom}:ro"]}}}
    copier_yml = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))
    for nom in ("config", "contenu"):
        assert f"deploiement/compose.{nom}.yml" not in copier_yml["_skip_if_exists"]


# Lot 12 (M-0006, § 6) : les chemins de l'instance sont définis dans lib.sh seulement, d'après le
# mode ; aucun script n'écrit en dur un chemin de l'env, des secrets, des clés ou de l'instance. La
# sauvegarde lit la clé hors ligne dans le clone des données.
@pytest.mark.parametrize(
    "reponses", [REPONSES_SERVEUR_CODE, REPONSES_SERVEUR], ids=["deux-depots", "un-depot"]
)
def test_chemins_de_l_instance_dans_lib_seulement(rendre, reponses):
    rendu = rendre(**reponses)
    definition = re.compile(r"^\s*(SOUS_DOSSIER_[A-Z]+)=", re.MULTILINE)
    en_dur = re.compile(r"CLONE(?:_DONNEES)?\}?/(?:deploiement/(?:env|secrets|cles)|instance)\b")
    noms = {f"SOUS_DOSSIER_{n}" for n in ("ENV", "SECRETS", "CLES", "CONFIG", "CONTENU")}
    for chemin in sorted((rendu / "deploiement").rglob("*.sh")):
        texte = chemin.read_text(encoding="utf-8")
        assert not en_dur.search(texte), chemin
        attendus = noms if chemin.name == "lib.sh" else set()
        assert set(definition.findall(texte)) == attendus, chemin
    sauvegarde = lire(rendu, "deploiement/sauvegarder.sh")
    assert 'local cle="$ESSAI_CLONE_DONNEES/$SOUS_DOSSIER_CLES/hors-ligne.pub"' in sauvegarde


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


# Lot 9 : le dépôt GHCR du projet est défini une seule fois, dans lib.sh, et la sonde comme le
# ménage des images s'en servent. Seule une ligne qui commence par `DEPOT_IMAGE=` le définit :
# l'usage et les commentaires citent la variable de test, `ESSAI_DEPOT_IMAGE=…`.
def test_depot_image_defini_une_seule_fois(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    definition = re.compile(r"^DEPOT_IMAGE=.*$", re.MULTILINE)
    assert definition.findall(lire(rendu, "deploiement/lib.sh")) == ["DEPOT_IMAGE=ghcr.io/edouardzemb/essai"]
    for chemin in ("deploiement/sonder.sh", "deploiement/nettoyer-images.sh"):
        texte = lire(rendu, chemin)
        assert not definition.search(texte), chemin
        assert "$DEPOT_IMAGE" in texte, chemin
    for chemin in sorted((rendu / "deploiement").rglob("*.sh")):
        if chemin.name != "lib.sh":
            assert not definition.search(chemin.read_text(encoding="utf-8")), chemin


# Lot 9 (R13) : la forme de l'état et sa lecture sont définies une seule fois, dans lib.sh.
# deployer.sh, qui écrit l'état, nettoyer-images.sh et lire_deploye, qui le relisent, s'en
# servent : une forme nouvelle que deployer.sh accepterait vaudrait aussi pour le ménage, qui ne
# s'annulerait pas, en silence, à chaque passage. Ni copie des motifs, ni motif en ligne.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_motifs_de_l_etat_definis_une_seule_fois(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    definitions = {
        "MOTIF_REFERENCE": re.compile(r"^MOTIF_REFERENCE=", re.MULTILINE),
        "MOTIF_VERSION": re.compile(r"^MOTIF_VERSION=", re.MULTILINE),
        "MOTIF_COMMIT": re.compile(r"^MOTIF_COMMIT=", re.MULTILINE),
        "lire_version": re.compile(r"^\s*(?:function\s+)?lire_version\s*\(\)", re.MULTILINE),
        # le motif de la référence en toutes lettres, en ligne comme dans une définition
        "motif en ligne": re.compile(re.escape("[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}")),
    }
    trouvees = {nom: [] for nom in definitions}
    for chemin in sorted((rendu / "deploiement").rglob("*.sh")):
        texte = chemin.read_text(encoding="utf-8")
        for nom, motif in definitions.items():
            trouvees[nom] += [chemin.name] * len(motif.findall(texte))
    assert trouvees == {nom: ["lib.sh"] for nom in definitions}
    lib = lire(rendu, "deploiement/lib.sh")
    assert '[[ "$DEPLOYE_IMAGE" =~ $MOTIF_REFERENCE ]]' in lib
    for chemin in ("deploiement/deployer.sh", "deploiement/nettoyer-images.sh"):
        texte = lire(rendu, chemin)
        assert "$MOTIF_REFERENCE" in texte, chemin
        assert re.search(r"^\s*(?:if )?lire_version ", texte, re.MULTILINE), chemin
    assert "$MOTIF_VERSION" in lire(rendu, "deploiement/deployer.sh")


# Review Focus 2 du lot 12 (M-0004, amendé) : un retour par une étiquette du code vers une version
# d'avant la v0.7.0 relit l'état que la v0.7.0 écrit. deploye et precedent y ont un troisième champ,
# le commit de données, et echec un second : les scripts de la v0.6.0 n'en lisent que les premiers,
# lib.sh (lire_version, lire_deploye), sonder.sh (deploye, echec) et nettoyer-images.sh (lire_etat).
# Le rendu de la v0.6.0 porte de vraies clés publiques : aucun de ses fichiers n'est imprimé ni
# comparé comme du texte ; seule la sortie des lectures, faite des valeurs du test, l'est.
LECTURE_D_ECHEC = re.compile(
    r'^\s*(\{ read -r en_echec _ \|\| true; \} <"\$etat/echec")$', re.MULTILINE
)
LECTURE_DE_DEPLOYE = re.compile(
    r'^\s*(\{ read -r deployee version_deployee _ \|\| true; \} <"\$etat/deploye")$',
    re.MULTILINE,
)
# nettoyer-images.sh lit deploye et precedent par lire_version, echec par `read -r image _`.
LIRE_ETAT = re.compile(r"^(lire_etat\(\) \{\n.*?\n\})$", re.MULTILINE | re.DOTALL)


def test_un_couple_se_lit_par_les_scripts_de_la_v0_6_0(tmp_path):
    reponses = {
        cle: valeur for cle, valeur in REPONSES_SERVEUR.items() if not cle.startswith("cle_")
    }
    rendu = tmp_path / "v0.6.0"
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=copier.errors.DirtyLocalWarning)
        copier.run_copy(
            str(RACINE), rendu, data=reponses, vcs_ref="v0.6.0", defaults=True, quiet=True
        )
    image = "ghcr.io/exemple/essai@sha256:" + "1" * 64
    precedente = "ghcr.io/exemple/essai@sha256:" + "2" * 64
    commit = "0123456789abcdef0123456789abcdef01234567"
    etat = tmp_path / "etat"
    etat.mkdir()
    for nom, ligne in (
        ("deploye", f"{image} 0.2.0 {commit}"),
        ("precedent", f"{precedente} 0.1.0 -"),
        ("echec", f"{image} {commit}"),
    ):
        (etat / nom).write_text(ligne + "\n", encoding="utf-8", newline="\n")
    sonder = (rendu / "deploiement/sonder.sh").read_text(encoding="utf-8")
    lecture = LECTURE_D_ECHEC.search(sonder)
    assert lecture is not None, "sonder.sh de la v0.6.0 ne lit plus echec par read -r en_echec _"
    lecture_deploye = LECTURE_DE_DEPLOYE.search(sonder)
    assert lecture_deploye is not None, "sonder.sh de la v0.6.0 ne lit plus deploye par read -r"
    nettoyer = (rendu / "deploiement/nettoyer-images.sh").read_text(encoding="utf-8")
    lire_etat = LIRE_ETAT.search(nettoyer)
    assert lire_etat is not None, "nettoyer-images.sh de la v0.6.0 n'a plus lire_etat"
    script = "\n".join(
        (
            "set -euo pipefail",
            ". deploiement/lib.sh",
            'ESSAI_ETAT="$1"',
            'lire_version "$ESSAI_ETAT/deploye"',
            'echo "deploye $IMAGE_LUE $VERSION_LUE"',
            'lire_version "$ESSAI_ETAT/precedent"',
            'echo "precedent $IMAGE_LUE $VERSION_LUE"',
            "lire_deploye",
            'echo "lire_deploye $DEPLOYE_IMAGE $DEPLOYE_VERSION"',
            'etat="$ESSAI_ETAT" en_echec=""',
            lecture.group(1),
            'echo "echec $en_echec"',
            'deployee="" version_deployee=""',
            lecture_deploye.group(1),
            'echo "sonder $deployee $version_deployee"',
            "declare -A NOMMEE=()",
            'annuler() { echo "annuler $*"; exit 1; }',
            lire_etat.group(1),
            'lire_etat "$ESSAI_ETAT"',
            'printf "nettoyer %s\\n" "${!NOMMEE[@]}" | sort',
        )
    )
    r = subprocess.run(
        [trouver_bash(), "--noprofile", "--norc", "-c", script, "bash", etat.as_posix()],
        cwd=rendu,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == [
        f"deploye {image} 0.2.0",
        f"precedent {precedente} 0.1.0",
        f"lire_deploye {image} 0.2.0",
        f"echec {image}",
        f"sonder {image} 0.2.0",
        f"nettoyer {image}",
        f"nettoyer {precedente}",
    ]


# Lot 12 (M-0006, § 6) : l'en-tête et les messages de deployer.sh disent où est l'env de
# l'environnement dans chaque mode, et son usage dit le couple, l'option --commit-donnees.
@pytest.mark.parametrize(
    "reponses, env",
    [
        (REPONSES_SERVEUR_CODE, "env/<env>.env du clone des données"),
        (REPONSES_SERVEUR, "deploiement/env/<env>.env"),
    ],
    ids=["deux-depots", "un-depot"],
)
def test_deployer_dit_l_env_de_son_mode_et_le_couple(rendre, reponses, env):
    texte = lire(rendre(**reponses), "deploiement/deployer.sh")
    entete = "\n".join(en_tete(texte))
    assert env in entete
    if reponses["nature"] == "code":
        assert "deploiement/env/" not in texte
    synopsis = "bash deploiement/deployer.sh <prod|staging> <image@sha256:…> <version>"
    options = "[--commit-donnees <sha>] [--donnees-neuves]"
    assert f"#   {synopsis} {options}" in entete
    assert f'"usage : {synopsis} {options} | ' in texte


# Les scripts de deploiement/ sont enregistrés exécutables (100755), comme deployer.sh : un projet
# né du modèle les reçoit ainsi, quel que soit le poste qui l'a créé.
def test_scripts_de_deploiement_executables_dans_l_index():
    dossier = "template/{% if cible == 'serveur' %}deploiement{% endif %}"
    sortie = subprocess.run(
        ["git", "ls-files", "-s", "-z", "--", dossier],
        cwd=RACINE,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    modes = {}
    for entree in filter(None, sortie.split("\0")):
        infos, chemin = entree.split("\t", 1)
        nom = re.sub(r"\{%.*?%\}", "", chemin.rsplit("/", 1)[-1])
        if nom.endswith(".sh.jinja"):
            modes[nom] = infos.split()[0]
    assert {"deployer.sh.jinja", "lib.sh.jinja", "nettoyer-images.sh.jinja"} <= set(modes), modes
    assert {nom: mode for nom, mode in modes.items() if mode != "100755"} == {}


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
    assert cles_pub == {CLE_SERVEUR_DE_TEST, CLE_HORS_LIGNE_DE_TEST}
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
    "Les images",
    "Débloquer un déploiement",
    "Restaurer",
    "Exercice trimestriel",
    "Secrets",
    "Échéances",
    "Unités",
    "Tout arrêter",
]
SECTIONS_DES_SAUVEGARDES = ("Débloquer un déploiement", "Restaurer", "Exercice trimestriel")


def section(texte, titre):
    return texte.split(f"\n## {titre}\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_dit_le_menage(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    images = section(lire(rendu, "docs/exploitation.md"), "Les images")
    assert "bash ~/essai/deploiement/nettoyer-images.sh prod" in images
    assert "les 3 plus récentes" in images
    # R5 : le retrait des images à plusieurs étiquettes, sans jamais -f
    assert "docker image rm <dépôt>:<étiquette>" in images
    assert "jamais `-f`" in images
    m0004 = lire(rendu, "docs/modele/decisions/M-0004-chaine-de-livraison.md")
    assert "nettoyer-images.sh" in m0004
    # Sauté dès que l'autre environnement tient son verrou : sa sonde à chaque passage, et la
    # sauvegarde ou la restauration de la prod, dans le seul rendu qui en a.
    plat = a_plat(images)
    assert "un passage de sa sonde" in plat
    assert ("une sauvegarde ou une restauration" in plat) is sauvegardes
    # Où lire un ménage sauté, annulé ou en échec : le journal de l'unité de la sonde, et le bilan.
    assert "journalctl --user -u essai-sonde-prod" in plat
    assert "`essai-sonde-staging`" in plat
    assert "`ménage des images : <n> retirées, <n> gardées (…)`" in plat
    assert "`ménage des images sauté : …`" in plat
    # R15 : le ménage suppose le magasin d'images classique ; containerd n'est pas vérifié.
    assert "magasin classique" in plat
    assert "Son comportement avec le magasin containerd n'est pas vérifié." in plat


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_dit_la_garde_des_donnees(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    runbook = lire(rendu, "docs/exploitation.md")
    geste = "bash ~/essai/deploiement/deployer.sh prod <image@sha256:…> <X.Y.Z> --donnees-neuves"
    geste_staging = (
        "bash ~/essai-staging/deploiement/deployer.sh staging <image@sha256:…> main"
        " --donnees-neuves"
    )
    # Aucun gabarit de préfixe : le rendu nomme la variable du projet.
    assert "<PREFIXE>" not in runbook
    if not sauvegardes:
        assert "--donnees-neuves" not in runbook
        return
    plat = a_plat(section(runbook, "Débloquer un déploiement"))
    assert geste in plat
    assert geste_staging in plat
    assert "dossier de données vide" in plat
    assert "dossier de données changé" in plat
    # La limite du § 2.6 : une racine de l'état déplacée passe pour un premier déploiement.
    assert "racine de l'état" in plat
    assert "journalctl --user -u essai-sonde-<env>" in plat
    # Des données vraiment perdues se restaurent : la restauration ne passe pas par la garde.
    assert "« Restaurer »" in plat
    m0005 = a_plat(lire(rendu, "docs/modele/decisions/M-0005-sauvegardes-et-restauration.md"))
    assert "--donnees-neuves" in m0005
    assert "racine de l'état" in m0005
    # La référence est le chemin canonique du dernier succès : un lien repointé est vu.
    assert "canonique" in m0005


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_sections(rendre, sauvegardes):
    copier_yml = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))
    assert "docs/exploitation.md" in copier_yml["_skip_if_exists"]
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
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
    assert "Change visibility" in mise_en_service
    assert "clé de déploiement" in mise_en_service

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


# I1 : un projet né sous Windows enregistre ses scripts sans bit d'exécution (100644). Un geste qui
# lance `~/<nom>/deploiement/<script>` directement répond « Permission denied », au moment d'un
# secours. Le runbook, les en-têtes et les usages des scripts les lancent donc par `bash`, comme les
# unités et la CI.
CHEMIN_DE_SCRIPT = re.compile(r"[^\s'\"`(]*deploiement/(?:ci/)?[a-z][a-z-]*\.sh\b")
NOM_DE_SCRIPT = re.compile(r"[^\s'\"`(]*\b[a-z][a-z-]*\.sh\b")
# La ligne de synopsis d'un en-tête : « #   <script>.sh <arguments> ».
SYNOPSIS = re.compile(r"#   [\w~./<>-]*\.sh(?: |$)")
USAGES = re.compile(r'USAGE="((?:[^"\\]|\\.)*)"|"(usage : (?:[^"\\]|\\.)*)"', re.DOTALL)


def sans_bash(texte, motif):
    """Les appels de script (le motif) que `bash ` ne précède pas, le chemin entre guillemets ou non."""
    return [
        m.group(0)
        for m in motif.finditer(texte)
        if not texte[: m.start()].rstrip("\"'").endswith("bash ")
    ]


def en_tete(script):
    """Les lignes de commentaire du début d'un script, après le shebang."""
    return list(itertools.takewhile(lambda ligne: ligne.startswith("#"), script.splitlines()[1:]))


def a_plat(texte):
    """Le texte sur une ligne, les blancs réduits à une espace : les retours à la ligne du
    Markdown ne comptent pas."""
    return " ".join(texte.split())


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_scripts_lances_par_bash(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    runbook = lire(rendu, "docs/exploitation.md")
    fautes = [f"docs/exploitation.md : {a}" for a in sans_bash(runbook, CHEMIN_DE_SCRIPT)]
    scripts = sorted((rendu / "deploiement").rglob("*.sh"))
    assert len(scripts) >= 6, scripts
    for chemin in scripts:
        nom = chemin.relative_to(rendu).as_posix()
        texte = chemin.read_text(encoding="utf-8")
        # tout chemin de script, dans un commentaire comme dans un message, hors directive shellcheck
        code = "\n".join(
            ligne for ligne in texte.splitlines() if not ligne.startswith("# shellcheck source=")
        )
        fautes += [f"{nom} : {a}" for a in sans_bash(code, CHEMIN_DE_SCRIPT)]
        # le synopsis de l'en-tête
        synopsis = [ligne for ligne in en_tete(texte) if SYNOPSIS.match(ligne)]
        fautes += [f"{nom} : en-tête « {ligne} »" for ligne in synopsis]
        # les usages, chaque forme comprise
        for m in USAGES.finditer(texte):
            usage = m.group(1) or m.group(2)
            fautes += [f"{nom} : usage {a}" for a in sans_bash(usage, NOM_DE_SCRIPT)]
    assert not fautes, "\n".join(fautes)


# m1 : l'en-tête et l'usage de restaurer.sh donnent la forme du runbook, la clé hors ligne collée
# dans `read -rs` puis passée par l'entrée standard, jamais un fichier en clair du poste.
def test_restaurer_ne_garde_pas_la_cle_hors_ligne_dans_un_fichier(rendre):
    texte = lire(rendre(**REPONSES_SERVEUR), "deploiement/restaurer.sh")
    usage = USAGES.search(texte).group(1)
    for partie in ("\n".join(en_tete(texte)), usage):
        assert "hors-ligne.txt" not in partie
        assert "read -rs CLE" in partie
        assert "| ssh <le serveur> 'bash ~/essai/deploiement/restaurer.sh prod " in partie
        assert "--cle /dev/stdin" in partie
        assert "unset CLE" in partie


# I4 (R30) : un instantané impossible (une app qui redémarre en boucle) bloque tout déploiement,
# retour compris, puisque tous deux le prennent d'abord. Le runbook donne le geste : arrêter l'app,
# avec les fichiers, le fichier d'environnement et le projet que compose `dc` (lib.sh) ; la sonde
# suivante déploie sans instantané. Sans sauvegardes, pas d'instantané, donc pas de section.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_debloquer_un_deploiement(rendre, sauvegardes):
    texte = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes}), "docs/exploitation.md")
    assert ("Débloquer un déploiement" in texte) is sauvegardes
    if not sauvegardes:
        return
    debloquer = a_plat(section(texte, "Débloquer un déploiement"))
    environnements = (("prod", "essai", "~/essai"), ("staging", "essai-staging", "~/essai-staging"))
    for env, projet, clone in environnements:
        geste = (
            f"docker compose -p {projet} -f {clone}/deploiement/compose.yml"
            f" -f {clone}/deploiement/compose.projet.yml"
            f" --env-file ~/.local/state/essai/{env}/compose.env stop app"
        )
        assert geste in debloquer, geste
    assert "pas d'instantané" in debloquer
    assert "la nuit" in debloquer
    assert "bash ~/essai/deploiement/deployer.sh prod --retour" in debloquer
    # renvoyée par l'instantané qui échoue, et par le retour en arrière
    renvoi = "« Débloquer un déploiement »"
    mettre_en_ligne = a_plat(section(texte, "Mettre en ligne"))
    assert renvoi in mettre_en_ligne.split("S'il échoue, rien ne change", 1)[1]
    assert renvoi in a_plat(section(texte, "Revenir en arrière"))


# m11 : après `--retour`, la sonde attend une nouvelle image. Une étiquette neuve sur le même commit
# donne la même image, à la même empreinte, toujours en échec : la sonde attendrait en silence.
def test_exploitation_le_retour_attend_une_nouvelle_image(rendre):
    texte = lire(rendre(**REPONSES_SERVEUR), "docs/exploitation.md")
    retour = a_plat(section(texte, "Revenir en arrière"))
    assert "attend une nouvelle étiquette" not in retour
    assert "attend une nouvelle image" in retour
    assert "même empreinte" in retour
    assert "un nouveau commit" in retour
    # le seul geste des scripts qui efface la marque : un déploiement réussi de cette image
    assert "bash ~/essai/deploiement/deployer.sh prod <image@sha256:…> <X.Y.Z>" in retour
    assert "~/.local/state/essai/prod/echec" in retour


# m12 : l'ancien contenu des données est déplacé par la restauration, et effacé par la rétention
# après 30 jours. C'est parfois la seule copie de ce qui a changé depuis la dernière nuit.
def test_exploitation_avant_restauration(rendre):
    restaurer = a_plat(section(lire(rendre(**REPONSES_SERVEUR), "docs/exploitation.md"), "Restaurer"))
    assert "jamais supprimé, et la sauvegarde l'efface" not in restaurer
    assert "avant-restauration-<horodatage>/" in restaurer
    assert "30 jours" in restaurer
    assert "seule copie" in restaurer


# R61 (I1 de la revue de la partie B) : la sonde de `serveur` ne réinstalle que des unités absentes
# ou différentes de leur rendu ; une surcharge ou une unité masquée est une anomalie, et elle ne
# supprime jamais rien. La sonde de prod, elle, alerte sur tout écart, et la version suivante
# réinstalle.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_unites_et_sonde_de_serveur(rendre, sauvegardes):
    texte = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes}), "docs/exploitation.md")
    unites = a_plat(section(texte, "Unités"))
    for fragment in (
        "alerte au moindre écart (« unités divergentes »)",
        "ne réinstalle que des unités absentes ou différentes de leur rendu",
        "des heures changées dans `projets/essai.env`",
        "**Une surcharge `systemctl --user edit`** (un dossier `essai-<unité>.d`) ou une unité masquée",
        "elle la signale en anomalie à chaque passage, sans rien réinstaller",
        "La version suivante du projet, elle, la défait",
        "relance toutes les minuteries du projet (`enable --now`)",
    ):
        assert fragment in unites, fragment
    arreter = a_plat(section(texte, "Tout arrêter"))
    assert "La sonde de `serveur` ne supprime jamais rien" in arreter
    assert "comme sur une surcharge d'unité (« Unités »)" in arreter


# C0 : le runbook dit le report, sa copie jetable, l'option qui s'en passe et le rappel. Sans
# sauvegardes, il n'y a pas de section « Restaurer », ni de report.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_le_report(rendre, sauvegardes):
    texte = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes}), "docs/exploitation.md")
    assert ("REPORTER" in texte) is sauvegardes
    if not sauvegardes:
        return
    restaurer = a_plat(section(texte, "Restaurer"))
    for fragment in (
        "si `deploiement/projet.env` déclare `REPORTER`",
        "~/backups/essai/report-<horodatage>/",
        "S'il échoue, rien n'a changé",
        "relancer avec `--sans-report`",
        "`REPORTER_SECTION`",
        "« attention : le report n'a pas eu lieu »",
        # R67 : la sauvegarde de la nuit retire ce qu'une restauration tuée a laissé
        "restauration**, la sauvegarde de la nuit retire ce qu'elle a laissé",
    ):
        assert fragment in restaurer, fragment


# V10 : la mise en service dit l'uid de l'utilisateur de déploiement, et ce que fait la première
# sauvegarde lancée à la main : un vrai envoi, un signal, le verrou.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_exploitation_mise_en_service_uid_et_premiere_sauvegarde(rendre, sauvegardes):
    texte = lire(rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes}), "docs/exploitation.md")
    mise_en_service = a_plat(section(texte, "La mise en service"))
    assert "Un préalable : l'utilisateur de déploiement du serveur a l'uid 1000, celui du conteneur" in mise_en_service
    premiere = (
        "C'est une vraie sauvegarde, comme celle de la nuit : elle prend le verrou du projet"
        " (600 s d'attente au plus), envoie l'archive chiffrée au distant et signale `essai-sauvegarde`"
    )
    assert (premiere in mise_en_service) is sauvegardes


# V10 : le test de restauration lance l'image nue ; le contrat le dit.
@pytest.mark.parametrize("sauvegardes", [True, False])
def test_m0003_l_image_demarre_sans_son_environnement(rendre, sauvegardes):
    rendu = rendre(**{**REPONSES_SERVEUR, "sauvegardes": sauvegardes})
    m3 = a_plat(lire(rendu, "docs/modele/decisions/M-0003-contrat-de-l-image.md"))
    temoin = (
        "**démarre aussi sans son environnement** : le test de restauration la lance nue"
        " (`tester-restauration.sh`, `docker run` sans `-e`), sans `ESSAI_ENV`, `ESSAI_VERSION` ni"
        " `ESSAI_URL_PUBLIQUE`, et sans les secrets ni les variables de `compose.projet.yml`"
    )
    assert (temoin in m3) is sauvegardes


# Revue des corrections du lot 2 : les en-têtes disent ce que fait le code (m1, m6).
def test_en_tetes_du_report_et_du_compose(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    for chemin in ("deploiement/restaurer.sh", "tests/deploiement/sauvegarde.bats"):
        texte = lire(rendu, chemin)
        assert "document JSON" not in texte, chemin
        assert "un seul objet JSON" in texte, chemin
    compose = lire(rendu, "deploiement/compose.yml")
    assert "Toujours lancé par" not in compose
    assert "ou à la main avec les mêmes arguments" in compose


# Lot 12 : le compte GitHub est une réponse du modèle. Sans elle, le défaut est celui d'Edouard ; avec
# elle, l'image, la CI, la doc et les tests rendus suivent, en minuscules comme GHCR.
def test_compte_par_defaut(rendre):
    rendu = rendre(**REPONSES_SERVEUR)
    assert "DEPOT_IMAGE=ghcr.io/edouardzemb/essai" in lire(rendu, "deploiement/lib.sh")


def test_compte_rendu_partout(rendre):
    rendu = rendre(**REPONSES_SERVEUR, compte="Autre-Compte")
    for chemin in (
        "deploiement/lib.sh",
        ".github/workflows/modele-version.yml",
        ".github/actions/modele-image-publier/action.yml",
        "docs/exploitation.md",
    ):
        assert "ghcr.io/autre-compte/essai" in lire(rendu, chemin), chemin
    for chemin in fichiers_texte(rendu):
        texte = chemin.read_bytes().decode("utf-8", errors="replace")
        assert "ghcr.io/edouardzemb" not in texte, chemin
        assert "/edouardzemb/" not in texte, chemin
