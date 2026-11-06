"""La documentation de la racine : la licence et la carte, qui refusent en CI, et le gabarit resté
vide, qui avertit au `SessionStart`."""

import os
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
    # Un titre d'un niveau supérieur ferme aussi la section.
    ecrire(tmp_path, CLAUDE_md=CLAUDE + "\n# Annexe\n\n- [La notice](NOTICE.md).\n")
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : NOTICE.md {NON_LIE}"
    # Un sous-titre reste dans la section ; le titre suivant de même niveau la ferme.
    ecrire(tmp_path, CLAUDE_md=CLAUDE + "\n### Détail\n\n- [La notice](NOTICE.md).\n")
    assert d.carte(tmp_path) == (["carte : 2 fichiers .md à la racine, tous liés"], False)


def test_carte_suffixe_sans_casse_et_fichiers_seuls(tmp_path):
    ecrire(tmp_path, README_md=README, CLAUDE_md=CLAUDE)
    (tmp_path / "NOTICE.MD").write_text("# N\n", encoding="utf-8")
    (tmp_path / "docs.md").mkdir()
    assert d.carte(tmp_path) == (
        ["carte : 2 fichiers .md à la racine, 1 non lié", f"carte : NOTICE.MD {NON_LIE}"],
        True,
    )


def test_carte_ne_voit_pas_ce_que_git_ignore(tmp_path, env_isole, monkeypatch):
    """À la racine d'un dépôt git, la carte lit ce que git suit ou suivrait, comme la CI : un
    `CLAUDE.local.md` ignoré n'est pas compté, un fichier non suivi et non ignoré l'est."""
    env = env_isole()
    racine = tmp_path / "depot"
    racine.mkdir()
    git(racine, env, "init", "-q", "-b", "main")
    ecrire(
        racine,
        README_md=README,
        CLAUDE_md=CLAUDE,
        CLAUDE_local_md="# Local\n",
        _gitignore="/CLAUDE.local.md\n",
    )
    # Une variable `GIT_` de la session (un hook en pose) ne détourne pas git vers un autre dépôt.
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "absent"))
    assert d.carte(racine) == (["carte : 1 fichier .md à la racine, lié"], False)
    ecrire(racine, NOTICE_md="# Notice\n")
    assert d.carte(racine) == (
        ["carte : 2 fichiers .md à la racine, 1 non lié", f"carte : NOTICE.md {NON_LIE}"],
        True,
    )
    (racine / "NOTICE.md").unlink()
    git(racine, env, "add", "-f", "CLAUDE.local.md")  # suivi malgré la règle : la CI le verrait
    lignes, refus = d.carte(racine)
    assert refus
    assert lignes[-1] == f"carte : CLAUDE.local.md {NON_LIE}"


def test_carte_quand_git_echoue(tmp_path):
    """Un `.git` que git ne sait pas lire : la carte et la licence lisent tout le dossier, au lieu
    de ne rien voir."""
    racine = tmp_path / "depot"
    racine.mkdir()
    (racine / ".git").write_text("gitdir: ../absent\n", encoding="utf-8")
    ecrire(racine, README_md=README, CLAUDE_md=CLAUDE, LICENSE="MIT License\n")
    assert d.carte(racine) == (["carte : 1 fichier .md à la racine, lié"], False)
    assert d.licence(racine, "code") == (["licence : LICENSE présent (nature code)"], False)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows ne nomme un fichier qu'en Unicode")
def test_carte_nom_non_utf8_suivi_par_git(tmp_path, env_isole):
    """Sous Linux, un nom qui n'est pas de l'UTF-8, que git liste tel quel, est vu et affiché."""
    env = env_isole()
    racine = tmp_path / "depot"
    racine.mkdir()
    git(racine, env, "init", "-q", "-b", "main")
    ecrire(racine, README_md=README, CLAUDE_md=CLAUDE)
    nom = os.fsdecode(b"\xff.md")
    (racine / nom).write_text("# N\n", encoding="utf-8")
    git(racine, env, "add", "--", nom)
    lignes, refus = d.carte(racine)
    assert refus
    assert lignes[-1] == f"carte : ?.md {NON_LIE}"


