"""Le garde de Claude : refuse push vers main, contournement des hooks, fusion avant contrôles verts."""

import json
import os
import subprocess
import sys

import garde_claude
import pytest
from conftest import SCRIPTS, depot, faux_gh, faux_gh_lent, git

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
    # revue finale du lot 1 (I2) : une ligne par forme
    # a. substitution dans des guillemets doubles, réanalysée comme une commande
    ('x="$(gh pr merge 12 --squash)"', "contrôles", "lot-1/x", False),
    ('echo "$(git commit --no-verify -m x)"', "sans hooks", "lot-1/x", True),
    ('echo "`git push origin main`"', "push vers main", "lot-1/x", True),
    ('Write-Output "$(git push --no-verify origin lot-1/x)"', "sans hooks", "lot-1/x", True),
    # b. core.hooksPath dans n'importe quel jeton ; configuration git par l'environnement
    (
        "$env:GIT_CONFIG_COUNT=1; $env:GIT_CONFIG_KEY_0='core.hooksPath'; "
        + "$env:GIT_CONFIG_VALUE_0='x'; git commit -m x",
        "hooks",
        "lot-1/x",
        True,
    ),
    (
        "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/tmp/v; "
        + "git commit -m x",
        "hooks",
        "lot-1/x",
        True,
    ),
    ("export GIT_CONFIG_PARAMETERS=\"'core.hookspath=/tmp'\"; git commit -m x", "hooks", "lot-1/x", True),
    ("Set-Item env:GIT_CONFIG_COUNT 1; git commit -m x", "hooks", "lot-1/x", True),
    ("set GIT_CONFIG_PARAMETERS='core.hookspath=x'", "hooks", "lot-1/x", True),
    ("$env:git_config_count=1; git commit -m x", "hooks", "lot-1/x", True),
    ('sed -i "s/hooksPath = .githooks/hooksPath = x/" .git/config', "hooks", "lot-1/x", True),
    ("git commit -m x --template core.hooksPath", "hooks", "lot-1/x", True),
    # c. interprètes et enveloppes PowerShell, listes d'arguments, timeout, env -u
    (
        "Start-Process git -ArgumentList 'push','--no-verify','origin','lot-1/x' -Wait",
        "sans hooks",
        "lot-1/x",
        True,
    ),
    ("Start-Process gh -ArgumentList 'pr','merge','12'", "fusion", "lot-1/x", False),
    ("saps git -ArgumentList 'commit','--no-verify','-m','x'", "sans hooks", "lot-1/x", True),
    ("git push origin lot-1/x,main", "push vers main", "lot-1/x", True),
    ('iex "git push --no-verify origin lot-1/x"', "sans hooks", "lot-1/x", True),
    ('Invoke-Expression "git commit --no-verify -m x"', "sans hooks", "lot-1/x", True),
    ("timeout 60 git push --no-verify origin lot-1/x", "sans hooks", "lot-1/x", True),
    ("timeout -s KILL 60 git push origin main", "push vers main", "lot-1/x", True),
    ("env -u GIT_DIR git commit --no-verify -m x", "sans hooks", "lot-1/x", True),
    # d. alias et extensions de gh
    ("gh alias set m 'pr merge'", "alias gh", "lot-1/x", True),
    ("gh alias set --shell m 'gh pr merge \"$1\" --squash'", "alias gh", "lot-1/x", True),
    ("gh alias import alias.yml", "alias gh", "lot-1/x", True),
    ("gh m 12 --squash", "commande gh inconnue", "lot-1/x", True),
    # e. le jeton de gh, qui ouvrirait l'API sans passer par gh
    ("gh auth token", "jeton gh", "lot-1/x", True),
    ("gh auth status --show-token", "jeton gh", "lot-1/x", True),
    ("gh auth status -t", "jeton gh", "lot-1/x", True),
    ("gh auth status -at --hostname github.com", "jeton gh", "lot-1/x", True),
    # effacer, déplacer ou renommer .githooks ou scripts/modele
    ("rm -rf .githooks && git commit -m x", "garde-fous", "lot-1/x", True),
    ("Remove-Item -Recurse .githooks", "garde-fous", "lot-1/x", True),
    ("git rm -r scripts/modele", "garde-fous", "lot-1/x", True),
    ("mv .githooks .h", "garde-fous", "lot-1/x", True),
    ("rm ./.githooks/pre-commit", "garde-fous", "lot-1/x", True),
    (r"Remove-Item C:\x\.githooks\pre-commit", "garde-fous", "lot-1/x", True),
    (r"rd /s /q .githooks", "garde-fous", "lot-1/x", True),
    (r"ri -Recurse -Force scripts\modele", "garde-fous", "lot-1/x", True),
    (r"del .githooks\pre-push", "garde-fous", "lot-1/x", True),
    ("erase .githooks/commit-msg", "garde-fous", "lot-1/x", True),
    ("rmdir .GITHOOKS", "garde-fous", "lot-1/x", True),
    ("rm -rf scripts", "garde-fous", "lot-1/x", True),
    ("git mv scripts/modele/garde_claude.py x.py", "garde-fous", "lot-1/x", True),
    ("Rename-Item .githooks hooks-off", "garde-fous", "lot-1/x", True),
    ("rni scripts/modele/lancer.sh x.sh", "garde-fous", "lot-1/x", True),
    ("Move-Item -Path:scripts/modele -Destination ailleurs", "garde-fous", "lot-1/x", True),
    ("mi .githooks ailleurs", "garde-fous", "lot-1/x", True),
    (r"move .githooks C:\ailleurs", "garde-fous", "lot-1/x", True),
    ("ren .githooks h", "garde-fous", "lot-1/x", True),
    ('bash -c "rm -rf .githooks"', "garde-fous", "lot-1/x", True),
    # ce qui affiche les identifiants enregistrés
    ("git credential fill", "identifiants", "lot-1/x", True),
    ("printf 'protocol=https' | git credential fill", "identifiants", "lot-1/x", True),
    ("git credential-manager get", "identifiants", "lot-1/x", True),
    ("git-credential-manager.exe get", "identifiants", "lot-1/x", True),
    ("gh auth git-credential get", "identifiants", "lot-1/x", True),
    # here-string : pour un interprète, le texte est une commande
    ("bash <<< 'git commit --no-verify -m x'", "sans hooks", "lot-1/x", True),
    ('sh <<<"git push origin main"', "push vers main", "lot-1/x", True),
    ("pwsh -NoProfile <<< 'git push --no-verify origin lot-1/x'", "sans hooks", "lot-1/x", True),
    ("xargs git commit <<< --no-verify", "sans hooks", "lot-1/x", True),
    ('cat <<< "$(git push origin main)"', "push vers main", "lot-1/x", True),
    (
        'curl -X PUT -H "Authorization: token $(gh auth token)" '
        + "https://api.github.com/repos/o/r/pulls/12/merge",
        "jeton gh",
        "lot-1/x",
        True,
    ),
    # étiquettes et publications : à Edouard, dans les deux modes
    ("git push origin v1.2.0", "étiquette ou publication", "lot-1/x", True),
    ("git push origin refs/tags/v1.2.0", "étiquette ou publication", "lot-1/x", True),
    ("git push --tags", "étiquette ou publication", "lot-1/x", True),
    ("git push --follow-tags origin lot-2/x", "étiquette ou publication", "lot-1/x", True),
    ("git push origin HEAD:refs/tags/x", "étiquette ou publication", "lot-1/x", True),
    ("gh release create v1.2.0", "étiquette ou publication", "lot-1/x", True),
    ("gh release upload v1.2.0 f", "étiquette ou publication", "lot-1/x", True),
    ("gh release edit v1.2.0", "étiquette ou publication", "lot-1/x", True),
    ("gh release delete v1.2.0", "étiquette ou publication", "lot-1/x", True),
    ("gh api -X POST repos/o/d/releases", "étiquette ou publication", "lot-1/x", True),
    ("git push origin tag release-1", "étiquette ou publication", "lot-1/x", True),
    ("git push origin v1.2.0-rc1", "étiquette ou publication", "lot-1/x", True),
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
    # revue finale du lot 1
    ("git config --get core.hooksPath", "lot-1/x", True),
    ("git -C ../autre config --get core.hooksPath", "lot-1/x", True),
    ("git config --list", "lot-1/x", True),
    ("gh help", "lot-1/x", True),
    ("gh --version", "lot-1/x", True),
    ("gh auth status", "lot-1/x", True),
    ("gh auth status --active --hostname github.com", "lot-1/x", True),
    ("rm -rf node_modules", "lot-1/x", True),
    ("cat .githooks/pre-commit", "lot-1/x", True),
    ("rm scripts/build.sh", "lot-1/x", True),
    ("git rm docs/vieux.md", "lot-1/x", True),
    ("mv a.txt b.txt", "lot-1/x", True),
    ("Remove-Item -Recurse dist", "lot-1/x", True),
    ("git mv scripts/a.sh scripts/b.sh", "lot-1/x", True),
    ("rm -rf apps/web/scripts", "lot-1/x", True),
    ("cat <<< 'git push origin main'", "lot-1/x", True),
    ("git credential-manager --version", "lot-1/x", True),
    ("git config --get credential.helper", "lot-1/x", True),
    ("grep -c x <<< 'texte'", "lot-1/x", True),
    ("bash <<< 'git status'", "lot-1/x", True),
    ("mv tools/scripts tools/bin", "lot-1/x", True),
    ("gh alias list", "lot-1/x", True),
    ("gh co 12", "lot-1/x", True),
    ("timeout 5 git status", "lot-1/x", True),
    ('git commit -m "feat: a, b"', "lot-1/x", True),
    ('echo "$(git status)"', "lot-1/x", True),
    # les étiquettes se posent en local, les publications se lisent
    ("git tag v1.2.0", "lot-1/x", True),
    ("git push origin lot-2/x", "lot-1/x", True),
    ("gh release view v0.1.1", "lot-1/x", True),
    ("gh release list", "lot-1/x", True),
    ("gh api repos/o/d/releases", "lot-1/x", True),
    ("git push origin modele/alignement", "lot-1/x", True),
]


