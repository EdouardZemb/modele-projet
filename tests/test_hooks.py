"""Les hooks git d'un projet rendu : confidentialité, format des commits, branche principale."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pre_push
import pytest
import yaml
from conftest import RACINE, git

SH = shutil.which("sh") or (
    r"C:\Program Files\Git\bin\sh.exe" if Path(r"C:\Program Files\Git\bin\sh.exe").exists() else None
)
MOTIF = "motif-interdit-essai"
HOOKS = ("pre-commit", "commit-msg", "pre-push")


@pytest.fixture
def projet(rendre, env_isole):
    """Un projet rendu, dépôt git initialisé avec les hooks du modèle, et son environnement."""
    racine = rendre()
    env = {**env_isole(), "MOTIFS_INTERDITS": MOTIF}
    git(racine, env, "init", "-q", "-b", "main")
    git(racine, env, "config", "core.autocrlf", "false")
    git(racine, env, "config", "core.hooksPath", ".githooks")
    return racine, env


def lancer_git(racine, env, *args):
    return subprocess.run(
        ["git", *args],
        check=False,
        cwd=racine,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_hooks_lf_et_executables(rendre):
    racine = rendre()
    fichiers = [racine / ".githooks" / h for h in HOOKS] + [racine / "scripts/modele/lancer.sh"]
    for f in fichiers:
        assert b"\r" not in f.read_bytes(), f.name
    if sys.platform != "win32":
        for h in HOOKS:
            assert os.access(racine / ".githooks" / h, os.X_OK), h


@pytest.mark.skipif(not (RACINE / ".git").exists(), reason="pas de dépôt git autour du modèle")
def test_hooks_du_modele_executables_dans_l_index():
    # Sous Windows, `git add` d'un fichier recréé enregistre 100644, et Linux n'exécuterait plus
    # le hook. L'index fait foi, quel que soit le système de fichiers.
    r = subprocess.run(
        ["git", "ls-files", "-s", "--", ".githooks", "template/.githooks"],
        check=True,
        cwd=RACINE,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    modes = {ligne.split("\t", 1)[1]: ligne.split(" ", 1)[0] for ligne in r.stdout.splitlines()}
    attendus = {f"{d}/{h}" for d in (".githooks", "template/.githooks") for h in HOOKS}
    assert attendus <= set(modes), "hook absent de l'index : le test passerait à vide"
    for chemin, mode in sorted(modes.items()):
        assert mode == "100755", chemin


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_lancer_trouve_un_python(rendre):
    racine = rendre()
    r = subprocess.run(
        [SH, str(racine / "scripts/modele/lancer.sh"), "-c", "import sys; print(sys.version_info[0])"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "3"


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_commit_message_invalide_refuse(projet):
    racine, env = projet
    git(racine, env, "add", "-A")
    r = lancer_git(racine, env, "commit", "-m", "Ajoute x")
    assert r.returncode != 0
    assert "type(portée): sujet" in r.stderr


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_commit_motif_prive_refuse(projet):
    racine, env = projet
    (racine / "note.txt").write_text(f"voici {MOTIF} ici\n", encoding="utf-8")
    git(racine, env, "add", "-A")
    r = lancer_git(racine, env, "commit", "-m", "feat: essai")
    assert r.returncode != 0
    assert "motif privé n°1" in r.stderr
    assert MOTIF not in r.stderr + r.stdout


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_commit_conforme_accepte(projet):
    racine, env = projet
    git(racine, env, "add", "-A")
    r = lancer_git(racine, env, "commit", "-m", "feat: premier essai")
    assert r.returncode == 0, r.stderr


@pytest.fixture
def projet_avec_origin(projet, tmp_path):
    racine, env = projet
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, env, "init", "-q", "--bare", "-b", "main")
    git(racine, env, "add", "-A")
    git(racine, env, "commit", "-q", "--no-verify", "-m", "feat: base")
    git(racine, env, "remote", "add", "origin", str(origin))
    git(racine, env, "push", "-q", "--no-verify", "origin", "main")
    # Un commit de plus : sans lui, « git push origin main » dirait « up-to-date » sans appeler le hook.
    git(racine, env, "commit", "-q", "--no-verify", "--allow-empty", "-m", "feat: suite")
    return racine, env


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_push_vers_branche_principale_refuse(projet_avec_origin):
    racine, env = projet_avec_origin
    r = lancer_git(racine, env, "push", "origin", "main")
    assert r.returncode != 0
    assert "envoi refusé vers refs/heads/main" in r.stderr


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_push_branche_de_travail_accepte(projet_avec_origin):
    racine, env = projet_avec_origin
    r = lancer_git(racine, env, "push", "origin", "HEAD:refs/heads/lot-1/essai")
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_suppression_branche_principale_refusee(projet_avec_origin):
    racine, env = projet_avec_origin
    r = lancer_git(racine, env, "push", "origin", ":main")
    assert r.returncode != 0
    assert "envoi refusé vers refs/heads/main" in r.stderr


def test_refs_refusees():
    assert pre_push.refs_refusees("refs/heads/x 1 refs/heads/main 2\n", "main") == ["refs/heads/main"]
    assert pre_push.refs_refusees("refs/heads/x 1 refs/heads/lot-1/x 2\n", "main") == []


def test_branche_rendue(rendre):
    racine = rendre(branche_principale="principal")
    texte = (racine / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'BRANCHE_PRINCIPALE = "principal"' in texte


def test_entree_mal_formee_refusee(monkeypatch, capsys):
    import io

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"trop court\n")))
    assert pre_push.main(["--branche", "main"]) == 1
    assert "ligne d'entrée mal formée, envoi refusé" in capsys.readouterr().err
    assert pre_push.refs_refusees("\r\n\nrefs/heads/x 1 refs/heads/y 2\r\n", "main") == []


def test_visibilite_rendue(rendre):
    for visibilite in ("prive", "public"):
        reglages = rendre(visibilite=visibilite) / "scripts/modele/reglages.py"
        assert f'VISIBILITE = "{visibilite}"' in reglages.read_text(encoding="utf-8")


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_commit_prive_avertit_sans_refuser(rendre, env_isole):
    racine = rendre(visibilite="prive")
    env = {**env_isole(), "MOTIFS_INTERDITS": MOTIF}
    git(racine, env, "init", "-q", "-b", "main")
    git(racine, env, "config", "core.autocrlf", "false")
    git(racine, env, "config", "core.hooksPath", ".githooks")
    (racine / "note.txt").write_text(f"voici {MOTIF} ici\n", encoding="utf-8")
    git(racine, env, "add", "-A")
    r = lancer_git(racine, env, "commit", "-m", f"feat: essai {MOTIF}")
    assert r.returncode == 0, r.stderr
    assert "note.txt:1 — motif privé n°1" in r.stderr
    assert "dépôt privé : avertissement, pas de refus" in r.stderr
    assert MOTIF not in r.stderr.replace(f"feat: essai {MOTIF}", "")


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_aucun_cache_python(rendre, env_isole, tmp_path):
    """Hooks et garde importent reglages : rien ne doit rester dans scripts/modele/ (ancrage, 17/10)."""
    racine = rendre()
    env = {**env_isole(), "MOTIFS_INTERDITS": MOTIF}
    env.pop("PYTHONDONTWRITEBYTECODE", None)  # c'est lancer.sh qui doit le poser
    git(racine, env, "init", "-q", "-b", "main")
    git(racine, env, "config", "core.autocrlf", "false")
    git(racine, env, "config", "core.hooksPath", ".githooks")
    git(racine, env, "add", "-A")
    r = lancer_git(racine, env, "commit", "-q", "-m", "feat: base")
    assert r.returncode == 0, r.stderr
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, env, "init", "-q", "--bare", "-b", "main")
    git(racine, env, "remote", "add", "origin", str(origin))
    r = lancer_git(racine, env, "push", "-q", "origin", "HEAD:refs/heads/lot-1/essai")
    assert r.returncode == 0, r.stderr

    reglage = json.loads((racine / ".claude/settings.json").read_text(encoding="utf-8"))
    commande = reglage["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    env_garde = {**env, "CLAUDE_PROJECT_DIR": racine.as_posix()}
    for essai, attendu in (("git status", 0), ("git push origin main", 2)):
        entree = {"tool_name": "Bash", "tool_input": {"command": essai}, "cwd": str(racine)}
        r = subprocess.run(
            [SH, "-c", commande],
            input=json.dumps(entree),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env_garde,
            cwd=racine,
            check=False,
        )
        assert r.returncode == attendu, (essai, r.stderr)

    assert list(racine.rglob("__pycache__")) == []
    assert lancer_git(racine, env, "status", "--porcelain", "--ignored").stdout == ""


def test_gitignore_des_scripts_gere(rendre):
    """Géré (pas semé) : il atteint les projets alignés à leur prochain copier update."""
    copier_yml = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))
    assert "scripts/modele/.gitignore" not in copier_yml["_skip_if_exists"]
    assert (rendre() / "scripts/modele/.gitignore").read_bytes() == b"__pycache__/\n"


def test_pre_commit_lance_les_masques(rendre):
    """Le pre-commit lance la porte des fichiers masqués avant la confidentialité (LE-23)."""
    hook = (rendre() / ".githooks/pre-commit").read_text(encoding="utf-8")
    assert "scripts/modele/masques.py" in hook
    assert hook.index("masques.py") < hook.index("confidentialite.py")