def test_carte_deux_sections_ce_qui_fait_foi(tmp_path):
    """Deux sections « Ce qui fait foi » ne se collent pas : une définition seule qui ouvre la
    seconde, juste après la première, ne coupe pas un paragraphe, et ne lie rien."""
    ecrire(
        tmp_path,
        README_md=README,
        CLAUDE_md="# E\n\n## Ce qui fait foi\n\n- Texte\n## Ce qui fait foi\n[n]: NOTICE.md\n",
        NOTICE_md="# N\n",
    )
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : NOTICE.md {NON_LIE}"


def test_carte_reference_comme_sur_github(tmp_path):
    """Un lien de référence compte par son emploi ; sa définition peut être n'importe où dans le
    fichier, hors de « Ce qui fait foi » comprise. Une définition seule, ou qui coupe un paragraphe,
    ne se rend pas : elle ne lie rien."""
    for readme in (
        "# Essai\n\n[claude]: CLAUDE.md\n",
        "# Essai\n\nVoir le fichier\n[claude]: CLAUDE.md\n",
    ):
        ecrire(tmp_path, README_md=readme, CLAUDE_md=CLAUDE)
        lignes, refus = d.carte(tmp_path)
        assert refus, readme
        assert lignes[-1] == "carte : CLAUDE.md n'est pas lié par README.md", readme
    ecrire(
        tmp_path,
        README_md=README,
        CLAUDE_md=(
            "# Essai\n\n## Ce qui fait foi\n\n- La [notice][n].\n\n## Invariants\n\n- Rien.\n\n"
            "[n]: NOTICE.md\n"
        ),
        NOTICE_md="# Notice\n",
    )
    assert d.carte(tmp_path) == (["carte : 2 fichiers .md à la racine, tous liés"], False)
    ecrire(
        tmp_path,
        CLAUDE_md=(
            "# Essai\n\n## Ce qui fait foi\n\n[n]: NOTICE.md\n\n"
            "## Invariants\n\n- La [notice][n].\n"
        ),
    )
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : NOTICE.md {NON_LIE}"


def test_carte_lit_un_texte_avec_bom(tmp_path):
    """PowerShell 5.1 écrit l'UTF-8 avec un BOM : il ne cache ni un titre ni une définition."""
    (tmp_path / "README.md").write_bytes(
        b"\xef\xbb\xbf[claude]: CLAUDE.md\n\nVoir [le fichier][claude].\n"
    )
    (tmp_path / "CLAUDE.md").write_bytes(
        "\ufeff## Ce qui fait foi\n\n- [La notice](NOTICE.md).\n".encode()
    )
    ecrire(tmp_path, NOTICE_md="# Notice\n")
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


def test_affichable_remplace_les_caracteres_de_controle():
    assert d._affichable("a\x1b[31mb\nc\x7f.md") == "a?[31mb?c?.md"
    assert d._affichable("état — ok.md") == "état — ok.md"
    # Sous Linux, un nom qui n'est pas de l'UTF-8 arrive avec un « surrogate », que stdout, en
    # UTF-8 strict, refuserait d'écrire.
    assert d._affichable("\udcff.md") == "?.md"
    assert d._affichable("a\x01b\nc\x7fd") == "a?b?c?d"
    # Les séparateurs de ligne et de paragraphe coupent aussi une ligne (`splitlines`).
    assert d._affichable("a b c") == "a?b?c"


