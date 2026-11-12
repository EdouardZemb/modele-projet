"""Le contrôle des plans (`scripts/modele/plan.py`) : les trois sections d'un plan, « Mécanismes
annoncés » (LE-53), « Outils et cas limites » (LE-56) et « Revues » (LE-55)."""

import codecs
import re
import sys
from pathlib import Path

import plan as p
import pytest
import texte_pr

A_PY = "un\ndef f():\n    return 2\n"
REFUS = "plan : refus"
OUTIL_REFUSE = f"Outils et cas limites, ligne 2 : {p.FORMES[p.OUTILS]}"
REVUES_REFUSE = f"Revues, ligne 2 : {p.FORMES[p.REVUES]}"
MECA_REFUSE = f"Mécanismes annoncés, ligne 2 : {p.FORMES[p.MECANISMES]}"
OUVERT = p.COMMENTAIRE_OUVERT
# un titre de tâche après la clôture, comme dans les plans qui mettent à jour leur en-tête
APRES_LA_CLOTURE = ("### Tâche 1 : x", "### Tâche 2 : la clôture", "### Tâche 3 : l'en-tête")


def plan(
    meca="Aucun.",
    outils="Aucun.",
    revues="- relecture : Tâche 1",
    taches=("### Tâche 1 : x", "### Tâche 2 : la clôture"),
):
    """Un plan, dans cet ordre : un titre, les trois sections, `---`, puis les tâches. Une section
    à None est omise ; la ligne 1 d'une section est la ligne vide qui suit son titre, et son
    contenu commence à la ligne 2."""
    morceaux = ["# Un plan\n\n**Goal :** x\n"]
    for titre, contenu in (
        ("Mécanismes annoncés", meca),
        ("Outils et cas limites", outils),
        ("Revues", revues),
    ):
        if contenu is not None:
            morceaux.append(f"## {titre}\n\n{contenu}\n")
    morceaux.append("---\n")
    morceaux.extend(f"{tache}\n\n- [ ] une étape\n" for tache in taches)
    return "\n".join(morceaux)


def meca(lieu, extrait, comportement="le comportement annoncé"):
    """Une ligne de « Mécanismes annoncés »."""
    return f"- `{lieu}` — `{extrait}` — {comportement}"


@pytest.fixture
def racine(tmp_path):
    """Une racine où `src/a.py` a trois lignes."""
    r = tmp_path / "racine"
    (r / "src").mkdir(parents=True)
    (r / "src/a.py").write_bytes(A_PY.encode("utf-8"))
    return r


@pytest.fixture
def lancer(tmp_path, capsys):
    """Donne lancer(texte ou octets, *options) -> (code, sortie) : le plan est écrit dans
    `tmp_path/plan.md`, puis `main` le lit ; à None, le plan est absent."""

    def _lancer(texte, *options):
        fichier = tmp_path / "plan.md"
        fichier.unlink(missing_ok=True)
        if texte is not None:
            fichier.write_bytes(texte if isinstance(texte, bytes) else texte.encode("utf-8"))
        code = p.main([str(fichier), *options])
        captee = capsys.readouterr()
        return code, captee.out + captee.err

    return _lancer


def verifier(texte, racine, depots=None, lieux=True):
    return p.verifier(texte, racine, depots or {}, lieux)


def espionner(monkeypatch):
    """Pose des espions sur `Path.resolve`, `Path.read_bytes` et `Path.is_file` : la liste rendue
    note chaque appel, (nom, chemin)."""
    vus = []

    def espion(nom, vraie):
        def _espion(self, *args, **kwargs):
            vus.append((nom, str(self)))
            return vraie(self, *args, **kwargs)

        return _espion

    for nom in ("resolve", "read_bytes", "is_file"):
        monkeypatch.setattr(p.Path, nom, espion(nom, getattr(p.Path, nom)))
    return vus


def test_sections(racine):
    """Chaque section absente refuse et se nomme ; un titre de niveau 3 ne la remplace pas ; une
    section vide refuse ; « Aucun. » n'est admis que seul, et jamais dans « Revues » ; une ligne
    qui n'est ni une puce, ni sa suite, ni « Aucun. » refuse ; une ligne d'outil veut trois
    morceaux."""
    lignes, refus = verifier(plan(), racine)
    assert not refus, lignes
    assert lignes == ["0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues"]
    for cle, titre in (
        ("meca", "Mécanismes annoncés"),
        ("outils", "Outils et cas limites"),
        ("revues", "Revues"),
    ):
        lignes, refus = verifier(plan(**{cle: None}), racine)
        assert refus, cle
        assert f"section « {titre} » absente (titre de niveau 2)" in lignes, lignes
    niveau_3 = plan(revues=None).replace("---\n", "### Revues\n\n- relecture : Tâche 1\n\n---\n")
    lignes, refus = verifier(niveau_3, racine)
    assert refus
    assert "section « Revues » absente (titre de niveau 2)" in lignes, lignes
    cas = [
        ({"outils": ""}, "section « Outils et cas limites » vide"),
        ({"meca": "<!-- rien encore -->"}, "section « Mécanismes annoncés » vide"),
        ({"revues": "Aucun."}, REVUES_REFUSE),
        ({"outils": "Aucun.\n- git — un cas — un test"}, OUTIL_REFUSE),
        ({"meca": "Une phrase sans puce."}, MECA_REFUSE),
        ({"outils": "  git — un cas — un test"}, OUTIL_REFUSE),
        ({"outils": "- git — un cas"}, OUTIL_REFUSE),
        ({"outils": "- — un cas — un test"}, OUTIL_REFUSE),
        # un commentaire jamais fermé cache sur GitHub tout ce qui le suit
        (
            {"revues": "- relecture : Tâche 1\n<!-- - cachée : Tâche 1"},
            f"Revues, ligne 3 : {OUVERT}",
        ),
        # le même, après une puce qui serait valide sans lui : seul le refus du `<!--` jamais
        # fermé l'arrête, à sa ligne
        ({"revues": "- relecture : Tâche 1 <!-- note"}, f"Revues, ligne 2 : {OUVERT}"),
        ({"outils": "- <!-- a — b — c"}, f"Outils et cas limites, ligne 2 : {OUVERT}"),
    ]
    for reponses, attendu in cas:
        lignes, refus = verifier(plan(**reponses), racine)
        assert refus, reponses
        assert attendu in lignes, (reponses, lignes)
    # une ligne continuée par une ligne indentée, et un séparateur dans un code en ligne
    outils = (
        "- `git diff` — un chemin non ASCII,\n  mis entre guillemets — `test_x`\n"
        "- `a — b` — c — d"
    )
    lignes, refus = verifier(plan(outils=outils), racine)
    assert not refus, lignes
    assert lignes[-1] == "0 mécanismes vérifiés, 0 non vérifiés, 2 outils, 1 revues"
    # deux sections du même titre refusent, en double, et aucune des deux n'est lue : jointes, les
    # lignes de la seconde seraient nommées par un rang qui n'est pas le leur
    for titre, cle, contenu, resume in (
        (
            "Revues",
            "revues",
            "- relecture : Tâche 1\n\n## Revues\n\n- une relecture",
            "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 revues",
        ),
        (
            "Outils et cas limites",
            "outils",
            "- a — b — c\n\n## Outils et cas limites\n\n- d",
            "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues",
        ),
    ):
        lignes, refus = verifier(plan(**{cle: contenu}), racine)
        assert refus, cle
        assert f"section « {titre} » en double" in lignes, lignes
        assert not [ligne for ligne in lignes if ligne.startswith(f"{titre}, ligne")], lignes
        assert lignes[-1] == resume, lignes


