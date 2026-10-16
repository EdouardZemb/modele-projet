"""Le garde de Claude : refuse push vers main, contournement des hooks, fusion avant contrôles verts."""

import json
import os
import subprocess
import sys

import garde_claude
import pytest
from conftest import SCRIPTS, depot, git

BRANCHE = "main"

# (commande, fragment de la raison, branche courante simulée, checks verts simulés)
REFUS = [
    ("git push origin main", "push vers main", "lot-1/x", True),
    ("git push origin HEAD:main", "push vers main", "lot-1/x", True),
    ("git push origin HEAD:refs/heads/main", "push vers main", "lot-1/x", True),
    ("git push --force origin main", "push vers main", "lot-1/x", True),
    ("git push origin +main", "push vers main", "lot-1/x", True),
    ("git push origin :main", "push vers main", "lot-1/x", True),
    ("git push origin --delete main", "push vers main", "lot-1/x", True),
    ("git push", "push vers main", "main", True),
    ("git push origin", "push vers main", "main", True),
    ("git push --all origin", "toutes les branches", "lot-1/x", True),
    ("git push --mirror origin", "toutes les branches", "lot-1/x", True),
    ("git push --no-verify origin lot-1/x", "sans hooks", "lot-1/x", True),
    ('git commit --no-verify -m "feat: x"', "sans hooks", "lot-1/x", True),
    ('git commit -nm "feat: x"', "sans hooks", "lot-1/x", True),
    ('git -c core.hooksPath=/dev/null commit -m "feat: x"', "hooks", "lot-1/x", True),
    ("cd sous-dossier && git push origin main", "push vers main", "lot-1/x", True),
    ("git push origin main; echo fini", "push vers main", "lot-1/x", True),
    ("gh pr merge 12 --squash", "contrôles", "lot-1/x", False),
    ("gh pr merge 12 --admin --squash", "contournant", "lot-1/x", True),
    ("gh api -X PUT repos/EdouardZemb/x/pulls/12/merge", "l'API", "lot-1/x", True),
    # variantes d'un agent qui cherche à passer
    ("git push origin main; Write-Host 'c''est fini'", "push vers main", "lot-1/x", True),
    ("git push origin main 'guillemet non fermé", "push vers main", "lot-1/x", True),
    ("git push origin HEAD", "push vers main", "main", True),
    ("git push origin HEAD", "push vers main", None, True),
    ("git push origin refs/heads/*:refs/heads/*", "push vers main", "lot-1/x", True),
    ("git push origin HEAD:heads/main", "push vers main", "lot-1/x", True),
    ("git push origin lot-1/x main", "push vers main", "lot-1/x", True),
    ("git push -o ci.skip origin main", "push vers main", "lot-1/x", True),
    ("git push --repo=origin --force main", "push vers main", "lot-1/x", True),
    ("git -C ../autre push origin main", "push vers main", "lot-1/x", True),
    ("git.exe push origin main", "push vers main", "lot-1/x", True),
    ("/usr/bin/git push origin main", "push vers main", "lot-1/x", True),
    ("GIT_TRACE=1 git push origin main", "push vers main", "lot-1/x", True),
    ("env git push origin main", "push vers main", "lot-1/x", True),
    ("echo ok && git push origin main", "push vers main", "lot-1/x", True),
    ("git status | cat\ngit push origin main", "push vers main", "lot-1/x", True),
    ("(git push origin main)", "push vers main", "lot-1/x", True),
    ("echo $(git push origin main)", "push vers main", "lot-1/x", True),
    ("echo `git push origin main`", "push vers main", "lot-1/x", True),
    ('bash -c "git push origin main"', "push vers main", "lot-1/x", True),
    ("pwsh -Command git push origin main", "push vers main", "lot-1/x", True),
    ("git push origin > sortie.txt", "push vers main", "main", True),
    ("git push 2>&1 origin", "push vers main", "main", True),
    ("git push --al origin", "toutes les branches", "lot-1/x", True),
    ("git push --no-ver origin lot-1/x", "sans hooks", "lot-1/x", True),
    ("git merge --no-verify lot-2", "sans hooks", "lot-1/x", True),
    ("git commit -a -n", "sans hooks", "lot-1/x", True),
    ("git commit -m x --no-verify", "sans hooks", "lot-1/x", True),
    ("git commit -anm x", "sans hooks", "lot-1/x", True),
    ("git --config-env=core.hooksPath=VIDE commit -m x", "hooks", "lot-1/x", True),
    ("git -c core.hookspath=/tmp push origin lot-1/x", "hooks", "lot-1/x", True),
    ("git config core.hooksPath /tmp", "hooks", "lot-1/x", True),
    ("GIT_CONFIG_KEY_0=core.hooksPath git commit -m x", "hooks", "lot-1/x", True),
    ("gh pr merge --admin 12", "contournant", "lot-1/x", True),
    ("gh pr merge 12 -R autre/depot", "contrôles", "lot-1/x", True),
    ("gh.exe pr merge 12", "contrôles", "lot-1/x", False),
    ("gh pr merge", "contrôles", "lot-1/x", False),
    ("gh api repos/o/x/pulls/12/merge -X PUT", "l'API", "lot-1/x", True),
    ("gh api repos/o/x/pulls/12/merge --method PUT", "l'API", "lot-1/x", True),
    ("gh api repos/o/x/pulls/12/merge -f merge_method=squash", "l'API", "lot-1/x", True),
    ("gh api -X PATCH repos/o/x/git/refs/heads/main -f sha=abc", "l'API", "lot-1/x", True),
    (
        "gh api graphql -f query='mutation { mergePullRequest(input: {}) { id } }'",
        "l'API",
        "lot-1/x",
        True,
    ),
]