def test_carte_affiche_un_nom_a_caractere_de_controle(tmp_path, monkeypatch):
    """Windows refuse ces noms : `os.listdir` et `is_file` sont simulés pour eux."""
    ecrire(tmp_path, README_md=README, CLAUDE_md=CLAUDE)
    noms = ["README.md", "CLAUDE.md", "a\x1bb.md", "\udcff.md"]
    monkeypatch.setattr(d.os, "listdir", lambda racine: list(noms))
    vrai = d.Path.is_file
    monkeypatch.setattr(d.Path, "is_file", lambda self: self.name in noms[2:] or vrai(self))
    assert d.carte(tmp_path) == (
        [
            "carte : 3 fichiers .md à la racine, 2 non liés",
            f"carte : a?b.md {NON_LIE}",
            f"carte : ?.md {NON_LIE}",
        ],
        True,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Windows refuse un saut de ligne dans un nom")
def test_carte_nom_reel_a_caractere_de_controle(tmp_path):
    ecrire(tmp_path, README_md=README, CLAUDE_md=CLAUDE)
    (tmp_path / "a\nb.md").write_text("# N\n", encoding="utf-8")
    lignes, refus = d.carte(tmp_path)
    assert refus
    assert lignes[-1] == f"carte : a?b.md {NON_LIE}"


def test_liens_et_cible_locale(tmp_path):
    texte = (
        "[a](un.md) ![i](deux.png)\n"
        '[t](trois.md "titre") [c](<quatre et cinq.md>)\n'
        "[![badge](six.png)](sept.md)\n"
        "[a [b] c](huit.md)\n"
        "[a [b](neuf.md) c](non1.md)\n"
        "[sur deux\nlignes](dix.md#ancre)\n"
        "`[code](non2.md)` et ``[x](non3.md)``\n"
        "<!-- [commentaire](non4.md) -->\n"
        "```\n[bloc](non5.md)\n```\n"
        "~~~~\n[bloc](non6.md)\n~~~~\n"
        "```\n~~~\n[bloc](non7.md)\n```\n"
        "```bash```\n[après](onze.md)\n"
        "\\[échappé](non8.md)\n"
        "[texte\n\ncoupé par un paragraphe](non9.md)\n"
        "[voir][ref] et [ref2][]\n"
        "\n"
        "[ref]: douze.md\n"
        "[ref2]:\n  <treize.md>\n"
        "\n"
        "[^1]: une note, pas un lien\n"
    )
    assert d.liens(texte) == [
        "un.md",
        "deux.png",
        "trois.md",
        "quatre et cinq.md",
        "six.png",
        "sept.md",
        "huit.md",
        "neuf.md",
        "dix.md#ancre",
        "onze.md",
        "douze.md",
        "treize.md",
    ]
    assert d.liens(texte.replace("\n", "\r\n")) == d.liens(texte)
    # L'ordre est celui où les liens paraissent, celui d'une référence étant celui de son emploi.
    assert d.liens("[b][r] puis [a](un.md)\n\n[r]: zero.md\n") == ["zero.md", "un.md"]
    for cible in (
        "https://x", "mailto:a", "#état", "../hors.md", "docs/../../hors.md", "", "//CLAUDE.md",
    ):
        assert d.cible_locale(cible, tmp_path) is None, cible
    assert d.cible_locale("./CLAUDE.md#état", tmp_path) == "CLAUDE.md"
    assert d.cible_locale("docs/a%20b.md", tmp_path) == "docs/a b.md"
    assert d.cible_locale("/docs/", tmp_path) == "docs"
    assert d.cible_locale("docs/a.md?plain=1#l1", tmp_path) == "docs/a.md"
    assert d.cible_locale("docs/../CLAUDE.md", tmp_path) == "CLAUDE.md"
    assert d.cible_locale("%C3%A9tat.md", tmp_path) == "état.md"
    assert d.cible_locale("CLAUDE\\.md", tmp_path) == "CLAUDE.md"


def test_liens_de_reference():
    """Un lien de référence, `[texte][x]`, `[x][]` ou `[x]`, compte par son emploi, quand une
    définition `[x]: cible` de son étiquette (sans égard à la casse ni aux blancs) est dans le
    texte ; la première définition l'emporte. Une définition seule n'est pas un lien, ni une
    définition qui coupe un paragraphe, ni une définition dans un bloc de code."""
    texte = (
        "[plein][Note] [note][] [NOTE]\n"
        "[sur\ndeux] et ![image][sur deux]\n"
        "[a][absente](suite.md)\n"
        "[^1] et [jamais] et [bloc]\n"
        "\n"
        "[note]: notice.md\n"
        "[NOTE]: autre.md\n"
        "[sur deux]: <deux.md> \"titre\"\n"
        "[seule]: seule.md\n"
        "\n"
        "Une ligne de prose\n"
        "[jamais]: coupe.md\n"
        "\n"
        "```\n[bloc]: bloc.md\n```\n"
    )
    assert d.liens(texte) == [
        "notice.md", "notice.md", "notice.md", "deux.md", "deux.md", "suite.md",
    ]
    # Une définition peut suivre un titre ; son titre peut tenir sur la ligne suivante, et une
    # autre définition la suivre ; un reste sur sa ligne en fait du texte (CommonMark).
    assert d.liens("# Titre\n[t]: titre.md\n\n[voir][t]\n") == ["titre.md"]
    # Une ligne de blancs sépare comme une ligne vide : la définition qui la suit en est une.
    assert d.liens("texte\n   \n[r]: r.md\n\n[voir][r]\n") == ["r.md"]
    assert d.liens('[a][a] [b][b]\n\n[a]: a.md\n  "titre"\n[b]: b.md\n') == ["a.md", "b.md"]
    assert d.liens("[voir][r]\n\n[r]: r.md suite\n") == []
    assert d.liens('[voir][r]\n\n[r]: r.md "titre" suite\n') == []
    # Un lien dans le texte d'une référence pleine l'emporte, et son étiquette reste un lien
    # (CommonMark, `[foo [bar](/uri)][ref]`).
    assert d.liens("[a [b](c.md) d][r]\n\n[r]: r.md\n") == ["c.md", "r.md"]
    # Une étiquette blanche, ou de plus de 999 caractères, n'en est pas une.
    assert d.liens("[t][ ]\n\n[ ]: blanc.md\n") == []
    for n, attendu in ((999, ["long.md"]), (1000, [])):
        assert d.liens(f"[t][{'a' * n}]\n\n[{'a' * n}]: long.md\n") == attendu, n
    # Les définitions peuvent se lire dans un autre texte, le fichier entier d'une section.
    section = "- La [notice][n].\n"
    assert d.liens(section) == []
    assert d.liens(section, document="# T\n\n" + section + "\n# U\n\n[n]: NOTICE.md\n") == [
        "NOTICE.md"
    ]
    assert d.liens("[n]: NOTICE.md\n", document="[voir][n]\n\n[n]: NOTICE.md\n") == []


def lien_de_dossier(lien, cible):
    """Un lien symbolique vers un dossier ; sous Windows sans le droit d'en créer, une jonction."""
    try:
        lien.symlink_to(cible, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(lien), str(cible)], check=True, capture_output=True
        )


