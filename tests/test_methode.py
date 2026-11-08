"""Les fichiers gérés de la méthode : méthode, ADR hérités, /consigner, modèles."""

import ast
import re

import pytest
import yaml
from conftest import (
    RACINE,
    REGISTRE_ENTETE,
    RENVOI_AU_PLAN,
    REPONSES_SERVEUR,
    REPONSES_SERVEUR_CODE,
    git,
)

TEMPLATE = RACINE / "template"
METHODE = TEMPLATE / "docs/modele/methode.md"
DECISIONS = TEMPLATE / "docs/modele/decisions"

SECTIONS = [
    "## Le cycle d'un lot",
    "## Les outils",
    "## Les worktrees",
    "## « Fini »",
    "## Les commits",
    "## Les questions groupées",
    "## Les invariants communs",
    "## Les garde-fous",
    "## Les fichiers gérés par le modèle",
    "## Le registre",
    "## Les familles de garde-fous de l'écosystème",
]


def lire(chemin):
    return chemin.read_text(encoding="utf-8")


def test_methode_sections():
    lignes = lire(METHODE).splitlines()
    assert lignes[0] == "# La méthode des projets nés du modèle"
    assert [ligne for ligne in lignes if ligne.startswith("## ")] == SECTIONS


def test_methode_sans_jinja():
    texte = lire(METHODE)
    assert "{{" not in texte
    assert "{%" not in texte


def test_invariants_communs():
    texte = lire(METHODE)
    section = texte.split("## Les invariants communs", 1)[1].split("\n## ", 1)[0]
    assert len(re.findall(r"^\d+\. ", section, flags=re.MULTILINE)) == 5
    # L'invariant 3, au mot près de la spec (§5.2) : il vaut pour tous, Edouard compris, sauf ses
    # gestes 👤 écrits à l'avance (clôture du lot 2).
    assert (
        "3. Personne n'écrit sur le serveur après son amorçage : tout y arrive par git. "
        "Une session y lit, elle n'y écrit jamais." in " ".join(section.split())
    )
    assert (
        "Seule exception : les gestes 👤 écrits à l'avance, qu'Edouard lance lui-même"
        in " ".join(section.split())
    )


def test_fusion_dans_un_autre_depot():
    """Le garde ne lit le mode et les contrôles que du dépôt de la session (LE-22)."""
    texte = " ".join(lire(METHODE).split())
    assert "Le garde ne fusionne que dans le dépôt de la session." in texte
    assert "fusion dans un autre dépôt : contrôles invérifiables ici" in texte
    assert "Un plan qui touche plusieurs dépôts dit, pour chaque PR, qui la fusionne" in texte
    # Tout dépôt nommé est refusé, même celui de la session : on fusionne depuis le clone. GIT_DIR
    # aussi, où gh lit ses remotes (revue de la PR du lot 13, tour 1).
    assert (
        "toute fusion qui nomme un dépôt (`-R`, `--repo`, `GH_REPO`, `GIT_DIR`, une adresse de PR)"
        in texte
    )
    assert "`gh pr merge <n>`, depuis le clone" in texte
    assert "en mode `edouard`, toute fusion est refusée de toute façon" in texte
    # Revue finale du lot 13 (garde-5) : le mode et les contrôles se lisent dans le dossier de la
    # session, jamais dans celui d'un `cd`, et une fusion qui suit un changement de dossier est
    # refusée.
    assert "que du dossier de la session (le `cwd` du hook)" in texte
    assert "que du dépôt du dossier courant" not in texte
    assert "ou qui suit, dans la même commande, un changement de dossier" in texte
    formes = texte.split("ou qui suit, dans la même commande", 1)[1][:300]
    for forme in ("`cd`", "`popd`", "`Set-Location`", "`env -C`", "`Start-Process -WorkingDirectory`"):
        assert forme in formes, forme
    assert "« fusion après un changement de dossier »" in texte
    assert "`gh pr merge <n>`, depuis le clone, sans `cd`" in texte


# Les ADR hérités selon la cible : M-0003 et M-0004 pour `serveur`, M-0005 avec les sauvegardes.
# M-0006 (le code et les données) vaut pour toutes les cibles.
ADR_SOCLE = [
    "M-0001-ecosysteme-des-applications-personnelles.md",
    "M-0002-garde-fous-et-confidentialite.md",
]
ADR_SERVEUR = ["M-0003-contrat-de-l-image.md", "M-0004-chaine-de-livraison.md"]
ADR_SAUVEGARDES = ["M-0005-sauvegardes-et-restauration.md"]
ADR_SEPARATION = ["M-0006-code-et-donnees.md"]
DATES_ADR = {**dict.fromkeys(ADR_SOCLE, "2026-10-16"), "M-0006-code-et-donnees.md": "2026-10-29"}


@pytest.mark.parametrize(
    ("reponses", "attendus"),
    [
        ({}, ADR_SOCLE + ADR_SEPARATION),
        ({**REPONSES_SERVEUR, "sauvegardes": False}, ADR_SOCLE + ADR_SERVEUR + ADR_SEPARATION),
        (REPONSES_SERVEUR, ADR_SOCLE + ADR_SERVEUR + ADR_SAUVEGARDES + ADR_SEPARATION),
    ],
    ids=["aucune", "serveur-sans-sauvegardes", "serveur-avec-sauvegardes"],
)
def test_adr_herites_format(rendre, reponses, attendus):
    adr = sorted((rendre(**reponses) / "docs/modele/decisions").iterdir())
    assert [a.name for a in adr] == attendus
    for chemin in adr:
        lignes = lire(chemin).splitlines()
        assert re.match(rf"^# {chemin.name[:6]} — .+ : .+$", lignes[0]), chemin.name
        date = DATES_ADR.get(chemin.name, "2026-10-18")
        assert f"- **Statut** : accepté le {date}" in lignes, chemin.name
        for titre in ("## Contexte", "## Décision", "## Conséquences", "## Révision"):
            assert titre in lignes, (chemin.name, titre)


def test_m0006_fixe_le_contrat_de_l_app():
    """Les noms du contrat sur lesquels les projets bâtissent avant la chaîne à deux dépôts."""
    texte = " ".join(lire(DECISIONS / "M-0006-code-et-donnees.md").split())
    for attendu in (
        "La réponse `nature` (`code` ou `donnees`) remplace la réponse `visibilite`.",
        "Il est toujours privé et se nomme `<nom>-donnees`.",
        "configuration d'exemple (`exemple/`)",
        "Elle lit sa configuration réelle dans `/config`** et son contenu dans `/contenu`",
        "**Le repli sur l'exemple n'existe pas en prod.**",
        "un champ `configuration`, qui vaut `exemple` ou `montee`",
        "**`VERIFIER_CONFIG <dossier>`**",
        "**`VERIFIER_CONTENU <dossier> [<en service>]`**",
        "elle rend 0 si la configuration est conforme, 2 si elle ne l'est pas, 64 en cas d'erreur d'usage",
        "**Le staging ne monte jamais `/config`.**",
        "Une nature absente ou illisible vaut `code`, la plus stricte.",
        "**L'état déployé est un couple**",
        (
            "- **Amendé** le 2026-10-29, avec le lot 11 : la liste des constats acceptés nomme un "
            "constat par son commit et son chemin, le motif en commentaire ; le numéro d'un motif "
            "change quand la liste privée se réordonne."
        ),
        "nomme chaque constat accepté par son commit et son chemin, le motif en commentaire",
        # la relecture hebdomadaire telle que modele-historique.yml la lance
        (
            "`--exiger-prives --historique --acceptes .github/constats-acceptes.txt`, qui relit "
            "tout l'historique (`git log --all -p`)"
        ),
    ):
        assert attendu in texte, attendu
    assert "`--exiger-prives --public` sur tout l'historique exporté" not in texte


def test_skill_consigner():
    texte = lire(
        TEMPLATE / ".claude/skills/{% if cible != 'donnees' %}consigner{% endif %}/SKILL.md"
    )
    _, entete, corps = texte.split("---", 2)
    meta = yaml.safe_load(entete)
    assert meta["name"] == "consigner"
    assert str(meta["description"]).strip()
    assert meta["argument-hint"] == "[constat en une phrase]"
    assert REGISTRE_ENTETE in corps
    assert "$ARGUMENTS" in corps


def test_formulaire_lot():
    formulaire = yaml.safe_load(
        lire(TEMPLATE / ".github/{% if cible != 'donnees' %}ISSUE_TEMPLATE{% endif %}/lot.yml")
    )
    assert formulaire["name"] == "Lot"
    champs = {c["id"]: c for c in formulaire["body"] if c["type"] == "textarea"}
    assert set(champs) == {"objectif", "criteres", "hors-perimetre"}
    for champ in champs.values():
        assert champ["validations"]["required"] is True


def test_modele_de_pr():
    texte = lire(TEMPLATE / ".github/pull_request_template.md")
    lignes = texte.splitlines()
    for titre in (
        "## Ce que fait cette PR",
        "## Écarts à la spec",
        "## Vérifications",
        "## Reste ouvert",
        "## Registre",
        "## Pour un fix : cause racine et prévention",
    ):
        assert titre in lignes, titre
    # La section des écarts dit « Aucun. » par défaut : sa première ligne qui n'est ni vide ni un
    # commentaire (lot 15, LE-37).
    apres = lignes[lignes.index("## Écarts à la spec") + 1 :]
    (premiere, *_) = [ligne for ligne in apres if ligne.strip() and not ligne.startswith("<!--")]
    assert premiere == "Aucun."