def refus(commande, courante="lot-1/x", verts=True, fusion=lambda d: "session"):
    return garde_claude.motif_de_refus(
        commande, BRANCHE, lambda chemin: courante, lambda pr: verts, fusion=fusion
    )


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

    garde_claude.motif_de_refus(
        "gh pr merge 12 --squash", BRANCHE, lambda c: "x", verts, fusion=lambda d: "session"
    )
    garde_claude.motif_de_refus(
        "gh pr merge --squash", BRANCHE, lambda c: "x", verts, fusion=lambda d: "session"
    )
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


# Les outils qui lancent une commande hors de Bash et de PowerShell (revue finale du lot 1, I1).
REFUS_OUTILS = [
    ("Monitor", {"command": "git commit --no-verify -m x"}, "sans hooks"),
    ("Monitor", {"command": "echo `git push origin main`", "description": "x"}, "push vers main"),
    ("mcp__desktop-commander__start_process", {"command": "git push origin main", "timeout_ms": 1}, "push vers main"),
    ("mcp__desktop-commander__start_process", {"command": "git commit --no-verify -m x"}, "sans hooks"),
    ("mcp__desktop-commander__interact_with_process", {"pid": 1, "input": "git push --no-verify"}, "sans hooks"),
    ("mcp__autre__shell", {"cmd": "Start-Process git -ArgumentList 'push','--no-verify'"}, "sans hooks"),
    ("mcp__autre__script", {"script": "git -c core.hooksPath=/dev/null commit -m x"}, "hooks"),
    # un argv est joint par des espaces ; tout autre type non chaîne est refusé
    ("mcp__autre__shell", {"command": ["git", "commit", "--no-verify", "-m", "x"]}, "sans hooks"),
    ("mcp__autre__outil", {"command": ["git", "push", "origin", "main"]}, "push vers main"),
    # Bash, PowerShell et Monitor : la commande doit être un texte, tout autre type est refusé
    ("Bash", {"command": 12}, "type inattendu"),
    ("Bash", {"command": None}, "type inattendu"),
    ("Bash", {"command": {"texte": "git status"}}, "type inattendu"),
    ("PowerShell", {"command": ["git", 1]}, "type inattendu"),
    ("Monitor", {"command": 12, "cmd": "git status"}, "type inattendu"),
    # tout autre outil : un champ d'un autre type est ignoré, le suivant est lu
    ("mcp__exemple__outil", {"input": {"a": 1}, "command": "git push origin main"}, "push vers main"),
    ("mcp__exemple__outil", {"command": 12, "cmd": "git push origin main"}, "push vers main"),
    ("mcp__exemple__outil", {"input": {"a": 1}, "script": ["git", "commit", "--no-verify"]}, "sans hooks"),
]