def test_sous_liste_et_bloc_html(racine):
    """Une sous-liste, ou une ligne ouverte par un commentaire puis portant un texte, ne continue
    pas la puce d'avant : jointe à elle, elle passerait sans être lue, un lieu faux jamais ouvert
    (revue finale du lot 15). Chaque forme refuse, à son rang, dans les trois sections, et la puce
    d'avant reste lue : le résumé la compte. Une ligne de continuation ordinaire, un commentaire
    seul sur sa ligne, un commentaire suivi d'un texte après quatre espaces, au-delà de la borne
    des trois, ou les mêmes lignes dans un bloc clôturé, ne refusent pas. Une ligne qui commence
    par `-`, `*`, `+` ou un nombre sans être une puce, ou qui porte un marqueur au milieu, continue
    la puce : elle ne refuse pas, et le résumé compte la puce."""
    titres = {"meca": p.MECANISMES, "outils": p.OUTILS, "revues": p.REVUES}
    premieres = {
        "meca": meca("src/a.py:2", "def f("),
        "outils": "- git — un cas — un test",
        "revues": "- relecture : Tâche 1",
    }
    # chaque suite, jointe à sa puce, passerait : son lieu ne serait pas ouvert, son outil et sa
    # revue se fondraient dans ceux de la puce
    suites = {
        "meca": "`src/a.py:999` — `inexistant` — un second mécanisme",
        "outils": "git — un second cas — un second test",
        "revues": "finale : Tâche 1",
    }
    # le résumé, la puce d'avant comptée ; « Revues » garde sa puce par défaut dans les deux autres
    resumes = {
        "meca": "1 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues",
        "outils": "0 mécanismes vérifiés, 0 non vérifiés, 1 outils, 1 revues",
        "revues": "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues",
    }
    # « 1) », et un commentaire collé à une puce, que la lecture prendrait pour une puce en
    # colonne 0 (relecture de la revue finale du lot 15) ; « 2. », « 10. » et une sous-puce à six
    # espaces, que GitHub joint à la puce d'avant, et une sous-puce à quatre espaces, qu'il
    # imbrique (sa ronde 2) ; une tabulation après le marqueur, qu'il imbrique aussi (sa ronde 5)
    debuts = (
        "  - ",
        "   * ",
        "  + ",
        "  1. ",
        "  1) ",
        "  2. ",
        "  10. ",
        "    - ",
        "      - ",
        "\t- ",
        "  -\t",
        "  1.\t",
        "<!-- c --> - ",
        "<!-- c -->- ",
        "   <!-- c --> ",
    )
    for cle, titre in titres.items():
        contenus = [f"{premieres[cle]}\n{debut}{suites[cle]}" for debut in debuts]
        contenus.append(f"{premieres[cle]}\n  -")  # une puce seule, en fin de ligne
        for contenu in contenus:
            lignes, refus = verifier(plan(**{cle: contenu}), racine)
            assert refus, (cle, contenu, lignes)
            nommees = [ligne for ligne in lignes if ligne.startswith(f"{titre}, ligne")]
            assert nommees == [f"{titre}, ligne 3 : {p.FORMES[titre]}"], (cle, contenu, lignes)
            assert lignes[-1] == resumes[cle], (cle, contenu, lignes)
        # la ligne qui ferme un commentaire de deux lignes porte le rang
        texte = plan(**{cle: f"{premieres[cle]}\n<!-- c\nc --> {suites[cle]}"})
        lignes, refus = verifier(texte, racine)
        assert refus, (cle, lignes)
        assert f"{titre}, ligne 4 : {p.FORMES[titre]}" in lignes, (cle, lignes)
        assert lignes[-1] == resumes[cle], (cle, lignes)
    # « Aucun. » derrière un commentaire : GitHub rend la ligne en bloc HTML, jamais en « Aucun. »
    # (« Revues » refuse « Aucun. » de toute façon)
    for cle in ("meca", "outils"):
        lignes, refus = verifier(plan(**{cle: "<!-- c -->Aucun."}), racine)
        assert refus, (cle, lignes)
        nommees = [ligne for ligne in lignes if ligne.startswith(f"{titres[cle]}, ligne")]
        assert nommees == [f"{titres[cle]}, ligne 2 : {p.FORMES[titres[cle]]}"], (cle, lignes)
    admises = (
        "\n  suite du texte",
        "\n<!-- c -->",
        "\n\n```\n<!-- c --> - x\n  - y\n```",
        # un commentaire après quatre espaces, puis un texte : au-delà de la borne des trois
        # espaces, la ligne continue la puce, et GitHub la montre dans la puce (relecture de la
        # revue finale du lot 15, ronde 3)
        "\n    <!-- c --> suite du texte",
        # une ligne qui commence par `-`, `*`, `+` ou un nombre sans être une puce, faute d'un
        # blanc après le marqueur, ou qui porte un marqueur au milieu : elle continue la puce, et
        # GitHub la montre dans la puce (relecture de la revue finale du lot 15, rondes 4 et 5)
        "\n  -v est l'option qui le montre",
        "\n  *Note* : sous Windows seulement",
        "\n  2.5 fois plus lent",
        "\n  le cas - un autre cas",
        "\n  voir le point 3) plus haut",
        "\n  +3 s sous Windows",
        "\n  3)suite du texte",
    )
    for cle in titres:
        for suite in admises:
            lignes, refus = verifier(plan(**{cle: premieres[cle] + suite}), racine)
            assert not refus, (cle, suite, lignes)
            assert lignes[-1] == resumes[cle], (cle, suite, lignes)
    lignes, refus = verifier(plan(meca=premieres["meca"] + "\n  suite du texte"), racine)
    assert lignes[-1].startswith("1 mécanismes vérifiés, 0 non vérifiés"), lignes


