"""La documentation de la racine : la licence et la carte, qui refusent en CI."""

import shutil
import subprocess
import sys

import documentation as d
import pytest
from conftest import SCRIPTS, git

SCRIPT = SCRIPTS / "documentation.py"

README = "# Essai\n\nAvant d'y travailler : [CLAUDE.md](CLAUDE.md).\n"
CLAUDE = "# Essai\n\n## Ce qui fait foi\n\n- Le comportement, c'est le code.\n"
NON_LIE = "n'est lié ni par README.md ni par « Ce qui fait foi » de CLAUDE.md"


def ecrire(racine, **fichiers):
    """Écrit les fichiers nommés (`_` pour `.`), en LF, sauf un texte déjà en CRLF."""
    for nom, texte in fichiers.items():
        (racine / nom.replace("_", ".")).write_text(texte, encoding="utf-8", newline="")
    return racine


def lancer(*args, env=None, cwd=None, script=SCRIPT):
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
        cwd=cwd,
    )


# --- la licence ------------------------------------------------------------------------------


def test_licence_presente(tmp_path):
    ecrire(tmp_path, LICENSE="MIT License\n")
    assert d.licence(tmp_path, "code") == (["licence : LICENSE présent (nature code)"], False)


@pytest.mark.parametrize("cas", ["absent", "vide", "espaces seuls", "minuscules", "dossier"])
def test_licence_absente_ou_vide_refuse(tmp_path, cas):
    if cas == "vide":
        ecrire(tmp_path, LICENSE="")
    elif cas == "espaces seuls":
        ecrire(tmp_path, LICENSE=" \n\t\n")
    elif cas == "minuscules":  # GitHub, et la CI sous Linux, lisent la casse
        (tmp_path / "license").write_text("MIT License\n", encoding="utf-8")
    elif cas == "dossier":
        (tmp_path / "LICENSE").mkdir()
    assert d.licence(tmp_path, "code") == (
        ["licence : LICENSE absent ou vide, exigé en nature code"],
        True,
    )


def test_licence_non_exigee_en_donnees(tmp_path):
    assert d.licence(tmp_path, "donnees") == (["licence : non exigée (nature donnees)"], False)


# --- la carte --------------------------------------------------------------------------------


def test_carte_tout_lie(tmp_path):
    ecrire(tmp_path, README_md=README, CLAUDE_md=CLAUDE)
    assert d.carte(tmp_path) == (["carte : 1 fichier .md à la racine, lié"], False)
    ecrire(
        tmp_path,
        CLAUDE_md="# Essai\n\n## Ce qui fait foi\n\n- La notice : [la notice](NOTICE.md).\n",
        NOTICE_md="# Notice\n",
    )
    assert d.carte(tmp_path) == (["carte : 2 fichiers .md à la racine, tous liés"], False)


def test_carte_claude_non_lie_par_le_readme(tmp_path):
    ecrire(
        tmp_path,
        README_md="# Essai\n\nRien d'autre.\n",
        CLAUDE_md="# Essai\n\n## Ce qui fait foi\n\n- [Ce fichier](CLAUDE.md).\n",
    )
    assert d.carte(tmp_path) == (
        [
            "carte : 1 fichier .md à la racine, 1 non lié",
            "carte : CLAUDE.md n'est pas lié par README.md",
        ],
        True,
    )


def test_carte_fichier_non_lie(tmp_path):
    ecrire(
        tmp_path,
        README_md=README + "\nLa notice est dans `NOTICE.md`.\n",
        CLAUDE_md=CLAUDE + "- La notice : `NOTICE.md`.\n",
        NOTICE_md="# Notice\n",
    )
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[0] == "carte : 2 fichiers .md à la racine, 1 non lié"
    assert lignes[-1] == f"carte : NOTICE.md {NON_LIE}"
    (tmp_path / "NOTICE.md").unlink()
    ecrire(tmp_path, REGISTRE_md="# Registre\n")
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : REGISTRE.md {NON_LIE}"