@pytest.mark.parametrize(("outil", "entree", "fragment"), REFUS_OUTILS)
def test_cli_outils_qui_lancent_une_commande(outil, entree, fragment):
    r = lancer(json.dumps({"tool_name": outil, "tool_input": entree, "cwd": "."}), "--branche", "main")
    assert r.returncode == 2, (outil, entree)
    assert fragment in r.stderr.decode("utf-8"), (outil, entree)


@pytest.mark.parametrize(
    ("outil", "attendu"),
    [("Monitor", 0), ("Bash", 0), ("PowerShell", 2), ("mcp__autre__shell", 2)],
)
def test_cli_lecture_selon_l_outil(outil, attendu):
    # « ma`in » vaut « main » pour PowerShell (échappement), pas pour Bash (substitution).
    # Monitor est lu comme Bash ; un outil inconnu, de toutes les façons.
    commande = "git push origin ma" + chr(96) + "in"
    entree = {"tool_name": outil, "tool_input": {"command": commande}, "cwd": "."}
    assert lancer(json.dumps(entree), "--branche", "main").returncode == attendu


@pytest.mark.parametrize(
    ("outil", "entree"),
    [
        ("mcp__claude_ai_Gmail__search_threads", {"query": "git push origin main"}),
        ("mcp__autre__outil", {}),
        ("mcp__autre__outil", {"command": ["git", "status", "--short"]}),
        ("mcp__autre__outil", {"command": []}),
        ("mcp__exemple__outil", {"input": {"a": 1}}),
        ("mcp__exemple__outil", {"command": None, "input": 12, "script": ["git", 1]}),
        ("mcp__exemple__outil", {"input": {"a": 1}, "cmd": "git status"}),
        ("Monitor", {"command": "git status"}),
        ("mcp__desktop-commander__start_process", {"command": "git status"}),
    ],
)
def test_cli_outils_admis(outil, entree):
    r = lancer(json.dumps({"tool_name": outil, "tool_input": entree, "cwd": "."}), "--branche", "main")
    assert r.returncode == 0, (outil, entree, r.stderr)


