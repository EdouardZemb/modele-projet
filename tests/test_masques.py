"""masques.py : un fichier que le modèle écrit ne doit pas être masqué par le .gitignore du projet."""

import fnmatch
import re
import subprocess
from pathlib import Path

import masques
import pytest
import yaml
from conftest import RACINE, REPONSES_DONNEES_SERVEUR, REPONSES_SERVEUR, git

METHODE = RACINE / "template/docs/modele/methode.md"
GERE = "scripts/modele/verifier_secrets.py"
AUTRE_REMEDE = (
    "Si ce fichier n'est ni du modèle ni un secret chiffré que la chaîne lit (un fichier local), "
    "le sortir de ce dossier ; ne jamais lever le masque d'un secret en clair."
)


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def ecrire(racine: Path, chemin: str, texte: str = "x\n") -> None:
    cible = racine / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8", newline="\n")


def ignore(racine: Path, env, chemin: str) -> bool:
    """Vrai si le .gitignore de `racine` masque `chemin`."""
    r = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", chemin],
        cwd=racine,
        env=env,
        capture_output=True,
        check=False,
    )
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


def modifier_reponses(racine, env, cible="aucune"):
    """Change `_commit` (ou la cible) dans les réponses, puis les indexe : le déclencheur."""
    ecrire(racine, ".copier-answers.yml", f"_commit: v0.2.3\ncible: {cible}\n")
    git(racine, env, "add", ".copier-answers.yml")


@pytest.fixture
def env(env_isole):
    return env_isole()


@pytest.fixture
def depot_masque(tmp_path, env):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, env, "init", "-q", "-b", "main")
    git(d, env, "config", "core.autocrlf", "false")
    ecrire(d, ".gitignore", "*secret*\n*.env\n")
    ecrire(d, ".copier-answers.yml", "_commit: v0.2.2\ncible: aucune\n")
    git(d, env, "add", ".gitignore", ".copier-answers.yml")
    git(d, env, "commit", "-q", "-m", "chore: départ")
    ecrire(d, GERE)
    return d


def test_sans_declencheur_rien_a_faire(depot_masque):
    assert masques.declenche(depot_masque) is False
    assert masques.main(["--racine", str(depot_masque)]) == 0


def test_fichier_gere_masque_refuse(depot_masque, env, capsys):
    ecrire(depot_masque, "scripts/modele/secrets.ps1")
    modifier_reponses(depot_masque, env)
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert "scripts/modele/verifier_secrets.py" in err
    assert ".gitignore:1:*secret*" in err
    assert "!scripts/modele/verifier_secrets.py" in err
    assert "!scripts/modele/secrets.ps1" in err
    # L'autre remède, une seule fois pour deux fichiers, juste avant le renvoi à methode.md.
    lignes = err.splitlines()
    assert lignes.count(AUTRE_REMEDE) == 1
    assert lignes[-2:] == [AUTRE_REMEDE, masques.RENVOI]


def test_dossier_parent_exclu(depot_masque, env, capsys):
    """Sous un dossier exclu, `!<fichier>` ne vaut rien : git n'y regarde pas. Le remède lève le
    dossier."""
    ecrire(depot_masque, ".gitignore", "env/\n")
    ecrire(depot_masque, "deploiement/env/prod.env")
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert "deploiement/env/prod.env (règle .gitignore:1:env/)" in err
    assert "Ajouter `!deploiement/env/` à ce fichier, puis indexer le fichier." in err
    assert "!deploiement/env/prod.env" not in err
    ecrire(depot_masque, ".gitignore", "env/\n!deploiement/env/\n")
    assert masques.main(["--racine", str(depot_masque)]) == 0


def test_dossier_parent_exclu_avec_un_fichier_suivi(depot_masque, env, capsys):
    """Un dossier exclu qui contient déjà un fichier suivi reste exclu pour un fichier neuf. Sans
    `--no-index`, git le tiendrait pour suivi et ne le dirait pas exclu : le remède retomberait sur
    `!<fichier>`, qui ne vaut rien, et le refus reviendrait en boucle."""
    ecrire(depot_masque, ".gitignore", "env/\n")
    ecrire(depot_masque, "deploiement/env/staging.env")
    git(depot_masque, env, "add", "-f", "deploiement/env/staging.env")
    git(depot_masque, env, "commit", "-q", "-m", "chore: staging suivi")
    ecrire(depot_masque, "deploiement/env/prod.env")
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert "deploiement/env/prod.env (règle .gitignore:1:env/)" in err
    assert "Ajouter `!deploiement/env/` à ce fichier, puis indexer le fichier." in err
    assert "!deploiement/env/prod.env" not in err
    ecrire(depot_masque, ".gitignore", "env/\n!deploiement/env/\n")
    assert masques.main(["--racine", str(depot_masque)]) == 0