def test_carte_lien_hors_de_ce_qui_fait_foi(tmp_path):
    ecrire(
        tmp_path,
        README_md=README,
        CLAUDE_md=CLAUDE + "\n## Invariants\n\n- [La notice](NOTICE.md).\n",
        NOTICE_md="# Notice\n",
    )
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : NOTICE.md {NON_LIE}"
    # Un sous-titre reste dans la section ; le titre suivant de même niveau la ferme.
    ecrire(tmp_path, CLAUDE_md=CLAUDE + "\n### Détail\n\n- [La notice](NOTICE.md).\n")
    assert d.carte(tmp_path) == (["carte : 2 fichiers .md à la racine, tous liés"], False)


def test_carte_sans_readme(tmp_path):
    ecrire(tmp_path, CLAUDE_md=CLAUDE)
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[0] == "carte : 1 fichier .md à la racine, 1 non lié"
    assert "carte : README.md absent" in lignes


def test_carte_sans_claude(tmp_path):
    ecrire(tmp_path, README_md=README)
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[0] == "carte : 0 fichier .md à la racine"
    assert "carte : CLAUDE.md absent" in lignes


@pytest.mark.parametrize(
    "lien",
    [
        "[`CLAUDE.md`](CLAUDE.md)",
        '[CLAUDE.md](CLAUDE.md "le titre")',
        "[CLAUDE.md](<CLAUDE.md>)",
        "[CLAUDE.md](./CLAUDE.md)",
        "[l'état](CLAUDE.md#état)",
        "[CLAUDE.md](/CLAUDE.md)",
    ],
)
def test_carte_admet_les_formes_de_lien(tmp_path, lien):
    ecrire(tmp_path, README_md=f"# Essai\n\nAvant d'y travailler : {lien}.\n", CLAUDE_md=CLAUDE)
    assert d.carte(tmp_path) == (["carte : 1 fichier .md à la racine, lié"], False)


def test_carte_lit_un_texte_en_crlf(tmp_path):
    ecrire(
        tmp_path,
        README_md="# Essai\r\n\r\nAvant d'y travailler, [le fichier\r\nCLAUDE.md](CLAUDE.md).\r\n",
        CLAUDE_md=(
            "# Essai\r\n\r\n## Ce qui fait foi ##\r\n\r\n- [La notice](NOTICE.md).\r\n"
            "\r\n## Invariants\r\n\r\n- [Le registre](REGISTRE.md).\r\n"
        ),
        NOTICE_md="# Notice\r\n",
        REGISTRE_md="# Registre\r\n",
    )
    assert d.carte(tmp_path) == (
        ["carte : 3 fichiers .md à la racine, 1 non lié", f"carte : REGISTRE.md {NON_LIE}"],
        True,
    )


def test_carte_bloc_de_code_et_reference(tmp_path):
    for bloc in ("```\n[CLAUDE.md](CLAUDE.md)\n```\n", "~~~~ md\n[c][r]\n\n[r]: CLAUDE.md\n~~~~\n"):
        ecrire(tmp_path, README_md=f"# Essai\n\n{bloc}", CLAUDE_md=CLAUDE)
        lignes, refus = d.carte(tmp_path)
        assert refus, bloc
        assert lignes[-1] == "carte : CLAUDE.md n'est pas lié par README.md", bloc
    ecrire(tmp_path, README_md="# Essai\n\nVoir [le fichier][claude].\n\n[claude]: CLAUDE.md\n")
    assert d.carte(tmp_path) == (["carte : 1 fichier .md à la racine, lié"], False)


def test_carte_casse_exacte(tmp_path):
    ecrire(tmp_path, README_md="# Essai\n\n[CLAUDE.md](claude.md)\n", CLAUDE_md=CLAUDE)
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == "carte : CLAUDE.md n'est pas lié par README.md"