def test_cli_outil_sans_commande_ne_lance_rien():
    # Sans --branche ni réglages, un outil qui porte une commande sortirait en 64 : celui-ci sort
    # en 0, preuve que rien n'a été chargé ni lancé.
    entree = json.dumps({"tool_name": "mcp__autre__outil", "tool_input": {"query": "x"}, "cwd": "."})
    assert lancer(entree).returncode == 0
    entree = json.dumps({"tool_name": "mcp__exemple__outil", "tool_input": {"input": {"a": 1}}})
    assert lancer(entree).returncode == 0
    entree = json.dumps({"tool_name": "Monitor", "tool_input": {"command": "git status"}, "cwd": "."})
    assert lancer(entree).returncode == 64


def test_cli_json_illisible():
    assert lancer("pas du json", "--branche", "main").returncode == 1
    assert lancer("[1, 2]", "--branche", "main").returncode == 1


def test_cli_sans_reglages_ni_branche():
    entree = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "."})
    assert lancer(entree).returncode == 64


def gh_en_tete(monkeypatch, dossier):
    monkeypatch.setenv("PATH", str(dossier) + os.pathsep + os.environ["PATH"])


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
    assert crochet["matcher"] == "Bash|PowerShell|Monitor|mcp__.*"
    commande = crochet["hooks"][0]["command"]
    assert "lancer.sh" in commande
    assert "garde_claude.py" in commande
    assert b"\r" not in chemin.read_bytes()


# --- ronde de corrections 1 ---

CHEMIN_WIN = r"C:\src\github.com\EdouardZemb\modele-projet.worktrees\lot-1"


def refus_outil(commande, outil, courante="lot-1/x", verts=True):
    """Comme refus(), mais la branche courante n'est lisible que pour le vrai chemin Windows."""

    def lire(chemin):
        return courante if chemin in (None, CHEMIN_WIN) else None

    return garde_claude.motif_de_refus(
        commande, BRANCHE, lire, lambda pr: verts, outil, fusion=lambda d: "session"
    )


@pytest.mark.parametrize(
    "commande",
    [
        f"git -C {CHEMIN_WIN} push -u origin HEAD",
        f"git -C {CHEMIN_WIN} push",
        f"cd {CHEMIN_WIN}; git push -u origin HEAD",
        f"Set-Location {CHEMIN_WIN}; git push",
    ],
)
def test_powershell_chemin_windows_admis(commande):
    assert refus_outil(commande, "PowerShell") is None


def test_powershell_apostrophe_inversee_est_l_echappement():
    assert "push vers main" in refus_outil("git push origin ma`in", "PowerShell")
    assert "push vers main" in refus_outil("git push origin main", "PowerShell")


def test_bash_apostrophe_inversee_est_une_substitution():
    assert "push vers main" in refus_outil("echo `git push origin main`", "Bash")


@pytest.mark.parametrize(
    "commande",
    ["cd ../lot-2 && gh pr merge --squash", r"Set-Location ..\lot-2; gh pr merge --squash"],
)
def test_fusion_sans_numero_apres_changement_de_dossier(commande):
    for outil in ("Bash", "PowerShell"):
        motif = refus_outil(commande, outil)
        assert motif is not None
        assert "préciser le numéro de PR" in motif


def test_fusion_avec_numero_apres_changement_de_dossier():
    assert refus_outil("cd ../lot-2 && gh pr merge 12 --squash", "Bash") is None


@pytest.mark.parametrize(
    "commande",
    [
        "gh api repos/o/x/rulesets",
        "gh api repos/{owner}/{repo}/rulesets --jq '.[].name'",
        (
            "gh api graphql -f query='query { repository(owner:\"o\", name:\"x\") "
            "{ branchProtectionRules(first: 5) { nodes { pattern } } } }'"
        ),
    ],
)
def test_api_en_lecture_admise(commande):
    assert refus(commande) is None


def test_api_en_ecriture_refusee():
    assert "l'API" in refus("gh api -X POST repos/o/x/rulesets --input f.json")
    mutation = (
        "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) "
        "{ clientMutationId } }'"
    )
    assert "l'API" in refus(mutation)


