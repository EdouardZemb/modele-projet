"""La mise à jour par Copier propage le géré et préserve le semé (spec §8, critère 3)."""

import shutil

import copier
import yaml
from conftest import RACINE, REPONSES_PAR_DEFAUT, REPONSES_SERVEUR, git

IGNORES = shutil.ignore_patterns(
    ".git", ".superpowers", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv"
)
LIGNE_PROJET = "Ligne ajoutée par le projet"
LIGNE_MODELE = "Ligne ajoutée en v0.0.2"


def _modele_v1(tmp_path, env):
    modele = tmp_path / "modele"
    shutil.copytree(RACINE, modele, ignore=IGNORES)
    git(modele, env, "init", "-q", "-b", "main")
    git(modele, env, "config", "core.autocrlf", "false")
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.1")
    git(modele, env, "tag", "v0.0.1")
    return modele


def _projet_v1(tmp_path, env, modele, reponses=REPONSES_PAR_DEFAUT):
    projet = tmp_path / "projet"
    copier.run_copy(
        str(modele),
        str(projet),
        data=reponses,
        defaults=True,
        vcs_ref="v0.0.1",
        quiet=True,
    )
    git(projet, env, "init", "-q", "-b", "main")
    git(projet, env, "config", "core.autocrlf", "false")
    git(projet, env, "add", "-A")
    git(projet, env, "commit", "-q", "-m", "etat initial")
    return projet


def test_mise_a_jour_propage_et_preserve(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)

    with (projet / "CLAUDE.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n{LIGNE_PROJET}\n")
    git(projet, env, "commit", "-q", "-am", "claude du projet")

    with (modele / "template/docs/modele/methode.md").open(
        "a", encoding="utf-8", newline="\n"
    ) as f:
        f.write(f"\n{LIGNE_MODELE}\n")
    git(modele, env, "commit", "-q", "-am", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")

    copier.run_update(
        str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.2", quiet=True
    )

    assert LIGNE_MODELE in (projet / "docs/modele/methode.md").read_text(encoding="utf-8")
    assert LIGNE_PROJET in (projet / "CLAUDE.md").read_text(encoding="utf-8")
    assert not list(projet.rglob("*.rej"))
    for chemin in projet.rglob("*"):
        if chemin.is_file() and ".git" not in chemin.relative_to(projet).parts:
            try:
                texte = chemin.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert "<<<<<<<" not in texte, chemin
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["_commit"] == "v0.0.2"


def test_mise_a_jour_sans_changement(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)

    copier.run_update(
        str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.1", quiet=True
    )

    assert git(projet, env, "status", "--porcelain").strip() == ""


def _modele_v2(modele, env):
    """Une v0.0.2 sans autre changement que l'étiquette : seul le changement de cible compte."""
    git(modele, env, "commit", "-q", "--allow-empty", "-m", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")


def _sans_conflit(projet):
    assert not list(projet.rglob("*.rej"))
    for chemin in projet.rglob("*"):
        if chemin.is_file() and ".git" not in chemin.relative_to(projet).parts:
            try:
                texte = chemin.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert "<<<<<<<" not in texte, chemin


def test_passage_en_cible_serveur(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)
    claude = (projet / "CLAUDE.md").read_bytes()
    registre = (projet / "docs/registre.md").read_bytes()
    assert not (projet / "deploiement").exists()
    _modele_v2(modele, env)

    copier.run_update(
        str(projet),
        data={"cible": "serveur", "bloc_ports": 4310, "sauvegardes": True, "fusion": "session"},
        defaults=True,
        overwrite=True,
        vcs_ref="v0.0.2",
        quiet=True,
    )

    assert (projet / "deploiement/lib.sh").is_file()
    assert (projet / "deploiement/projet.env").is_file()
    assert (projet / ".sops.yaml").is_file()
    assert (projet / "docs/modele/decisions/M-0003-contrat-de-l-image.md").is_file()
    assert (projet / "CLAUDE.md").read_bytes() == claude
    assert (projet / "docs/registre.md").read_bytes() == registre
    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["cible"] == "serveur"
    assert reponses["bloc_ports"] == 4310


def test_retour_en_cible_aucune(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele, REPONSES_SERVEUR)
    assert (projet / "deploiement/projet.env").is_file()
    assert (projet / ".sops.yaml").is_file()
    lib = projet / "deploiement/lib.sh"
    for retouche in (projet / "deploiement/projet.env", lib):
        with retouche.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n# {LIGNE_PROJET}\n")
    git(projet, env, "commit", "-q", "-am", "retouches du projet")
    _modele_v2(modele, env)

    copier.run_update(
        str(projet),
        data={"cible": "aucune", "fusion": "session"},
        defaults=True,
        overwrite=True,
        vcs_ref="v0.0.2",
        quiet=True,
    )

    # Le géré de l'ancienne cible disparaît, retouché ou non.
    assert not lib.exists()
    assert not (projet / ".sops.yaml").exists()
    # Écart au §8 de la spec : Copier supprime aussi les semés de l'ancienne cible, dossier
    # compris, retouchés ou non (observé avec Copier 9.19.1).
    assert not (projet / "deploiement").exists()
    assert not (projet / "tests/deploiement").exists()
    assert not (projet / "docs/exploitation.md").exists()
    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["cible"] == "aucune"