def test_carte_lien_sur_deux_lignes_et_code_en_ligne(tmp_path):
    ecrire(
        tmp_path,
        README_md="# Essai\n\nLes commandes sont dans [les\ncommandes](CLAUDE.md#commandes).\n",
        CLAUDE_md=CLAUDE,
    )
    assert d.carte(tmp_path) == (["carte : 1 fichier .md à la racine, lié"], False)
    ecrire(tmp_path, README_md=README + "\nUn exemple : `[x](NOTICE.md)`.\n", NOTICE_md="# N\n")
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : NOTICE.md {NON_LIE}"


def test_carte_lit_un_fichier_mal_encode(tmp_path):
    (tmp_path / "README.md").write_bytes(b"# \xff\xfe\x80\n\n[CLAUDE.md](CLAUDE.md)\n")
    (tmp_path / "CLAUDE.md").write_bytes(b"# \x80\n\n## Ce qui fait foi\n\n- [N](NOTICE.md)\n")
    (tmp_path / "NOTICE.md").write_bytes(b"\xff")
    assert d.carte(tmp_path) == (["carte : 2 fichiers .md à la racine, tous liés"], False)


def test_carte_affiche_les_noms_sans_caractere_de_controle():
    assert d._affichable("a\x1b[31mb\nc\x7f.md") == "a?[31mb?c?.md"
    assert d._affichable("état — ok.md") == "état — ok.md"


def test_liens_et_cible_locale(tmp_path):
    texte = (
        "[a](un.md) ![i](deux.png)\n"
        '[t](trois.md "titre") [c](<quatre et cinq.md>)\n'
        "[![badge](six.png)](sept.md)\n"
        "[a [b] c](huit.md)\n"
        "[sur deux\nlignes](neuf.md#ancre)\n"
        "`[code](non1.md)` et ``[x](non2.md)``\n"
        "<!-- [commentaire](non3.md) -->\n"
        "```\n[bloc](non4.md)\n```\n"
        "~~~~\n[bloc](non5.md)\n~~~~\n"
        "\\[échappé](non6.md)\n"
        "[texte\n\ncoupé par un paragraphe](non7.md)\n"
        "[^1]: une note, pas un lien\n"
        "[ref]: dix.md\n"
        "[ref2]:\n  <onze.md>\n"
    )
    assert d.liens(texte) == [
        "un.md",
        "deux.png",
        "trois.md",
        "quatre et cinq.md",
        "six.png",
        "sept.md",
        "huit.md",
        "neuf.md#ancre",
        "dix.md",
        "onze.md",
    ]
    assert d.liens(texte.replace("\n", "\r\n")) == d.liens(texte)
    for cible in ("https://x", "mailto:a", "#état", "../hors.md", "docs/../../hors.md", ""):
        assert d.cible_locale(cible, tmp_path) is None, cible
    assert d.cible_locale("./CLAUDE.md#état", tmp_path) == "CLAUDE.md"
    assert d.cible_locale("docs/a%20b.md", tmp_path) == "docs/a b.md"
    assert d.cible_locale("/docs/", tmp_path) == "docs"
    assert d.cible_locale("docs/a.md?plain=1#l1", tmp_path) == "docs/a.md"
    assert d.cible_locale("docs/../CLAUDE.md", tmp_path) == "CLAUDE.md"
    assert d.cible_locale("%C3%A9tat.md", tmp_path) == "état.md"


# --- la ligne de commande --------------------------------------------------------------------