@pytest.mark.parametrize(
    ("motif", "fichier"),
    [("env/*", "env/prod.env"), ("secrets/*", "secrets/prod.env.enc")],
    ids=["env", "secrets"],
)
def test_contenu_d_un_dossier_exclu(depot_masque, env, capsys, motif, fichier):
    """`<dossier>/*` exclut ce que contient le dossier, pas le dossier : `!<dossier>/` n'y vaut
    rien, et le remède nomme le fichier. Git compare ce motif à `<dossier>/` et le dit exclu :
    un remède sur le dossier reviendrait en boucle."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", f"{motif}\n")
    ecrire(depot_masque, fichier)
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert f"{fichier} (règle .gitignore:1:{motif}). Ajouter `!{fichier}` à ce fichier" in err
    assert f"`!{fichier.split('/')[0]}/`" not in err
    ecrire(depot_masque, ".gitignore", f"{motif}\n!{fichier}\n")
    assert masques.main(["--racine", str(depot_masque)]) == 0


def test_exception_nommee_acceptee(depot_masque, env):
    ecrire(depot_masque, ".gitignore", f"*secret*\n*.env\n!{GERE}\n")
    modifier_reponses(depot_masque, env)
    assert masques.main(["--racine", str(depot_masque)]) == 0


def test_cache_python_ignore(depot_masque, env):
    ecrire(depot_masque, ".gitignore", "__pycache__/\n*.pyc\n")
    ecrire(depot_masque, "scripts/modele/__pycache__/x.cpython-312.pyc")
    modifier_reponses(depot_masque, env)
    assert masques.main(["--racine", str(depot_masque)]) == 0


def test_chemins_serveur_selon_la_cible(depot_masque, env):
    ecrire(depot_masque, ".gitignore", "*.env\n")
    ecrire(depot_masque, "deploiement/env/prod.env")
    modifier_reponses(depot_masque, env, cible="aucune")
    assert masques.main(["--racine", str(depot_masque)]) == 0
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1


SERVEUR = masques.CHEMINS_COMMUNS + masques.CHEMINS_SERVEUR
DONNEES = masques.CHEMINS_COMMUNS + masques.CHEMINS_DONNEES
DONNEES_SERVEUR = DONNEES + masques.CHEMINS_INSTANCE


def test_cible_illisible_vaut_serveur(depot_masque):
    ecrire(depot_masque, ".copier-answers.yml", "_commit: v0.2.3\n")
    assert masques.chemins_examines(depot_masque) == SERVEUR
    ecrire(depot_masque, ".copier-answers.yml", "cible: aucune\n")
    assert masques.chemins_examines(depot_masque) == masques.CHEMINS_COMMUNS
    ecrire(depot_masque, ".copier-answers.yml", "cible: 'serveur'\n")
    assert masques.chemins_examines(depot_masque) == SERVEUR
    (depot_masque / ".copier-answers.yml").unlink()
    assert masques.chemins_examines(depot_masque) == SERVEUR


def test_cible_code_illisible_vaut_serveur(depot_masque):
    """Un dépôt de données examine son instance, sauf si sa `cible_code` dit `aucune`."""
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: aucune\n")
    assert masques.chemins_examines(depot_masque) == DONNEES
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    assert masques.chemins_examines(depot_masque) == DONNEES_SERVEUR
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\n")
    assert masques.chemins_examines(depot_masque) == DONNEES_SERVEUR


# Le .gitignore de `veille-emploi` avant sa scission : il masque tout dotenv et tout ce qui nomme
# un secret, et la porte ne voyait rien de l'instance d'un dépôt de données.
GITIGNORE_A_UN_DEPOT = "*secret*\n*.env\n"
INSTANCE_DES_DONNEES = (
    "env/prod.env",
    "env/staging.env",
    "cles/serveur.pub",
    "cles/hors-ligne.pub",
    ".sops.yaml",
    "secrets/prod.env.enc",
    "secrets/staging.env.enc",
)


def test_instance_des_donnees_masquee_refuse(depot_masque, env, capsys):
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", GITIGNORE_A_UN_DEPOT + "cles/\n.sops.yaml\n")
    for chemin in INSTANCE_DES_DONNEES:
        ecrire(depot_masque, chemin)
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    for chemin in INSTANCE_DES_DONNEES:
        assert f"{chemin} (règle" in err, chemin
    assert "env/prod.env (règle .gitignore:2:*.env)" in err
    assert "secrets/prod.env.enc (règle .gitignore:1:*secret*)" in err
    assert (
        "secret chiffré que la chaîne lit, masqué par le .gitignore : secrets/prod.env.enc "
        "(règle .gitignore:1:*secret*)"
    ) in err
    assert "`!/secrets/`, `/secrets/*` et `!/secrets/*.env.enc`, dans cet ordre" in err
    assert "Ajouter `!secrets/` à ce fichier" not in err
    assert "Ajouter `!/secrets/` à ce fichier" not in err
    # Le .gitignore d'un dépôt de données : l'instance passe, les secrets en clair restent dehors.
    ecrire(
        depot_masque,
        ".gitignore",
        GITIGNORE_A_UN_DEPOT
        + "!env/prod.env\n!env/staging.env\n!/secrets/\n/secrets/*\n!/secrets/*.env.enc\n",
    )
    assert masques.main(["--racine", str(depot_masque)]) == 0


# Sous un dossier de secrets exclu (`*secret*` exclut `secrets/` comme `deploiement/secrets/`),
# `!<dossier>` seul laisserait entrer les secrets en clair : le remède lève le dossier, en exclut le
# contenu, puis n'admet que ce que la chaîne y lit (M-0002, amendement du 2026-11-04). Ses lignes
# sont ancrées à la racine : `!secrets/`, sans `/` en tête, vaudrait à toute profondeur, et lèverait
# le masque de tout dossier `secrets/` imbriqué que `*secret*` exclut.
REMEDE_SECRETS = (
    "Ajouter à la fin de ce fichier `!/secrets/`, `/secrets/*` et `!/secrets/*.env.enc`, dans cet "
    "ordre, puis indexer le fichier : jamais `!/secrets/` seul, qui laisserait entrer les secrets "
    "en clair."
)
REMEDE_SECRETS_A_UN_DEPOT = (
    "Ajouter à la fin de ce fichier `!/deploiement/secrets/`, `/deploiement/secrets/*`, "
    "`!/deploiement/secrets/*.cles` et `!/deploiement/secrets/*.env.enc`, dans cet ordre, puis "
    "indexer le fichier : jamais `!/deploiement/secrets/` seul, qui laisserait entrer les secrets "
    "en clair."
)
# Des dossiers `secrets/` imbriqués, que `*secret*` masque, et que le remède doit laisser masqués.
SECRETS_IMBRIQUES = (
    "deploiement/secrets/identite.txt",
    "config/secrets/jeton.txt",
    "contenu/brouillons/secrets/cle.pem",
)


def lignes_du_remede(remede: str) -> list[str]:
    """Les lignes qu'un remède demande d'ajouter, dans son ordre."""
    return re.findall(r"`([^`]+)`", remede.split(", dans cet ordre", 1)[0])


def appliquer(racine: Path, gitignore: str, remede: str) -> None:
    """Écrit le .gitignore, suivi des lignes du remède, à la lettre."""
    lignes = "".join(f"{ligne}\n" for ligne in lignes_du_remede(remede))
    ecrire(racine, ".gitignore", gitignore + lignes)


def test_secret_chiffre_sous_un_dossier_de_secrets_exclu(depot_masque, env, capsys):
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "*secret*\n")
    clairs = ("secrets/prod.env", "secrets/age.txt", *SECRETS_IMBRIQUES)
    for chemin in ("secrets/prod.env.enc", *clairs):
        ecrire(depot_masque, chemin)
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert (
        "modele-projet : refusé — secret chiffré que la chaîne lit, masqué par le .gitignore : "
        f"secrets/prod.env.enc (règle .gitignore:1:*secret*). {REMEDE_SECRETS}"
    ) in err.splitlines()
    # Ni « fichier du modèle », ni un remède qui sortirait le secret chiffré : il doit entrer.
    assert "fichier du modèle" not in err
    assert err.splitlines()[-2:] == [AUTRE_REMEDE, masques.RENVOI]
    # Les secrets en clair ne sont pas examinés : rien n'en est dit.
    assert "secrets/prod.env " not in err
    assert "secrets/age.txt" not in err
    for clair in SECRETS_IMBRIQUES:
        assert f" : {clair} (règle " not in err, clair
    appliquer(depot_masque, "*secret*\n", REMEDE_SECRETS)
    assert masques.main(["--racine", str(depot_masque)]) == 0
    # Le remède appliqué à la lettre : aucun secret en clair ne paraît, imbriqué ou non.
    assert [clair for clair in clairs if not ignore(depot_masque, env, clair)] == []
    assert not ignore(depot_masque, env, "secrets/prod.env.enc")


# Ce qu'un projet à un dépôt garde en local sous `deploiement/secrets/`, hors de ce que la chaîne y
# lit au premier niveau (`*.cles`, `*.env.enc`) : un secret en clair, une identité, une copie.
CLAIRS_A_UN_DEPOT = (
    "deploiement/secrets/prod.env",
    "deploiement/secrets/age.txt",
    "deploiement/secrets/ancien/staging.env.enc",
)


def test_secret_chiffre_d_un_projet_a_un_depot(depot_masque, env, capsys):
    """En cible `serveur`, `deploiement/secrets/` porte aussi les `.cles` du modèle. La porte examine
    tout `deploiement/`, mais n'y voit, sous `deploiement/secrets/`, que ce que la chaîne y lit au
    premier niveau : un secret en clair y reste masqué, sans refus ni remède qui le nomme."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "*secret*\n")
    for chemin in (
        "deploiement/secrets/prod.cles",
        "deploiement/secrets/prod.env.enc",
        *CLAIRS_A_UN_DEPOT,
    ):
        ecrire(depot_masque, chemin)
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    for clair in CLAIRS_A_UN_DEPOT:
        assert f" : {clair} (règle " not in err, clair
    lignes = err.splitlines()
    assert (
        "modele-projet : refusé — fichier du modèle masqué par le .gitignore : "
        "deploiement/secrets/prod.cles (règle .gitignore:1:*secret*). "
        f"{REMEDE_SECRETS_A_UN_DEPOT}"
    ) in lignes
    assert (
        "modele-projet : refusé — secret chiffré que la chaîne lit, masqué par le .gitignore : "
        "deploiement/secrets/prod.env.enc (règle .gitignore:1:*secret*). "
        f"{REMEDE_SECRETS_A_UN_DEPOT}"
    ) in lignes
    appliquer(depot_masque, "*secret*\n", REMEDE_SECRETS_A_UN_DEPOT)
    assert masques.main(["--racine", str(depot_masque)]) == 0
    assert [clair for clair in CLAIRS_A_UN_DEPOT if not ignore(depot_masque, env, clair)] == []
    assert not ignore(depot_masque, env, "deploiement/secrets/prod.cles")
    assert not ignore(depot_masque, env, "deploiement/secrets/prod.env.enc")