@pytest.mark.parametrize(
    "commande",
    [
        "git config core.hooksPath .githooks",
        "git config --local core.hooksPath .githooks",
        "git config --worktree core.hooksPath .githooks",
        "git -C ../autre config core.hooksPath .githooks",
    ],
)
def test_reparation_des_hooks_admise(commande):
    assert refus(commande) is None


@pytest.mark.parametrize(
    "commande",
    [
        "git config core.hooksPath /dev/null",
        "git config core.hooksPath .githooks-vide",
        "git config core.hooksPath",
        "git config --unset core.hooksPath",
        "git config --global core.hooksPath .githooks",
        "git config --system core.hooksPath .githooks",
        "git config --file x core.hooksPath .githooks",
        "git config core.hooksPath .githooks extra",
        "git -c core.hooksPath=.githooks-vide commit -m x",
    ],
)
def test_detournement_des_hooks_refuse(commande):
    assert "hooks" in refus(commande)


@pytest.mark.parametrize(
    "commande",
    [
        "gh -R o/r pr merge 12 --admin",
        "gh pr -R o/r merge 12 --admin",
        "gh --repo o/r pr merge 12 --admin",
    ],
)
def test_admin_malgre_option_de_depot(commande):
    assert "contournant" in refus(commande)


def test_option_de_depot_sans_admin_refusee():
    assert "contrôles" in refus("gh -R o/r pr merge 12")


def test_gh_api_apres_option_de_depot():
    assert "l'API" in refus("gh -R o/r api -X PUT repos/o/x/pulls/12/merge")


def test_checks_verts_gh_budget_epuise(tmp_path, monkeypatch):
    faux_gh_lent(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setattr(garde_claude, "BUDGET", 0.5)
    assert garde_claude.checks_verts_gh("12", str(tmp_path)) is False


def test_budget_deja_epuise_ne_lance_rien(monkeypatch):
    monkeypatch.setattr(garde_claude, "_echeance", garde_claude.time.monotonic() - 1)
    assert garde_claude.branche_courante_git(None, ".") is None


def test_main_exception_inattendue_refuse(monkeypatch, capsys):
    import io
    import types

    module = types.ModuleType("reglages")

    def explose(nom):
        raise RuntimeError("boum")

    module.__getattr__ = explose
    monkeypatch.setitem(sys.modules, "reglages", module)
    entree = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "."})
    monkeypatch.setattr(
        sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(entree.encode("utf-8")))
    )
    assert garde_claude.main([]) == 2
    assert "commande impossible à analyser" in capsys.readouterr().err
    assert garde_claude._echeance is None


# --- ronde de corrections 2 ---

BS, NL, CR, BT = chr(92), chr(10), chr(13), chr(96)
MUTATION = "-f query='mutation { mergePullRequest(input: {pullRequestId: " + chr(34) + "x" + chr(34) + "}) { id } }'"


@pytest.mark.parametrize("outil", ["Bash", "PowerShell", None])
@pytest.mark.parametrize(
    "point", ["graphql", "/graphql", "https://api.github.com/graphql", "https://ghe.exemple.fr/api/graphql"]
)
def test_graphql_mutation_refusee_quel_que_soit_le_point(point, outil):
    assert "l'API" in refus_outil(f"gh api {point} {MUTATION}", outil)


def test_graphql_lecture_par_chemin_admise():
    lecture = "-f query='query { repository(name: 1) { branchProtectionRules(first: 5) { id } } }'"
    for outil in ("Bash", "PowerShell"):
        assert refus_outil(f"gh api /graphql {lecture}", outil) is None


def test_merge_branch_refuse():
    mutation = "gh api graphql -f query='mutation { mergeBranch(input: {base: 1}) { id } }'"
    assert "l'API" in refus(mutation)


def test_push_location_change_de_dossier():
    motif = refus_outil(r"Push-Location ..\lot-2; gh pr merge --squash", "PowerShell")
    assert "préciser le numéro de PR" in motif


@pytest.mark.parametrize(
    "commande",
    [
        "git push origin " + BS + NL + "main",
        "git push origin ma" + BS + NL + "in",
        "git push origin " + BS + CR + NL + "main",
    ],
)
def test_continuation_bash(commande):
    assert "push vers main" in refus_outil(commande, "Bash")
    assert "push vers main" in refus_outil(commande, None)


@pytest.mark.parametrize("fin", [NL, CR + NL])
def test_continuation_powershell(fin):
    assert "push vers main" in refus_outil("git push origin " + BT + fin + "main", "PowerShell")


# --- ronde de corrections 3 ---