def test_modele_de_pr_a_la_case_du_readme():
    """La case du README relu, une ligne entière, après les trois cases d'aujourd'hui : elle paraît
    sur toute PR, et son libellé dit quand elle compte (lot 14)."""
    lignes = lire(TEMPLATE / ".github/pull_request_template.md").splitlines()
    cases = [ligne for ligne in lignes if ligne.startswith("- [ ] ")]
    assert cases == [
        "- [ ] Tests verts",
        "- [ ] CI verte",
        "- [ ] `CLAUDE.md` et ADR à jour si la PR change une règle ou une décision",
        "- [ ] README relu, à la clôture d'un lot (`docs/modele/documentation.md`)",
    ]


def test_modele_de_pr_ferme_l_issue():
    # GitHub ne ferme l'issue à la fusion que sur un mot-clé anglais (LE-30). Seule la PR de
    # clôture d'un lot le porte ; les autres nomment l'issue sans mot-clé (lot 15, LE-55).
    texte = lire(TEMPLATE / ".github/pull_request_template.md")
    assert "« Closes #n »" in texte
    assert "« Partie de #n »" in texte
    assert "Dans la seule PR de clôture du lot : « Closes #n »" in texte
    assert "Ferme #" not in texte
    # la tête relue : une ligne, pas une case, après les cases de « Vérifications »
    lignes = texte.splitlines()
    (rang,) = [i for i, ligne in enumerate(lignes) if ligne.rstrip() == "Tête relue :"]
    assert rang > max(i for i, ligne in enumerate(lignes) if ligne.startswith("- [ ] "))
    a_plat = " ".join(texte.split())
    assert "le SHA complet de la tête qu'a lue la dernière relecture" in a_plat
    # hors des lots, un correctif qui ferme une issue nomme aussi la tête relue, comme le dit la
    # méthode
    assert (
        "Dans la PR de clôture, ou dans un correctif hors des lots qui ferme une issue par "
        "`Fixes #N` : le SHA complet"
    ) in a_plat


def test_modele_de_pr_renvoie_un_depot_de_donnees_au_registre_du_code():
    texte = " ".join(lire(TEMPLATE / ".github/pull_request_template.md").split())
    assert (
        "ou « aucun constat ». Dans un dépôt de données, le registre est celui du dépôt de code."
        in texte
    )


# --- revue finale du lot 1 ---

CHEMINS_GERES = (
    "`.githooks/`",
    "`scripts/modele/`",
    "`docs/modele/`",
    "`.github/modele/`",
    "`.github/workflows/modele-*.yml`",
    "`.claude/skills/consigner/`",
)


def test_chemins_geres_exclus_des_formateurs():
    texte = lire(METHODE)
    section = texte.split("## Les fichiers gérés par le modèle", 1)[1].split("\n## ", 1)[0]
    assert "exclus des formateurs et des linters" in section
    for chemin in CHEMINS_GERES:
        assert chemin in section, chemin


def test_garde_fous_a_jour():
    section = lire(METHODE).split("## Les garde-fous", 1)[1].split("\n## ", 1)[0]
    for fragment in (
        "`Monitor`",
        "tout outil MCP",
        "sauf la réparation `git config core.hooksPath .githooks`",
        "tout l'historique chaque semaine et à la demande (`modele-historique.yml`)",
        "des messages de commit",
        "| Dependabot |",
        "un envoi direct de cette tête est accepté et marque la PR fusionnée, sans squash",
        "avertit sur ce qui identifie et refuse toujours les secrets",
        "`DEPOT_PRIVE`",
        "`git commit -F <fichier>`",
        "`gh pr create --body-file <fichier>`",
        # revue finale du lot 13 (garde-5) : les enveloppes à option, lues elles aussi
        "`nice -n`",
        "`env -C`",
        "`Start-Process -WorkingDirectory`",
        "la branche courante est illisible",
        # revue de la PR du lot 13 (tour 1) : les blocs et les affectations de PowerShell
        "les blocs PowerShell (`try { … }`, `& { … }`, `% { … }`) et ses affectations (`$x = …`)",
        # lot 14 : la licence et la carte de la racine refusent en CI
        "la licence et la carte de la racine",
    ):
        assert fragment in section, fragment
    (ci,) = [ligne for ligne in section.splitlines() if ligne.startswith("| CI de base |")]
    assert "la licence et la carte de la racine (`scripts/modele/documentation.py`)" in ci
    assert "gitleaks sur tout l'historique ;" not in section
    assert "quatre étapes obligatoires" not in section
    assert "VISIBILITE" not in lire(METHODE)
    assert "(voir plus bas)" in section
    assert "(voir plus haut)" not in section
    assert "visibilite" not in lire(METHODE)


def test_methode_dit_le_texte_de_la_pr():
    """Le workflow `texte-pr` (lot 15) : la section des écarts et sa règle (LE-37), la tête relue
    lue par l'API (LE-55), leurs limites, et le garde qui lit tous les contrôles."""
    section = lire(METHODE).split("## Les garde-fous", 1)[1].split("\n## ", 1)[0]
    texte = " ".join(section.split())
    for fragment in (
        "`## Écarts à la spec`",
        "« Aucun. »",
        "`dependabot[bot]`",
        "ni que l'accord est réel, ni qu'un écart n'a pas été tu",
        "jamais contre l'ancien comportement",
        "ni contre le seul mécanisme principal",
        "l'accord d'Edouard porte sur cette promesse, citée",
        "`Tête relue : <SHA>`",
        "`closingIssuesReferences`",
        "force à nommer une tête, pas à la relire",
        "la PR de revue finale n'est pas visée",
        "hors des lots, un correctif qui ferme une issue par `Fixes #N` nomme aussi la tête relue",
        "aucun type d'événement documenté ne suit ce lien",
        "la branche par défaut",
        "seul à écouter `edited`",
        "le garde lit tous les contrôles, `texte-pr` compris",
        # la revue de la tâche (ronde 2) : la forme stricte, ses refus et ses bornes
        (
            "La section s'arrête au premier titre, quel que soit son niveau, ou à la première ligne de "
            "séparation (`---`) : un écart écrit après n'est pas lu"
        ),
        (
            "dans cet ordre : l'écart, qui peut contenir un séparateur, puis la promesse, qui n'en "
            "contient pas, puis l'accord, dont la date termine la ligne"
        ),
        (
            "Une ligne indentée qui commence par une puce ou un numéro (`-`, `*`, `+`, `1.`) est une "
            "sous-liste, et ne continue pas l'écart"
        ),
        "une section absente, vide ou en double",
        "avec un texte après la date, ou hors de cet ordre",
        "Un commentaire fermé ou un bloc clôturé ne compte pas",
        (
            "Un bloc indenté de quatre espaces n'est pas écarté : après une puce, il continue l'écart ; "
            "sans puce avant lui, il refuse"
        ),
        "dès que le `ci.yml` du projet n'écoute plus `edited`",
        # le workflow est géré : c'est le `ci.yml` du projet qui est semé (ronde 3)
        (
            "Le `ci.yml` d'un projet est semé : à sa mise à jour, un projet déjà né en retire "
            "`edited` lui-même"
        ),
        (
            "En mode `edouard`, le garde refuse toute fusion de la session : Edouard fusionne, et rien "
            "ne lit les contrôles à sa place"
        ),
        "la CI (le socle et `texte-pr`) le seul filet",
        # une ligne qui commence par un commentaire refuse, et le rendu de GitHub dit pourquoi
        # (ronde 3) : sous une puce, indentée comme son texte, elle paraît dans la puce
        (
            "Une ligne qui commence par un commentaire, après au plus trois espaces, et porte un texte "
            "après lui refuse, comme une "
            "ligne qui n'est ni « Aucun. » ni un écart : GitHub la rend en bloc HTML, son texte tel "
            "quel, sans Markdown, jamais en puce ; sous une puce, il ne la montre dans la puce que si "
            "elle est indentée au moins autant que le texte de la puce"
        ),
        # l'épreuve de la relance (LE-56) : elle rejoue l'événement d'origine, et l'ancien corps
        (
            "Une relance, par `gh run rerun` ou depuis l'interface de GitHub, rejoue l'événement "
            "d'origine : elle relit le titre et le corps de ce moment-là, pas ceux de la PR telle "
            "qu'elle est."
        ),
        "**Ne jamais relancer `texte-pr`.**",
        "Éprouvé dans le dépôt modèle le 07/11/2026",
        (
            "la relance de la première exécution par `gh run rerun` a relu le corps d'avant et est "
            "passée, et `gh pr checks` a montré `texte-pr` vert sur un corps qui refusait"
        ),
        (
            "Pour relire le texte, on retouche le titre ou le corps : la retouche relance "
            "`texte-pr` sur le texte en cours."
        ),
    ):
        assert fragment in texte, fragment
    for perime in (
        "un bloc de code ne compte pas",
        "rien ne bloque côté agent",
        "Ce fichier est semé",
        "GitHub la rend hors de toute liste",
    ):
        assert perime not in texte, perime
    lignes = section.splitlines()
    (ci,) = [ligne for ligne in lignes if ligne.startswith("| CI de base |")]
    assert "du texte de la PR" not in ci
    (rang,) = [i for i, ligne in enumerate(lignes) if ligne.startswith("| workflow `texte-pr` |")]
    assert lignes[rang - 1] == ci
    assert "**Le texte de la PR.**" in texte
    # Le cycle : seule la PR de clôture ferme l'issue, et elle nomme la tête relue.
    cycle = lire(METHODE).split("## Le cycle d'un lot", 1)[1].split("\n## ", 1)[0]
    (point,) = [b for b in blocs(cycle) if b[0].startswith("5. ")]
    point = " ".join(" ".join(point).split())
    assert "« Closes #N »" in point
    assert "tête relue" in point


