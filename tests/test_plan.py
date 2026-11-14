"""Le contrôle des plans (`scripts/modele/plan.py`) : les sections d'un plan, « Mécanismes
annoncés » (LE-53), « Outils et cas limites » (LE-56), « Effets cherchés » et « Revues » (LE-55)."""

import codecs
import re
import sys
from pathlib import Path

import plan as p
import pytest
import texte_pr
from conftest import RACINE

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
    effets=None,
    revues="- relecture : Tâche 1",
    taches=("### Tâche 1 : x", "### Tâche 2 : la clôture"),
    entete="",
):
    """Un plan en cours, dans cet ordre : un titre, `entete`, les sections, `---`, puis les tâches.
    Une section à None est omise ; « Effets cherchés » l'est par défaut ; la ligne 1 d'une
    section est la ligne vide qui suit son titre, et son contenu commence à la ligne 2."""
    morceaux = ["# Un plan\n\n**Goal :** x\n" + entete]
    for titre, contenu in (
        ("Mécanismes annoncés", meca),
        ("Outils et cas limites", outils),
        ("Effets cherchés", effets),
        ("Revues", revues),
    ):
        if contenu is not None:
            morceaux.append(f"## {titre}\n\n{contenu}\n")
    morceaux.append("---\n")
    morceaux.extend(f"{tache}\n\n- [ ] une étape\n" for tache in taches)
    return "\n".join(morceaux)


# une clôture qui nomme les six gestes, chacun par un passage de `PASSAGES`
CLOTURE_CONFORME = (
    "Supprimer le plan ; `CLAUDE.md` à jour ; README relu ; les leçons du lot au registre ; "
    "« Closes #1 » ; Tête relue."
)
PASSAGES = {
    "le plan supprimé": "Supprimer le plan",
    "CLAUDE.md ou un ADR": "`CLAUDE.md` à jour",
    "le README": "README relu",
    "les leçons du lot": "les leçons du lot au registre",
    "la fermeture de l'issue": "« Closes #1 »",
    "la tête relue": "Tête relue",
}


def cloture(texte=CLOTURE_CONFORME, titre="### Tâche 2 : la clôture"):
    """Les tâches d'un plan dont l'unité de clôture, la Tâche 2, porte `texte`."""
    return ("### Tâche 1 : x", f"{titre}\n\n{texte}")


def plan_neuf(**kw):
    """Un plan neuf : celui de `plan()`, avec « Effets cherchés » à « Aucun. » et une clôture qui
    nomme les six gestes, sauf si `effets` ou `taches` sont donnés."""
    kw.setdefault("effets", "Aucun.")
    kw.setdefault("taches", cloture())
    return plan(**kw)


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