ADMIS = [
    ("git push -u origin lot-1/x", "lot-1/x", True),
    ("git push origin lot-1/x --force-with-lease", "lot-1/x", True),
    ("git push", "lot-1/x", True),
    ("git push origin HEAD", "lot-1/x", True),
    ("git push origin HEAD:lot-1/x", "lot-1/x", True),
    ("git push origin main-bis", "lot-1/x", True),
    ("git status", "lot-1/x", True),
    ('git commit -m "feat: -n n\'est pas une option ici"', "lot-1/x", True),
    ("git commit -m -n", "lot-1/x", True),
    ("git commit -am 'feat: x'", "lot-1/x", True),
    ("git -c user.name=Essai commit -m x", "lot-1/x", True),
    ("git config user.name Essai", "lot-1/x", True),
    ("gh pr merge 12 --squash", "lot-1/x", True),
    ("gh pr view 12", "lot-1/x", True),
    ("gh pr checks 12", "lot-1/x", True),
    ("gh api repos/o/x/pulls/12", "lot-1/x", True),
    ("gh api graphql -f query='query { viewer { login } }'", "lot-1/x", True),
    ("echo main", "lot-1/x", True),
    ("echo git push origin main", "lot-1/x", True),
    ("", "lot-1/x", True),
]


def refus(commande, courante="lot-1/x", verts=True):
    return garde_claude.motif_de_refus(commande, BRANCHE, lambda chemin: courante, lambda pr: verts)


@pytest.mark.parametrize(("commande", "fragment", "courante", "verts"), REFUS)
def test_refus(commande, fragment, courante, verts):
    motif = refus(commande, courante, verts)
    assert motif is not None, commande
    assert fragment in motif, (commande, motif)


@pytest.mark.parametrize(("commande", "courante", "verts"), ADMIS)
def test_admis(commande, courante, verts):
    assert refus(commande, courante, verts) is None, commande


def test_cd_change_la_branche_courante():
    vus = []

    def courante(chemin):
        vus.append(chemin)
        return "main" if chemin == "ailleurs" else "lot-1/x"

    motif = garde_claude.motif_de_refus("cd ailleurs && git push", BRANCHE, courante, lambda pr: True)
    assert motif is not None
    assert "ailleurs" in vus