def test_methode_dit_l_ordre_du_passage_en_public():
    """GitHub refuse une règle de protection sur un dépôt privé d'un compte gratuit : la
    visibilité d'abord, la règle ensuite (M-0002)."""
    texte = " ".join(lire(METHODE).split())
    assert (
        "d'abord, 👤, Edouard change la visibilité ; ensuite seulement, la règle de protection"
    ) in texte
    assert "Le changement de visibilité est ensuite à Edouard" not in texte
    aligner = " ".join(lire(RACINE / "docs/aligner.md").split())
    assert (
        "d'abord, 👤, le changement de visibilité ; ensuite seulement, la règle de protection"
        in aligner
    )
    assert "une ligne par couple (commit, chemin)" in texte
    assert "une ligne par constat, `<commit> <chemin>`" not in texte


def test_methode_dit_la_nature_des_depots():
    texte = " ".join(lire(METHODE).split())
    for fragment in (
        "**Dépôt de code, dépôt de données.**",
        (
            "La nature est une réponse du modèle (`nature` dans `.copier-answers.yml`, `NATURE` dans "
            "`scripts/modele/reglages.py`)."
        ),
        "Dans un dépôt de code, tout constat refuse, quelle que soit sa visibilité.",
        (
            "En CI, un dépôt public est toujours un dépôt de code, et un dépôt privé prend la nature "
            "écrite sur sa branche par défaut, jamais celle de la PR."
        ),
        (
            "**Un dépôt de code né après M-0006 passe en public sans travail préalable** : il ne lui "
            "faut que sa règle de protection."
        ),
        "**Un dépôt d'avant M-0006 ne passe pas en public** : il se scinde (M-0006, § 7).",
        "la porte relit aussi l'historique d'un dépôt de code chaque semaine (`modele-historique.yml`)",
        "`.github/constats-acceptes.txt`",
        "le message d'un commit compte comme un chemin, `message`",
        "le modèle outille en partie seulement « aucune donnée réelle dans le dépôt »",
        "**Le test d'isolation des chemins de données reste une obligation du projet**",
        "Un dépôt de données n'a pas de registre à lui",
        "Arbitrage du 16/10 : le modèle outille **quatre** familles",
    ):
        assert fragment in texte, fragment
    assert "Avant de passer un dépôt privé en public" not in texte


def test_garde_fous_dit_la_porte_des_masques():
    """La ligne `pre-commit` cite la porte des fichiers masqués (LE-23)."""
    section = " ".join(lire(METHODE).split("## Les garde-fous", 1)[1].split("\n## ", 1)[0].split())
    ligne = section.split("| hook git `pre-commit` |", 1)[1].split("| hook git `commit-msg`", 1)[0]
    assert "`.copier-answers.yml`" in ligne
    # Correctif #94 : la porte examine aussi les secrets chiffrés, selon la cible, et en cible
    # `serveur`, à un dépôt seulement (M-0002, amendement du 2026-11-04 ; #95, ronde 3).
    assert (
        "refus d'un fichier du modèle, ou d'un secret chiffré que la chaîne lit (en cible "
        "`donnees`, sauf `cible_code: aucune`, `secrets/*.env.enc` ; en cible `serveur` à un "
        "dépôt, de nature `donnees`, `deploiement/secrets/*.env.enc`), que le `.gitignore` du "
        "projet masque"
    ) in ligne
    assert "dans un dépôt de données, d'un secret chiffré" not in ligne
    # Le principe du remède, et ses trois formes, sans la liste des cas d'avant (#95, ronde 2).
    for fragment in (
        "un dossier du modèle exclu se lève par `!/<dossier>/`",
        (
            "un dossier mixte, où un fichier local peut vivre à côté d'un fichier examiné, se lève, "
            "en exclut le contenu, puis n'admet que ce qu'elle y examine (`!/cles/`, `/cles/*` puis "
            "`!/cles/*.pub`), et un ancêtre exclu, de même, suivi des lignes de ses dossiers"
        ),
        "sous un `.gitignore` imbriqué, ces lignes partent de son dossier",
        # Ce qui reste masqué, sans promettre plus que le code (#95, ronde 3).
        (
            "Ce que la porte n'examine pas reste masqué, sans refus : dans un dossier mixte, un "
            "secret en clair, une clé privée ou un fichier local ; sous un ancêtre levé, un semé du "
            "projet (`docs/cadrage.md` sous `docs/`). Sous un dossier du modèle, tout fichier est "
            "du modèle, sauf un dossier de secrets ou de clés imbriqué, ou un cache Python : un "
            "autre fichier local posé là, même un `.env`, est refusé comme fichier du modèle"
        ),
    ):
        assert fragment in ligne, fragment
    for ancien in (
        "Exclu, ce dossier se lève par",
        "un dossier exclu qui en contient un",
        "`!secrets/`",
        "Un secret en clair, une clé privée ou un fichier local restent ainsi masqués",
    ):
        assert ancien not in ligne, ancien
    # La phrase des masqués vient après celle de la confidentialité : placée avant, elle se lirait
    # comme si la porte des masqués n'avertissait que dans un dépôt privé et tournait en CI.
    assert ligne.index("au hook comme en CI") < ligne.index("Au commit d'un alignement")


def adr_rendu(rendre, nom, **reponses):
    rendu = rendre(**{**REPONSES_SERVEUR, **reponses})
    return " ".join(lire(rendu / "docs/modele/decisions" / nom).split())


def test_m0003_dit_ce_que_la_ci_ne_prouve_pas(rendre):
    """R23 : la CI lance les deux commandes par `docker exec`, qui contourne l'`ENTRYPOINT`."""
    texte = adr_rendu(rendre, "M-0003-contrat-de-l-image.md")
    assert "Le contrat se vérifie à chaque PR" not in texte
    assert "`SAUVEGARDER` et `VERIFIER` dans le conteneur, par `docker exec`" in texte
    assert "La CI ne prouve pas la clause de l'`ENTRYPOINT`" in texte
    assert "le test de restauration" in texte
    # R24 : la mécanique ne pose que deux variables en CI, le projet peut en ajouter
    assert "la mécanique ne pose que `ESSAI_ENV=ci` et `ESSAI_URL_PUBLIQUE`" in texte


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_m0003_et_m0005_disent_le_report(rendre, sauvegardes):
    """C0 : la commande facultative `REPORTER`, son contrat, et la restauration qui la lance."""
    m3 = adr_rendu(rendre, "M-0003-contrat-de-l-image.md", sauvegardes=sauvegardes)
    assert ("REPORTER" in m3) is sauvegardes
    if not sauvegardes:
        return
    for fragment in (
        "une troisième, facultative (`REPORTER=…`)",
        "**`REPORTER /actuel /donnees`, facultative**",
        "`/actuel` est une copie jetable des données en service, montée en écriture",
        # V9 : le rapport est un seul objet JSON, comme le contrôle de restaurer.sh l'exige
        "sa sortie standard étant alors un seul objet JSON",
        "une sortie qui n'est pas un seul objet JSON aussi",
        "64 en cas d'erreur d'usage, ce que rend une image qui ne connaît pas la commande",
        "aucune donnée personnelle",
        # revue C0, mineur 3 : sur un code 0, seul le rapport va au journal
        "seule sa sortie standard, le rapport, va au journal ; sur un échec, ses deux sorties y vont",
        "`REPORTER_SECTION`",
        "**Rien ne lance `REPORTER` avant une vraie restauration**",
    ):
        assert fragment in m3, fragment
    m5 = adr_rendu(rendre, "M-0005-sauvegardes-et-restauration.md")
    for fragment in (
        "[--cle <identité age>] [--sans-report]`",
        "**Le report.**",
        "`~/backups/<nom>/report-<horodatage>/`, en 700",
        "Les données en service ne sont jamais montées",
        "**La copie jetable contient des données personnelles.**",
        "Le projet garantit qu'elles ne portent aucune donnée personnelle",
        "**Tout échec abandonne la restauration, rien n'a changé**",
        "sur un code 0, la sortie standard est un seul objet JSON, le rapport",
        "une sortie qui n'est pas un seul objet JSON",
        # R63 : la copie recontrôlée après le report, sans second VERIFIER ; jq exigé
        "la forme exigée de l'instantané (non vide, rien que des fichiers et des dossiers)",
        "`VERIFIER` ne tourne pas une seconde fois",
        "une restauration où le report doit jouer est refusée avant tout effet",
        # R67 : le reste d'une restauration tuée de force a sa rétention
        "celle qu'un arrêt brutal laisse, la sauvegarde de la nuit la retire, sous le même verrou",
        "**`--sans-report`** est le choix explicite de l'opérateur",
        "`tester-restauration.sh` ne le lance pas",
    ):
        assert fragment in m5, fragment


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_m0004_ne_renvoie_a_m0005_qu_avec_sauvegardes(rendre, sauvegardes):
    """R24 : sans sauvegardes, M-0005 n'est pas rendu, et M-0004 n'y renvoie pas. L'instantané
    des données, celui que la chaîne monte sur /config et /contenu, existe dans les deux cas ;
    seul celui de /donnees suit les sauvegardes."""
    texte = adr_rendu(rendre, "M-0004-chaine-de-livraison.md", sauvegardes=sauvegardes)
    assert ("M-0005" in texte) is sauvegardes
    assert ("instantané de `/donnees`" in texte) is sauvegardes
    assert "**L'instantané des données.** Pour un couple qui a un commit" in texte