def test_cible_locale_refuse_une_sortie_par_un_lien(tmp_path):
    racine = tmp_path / "racine"
    (racine / "docs").mkdir(parents=True)
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    lien_de_dossier(racine / "lien", dehors)
    assert d.cible_locale("lien/x.md", racine) is None
    assert d.cible_locale("docs/x.md", racine) == "docs/x.md"


def test_cible_locale_sans_reseau(tmp_path, monkeypatch):
    """Une barre oblique inverse restée après les échappements n'est jamais un chemin du dépôt, et
    `resolve` ne la voit pas : sous Windows, deux en tête nomment un partage réseau, que `resolve`
    ouvrirait au `SessionStart`, au-delà du délai du hook. L'espion n'ouvre jamais rien : rouge, ce
    test ne touche pas le réseau."""
    vus = []
    resolve = d.Path.resolve

    def espion(self, *args, **kwargs):
        if "hote.exemple.org" in str(self):
            vus.append(str(self))
            raise OSError("pas de réseau dans un test")
        return resolve(self, *args, **kwargs)

    monkeypatch.setattr(d.Path, "resolve", espion)
    b = chr(92)  # les outils décodent les barres obliques inverses écrites en clair
    partage = f"{b * 4}hote.exemple.org{b * 2}p{b * 2}x.md"  # deux en tête, une fois lues
    readme = (
        f"# E\n\n[CLAUDE.md](CLAUDE.md) [p]({partage}) [q](</{partage}>)\n"
        "[r](%5C%5Chote.exemple.org%5Cx.md)\n"
    )
    arbre(tmp_path, {"README.md": readme, "CLAUDE.md": "# C\n\nDu texte.\n"})
    assert d.gabarits_vides(tmp_path) == []
    assert vus == []
    # Le même lien, sous Linux, ne nomme pas un sous-dossier : GitHub ne lit pas `\` comme un
    # séparateur, et la cible n'est locale nulle part.
    arbre(tmp_path, {"docs/x.md": ""})
    assert d.cible_locale(f"docs{b}x.md", tmp_path) is None


