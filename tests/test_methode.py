"""Les fichiers gérés de la méthode : méthode, ADR hérités, /consigner, modèles."""

import re

import pytest
import yaml
from conftest import RACINE, REGISTRE_ENTETE, REPONSES_SERVEUR, REPONSES_SERVEUR_CODE

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
    # Tout dépôt nommé est refusé, même celui de la session : on fusionne depuis le clone.
    assert "toute fusion qui nomme un dépôt (`-R`, `--repo`, `GH_REPO`, une adresse de PR)" in texte
    assert "`gh pr merge <n>`, depuis le clone" in texte
    assert "en mode `edouard`, toute fusion est refusée de toute façon" in texte


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
    ):
        assert attendu in texte, attendu


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
    for titre in (
        "## Ce que fait cette PR",
        "## Vérifications",
        "## Reste ouvert",
        "## Registre",
        "## Pour un fix : cause racine et prévention",
    ):
        assert titre in texte.splitlines(), titre


def test_modele_de_pr_ferme_l_issue():
    # GitHub ne ferme l'issue à la fusion que sur un mot-clé anglais (LE-30).
    texte = lire(TEMPLATE / ".github/pull_request_template.md")
    assert "« Closes #n »" in texte
    assert "Ferme #" not in texte


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
    ):
        assert fragment in section, fragment
    assert "gitleaks sur tout l'historique ;" not in section
    assert "quatre étapes obligatoires" not in section
    assert "VISIBILITE" not in lire(METHODE)
    assert "(voir plus bas)" in section
    assert "(voir plus haut)" not in section
    assert "visibilite" not in lire(METHODE)


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
    assert "refus d'un fichier du modèle que le `.gitignore` du projet masque" in ligne
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
    assert ("instantané de /donnees" in texte) is False


def test_m0002_amende():
    texte = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    assert "le contrôle de dérive en tient compte" not in texte
    assert "le garde de Claude est alors la seule serrure côté agent" in texte
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
    assert dates == ["2026-10-17", "2026-10-18", "2026-10-27", "2026-10-29", "2026-10-29"]
    assert (
        "- **Amendé** le 2026-10-29, avec le lot 11 : la porte suit la nature du dépôt, de code ou "
        "de données (M-0006)"
    ) in texte
    # le remède des masqués, tel que masques.py le prescrit
    texte = " ".join(texte.split())
    assert "ou `!<dossier>/` quand un dossier parent est exclu" in texte
    assert "le masque d'un fichier de secrets ne se lève jamais" in texte


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
# Les numéros du plan ne vivent que dans le plan, qui disparaît à la clôture du lot.
RENVOI_AU_PLAN = re.compile(r"\b(?:Ruling|ruling) \d|\bP[1-8]\b|\btâche \d|\bdécision \d du lot")


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
        "une commande déclarée sans son dossier d'exemple refuse",
        "un dossier d'exemple sans sa commande n'est pas vérifié, et le journal le dit",
        "**Un projet qui ne déclare ni l'une ni l'autre ne voit aucun changement**",
    ):
        assert fragment in texte, fragment
    # La route de santé du § 2 annonce le champ, et la CI prouve la clause de l'ENTRYPOINT pour
    # les deux commandes de l'instance, qu'elle lance par docker run.
    assert "le champ `configuration` (§ 6)" in texte
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
        # une commande ajoutée ou retirée
        "Dans l'intervalle, la CI des données refuse",
        # le retour arrière et ses deux cas de transition
        "ne monte ni ne vérifie rien, même si `projet.env` déclare une commande",
        "pas de retour arrière après une version qui retire ses commandes",
        "forme un couple nouveau : l'ancienne image et le commit de données en service",
        # les clones des données
        "« clone des données absent »",
        "seule l'absence du signal ok avertit",
        "« clone des données modifié »",
        "« mise à jour du clone des données impossible »",
        # le ménage des instantanés
        "le ménage des instantanés",
    ):
        assert fragment in texte, fragment
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
    ):
        assert fragment in texte, fragment
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
        "un fichier nommé `*.enc` ou `.sops.yaml`, et un `*.pub` dans un dossier `cles/`, à toute profondeur",
        "une clé publique `age` (`age1…`), où qu'elle soit écrite",
        "Un gabarit `….jinja` n'est pas le fichier qu'il rend",
        "`.github/constats-acceptes.txt`",
        "`donnees-AAAA.MM.JJ.n`",
    ):
        assert fragment in texte, fragment
    assert not RENVOI_AU_PLAN.search(texte)


def test_m0006_dit_le_choix_des_deux_modes():
    """M-0006 : son § 6 dit le choix fait (les deux modes sont gardés) ; son § 3 dit la règle des
    chemins telle que la porte la tient (le premier segment)."""
    texte = " ".join(lire(DECISIONS / "M-0006-code-et-donnees.md").split())
    assert AMENDE_LOT_12 in texte
    assert "Le lot de la chaîne a gardé les deux modes" in texte
    assert "`instance/config/` et `instance/contenu/`" in texte
    assert "tout `contenu/`, à n'importe quelle profondeur" not in texte
    assert (
        "tout fichier sous un dossier de premier niveau `instance/`, `config/` ou `contenu/`"
        in texte
    )
    assert not RENVOI_AU_PLAN.search(texte)