def test_main_codes(tmp_path, env_isole):
    env = env_isole()
    conforme = tmp_path / "conforme"
    conforme.mkdir()
    ecrire(conforme, README_md=README, CLAUDE_md=CLAUDE, LICENSE="MIT License\n")
    r = lancer("--racine", str(conforme), env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == [
        "documentation : licence : LICENSE présent (nature code)",
        "documentation : carte : 1 fichier .md à la racine, lié",
    ]
    (conforme / "LICENSE").unlink()
    r = lancer("--racine", str(conforme), env=env)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.splitlines()[-1] == "documentation : refus"
    r = lancer("--racine", str(tmp_path / "absente-SENTINELLE"), env=env)
    assert r.returncode == 64, r.stdout + r.stderr
    assert "SENTINELLE" not in r.stdout + r.stderr
    r = lancer("--inconnue-SENTINELLE", env=env)
    assert r.returncode == 64, r.stdout + r.stderr
    assert "SENTINELLE" not in r.stdout + r.stderr
    r = lancer(env=env, cwd=conforme)  # sans --racine, le dossier courant
    assert r.returncode == 1, r.stdout + r.stderr
    assert d.main(["--help"]) == 0


def test_main_ne_cite_aucun_contenu(tmp_path, env_isole):
    ecrire(
        tmp_path,
        README_md="# SENTINELLE\n\nSENTINELLE [SENTINELLE](CLAUDE.md \"SENTINELLE\")\n",
        CLAUDE_md="# SENTINELLE\n\n## Ce qui fait foi\n\n- SENTINELLE `NOTICE.md`\n",
        NOTICE_md="SENTINELLE\n",
        LICENSE="SENTINELLE\n",
    )
    r = lancer("--racine", str(tmp_path), env=env_isole())
    assert r.returncode == 1, r.stdout + r.stderr
    assert "NOTICE.md" in r.stdout
    assert "SENTINELLE" not in r.stdout + r.stderr


def clone_de_nature(tmp_path, env, sur_la_branche, dans_la_copie):
    """Un clone dont `origin/main` porte `sur_la_branche` et la copie `dans_la_copie`, avec les deux
    scripts, un README et un CLAUDE.md conformes, sans LICENSE."""
    origine = tmp_path / "origine.git"
    origine.mkdir(parents=True)
    git(origine, env, "init", "-q", "--bare", "-b", "main")
    clone = tmp_path / "clone"
    clone.mkdir(parents=True)
    git(clone, env, "init", "-q", "-b", "main")
    git(clone, env, "config", "core.autocrlf", "false")
    dossier = clone / "scripts/modele"
    dossier.mkdir(parents=True)
    shutil.copy(SCRIPTS / "confidentialite.py", dossier / "confidentialite.py")
    shutil.copy(SCRIPT, dossier / "documentation.py")
    reglages = dossier / "reglages.py"
    reglages.write_text(f'NATURE = "{sur_la_branche}"\n', encoding="utf-8")
    ecrire(clone, README_md=README, CLAUDE_md=CLAUDE)
    git(clone, env, "add", "scripts/modele", "README.md", "CLAUDE.md")
    git(clone, env, "commit", "-q", "-m", "chore: base")
    git(clone, env, "remote", "add", "origin", str(origine))
    git(clone, env, "push", "-q", "origin", "main")
    reglages.write_text(f'NATURE = "{dans_la_copie}"\n', encoding="utf-8")
    return clone


def test_main_nature_lue_sur_la_branche_par_defaut(tmp_path, env_isole):
    """En CI, une PR qui écrit `NATURE = "donnees"` n'échappe pas à la licence : la nature se lit
    sur la branche par défaut, comme la lit la porte de confidentialité."""
    env = env_isole()
    clone = clone_de_nature(tmp_path / "a", env, "code", "donnees")
    script = clone / "scripts/modele/documentation.py"
    en_ci = {**env, "DEPOT_PRIVE": "true", "BRANCHE_DEFAUT": "main"}
    r = lancer(env=en_ci, cwd=clone, script=script)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "documentation : licence : LICENSE absent ou vide, exigé en nature code" in r.stdout
    r = lancer(env={**en_ci, "DEPOT_PRIVE": "false"}, cwd=clone, script=script)
    assert r.returncode == 1, r.stdout + r.stderr
    r = lancer(env=env, cwd=clone, script=script)  # hors CI, la copie fait foi
    assert r.returncode == 0, r.stdout + r.stderr
    assert "documentation : licence : non exigée (nature donnees)" in r.stdout

    clone = clone_de_nature(tmp_path / "b", env, "donnees", "code")
    script = clone / "scripts/modele/documentation.py"
    r = lancer(env=en_ci, cwd=clone, script=script)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "documentation : licence : non exigée (nature donnees)" in r.stdout
