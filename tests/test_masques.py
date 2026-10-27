"""masques.py : un fichier que le modèle écrit ne doit pas être masqué par le .gitignore du projet."""

import fnmatch
import re
from pathlib import Path

import masques
import pytest
import yaml
from conftest import RACINE, REPONSES_SERVEUR, git

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


def test_cible_illisible_vaut_serveur(depot_masque):
    ecrire(depot_masque, ".copier-answers.yml", "_commit: v0.2.3\n")
    assert masques.cible_serveur(depot_masque) is True
    ecrire(depot_masque, ".copier-answers.yml", "cible: aucune\n")
    assert masques.cible_serveur(depot_masque) is False
    (depot_masque / ".copier-answers.yml").unlink()
    assert masques.cible_serveur(depot_masque) is True


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


@pytest.mark.parametrize("reponses", [{}, REPONSES_SERVEUR], ids=["aucune", "serveur"])
def test_chemins_couvrent_le_rendu(rendre, reponses):
    """Chaque fichier géré du rendu (tout ce que `_skip_if_exists` ne sème pas) est examiné."""
    semes = set(yaml.safe_load(lire(RACINE / "copier.yml"))["_skip_if_exists"])
    chemins = masques.CHEMINS_COMMUNS + (masques.CHEMINS_SERVEUR if reponses else ())
    rendu = rendre(**reponses)
    geres = [p.relative_to(rendu).as_posix() for p in sorted(rendu.rglob("*")) if p.is_file()]
    geres = [g for g in geres if g not in semes]
    assert geres
    assert [g for g in geres if not couvert(g, chemins)] == []