@pytest.mark.parametrize("outil", ["Bash", "PowerShell"])
@pytest.mark.parametrize(
    "commande",
    [
        "gh api -X PUT repos/o/r/contents/graphql -f content=x",
        "gh api -X POST repos/o/r/git/refs/heads/graphql -f sha=1",
        "gh api /graphql?x=1 " + MUTATION,
    ],
)
def test_api_ecriture_sans_egard_au_point(commande, outil):
    assert "l'API" in refus_outil(commande, outil)


def test_api_graphql_lecture_et_get_admis():
    lecture = "-f query='query { repository(name: 1) { branchProtectionRules(first: 5) { id } } }'"
    for point in ("graphql", "/graphql", "https://api.github.com/graphql", "/graphql?x=1"):
        assert refus(f"gh api {point} {lecture}") is None
    assert refus("gh api repos/o/r/graphql") is None


# --- revue finale du lot 1 ---


def test_powershell_liste_d_arguments():
    commande = "Start-Process gh -ArgumentList 'pr','merge','12' -Wait"
    assert "contrôles" in refus_outil(commande, "PowerShell", verts=False)
    assert refus_outil(commande, "PowerShell", verts=True) is None
    # une virgule entre guillemets n'est pas un séparateur
    assert refus_outil("git commit -m 'feat: a,-n'", "PowerShell") is None


@pytest.mark.parametrize("outil", ["Bash", "PowerShell", None])
def test_substitution_entre_guillemets_doubles(outil):
    assert "sans hooks" in refus_outil('echo "$(git commit --no-verify -m x)"', outil)
    assert refus_outil('echo "$(git status)"', outil) is None


@pytest.mark.parametrize("outil", ["Bash", "PowerShell", None])
def test_reparation_et_lecture_des_hooks_admises_partout(outil):
    for commande in ("git config core.hooksPath .githooks", "git config --get core.hooksPath"):
        assert refus_outil(commande, outil) is None, (commande, outil)


def test_commande_de():
    assert garde_claude.commande_de({"command": "a", "cmd": "b"}) == "a"
    assert garde_claude.commande_de({"script": "d"}) == "d"
    assert garde_claude.commande_de({"input": ["git", "commit", "-m", "x"]}) == "git commit -m x"
    assert garde_claude.commande_de({"query": "e"}) is None
    for illisible in ({"command": 1, "input": "c"}, {"cmd": None}, {"input": ["a", 2]}, {"script": {}}):
        with pytest.raises(garde_claude.CommandeIllisible):
            garde_claude.commande_de(illisible)
    # hors de Bash, PowerShell et Monitor : un champ d'un autre type est ignoré
    assert garde_claude.commande_de({"command": 1, "input": "c"}, stricte=False) == "c"
    assert garde_claude.commande_de({"input": {"a": 1}}, stricte=False) is None
    assert garde_claude.commande_de({"cmd": None, "script": ["x", "y"]}, stricte=False) == "x y"


@pytest.mark.parametrize(
    ("chemin", "vise"),
    [
        (".githooks", True),
        ("./.githooks/pre-commit", True),
        ("scripts/modele", True),
        ("scripts/modele/garde_claude.py", True),
        ("scripts", True),
        ("scripts/", True),
        ("./scripts", True),
        ("apps/web/scripts", False),
        ("tools/scripts/", False),
        ("/srv/scripts", False),
        ("apps/web/scripts/modele", True),
        ("-Path:.githooks", True),
        ("--chemin=scripts/modele", True),
        ("scripts/build.sh", False),
        ("node_modules", False),
        (".githooks-ancien", False),
        ("-Recurse", False),
    ],
)
def test_vise_garde_fous(chemin, vise):
    assert garde_claude._vise_garde_fous(chemin) is vise
    windows = chemin.replace("/", chr(92))
    assert garde_claude._vise_garde_fous(windows) is vise


def test_effacement_des_hooks_en_powershell_par_chemin_absolu():
    commande = "Remove-Item -Recurse -Force " + chr(92).join(["C:", "src", "x", ".githooks"])
    assert "garde-fous" in refus_outil(commande, "PowerShell")


# --- le mode de fusion ------------------------------------------------------------------------

REFUS_EDOUARD = [
    "gh pr merge 12 --squash",
    "gh pr merge 12 --auto --squash",
    "gh pr merge --admin 12",
    "gh api -X PUT repos/o/d/pulls/12/merge",
    "gh api graphql -f query='mutation{mergePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'",
    "gh api graphql -f query='mutation{enablePullRequestAutoMerge(input:{pullRequestId:\"x\"}){clientMutationId}}'",
]


@pytest.mark.parametrize("commande", REFUS_EDOUARD)
def test_fusion_refusee_en_mode_edouard(commande):
    motif = refus(commande, verts=True, fusion=lambda d: "edouard")
    assert motif is not None, commande
    assert "mode fusion : edouard" in motif, (commande, motif)