# --- le gabarit resté vide -------------------------------------------------------------------

MARQUEUR = "garde le marqueur *AAAA-MM-JJ* du gabarit"
VIDE = "corps vide (titres et consignes seulement)"
DOSSIER = "dossier sans autre fichier que README.md"
AUCUN = "le README ne lie aucun document du dépôt"


def arbre(racine, fichiers):
    """Écrit les fichiers, nommés par leur chemin relatif en `/`, leurs dossiers créés ; un texte
    tel quel (en CRLF s'il l'est), des octets bruts."""
    for chemin, contenu in fichiers.items():
        f = racine / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contenu, bytes):
            f.write_bytes(contenu)
        else:
            f.write_text(contenu, encoding="utf-8", newline="")
    return racine


def test_marqueur(tmp_path):
    arbre(
        tmp_path,
        {
            "README.md": "# E\n\nLe [cadrage](docs/cadrage.md).\n",
            "docs/cadrage.md": "# Cadrage\n\n- **Date** : *AAAA-MM-JJ*\n\nUn texte.\n",
        },
    )
    assert d.gabarits_vides(tmp_path) == [f"docs/cadrage.md : {MARQUEUR}"]
    # Un constat par chemin, la première règle qui touche : le marqueur avant le corps vide.
    arbre(tmp_path, {"docs/cadrage.md": "# Cadrage\n\n*AAAA-MM-JJ*\n"})
    assert d.gabarits_vides(tmp_path) == [f"docs/cadrage.md : {MARQUEUR}"]
    # Cité dans un bloc de code ou entre accents graves, le marqueur ne compte pas.
    for cite in (
        "```\n- **Date** : *AAAA-MM-JJ*\n```\n",
        "Le marqueur `*AAAA-MM-JJ*` se remplace par la date.\n",
    ):
        arbre(tmp_path, {"docs/cadrage.md": f"# Cadrage\n\n{cite}"})
        assert d.gabarits_vides(tmp_path) == [], cite


def test_corps_vide(tmp_path):
    vide = (
        "# Un\n## Deux\n### Trois\n#### Quatre\n##### Cinq\n###### Six\n\n"
        "<!-- Une consigne\n     sur trois\n     lignes. -->\n"
        "*Une consigne en italique.*\n"
        "_Une autre consigne._\n"
        "\n"
    )
    arbre(tmp_path, {"README.md": "# E\n\nLe [brief](docs/brief.md).\n", "docs/brief.md": vide})
    assert d.gabarits_vides(tmp_path) == [f"docs/brief.md : {VIDE}"]
    arbre(tmp_path, {"docs/brief.md": ""})
    assert d.gabarits_vides(tmp_path) == [f"docs/brief.md : {VIDE}"]
    # Un document se reconnaît à son suffixe, sans égard à la casse.
    arbre(tmp_path, {"README.md": "# E\n\nLa [note](docs/NOTE.MD).\n", "docs/NOTE.MD": vide})
    assert d.gabarits_vides(tmp_path) == [f"docs/NOTE.MD : {VIDE}"]
    arbre(tmp_path, {"README.md": "# E\n\nLe [brief](docs/brief.md).\n"})
    for corps in (
        "Une ligne ordinaire.\n",
        "```\n# Une ligne dans un bloc de code\n```\n",
        "*Une consigne* et *une autre*\n",
        "####### Sept dièses ne font pas un titre.\n",
    ):
        arbre(tmp_path, {"docs/brief.md": vide + corps})
        assert d.gabarits_vides(tmp_path) == [], corps


