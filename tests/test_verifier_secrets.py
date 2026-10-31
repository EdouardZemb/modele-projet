"""verifier_secrets.py : les secrets chiffrés par sops, contrôlés sans être déchiffrés."""

import os
import shutil
import subprocess
import sys

import pytest
import verifier_secrets
from conftest import REPONSES_SERVEUR, REPONSES_SERVEUR_CODE, SCRIPTS, exiger

SCRIPT = SCRIPTS / "verifier_secrets.py"
TEMOIN = "TEMOIN-NE-PAS-AFFICHER"
# Construits par concaténation : le dépôt est public, aucune adresse ne s'y écrit en entier.
DEST_A = "age1" + "a" * 58
DEST_B = "age1" + "b" * 58
BOM = chr(0xFEFF)


def enc(cles, destinataires, valeur=TEMOIN):
    lignes = [f"{c}=ENC[AES256_GCM,data:{valeur},iv:xx,tag:yy,type:str]" for c in cles]
    for i, d in enumerate(destinataires):
        lignes.append(f"sops_age__list_{i}__map_recipient={d}")
        lignes.append(
            f"sops_age__list_{i}__map_enc=-----BEGIN AGE ENCRYPTED FILE-----\\n{valeur}\\n-----END AGE ENCRYPTED FILE-----\\n"
        )
    lignes += [
        "sops_lastmodified=2026-10-18T10:00:00Z",
        f"sops_mac=ENC[AES256_GCM,data:{valeur}]",
        "sops_unencrypted_suffix=_unencrypted",
        "sops_version=3.13.3",
    ]
    return "\n".join(lignes) + "\n"


def monter(tmp_path, *, cles=("HC_SONDE", "TOKEN"), chiffre=None, destinataires=(DEST_A,), sops_yaml=(DEST_A,)):
    d = tmp_path / "depot"
    (d / "deploiement/secrets").mkdir(parents=True)
    if sops_yaml is not None:
        (d / ".sops.yaml").write_text("creation_rules:\n  - age: " + ",".join(sops_yaml) + "\n", encoding="utf-8")
    if cles is not None:
        (d / "deploiement/secrets/prod.cles").write_text("# clés\n\n" + "\n".join(cles) + "\n", encoding="utf-8")
    if chiffre is not False:
        contenu = chiffre if chiffre is not None else enc(cles or [], destinataires)
        (d / "deploiement/secrets/prod.env.enc").write_text(contenu, encoding="utf-8")
    return d


def lancer(racine):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(racine)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def sortie(r):
    return r.stdout + r.stderr


def test_conforme(tmp_path):
    r = lancer(monter(tmp_path))
    assert r.returncode == 0, sortie(r)


def test_cle_manquante(tmp_path):
    r = lancer(monter(tmp_path, chiffre=enc(["TOKEN"], [DEST_A])))
    assert r.returncode == 1
    assert "HC_SONDE" in sortie(r)


def test_cle_en_trop(tmp_path):
    r = lancer(monter(tmp_path, chiffre=enc(["HC_SONDE", "TOKEN", "EXTRA"], [DEST_A])))
    assert r.returncode == 1
    assert "EXTRA" in sortie(r)


def test_autre_destinataire(tmp_path):
    r = lancer(monter(tmp_path, destinataires=(DEST_A, DEST_B)))
    assert r.returncode == 1


def test_destinataire_manquant(tmp_path):
    r = lancer(monter(tmp_path, sops_yaml=(DEST_A, DEST_B)))
    assert r.returncode == 1


def test_cles_exigees_par_la_mecanique(tmp_path):
    d = monter(tmp_path, cles=("TOKEN",))
    exiges = {"deploiement/secrets/prod.cles": ["HC_SONDE"]}
    refus = [c for c in verifier_secrets.verifier(d, exiges) if c.niveau == "refus"]
    assert refus
    assert "HC_SONDE" in refus[0].message
    assert verifier_secrets.main(["--racine", str(d)], exiges) == 1
    assert verifier_secrets.main(["--racine", str(d)], {}) == 0


def test_enc_sans_cles(tmp_path):
    r = lancer(monter(tmp_path, cles=None, chiffre=enc(["TOKEN"], [DEST_A])))
    assert r.returncode == 1