@pytest.mark.parametrize(("commande", "courante", "verts"), [a for a in ADMIS if "merge" in a[0]])
def test_mode_session_inchange(commande, courante, verts):
    assert refus(commande, courante, verts, fusion=lambda d: "session") is None


def test_fusion_lue_une_fois_et_seulement_pour_une_fusion():
    appels = []

    def fusion(dossier):
        appels.append(1)
        return "session"

    for commande in ("git status", "git push origin lot-2/x", "gh pr view 1"):
        refus(commande, fusion=fusion)
    assert appels == []
    refus("gh pr merge 1 && gh pr merge 2", fusion=fusion)
    assert appels == [1]


def test_fusion_par_defaut_est_edouard():
    motif = garde_claude.motif_de_refus("gh pr merge 3", BRANCHE, lambda c: "x", lambda pr: True)
    assert motif is not None
    assert "mode fusion : edouard" in motif


@pytest.mark.parametrize(
    ("sortie", "attendu"),
    [
        ((0, "fusion: session\n"), "session"),
        ((0, "nom: x\nfusion: session\nautre: y\n"), "session"),
        ((0, "fusion: edouard\n"), "edouard"),
        ((0, "fusion: Session\n"), "edouard"),
        ((0, "fusion: sessions\n"), "edouard"),
        ((0, "nom: x\n"), "edouard"),
        ((1, ""), "edouard"),
        ((1, "fusion: session\n"), "edouard"),
    ],
)
def test_fusion_du_depot(tmp_path, monkeypatch, sortie, attendu):
    faux_gh(tmp_path, {"api": sortie})
    gh_en_tete(monkeypatch, tmp_path)
    assert garde_claude.fusion_du_depot("main", str(tmp_path)) == attendu
    appel = (tmp_path / "appels").read_text(encoding="utf-8")
    assert "?ref=main" in appel
    assert "contents/.copier-answers.yml" in appel


def test_fusion_du_depot_sans_gh(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert garde_claude.fusion_du_depot("main", str(tmp_path)) == "edouard"


def test_fusion_du_depot_budget_epuise(tmp_path, monkeypatch):
    faux_gh_lent(tmp_path, "fusion: session")  # sans budget, il répondrait « session »
    gh_en_tete(monkeypatch, tmp_path)
    monkeypatch.setattr(garde_claude, "BUDGET", 0.5)
    assert garde_claude.fusion_du_depot("main", str(tmp_path)) == "edouard"


def _entree_fusion(dossier):
    return json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 3 --squash"},
            "cwd": str(dossier),
        }
    )


def lancer_avec_gh(dossier, entree, *args):
    env = dict(os.environ)
    env["PATH"] = str(dossier) + os.pathsep + env["PATH"]
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "garde_claude.py"), *args],
        input=entree.encode("utf-8"),
        capture_output=True,
        check=False,
        env=env,
    )