def test_dossier(tmp_path):
    arbre(
        tmp_path,
        {
            "README.md": "# E\n\nLes [décisions](docs/decisions/), [ici aussi](docs/decisions).\n",
            "docs/decisions/README.md": "# Décisions\n\nUne par fichier.\n",
        },
    )
    assert d.gabarits_vides(tmp_path) == [f"docs/decisions/ : {DOSSIER}"]
    arbre(tmp_path, {"docs/decisions/.gitkeep": ""})
    assert d.gabarits_vides(tmp_path) == [f"docs/decisions/ : {DOSSIER}"]
    arbre(tmp_path, {"docs/decisions/0001-un-choix.md": ""})
    assert d.gabarits_vides(tmp_path) == []
    (tmp_path / "docs/decisions/0001-un-choix.md").unlink()
    (tmp_path / "docs/decisions/anciennes").mkdir()
    assert d.gabarits_vides(tmp_path) == []


def test_mis_de_cote(tmp_path):
    """Le registre, les plans et les fichiers d'ADR ne sont pas lus ; le `README.md` du dossier des
    ADR, si."""
    arbre(
        tmp_path,
        {
            "README.md": (
                "# E\n\n[r](docs/registre.md) [R](REGISTRE.md) [p](.claude/plans/2026-11-06-x.md)\n"
                "[a](docs/decisions/0001-x.md) [b](docs/adr/0002-y.md)\n"
            ),
            "docs/registre.md": "",
            "REGISTRE.md": "",
            ".claude/plans/2026-11-06-x.md": "",
            "docs/decisions/0001-x.md": "# Un choix\n\n- **Date** : *AAAA-MM-JJ*\n",
            "docs/adr/0002-y.md": "",
        },
    )
    assert d.gabarits_vides(tmp_path) == []
    arbre(tmp_path, {"README.md": "# E\n\n[Les décisions](docs/decisions/README.md)\n"})
    arbre(tmp_path, {"docs/decisions/README.md": "# Décisions\n"})
    assert d.gabarits_vides(tmp_path) == [f"docs/decisions/README.md : {VIDE}"]


def test_readme_ne_lie_rien(tmp_path):
    arbre(tmp_path, {"README.md": "# E\n\nLe [site](https://exemple.org/a.md), [ici](#e).\n"})
    assert d.gabarits_vides(tmp_path) == [AUCUN]
    arbre(
        tmp_path,
        {
            "README.md": "# E\n\n[CLAUDE.md](CLAUDE.md), [la doc](docs/).\n",
            "CLAUDE.md": "# C\n\nDu texte.\n",
            "docs/a.md": "Du texte.\n",
        },
    )
    assert d.gabarits_vides(tmp_path) == []
    (tmp_path / "README.md").unlink()
    assert d.gabarits_vides(tmp_path) == ["pas de README.md"]
    arbre(tmp_path, {"readme.md": "# E\n\n[CLAUDE.md](CLAUDE.md)\n"})  # la casse compte
    assert d.gabarits_vides(tmp_path) == ["pas de README.md"]


def test_ignores(tmp_path):
    arbre(
        tmp_path,
        {
            "README.md": (
                "# E\n\n![capture](docs/capture.png) [script](scripts/vide.py)\n"
                "[site](https://exemple.org/vide.md) [absent](docs/absent.md) [mal](docs/mal.md)\n"
            ),
            "docs/capture.png": b"\x89PNG\r\n",
            "scripts/vide.py": "",
            "docs/mal.md": b"\xff\xfe\x00",
        },
    )
    assert d.gabarits_vides(tmp_path) == []
    arbre(tmp_path, {"README.md": "# E\n\n![capture](docs/capture.png)\n"})
    assert d.gabarits_vides(tmp_path) == [AUCUN]