def test_m0002_amende():
    texte = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    assert "le contrôle de dérive en tient compte" not in texte
    assert "le garde de Claude est alors la seule serrure côté agent" in texte
    # lot 15 : le texte de la PR sort du socle, vers `texte-pr`, qui fait partie du filet
    assert "la CI (le socle et `texte-pr`) le seul filet" in " ".join(texte.split())
    assert "CI du socle le seul filet" not in " ".join(texte.split())
    assert "avertit sur ce qui identifie" in texte
    assert "refuse toujours les secrets" in texte
    assert "gitleaks n'est pas concerné" not in texte
    assert "github.event.repository.private" in texte
    assert "quatre étapes obligatoires" not in texte
    assert "visibilite=public" not in texte
    assert "`VISIBILITE`" not in texte
    assert "la porte suit la nature du dépôt, de code ou de données (M-0006)" in texte
    assert "amendement du 2026-10-17" in texte
    assert "`Monitor`" in texte
    assert "PR obligatoire" not in texte
    # amendement du 18/10 : qui fusionne (`fusion`), et les étiquettes réservées à Edouard
    assert "- **Amendé** le 2026-10-18" in texte
    assert "`fusion`" in texte
    assert "étiquette" in texte
    # les amendements, dans l'ordre chronologique
    dates = re.findall(r"^- \*\*Amendé\*\* le (\S+),", texte, flags=re.MULTILINE)
    assert dates == [
        "2026-10-17",
        "2026-10-18",
        "2026-10-27",
        "2026-10-29",
        "2026-10-29",
        "2026-11-04",
        "2026-11-06",
    ]
    assert (
        "- **Amendé** le 2026-10-29, avec le lot 11 : la porte suit la nature du dépôt, de code ou "
        "de données (M-0006)"
    ) in texte
    # le remède des masqués, tel que masques.py le prescrit : des lignes ancrées (#95, ronde 2)
    texte = " ".join(texte.split())
    assert "ou `!<dossier>/` quand un dossier parent est exclu" not in texte
    assert (
        "`!/<chemin>`, ou les lignes du plus haut dossier exclu, car git ne regarde pas dans un "
        "dossier exclu"
    ) in texte
    # Correctif #94 : un secret chiffré entre ; seul le masque d'un secret en clair ne se lève pas.
    assert "le masque d'un fichier de secrets ne se lève jamais" not in texte
    assert "le masque d'un secret en clair ne se lève jamais" in texte
    # Sous un dossier du modèle, seul un cache Python s'en sort (#95, ronde 4).
    assert "un fichier local s'en sort" not in texte
    assert (
        "ou un cache Python : un autre fichier local posé là, même un `.env`, est refusé comme "
        "fichier du modèle. Ailleurs, le masque d'un secret en clair ne se lève jamais"
    ) in texte


def test_m0002_amende_par_le_correctif_94():
    """La porte des masqués examine l'instance d'un dépôt de données, secrets chiffrés compris, et
    leur remède ne laisse pas entrer un secret en clair (masques.py, `remede`)."""
    brut = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    texte = " ".join(brut.split())
    # La porte suit la cible, comme `chemins_examines`, et, en cible `serveur`, la nature.
    assert (
        "- **Amendé** le 2026-11-04, avec le correctif modele-projet#94 : en cible `donnees`, la "
        "porte des fichiers masqués examine aussi l'instance"
    ) in texte
    for fragment in (
        "En cible `donnees`, elle examine aussi `config/README.md` et `contenu/README.md`",
        (
            "sauf `cible_code: aucune`, l'instance : `.sops.yaml`, `env/prod.env`, "
            "`env/staging.env`, `cles/*.pub` et les secrets chiffrés `secrets/*.env.enc`, que la "
            "chaîne lit (amendement du 2026-11-04)"
        ),
        # Le principe du remède, une fois, sans la liste des cas d'avant (#95, ronde 2).
        "un dossier du modèle se lève par `!/<dossier>/`",
        (
            "un dossier mixte, où un fichier local peut vivre à côté d'un fichier examiné, se lève, "
            "en exclut le contenu, puis n'admet que ce qu'elle y examine, et un ancêtre exclu, de "
            "même, suivi des lignes de ses dossiers"
        ),
        "Sous un `.gitignore` imbriqué, ces lignes partent de son dossier",
        # En cible `serveur`, ce que le modèle écrit, et l'instance à un dépôt (#95, ronde 3).
        (
            "En cible `serveur`, elle n'examine sous `deploiement/` que ce que le modèle y écrit, "
            "ses fichiers de premier niveau par leur nom, et l'instance et ses secrets chiffrés "
            "qu'à un dépôt, en nature `donnees` : un dépôt de code a les siens dans "
            "`<nom>-donnees`"
        ),
        (
            "Ce que la porte n'examine pas reste masqué, sans refus, un semé du projet sous un "
            "ancêtre levé compris, que la vérification de `docs/aligner.md` voit"
        ),
    ):
        assert fragment in texte, fragment
    assert "Dans un dépôt de données, elle examine aussi" not in texte
    for ancien in (
        "Exclu, ce dossier se lève par",
        "un dossier exclu qui en contient un",
        "`!secrets/`",
        "lève leur masque sans celui des secrets en clair",
    ):
        assert ancien not in texte, ancien
    # Relecture de la reprise : une ligne de la puce dépassait 100 caractères.
    (puce,) = [
        b for b in blocs(brut) if b[0].startswith("- **Un fichier du modèle que le `.gitignore`")
    ]
    (amendement,) = [
        b for b in blocs(brut) if b[0].startswith("- **Amendé** le 2026-11-04, avec le correctif")
    ]
    longues = [ligne for ligne in (*puce, *amendement) if len(ligne) > 100]
    assert not longues, longues


def test_m0006_dit_ce_que_la_scission_refait():
    """La scission ne fait pas que déplacer : `env/` et `cles/` sont rendus à neuf, et
    `.sops.yaml`, resté à la racine, se refait pour le nouveau chemin des secrets (#94)."""
    brut = lire(DECISIONS / "M-0006-code-et-donnees.md")
    assert "- **Amendé** le 2026-11-04, avec le correctif modele-projet#94 : à la scission," in brut
    texte = " ".join(brut.split())
    assert "ne fait ensuite que déplacer ces dossiers, avec `deploiement/env/`" not in texte
    for fragment in (
        "La scission déplace ensuite ces dossiers et les secrets chiffrés vers le dépôt de données",
        "Le modèle y rend `env/` et `cles/` à la place de `deploiement/env/` et de `deploiement/cles/`",
        "`.sops.yaml` s'y refait pour le nouveau chemin des secrets (amendement du 2026-11-04)",
        "Le contrat de l'application ne change pas (M-0004, § 8)",
    ):
        assert fragment in texte, fragment
    puce = brut.split("- **Un projet né avant M-0006 garde la chaîne à un dépôt", 1)[1]
    puce = puce.split("\n\n", 1)[0]
    longues = [ligne for ligne in puce.splitlines() if len(ligne) > 100]
    assert not longues, longues


# m3 : ce qui est garanti, exactement. Le mode lui-même se lit par l'API de GitHub ; la branche de
# `ref=` vient des réglages locaux, et `--fusion` posé dans un `settings.json` local l'emporte.
@pytest.mark.parametrize("chemin", [METHODE, DECISIONS / "M-0002-garde-fous-et-confidentialite.md"])
def test_lecture_du_mode_de_fusion_exacte(chemin):
    texte = " ".join(lire(chemin).split())
    assert "jamais dans la copie locale" not in texte
    assert "pas dans la copie locale" not in texte
    assert "Le mode lui-même se lit sur GitHub, par l'API (`gh api`)" in texte
    assert "Deux entrées restent locales" in texte
    assert "`BRANCHE_PRINCIPALE`" in texte
    assert "`ref=`" in texte
    assert "`--fusion" in texte
    assert "dans un `settings.json` de la copie" in texte


def test_methode_ligne_signaux():
    texte = lire(METHODE)
    assert "| hook Claude `SessionStart`" in texte
    assert "le garde de Claude **et les signaux** toujours branchés" in texte
    # lot 14 : le gabarit resté vide, après « Il ne bloque jamais. », avant les phrases des forks
    (ligne,) = [lig for lig in texte.splitlines() if lig.startswith("| hook Claude `SessionStart`")]
    assert ligne.startswith(
        "| hook Claude `SessionStart` (au démarrage et à la reprise) | affiche ce qui est rouge sur "
        "GitHub : les exécutions de la branche principale, les PR ouvertes et les workflows "
        "désactivés. Il ne bloque jamais. Il signale aussi un gabarit resté vide que le README lie, "
        "et un README qui ne lie aucun document du dépôt. Ce que n'importe qui écrit depuis un fork "
        "n'entre pas dans le contexte de Claude : "
    )
    for phrase in (
        "les exécutions de PR (`pull_request…`) sont écartées",
        "une PR ou un workflow venus d'ailleurs que le dépôt s'affichent sans le texte qu'ils portent",
        (
            "Une PR d'un fork paraît ainsi sans titre ni nom de contrôle, un workflow absent de la "
            "copie, sans son nom |"
        ),
    ):
        assert phrase in ligne, phrase
    texte = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    assert "`SessionStart`" in texte
    assert "signaux.py" in texte