def test_cles_sans_enc_avertit(tmp_path):
    r = lancer(monter(tmp_path, chiffre=False))
    assert r.returncode == 0
    assert "avertissement" in sortie(r)


@pytest.mark.parametrize(("mode", "avertit"), [("deux", False), ("un", True), (None, True)])
def test_cles_sans_enc_selon_le_mode_des_donnees(tmp_path, mode, avertit):
    """À deux dépôts (MODE_DONNEES de deploiement/lib.sh), les .enc vivent dans le dépôt de
    données : le dépôt de code, qui n'a que ses .cles, ne dit rien d'un .enc absent, à chaque CI.
    À un dépôt, ou sans lib.sh, l'avertissement reste. Les autres contrôles ne changent pas."""
    d = monter(tmp_path, chiffre=False)
    if mode is not None:
        (d / "deploiement/lib.sh").write_text(f'#!/usr/bin/env bash\nMODE_DONNEES="{mode}"\n', encoding="utf-8")
    r = lancer(d)
    assert r.returncode == 0, sortie(r)
    assert ("avertissement : deploiement/secrets/prod.cles : pas de prod.env.enc" in sortie(r)) is avertit
    # une clé exigée par la mécanique manque : le refus reste, à deux dépôts comme ailleurs
    constats = verifier_secrets.verifier(d, {"deploiement/secrets/prod.cles": ["HC_ABSENTE"]})
    assert [(c.niveau, c.chemin) for c in constats if c.niveau == "refus"] == [
        ("refus", "deploiement/secrets/prod.cles")
    ]


@pytest.mark.parametrize(
    ("reponses", "avertit"),
    [(REPONSES_SERVEUR_CODE, False), (REPONSES_SERVEUR, True)],
    ids=["deux-depots", "un-depot"],
)
def test_cles_sans_enc_dans_un_rendu(rendre, reponses, avertit):
    """Le contrôle du socle sur un projet `serveur` rendu, sans secrets posés : le dépôt de code à
    deux dépôts se tait, le projet à un dépôt avertit."""
    r = lancer_dans(rendre(**reponses))
    assert r.returncode == 0, sortie(r)
    assert ("pas encore posés" in sortie(r)) is avertit
    assert "avertissement" in sortie(r) or not avertit


def test_sans_sops_yaml(tmp_path):
    r = lancer(monter(tmp_path, sops_yaml=None))
    assert r.returncode == 1


def test_ligne_illisible(tmp_path):
    contenu = enc(["HC_SONDE", "TOKEN"], [DEST_A]) + f"ligne sans egal {TEMOIN}\n"
    numero = contenu.count("\n")
    r = lancer(monter(tmp_path, chiffre=contenu))
    assert r.returncode == 1
    assert f":{numero}" in sortie(r)
    assert TEMOIN not in sortie(r)