# Un dossier exclu qui contient un dossier de secrets : `!/deploiement/` seul ferait entrer tout
# `deploiement/secrets/`. Le remède lève aussi le dossier de secrets, au cas où une autre règle
# l'exclut, en exclut le contenu, puis n'admet que ce que la chaîne y lit.
REMEDE_DEPLOIEMENT = (
    "Ajouter à la fin de ce fichier `!/deploiement/`, `!/deploiement/secrets/`, "
    "`/deploiement/secrets/*`, `!/deploiement/secrets/*.cles` et "
    "`!/deploiement/secrets/*.env.enc`, dans cet ordre, puis indexer le fichier : jamais "
    "`!/deploiement/` seul, qui laisserait entrer les secrets en clair."
)


@pytest.mark.parametrize(
    "gitignore", ["deploiement/\n", "*secret*\ndeploiement/\n"], ids=["deploiement", "et-secret"]
)
def test_dossier_exclu_qui_contient_un_dossier_de_secrets(depot_masque, env, capsys, gitignore):
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", gitignore)
    du_modele = (
        "deploiement/deployer.sh",
        "deploiement/secrets/prod.cles",
        "deploiement/secrets/prod.env.enc",
    )
    for chemin in (*du_modele, *CLAIRS_A_UN_DEPOT):
        ecrire(depot_masque, chemin)
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    for chemin in du_modele:
        (ligne,) = [ligne for ligne in err.splitlines() if f" : {chemin} (règle " in ligne]
        assert ligne.endswith(f"). {REMEDE_DEPLOIEMENT}"), ligne
    for clair in CLAIRS_A_UN_DEPOT:
        assert f" : {clair} (règle " not in err, clair
    # Appliqué à la lettre, le remède converge en un tour, et les secrets en clair restent dehors.
    appliquer(depot_masque, gitignore, REMEDE_DEPLOIEMENT)
    assert masques.main(["--racine", str(depot_masque)]) == 0
    assert [clair for clair in CLAIRS_A_UN_DEPOT if not ignore(depot_masque, env, clair)] == []
    assert [chemin for chemin in du_modele if ignore(depot_masque, env, chemin)] == []