@pytest.mark.parametrize("chemin", [METHODE, DECISIONS / "M-0002-garde-fous-et-confidentialite.md"])
def test_signaux_n_affichent_pas_ce_qu_un_fork_ecrit(chemin):
    """Revue finale du lot 8 : les exécutions de PR écartées, et rien du texte d'un fork."""
    texte = " ".join(lire(chemin).split())
    assert "les exécutions de PR (`pull_request…`) sont écartées" in texte
    assert (
        "une PR ou un workflow venus d'ailleurs que le dépôt s'affichent sans le texte qu'ils portent"
        in texte
    )
    assert (
        "Une PR d'un fork paraît ainsi sans titre ni nom de contrôle, un workflow absent de la "
        "copie, sans son nom" in texte
    )
    assert "que tout le monde peut écrire" not in texte
    assert "que n'importe qui peut écrire sur un dépôt public" not in texte


# --- lot 12 : le contrat de /config et la chaîne à deux dépôts (M-0006, §§ 4 à 6) ---

AMENDE_LOT_12 = "- **Amendé** le 2026-10-29, avec le lot 12 :"


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_m0003_dit_le_contrat_de_l_instance(rendre, sauvegardes):
    """M-0003, amendé : /config, /contenu, les deux commandes, le champ configuration, la règle
    des paires et l'exemple, tels que lib.sh, deployer.sh et ci/verifier-image.sh les font."""
    texte = adr_rendu(rendre, "M-0003-contrat-de-l-image.md", sauvegardes=sauvegardes)
    assert AMENDE_LOT_12 in texte
    for fragment in (
        "### 6. L'instance : `/config` et `/contenu`",
        "`VERIFIER_CONFIG=<mots>` : lancée en `<mots> /config`",
        "`<mots> /contenu /en-service`",
        "Codes : 0 conforme, 2 non conforme, 64 usage ; tout autre code refuse.",
        "sans réseau (`--network none`)",
        "**Ils vont par paires**",
        "au moins un fichier autre que le `README.md` de sa racine",
        "**La santé dit quelle configuration sert**",
        "`exemple` en staging et `montee` en prod",
        "**Le staging ne monte jamais `/config`**",
        "**La prod ne se replie pas sur l'exemple**",
        "vers un couple précédent sans commit de données",
        # la prod sert sans /config dans deux cas : les deux retours vers une version d'avant
        "Deux exceptions, où la prod sert sans `/config`",
        "l'échec de la première version qui déclare `VERIFIER_CONFIG`",
        "une commande déclarée sans son dossier d'exemple refuse",
        "un dossier d'exemple sans sa commande n'est pas vérifié, et le journal le dit",
        "Un projet à un dépôt porte lui aussi son exemple, à côté d'`instance/`",
        "**Un projet qui ne déclare ni l'une ni l'autre ne voit aucun changement**",
        # à un dépôt, la CI du code vérifie instance/ comme le fera le déploiement
        (
            "À un dépôt, la CI du code vérifie `instance/` comme le fera le déploiement, dès qu'une "
            "commande est déclarée"
        ),
        "et le déploiement revérifie",
    ):
        assert fragment in texte, fragment
    assert "la CI ne lit pas `instance/`" not in texte
    assert "Une seule exception" not in texte
    # La route de santé du § 2 annonce le champ, et la CI prouve la clause de l'ENTRYPOINT pour
    # les deux commandes de l'instance, qu'elle lance par docker run.
    assert "pour un projet qui lit son instance (amendement du 2026-10-29) : `exemple` ou" in texte
    assert (
        "**La CI prouve la clause de l'`ENTRYPOINT` pour `VERIFIER_CONFIG` et `VERIFIER_CONTENU`**"
        in texte
    )
    assert not RENVOI_AU_PLAN.search(texte)