def test_checks_verts_recoit_l_argument_de_pr():
    vus = []

    def verts(pr):
        vus.append(pr)
        return True

    garde_claude.motif_de_refus("gh pr merge 12 --squash", BRANCHE, lambda c: "x", verts)
    garde_claude.motif_de_refus("gh pr merge --squash", BRANCHE, lambda c: "x", verts)
    assert vus == ["12", None]


def test_jamais_d_exception():
    commandes = ["'", '"', "git push origin '", "a && ", "|| ;", "\x00", "git -C", "git -c"]
    for commande in [*commandes, "git push -o", "gh pr merge -b", "gh api", "bash -c"]:
        refus(commande)


def lancer(entree, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "garde_claude.py"), *args],
        input=entree.encode("utf-8"),
        capture_output=True,
        check=False,
    )


def test_cli_bloque():
    entree = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": "."}
    )
    r = lancer(entree, "--branche", "main")
    assert r.returncode == 2
    erreur = r.stderr.decode("utf-8")
    assert "refusé — push vers main" in erreur
    assert "docs/modele/methode.md" in erreur


def test_cli_powershell_bloque():
    entree = json.dumps(
        {"tool_name": "PowerShell", "tool_input": {"command": "git push origin main"}, "cwd": "."}
    )
    assert lancer(entree, "--branche", "main").returncode == 2


def test_cli_admet():
    entree = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "."})
    assert lancer(entree, "--branche", "main").returncode == 0


def test_cli_autre_outil():
    entree = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}, "cwd": "."})
    assert lancer(entree, "--branche", "main").returncode == 0


def test_cli_json_illisible():
    assert lancer("pas du json", "--branche", "main").returncode == 1
    assert lancer("[1, 2]", "--branche", "main").returncode == 1


def test_cli_sans_reglages_ni_branche():
    entree = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "."})
    assert lancer(entree).returncode == 64


def faux_gh(dossier, sortie):
    """Un faux « gh » qui imprime `sortie`, placé dans `dossier`."""
    if sys.platform == "win32":
        f = dossier / "gh.cmd"
        f.write_text(f"@echo off\r\necho {sortie}\r\n", encoding="utf-8")
    else:
        f = dossier / "gh"
        f.write_text(f"#!/bin/sh\necho '{sortie}'\n", encoding="utf-8")
        f.chmod(0o755)
    return f


@pytest.mark.parametrize(
    ("sortie", "attendu"),
    [
        ("[]", False),
        ('[{"bucket":"pass"},{"bucket":"skipping"}]', True),
        ('[{"bucket":"pass"},{"bucket":"pending"}]', False),
        ('[{"bucket":"pass"},{"bucket":"fail"}]', False),
        ("pas du json", False),
        ('{"bucket":"pass"}', False),
    ],
)
def test_checks_verts_gh(tmp_path, monkeypatch, sortie, attendu):
    faux_gh(tmp_path, sortie)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert garde_claude.checks_verts_gh("12", str(tmp_path)) is attendu


def test_checks_verts_gh_liste_vide(tmp_path, monkeypatch):
    faux_gh(tmp_path, "[]")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert garde_claude.checks_verts_gh(None, str(tmp_path)) is False


def test_checks_verts_gh_sans_gh(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert garde_claude.checks_verts_gh("12", str(tmp_path)) is False


def test_branche_courante_git(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a").write_text("a", encoding="utf-8")
    git(d, env, "add", "a")
    git(d, env, "commit", "-q", "-m", "chore: a")
    assert garde_claude.branche_courante_git(None, str(d)) == "main"
    assert garde_claude.branche_courante_git(str(d), str(tmp_path)) == "main"
    assert garde_claude.branche_courante_git("inexistant", str(d)) is None


def test_settings_rendu(rendre):
    racine = rendre()
    chemin = racine / ".claude/settings.json"
    reglage = json.loads(chemin.read_text(encoding="utf-8"))
    crochet = reglage["hooks"]["PreToolUse"][0]
    assert crochet["matcher"] == "Bash|PowerShell"
    commande = crochet["hooks"][0]["command"]
    assert "lancer.sh" in commande
    assert "garde_claude.py" in commande
    assert b"\r" not in chemin.read_bytes()