def test_depot_de_donnees_garde_ce_qu_il_peut_ignorer(depot_masque, env):
    """Un secret en clair, une clé privée, un fichier local de config/ ou de contenu/ : un dépôt
    de données a le droit de les ignorer, et la porte ne lui demande pas de lever leur masque."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "*secret*\n*.env\n*.txt\nconfig/.env\ncontenu/local/\n")
    for chemin in (
        "secrets/prod.env",
        "cles/hors-ligne.txt",
        "config/.env",
        "contenu/local/brouillon.md",
    ):
        ecrire(depot_masque, chemin)
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 0


def test_motifs_de_l_instance_au_premier_niveau(depot_masque, env):
    """`secrets/*.env.enc` et `cles/*.pub` ne valent qu'au premier niveau de leur dossier, comme le
    .gitignore semé et `.sops.yaml` : ce que le .gitignore semé masque exprès sous `secrets/sous/`,
    ou un ancien dossier de clés, n'est pas examiné."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "secrets/*\n!secrets/*.env.enc\ncles/ancien/\n")
    for chemin in ("secrets/sous/prod.env.enc", "cles/ancien/vieux.pub", "secrets/prod.env.enc"):
        ecrire(depot_masque, chemin)
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 0
    assert masques.fichiers_masques(depot_masque, masques.chemins_examines(depot_masque)) == []