def test_plan_lit_sous_liste_et_bloc_html_par_documentation(racine, monkeypatch):
    """`plan.py` et `texte_pr.py` lisent une sous-liste et une ligne en bloc HTML par
    `documentation.py`, à l'appel, sans leur propre copie : un double posé sur `documentation`
    change ce qu'ils refusent (relecture de la revue finale du lot 15). La docstring de `plan.py`
    dit les deux refus, et le commentaire de `SOUS_LISTE` dit sa sévérité."""
    import documentation

    for script in (p, texte_pr):
        assert not hasattr(script, "_SOUS_LISTE"), script

    def corps(section):
        return "## Ce que fait cette PR\n\nx\n\n## Écarts à la spec\n\n" + section + "\n"

    continue_la_revue = plan(revues="- relecture : Tâche 1\n  suite")
    ecart = corps("- un écart — promesse : spec § 4.1 — accord d'Edouard : 07/11/2026")
    continue_l_ecart = corps("- un écart\n  — promesse : § 2 — accord d'Edouard : 07/11/2026")
    # sans double
    assert not verifier(continue_la_revue, racine)[1]
    assert texte_pr.ecarts(ecart)[1] is False
    assert texte_pr.ecarts(continue_l_ecart)[1] is False
    # la ligne 2 de chaque section, lue en bloc HTML
    with monkeypatch.context() as m:
        m.setattr(documentation, "lignes_en_bloc_html", lambda texte: {2})
        assert verifier(plan(revues="- relecture : Tâche 1"), racine)[1]
        assert texte_pr.ecarts(ecart)[1] is True
    # toute ligne indentée, lue en sous-liste
    with monkeypatch.context() as m:
        m.setattr(documentation, "SOUS_LISTE", re.compile(r"[ \t]+"))
        assert verifier(continue_la_revue, racine)[1]
        assert texte_pr.ecarts(continue_l_ecart)[1] is True
    source = Path(documentation.__file__).read_text(encoding="utf-8").split("\n")
    fin = next(i for i, ligne in enumerate(source) if ligne.startswith("SOUS_LISTE = "))
    debut = fin
    while source[debut - 1].startswith("#"):
        debut -= 1
    commentaire = " ".join(" ".join(ligne[1:] for ligne in source[debut:fin]).split())
    assert (
        "`texte_pr.py` et `plan.py` la refusent toujours, plus strictement que GitHub, qui joint à "
        "la puce d'avant un numéro autre que 1 et une ligne indentée de quatre colonnes ou plus "
        "au-delà du texte de la puce."
    ) in commentaire, commentaire
    assert "GitHub en fait un élément de liste à part" not in commentaire, commentaire
    docstring = " ".join(p.__doc__.split())
    for fragment in (
        (
            "Une ligne indentée qui commence par une puce ou un numéro (`-`, `*`, `+`, `1.`) est "
            "une sous-liste, et ne continue pas la puce d'avant : elle refuse."
        ),
        (
            "Une ligne qui commence par un commentaire, après au plus trois espaces, et porte un "
            "texte après sa fermeture n'est ni une puce ni la suite d'une puce : GitHub la rend en "
            "bloc HTML, et elle refuse aussi."
        ),
    ):
        assert fragment in docstring, fragment


def test_normalisation_hors_du_code(racine):
    """Hors du code en ligne, un tiret demi-cadratin sépare comme un cadratin, une espace insécable
    (U+00A0, U+202F) compte pour une espace, et les apostrophes typographiques (U+2019, U+02BC)
    deviennent droites : un plan écrit dans un traitement de texte se lit comme un plan écrit à la
    main. Aucune règle de `plan.py` ne lit une apostrophe hors du code : leur normalisation se voit
    sur `_normaliser`, et le test de parité avec `texte_pr.py` la garde."""
    demi = "\u2013"
    cas = [
        ("U+2013", "meca", f"- `src/a.py:2` {demi} `def f(` {demi} la fonction existe"),
        ("U+2013", "outils", f"- git {demi} un cas {demi} un test"),
    ]
    for nom, espace in (("U+00A0", "\u00a0"), ("U+202F", "\u202f")):
        cas += [
            (nom, "meca", f"- `src/a.py:2`{espace}—{espace}`def f(`{espace}—{espace}x"),
            (nom, "outils", f"- git{espace}—{espace}un cas{espace}—{espace}un test"),
            (nom, "revues", f"- relecture : Tâche{espace}1"),
        ]
    for nom, cle, ligne in cas:
        reponses = {"meca": meca("src/a.py:2", "def f("), "outils": "- a — b — c", cle: ligne}
        lignes, refus = verifier(plan(**reponses), racine)
        assert not refus, (nom, cle, lignes)
        assert lignes[-1] == "1 mécanismes vérifiés, 0 non vérifiés, 1 outils, 1 revues", (
            nom,
            cle,
            lignes,
        )
    doc = p._documentation()
    brut = "l\u2019outil, l\u02bcoutil,\u00a0un\u202fcas, e\u0301 ; `l\u2019outil\u00a0`"
    assert p._normaliser(brut, doc) == "l'outil, l'outil, un cas, é ; `l\u2019outil\u00a0`"


