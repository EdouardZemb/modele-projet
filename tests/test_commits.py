"""Tests du contrôle du format des commits (Conventional Commits)."""

import subprocess
import sys

import commits as k
import pytest
from conftest import SCRIPTS, depot, git

SCRIPT = SCRIPTS / "commits.py"
FORME = "type(portée): sujet"


def lancer(args, env, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
        cwd=cwd,
    )


@pytest.mark.parametrize(
    "entete",
    [
        "feat: ajoute la porte",
        "fix(ci): épingle checkout",
        "feat!: rompt le contrat",
        "feat(api)!: rompt le contrat",
        "docs: CLAUDE.md ne fige plus la version",
        "chore: Majuscule au sujet",
    ],
)
def test_entetes_conformes(entete):
    assert k.verifier_entete(entete) is None


@pytest.mark.parametrize(
    "entete",
    ["Ajoute la porte", "feat:sans espace", "feature: x", "feat(Ci): x", "feat: ", "", "feat():x"],
)
def test_entetes_refuses(entete):
    raison = k.verifier_entete(entete)
    assert raison is not None
    assert FORME in raison


def test_longueur():
    base = "feat: "
    valide = base + "x" * (100 - len(base))
    assert len(valide) == 100
    assert k.verifier_entete(valide) is None
    trop = valide + "x"
    assert "100 caractères (101)" in k.verifier_entete(trop)


@pytest.mark.parametrize(
    "entete",
    [
        "Merge branch 'x'",
        'Revert "feat: x"',
        "fixup! feat: x",
        "squash! feat: x",
        "amend! feat: x",
    ],
)
def test_exemptions(entete):
    assert k.verifier_entete(entete) is None


def test_commentaires_ignores():
    assert k.entete_du_message("# commentaire\nfeat: x\n") == "feat: x"
    assert k.entete_du_message("feat: x  \r\n\r\ncorps\n") == "feat: x"
    assert k.entete_du_message("# seulement\n") == ""


def test_plage(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    git(d, env, "commit", "-q", "--allow-empty", "-m", "feat: base")
    git(d, env, "commit", "-q", "--allow-empty", "-m", "feat: bien formé")
    git(d, env, "commit", "-q", "--allow-empty", "-m", "Mal formé")
    fautif = git(d, env, "rev-parse", "--short", "HEAD").strip()
    r = lancer(["--plage", "HEAD~2..HEAD"], env, d)
    assert r.returncode == 1
    assert fautif in r.stderr
    assert "Mal formé" not in r.stderr
    assert lancer(["--plage", "HEAD~2..HEAD~1"], env, d).returncode == 0


def test_plage_invalide_echoue_ferme(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    git(d, env, "commit", "-q", "--allow-empty", "-m", "feat: base")
    assert lancer(["--plage", "nexistepas..HEAD"], env, d).returncode == 64
    assert lancer(["--plage", "-x"], env, d).returncode == 64
    assert lancer(["--plage", ""], env, d).returncode == 64


def test_message(tmp_path, env_isole):
    env = env_isole()
    f = tmp_path / "msg.txt"
    f.write_bytes(b"\xef\xbb\xbf# note\r\nfeat: ok\r\n\r\ncorps\r\n")
    assert lancer(["--message", str(f)], env).returncode == 0
    f.write_bytes(b"Pas bon\n")
    r = lancer(["--message", str(f)], env)
    assert r.returncode == 1
    assert FORME in r.stderr
    f.write_bytes(b"")
    assert lancer(["--message", str(f)], env).returncode == 1
    assert lancer(["--message", str(tmp_path / "absent")], env).returncode == 64


def test_titre(env_isole):
    assert lancer(["--titre", "feat: x"], env_isole()).returncode == 0
    assert lancer(["--titre", "x"], env_isole()).returncode == 1


def test_usage(env_isole):
    assert lancer([], env_isole()).returncode == 64
    assert lancer(["--titre", "x", "--plage", "a..b"], env_isole()).returncode == 64