def verifier(texte, racine, depots=None, lieux=True, neuf=False, cloture=()):
    return p.verifier(texte, racine, depots or {}, lieux, neuf, cloture)


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
    assert lignes == ["0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues"]
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
    assert lignes[-1] == "0 mécanismes vérifiés, 0 non vérifiés, 2 outils, 0 effets, 1 revues"
    # deux sections du même titre refusent, en double, et aucune des deux n'est lue : jointes, les
    # lignes de la seconde seraient nommées par un rang qui n'est pas le leur
    for titre, cle, contenu, resume in (
        (
            "Revues",
            "revues",
            "- relecture : Tâche 1\n\n## Revues\n\n- une relecture",
            "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 0 revues",
        ),
        (
            "Outils et cas limites",
            "outils",
            "- a — b — c\n\n## Outils et cas limites\n\n- d",
            "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues",
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
        "meca": "1 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues",
        "outils": "0 mécanismes vérifiés, 0 non vérifiés, 1 outils, 0 effets, 1 revues",
        "revues": "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues",
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
        resume = "1 mécanismes vérifiés, 0 non vérifiés, 1 outils, 0 effets, 1 revues"
        assert lignes[-1] == resume, (nom, cle, lignes)
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
    assert "1 mécanismes vérifiés, 0 non vérifiés, 1 outils, 0 effets, 1 revues" in sortie, sortie


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
    assert "1 mécanismes, lieux non ouverts, 0 outils, 0 effets, 1 revues" in sortie, sortie
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
    assert lignes == ["0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues"]
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
        "Effets cherchés": "forme attendue : - <décision> — <où elle arrive> — "
        "<comment c'est vérifié>, ou « Aucun. » seul",
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


def test_docstring_dit_les_effets():
    """Le module dit la quatrième section, `--neuf` et sa limite, la ligne « Usage : » et le 64
    de la valeur vide de `--cloture`."""
    doc = " ".join(p.__doc__.split())
    for fragment in (
        "ses quatre sections de niveau 2",
        "« Effets cherchés » et « Revues »",
        "Effets cherchés. Une puce par décision du plan",
        "« Aucun. » seul est admis",
        "La section n'est exigée que d'un plan neuf (`--neuf`)",
        "`--neuf` ne dit rien de plus que la nouveauté du plan : il est distinct de `--sans-lieux`",
        "sans `--neuf`, retirer la section entière d'un plan qui la portait n'est pas vu",
        "[--sans-lieux] [--neuf] [--cloture MOT]...",
        "--neuf exige « Effets cherchés » : un plan neuf",
        "valeur vide de --cloture",
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
    resume = "plan.md : 0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues"
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


EFFETS_ABSENTE = "section « Effets cherchés » absente (titre de niveau 2)"
EFFETS_REFUSE = f"Effets cherchés, ligne 2 : {p.FORMES[p.EFFETS]}"


def test_effets_section(racine):
    """« Effets cherchés » se lit comme « Outils et cas limites » : trois morceaux non vides,
    « Aucun. » seul, une seule section ; le résumé compte ses lignes."""
    lignes, refus = verifier(plan_neuf(), racine, neuf=True)
    assert not refus, lignes
    assert lignes[-1] == "0 mécanismes vérifiés, 0 non vérifiés, 0 outils, 0 effets, 1 revues"
    lignes, refus = verifier(plan_neuf(effets="- a — b — c"), racine)
    assert not refus, lignes
    assert lignes[-1].endswith("0 outils, 1 effets, 1 revues"), lignes
    for mauvais in ("- — b — c", "- a — b"):
        lignes, refus = verifier(plan(effets=mauvais), racine)
        assert refus
        assert EFFETS_REFUSE in lignes, (mauvais, lignes)
    assert p.FORMES[p.EFFETS] == (
        "forme attendue : - <décision> — <où elle arrive> — <comment c'est vérifié>, "
        "ou « Aucun. » seul"
    )
    double = plan(effets="- a — b — c").replace("---\n", "## Effets cherchés\n\nAucun.\n\n---\n")
    lignes, refus = verifier(double, racine)
    assert refus
    assert "section « Effets cherchés » en double" in lignes, lignes


def test_effets_neuf(racine):
    """Avec `--neuf`, « Effets cherchés » absente refuse, lieux ouverts comme par `--sans-lieux` ;
    sans lui, son absence ne refuse pas, mais mal formée elle refuse."""
    for lieux in (True, False):
        lignes, refus = verifier(plan(), racine, lieux=lieux, neuf=True)
        assert refus, lieux
        assert EFFETS_ABSENTE in lignes, lignes
    lignes, refus = verifier(plan(), racine)
    assert not refus, lignes
    assert EFFETS_ABSENTE not in lignes
    lignes, refus = verifier(plan(effets="Une phrase."), racine)
    assert refus
    assert EFFETS_REFUSE in lignes, lignes


def test_effets_resume_sans_lieux(racine):
    lignes, refus = verifier(plan_neuf(), racine, lieux=False, neuf=True)
    assert not refus, lignes
    assert lignes[-1] == "0 mécanismes, lieux non ouverts, 0 outils, 0 effets, 1 revues"


def test_main_neuf(racine, lancer):
    """`--neuf` : 1 sur un plan sans « Effets cherchés », 0 sans l'option ; la valeur vide de
    `--cloture` est une erreur d'usage."""
    code, sortie = lancer(plan(), "--racine", str(racine), "--neuf")
    assert code == 1, sortie
    assert EFFETS_ABSENTE in sortie
    code, sortie = lancer(plan(), "--racine", str(racine))
    assert code == 0, sortie
    code, sortie = lancer(plan_neuf(), "--racine", str(racine), "--neuf")
    assert code == 0, sortie
    code, sortie = lancer(plan(), "--racine", str(racine), "--cloture", "  ")
    assert code == 64, sortie
    assert "--cloture MOT attendu" in sortie
    code, sortie = lancer(plan(), "--racine", str(racine), "--cloture", "cadrage")
    assert code == 0, sortie


# --- la clôture d'un plan neuf, le plan de tranche et le plan hors lot ---

TOUS_LES_GESTES = (
    "le plan supprimé, CLAUDE.md ou un ADR, le README, les leçons du lot, la fermeture de l'issue, "
    "la tête relue"
)


def non_nommes(noms, unite="Tâche 2"):
    """Le refus d'une clôture qui ne nomme pas `noms`."""
    return f"clôture ({unite}) : gestes non nommés : {noms}"


def test_cloture_conforme(racine):
    """Une clôture qui nomme les six gestes passe ; il en manque un, puis deux : le refus les nomme
    dans l'ordre de `GESTES`, jamais le texte du plan."""
    assert list(p.GESTES) == [
        "le plan supprimé",
        "CLAUDE.md ou un ADR",
        "le README",
        "les leçons du lot",
        "la fermeture de l'issue",
        "la tête relue",
    ]
    assert list(PASSAGES) == list(p.GESTES)
    assert p.AUCUNE_CLOTURE == (
        "aucune unité de clôture : un titre `### Tâche N : … clôture`, ou `### Tranche N · … "
        "clôture` dans un plan maître ; un plan de tranche porte la ligne `Plan maître :`, un plan "
        "hors lot la ligne `Hors lot :`"
    )
    for lieux in (True, False):
        lignes, refus = verifier(plan_neuf(), racine, lieux=lieux, neuf=True)
        assert not refus, lignes
    sans_readme = CLOTURE_CONFORME.replace("README relu ; ", "")
    lignes, refus = verifier(plan_neuf(taches=cloture(sans_readme)), racine, neuf=True)
    assert refus
    assert non_nommes("le README") in lignes, lignes
    sans_deux = sans_readme.replace("les leçons du lot au registre ; ", "")
    lignes, refus = verifier(plan_neuf(taches=cloture(sans_deux)), racine, neuf=True)
    assert refus
    assert non_nommes("le README, les leçons du lot") in lignes, lignes
    # la clôture se vérifie après les sections, avant le double des numéros et le résumé
    taches = (*cloture(sans_readme), "### Tâche 2 : y")
    lignes, refus = verifier(plan_neuf(outils="Une phrase.", taches=taches), racine, neuf=True)
    assert lignes[-4:-1] == [OUTIL_REFUSE, non_nommes("le README"), "Tâche 2 en double"], lignes


def test_cloture_expressions(racine):
    """Chaque geste se reconnaît à son expression, cherchée dans le texte replié de l'unité : ses
    tournures admises passent, et un voisin refuse en le nommant. Pour chaque borne `(?<!\\w)` et
    `(?!\\w)`, un cas que seule elle refuse."""
    admis = {
        "le plan supprimé": ("plan supprimé", "Suppression du plan"),
        "CLAUDE.md ou un ADR": ("un ADR", "ADR"),
        "les leçons du lot": ("leçons", "les constats au registre"),
        "la fermeture de l'issue": (
            "Fixes #1",
            "ferme l'issue",
            # l'apostrophe typographique dans un code en ligne : `_normaliser` l'y laisserait
            "`ferme l\u2019issue`",
        ),
        "la tête relue": ("Tête  relue", "Te\u0302te relue", "`Tête\u00a0relue`"),
    }
    for nom, tournures in admis.items():
        for tournure in tournures:
            texte = CLOTURE_CONFORME.replace(PASSAGES[nom], tournure)
            assert texte != CLOTURE_CONFORME, tournure
            lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
            assert not refus, (nom, tournure, lignes)
    refuses = {
        # le voisin, puis un cas par borne
        "le plan supprimé": ("retire le plan", "nonsupprimé le plan"),
        "CLAUDE.md ou un ADR": (
            "`CLAUDE-md` à jour",
            "monclaude.md",
            "CLAUDE.mdx",
            "cadr",
            "adrénaline",
            "le cadrage",
        ),
        "le README": ("LISEZMOI relu", "xreadme", "readmes"),
        "les leçons du lot": ("le registre", "surleçon", "leçonnaire"),
        "la fermeture de l'issue": (
            "« Closed #1 »",
            "encloses",
            "closeset",
            "prefixes",
            "fixesx",
            "referme l'issue",
            "ferme l'issues",
            "se ferme",
        ),
        "la tête relue": ("tête lue", "l'entête relue", "tête relues"),
    }
    for nom, voisins in refuses.items():
        for voisin in voisins:
            texte = CLOTURE_CONFORME.replace(PASSAGES[nom], voisin)
            lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
            assert refus, (nom, voisin, lignes)
            assert non_nommes(nom) in lignes, (nom, voisin, lignes)


def test_cloture_mots_coupes_en_fin_de_ligne(racine):
    """Une clôture en prose coupée à 100 colonnes, sous une puce indentée : « ferme l'issue »,
    « Tête relue » et un mot de `--cloture` enjambent une fin de ligne, et passent."""
    texte = (
        "- [ ] **Étape 1 : la PR de clôture.** Elle supprime le plan, reporte dans `CLAUDE.md` ce\n"
        "  qui doit survivre, relit le README et porte au registre les leçons du lot ; elle ferme\n"
        "  l'issue, nomme la tête\n"
        "  relue, et recueille les « À\n"
        "  relire »."
    )
    taches = cloture(texte)
    lignes, refus = verifier(plan_neuf(taches=taches), racine, neuf=True, cloture=("à relire",))
    assert not refus, lignes


def test_cloture_commentaires_et_blocs(racine):
    """Un geste nommé dans un commentaire ne compte pas ; dans un bloc de code, il compte, sauf
    dans un bloc pris dans un commentaire retiré. L'unité court jusqu'au titre suivant de niveau 1
    à 3, lu hors des blocs de code et des blocs de commentaire : un `# commentaire` dans un bloc,
    un `### …` dans un bloc de commentaire ou un titre de niveau 4 ne la coupe pas ; un titre de
    niveau 3, 2 ou 1 après elle la coupe. Un `<!--` jamais fermé dans l'unité refuse."""
    sans_readme = CLOTURE_CONFORME.replace("README relu ; ", "")
    for texte in (
        CLOTURE_CONFORME.replace("README relu", "<!-- README relu -->"),
        CLOTURE_CONFORME.replace("README relu", "<!--\nREADME relu\n-->"),
        sans_readme + "\n\n<!--\n```sh\ngit add README.md\n```\n-->",
    ):
        lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
        assert refus, (texte, lignes)
        assert non_nommes("le README") in lignes, (texte, lignes)
    for texte in (
        sans_readme + "\n\n```sh\ngit add README.md\n```",
        sans_readme + "\n\n```sh\n# un commentaire\n```\n\nREADME relu.",
        sans_readme + "\n\n#### Le dernier geste\n\nREADME relu.",
        # un `<!--` dans un bloc de code, ou dans un code en ligne, ne retire rien
        sans_readme + "\n\n```html\n<!-- début\n```\n\nREADME relu.",
        sans_readme + " Un `<!--` en code en ligne. README relu.",
        sans_readme + " <!-- note --> README relu.",
        # un titre de niveau 3 dans un bloc de commentaire ne coupe pas l'unité (revue finale du
        # lot 17)
        sans_readme + "\n\n<!--\n### Une note\n-->\n\nREADME relu.",
    ):
        lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
        assert not refus, (texte, lignes)
    # un titre de niveau 3, 2 ou 1 après l'unité la coupe : le geste nommé après lui ne compte pas
    # (revue finale du lot 17)
    for suite in ("### Tâche 3 : x", "## Annexe", "# Annexe"):
        taches = (*cloture(sans_readme), f"{suite}\n\nREADME relu.")
        lignes, refus = verifier(plan_neuf(taches=taches), racine, neuf=True)
        assert refus, (suite, lignes)
        assert non_nommes("le README") in lignes, (suite, lignes)
    ouvert = f"clôture (Tâche 2) : {p.COMMENTAIRE_OUVERT}"
    assert ouvert == "clôture (Tâche 2) : commentaire HTML jamais fermé, qui cache la suite"
    for texte, manquants in (
        (CLOTURE_CONFORME + "\n\n<!-- une note", None),
        (CLOTURE_CONFORME + " texte <!-- une note", None),
        # le commentaire cache la suite : le README, nommé après lui, ne compte pas
        (sans_readme + "\n\n<!-- une note\n\nREADME relu.", "le README"),
    ):
        lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
        assert refus, (texte, lignes)
        assert ouvert in lignes, (texte, lignes)
        nommes = [ligne for ligne in lignes if "gestes non nommés" in ligne]
        assert nommes == ([] if manquants is None else [non_nommes(manquants)]), (texte, lignes)


def test_cloture_souligne_colle_au_mot(racine):
    """Un mot se cherche sans lettre, chiffre ni `_` à côté de lui : `\\w` compte `_`. L'emphase
    par soulignés, `_README_` ou `__Tête relue__`, cache le geste, et le refus le nomme ; le gras
    par astérisques, `**Tête relue**`, le laisse lire. De même pour un mot de `--cloture` (revue
    finale du lot 17)."""
    for nom, tournure in (("le README", "_README_ relu"), ("la tête relue", "__Tête relue__")):
        texte = CLOTURE_CONFORME.replace(PASSAGES[nom], tournure)
        assert texte != CLOTURE_CONFORME, tournure
        lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
        assert refus, (tournure, lignes)
        assert non_nommes(nom) in lignes, (tournure, lignes)
    for tournure in ("**Tête relue**", "*Tête relue*"):
        texte = CLOTURE_CONFORME.replace(PASSAGES["la tête relue"], tournure)
        lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
        assert not refus, (tournure, lignes)
    avec = plan_neuf(taches=cloture(CLOTURE_CONFORME + " Le _cadrage_ amendé."))
    lignes, refus = verifier(avec, racine, neuf=True, cloture=("cadrage",))
    assert non_nommes("« cadrage »") in lignes, lignes
    avec = plan_neuf(taches=cloture(CLOTURE_CONFORME + " Le **cadrage** amendé."))
    lignes, refus = verifier(avec, racine, neuf=True, cloture=("cadrage",))
    assert not refus, lignes


def test_ordre_des_sections_dans_les_refus(racine):
    """Les refus des sections suivent l'ordre des sections, mécanismes, outils, effets, revues,
    quel que soit l'ordre du plan : le relevé compare ces lignes (revue finale du lot 17)."""
    attendus = [MECA_REFUSE, OUTIL_REFUSE, EFFETS_REFUSE, REVUES_REFUSE]
    mal = "Une phrase."
    texte = plan(meca=mal, outils=mal, effets=mal, revues=mal)
    lignes, refus = verifier(texte, racine)
    assert refus
    assert [ligne for ligne in lignes if ligne in attendus] == attendus, lignes
    # les sections écrites dans un autre ordre : les refus gardent le leur
    a_l_envers = (
        "# Un plan\n\n"
        f"## Revues\n\n{mal}\n\n## Effets cherchés\n\n{mal}\n\n"
        f"## Outils et cas limites\n\n{mal}\n\n## Mécanismes annoncés\n\n{mal}\n\n"
        "---\n\n### Tâche 1 : x\n\n### Tâche 2 : la clôture\n\n" + CLOTURE_CONFORME + "\n"
    )
    lignes, refus = verifier(a_l_envers, racine)
    assert refus
    assert [ligne for ligne in lignes if ligne in attendus] == attendus, lignes


def test_cloture_mots_du_depot(racine, lancer):
    """`--cloture` ajoute des mots, repliés comme le texte : le refus les nomme entre guillemets,
    après les gestes, chaque caractère de contrôle remplacé ; une valeur vide rend 64 ; `#133` se
    trouve après une espace."""
    avec = CLOTURE_CONFORME + " Le cadrage amendé ; les « À relire » recueillis."
    mots = ("cadrage", "à relire")
    lignes, refus = verifier(plan_neuf(taches=cloture(avec)), racine, neuf=True, cloture=mots)
    assert not refus, lignes
    lignes, refus = verifier(plan_neuf(), racine, neuf=True, cloture=mots)
    assert refus
    assert non_nommes("« cadrage », « à relire »") in lignes, lignes
    sans_readme = CLOTURE_CONFORME.replace("README relu ; ", "")
    texte = plan_neuf(taches=cloture(sans_readme))
    lignes, refus = verifier(texte, racine, neuf=True, cloture=mots)
    assert non_nommes("le README, « cadrage », « à relire »") in lignes, lignes
    lignes, refus = verifier(plan_neuf(), racine, neuf=True, cloture=("a\x07b",))
    assert non_nommes("« a?b »") in lignes, lignes
    options = ("--racine", str(racine), "--neuf")
    # « À relire » de l'option contre « À relire » du texte, sans égard à la casse ni aux blancs
    for mot in ("À relire", "À  relire", "à relire"):
        code, sortie = lancer(
            plan_neuf(taches=cloture(avec)), *options, "--cloture", "cadrage", "--cloture", mot
        )
        assert code == 0, (mot, sortie)
    code, sortie = lancer(plan_neuf(), *options, "--cloture", "À relire")
    assert code == 1, sortie
    assert non_nommes("« à relire »") in sortie, sortie
    for vide in ("", "\u00a0"):
        code, sortie = lancer(plan_neuf(), *options, "--cloture", vide)
        assert code == 64, sortie
        assert "--cloture MOT attendu" in sortie, sortie
    prochain = plan_neuf(taches=cloture(CLOTURE_CONFORME + " Prochain cite #133."))
    code, sortie = lancer(prochain, *options, "--cloture", "#133")
    assert code == 0, sortie
    code, sortie = lancer(plan_neuf(), *options, "--cloture", "#133")
    assert code == 1, sortie
    assert non_nommes("« #133 »") in sortie, sortie


def test_cloture_exigee_quand_la_section_est_presente(racine):
    """Un plan neuf qui porte « Effets cherchés », vérifié plus tard sans `--neuf` comme un plan
    modifié, reste tenu à sa clôture : le retrait d'un geste refuse. Un plan en cours, avec la même
    clôture, passe."""
    sans_readme = cloture(CLOTURE_CONFORME.replace("README relu ; ", ""))
    for lieux in (True, False):
        lignes, refus = verifier(plan_neuf(taches=sans_readme), racine, lieux=lieux)
        assert refus, (lieux, lignes)
        assert non_nommes("le README") in lignes, lignes
        lignes, refus = verifier(plan(taches=sans_readme), racine, lieux=lieux)
        assert not refus, (lieux, lignes)
    lignes, refus = verifier(plan_neuf(), racine)
    assert not refus, lignes


def test_cloture_absente(racine):
    """Sans unité de clôture, un plan neuf refuse, par `AUCUNE_CLOTURE` ; un plan en cours
    passe."""
    une_tache = ("### Tâche 1 : x",)
    for lieux in (True, False):
        lignes, refus = verifier(plan(taches=une_tache), racine, lieux=lieux, neuf=True)
        assert refus
        assert p.AUCUNE_CLOTURE in lignes, lignes
        lignes, refus = verifier(plan(taches=une_tache), racine, lieux=lieux)
        assert not refus, lignes
        lignes, refus = verifier(plan_neuf(taches=une_tache), racine, lieux=lieux)
        assert refus
        assert p.AUCUNE_CLOTURE in lignes, lignes


def test_cloture_premier_titre(racine):
    """L'unité de clôture est la première dont le titre dit « clôture » : un titre qui le dit avant
    la vraie clôture en devient l'unité, et le refus la nomme."""
    taches = (
        "### Tâche 1 : x",
        "### Tâche 2 : la porte de clôture",
        "### Tâche 3 : la clôture\n\n" + CLOTURE_CONFORME,
    )
    lignes, refus = verifier(plan_neuf(taches=taches), racine, neuf=True)
    assert refus
    assert non_nommes(TOUS_LES_GESTES) in lignes, lignes
    assert not [ligne for ligne in lignes if "Tâche 3" in ligne], lignes


MAITRE_CONFORME = ("### Tranche 1 · x", "### Tranche 2 · y", "### Tranche 3 · la clôture")
REVUE_DE_TRANCHE = "- relecture : Tranche 1"


def plan_maitre(texte=CLOTURE_CONFORME, **kw):
    """Un plan maître neuf, dont la Tranche 3 est la clôture qui porte `texte`."""
    titres = (*MAITRE_CONFORME[:2], f"{MAITRE_CONFORME[2]}\n\n{texte}")
    return plan_neuf(revues=REVUE_DE_TRANCHE, taches=titres, **kw)


def test_cloture_plan_maitre(racine):
    """Un plan maître est tenu à sa clôture comme un plan à tâches : sa tranche de clôture nomme les
    gestes, et le refus nomme la tranche."""
    lignes, refus = verifier(plan_maitre(), racine, neuf=True)
    assert not refus, lignes
    lignes, refus = verifier(plan_maitre("Une étape."), racine, neuf=True)
    assert refus
    assert non_nommes(TOUS_LES_GESTES, "Tranche 3") in lignes, lignes


def plan_de_tranche(entete, **kw):
    """Un plan neuf qui porte `entete` et n'a qu'une tâche, sans unité de clôture."""
    kw.setdefault("taches", ("### Tâche 1 : x",))
    return plan_neuf(entete=entete, **kw)


def test_plan_de_tranche(racine, monkeypatch):
    """La ligne `Plan maître :` dispense un plan de tranche d'unité de clôture et de gestes. Sa
    forme se vérifie sans ouvrir de fichier ; lieux ouverts, sa cible est un plan maître sous la
    racine. Elle ne se lit qu'avant la première unité, hors des blocs de code et des
    commentaires."""
    plans = racine / ".claude/plans"
    plans.mkdir(parents=True)
    (plans / "m.md").write_text(plan_maitre(), encoding="utf-8")
    (plans / "u.md").write_bytes(plan_maitre().encode("utf-16"))
    (plans / "t.md").write_text(plan_neuf(), encoding="utf-8")
    (plans / "d.md").mkdir()
    ligne = "Plan maître : `.claude/plans/m.md`"
    for entete in (
        ligne,
        "**Plan maître :** `.claude/plans/m.md`",
        "**Plan maître** : `.claude/plans/m.md`",
        "Plan maître: `.claude/plans/m.md`",
        "   PLAN MAÎTRE : `.claude/plans/m.md`  ",
        "Plan maître : `.claude/plans/u.md`",
        "\n### Les écarts\n\n" + ligne,
    ):
        for lieux in (True, False):
            lignes, refus = verifier(plan_de_tranche(entete), racine, lieux=lieux, neuf=True)
            assert not refus, (entete, lieux, lignes)
    for chemin, attendu in (
        (".claude/plans/absent.md", "plan maître absent : .claude/plans/absent.md"),
        (".claude/plans/d.md", "plan maître absent : .claude/plans/d.md"),
        (".claude/plans/t.md", ".claude/plans/t.md n'est pas un plan maître"),
    ):
        lignes, refus = verifier(plan_de_tranche(f"Plan maître : `{chemin}`"), racine, neuf=True)
        assert refus, (chemin, lignes)
        assert attendu in lignes, (chemin, lignes)
        # sans les lieux, la cible n'est pas lue
        lignes, refus = verifier(
            plan_de_tranche(f"Plan maître : `{chemin}`"), racine, lieux=False, neuf=True
        )
        assert not refus, (chemin, lignes)
    b = chr(92)
    raisons = {
        "C:/x.md": "deux-points dans le chemin",
        "/x.md": "chemin absolu",
        f".claude{b}plans{b}m.md": "barre oblique inverse",
        ".claude/plans/../m.md": "..",
        "docs/m.md": "hors de .claude/plans/",
        ".claude/plans/m.txt": "sans .md",
    }
    for chemin, raison in raisons.items():
        assert p._chemin_du_plan_maitre(chemin) == raison, chemin
    assert p._chemin_du_plan_maitre(".claude/plans/m.md") is None
    assert p._chemin_du_plan_maitre(".claude/plans/x/m.md") is None
    vus = espionner(monkeypatch)
    for chemin, raison in raisons.items():
        for lieux in (True, False):
            vus.clear()
            texte = plan_de_tranche(f"Plan maître : `{chemin}`")
            lignes, refus = verifier(texte, racine, lieux=lieux, neuf=True)
            assert refus, (chemin, lignes)
            assert f"chemin du plan maître refusé ({raison})" in lignes, (chemin, lignes)
            assert vus == [], (chemin, vus)
    # sans les lieux, rien n'est lu, et le double refuse toujours
    absent = "Plan maître : `.claude/plans/absent.md`"
    vus.clear()
    lignes, refus = verifier(plan_de_tranche(absent), racine, lieux=False, neuf=True)
    assert not refus and vus == [], (lignes, vus)
    for lieux in (True, False):
        texte = plan_de_tranche(f"{ligne}\n{absent}")
        lignes, refus = verifier(texte, racine, lieux=lieux, neuf=True)
        assert refus
        assert "plan maître en double" in lignes, lignes
    monkeypatch.undo()
    for entete in ("Plan maître :", "Plan maître : .claude/plans/m.md", f"{ligne} et la suite"):
        lignes, refus = verifier(plan_de_tranche(entete), racine, neuf=True)
        assert refus, (entete, lignes)
        assert "ligne « Plan maître : » sans chemin" in lignes, (entete, lignes)
    lignes, refus = verifier(plan_maitre(entete=ligne), racine, neuf=True)
    assert refus
    assert "un plan maître ne nomme pas de plan maître" in lignes, lignes
    # la ligne ne dispense pas un plan maître de sa clôture
    lignes, refus = verifier(plan_maitre("Une étape.", entete=ligne), racine, neuf=True)
    assert "un plan maître ne nomme pas de plan maître" in lignes, lignes
    assert non_nommes(TOUS_LES_GESTES, "Tranche 3") in lignes, lignes
    # après la première unité, dans un bloc de code ou dans un commentaire, la ligne ne compte pas
    for texte in (
        plan_neuf(taches=(f"### Tâche 1 : x\n\n{ligne}",)),
        plan_de_tranche(f"```\n{ligne}\n```"),
        plan_de_tranche(f"<!-- {ligne} -->"),
    ):
        lignes, refus = verifier(texte, racine, neuf=True)
        assert refus, lignes
        assert p.AUCUNE_CLOTURE in lignes, lignes
    # sans `--neuf` ni « Effets cherchés », aucune de ces règles ne s'applique
    for entete in ("Plan maître : `C:/x.md`", f"{ligne}\n{ligne}", "Plan maître :"):
        lignes, refus = verifier(plan(entete=entete, taches=("### Tâche 1 : x",)), racine)
        assert not refus, (entete, lignes)


def test_plan_hors_lot(racine):
    """La ligne `Hors lot :` dispense un plan d'unité de clôture et de gestes ; sa raison vide, son
    double, sa présence dans un plan maître ou à côté de `Plan maître :` refusent."""
    for entete in ("Hors lot : une hypothèse", "**Hors lot :** un correctif", "Hors lot: un essai"):
        for lieux in (True, False):
            lignes, refus = verifier(plan_de_tranche(entete), racine, lieux=lieux, neuf=True)
            assert not refus, (entete, lignes)
    ligne = "Hors lot : une hypothèse"
    for texte, attendu in (
        (plan_de_tranche("Hors lot :"), "ligne « Hors lot : » sans raison"),
        (plan_de_tranche("Hors lot :   "), "ligne « Hors lot : » sans raison"),
        (plan_de_tranche(f"{ligne}\nHors lot : un essai"), "ligne « Hors lot : » en double"),
        (plan_maitre(entete=ligne), "un plan maître n'est pas hors lot"),
        (
            plan_de_tranche(f"{ligne}\nPlan maître : `.claude/plans/m.md`"),
            "un plan ne porte pas à la fois « Plan maître : » et « Hors lot : »",
        ),
    ):
        for lieux in (True, False):
            lignes, refus = verifier(texte, racine, lieux=lieux, neuf=True)
            assert refus, (attendu, lignes)
            assert attendu in lignes, (attendu, lignes)
    # la ligne ne dispense pas un plan maître de sa clôture
    lignes, refus = verifier(plan_maitre("Une étape.", entete=ligne), racine, neuf=True)
    assert "un plan maître n'est pas hors lot" in lignes, lignes
    assert non_nommes(TOUS_LES_GESTES, "Tranche 3") in lignes, lignes
    lignes, refus = verifier(plan(entete="Hors lot :", taches=("### Tâche 1 : x",)), racine)
    assert not refus, lignes


ANGLAIS = SUPERPOWERS.replace("## Revues", "## Effets cherchés\n\nAucun.\n\n## Revues").split(
    "### Task 2: closure"
)[0] + (
    "### Task 2: closure\n\n"
    "- [ ] **Step 1: Delete the plan**\n"
    "- [ ] **Step 2: Add the lessons to the registry**\n"
    "- [ ] **Step 3: Close the issue, and name the reviewed head**\n"
)


def test_cloture_plan_en_anglais(racine, lancer):
    """Un plan neuf au gabarit de *superpowers*, dont la clôture dit ses gestes en anglais : il
    refuse en nommant les six gestes, sans planter (Review Focus 1)."""
    code, sortie = lancer(ANGLAIS, "--racine", str(racine), "--neuf")
    assert code == 1, sortie
    assert non_nommes(TOUS_LES_GESTES) in sortie, sortie
    assert "Traceback" not in sortie, sortie


# Des plans de banc de la forme des huit plans en cours (relevés le 13/11), et les lignes que
# leur donnait `plan.py` en `v0.11.0`, par `--sans-lieux`, hors du résumé.
EN_COURS = {
    "un plan à tâches, sans « Effets cherchés » ni gestes": (
        plan(
            taches=cloture(
                "Elle retire ce plan ; #3 se ferme ; le registre reçoit les constats du lot."
            )
        ),
        [],
    ),
    "un plan maître sans ses sections": (
        "# Un plan maître\n\n### Tranche 1 · x\n\n### Tranche 2 · la clôture\n\n- [ ] une étape\n",
        [
            "section « Mécanismes annoncés » absente (titre de niveau 2)",
            "section « Outils et cas limites » absente (titre de niveau 2)",
            "section « Revues » absente (titre de niveau 2)",
        ],
    ),
    "un plan de tranche à ligne « Spécification : »": (
        plan(
            entete="**Spécification :** le plan maître `.claude/plans/lot1.md`, tranche 1.\n",
            taches=("### Tâche 1 : x", "### Tâche 2 : la clôture de la Tranche 1"),
        ),
        [],
    ),
    "un plan sans unité de clôture": (
        plan(taches=("### Tâche 1 : x", "### Ensuite")),
        [],
    ),
}


def test_plans_en_cours(racine):
    """Les plans en cours, sans « Effets cherchés », vérifiés sans `--neuf` comme la CI vérifie un
    plan modifié : les mêmes lignes qu'en `v0.11.0`, hors du résumé, qui gagne le compte des
    effets."""
    for nom, (texte, attendues) in EN_COURS.items():
        lignes, refus = verifier(texte, racine, lieux=False)
        assert lignes[:-1] == attendues, (nom, lignes)
        assert refus == bool(attendues), (nom, lignes)


def test_gestes_de_la_methode():
    """La liste des gestes du paragraphe « La clôture d'un plan » de `methode.md` est celle de
    `GESTES`, dans l'ordre ; le refus sans unité de clôture y est cité tel quel."""
    texte = (RACINE / "template/docs/modele/methode.md").read_text(encoding="utf-8")
    suite = texte.split("**La clôture d'un plan.**", 1)[1]
    liste = suite.split("\n\n- ", 1)[1].split("\n\n", 1)[0]
    noms = [element.split(" : ", 1)[0].replace("`", "") for element in liste.split("\n- ")]
    assert noms == list(p.GESTES), noms
    assert p.AUCUNE_CLOTURE in " ".join(texte.split())
    assert f"« {p.MAITRE_SANS_CHEMIN} »" in " ".join(texte.split())


def test_replier():
    """Le texte de la clôture et les mots de `--cloture` se replient sur tout leur texte, code en
    ligne compris : NFC, apostrophes droites, espaces ordinaires, sans égard à la casse."""
    brut = "Te\u0302te\u00a0RELUE, `l\u2019Issue\u202f`"
    assert p._replier(brut) == "tête relue, `l'issue `"
    assert p._mot("à relire").search("les « à\n  relire »")
    assert not p._mot("à relire").search("les « à relirex »")
    assert not p._mot("cadrage").search("encadrage")
    assert p._mot("#133").search("cite #133.")


def test_docstring_dit_la_cloture():
    """Le module dit la clôture, ses gestes, son texte, `--cloture`, et les deux lignes déclarées,
    chaque phrase neuve par un fragment ; `verifier`, `_texte_de_cloture`,
    `_verifier_declarations` et `_dit_cloture` disent ce qu'ils font."""
    doc = " ".join(p.__doc__.split())
    for fragment in (
        # la clôture
        (
            "La clôture. Un plan neuf, ou qui porte « Effets cherchés », a une unité de clôture, "
            "celle que lit « Revues » : un titre qui dit « clôture » avant la vraie clôture en "
            "devient l'unité."
        ),
        (
            "Elle nomme six gestes, le plan supprimé, `CLAUDE.md` ou un ADR, le README, les leçons "
            "du lot, la fermeture de l'issue, la tête relue (`GESTES`), et chaque mot de "
            "`--cloture`, à répéter."
        ),
        (
            "Son texte va de son titre à la ligne qui précède le titre suivant de niveau 1 à 3, lu "
            "comme dans `sections()`, ou à la fin du plan."
        ),
        (
            "Il se prend sur les lignes d'origine, les commentaires retirés, les blocs de code "
            "gardés, sauf un bloc pris dans un commentaire retiré, puis se lit en NFC, apostrophes "
            "droites, espaces ordinaires, sans égard à la casse, code compris."
        ),
        # `\w` compte `_` (revue finale du lot 17)
        (
            "Un mot se cherche sans lettre, chiffre ni `_` juste avant ni juste après lui (`\\w`, "
            "qui compte `_` : l'emphase `_README_` cache le mot) ; `supprim` et `suppress` n'ont "
            "cette limite qu'avant eux ; entre deux mots, tout blanc compte, retour à la ligne "
            "compris."
        ),
        "Un `<!--` jamais fermé dans l'unité refuse, et cache la suite.",
        (
            "Le refus nomme l'unité et les gestes qui manquent, dans l'ordre de `GESTES` puis des "
            "options, un mot de `--cloture` entre guillemets."
        ),
        (
            "Sans unité de clôture, un tel plan refuse (`AUCUNE_CLOTURE`), sauf un plan de tranche "
            "ou un plan hors lot, qui n'est tenu ni à l'unité ni aux gestes."
        ),
        (
            "La porte voit un geste que la clôture ne nomme pas, jamais un geste nommé mais fait à "
            "moitié."
        ),
        # les lignes déclarées
        (
            "Les lignes déclarées. Avant la première unité, hors des blocs de code et des "
            "commentaires, jusqu'à trois espaces en tête, le gras admis autour du nom, deux-points "
            "compris ou non : `` Plan maître : `.claude/plans/<fichier>.md` `` dit un plan de "
            "tranche, `Hors lot : <raison>` un plan hors lot."
        ),
        (
            "Le chemin, un code en ligne seul après les deux-points, refuse avant toute lecture "
            "pour les raisons d'un lieu, puis hors de `.claude/plans/` ou sans `.md` ; lieux "
            "ouverts, il nomme un plan maître sous la racine, lu comme un plan."
        ),
        (
            "Une raison vide, deux lignes de la même sorte, les deux sortes ensemble, ou l'une "
            "d'elles dans un plan maître refusent."
        ),
        "Sans `--neuf` ni « Effets cherchés », ni la clôture ni ces lignes ne se vérifient.",
        # la sortie et l'usage
        (
            "les titres des sections, les noms des gestes, les mots de `--cloture` et les formes "
            "fixes des refus"
        ),
        (
            "--neuf exige « Effets cherchés » : un plan neuf, tenu aussi à sa clôture. --cloture "
            "MOT ajoute un mot que la clôture doit nommer."
        ),
    ):
        assert fragment in doc, fragment
    verifier_doc = " ".join(p.verifier.__doc__.split())
    for fragment in (
        "Les sections d'un plan, puis sa clôture : (lignes, refus).",
        (
            "Avec `lieux=False`, la forme de chaque lieu se vérifie par `lieu()`, sans ouvrir de "
            "fichier, et la cible d'une ligne `Plan maître :` n'est pas lue."
        ),
        (
            "Avec `neuf`, ou la section présente, l'unité de clôture nomme les gestes et chaque "
            "mot de `cloture`, sauf dans un plan de tranche ou un plan hors lot."
        ),
        (
            "`cloture` : des mots déjà repliés par `_replier`, sans blanc autour, comme `main` les "
            "passe."
        ),
    ):
        assert fragment in verifier_doc, fragment
    assert "sans effet encore" not in verifier_doc
    assert "sans lettre ni chiffre" not in doc
    assert "sans lettre, chiffre ni `_` juste avant ni juste après." in " ".join(
        p._mot.__doc__.split()
    )
    for fonction, fragments in (
        (
            p._texte_de_cloture,
            (
                (
                    "Le texte de l'unité de clôture, replié, et le rang dans le plan, la première "
                    "ligne au rang 1, d'un `<!--` jamais fermé qu'elle porte, ou `None` ; `None` "
                    "sans unité de clôture."
                ),
                (
                    "Un `<!--` dans un bloc de code ne retire rien ; un bloc pris dans un "
                    "commentaire retiré ne revient pas."
                ),
                "Un `<!--` jamais fermé, hors du code, cache la suite : le texte s'arrête à lui.",
            ),
        ),
        (
            p._verifier_declarations,
            (
                (
                    "Un plan qui en porte une est dispensé d'unité de clôture et de gestes, sauf "
                    "un plan maître, qui ne peut en porter aucune."
                ),
            ),
        ),
        (
            p._declarations,
            ("le contenu de leur code en ligne, s'il est seul après les deux-points, ou `\"\"`",),
        ),
        (
            p._dit_cloture,
            (
                (
                    "Le titre replié d'une unité dit la clôture : « clôture » ou « closure ». "
                    "`verifier` et `_texte_de_cloture` reconnaissent l'unité de clôture par lui "
                    "seul."
                ),
            ),
        ),
    ):
        texte = " ".join(fonction.__doc__.split())
        for fragment in fragments:
            assert fragment in texte, (fonction.__name__, fragment)


def test_cloture_un_seul_predicat(racine, monkeypatch):
    """`verifier` et `_texte_de_cloture` reconnaissent l'unité de clôture par le même prédicat,
    `_dit_cloture` : changé, il change les deux, et le refus nomme l'unité dont le texte est lu."""
    assert p._dit_cloture("### tâche 2 : la clôture")
    assert p._dit_cloture("### task 2: closure")
    assert not p._dit_cloture("### tâche 2 : la porte")
    taches = (
        "### Tâche 1 : x",
        "### Tâche 2 : la porte",
        "### Tâche 3 : la clôture\n\n" + CLOTURE_CONFORME,
    )
    lignes, refus = verifier(plan_neuf(taches=taches), racine, neuf=True)
    assert not refus, lignes
    monkeypatch.setattr(p, "_dit_cloture", lambda titre: "porte" in titre)
    lignes, refus = verifier(plan_neuf(taches=taches), racine, neuf=True)
    assert refus
    assert non_nommes(TOUS_LES_GESTES) in lignes, lignes


def test_texte_de_cloture_rang_du_commentaire_ouvert():
    """`_texte_de_cloture` rend le rang dans le plan, la première ligne au rang 1, du `<!--` jamais
    fermé de l'unité, un bloc de code avant lui compris dans le compte ; `None` sans lui ; et `None`
    au lieu du couple sans unité de clôture."""
    doc = p._documentation()
    bloc = "```sh\nune commande\n\nune autre\n```"
    for suite in ("\n\n<!-- une note", " texte <!-- une note", f"\n\n{bloc}\n\n<!-- une note"):
        texte = plan_neuf(taches=cloture(CLOTURE_CONFORME + suite))
        lu = p._texte_de_cloture(texte, doc)
        assert lu is not None, suite
        rang = next(i for i, ligne in enumerate(texte.split("\n"), 1) if "<!-- une note" in ligne)
        assert lu[1] == rang, (suite, lu[1], rang)
    for texte in (plan_neuf(), plan_neuf(taches=cloture(CLOTURE_CONFORME + f"\n\n{bloc}"))):
        lu = p._texte_de_cloture(texte, doc)
        assert lu is not None and lu[1] is None, lu
    assert p._texte_de_cloture(plan(taches=("### Tâche 1 : x",)), doc) is None


def test_cloture_lignes_vides_hors_des_blocs(racine):
    """Seules les lignes d'un bloc de code clôturé y tiennent la place d'un jeton : une ligne vide
    hors d'un bloc reste vide, et arrête un code en ligne. Un accent grave seul, puis, après une
    ligne vide, un `<!--` jamais fermé qui ouvre un bloc de commentaire : il refuse, et n'est pas
    pris dans un code en ligne qui franchirait la ligne vide."""
    texte = CLOTURE_CONFORME + "\n\nUn accent ` seul.\n\n<!-- une note\n\nLa suite ` ici."
    lignes, refus = verifier(plan_neuf(taches=cloture(texte)), racine, neuf=True)
    assert refus
    assert f"clôture (Tâche 2) : {p.COMMENTAIRE_OUVERT}" in lignes, lignes


def test_declarations_formes(racine):
    """Les formes d'une ligne déclarée : trois espaces en tête, pas quatre ; « maître » écrit avec
    un « î » décomposé, une espace insécable avant les deux-points, lues comme la forme simple ; le
    chemin seul après les deux-points, un point final ou un texte après lui donnant « sans
    chemin »."""
    plans = racine / ".claude/plans"
    plans.mkdir(parents=True)
    (plans / "m.md").write_text(plan_maitre(), encoding="utf-8")
    chemin = "`.claude/plans/m.md`"
    for entete in (
        f"   Plan maître : {chemin}",
        f"Plan mai\u0302tre : {chemin}",
        f"Plan maître\u00a0: {chemin}",
        f"**Plan maître\u202f:** {chemin}",
        "Hors lot\u00a0: une hypothèse",
        "   Hors lot : une hypothèse",
    ):
        lignes, refus = verifier(plan_de_tranche(entete), racine, neuf=True)
        assert not refus, (entete, lignes)
    for entete in (f"    Plan maître : {chemin}", "    Hors lot : une hypothèse"):
        lignes, refus = verifier(plan_de_tranche(entete), racine, neuf=True)
        assert refus, (entete, lignes)
        assert p.AUCUNE_CLOTURE in lignes, (entete, lignes)
    for entete in (f"Plan maître : {chemin}.", f"Plan maître : {chemin} (la tranche 1)"):
        lignes, refus = verifier(plan_de_tranche(entete), racine, neuf=True)
        assert refus, (entete, lignes)
        assert "ligne « Plan maître : » sans chemin" in lignes, (entete, lignes)
