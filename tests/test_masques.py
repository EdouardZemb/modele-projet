"""masques.py : un fichier que le modèle écrit ne doit pas être masqué par le .gitignore du projet."""

import fnmatch
import re
import subprocess
from pathlib import Path

import masques
import pytest
import yaml
from conftest import (
    RACINE,
    REPONSES_DONNEES_SERVEUR,
    REPONSES_SERVEUR,
    REPONSES_SERVEUR_CODE,
    git,
)

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
    # Ancrées : `!secrets.ps1`, sans `/`, vaudrait à toute profondeur.
    assert "Ajouter `!/scripts/modele/verifier_secrets.py` à ce fichier, puis l'indexer." in err
    assert "Ajouter `!/scripts/modele/secrets.ps1` à ce fichier, puis l'indexer." in err
    # L'autre remède, une seule fois pour deux fichiers, juste avant le renvoi à methode.md.
    lignes = err.splitlines()
    assert lignes.count(AUTRE_REMEDE) == 1
    assert lignes[-2:] == [AUTRE_REMEDE, masques.RENVOI]


def remede_attendu(*lignes: str) -> str:
    """Le remède d'un dossier exclu, tel que la porte l'écrit : ses lignes, dans leur ordre."""
    cites = [f"`{ligne}`" for ligne in lignes]
    return (
        f"Ajouter à la fin de ce fichier {', '.join(cites[:-1])} et {cites[-1]}, dans cet ordre, "
        f"puis indexer le fichier : ces lignes n'admettent que ce que la porte examine, et "
        f"{cites[0]} seul ferait entrer tout le dossier."
    )


# `deploiement/env/` est mixte : un fichier local peut y vivre à côté des deux du modèle.
REMEDE_ENV_A_UN_DEPOT = remede_attendu(
    "!/deploiement/env/",
    "/deploiement/env/*",
    "!/deploiement/env/prod.env",
    "!/deploiement/env/staging.env",
)


def test_dossier_parent_exclu(depot_masque, env, capsys):
    """Sous un dossier exclu, `!/<fichier>` ne vaut rien : git n'y regarde pas. Le remède lève le
    dossier, et n'y admet que ce que la porte examine : un fichier local reste masqué."""
    ecrire(depot_masque, ".gitignore", "env/\n")
    ecrire(depot_masque, "deploiement/env/prod.env")
    ecrire(depot_masque, "deploiement/env/local.env")
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert f"deploiement/env/prod.env (règle .gitignore:1:env/). {REMEDE_ENV_A_UN_DEPOT}" in err
    assert "local.env" not in err
    appliquer(depot_masque, "env/\n", REMEDE_ENV_A_UN_DEPOT)
    assert masques.main(["--racine", str(depot_masque)]) == 0
    assert ignore(depot_masque, env, "deploiement/env/local.env")


def test_dossier_parent_exclu_avec_un_fichier_suivi(depot_masque, env, capsys):
    """Un dossier exclu qui contient déjà un fichier suivi reste exclu pour un fichier neuf. Sans
    `--no-index`, git le tiendrait pour suivi et ne le dirait pas exclu : le remède retomberait sur
    `!/<fichier>`, qui ne vaut rien, et le refus reviendrait en boucle."""
    ecrire(depot_masque, ".gitignore", "env/\n")
    ecrire(depot_masque, "deploiement/env/staging.env")
    git(depot_masque, env, "add", "-f", "deploiement/env/staging.env")
    git(depot_masque, env, "commit", "-q", "-m", "chore: staging suivi")
    ecrire(depot_masque, "deploiement/env/prod.env")
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert f"deploiement/env/prod.env (règle .gitignore:1:env/). {REMEDE_ENV_A_UN_DEPOT}" in err
    appliquer(depot_masque, "env/\n", REMEDE_ENV_A_UN_DEPOT)
    assert masques.main(["--racine", str(depot_masque)]) == 0