@pytest.mark.parametrize(
    ("reponses", "mode"),
    [(REPONSES_SERVEUR, "un"), (REPONSES_SERVEUR_CODE, "deux")],
    ids=["un-depot", "deux-depots"],
)
def test_m0004_dit_le_couple_et_les_deux_modes(rendre, reponses, mode):
    """M-0004, amendé : les deux modes, le couple, l'instantané monté, les étiquettes de données,
    les déclencheurs et le retour arrière, avec les limites que la sonde et deployer.sh tiennent."""
    texte = " ".join(
        (rendre(**reponses) / "docs/modele/decisions/M-0004-chaine-de-livraison.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert AMENDE_LOT_12 in texte
    for fragment in (
        "### 8. Le couple et les deux modes",
        "| | À deux dépôts | À un dépôt |",
        "`deploye` et `precedent` portent `<image@sha256:…> <version> <commit>`",
        "`echec` porte `<image@sha256:…> <commit>`",
        "`read -r image version _`",
        "`donnees-AAAA.MM.JJ.n`",
        # le mode un : le commit du couple est la révision de l'image
        "la révision de l'image visée",
        "le commit que la `vX.Y.Z` désigne",
        # la déclaration qui compte : celle de la version du code visée
        "la déclaration de la version du code visée, jamais celle qu'on quitte",
        # un projet sans commande, et la limite de l'env et des secrets
        "qu'avant l'appel de `deployer.sh`",
        "**La limite d'un projet sans commande.**",
        # l'attente d'une étiquette de données
        "« aucune version des données »",
        "son signal ok dit « <version> attend une version des données »",
        # le staging suit la branche que nomme BRANCHE_DONNEES, pas forcément la principale
        "la tête de la branche que nomme `ESSAI_BRANCHE_DONNEES`",
        # une commande ajoutée ou retirée
        "Dans l'intervalle, la CI des données refuse",
        # le retour arrière et ses deux cas de transition
        "ne monte ni ne vérifie rien, même si `projet.env` déclare une commande",
        "pas de retour arrière après une version qui retire ses commandes",
        # le cas général : --retour vérifie precedent avec la déclaration de la version quittée
        (
            "`--retour` vérifie le couple de `precedent` avec la déclaration de la version qu'il "
            "quitte, le `projet.env` du clone en service. Après une version qui ajoute ou retire "
            "une commande, le retour peut donc être refusé : par la règle des paires, ou par le "
            "code 64 de l'ancienne image, qui ne connaît pas la commande. Le refus ne change rien. "
            "Le remède est une étiquette (§ 2), qui remet en service un couple vérifié."
        ),
        "forme un couple nouveau : l'ancienne image et le commit de données en service",
        # les clones des données
        "« clone des données absent »",
        "seule l'absence du signal ok avertit",
        "« clone des données modifié »",
        "« mise à jour du clone des données impossible »",
        # le ménage des instantanés, au § 8 : ce qu'il garde
        "**Le ménage des instantanés.**",
        "plus les 3 plus récents des autres, et retire les autres, ainsi que tout `.partiel`",
        # l'instantané, puis son montage, en deux paragraphes
        "**Le montage de l'instantané.**",
    ):
        assert fragment in texte, fragment
    assert "la tête de la branche principale des données" not in texte
    assert "la tête de sa branche principale" not in texte
    # Les clés du parc se lisent dans le clone des données, selon le mode.
    assert "`deploiement/cles/serveur.pub` et `hors-ligne.pub`" not in texte
    assert "`cles/` à deux dépôts, `deploiement/cles/` à un dépôt" in texte
    # Ce projet-ci : son mode, dit en une phrase.
    phrase = {"un": "Ce projet est à un dépôt", "deux": "Ce projet est à deux dépôts"}
    assert phrase[mode] in texte
    autre = "deux" if mode == "un" else "un"
    assert phrase[autre] not in texte
    assert not RENVOI_AU_PLAN.search(texte)


def test_m0005_dit_le_couple_de_l_instantane(rendre):
    """M-0005, amendé : le .couple voisin, son chiffrement, son envoi, et la restauration qui le
    dit ; la clé hors ligne se lit dans le clone des données."""
    texte = adr_rendu(rendre, "M-0005-sauvegardes-et-restauration.md")
    assert AMENDE_LOT_12 in texte
    for fragment in (
        "**Le couple de l'instantané.**",
        "`<nom>-<horodatage>.couple`",
        "celui de `deploye` à cet instant",
        "pour `pre-deploiement/`, le couple que le déploiement quitte",
        "`<nom>-<horodatage>.couple.age`",
        "l'archive part quand même, et la nuit est en échec",
        "« couple de l'instantané inconnu »",
        "Le couple ne décide de rien",
        "demande la phrase deux fois",
        # au premier déploiement, sans deploye, pas de .couple
        "Sans `deploye`, ou s'il ne se lit pas, il n'y a pas de `.couple`",
        # la restauration lit le couple avec la source, et le dit après VERIFIER
        "Avec la source, la restauration lit le couple dans le fichier voisin",
        "Après `VERIFIER`, elle le dit quand il diffère du couple déployé",
    ):
        assert fragment in texte, fragment
    assert "Après `VERIFIER`, la restauration lit le couple" not in texte
    assert "deploiement/cles/" not in texte
    assert "en 4e position" not in texte
    assert not RENVOI_AU_PLAN.search(texte)


def test_m0002_amende_par_le_lot_12():
    """La porte d'un dépôt de code suit le premier segment du chemin, et le motif age ; le garde
    refuse l'envoi d'une étiquette de données."""
    texte = " ".join(lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md").split())
    assert AMENDE_LOT_12 in texte
    for fragment in (
        "**Dans un dépôt de code, la porte suit aussi les chemins**",
        "un fichier dont le premier segment du chemin est `instance/`, `config/` ou `contenu/`",
        "un `src/config/` reste du code",
        (
            "un fichier nommé `*.enc` ou `.sops.yaml`, et un `*.pub` dans un dossier `cles/`, "
            "à toute profondeur"
        ),
        "une clé publique `age` (`age1…`), où qu'elle soit écrite",
        # l'exception du gabarit ne vaut que pour les noms : config/x.jinja refuse
        "sauf un gabarit `….jinja`, qui n'est pas le fichier qu'il rend",
        "`instance/`, `config/` ou `contenu/`, gabarit compris",
        "`.github/constats-acceptes.txt`",
        "`donnees-AAAA.MM.JJ.n`",
    ):
        assert fragment in texte, fragment
    assert "où qu'elle soit écrite. Un gabarit" not in texte
    assert not RENVOI_AU_PLAN.search(texte)


def test_m0006_dit_le_choix_des_deux_modes():
    """M-0006 : son § 6 dit le choix fait (les deux modes sont gardés) ; son § 3 dit la règle des
    chemins telle que la porte la tient (le premier segment)."""
    texte = " ".join(lire(DECISIONS / "M-0006-code-et-donnees.md").split())
    assert AMENDE_LOT_12 in texte
    assert "Le lot de la chaîne a gardé les deux modes" in texte
    assert "passe aux versions suivantes du modèle sans attendre sa scission" in texte
    assert "`instance/config/` et `instance/contenu/`" in texte
    assert "tout `contenu/`, à n'importe quelle profondeur" not in texte
    assert (
        "tout fichier sous un dossier de premier niveau `instance/`, `config/` ou `contenu/`"
        in texte
    )
    assert not RENVOI_AU_PLAN.search(texte)


def test_m0006_dit_ou_vit_le_script():
    """M-0006, § 7 : le script de création des deux dépôts est nommé, avec son dépôt."""
    texte = " ".join(lire(DECISIONS / "M-0006-code-et-donnees.md").split())
    assert "`poste/Nouveau-Projet.ps1`" in texte
    assert "`modele-projet`" in texte


def test_methode_dit_les_deux_modes_et_les_etiquettes_de_donnees():
    """La méthode : les étiquettes de données sont à Edouard (la table du garde), la porte d'un
    dépôt de code suit les chemins, et les deux modes de la chaîne, avec le contrôle des secrets
    d'un dépôt de données."""
    texte = " ".join(lire(METHODE).split())

    def ligne_de_la_table(debut, suivante):
        return texte.split(debut, 1)[1].split(suivante, 1)[0]

    garde = ligne_de_la_table("| hook Claude `PreToolUse`", "| hook Claude `SessionStart`")
    assert "un refspec `refs/tags/…`, `v1.2.3` ou `donnees-…`" in garde
    pre_commit = ligne_de_la_table("| hook git `pre-commit` |", "| hook git `commit-msg`")
    instance = "les fichiers de l'instance, lus sur leur chemin, et toute clé publique `age`"
    assert instance in pre_commit
    for fragment in (
        "Les étiquettes de données `donnees-AAAA.MM.JJ.n` sont à Edouard, comme les `vX.Y.Z`",
        "**La porte d'un dépôt de code suit aussi les chemins.**",
        "tout fichier dont le premier segment du chemin est `instance/`, `config/` ou `contenu/`",
        "sauf un gabarit `….jinja`, qui n'est pas le fichier qu'il rend",
        "`instance/`, `config/` ou `contenu/`, gabarit compris",
        "**Les deux modes de la chaîne.**",
        "la branche des données que nomme `env/staging.env` (`…_BRANCHE_DONNEES`)",
        "**À deux dépôts**",
        "**À un dépôt**",
        "la plus haute `vX.Y.Z` du code et la plus haute étiquette de données",
        "la prod prend le commit de la plus haute `vX.Y.Z`",
        "sont contrôlés par `modele-donnees.yml`, contre le `.cles` du dépôt de code",
        "`secrets.ps1 refaire` y prend le `.cles` du clone voisin du dépôt de code",
    ):
        assert fragment in texte, fragment
    assert not RENVOI_AU_PLAN.search(texte)


def blocs(texte):
    """Les paragraphes et les éléments de liste du Markdown, chacun en ses lignes."""
    resultat, courant = [], []
    for ligne in texte.splitlines():
        if not ligne.strip() or re.match(r"\s*(?:[-*] |\d+\. |#)", ligne):
            if courant:
                resultat.append(courant)
            courant = [ligne] if ligne.strip() else []
        else:
            courant.append(ligne)
    if courant:
        resultat.append(courant)
    return resultat


def test_les_phrases_recoupees_tiennent_en_100_caracteres():
    """La revue finale du lot de la chaîne : trois phrases dépassaient 100 caractères, ou étaient
    coupées par un retour à la ligne au milieu de leur élément. Chaque élément qui les porte tient
    en 100 caractères par ligne, et seule sa dernière ligne est courte."""
    (m0005,) = DECISIONS.glob("*M-0005-sauvegardes-et-restauration.md*")
    cas = (
        (m0005, "**Le couple ne décide de rien**"),
        (METHODE, "`secrets.ps1 refaire` y prend le `.cles` du clone voisin du dépôt de code"),
        (DECISIONS / "M-0006-code-et-donnees.md", "La prod y prend le commit de la plus haute"),
    )
    for chemin, phrase in cas:
        trouves = [b for b in blocs(lire(chemin)) if phrase in " ".join(" ".join(b).split())]
        assert len(trouves) == 1, phrase
        (bloc,) = trouves
        assert max(len(ligne) for ligne in bloc) <= 100, phrase
        assert min(len(ligne) for ligne in bloc[:-1]) >= 70, phrase


def test_changer_de_cible_dit_ce_que_fait_copier():
    """« Changer de cible » disait que les semés de l'ancienne cible restaient : Copier en retire
    une partie, même retouchés, et garde l'ancien contenu des autres (#94). Le passage d'un projet
    à un dépôt en dépôt de données, qu'éprouve `tests/test_mise_a_jour.py`, y est nommé."""
    (bloc,) = [b for b in blocs(lire(METHODE)) if b[0].startswith("- Changer de cible,")]
    texte = " ".join(" ".join(bloc).split())
    assert "Les fichiers semés de l'ancienne cible restent" not in texte
    for fragment in (
        (
            "Les fichiers semés de l'ancienne cible que la nouvelle ne rend pas disparaissent "
            "aussi, même retouchés, sans conflit ni `.rej`"
        ),
        "Les semés que les deux cibles rendent gardent leur contenu d'avant",
        "Copier sème à neuf un semé absent du projet",
        "Une question nouvelle prend son défaut sous `--defaults`",
        "`--data cible_code=serveur` est obligatoire",
        # Revue de #95 : `.gitignore` porte les règles du projet, et son retrait salit l'arbre.
        "Sauf `.gitignore`, qui ne se retire jamais",
        "ce que Copier refuse comme un arbre sale",
        # Relecture de la reprise : sous `*secret*`, `secrets/` reste exclu sans `!/secrets/`, et la
        # porte des masqués ne le voit pas, puisque le secret chiffré déplacé est suivi. Ces lignes
        # sont celles de son remède pour ce dossier mixte (#95, ronde 2).
        (
            "pour un dépôt de données, `!/secrets/`, `/secrets/*` puis `!/secrets/*.env.enc`, à la "
            "fin du fichier : les lignes que la porte des masqués donne pour ce dossier mixte, et "
            "qu'elle ne demande pas, puisqu'elle ne voit pas un secret chiffré déjà suivi"
        ),
        # Copier ne déplace rien de ce qu'il ne connaît pas.
        "Ce que le modèle ne connaît pas reste où il est",
        "se déplacent par `git mv`",
    ):
        assert fragment in texte, fragment
    assert max(len(ligne) for ligne in bloc) <= 100
    assert min(len(ligne) for ligne in bloc[:-1]) >= 70


# Le principe du remède de la porte des masqués (#95, ronde 2 après relecture) : chaque texte le dit
# une fois, au lieu d'énumérer des cas, et `tests/test_masques.py` le prouve par une matrice.
PRINCIPE_DU_REMEDE = "n'admet que ce que la porte examine, toujours par des lignes ancrées"


def _aplati(texte):
    return " ".join(texte.split())


def _docstring_des_masques():
    return _aplati(ast.get_docstring(ast.parse(lire(TEMPLATE / "scripts/modele/masques.py"))))


def _ligne_pre_commit():
    section = _aplati(lire(METHODE).split("## Les garde-fous", 1)[1].split("\n## ", 1)[0])
    return section.split("| hook git `pre-commit` |", 1)[1].split("| hook git `commit-msg`", 1)[0]


def _changer_de_cible():
    (bloc,) = [b for b in blocs(lire(METHODE)) if b[0].startswith("- Changer de cible,")]
    return _aplati(" ".join(bloc))


def _puce_des_masques_de_m0002():
    brut = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    (puce,) = [
        b for b in blocs(brut) if b[0].startswith("- **Un fichier du modèle que le `.gitignore`")
    ]
    return _aplati(" ".join(puce))


def _correctif_dans_claude_md():
    brut = lire(RACINE / "CLAUDE.md")
    return _aplati(brut.split("Correctif du 04/11 : la scission", 1)[1].split("\n\n", 1)[0])


@pytest.mark.parametrize(
    ("texte", "fragment", "anciens"),
    [
        (
            _docstring_des_masques,
            f"Le principe du remède : il {PRINCIPE_DU_REMEDE}.",
            ("Un dossier de secrets exclu ne se lève jamais seul",),
        ),
        (_ligne_pre_commit, f"Le remède {PRINCIPE_DU_REMEDE}", ("Exclu, ce dossier se lève",)),
        (
            _changer_de_cible,
            "les lignes que la porte des masqués donne pour ce dossier mixte",
            ("puisque la porte des masqués ne voit pas un secret chiffré déjà suivi, et",),
        ),
        (
            _puce_des_masques_de_m0002,
            f"Le remède {PRINCIPE_DU_REMEDE}",
            ("Exclu, ce dossier se lève", "un dossier exclu qui en contient un"),
        ),
        (
            _correctif_dans_claude_md,
            f"le remède {PRINCIPE_DU_REMEDE}",
            ("et de même après l'exception d'un dossier exclu qui le contient",),
        ),
    ],
    ids=["docstring", "pre-commit", "changer-de-cible", "m0002", "claude-md"],
)
def test_le_principe_du_remede_dit_une_fois(texte, fragment, anciens):
    lu = texte()
    assert lu.count(fragment) == 1, fragment
    for ancien in anciens:
        assert ancien not in lu, ancien


# --- lot 14 : le README des projets ---

DOCUMENTATION = TEMPLATE / "docs/modele/documentation.md"
M0002 = DECISIONS / "M-0002-garde-fous-et-confidentialite.md"
# Un bloc de code clôturé, de sa clôture d'ouverture à sa clôture de fermeture.
CLOTURE = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL)
TITRES_DOCUMENTATION = [
    "## Le README",
    "## Ce qui n'y va jamais",
    "## Sur un téléphone",
    "## Un fait une fois",
    "## Les textes d'un projet",
    "## Retirer un texte",
    "## Les trois contrôles",
]
# Ce que le texte géré et la docstring de `documentation.py` disent dans les mêmes mots : ce que
# la carte ne compte pas, ce qu'un lancement local dit de la CI, et les écarts connus à GitHub.
DOCUMENTATION_ET_DOCSTRING = (
    "`CLAUDE.local.md`, que le `.gitignore` semé exclut ; un projet né plus tôt l'y ajoute",
    "un `.md` de la racine non suivi compte en local, et la CI ne le voit pas",
    "le README et `CLAUDE.md` se lisent tels qu'ils sont dans la copie, validés ou non",
    (
        "la nature se lit dans la copie, alors qu'en CI un dépôt privé prend celle de sa branche "
        "par défaut"
    ),
    "ne compte en local qu'un `LICENSE` suivi, comme la CI",
    (
        'Un lien HTML (`<a href="…">`) ne compte pas : la carte demande un lien Markdown, et le '
        "remède est la forme `[texte](cible)`"
    ),
    (
        "dans un bloc clôturé à l'intérieur d'une citation, ou d'un élément de liste indenté de "
        "quatre colonnes ou plus, s'il s'ouvre par des tildes ou qu'une ligne vide le coupe"
    ),
    "dans une citation ou un élément de liste, dans un bloc ouvert par `<!--`",
    "un lien dont le texte porte un `|` dans une cellule de tableau",
    # les liens seulement : un titre qui suit coupe le paragraphe, et reste lu, comme sur GitHub
    "un commentaire HTML ouvert dans un paragraphe cache les liens jusqu'à sa fermeture, plus loin",
    (
        "et d'autres formes rares des conteneurs et des commentaires (un bloc clôturé non fermé "
        "dans un élément de liste, un code en ligne qui franchit une ligne `>` vide, un texte de "
        "lien à plus de trois niveaux de crochets, une définition après un titre souligné, un "
        "commentaire fermé par `--->` dans un paragraphe)"
    ),
)


def test_documentation_md(tmp_path, env_isole):
    """Le texte géré de la documentation (spec du lot 14, § 4) : sans Jinja ni renvoi au plan, ses
    sections, la règle du semé, les sorties des trois contrôles telles que `documentation.py` les
    écrit, et la ligne des décisions dans un bloc de code : hors de lui, elle serait un lien mort
    depuis `docs/modele/`."""
    import documentation

    texte = lire(DOCUMENTATION)
    assert "{{" not in texte
    assert "{%" not in texte
    assert not RENVOI_AU_PLAN.search(texte)
    assert texte.splitlines()[0] == "# Documenter un projet né du modèle"
    hors_du_code = CLOTURE.sub("", texte)
    assert [ligne for ligne in hors_du_code.splitlines() if ligne.startswith("## ")] == (
        TITRES_DOCUMENTATION
    )
    plat = " ".join(texte.split())
    for fragment in (
        "semé se vide ou se réécrit, il ne se supprime pas",
        "fichier de la racine se cite par un lien",
        "`python -B scripts/modele/documentation.py --gabarits-vides`",
        "La documentation de la racine (licence, carte)",
        # un lancement local, et ce qu'il dit de la CI : trois écarts, la licence comme en CI
        "`python -B scripts/modele/documentation.py`, lancé depuis la racine",
        "La PR qui pose ou change la nature d'un dépôt privé y est donc jugée sous l'ancienne",
        "Un `LICENSE` qu'un `copier update` vient de créer n'est pas suivi : il s'indexe",
        # les sorties, telles que le script les écrit
        "<chemin> : garde le marqueur *AAAA-MM-JJ* du gabarit",
        "<chemin> : corps vide (titres et consignes seulement)",
        "<chemin>/ : dossier sans autre fichier que README.md",
        "le README ne lie aucun document du dépôt",
        "pas de README.md",
        "licence : non exigée (nature donnees)",
        "licence : LICENSE absent ou vide, exigé en nature code",
        "carte : CLAUDE.md n'est pas lié par README.md",
        f"carte : <nom> {documentation.NON_LIE}",
        "`refus`, en dernière ligne",
        "la première ligne, quand un fichier n'est pas lié",
        "refusent quelle que soit la première ligne",
        "documentation : non lue (erreur)",
        "le titre `documentation :` puis une ligne `- <constat>` chacun",
        "imprime un constat par ligne et rend toujours 0",
        # comment répondre à chaque sortie
        "À `carte : README.md absent` ou `carte : CLAUDE.md absent`, rendre le fichier",
        "À `pas de README.md`, de même",
        # ce qui n'est pas local
        "porte un deux-points sous Windows, qui y nomme un lecteur (`Z:`, en tête comme plus loin",
        # les écarts connus au rendu de GitHub, repris de la docstring du script
        "dans un bloc de code indenté",
        "un lien `docs/Cadrage.md` vers `docs/cadrage.md`",
        "un avertissement de trop, jamais un refus",
        *DOCUMENTATION_ET_DOCSTRING,
    ):
        assert fragment in plat, fragment
    for ancien in (
        "donne les mêmes lignes que la CI",
        "comme `CLAUDE.local.md`, n'est pas compté",
        "Quatre laissent passer",
    ):
        assert ancien not in plat, ancien
    # Les lignes de la licence et de la carte, telles que le script les écrit sur une racine, sont
    # chacune dans la liste de leur contrôle.
    section = texte.split("### La licence", 1)[1].split("### Le gabarit resté vide", 1)[0]
    listes = " ".join(ligne for ligne in section.splitlines() if ligne.startswith("- `"))
    racine = tmp_path / "racine"
    racine.mkdir()
    # Une racine vide : la licence absente, la tête à 0 fichier, README.md et CLAUDE.md absents.
    sorties = [*documentation.licence(racine, "code")[0], *documentation.carte(racine)[0]]
    (racine / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (racine / "README.md").write_text("[c](CLAUDE.md)\n", encoding="utf-8")
    (racine / "CLAUDE.md").write_text("# C\n", encoding="utf-8")
    # README.md et CLAUDE.md seuls : la tête au singulier, sans nombre à remplacer.
    sorties.append(documentation.carte(racine)[0][0])
    (racine / "NOTICE.md").write_text("# N\n", encoding="utf-8")
    # Un `.md` non lié : la tête d'un refus, ses deux nombres en place.
    sorties.append(
        documentation.carte(racine)[0][0].replace(" 2 ", " <n> ", 1).replace(" 1 ", " <k> ", 1)
    )
    (racine / "README.md").write_text("[c](CLAUDE.md) [n](NOTICE.md)\n", encoding="utf-8")
    # Une racine en ordre : la licence présente, et la tête de la carte, son nombre en place.
    sorties += documentation.licence(racine, "code")[0]
    sorties.append(documentation.carte(racine)[0][0].replace(" 2 ", " <n> ", 1))
    # À la racine d'un dépôt git, un LICENSE que git ne suit pas.
    depot = tmp_path / "depot"
    depot.mkdir()
    git(depot, env_isole(), "init", "-q", "-b", "main")
    (depot / "LICENSE").write_text("MIT\n", encoding="utf-8")
    sorties += documentation.licence(depot, "code")[0]
    assert len(sorties) == 9, sorties
    assert len(set(sorties)) == 9, sorties
    for ligne in sorties:
        assert f"`{ligne}`" in listes, ligne
    decisions = "| [Les décisions](docs/decisions/) |"
    assert any(decisions in bloc.group(0) for bloc in CLOTURE.finditer(texte))
    assert decisions not in hors_du_code
    # Le gabarit se montre par ses places, jamais par sa syntaxe.
    assert any("# <nom>" in bloc.group(0) for bloc in CLOTURE.finditer(texte))
    # Aucun lien hors du code : depuis `docs/modele/`, un chemin de la racine mènerait nulle part.
    assert documentation.liens(texte) == []
    # Lié par un README, le texte ne se signale pas lui-même : il ne cite le marqueur qu'en code.
    assert documentation.MARQUEUR in texte
    (tmp_path / "docs/modele").mkdir(parents=True)
    (tmp_path / "docs/modele/documentation.md").write_text(texte, encoding="utf-8")
    (tmp_path / "README.md").write_text("[d](docs/modele/documentation.md)\n", encoding="utf-8")
    assert documentation.gabarits_vides(tmp_path) == []


def test_documentation_md_avant_de_reecrire_un_readme():
    """Trois gestes avant de réécrire un README, relevés par les projets à leur passage à la
    `v0.9.0` : une ancre de l'ancien README citée ailleurs, un brief figé compris ; un fait que seul
    le README portait ; la section « Licence », dont le lien attend le `LICENSE` de la mise à jour.
    Sous le titre « Réécrire un README », que la piste des pièges d'une scission cite par son nom,
    dans la section « Le README », avant le titre suivant, hors des blocs de code."""
    hors_du_code = CLOTURE.sub("", lire(DOCUMENTATION))
    section = hors_du_code.split("\n## Le README\n", 1)[1].split("\n## ", 1)[0]
    titre = "\n### Réécrire un README\n"
    assert titre in section, titre.strip()
    sous_titre = section.split(titre, 1)[1]
    sous_titre = re.split(r"^#{1,6}[ \t]", sous_titre, maxsplit=1, flags=re.MULTILINE)[0]
    plat = " ".join(sous_titre.split())
    for phrase in (
        (
            "Avant de réécrire un README, chercher dans tout le dépôt `README.md#` et tout renvoi "
            "au README, ceux d'un texte figé compris."
        ),
        "Ce que seul le README porte se déplace ailleurs avant d'en être retiré.",
        (
            "Un projet de code né avant la `v0.9.0` met la section « Licence » dans la PR de mise "
            "à jour, qui apporte `LICENSE`."
        ),
    ):
        assert phrase in plat, phrase


def test_docstring_suit_documentation_md():
    """La docstring de `documentation.py` dit ce que dit le texte géré, dans les mêmes mots, sans
    l'ancien décompte des écarts ni la promesse d'un lancement local identique à la CI."""
    import documentation

    docstring = " ".join(documentation.__doc__.split())
    for fragment in DOCUMENTATION_ET_DOCSTRING:
        assert fragment in docstring, fragment
    for ancien in ("Quatre laissent passer", "comme en CI : un fichier qu'il ignore"):
        assert ancien not in docstring, ancien


def test_renvoi_au_plan_sait_mordre():
    """Le garde des renvois au plan voit les décisions du plan jusqu'à P19, et une tâche ou un
    constat en tête de phrase : un motif cassé laisserait passer les textes à vide."""
    for renvoi in (
        "P1", "P8", "P9", "P13", "P19", "tâche 3", "Tâche 3", "constat 2", "Constat 2",
        "Ruling 4", "ruling 4", "décision 2 du lot", "Review Focus",
    ):
        assert RENVOI_AU_PLAN.search(f"x {renvoi} y"), renvoi
    for sain in ("PR 12", "P20", "PR", "les tâches", "un constat", "M-0006", "LE-41", "P1a"):
        assert not RENVOI_AU_PLAN.search(f"x {sain} y"), sain


def test_methode_dit_qu_un_seme_absent_revient():
    """`copier update` sème à neuf un semé absent, retiré ou nouveau dans le modèle comme
    `LICENSE` : la méthode ne dit plus qu'il ne touche jamais un semé, et dit quoi faire du fichier
    non suivi qu'il laisse."""
    section = lire(METHODE).split("## Les fichiers gérés par le modèle", 1)[1].split("\n## ", 1)[0]
    plat = " ".join(section.split())
    assert (
        "Les fichiers **semés** sont créés une fois, puis appartiennent au projet : "
        "`copier update` ne touche plus un semé présent, mais sème à neuf un semé absent, qu'il "
        "ait été retiré ou qu'il soit nouveau dans le modèle, comme `LICENSE`. Un fichier non "
        "suivi (`??`) après la mise à jour s'indexe, ou se retire."
    ) in plat
    assert "`copier update` ne les touche plus" not in plat


def test_methode_nomme_documentation_md():
    section = lire(METHODE).split("## Le cycle d'un lot", 1)[1].split("\n## ", 1)[0]
    (point,) = [b for b in blocs(section) if b[0].startswith("5. ")]
    assert "`docs/modele/documentation.md`" in " ".join(point)
    assert "relit le README" in " ".join(" ".join(point).split())


def test_methode_dit_les_plans():
    """Le contrôle des plans (LE-53, LE-55, LE-56) : les trois sections d'un plan et la forme de
    leurs lignes, la revue du plan, les revues comme tâches du plan, le cas limite d'un outil, le
    mutant, et ce que la CI vérifie d'un plan ajouté ou modifié. Le tableau des garde-fous nomme le
    script ; le point 2 du cycle renvoie aux trois sections et à la revue du plan."""
    texte = _aplati(lire(METHODE))
    for fragment in (
        # les puces que `plan.py` admet, et le refus d'une section en double
        "n'admet que des puces `-` ou `*`",
        "deux sections du même titre refusent, et aucune des deux n'est lue",
        # la tête qui part, relue dans la PR de clôture, n'est pas un temps de « Revues »
        (
            "La relecture de la tête qui part, dans la PR de clôture, ne s'écrit pas dans "
            "« Revues » : c'est la ligne `Tête relue` de cette PR qui la porte"
        ),
        # l'étape ne passe pas `--depot` : un lieu d'un autre dépôt n'y est pas ouvert
        "chaque fichier du dépôt qu'il cite ouvert",
        "un lieu préfixé par un autre dépôt y reste « non vérifié », sans refus",
        # ce lieu se vérifie hors de la CI, par `--depot`, que la session passe elle-même
        "une session vérifie ce lieu en lançant `plan.py` avec `--depot <dépôt>=<clone>`",
        "`## Mécanismes annoncés`",
        "`## Outils et cas limites`",
        "`## Revues`",
        "`` - `<chemin>:<ligne>` — `<extrait>` — <comportement annoncé> ``",
        "`<chemin>:<ligne>-<fin>`",
        "`<dépôt>:<chemin>:<ligne>`",
        "`--depot <dépôt>=<clone>`",
        "`- <outil> — <cas limite que l'outil traite autrement> — <test qui l'exerce>`",
        "`- <revue> : Tâche N`",
        "`Tâche N` ou `Task N`",
        "la revue du plan",
        "chaque temps d'une revue est une tâche du plan, avant la clôture",
        "une correction cherche aussi la même croyance dans le reste du plan et dans la spec",
        "une revue se juge sur la tête qui part",
        "le cas limite que cet outil traite autrement",
        "hors du plan",
        "est éprouvé par un mutant",
        "un plan modifié se vérifie sans ouvrir les fichiers cités",
    ):
        assert fragment in texte, fragment
    assert "chaque fichier cité ouvert" not in texte
    assert "seule la revue du plan le relit" not in texte
    assert not RENVOI_AU_PLAN.search(texte)
    section = lire(METHODE).split("## Les garde-fous", 1)[1].split("\n## ", 1)[0]
    (ligne,) = [ligne for ligne in section.splitlines() if "`scripts/modele/plan.py`" in ligne]
    assert ligne.startswith("| ") and ligne.endswith(" |"), ligne
    assert "un lieu d'un autre dépôt restant « non vérifié », sans refus" in ligne, ligne
    cycle = lire(METHODE).split("## Le cycle d'un lot", 1)[1].split("\n## ", 1)[0]
    (point,) = [b for b in blocs(cycle) if b[0].startswith("2. ")]
    point = _aplati(" ".join(point))
    assert "trois sections" in point, point
    assert "la revue du plan" in point, point


def test_m0002_amende_par_le_lot_14():
    """La CI refuse la licence et la carte de la racine ; le `SessionStart` signale le gabarit
    resté vide. L'amendement est daté, sans numéro du plan."""
    brut = lire(M0002)
    texte = " ".join(brut.split())
    assert "- **Amendé** le 2026-11-06, avec le lot 14 :" in texte
    corps = " ".join(brut.split("## Décision", 1)[1].split("## Conséquences", 1)[0].split())
    assert "la licence et la carte de la racine" in corps
    assert "gabarit resté vide" in corps
    # Le hook lance `gh` : seul le contrôle du gabarit resté vide se passe de sous-processus.
    assert "Ce contrôle avertit, sans jamais refuser, et lit la copie sans lancer" in corps
    assert "Il avertit, sans jamais refuser" not in corps
    # La carte, comme le script la tient.
    assert "chaque fichier `.md` de la racine, sauf `README.md`, est lié" in corps
    assert "`README.md` et `CLAUDE.md` doivent exister" in corps
    assert not RENVOI_AU_PLAN.search(texte)
    (amendement,) = [
        b for b in blocs(brut) if b[0].startswith("- **Amendé** le 2026-11-06, avec le lot 14")
    ]
    longues = [ligne for ligne in amendement if len(ligne) > 100]
    assert not longues, longues
