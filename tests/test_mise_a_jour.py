"""La mise à jour par Copier propage le géré et préserve le semé (spec §8, critère 3)."""

import shutil
import subprocess
from pathlib import Path

import copier
import pytest
import yaml
from conftest import RACINE, REPONSES_PAR_DEFAUT, REPONSES_SERVEUR, git

SH = shutil.which("sh") or (
    r"C:\Program Files\Git\bin\sh.exe" if Path(r"C:\Program Files\Git\bin\sh.exe").exists() else None
)

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


LIGNE_GABARIT = "Ligne ajoutée au gabarit en v0.0.2"
SEMES_RETOUCHES = ("template/CLAUDE.md.jinja", "template/docs/registre.md")


def _modele_v2(modele, env):
    """Une v0.0.2 qui ajoute une ligne aux gabarits de deux semés : ils ne doivent pas l'accueillir."""
    for gabarit in SEMES_RETOUCHES:
        with (modele / gabarit).open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n{LIGNE_GABARIT}\n")
    git(modele, env, "commit", "-q", "-am", "v0.0.2")
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


def _retoucher(*chemins):
    for chemin in chemins:
        with chemin.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n# {LIGNE_PROJET}\n")


def test_passage_en_cible_serveur(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)
    _retoucher(projet / "CLAUDE.md", projet / "docs/registre.md")
    git(projet, env, "commit", "-q", "-am", "semés retouchés par le projet")
    claude = (projet / "CLAUDE.md").read_bytes()
    registre = (projet / "docs/registre.md").read_bytes()
    assert LIGNE_PROJET.encode() in claude
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
    assert LIGNE_GABARIT not in (projet / "CLAUDE.md").read_text(encoding="utf-8")
    assert LIGNE_GABARIT not in (projet / "docs/registre.md").read_text(encoding="utf-8")
    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["cible"] == "serveur"
    assert reponses["bloc_ports"] == 4310


def test_retour_en_cible_aucune(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele, REPONSES_SERVEUR)
    lib = projet / "deploiement/lib.sh"
    for present in (
        lib,
        projet / "deploiement/projet.env",
        projet / "deploiement/compose.projet.yml",
        projet / ".sops.yaml",
        projet / "tests/deploiement",
        projet / "docs/exploitation.md",
    ):
        assert present.exists(), present
    _retoucher(
        projet / "deploiement/projet.env", lib, projet / "CLAUDE.md", projet / "docs/registre.md"
    )
    claude = (projet / "CLAUDE.md").read_bytes()
    registre = (projet / "docs/registre.md").read_bytes()
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
    # Les semés qui ne sont pas propres à la cible survivent, retouches comprises.
    assert (projet / "CLAUDE.md").read_bytes() == claude
    assert (projet / "docs/registre.md").read_bytes() == registre
    assert LIGNE_GABARIT not in (projet / "CLAUDE.md").read_text(encoding="utf-8")
    assert LIGNE_GABARIT not in (projet / "docs/registre.md").read_text(encoding="utf-8")
    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["cible"] == "aucune"


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_mise_a_jour_refuse_un_fichier_masque(tmp_path, env_isole):
    """Le critère de sortie de LE-8 : la vérification dans le test de mise à jour (LE-23)."""
    env = {**env_isole(), "MOTIFS_INTERDITS": "motif-interdit-essai"}
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)
    git(projet, env, "config", "core.hooksPath", ".githooks")

    with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n*secret*\n")
    git(projet, env, "add", ".gitignore")
    git(projet, env, "commit", "-q", "-m", "chore: ignorer les secrets")

    nouveau = modele / "template/scripts/modele/outil_secret.py"
    nouveau.write_text('"""Un outil du modèle que le .gitignore du projet masque."""\n', encoding="utf-8")
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")

    copier.run_update(str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.2", quiet=True)
    assert (projet / "scripts/modele/outil_secret.py").is_file()

    def valider():
        git(projet, env, "add", "-A")
        return subprocess.run(
            ["git", "commit", "-q", "-m", "chore: mise à jour du modèle"],
            check=False,
            cwd=projet,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    r = valider()
    assert r.returncode != 0
    assert "scripts/modele/outil_secret.py" in r.stderr

    with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
        f.write("!scripts/modele/outil_secret.py\n")
    r = valider()
    assert r.returncode == 0, r.stderr
    suivis = subprocess.run(
        ["git", "ls-files", "scripts/modele/outil_secret.py"],
        check=True,
        cwd=projet,
        env=env,
        capture_output=True,
        text=True,
    )
    assert "outil_secret.py" in suivis.stdout


def _modele_depuis_v0_5_0(tmp_path, env):
    """Un modèle de test : la v0.5.0 du dépôt (v0.0.1), puis l'arbre de travail actuel (v0.0.2)."""
    modele = tmp_path / "modele"
    modele.mkdir()
    archive = tmp_path / "v0.5.0.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "v0.5.0"],
        check=True,
        cwd=RACINE,
        env=env,
    )
    shutil.unpack_archive(archive, modele)
    git(modele, env, "init", "-q", "-b", "main")
    git(modele, env, "config", "core.autocrlf", "false")
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.1")
    git(modele, env, "tag", "v0.0.1")
    # L'arbre est vidé avant la copie : un fichier retiré depuis la v0.5.0 doit l'être vraiment.
    for chemin in modele.iterdir():
        if chemin.name != ".git":
            shutil.rmtree(chemin) if chemin.is_dir() else chemin.unlink()
    shutil.copytree(RACINE, modele, ignore=IGNORES, dirs_exist_ok=True)
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")
    return modele


def _mettre_a_jour_depuis_v0_5_0(tmp_path, env, reponses, **update):
    modele = _modele_depuis_v0_5_0(tmp_path, env)
    projet = tmp_path / "projet"
    copier.run_copy(
        str(modele), str(projet), data=reponses, defaults=True, vcs_ref="v0.0.1", quiet=True
    )
    git(projet, env, "init", "-q", "-b", "main")
    git(projet, env, "config", "core.autocrlf", "false")
    git(projet, env, "add", "-A")
    git(projet, env, "commit", "-q", "-m", "etat initial")
    copier.run_update(
        str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.2", quiet=True, **update
    )
    return projet


def test_mise_a_jour_d_un_projet_prive_serveur_garde_tout(tmp_path, env_isole):
    env = env_isole()
    reponses = {**REPONSES_SERVEUR, "visibilite": "prive"}
    projet = _mettre_a_jour_depuis_v0_5_0(tmp_path, env, reponses)

    reglages = (projet / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "donnees"' in reglages
    assert "VISIBILITE" not in reglages
    assert (projet / "deploiement/deployer.sh").is_file()
    reponses_finales = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses_finales["nature"] == "donnees"
    _sans_conflit(projet)


def test_mise_a_jour_d_un_projet_public_passe_en_code(tmp_path, env_isole):
    env = env_isole()
    reponses = {**REPONSES_PAR_DEFAUT, "visibilite": "public", "cible": "aucune"}
    projet = _mettre_a_jour_depuis_v0_5_0(tmp_path, env, reponses)

    reglages = (projet / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "code"' in reglages
    assert "VISIBILITE" not in reglages
    reponses_finales = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses_finales["nature"] == "code"
    _sans_conflit(projet)