def test_plan_et_texte_pr_normalisent_de_meme():
    """La normalisation est copiée dans les deux scripts, qui lisent une section de la même façon :
    la même table de traduction, le même séparateur et la même puce. Ce test les empêche de
    diverger."""
    assert p._TRADUCTION == texte_pr._TRADUCTION
    assert p._SEPARATEUR.pattern == texte_pr._SEPARATEUR.pattern
    assert p._PUCE.pattern == texte_pr._PUCE.pattern


SUPERPOWERS = """# Une fonction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** une fonction.

**Architecture:** un module.

**Tech Stack:** Python.

## Review Focus

1. Le cas limite de la fonction.

## Mécanismes annoncés

- `src/a.py:2` — `def f(` — la fonction existe déjà.

## Outils et cas limites

- `git diff` — un chemin non ASCII entre guillemets — `test_x`

## Revues

- la revue de chaque tâche : Task 1

---

### Task 1: x

**Files:**
- Create: `src/b.py`
- Test: `tests/test_b.py`

- [ ] **Step 1: Write the failing test**

```python
def test_x():
    assert f() == 2
```

- [ ] **Step 2: Run the test**

### Task 2: closure

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Delete the plan**
"""


def test_plan_forme_superpowers(racine, lancer):
    """Le gabarit de *superpowers* : un en-tête, une section de tête, les trois sections, `---`,
    puis les tâches, chacune avec ses fichiers et ses cases. Une section se lit bornée, jusqu'au
    premier titre ou séparateur : sans quoi « Revues » avalerait les tâches."""
    code, sortie = lancer(SUPERPOWERS, "--racine", str(racine))
    assert code == 0, sortie
    assert "1 mécanismes vérifiés, 0 non vérifiés, 1 outils, 1 revues" in sortie, sortie


def test_mecanismes(racine):
    """Un lieu, un extrait, un comportement : l'extrait se cherche sur la ligne citée, ou dans la
    plage, de 40 lignes au plus."""
    (racine / "src/long.py").write_text(
        "".join(f"ligne {n}\n" for n in range(1, 101)), encoding="utf-8"
    )
    (racine / "src/c.py").write_text("x = 'a`b'\n", encoding="utf-8")
    (racine / "src/d.py").write_text('message = "l’outil"\n', encoding="utf-8")
    verifies = [
        meca("src/a.py:2", "def f("),
        meca("src/a.py:2-3", "return 2"),
        meca("src/long.py:1-40", "ligne 40"),
        # un extrait entre deux accents graves, qui en contient un
        "- `src/c.py:1` — `` a`b `` — un accent grave dans l'extrait",
        # la normalisation ne touche pas un code en ligne : l'apostrophe typographique y reste
        meca("src/d.py:1", "l’outil"),
    ]
    for ligne in verifies:
        lignes, refus = verifier(plan(meca=ligne), racine)
        assert not refus, (ligne, lignes)
        assert lignes[-1].startswith("1 mécanismes vérifiés, 0 non vérifiés"), lignes
    refuses = [
        (meca("src/a.py:3", "def f("), "extrait absent de src/a.py:3"),
        (meca("src/a.py:4", "def f("), "ligne 4 hors du fichier (3 lignes)"),
        (meca("src/b.py:1", "def f("), "fichier absent : src/b.py"),
        (meca("src/long.py:1-41", "ligne 41"), "chemin refusé (plage de plus de 40 lignes)"),
        ("- `src/a.py:2` — `def f(`", p.FORMES[p.MECANISMES]),
        ("- `src/a.py:2` — `def f(` —", p.FORMES[p.MECANISMES]),
        ("- `src/a.py:2` — ` ` — x", p.FORMES[p.MECANISMES]),
        ("- src/a.py:2 — `def f(` — x", p.FORMES[p.MECANISMES]),
    ]
    for ligne, attendu in refuses:
        lignes, refus = verifier(plan(meca=ligne), racine)
        assert refus, ligne
        assert f"Mécanismes annoncés, ligne 2 : {attendu}" in lignes, (ligne, lignes)