def test_gabarits_vides_ordre_et_doublons(tmp_path):
    """Les constats suivent l'ordre des liens du README, un par chemin."""
    arbre(
        tmp_path,
        {
            "README.md": "# E\n\n[b](docs/b.md) [a](docs/a.md) [b encore](./docs/b.md#titre)\n",
            "docs/a.md": "",
            "docs/b.md": "# B\n\n*AAAA-MM-JJ*\n",
        },
    )
    assert d.gabarits_vides(tmp_path) == [f"docs/b.md : {MARQUEUR}", f"docs/a.md : {VIDE}"]


def test_gabarits_vides_lit_un_texte_en_crlf(tmp_path):
    arbre(
        tmp_path,
        {
            "README.md": (
                "# E\r\n\r\nLe [brief](docs/brief.md), le\r\n[cadrage](docs/cadrage.md).\r\n"
            ),
            "docs/brief.md": "# Brief\r\n\r\n<!-- Une\r\nconsigne. -->\r\n*En italique.*\r\n",
            "docs/cadrage.md": (
                "# Cadrage\r\n\r\n```\r\nUn bloc.\r\n```\r\n- **Date** : *AAAA-MM-JJ*\r\n"
            ),
        },
    )
    assert d.gabarits_vides(tmp_path) == [
        f"docs/brief.md : {VIDE}",
        f"docs/cadrage.md : {MARQUEUR}",
    ]


def test_gabarits_vides_chemins_pieges(tmp_path):
    racine = tmp_path / "racine"
    arbre(tmp_path, {"hors.md": ""})
    arbre(
        racine,
        {
            "README.md": "# E\n\n[Dehors](../hors.md), les [décisions](docs/d%C3%A9cisions/).\n",
            "docs/décisions/README.md": "# Décisions\n\nUne par fichier.\n",
        },
    )
    assert d.gabarits_vides(racine) == [f"docs/décisions/ : {DOSSIER}"]


@pytest.mark.skipif(sys.platform == "win32", reason="Windows refuse un saut de ligne dans un nom")
def test_gabarits_vides_nom_a_caractere_de_controle(tmp_path):
    arbre(tmp_path, {"README.md": "# E\n\n[Vide](docs/a%0Ab.md)\n", "docs/a\nb.md": ""})
    assert d.gabarits_vides(tmp_path) == [f"docs/a?b.md : {VIDE}"]


def test_gabarits_vides_en_ligne_de_commande(tmp_path, capsys, monkeypatch):
    """`--gabarits-vides` imprime un constat par ligne et rend toujours 0, une erreur comprise."""
    arbre(
        tmp_path,
        {
            "README.md": "# E\n\n[a](docs/a.md) [b](docs/b.md)\n",
            "docs/a.md": "",
            "docs/b.md": "# B\n\n*AAAA-MM-JJ*\n",
        },
    )
    assert d.main(["--racine", str(tmp_path), "--gabarits-vides"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"documentation : docs/a.md : {VIDE}",
        f"documentation : docs/b.md : {MARQUEUR}",
    ]
    arbre(tmp_path, {"docs/a.md": "Du texte.\n", "docs/b.md": "Du texte.\n"})
    assert d.main(["--racine", str(tmp_path), "--gabarits-vides"]) == 0
    assert capsys.readouterr().out == ""

    def explose(racine):
        raise RuntimeError("boum")

    monkeypatch.setattr(d, "gabarits_vides", explose, raising=False)
    assert d.main(["--racine", str(tmp_path), "--gabarits-vides"]) == 0
    assert capsys.readouterr().out.splitlines() == ["documentation : non lue (erreur)"]


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
    # Un dépôt public est de code, quoi que dise sa branche par défaut.
    r = lancer(env={**en_ci, "DEPOT_PRIVE": "false"}, cwd=clone, script=script)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "documentation : licence : LICENSE absent ou vide, exigé en nature code" in r.stdout
