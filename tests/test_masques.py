"""masques.py : un fichier que le modèle écrit ne doit pas être masqué par le .gitignore du projet."""

import fnmatch
import re
from pathlib import Path

import masques
import pytest
import yaml
from conftest import RACINE, REPONSES_DONNEES_SERVEUR, REPONSES_SERVEUR, git

METHODE = RACINE / "template/docs/modele/methode.md"
GERE = "scripts/modele/verifier_secrets.py"
AUTRE_REMEDE = (
    "Si ce fichier n'est pas du modèle (un fichier local), le sortir de ce dossier ; "
    "ne jamais lever le masque d'un fichier de secrets."
)


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def ecrire(racine: Path, chemin: str, texte: str = "x\n") -> None:
    cible = racine / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8", newline="\n")


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
    assert "Ajouter `!secrets/` à ce fichier, puis indexer le fichier." in err
    # Le .gitignore d'un dépôt de données : l'instance passe, les secrets en clair restent dehors.
    ecrire(
        depot_masque,
        ".gitignore",
        GITIGNORE_A_UN_DEPOT
        + "!env/prod.env\n!env/staging.env\n!secrets/\nsecrets/*\n!secrets/*.env.enc\n",
    )
    assert masques.main(["--racine", str(depot_masque)]) == 0


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
    un motif `*` se compare par fnmatch, tout autre chemin se compare tel quel."""
    for chemin in chemins:
        if chemin.endswith("/"):
            if fichier.startswith(chemin):
                return True
        elif "*" in chemin:
            if fnmatch.fnmatchcase(fichier, chemin):
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