def test_mecanismes_autre_depot(racine, tmp_path, lancer):
    """Un lieu préfixé se vérifie dans le clone que nomme `--depot` ; sans lui, il est « non
    vérifié », sans refus. Un clone absent est une erreur d'usage."""
    clone = tmp_path / "serveur"
    (clone / "outils").mkdir(parents=True)
    (clone / "outils/x.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    texte = plan(meca=meca("serveur:outils/x.sh:1", "#!/bin/sh"))
    code, sortie = lancer(texte, "--racine", str(racine))
    assert code == 0, sortie
    assert "Mécanismes annoncés, ligne 2 : non vérifié (dépôt serveur absent)" in sortie, sortie
    assert "0 mécanismes vérifiés, 1 non vérifiés" in sortie, sortie
    code, sortie = lancer(texte, "--racine", str(racine), "--depot", f"serveur={clone}")
    assert code == 0, sortie
    assert "1 mécanismes vérifiés, 0 non vérifiés" in sortie, sortie
    absent = plan(meca=meca("serveur:outils/x.sh:2", "#!/bin/sh"))
    code, sortie = lancer(absent, "--racine", str(racine), "--depot", f"serveur={clone}")
    assert code == 1, sortie
    assert "extrait absent de serveur:outils/x.sh:2" in sortie, sortie
    absent = f"serveur={tmp_path / 'absent'}"
    code, sortie = lancer(texte, "--racine", str(racine), "--depot", absent)
    assert code == p.EXIT_USAGE == 64, sortie


def test_sans_lieux(racine, lancer):
    """Avec `--sans-lieux`, un lieu se lit sans ouvrir de fichier : une ligne absente passe, et le
    résumé le dit ; un chemin refusé refuse quand même."""
    code, sortie = lancer(plan(meca=meca("src/a.py:9", "def f(")), "--racine", str(racine))
    assert code == 1, sortie
    code, sortie = lancer(
        plan(meca=meca("src/a.py:9", "def f(")), "--racine", str(racine), "--sans-lieux"
    )
    assert code == 0, sortie
    assert "1 mécanismes, lieux non ouverts, 0 outils, 1 revues" in sortie, sortie
    sortant = plan(meca=meca("../x.py:1", "x"))
    code, sortie = lancer(sortant, "--racine", str(racine), "--sans-lieux")
    assert code == 1, sortie
    assert "Mécanismes annoncés, ligne 2 : chemin refusé (..)" in sortie, sortie


def test_plan_chemins_refuses_avant_resolve(racine, monkeypatch):
    """Un chemin qui sort de la racine, absolu, à barre oblique inverse ou à deux-points refuse
    avant tout `Path` : rien ne le résout ni ne le lit. Sous Windows, `resolve` ouvrirait un
    partage réseau ou un lecteur, et `racine / "/etc/x"` donnerait `/etc/x`."""
    b = chr(92)  # les outils décodent les barres obliques inverses écrites en clair
    assert p.lieu("src/a.py:2") == (None, "src/a.py", 2, 2)
    assert p.lieu("serveur:outils/x.sh:1-3") == ("serveur", "outils/x.sh", 1, 3)
    raisons = {
        "../x.py:1": "..",
        "/etc/x:1": "chemin absolu",
        f"src{b}a.py:1": "barre oblique inverse",
        "src/a:b.py:1": "deux-points dans le chemin",
        "Z:/x.py:1": "chemin absolu",
        "src/../a.py:1": "..",
        "a:b:c:1": "deux-points dans le chemin",
        "src/a.py": "ligne invalide",
        "src/a.py:0": "ligne invalide",
        "src/a.py:x": "ligne invalide",
        "src/a.py:3-2": "ligne invalide",
        "src/a.py:1-41": "plage de plus de 40 lignes",
    }
    for texte, raison in raisons.items():
        with pytest.raises(ValueError) as erreur:
            p.lieu(texte)
        assert str(erreur.value) == raison, texte
    vus = espionner(monkeypatch)
    for texte in list(raisons)[:6]:
        vus.clear()
        lignes, refus = verifier(plan(meca=meca(texte, "x")), racine)
        assert refus, texte
        assert f"Mécanismes annoncés, ligne 2 : chemin refusé ({raisons[texte]})" in lignes, lignes
        assert vus == [], (texte, vus)


def test_plan_chemin_vide_refuse_avant_resolve(racine, monkeypatch):
    """Un lieu sans chemin (`:2`, `serveur::2`) refuse, avec ou sans les lieux, avant tout `Path` :
    sous `--sans-lieux`, il compterait sinon comme un mécanisme, et avec les lieux le refus dirait
    « fichier absent » sans nommer de fichier."""
    vides = (":2", "serveur::2")
    for texte in vides:
        with pytest.raises(ValueError) as erreur:
            p.lieu(texte)
        assert str(erreur.value) == "ligne invalide", texte
    vus = espionner(monkeypatch)
    for texte in vides:
        for lieux in (True, False):
            vus.clear()
            texte_du_plan = plan(meca=meca(texte, "def f("))
            lignes, refus = verifier(texte_du_plan, racine, {"serveur": racine}, lieux)
            assert refus, (texte, lieux, lignes)
            assert "Mécanismes annoncés, ligne 2 : chemin refusé (ligne invalide)" in lignes, lignes
            assert vus == [], (texte, lieux, vus)


def test_plan_lien_hors_de_la_racine(racine, tmp_path):
    """Un fichier cité qui sort de sa racine une fois résolu, par un lien symbolique, est absent,
    même s'il porte l'extrait ; un lien qui reste sous la racine se lit. Sous Windows, créer un
    lien demande un droit que la session peut ne pas avoir : le test saute alors, jamais
    ailleurs."""
    dehors = tmp_path / "dehors.py"
    dehors.write_text("un\ndef f():\n", encoding="utf-8")
    try:
        (racine / "src/sortant.py").symlink_to(dehors)
        (racine / "src/dedans.py").symlink_to(racine / "src/a.py")
    except OSError as erreur:
        if sys.platform != "win32":
            raise
        pytest.skip(f"lien symbolique impossible sans le droit de le créer ({erreur.winerror})")
    lignes, refus = verifier(plan(meca=meca("src/dedans.py:2", "def f(")), racine)
    assert not refus, lignes
    lignes, refus = verifier(plan(meca=meca("src/sortant.py:2", "def f(")), racine)
    assert refus, lignes
    assert "Mécanismes annoncés, ligne 2 : fichier absent : src/sortant.py" in lignes, lignes


def test_plan_chemin_a_espaces_et_gabarit(racine):
    """Un chemin peut porter des espaces, des `{%` et des `'`, comme les gabarits du modèle."""
    chemin = "template/{% if cible == 'serveur' %}deploiement{% endif %}/a b.sh"
    (racine / chemin).parent.mkdir(parents=True)
    (racine / chemin).write_text("echo un\n", encoding="utf-8")
    lignes, refus = verifier(plan(meca=meca(f"{chemin}:1", "echo un")), racine)
    assert not refus, lignes
    assert lignes[-1].startswith("1 mécanismes vérifiés"), lignes


def test_revues(racine):
    """Chaque revue cite au moins une tâche des titres de niveau 3, `Tâche N` ou `Task N`, sans
    égard à la casse ; une tâche citée précède la clôture ; un numéro en double refuse. Un titre
    après la clôture ne refuse pas, mais une revue qui le cite refuse."""
    cas = [
        ({"revues": "- relecture : Tâche 3"}, "Revues, ligne 2 : Tâche 3 absente des titres"),
        (
            {"revues": "- relecture : Tâche 2"},
            "Revues, ligne 2 : Tâche 2 ne précède pas la clôture (Tâche 2)",
        ),
        ({"revues": "- une relecture"}, "Revues, ligne 2 : aucune tâche citée"),
        (
            {"taches": ("### Tâche 1 : x", "### Tâche 1 : y", "### Tâche 2 : la clôture")},
            "Tâche 1 en double",
        ),
        (
            {"revues": "- relecture : Tâche 3", "taches": APRES_LA_CLOTURE},
            "Revues, ligne 2 : Tâche 3 ne précède pas la clôture (Tâche 2)",
        ),
    ]
    for reponses, attendu in cas:
        lignes, refus = verifier(plan(**reponses), racine)
        assert refus, reponses
        assert attendu in lignes, (reponses, lignes)
    for reponses in (
        {"revues": "- relecture : tâche 1"},
        {"revues": "- relecture : Tâche 1\n- finale : TASK 1, puis tâche 1"},
        {"taches": APRES_LA_CLOTURE},
        {"revues": "- relecture : Tâche 2", "taches": ("### Tâche 1 : x", "### Tâche 2 : y")},
    ):
        lignes, refus = verifier(plan(**reponses), racine)
        assert not refus, (reponses, lignes)


MAITRE = ("### Tranche 1 · x", "### Tranche 2 · y", "### Tranche 3 · la clôture")


def test_plan_tranches_unites(racine):
    """`### Tranche N` est une unité, sans égard à la casse ; `### Tranche 2.1` est la tranche 2 ;
    `### Tranches` et `### Ce que ce plan tranche` n'en sont pas, ni un titre dans un bloc de code
    ou un commentaire. Un plan sans unité reste un plan à tâches."""
    maitre = ("### Tranche 1 · x", "### tranche 2 : y", "### Tranche 3 · la clôture")
    revues = "- relecture : Tranche 1, Tranche 2"
    lignes, refus = verifier(plan(revues=revues, taches=maitre), racine)
    assert not refus, lignes
    assert lignes == ["0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues"]
    doubles = ("### Tranche 2.1 · a", "### Tranche 2.2 · b", "### Tranche 3 · la clôture")
    lignes, refus = verifier(plan(revues="- relecture : Tranche 2", taches=doubles), racine)
    assert refus and "Tranche 2 en double" in lignes, lignes
    autres = (
        "### Tranches 3 · x\n\n### Ce que ce plan tranche",
        "```\n### Tranche 4 · code\n```",
        "<!--\n### Tranche 5 · cachée\n-->",
        *APRES_LA_CLOTURE,
    )
    lignes, refus = verifier(plan(taches=autres), racine)
    assert not refus, lignes  # un plan à tâches, non mêlé
    lignes, refus = verifier(plan(taches=()), racine)
    assert "Revues, ligne 2 : Tâche 1 absente des titres" in lignes, lignes


def test_plan_citations_selon_la_sorte(racine):
    """Un plan à tâches cite des tâches, un plan maître des tranches ; l'autre mot n'est que du
    texte. « qui tranche 2 questions » cite la tranche 2 ; les pluriels, « trancher 2 » et
    « retranche 2 » ne citent rien."""
    aucune = "Revues, ligne 2 : aucune tranche citée"
    cas = [
        # (titres, revue, refus attendu ou None)
        (None, "- la revue de la tranche 1 : Tâche 1", None),
        (None, "- la revue de la tranche 1", "Revues, ligne 2 : aucune tâche citée"),
        (MAITRE, "- la revue de la tâche 3 du plan de la tranche 2 : Tranche 2", None),
        (MAITRE, "- relecture : Tâche 1", aucune),
        (MAITRE, "- une revue qui tranche 2 questions", None),
        (MAITRE, "- relecture : TRANCHE 1", None),
        (MAITRE, "- Tranches 1 à 2", aucune),
        (MAITRE, "- trancher 2 points", aucune),
        (MAITRE, "- on retranche 2 lignes", aucune),
        (MAITRE, "- relecture : Tranche 4", "Revues, ligne 2 : Tranche 4 absente des titres"),
        (
            MAITRE,
            "- finale : Tranche 3",
            "Revues, ligne 2 : Tranche 3 ne précède pas la clôture (Tranche 3)",
        ),
    ]
    for titres, revue, attendu in cas:
        reponses = {"revues": revue} | ({} if titres is None else {"taches": titres})
        lignes, refus = verifier(plan(**reponses), racine)
        if attendu is None:
            assert not refus, (revue, lignes)
        else:
            assert refus and attendu in lignes, (revue, lignes)


def test_plan_mele(racine):
    """Un plan qui mêle tâches et tranches refuse, juste avant le résumé ; ses citations se lisent
    dans les deux sortes, chacune contre ses titres, sa clôture dans l'une ou l'autre."""
    taches = ("### Tâche 1 : x", "### Tranche 2 · y", "### Tâche 3 : la clôture")
    revues = "- relecture : Tâche 1, Tranche 2\n- finale : Tranche 5\n- une relecture"
    lignes, refus = verifier(plan(revues=revues, taches=taches), racine)
    assert refus
    assert lignes[-2] == p.MELE == "le plan mêle des tâches et des tranches", lignes
    assert "Revues, ligne 3 : Tranche 5 absente des titres" in lignes, lignes
    assert "Revues, ligne 4 : aucune tâche ni tranche citée" in lignes, lignes
    assert not [ligne for ligne in lignes if ligne.startswith("Revues, ligne 2")], lignes


def test_plan_mele_cloture_croisee(racine):
    """Dans un plan mêlé, la clôture est la première unité de l'une ou l'autre sorte : une
    tâche citée après une clôture qui est une tranche refuse ; le même numéro dans les deux sortes
    n'est jamais « en double », seul le refus du plan mêlé paraît."""
    taches = ("### Tâche 1 : x", "### Tranche 2 · la clôture", "### Tâche 3 : y")
    lignes, refus = verifier(plan(revues="- relecture : Tâche 3", taches=taches), racine)
    attendu = "Revues, ligne 2 : Tâche 3 ne précède pas la clôture (Tranche 2)"
    assert refus and attendu in lignes, lignes
    memes = ("### Tâche 1 : x", "### Tranche 1 · y", "### Tâche 2 : la clôture")
    lignes, refus = verifier(plan(revues="- relecture : Tâche 1, Tranche 1", taches=memes), racine)
    assert refus
    assert lignes[-2] == p.MELE, lignes
    assert not [ligne for ligne in lignes if "en double" in ligne or "Revues" in ligne], lignes


def test_plan_titres_d_un_plan_maitre_reel(racine):
    """Les titres du plan maître du lot 1 de `pupitre` (Review Focus 1) : deux titres de niveau 3
    qui ne sont pas des unités, puis huit tranches, la dernière portant la clôture."""
    taches = (
        "### Les choix de la maîtrise d'ouvrage (2026-11-09)",
        "### Ce que ce plan tranche",
        *(f"### Tranche {n} · x" for n in range(1, 8)),
        "### Tranche 8 · la revue finale et la clôture",
    )
    sept = ", ".join(f"Tranche {n}" for n in range(1, 8))
    revues = f"- la revue de chaque plan de tranche : {sept}"
    lignes, refus = verifier(plan(revues=revues, taches=taches), racine)
    assert not refus, lignes
    lignes, refus = verifier(plan(revues="- la revue finale : Tranche 8", taches=taches), racine)
    attendu = "Revues, ligne 2 : Tranche 8 ne précède pas la clôture (Tranche 8)"
    assert refus and attendu in lignes, lignes


def test_plan_a_taches_qui_nomme_sa_tranche(racine):
    """Un plan de tranche, à tâches, qui écrit « Tranche N » dans ses titres et ses revues passe
    (Review Focus 2)."""
    taches = (
        "### Tâche 1 : le stockage de la tranche 1",
        "### Tâche 2 : la clôture de la Tranche 1",
    )
    revues = "- la revue de la Tranche 1 : Tâche 1"
    lignes, refus = verifier(plan(revues=revues, taches=taches), racine)
    assert not refus, lignes


def test_formes_dites(racine):
    """Chaque refus de forme dit la forme de sa section ; le `<!--` jamais fermé a son message."""
    assert p.FORMES == {
        "Mécanismes annoncés": "forme attendue : - `<chemin>:<ligne>` — `<extrait>` — "
        "<comportement annoncé>, ou « Aucun. » seul",
        "Outils et cas limites": "forme attendue : - <outil> — <cas limite> — <test>, "
        "ou « Aucun. » seul",
        "Revues": "forme attendue : - <revue> : Tâche N, ou Tranche N dans un plan maître ; "
        "jamais « Aucun. »",
    }
    assert p.COMMENTAIRE_OUVERT == "commentaire HTML jamais fermé, qui cache la suite"
    mal_formees = {"meca": "Une phrase.", "outils": "- a — b", "revues": "Aucun."}
    titres = {"meca": p.MECANISMES, "outils": p.OUTILS, "revues": p.REVUES}
    for cle, ligne in mal_formees.items():
        lignes, refus = verifier(plan(**{cle: ligne}), racine)
        assert refus, cle
        assert f"{titres[cle]}, ligne 2 : {p.FORMES[titres[cle]]}" in lignes, (cle, lignes)
    ouverts = (
        ({"revues": "- relecture : Tâche 1 <!-- note"}, "Revues", 2),
        ({"revues": "- relecture : Tâche 1\n<!-- - cachée : Tâche 1"}, "Revues", 3),
        ({"outils": "- <!-- a — b — c"}, "Outils et cas limites", 2),
        ({"meca": "- <!-- a — b — c"}, "Mécanismes annoncés", 2),
    )
    for reponses, titre, rang in ouverts:
        lignes, refus = verifier(plan(**reponses), racine)
        assert refus, reponses
        assert f"{titre}, ligne {rang} : {p.COMMENTAIRE_OUVERT}" in lignes, (reponses, lignes)
        assert not [ligne for ligne in lignes if "vide" in ligne], (reponses, lignes)


def test_plan_titres_des_plans_reels(racine):
    """Les titres des plans réels : `### Task N:` de *superpowers*, une parenthèse avant le
    deux-points, un titre de niveau 2 qui nomme une tâche sans en être une, et un titre dans un
    bloc de code, qui n'en est pas un."""
    taches = (
        "### Task 1: x",
        "## Avant la tâche 1\n\n- [ ] relever l'état",
        "### Task 5 (`serveur`) : y\n\n```python\n### Tâche 9 : piège\nx = 1\n```",
    )
    revues = "- relecture : Task 1, puis Task 5"
    lignes, refus = verifier(plan(revues=revues, taches=taches), racine)
    assert not refus, lignes
    lignes, refus = verifier(plan(revues="- relecture : Tâche 9", taches=taches), racine)
    assert refus
    assert "Revues, ligne 2 : Tâche 9 absente des titres" in lignes, lignes


def test_titres_caches_par_un_commentaire_jamais_ferme(racine):
    """Un `<!--` jamais fermé qui ouvre un bloc, en tête de ligne, ou après une puce, un numéro ou
    `>`, cache sur GitHub tout ce qui le suit, les titres de tâche compris : `plan.py` ne les lit
    pas non plus, comme `sections()` (relecture de la revue finale du lot 15, rondes 2 et 3). Que
    les tâches suivent un titre de niveau 2 ou une ligne de séparation, la revue qui cite la
    tâche 1 refuse. Un `<!--` jamais fermé qui n'ouvre pas de bloc ne cache rien, sur GitHub comme
    ici : dans un bloc de code clôturé, au milieu d'un paragraphe, ou en code en ligne."""
    debut = (
        "# Plan\n\n## Mécanismes annoncés\n\nAucun.\n\n## Outils et cas limites\n\nAucun.\n\n"
        "## Revues\n\n- revue : Tâche 1\n\n"
    )
    taches = "\n\n### Tâche 1 : x\n\n### Tâche 2 : clôture\n"
    separations = (("p4a", "## Tâches\n\n"), ("p4b", "---\n\n"))
    # GitHub (`gh api markdown`) ne rend aucun titre après chacune de ces ouvertures
    for ouverture in (
        "<!-- jamais fermé",
        "- <!-- jamais fermé",
        "1. <!-- jamais fermé",
        "> <!-- jamais fermé",
    ):
        for nom, separation in separations:
            lignes, refus = verifier(debut + separation + ouverture + taches, racine)
            assert refus, (ouverture, nom, lignes)
            attendu = "Revues, ligne 2 : Tâche 1 absente des titres"
            assert attendu in lignes, (ouverture, nom, lignes)
    # GitHub rend les deux titres après chacun de ces textes : les tâches se lisent, la revue passe
    for avant in (
        "```\n<!-- dans un bloc de code\n```",
        "Un paragraphe <!-- jamais fermé au milieu.",
        "Un `<!--` en code en ligne.",
    ):
        for nom, separation in separations:
            lignes, refus = verifier(debut + separation + avant + taches, racine)
            assert not refus, (avant, nom, lignes)
    fragment = "lus hors des blocs de code clôturés et des blocs de commentaire HTML, fermés ou non"
    for docstring in (p.__doc__, p._unites.__doc__):
        assert fragment in " ".join(docstring.split()), docstring


def test_docstring_dit_les_tranches():
    """Le module dit les tranches, le plan maître, le plan mêlé et la forme de la sortie."""
    doc = " ".join(p.__doc__.split())
    for fragment in (
        "`### Tranche N`",
        "des numéros de tâche ou de tranche",
        "les formes fixes",
        "MELE",
    ):
        assert fragment in doc, fragment


def test_plan_encodages(racine, lancer):
    """Un plan écrit sous PowerShell 5.1, en UTF-16 ou en UTF-8 avec BOM, se lit ; un fichier cité
    en CRLF, ou qui porte U+2028, se numérote comme git et GitHub le numérotent, par `\\n`."""
    texte = plan(meca=meca("src/a.py:2", "def f("))
    # le BOM précède une ligne lue, le titre de la première section : laissé en tête, il la cache
    texte = texte[texte.index("## Mécanismes annoncés") :]
    for nom, octets in (
        ("UTF-16", texte.encode("utf-16")),
        ("UTF-16 BE", codecs.BOM_UTF16_BE + texte.encode("utf-16-be")),
        ("UTF-8 avec BOM", texte.encode("utf-8-sig")),
    ):
        code, sortie = lancer(octets, "--racine", str(racine))
        assert code == 0, (nom, sortie)
        assert "1 mécanismes vérifiés" in sortie, (nom, sortie)
    (racine / "src/crlf.py").write_bytes(b"un\r\ndef f():\r\n    return 2\r\n")
    (racine / "src/sep.py").write_bytes("un\ndef f():\u2028    pass\n    return 2\n".encode())
    for ligne in (
        meca("src/crlf.py:2", "def f():"),
        meca("src/crlf.py:3", "return 2"),
        meca("src/sep.py:3", "return 2"),
    ):
        lignes, refus = verifier(plan(meca=ligne), racine)
        assert not refus, (ligne, lignes)
    lignes, refus = verifier(plan(meca=meca("src/crlf.py:4", "x")), racine)
    assert "Mécanismes annoncés, ligne 2 : ligne 4 hors du fichier (3 lignes)" in lignes, lignes


def test_main(racine, lancer):
    """0 sans refus, 1 avec ; 64 pour un plan absent, une racine absente ou un `--depot` mal formé.
    La sortie ne cite jamais une ligne du plan, seulement des chemins, chaque caractère de contrôle
    ou séparateur de ligne remplacé par `?`."""
    code, sortie = lancer(plan(), "--racine", str(racine))
    assert code == 0, sortie
    assert REFUS not in sortie
    lignes = sortie.splitlines()
    resume = "plan.md : 0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues"
    assert lignes[-1].endswith(resume), sortie
    assert all(ligne.startswith("plan : ") for ligne in lignes), sortie
    refuse = plan(
        meca=meca("src/a.py:3", "def f(", "SENTINELLE")
        + "\n"
        + meca("src/b\u2028.py:1", "x", "SENTINELLE")
        + "\n- SENTINELLE"
    )
    code, sortie = lancer(refuse, "--racine", str(racine))
    assert code == 1, sortie
    assert sortie.splitlines()[-1] == REFUS, sortie
    assert "fichier absent : src/b?.py" in sortie, sortie
    assert "SENTINELLE" not in sortie, sortie
    for code, sortie in (
        lancer(None, "--racine", str(racine)),
        lancer(plan(), "--racine", str(racine.parent / "SENTINELLE")),  # une racine absente
        lancer(plan(), "--racine", str(racine), "--depot", "SENTINELLE"),
        lancer(plan(), "--racine", str(racine), "--depot", "=SENTINELLE"),
        lancer(plan(), "--inconnue", "SENTINELLE"),
    ):
        assert code == p.EXIT_USAGE == 64, sortie
        assert "SENTINELLE" not in sortie, sortie