@pytest.mark.parametrize(
    ("motif", "fichier"),
    [("env/*", "env/prod.env"), ("secrets/*", "secrets/prod.env.enc")],
    ids=["env", "secrets"],
)
def test_contenu_d_un_dossier_exclu(depot_masque, env, capsys, motif, fichier):
    """`<dossier>/*` exclut ce que contient le dossier, pas le dossier : `!/<dossier>/` n'y vaut
    rien, et le remède nomme le fichier. Git compare ce motif à `<dossier>/` et le dit exclu :
    un remède sur le dossier reviendrait en boucle."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", f"{motif}\n")
    ecrire(depot_masque, fichier)
    ecrire(depot_masque, ".copier-answers.yml", "cible: donnees\ncible_code: serveur\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert f"{fichier} (règle .gitignore:1:{motif}). Ajouter `!/{fichier}` à ce fichier" in err
    assert f"`!/{fichier.split('/')[0]}/`" not in err
    ecrire(depot_masque, ".gitignore", f"{motif}\n!/{fichier}\n")
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


SERVEUR_CODE = masques.CHEMINS_COMMUNS + masques.CHEMINS_SERVEUR
SERVEUR = SERVEUR_CODE + masques.CHEMINS_SERVEUR_A_UN_DEPOT
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


def test_nature_illisible_vaut_donnees(depot_masque):
    """En cible `serveur`, l'instance et ses secrets chiffrés ne sont examinés qu'à un dépôt, en
    nature `donnees` : un dépôt de code a les siens dans `<nom>-donnees` (#95, ronde 3). Une nature
    illisible vaut `donnees`, comme une cible illisible vaut `serveur`."""
    ecrire(depot_masque, ".copier-answers.yml", "cible: serveur\nnature: code\n")
    assert masques.chemins_examines(depot_masque) == SERVEUR_CODE
    ecrire(depot_masque, ".copier-answers.yml", "cible: serveur\nnature: 'donnees'\n")
    assert masques.chemins_examines(depot_masque) == SERVEUR
    ecrire(depot_masque, ".copier-answers.yml", "cible: serveur\n")
    assert masques.chemins_examines(depot_masque) == SERVEUR
    ecrire(depot_masque, ".copier-answers.yml", "_commit: v0.8.1\nnature: code\n")
    assert masques.chemins_examines(depot_masque) == SERVEUR_CODE


# L'instance d'un projet `serveur` à un dépôt : un dépôt de code n'en a rien (M-0006, § 3).
INSTANCE_A_UN_DEPOT = (
    ".sops.yaml",
    "deploiement/env/prod.env",
    "deploiement/env/staging.env",
    "deploiement/cles/serveur.pub",
    "deploiement/secrets/prod.env.enc",
)


def test_depot_de_code_n_examine_pas_l_instance(depot_masque, env, capsys):
    """Dans un dépôt de code `serveur`, un `.sops.yaml`, un `.enc` ou un fichier d'env locaux ne
    sont ni du modèle ni lus par la chaîne : ils restent masqués, sans refus. La confidentialité
    refuserait de toute façon les deux premiers, et le troisième entrerait dans un dépôt public."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "*.env\n*.enc\n*.pub\n.sops.yaml\n")
    for chemin in INSTANCE_A_UN_DEPOT:
        ecrire(depot_masque, chemin)
    ecrire(depot_masque, ".copier-answers.yml", "_commit: v0.8.1\ncible: serveur\nnature: code\n")
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 0
    assert capsys.readouterr().err == ""
    ecrire(
        depot_masque, ".copier-answers.yml", "_commit: v0.8.1\ncible: serveur\nnature: donnees\n"
    )
    git(depot_masque, env, "add", ".copier-answers.yml")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    for chemin in INSTANCE_A_UN_DEPOT:
        assert f" : {chemin} (règle " in err, chemin


def test_fichier_local_de_premier_niveau_sous_deploiement(depot_masque, env, capsys):
    """La porte nomme les fichiers que le modèle écrit au premier niveau de `deploiement/` : un
    `compose.override.yml` ou un script local y restent masqués, sans refus (#95, ronde 3)."""
    (depot_masque / GERE).unlink()
    ecrire(depot_masque, ".gitignore", "compose.override.yml\n*-locale.sh\nlib.sh\n")
    for chemin in ("deploiement/compose.override.yml", "deploiement/sauvegarde-locale.sh"):
        ecrire(depot_masque, chemin)
    modifier_reponses(depot_masque, env, cible="serveur")
    assert masques.main(["--racine", str(depot_masque)]) == 0
    ecrire(depot_masque, "deploiement/lib.sh")
    assert masques.main(["--racine", str(depot_masque)]) == 1
    err = capsys.readouterr().err
    assert "Ajouter `!/deploiement/lib.sh` à ce fichier, puis l'indexer." in err
    assert "compose.override.yml (" not in err
    assert "sauvegarde-locale.sh (" not in err


@pytest.mark.parametrize(
    ("chemin", "attendu"),
    [
        ("scripts/modele/secrets/jeton.txt", "scripts/modele/secrets/"),
        # Sous Windows, `git init` pose `core.ignorecase` : `*secret*` y masque `Secrets/`.
        ("scripts/modele/Secrets/jeton.txt", "scripts/modele/Secrets/"),
        ("tests/deploiement/SECRETS/cle.pem", "tests/deploiement/SECRETS/"),
        ("tests/deploiement/Cles/identite.txt", "tests/deploiement/Cles/"),
        ("tests/deploiement/cles/identite.txt", "tests/deploiement/cles/"),
        # Chaque niveau sous le dossier du modèle compte, pas seulement le premier (#95, ronde 4).
        ("tests/deploiement/doubles/secrets/x.pem", "tests/deploiement/doubles/secrets/"),
        ("scripts/modele/vieux.pyc", "scripts/modele/vieux.pyc"),
        ("scripts/modele/__pycache__/x.pyc", "scripts/modele/__pycache__/"),
        ("scripts/modele/cles.py", None),
        ("deploiement/cles/identite.txt", None),
    ],
)
def test_hors_de_la_porte_sans_la_casse(chemin, attendu):
    """Un dossier de secrets ou de clés imbriqué sous un dossier du modèle n'est pas examiné, quelle
    que soit sa casse."""
    assert masques.hors_de_la_porte(chemin, SERVEUR) == attendu


def test_remede_echappe_les_caracteres_de_motif():
    """Un chemin cité par un remède se lit comme un motif du .gitignore : ses `[`, `*`, `?` et ses
    barres obliques inverses s'échappent, sinon `/tests/deploiement/[secrets]/` viserait
    `tests/deploiement/s/`."""
    lignes = masques.a_poser(
        "tests/deploiement/x.bats", "tests/", SERVEUR, ["tests/deploiement/[secrets]/"]
    )
    assert lignes[-1] == "/tests/deploiement/\\[secrets]/"
    assert masques.a_poser("scripts/modele/a[1]?.py", None, SERVEUR, []) == [
        "!/scripts/modele/a\\[1]\\?.py"
    ]
    assert masques.exceptions("tests/deploiement/[x]/", SERVEUR) == ["!/tests/deploiement/\\[x]/"]
    assert masques.relative("!/a\\[b]/x.sh", "a[b]/") == "!/x.sh"
    assert masques.echapper("a*b\\c") == "a\\*b\\\\c"
    # Un remède ne ré-exclut que ce qui est sous le dossier qu'il lève (#95, ronde 4).
    lignes = masques.a_poser(
        "tests/deploiement/x.bats", "tests/", SERVEUR, ["scripts/modele/secrets/"]
    )
    assert "/scripts/modele/secrets/" not in lignes


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


# Un dossier de secrets est mixte (`*secret*` exclut `secrets/` comme `deploiement/secrets/`) : le
# remède le lève, en exclut le contenu, puis n'admet que ce que la porte y examine, par des lignes
# ancrées (M-0002, amendement du 2026-11-04). `!secrets/`, sans `/` en tête, vaudrait à toute
# profondeur, et lèverait le masque de tout dossier `secrets/` imbriqué que `*secret*` exclut.
REMEDE_SECRETS = (
    "Ajouter à la fin de ce fichier `!/secrets/`, `/secrets/*` et `!/secrets/*.env.enc`, dans cet "
    "ordre, puis indexer le fichier : ces lignes n'admettent que ce que la porte examine, et "
    "`!/secrets/` seul ferait entrer tout le dossier."
)
REMEDE_SECRETS_A_UN_DEPOT = remede_attendu(
    "!/deploiement/secrets/",
    "/deploiement/secrets/*",
    "!/deploiement/secrets/*.cles",
    "!/deploiement/secrets/*.env.enc",
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
    """En cible `serveur`, `deploiement/secrets/` porte aussi les `.cles` du modèle. La porte n'y
    examine que ce que la chaîne y lit au premier niveau : un secret en clair y reste masqué, sans
    refus ni remède qui le nomme."""
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


# `deploiement/` est mixte, et l'ancêtre de dossiers mixtes : `!/deploiement/` seul ferait entrer
# tout le dossier, secrets en clair, clés privées et fichiers locaux compris. Le remède le lève, en
# exclut le contenu, puis n'admet que ce que la porte y examine, chaque dossier mixte par ses
# propres lignes, levé au cas où une autre règle l'exclut.
REMEDE_DEPLOIEMENT = remede_attendu(
    "!/deploiement/",
    "/deploiement/*",
    # Ses fichiers de premier niveau, par leur nom : un fichier local y reste masqué (#95, ronde 3).
    "!/deploiement/alerter.sh",
    "!/deploiement/deployer.sh",
    "!/deploiement/installer-unites.sh",
    "!/deploiement/lib.sh",
    "!/deploiement/nettoyer-images.sh",
    "!/deploiement/sonder.sh",
    "!/deploiement/restaurer.sh",
    "!/deploiement/sauvegarder.sh",
    "!/deploiement/tester-restauration.sh",
    "!/deploiement/compose.yml",
    "!/deploiement/compose.config.yml",
    "!/deploiement/compose.contenu.yml",
    "!/deploiement/compose.projet.yml",
    "!/deploiement/projet.env",
    "!/deploiement/ci/",
    "!/deploiement/systemd/",
    "!/deploiement/secrets/",
    "/deploiement/secrets/*",
    "!/deploiement/secrets/*.cles",
    "!/deploiement/secrets/*.env.enc",
    "!/deploiement/env/",
    "/deploiement/env/*",
    "!/deploiement/env/prod.env",
    "!/deploiement/env/staging.env",
    "!/deploiement/cles/",
    "/deploiement/cles/*",
    "!/deploiement/cles/*.pub",
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


# Les semés que la porte laisse au projet : ils vivent hors des dossiers du modèle et de l'instance.
# Tout autre semé est examiné : un semé neuf sous `deploiement/` doit l'être, ou s'ajouter ici.
SEMES_DU_PROJET = {
    "CLAUDE.md",
    "README.md",
    "LICENSE",
    ".gitattributes",
    ".gitignore",
    ".editorconfig",
    "docs/00-brief-initial.md",
    "docs/cadrage.md",
    "docs/decisions/README.md",
    "docs/pistes.md",
    "docs/registre.md",
    "docs/exploitation.md",
    ".github/workflows/ci.yml",
    ".github/dependabot.yml",
}


@pytest.mark.parametrize(
    "reponses",
    [{}, REPONSES_SERVEUR, REPONSES_SERVEUR_CODE, REPONSES_DONNEES, REPONSES_DONNEES_SERVEUR],
    ids=["aucune", "serveur", "serveur-code", "donnees", "donnees-serveur"],
)
def test_chemins_couvrent_le_rendu(rendre, reponses):
    """Chaque fichier du rendu est examiné, sous les chemins que la porte tire des réponses du
    rendu, semés compris, sauf les semés que la porte laisse au projet (`SEMES_DU_PROJET`). Et,
    hors des chemins communs, la porte n'examine que ce que le modèle écrit : chaque chemin de la
    cible couvre un fichier du rendu, sauf les secrets chiffrés, que la chaîne lit (#95, ronde 3)."""
    semes = set(yaml.safe_load(lire(RACINE / "copier.yml"))["_skip_if_exists"])
    assert SEMES_DU_PROJET <= semes
    rendu = rendre(**reponses)
    chemins = masques.chemins_examines(rendu)
    tous = fichiers(rendu)
    assert [f for f in tous if f not in SEMES_DU_PROJET and not couvert(f, chemins)] == []
    propres = [c for c in chemins if c not in masques.CHEMINS_COMMUNS + masques.SECRETS_CHIFFRES]
    assert [c for c in propres if not any(couvert(f, (c,)) for f in tous)] == []
    # Ce que la porte n'examine pas sous ses chemins (un dossier de secrets ou de clés imbriqué, un
    # cache) : aucun fichier du rendu, semé ou géré, n'y échappe.
    assert [f for f in tous if masques.hors_de_la_porte(f, chemins) is not None] == []


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


# La matrice des remèdes (#95, rondes 2 et 3 après relecture). Le principe : un remède n'admet que
# ce que la porte examine, toujours par des lignes ancrées. Pour chaque cible et chaque .gitignore,
# les remèdes appliqués à la lettre, jusqu'au silence, ne font paraître aucun des fichiers plantés à
# côté des fichiers examinés, et rendent suivable tout ce que la porte examine, en autant de tours
# au plus que `TOURS` le dit. Un seul dépôt git par case, sans Copier.
EXAMINES_COMMUNS = (
    ".copier-answers.yml",
    ".githooks/pre-commit",
    "scripts/modele/verifier_secrets.py",
    "scripts/modele/secrets.ps1",
    "docs/modele/methode.md",
    "docs/modele/decisions/M-0002-garde-fous-et-confidentialite.md",
    ".github/modele/gitleaks.toml",
    ".github/workflows/modele-socle.yml",
    ".github/ISSUE_TEMPLATE/lot.yml",
    ".github/pull_request_template.md",
    ".claude/skills/consigner/SKILL.md",
    ".claude/settings.json",
)
EXAMINES_SERVEUR_CODE = (
    *EXAMINES_COMMUNS,
    "deploiement/alerter.sh",
    "deploiement/deployer.sh",
    "deploiement/lib.sh",
    "deploiement/compose.yml",
    "deploiement/compose.projet.yml",
    "deploiement/projet.env",
    "deploiement/ci/verifier-image.sh",
    "deploiement/systemd/essai-sonde.timer.in",
    "deploiement/secrets/prod.cles",
    "tests/deploiement/secrets.bats",
    "tests/deploiement/doubles/git",
    ".github/actions/modele-image-construire/action.yml",
)
EXAMINES_PAR_CIBLE = {
    "donnees": (
        *EXAMINES_COMMUNS,
        "config/README.md",
        "contenu/README.md",
        ".sops.yaml",
        "env/prod.env",
        "env/staging.env",
        "cles/serveur.pub",
        "cles/hors-ligne.pub",
        "secrets/prod.env.enc",
        "secrets/staging.env.enc",
    ),
    # Un projet `serveur` à un dépôt (nature `donnees`) porte son instance.
    "serveur": (*EXAMINES_SERVEUR_CODE, *INSTANCE_A_UN_DEPOT),
    "serveur-code": EXAMINES_SERVEUR_CODE,
}
REPONSES_PAR_CIBLE = {
    "donnees": "cible: donnees\ncible_code: serveur\n",
    "serveur": "cible: serveur\nnature: donnees\n",
    "serveur-code": "cible: serveur\nnature: code\n",
}
# Ce que la porte n'examine pas, à côté de ce qu'elle examine : des clés privées, des secrets en
# clair, des fichiers locaux, des dossiers de secrets, de clés ou d'env imbriqués, quelle que soit
# leur casse, un cache, un nom qui porte un caractère de motif.
PLANTES = (
    "cles/identite-age.txt",
    "deploiement/cles/identite-age.txt",
    "secrets/prod.env",
    "secrets/ancien/vieux.env.enc",
    "deploiement/secrets/prod.env",
    "deploiement/secrets/ancien/vieux.env.enc",
    "env/local.env",
    "deploiement/env/local.env",
    "deploiement/compose.override.yml",
    "deploiement/sauvegarde-locale.sh",
    "config/local.env",
    "config/secrets/jeton.txt",
    "contenu/brouillons/notes.md",
    "contenu/brouillons/env/prod.env",
    "deploiement/outils/secrets/cle.pem",
    "tests/deploiement/secrets/cle.pem",
    "tests/deploiement/cles/identite.txt",
    "tests/deploiement/[secrets]/cle.pem",
    "scripts/modele/Secrets/jeton.txt",
    "scripts/modele/Cles/id.txt",
    "scripts/modele/vieux.pyc",
    ".claude/settings.local.json",
    "scripts/modele/__pycache__/lancer.cpython-312.pyc",
)
# Un dépôt de code n'a rien de l'instance : un `.sops.yaml`, un env ou un `.enc` y sont locaux.
PLANTES_PAR_CIBLE = {
    "donnees": PLANTES,
    "serveur": PLANTES,
    "serveur-code": (*PLANTES, *INSTANCE_A_UN_DEPOT),
}
# Le dossier du .gitignore, et ses règles : celles de `veille-emploi`, des dossiers, des motifs, des
# fichiers locaux, une liste blanche, `*` seul, et des .gitignore imbriqués.
REGLES = {
    "veille-emploi": (".", "*.env\n*secret*\n"),
    "secrets": (".", "secrets/\n"),
    "secrets-a-la-racine": (".", "/secrets\n"),
    "cles": (".", "cles/\n"),
    "env": (".", "env/\n"),
    "config": (".", "config/\n"),
    "contenu": (".", "contenu/\n"),
    "deploiement": (".", "deploiement/\n"),
    "deploiement-contenu": (".", "deploiement/*\n"),
    "deploiement-tout": (".", "deploiement/**\n"),
    "secret-et-deploiement": (".", "*secret*\ndeploiement/\n"),
    "tests": (".", "tests/\n"),
    "scripts": (".", "scripts/\n"),
    "sous-dossiers-du-modele": (".", "decisions/\ndoubles/\n"),
    "fichiers-locaux": (".", "compose.override.yml\n*-locale.sh\n"),
    "pub": (".", "*.pub\n"),
    "enc": (".", "*.enc\n"),
    "sops": (".", ".sops.yaml\n"),
    "claude": (".", ".claude/\n"),
    "liste-blanche": (".", "*\n!*/\n!.gitignore\n"),
    "etoile": (".", "*\n!.gitignore\n"),
    "imbrique-secrets": ("secrets", "*\n!.gitignore\n"),
    "imbrique-cles": ("cles", "*\n"),
    "imbrique-deploiement": ("deploiement", "secrets/\n"),
    "imbrique-tests": ("tests", "*\n"),
}
# Les tours de remède qu'un .gitignore demande au plus, dans toute cible : un seul, sauf quand deux
# règles masquent le même fichier (git ne nomme que celle du dossier exclu, l'autre se voit au tour
# suivant), et sous `*` ou `**`, qui excluent aussi ce que contient un dossier levé, niveau par niveau.
TOURS = {"secret-et-deploiement": 2, "deploiement-tout": 2, "etoile": 3, "imbrique-tests": 3}
REFUS = re.compile(r"\(règle (.+?):\d+:.*?\)\. Ajouter (.+)$")


@pytest.fixture
def git_isole(tmp_path, monkeypatch):
    """Ni la configuration globale ni le fichier d'exclusion du poste : la porte, qui lance git
    dans le processus des tests, et les contrôles voient les mêmes règles."""
    home = tmp_path / "home-vide"
    home.mkdir()
    vide = home / "gitconfig"
    vide.write_text("", encoding="utf-8")
    for variable in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(variable, str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(vide))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def masques_parmi(racine: Path, chemins) -> set[str]:
    """Ceux des `chemins` que les .gitignore masquent, par un seul `git check-ignore`."""
    r = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=racine,
        input="".join(f"{c}\0" for c in chemins).encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert r.returncode in (0, 1), r.stderr
    return {c for c in r.stdout.decode("utf-8").split("\0") if c}


def remedes_a_la_lettre(err: str) -> list[tuple[str, tuple[str, ...]]]:
    """Chaque remède d'un refus, une fois : le fichier qui porte la règle, et les lignes à y
    ajouter, dans leur ordre."""
    remedes = []
    for ligne in err.splitlines():
        m = REFUS.search(ligne)
        if m is None:
            continue
        texte = re.split(r", dans cet ordre| à ce fichier", m.group(2), maxsplit=1)[0]
        remede = (m.group(1), tuple(re.findall(r"`([^`]+)`", texte)))
        if remede not in remedes:
            remedes.append(remede)
    return remedes


def depot_de_la_matrice(racine: Path, cible: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Un dépôt neuf, ses fichiers examinés et plantés, ses réponses non suivies (le déclencheur)."""
    racine.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=racine, check=True, capture_output=True)
    examines, plantes = EXAMINES_PAR_CIBLE[cible], PLANTES_PAR_CIBLE[cible]
    for chemin in (*examines, *plantes):
        ecrire(racine, chemin)
    ecrire(racine, ".copier-answers.yml", REPONSES_PAR_CIBLE[cible])
    return examines, plantes


@pytest.mark.parametrize("regle", list(REGLES))
@pytest.mark.parametrize("cible", list(EXAMINES_PAR_CIBLE))
def test_matrice_des_remedes(tmp_path, git_isole, capsys, cible, regle):
    d = tmp_path / "depot"
    examines, plantes = depot_de_la_matrice(d, cible)
    dossier, regles = REGLES[regle]
    ecrire(d, ".gitignore" if dossier == "." else f"{dossier}/.gitignore", regles)
    plantes_masques = masques_parmi(d, plantes)
    tours = 0
    while masques.main(["--racine", str(d)]) != 0 and tours <= TOURS.get(regle, 1):
        tours += 1
        for source, lignes in remedes_a_la_lettre(capsys.readouterr().err):
            with (d / source).open("a", encoding="utf-8", newline="\n") as f:
                f.write("".join(f"{ligne}\n" for ligne in lignes))
    assert masques.main(["--racine", str(d)]) == 0, capsys.readouterr().err
    assert tours <= TOURS.get(regle, 1), f"{tours} tours"
    apres = masques_parmi(d, (*examines, *plantes))
    leves = sorted(plantes_masques - apres)
    assert not leves, f"plantés levés par un remède : {leves}"
    encore = sorted(apres & set(examines))
    assert not encore, f"examinés encore masqués : {encore}"


@pytest.mark.parametrize("cible", list(EXAMINES_PAR_CIBLE))
def test_la_matrice_plante_hors_de_ce_que_la_porte_examine(tmp_path, git_isole, cible):
    """Sous une liste blanche qui masque tout fichier, la porte voit exactement les fichiers
    examinés de la matrice : aucun fichier planté n'est examiné."""
    d = tmp_path / "depot"
    examines, _ = depot_de_la_matrice(d, cible)
    ecrire(d, ".gitignore", "*\n!*/\n")
    assert masques.fichiers_masques(d, masques.chemins_examines(d)) == sorted(examines)


@pytest.mark.parametrize(
    ("source", "dossier"),
    [
        (".gitignore", ""),
        ("secrets/.gitignore", "secrets/"),
        ("deploiement/secrets/.gitignore", "deploiement/secrets/"),
        (".git/info/exclude", ""),
        ("C:/Users/essai/.gitignore", ""),
        ("/home/essai/.gitignore", ""),
        ("~/.gitignore", ""),
    ],
)
def test_lignes_d_un_gitignore_imbrique(source, dossier):
    """Un .gitignore imbriqué lit ses lignes depuis son dossier : le remède y retire ce préfixe et
    garde le `/` de tête. La racine, `.git/info/exclude` et un fichier hors du dépôt lisent les leurs
    depuis la racine."""
    assert masques.dossier_de_la_regle(source) == dossier
    lignes = ["!/secrets/prod.env.enc", "/secrets/*"]
    attendu = ["!/prod.env.enc", "/*"] if dossier == "secrets/" else lignes
    assert [masques.relative(ligne, dossier) for ligne in lignes] == attendu