def test_depot_de_donnees_sans_serveur(depot_masque, env):
    """Sans `cible_code: serveur`, le dépôt de données n'a pas d'instance à examiner, mais ses deux
    README.md restent du modèle."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "*.env\n")
    ecrire(depot_masque, "env/prod.env")
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: aucune\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 0
    ecrire(depot_masque, ".gitignore", "*.env\nREADME.md\n")
    ecrire(depot_masque, "config/README.md")
    assert masques.main(["--racine", str(depot_masque)]) == 1


def test_reponses_non_suivies_declenchent(tmp_path, env, capsys):
    d = tmp_path / "neuf"
    d.mkdir()
    git(d, env, "init", "-q", "-b", "main")
    ecrire(d, ".gitignore", "*.yml\n")
    ecrire(d, ".copier-answers.yml", "cible: aucune\n")
    assert masques.declenche(d) is True
    assert masques.main(["--racine", str(d)]) == 1
    assert ".copier-answers.yml" in capsys.readouterr().err


def test_workflow_gere_seul(depot_masque, env):
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", ".github/workflows/ci.yml\n")
    ecrire(depot_masque, ".github/workflows/ci.yml")
    modifier_reponses(depot_masque, env)
    assert masques.main(["--racine", str(depot_masque)]) == 0
    ecrire(depot_masque, ".gitignore", ".github/workflows/modele-socle.yml\n")
    ecrire(depot_masque, ".github/workflows/modele-socle.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 1


def test_nom_avec_espace_et_accent(depot_masque, env, capsys):
    nom = "scripts/modele/vérifier secrets.py"
    ecrire(depot_masque, nom)
    modifier_reponses(depot_masque, env)
    assert masques.main(["--racine", str(depot_masque)]) == 1
    assert nom in capsys.readouterr().err


def test_lance_depuis_un_sous_dossier(depot_masque, env, monkeypatch):
    modifier_reponses(depot_masque, env)
    (depot_masque / "docs").mkdir()
    monkeypatch.chdir(depot_masque / "docs")
    assert masques.main([]) == 1


def test_git_en_echec_refuse(tmp_path, capsys):
    assert masques.main(["--racine", str(tmp_path)]) == 1
    assert "invérifiables" in capsys.readouterr().err


def test_usage_invalide():
    assert masques.main(["--inconnu"]) == 64


def test_chemins_couvrent_methode():
    """Chaque chemin géré que methode.md énumère est examiné."""
    section = lire(METHODE).split("## Les fichiers gérés par le modèle", 1)[1].split("\n## ", 1)[0]
    puce = next(ligne for ligne in section.split("\n- ") if "exclus des formateurs" in ligne)
    chemins = re.findall(r"`([^`]+/[^`]*)`", puce)
    assert chemins
    for chemin in chemins:
        assert chemin in masques.CHEMINS_COMMUNS, chemin


def couvert(fichier: str, chemins) -> bool:
    """Vrai si un chemin de la liste couvre `fichier` : un dossier (`…/`) couvre ce qu'il contient,
    un motif `*` se compare par fnmatch sans franchir un `/`, comme la porte le lit
    (`--glob-pathspecs`), tout autre chemin se compare tel quel."""
    for chemin in chemins:
        if chemin.endswith("/"):
            if fichier.startswith(chemin):
                return True
        elif "*" in chemin:
            if fichier.count("/") == chemin.count("/") and fnmatch.fnmatchcase(fichier, chemin):
                return True
        elif fichier == chemin:
            return True
    return False


REPONSES_DONNEES = {"nom": "essai-donnees", "cible": "donnees"}


def fichiers(rendu: Path) -> list[str]:
    return [p.relative_to(rendu).as_posix() for p in sorted(rendu.rglob("*")) if p.is_file()]


@pytest.mark.parametrize(
    "reponses",
    [{}, REPONSES_SERVEUR, REPONSES_DONNEES, REPONSES_DONNEES_SERVEUR],
    ids=["aucune", "serveur", "donnees", "donnees-serveur"],
)
def test_chemins_couvrent_le_rendu(rendre, reponses):
    """Chaque fichier géré du rendu (tout ce que `_skip_if_exists` ne sème pas) est examiné, sous
    les chemins que la porte tire des réponses du rendu."""
    semes = set(yaml.safe_load(lire(RACINE / "copier.yml"))["_skip_if_exists"])
    rendu = rendre(**reponses)
    chemins = masques.chemins_examines(rendu)
    geres = [g for g in fichiers(rendu) if g not in semes]
    assert geres
    assert [g for g in geres if not couvert(g, chemins)] == []
    # Sous un dossier de secrets, la porte n'examine que ce que la chaîne y lit : aucun fichier du
    # rendu, semé ou géré, n'y échappe.
    assert [f for f in fichiers(rendu) if masques.hors_de_la_chaine(f)] == []


@pytest.mark.parametrize(
    "reponses", [REPONSES_DONNEES, REPONSES_DONNEES_SERVEUR], ids=["donnees", "donnees-serveur"]
)
def test_chemins_couvrent_les_donnees(rendre, reponses):
    """Ce qu'un dépôt de données a de plus qu'un dépôt de code est examiné, semés compris (son
    instance, ses deux README.md), et les secrets chiffrés que la chaîne y lit aussi."""
    code = set(fichiers(rendre()))
    rendu = rendre(**reponses)
    chemins = masques.chemins_examines(rendu)
    propres = [f for f in fichiers(rendu) if f not in code]
    assert {"config/README.md", "contenu/README.md"} <= set(propres)
    if reponses.get("cible_code") == "serveur":
        assert {"env/prod.env", "env/staging.env", "cles/serveur.pub", ".sops.yaml"} <= set(
            propres
        )
        propres += ["secrets/prod.env.enc", "secrets/staging.env.enc"]
    assert [f for f in propres if not couvert(f, chemins)] == []