def test_aucun_fichier(tmp_path):
    r = lancer(tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_ne_divulgue_rien(tmp_path):
    cas = [
        monter(tmp_path / "a"),
        monter(tmp_path / "b", chiffre=enc(["TOKEN"], [DEST_A, DEST_B])),
        monter(tmp_path / "c", chiffre=enc(["HC_SONDE", "TOKEN", "EXTRA"], [DEST_A]) + f"{TEMOIN}\n"),
        monter(tmp_path / "d", cles=None, chiffre=enc(["TOKEN"], [DEST_A])),
        monter(tmp_path / "e", sops_yaml=None),
        monter(tmp_path / "f", chiffre=False),
        monter(tmp_path / "g", chiffre=f"#ENC[AES256_GCM,data:{TEMOIN},iv:xx,tag:yy,type:comment]\n" + enc(["HC_SONDE", "TOKEN"], [DEST_A])),
        monter(tmp_path / "h", chiffre=f"#ENC[AES256_GCM,data:{TEMOIN}" + enc(["HC_SONDE", "TOKEN"], [DEST_A])),
        monter(tmp_path / "i", chiffre=enc(["TOKEN"], [DEST_A]) + f"HC_SONDE={TEMOIN}\n"),
    ]
    for d in cas:
        assert TEMOIN not in sortie(lancer(d))


def test_commentaire_chiffre_ignore(tmp_path):
    commentaire = f"#ENC[AES256_GCM,data:{TEMOIN},iv:xx,tag:yy,type:comment]\n"
    r = lancer(monter(tmp_path, chiffre=commentaire + enc(["HC_SONDE", "TOKEN"], [DEST_A])))
    assert r.returncode == 0, sortie(r)


def test_valeur_en_clair_refusee(tmp_path):
    r = lancer(monter(tmp_path, chiffre=enc(["TOKEN"], [DEST_A]) + f"HC_SONDE={TEMOIN}\n"))
    assert r.returncode == 1
    assert "valeur non chiffrée : HC_SONDE" in sortie(r)
    assert TEMOIN not in sortie(r)


def test_bom_dans_cles_et_enc(tmp_path):
    d = monter(tmp_path)
    cles = d / "deploiement/secrets/prod.cles"
    cles.write_text(BOM + cles.read_text(encoding="utf-8"), encoding="utf-8")
    chiffre = d / "deploiement/secrets/prod.env.enc"
    chiffre.write_text(BOM + chiffre.read_text(encoding="utf-8"), encoding="utf-8")
    r = lancer(d)
    assert r.returncode == 0, sortie(r)


@pytest.mark.parametrize(
    ("fichier", "nom"),
    [
        ("deploiement/secrets/prod.cles", "deploiement/secrets/prod.cles:2"),
        ("deploiement/secrets/prod.env.enc", "deploiement/secrets/prod.env.enc:2"),
        (".sops.yaml", ".sops.yaml:2"),
    ],
)
def test_fichier_non_utf8_refuse(tmp_path, fichier, nom):
    # Un octet qui n'est pas de l'UTF-8 (ici, un BOM UTF-16 en ligne 2) : un refus qui nomme le
    # fichier et la ligne, pas une trace Python.
    d = monter(tmp_path)
    chemin = d / fichier
    chemin.write_bytes(b"# ligne 1\n\xff\xfe\n" + chemin.read_bytes())
    r = lancer(d)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {nom} : fichier non UTF-8" in sortie(r)
    assert "Traceback" not in sortie(r)


def test_fichier_non_utf8_apres_bom(tmp_path):
    # Le numéro de ligne compte depuis le début du fichier, BOM UTF-8 compris.
    d = monter(tmp_path)
    cles = d / "deploiement/secrets/prod.cles"
    cles.write_bytes(b"\xef\xbb\xbfHC_SONDE\nTOKEN\n\xff\n")
    r = lancer(d)
    assert r.returncode == 1, sortie(r)
    assert "refus : deploiement/secrets/prod.cles:3 : fichier non UTF-8" in sortie(r)


def test_usage():
    r = subprocess.run([sys.executable, str(SCRIPT), "--bidon"], check=False, capture_output=True, text=True)
    assert r.returncode == 64


def test_cles_doublon_et_forme(tmp_path):
    d = monter(tmp_path / "z", cles=("A", "A"), chiffre=enc(["A"], [DEST_A]))
    assert any(c.niveau == "refus" for c in verifier_secrets.verifier(d, {}))
    d = monter(tmp_path / "y", cles=("minuscule",), chiffre=enc(["minuscule"], [DEST_A]))
    assert any(c.niveau == "refus" for c in verifier_secrets.verifier(d, {}))


def test_vrai_fichier_sops(tmp_path):
    exiger("sops", "age-keygen")
    cle = tmp_path / "cle.txt"
    subprocess.run(["age-keygen", "-o", str(cle)], check=True, capture_output=True)
    publique = next(
        ligne.split(":", 1)[1].strip()
        for ligne in cle.read_text(encoding="utf-8").splitlines()
        if ligne.startswith("# public key:")
    )
    d = tmp_path / "depot"
    (d / "deploiement/secrets").mkdir(parents=True)
    (d / ".sops.yaml").write_text(
        "creation_rules:\n"
        "  - path_regex: ^deploiement[\\\\/]secrets[\\\\/][a-z]+\\.env\\.enc$\n"
        f"    age: {publique}\n",
        encoding="utf-8",
    )
    (d / "deploiement/secrets/prod.cles").write_text("HC_SONDE\nTOKEN\n", encoding="utf-8")
    env = {**os.environ, "SOPS_AGE_KEY_FILE": str(cle)}
    r = subprocess.run(
        [
            "sops", "encrypt", "--filename-override", "deploiement/secrets/prod.env.enc",
            "--input-type", "dotenv", "--output-type", "dotenv",
            "--output", "deploiement/secrets/prod.env.enc",
        ],
        cwd=d,
        env=env,
        input="# commentaire\nHC_SONDE=valeur-un\nTOKEN=valeur-deux\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stderr
    cles, destinataires = verifier_secrets.lire_chiffre(d / "deploiement/secrets/prod.env.enc")
    assert cles == {"HC_SONDE", "TOKEN"}
    assert destinataires == {publique}
    assert verifier_secrets.main(["--racine", str(d)], {}) == 0


# --- Le dépôt de données d'un projet `serveur` (M-0006, § 8) -------------------------------------
# Ses secrets chiffrés sont dans secrets/, la liste de leurs clés dans le dépôt de code
# (deploiement/secrets/<env>.cles), que modele-donnees.yml clone dans code/ ; ses destinataires,
# dans .sops.yaml et cles/*.pub.

MESSAGE_DONNEES = "secrets : contrôlés par modele-donnees.yml, contre le .cles du dépôt de code"


def monter_donnees(
    tmp_path, *, cles_code=None, chiffres=None, pubs=None, sops_yaml=(DEST_A, DEST_B)
):
    """Un dépôt de données et son dépôt de code dans code/. `cles_code` : {env: clés} du code ;
    `chiffres` : {env: (clés, destinataires)} de secrets/ ; `pubs` : {nom: texte} de cles/."""
    d = tmp_path / "donnees"
    (d / "secrets").mkdir(parents=True)
    (d / "cles").mkdir()
    code = d / "code/deploiement/secrets"
    code.mkdir(parents=True)
    if sops_yaml is not None:
        (d / ".sops.yaml").write_text(
            "creation_rules:\n  - path_regex: ^secrets[\\\\/][a-z]+\\.env\\.enc$\n    age: >-\n"
            "      " + ",".join(sops_yaml) + "\n",
            encoding="utf-8",
        )
    if pubs is None:
        pubs = {"serveur.pub": DEST_A + "\n", "hors-ligne.pub": DEST_B + "\n"}
    for nom, texte in pubs.items():
        (d / "cles" / nom).write_text(texte, encoding="utf-8")
    if cles_code is None:
        cles_code = {"prod": ("HC_SONDE", "TOKEN"), "staging": ("HC_SONDE",)}
    for env, cles in cles_code.items():
        (code / f"{env}.cles").write_text("\n".join(cles) + "\n", encoding="utf-8")
    if chiffres is None:
        chiffres = {"prod": (("HC_SONDE", "TOKEN"), (DEST_A, DEST_B))}
    for env, (cles, destinataires) in chiffres.items():
        (d / "secrets" / f"{env}.env.enc").write_text(enc(cles, destinataires), encoding="utf-8")
    return d, code


def lancer_cles(racine, cles):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(racine), "--cles", str(cles)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_cles_du_depot_de_code(tmp_path):
    d, code = monter_donnees(tmp_path)
    # un .cles laissé dans le dépôt de données ne compte pas : la liste est celle du code
    (d / "secrets/prod.cles").write_text("AUTRE\n", encoding="utf-8")
    r = lancer_cles(d, code)
    assert r.returncode == 0, sortie(r)
    # staging.cles, du code, n'a pas encore son .enc ; le .cles du dépôt de données n'est pas lu
    attendu = (
        "avertissement : code/deploiement/secrets/staging.cles : "
        "pas de staging.env.enc : secrets pas encore posés"
    )
    assert sortie(r).splitlines() == [attendu]


def test_cles_du_depot_de_code_comparees(tmp_path):
    # une clé du code que le chiffré n'a pas, une clé chiffrée que le code ne déclare plus
    d, code = monter_donnees(tmp_path, cles_code={"prod": ("HC_SONDE", "TOKEN", "NOUVELLE")})
    r = lancer_cles(d, code)
    assert r.returncode == 1
    assert "refus : secrets/prod.env.enc : clés manquantes : NOUVELLE" in sortie(r)
    d, code = monter_donnees(tmp_path / "b", cles_code={"prod": ("HC_SONDE",)})
    r = lancer_cles(d, code)
    assert r.returncode == 1
    assert "refus : secrets/prod.env.enc : clés en trop : TOKEN" in sortie(r)
    # un chiffré sans .cles dans le dépôt de code
    d, code = monter_donnees(tmp_path / "c", cles_code={})
    r = lancer_cles(d, code)
    assert r.returncode == 1
    assert "refus : secrets/prod.env.enc : pas de code/deploiement/secrets/prod.cles" in sortie(r)


def test_destinataires_compares_aux_cles_du_parc(tmp_path):
    """Les destinataires de .sops.yaml sont exactement les clés de cles/*.pub ; un écart se dit par
    le fichier et la clé abrégée, jamais la clé entière."""
    dest_c = "age1" + "c" * 58
    cas = [
        # une clé du parc que .sops.yaml n'a pas, et l'inverse
        (
            {"pubs": {"serveur.pub": DEST_A + "\n", "hors-ligne.pub": dest_c + "\n"}},
            [
                "refus : cles/hors-ligne.pub : clé absente de .sops.yaml : age1cccc…",
                "refus : .sops.yaml : destinataire sans clé dans cles/ : age1bbbb…",
            ],
        ),
        # un destinataire de .sops.yaml sans sa clé dans cles/
        (
            {"pubs": {"serveur.pub": DEST_A + "\n"}},
            ["refus : .sops.yaml : destinataire sans clé dans cles/ : age1bbbb…"],
        ),
        # un fichier de cles/ sans clé age
        (
            {
                "pubs": {
                    "serveur.pub": DEST_A + "\n",
                    "hors-ligne.pub": DEST_B + "\n",
                    "vide.pub": "\n",
                }
            },
            ["refus : cles/vide.pub : aucune clé age"],
        ),
    ]
    for i, (options, attendus) in enumerate(cas):
        d, code = monter_donnees(tmp_path / str(i), **options)
        r = lancer_cles(d, code)
        assert r.returncode == 1, (options, sortie(r))
        for attendu in attendus:
            assert attendu in sortie(r).splitlines(), (attendu, sortie(r))
        for cle in (DEST_A, DEST_B, dest_c):
            assert cle not in sortie(r)
    # sans .sops.yaml : rien ne se compare
    d, code = monter_donnees(tmp_path / "sans", sops_yaml=None)
    r = lancer_cles(d, code)
    assert r.returncode == 1
    absent = "refus : .sops.yaml : absent : les destinataires ne peuvent pas être contrôlés"
    assert absent in sortie(r)
    # sans aucun secret encore chiffré, la comparaison a lieu quand même
    d, code = monter_donnees(tmp_path / "neuf", chiffres={}, pubs={"serveur.pub": DEST_A + "\n"})
    r = lancer_cles(d, code)
    assert r.returncode == 1
    assert "refus : .sops.yaml : destinataire sans clé dans cles/ : age1bbbb…" in sortie(r)


def test_cles_seuls_les_secrets_de_la_racine(tmp_path):
    """Avec --cles, seuls les secrets/*.env.enc de la racine du dépôt de données sont lus : ni un
    .enc du clone code/, ni un .enc d'ailleurs dans le dépôt."""
    d, code = monter_donnees(tmp_path)
    for ailleurs in (
        "code/deploiement/secrets/prod.env.enc",
        "code/secrets/prod.env.enc",
        "secrets/sous/prod.env.enc",
        "config/autre.env.enc",
    ):
        (d / ailleurs).parent.mkdir(parents=True, exist_ok=True)
        (d / ailleurs).write_text("TOKEN=en clair\n", encoding="utf-8")
    r = lancer_cles(d, code)
    assert r.returncode == 0, sortie(r)
    attendu = (
        "avertissement : code/deploiement/secrets/staging.cles : "
        "pas de staging.env.enc : secrets pas encore posés"
    )
    assert sortie(r).splitlines() == [attendu]
    # un .enc du code au nom d'un .cles ne fait pas croire que ses secrets sont posés
    (d / "code/deploiement/secrets/staging.env.enc").write_text(
        enc(("HC_SONDE",), (DEST_A, DEST_B)), encoding="utf-8"
    )
    r = lancer_cles(d, code)
    assert r.returncode == 0, sortie(r)
    assert sortie(r).splitlines() == [attendu]


def test_cles_absent_usage(tmp_path):
    d, _code = monter_donnees(tmp_path)
    r = lancer_cles(d, tmp_path / "absent")
    assert r.returncode == 64
    assert "Traceback" not in sortie(r)


MODELE_DONNEES_YML = ".github/workflows/modele-donnees.yml"


def copier_avec_reglages(tmp_path, reglages, *, workflow=True):
    """Le dépôt de données, le script dans son scripts/modele/, à côté d'un reglages.py, comme dans
    un projet rendu : il y lit DEPOT_CODE et SECRETS_EXIGES. secrets/prod.env.enc n'a pas de .cles
    voisin : le contrôle ordinaire le refuse. `workflow` : le dépôt porte modele-donnees.yml, comme
    le dépôt de données d'un projet `serveur`."""
    d, code = monter_donnees(tmp_path)
    poser_le_script(d, reglages, workflow=workflow)
    return d, code


def poser_le_script(d, reglages, *, workflow):
    modele = d / "scripts/modele"
    modele.mkdir(parents=True)
    shutil.copy(SCRIPT, modele / SCRIPT.name)
    (modele / "reglages.py").write_text(reglages, encoding="utf-8")
    if workflow:
        (d / MODELE_DONNEES_YML).parent.mkdir(parents=True)
        (d / MODELE_DONNEES_YML).write_text("name: donnees\n", encoding="utf-8")


def lancer_dans(d, *arguments):
    return subprocess.run(
        [sys.executable, "scripts/modele/verifier_secrets.py", *arguments],
        cwd=d,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_depot_de_donnees_controle_par_modele_donnees(tmp_path):
    """Le socle lance le script sans argument dans tout dépôt : dans un dépôt de données, la liste des
    clés est dans le dépôt de code, et modele-donnees.yml la contrôle."""
    reglages = 'NATURE = "donnees"\nDEPOT_CODE = "essai"\nSECRETS_EXIGES = {}\n'
    d, code = copier_avec_reglages(tmp_path, reglages)
    r = lancer_dans(d)
    assert r.returncode == 0, sortie(r)
    assert r.stdout == MESSAGE_DONNEES + "\n"
    assert r.stderr == ""
    # avec --cles, le contrôle a lieu
    r = lancer_dans(d, "--cles", "code/deploiement/secrets")
    assert r.returncode == 0, sortie(r)
    assert MESSAGE_DONNEES not in sortie(r)
    (code / "prod.cles").write_text("HC_SONDE\n", encoding="utf-8")
    r = lancer_dans(d, "--cles", "code/deploiement/secrets")
    assert r.returncode == 1
    assert "refus : secrets/prod.env.enc : clés en trop : TOKEN" in sortie(r)


def test_depot_de_donnees_sans_modele_donnees_controle_ordinaire(tmp_path):
    """Le dépôt de données d'un projet sans serveur porte DEPOT_CODE, mais pas modele-donnees.yml :
    rien d'autre ne contrôlerait ses secrets, le contrôle ordinaire tourne."""
    reglages = 'NATURE = "donnees"\nDEPOT_CODE = "essai"\nSECRETS_EXIGES = {}\n'
    # sans fichier chiffré, ce qu'il est d'ordinaire : rien à dire
    d = tmp_path / "sans-serveur"
    d.mkdir()
    poser_le_script(d, reglages, workflow=False)
    r = lancer_dans(d)
    assert r.returncode == 0, sortie(r)
    assert sortie(r) == ""
    # un .enc s'y contrôle comme ailleurs : sans son .cles voisin, il refuse
    d, _code = copier_avec_reglages(tmp_path / "avec-enc", reglages, workflow=False)
    r = lancer_dans(d)
    assert r.returncode == 1
    assert MESSAGE_DONNEES not in sortie(r)
    assert "refus : secrets/prod.env.enc : pas de secrets/prod.cles" in sortie(r)


def test_sans_depot_code_controle_ordinaire(tmp_path):
    """Sans DEPOT_CODE, le contrôle ordinaire : le .enc de secrets/ n'a pas de .cles voisin."""
    d, _code = copier_avec_reglages(tmp_path, 'NATURE = "code"\nSECRETS_EXIGES = {}\n')
    r = lancer_dans(d)
    assert r.returncode == 1
    assert MESSAGE_DONNEES not in sortie(r)
    assert "refus : secrets/prod.env.enc : pas de secrets/prod.cles" in sortie(r)