def test_fusion_lue_sur_github_pas_dans_la_copie(tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("fusion: session\n", encoding="utf-8")
    faux_gh(
        tmp_path,
        {"pr checks": (0, '[{"bucket":"pass"}]'), "api": (0, "fusion: edouard\n")},
    )
    r = lancer_avec_gh(tmp_path, _entree_fusion(tmp_path), "--branche", "main")
    assert r.returncode == 2
    assert "mode fusion : edouard" in r.stderr.decode("utf-8")


def test_cli_option_fusion(tmp_path):
    faux_gh(tmp_path, {"pr checks": (0, '[{"bucket":"pass"}]')})
    entree = _entree_fusion(tmp_path)
    r = lancer_avec_gh(tmp_path, entree, "--branche", "main", "--fusion", "session")
    assert r.returncode == 0, r.stderr
    assert "contents" not in (tmp_path / "appels").read_text(encoding="utf-8")


def test_cli_option_fusion_edouard_l_emporte(tmp_path):
    faux_gh(tmp_path, {"pr checks": (0, '[{"bucket":"pass"}]'), "api": (0, "fusion: session\n")})
    entree = _entree_fusion(tmp_path)
    r = lancer_avec_gh(tmp_path, entree, "--branche", "main", "--fusion", "edouard")
    assert r.returncode == 2


def test_cli_option_fusion_invalide(tmp_path):
    entree = _entree_fusion(tmp_path)
    r = lancer_avec_gh(tmp_path, entree, "--branche", "main", "--fusion", "oui")
    assert r.returncode == 64


# --- correction n° 1 ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["session", "edouard"])
@pytest.mark.parametrize(
    ("commande", "fragment", "courante", "verts"),
    [r for r in REFUS if r[1] == "étiquette ou publication"],
)
def test_etiquette_refusee_dans_les_deux_modes(commande, fragment, courante, verts, mode):
    motif = refus(commande, courante, verts, fusion=lambda d: mode)
    assert motif is not None, commande
    assert fragment in motif, (commande, motif)


def _fusion_par_dossier(modes, vus=None):
    def fusion(dossier):
        if vus is not None:
            vus.append(dossier)
        return modes.get(dossier, "session")

    return fusion


def test_fusion_recoit_le_dossier_suivi_par_cd():
    vus = []
    fusion = _fusion_par_dossier({}, vus)
    assert refus("gh pr merge 12 --squash", fusion=fusion) is None
    assert refus("cd ../lot-2 && gh pr merge 12 --squash", fusion=fusion) is None
    assert vus == [None, "../lot-2"]


def test_fusion_apres_cd_en_mode_session_admise():
    assert refus("cd ../lot-2 && gh pr merge 12 --squash", fusion=lambda d: "session") is None


def test_fusion_apres_cd_en_mode_edouard_du_dossier_refusee():
    fusion = _fusion_par_dossier({"../lot-2": "edouard"})
    motif = refus("cd ../lot-2 && gh pr merge 12 --squash", fusion=fusion)
    assert motif is not None
    assert "mode fusion : edouard" in motif
    assert refus("gh pr merge 12 --squash", fusion=fusion) is None


@pytest.mark.parametrize(
    "commande",
    [
        "gh pr merge https://github.com/o/B/pull/12",
        "GH_REPO=o/B gh pr merge 12",
        "env GH_REPO=o/B gh pr merge 12 --squash",
    ],
)
def test_fusion_dans_un_autre_depot_refusee(commande):
    motif = refus(commande, fusion=lambda d: "session")
    assert motif is not None
    assert "autre dépôt" in motif


@pytest.mark.parametrize(
    ("mode", "attendu"), [("session", "autre dépôt"), ("edouard", "mode fusion : edouard")]
)
def test_fusion_qui_nomme_le_depot_meme_le_sien_refusee(mode, attendu):
    """Ce que dit methode.md (« Qui fusionne ») : tout -R est refusé, même vers ce dépôt-ci."""
    motif = refus("gh pr merge 26 -R EdouardZemb/modele-projet --squash", fusion=lambda d: mode)
    assert motif is not None
    assert attendu in motif


GRAPHQL_OPAQUES = [
    "gh api graphql -F query=@q.graphql",
    "gh api graphql --input q.json",
    "gh api graphql -f query='mutation($id:ID!){mergePullRequest(input:{pullRequestId:$id}){clientMutationId}}' -f id=x",
]


@pytest.mark.parametrize("commande", GRAPHQL_OPAQUES)
def test_graphql_opaque_refuse_en_mode_edouard(commande):
    motif = refus(commande, fusion=lambda d: "edouard")
    assert motif is not None
    assert "mode fusion : edouard" in motif


@pytest.mark.parametrize("commande", GRAPHQL_OPAQUES[:2])
def test_graphql_opaque_admis_en_mode_session(commande):
    assert refus(commande, fusion=lambda d: "session") is None


def test_cli_fusion_admise_selon_github_et_branche_donnee(tmp_path):
    faux_gh(
        tmp_path,
        {"pr checks": (0, '[{"bucket":"pass"}]'), "api": (0, "fusion: session\n")},
    )
    r = lancer_avec_gh(tmp_path, _entree_fusion(tmp_path), "--branche", "principal")
    assert r.returncode == 0, r.stderr
    assert "?ref=principal" in (tmp_path / "appels").read_text(encoding="utf-8")


# --- correction n° 2 ---------------------------------------------------------------------------

GH_REPO_FUSIONS = [
    "export GH_REPO=o/B; gh pr merge 12 --squash",
    "$env:GH_REPO='o/B'; gh pr merge 12 --squash",
    "GH_REPO=o/B; gh pr merge 12",
    "declare -x GH_REPO=o/B && gh pr merge 12",
    "Set-Item env:GH_REPO o/B; gh pr merge 12",
    "export GH_REPO=o/B; gh api -X PUT repos/o/B/pulls/12/merge",
    "export GH_REPO=o/B; gh api graphql -F query=@q.graphql",
    "export GH_REPO=o/B; gh api graphql -f query='mutation{mergePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'",
]


@pytest.mark.parametrize("mode", ["session", "edouard"])
@pytest.mark.parametrize("commande", GH_REPO_FUSIONS)
def test_gh_repo_dans_la_commande_refuse_la_fusion(commande, mode):
    motif = refus(commande, fusion=lambda d: mode)
    assert motif is not None, commande
    assert "autre dépôt" in motif, (commande, motif)


@pytest.mark.parametrize("mode", ["session", "edouard"])
def test_gh_repo_sans_fusion_admis(mode):
    assert refus("export GH_REPO=o/B; gh pr view 12", fusion=lambda d: mode) is None
