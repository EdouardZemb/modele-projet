"""Tests de la porte de confidentialité. Aucun faux secret n'est écrit en clair : tout est construit."""

import shutil
import subprocess
import sys

import confidentialite as c
import pytest
from conftest import SCRIPTS, depot, git

CLE_AGE = "AGE-SECRET-KEY-1" + "Q" * 58
SCRIPT = SCRIPTS / "confidentialite.py"

ECHANTILLONS = {
    "adresse IP privée": "serveur 192.168" + ".1.20",
    "adresse Tailscale": "noeud 100.101" + ".2.3",
    "cible SSH": "ssh -p 22 " + "deploy" + "@" + "hote.exemple",
    "cible scp": "scp f " + "deploy" + "@" + "hote:/tmp/f",
    "cible scp à hôte pointé": "scp f " + "deploy" + "@" + "hote" + ".lan:/tmp/f",
    "adresse IPv6 Tailscale": "noeud fd7a" + ":115c" + ":a1e0::1",
    "nom MagicDNS Tailscale": "https://machine" + ".tailnet-ab12" + ".ts" + ".net/",
    "clé privée age": CLE_AGE,
    "clé privée PEM": "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----",
    "jeton GitHub": "ghp_" + "A" * 36,
    "JWT": "eyJ" + "a" * 10 + ".eyJ" + "b" * 10 + "." + "c" * 10,
    "jeton de tunnel Cloudflare": "eyJ" + "A" * 120,
    "adresse de ping Healthchecks": "hc-ping.com/" + "a" * 24,
}


def test_tous_les_motifs_ont_un_echantillon():
    assert {m.nom for m in c.MOTIFS_GENERIQUES} == set(ECHANTILLONS)


@pytest.mark.parametrize("nom", [m.nom for m in c.MOTIFS_GENERIQUES])
def test_motifs_generiques_detectent(nom):
    constats = c.examiner([("f.txt:1", ECHANTILLONS[nom])], c.MOTIFS_GENERIQUES)
    assert [x.motif for x in constats] == [nom]
    assert constats[0].emplacement == "f.txt:1"


@pytest.mark.parametrize(
    "texte",
    [
        "git@github.com:EdouardZemb/x.git",
        "noreply@anthropic.com",
        "corepack pnpm@10.34.2",
        "version 10.34.2",
        "@docs/modele/methode.md",
        "age1" + "q" * 58,
        "ssh -T git@github.com",
        "essai@example.com",
        "les noms *.ts" + ".net de Tailscale",
        "https://docs.ts" + ".network/x",
        "fd7a:1",
    ],
)
def test_faux_positifs_ecartes(texte):
    assert c.examiner([("f.txt:1", texte)], c.MOTIFS_GENERIQUES) == []


def test_motifs_prives_litteral_et_regex():
    motifs = c.charger_motifs_prives("# commentaire\nValeur-Privee\nre:^machine-\\d+$\n")
    assert len(motifs) == 2
    a = c.examiner([("f:1", "valeur-privee")], motifs)
    assert [x.motif for x in a] == ["motif privé n°1"]
    b = c.examiner([("f:1", "machine-42")], motifs)
    assert [x.motif for x in b] == ["motif privé n°2"]


def test_motifs_prives_crlf_et_regex_invalide():
    motifs = c.charger_motifs_prives("abc\r\n\r\nxyz\r\n")
    assert len(motifs) == 2
    with pytest.raises(ValueError) as e:
        c.charger_motifs_prives("re:(secret-inconnu")
    assert "secret-inconnu" not in str(e.value)
    assert "n°1" in str(e.value)


def test_source_motifs_prives(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MOTIFS_INTERDITS", raising=False)
    assert c.source_motifs_prives(None) is None
    defaut = tmp_path / ".config/modele-projet/motifs-interdits.txt"
    defaut.parent.mkdir(parents=True)
    defaut.write_bytes(b"\xef\xbb\xbfpremier\r\n")
    assert (
        c.source_motifs_prives(None) == "premier\n" or c.source_motifs_prives(None) == "premier\r\n"
    )
    assert len(c.charger_motifs_prives(c.source_motifs_prives(None))) == 1
    # le BOM ne corrompt pas le premier motif
    m = c.charger_motifs_prives(c.source_motifs_prives(None))
    assert c.examiner([("f:1", "premier")], m)
    monkeypatch.setenv("MOTIFS_INTERDITS", "deuxieme")
    assert c.source_motifs_prives(None) == "deuxieme"
    fichier = tmp_path / "m.txt"
    fichier.write_text("troisieme", encoding="utf-8")
    assert c.source_motifs_prives(str(fichier)) == "troisieme"


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


def test_sortie_ne_divulgue_rien(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "f.txt"
    f.write_text(f"a valeur-privee-xyz\n{CLE_AGE}\n", encoding="utf-8")
    r = lancer(["--fichiers", str(f)], env)
    assert r.returncode == 1
    sortie = r.stdout + r.stderr
    assert "valeur-privee-xyz" not in sortie
    assert CLE_AGE not in sortie
    assert "motif privé n°1" in sortie
    assert "clé privée age" in sortie


def test_regex_invalide_ne_divulgue_pas(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "re:(motif-secret-zzz"
    f = tmp_path / "f.txt"
    f.write_text("x\n", encoding="utf-8")
    r = lancer(["--fichiers", str(f)], env)
    assert r.returncode == 64
    assert "motif-secret-zzz" not in r.stdout + r.stderr


def test_exiger_prives_sans_liste(tmp_path, env_isole):
    f = tmp_path / "f.txt"
    f.write_text("rien\n", encoding="utf-8")
    assert lancer(["--exiger-prives", "--texte", str(f)], env_isole()).returncode == 64


def test_usage(env_isole):
    assert lancer([], env_isole()).returncode == 64
    assert lancer(["--index", "--texte", "x"], env_isole()).returncode == 64


def test_index_ne_regarde_que_les_ajouts(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "f.txt").write_text(CLE_AGE + "\n", encoding="utf-8")
    git(d, env, "add", "f.txt")
    git(d, env, "commit", "-qm", "init")
    (d / "f.txt").write_text("propre\n", encoding="utf-8")
    git(d, env, "add", "f.txt")
    assert lancer(["--index"], env, d).returncode == 0
    git(d, env, "commit", "-qm", "nettoyage")
    (d / "f.txt").write_text("propre\n" + CLE_AGE + "\n", encoding="utf-8")
    git(d, env, "add", "f.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "f.txt:2" in r.stderr
    assert CLE_AGE not in r.stdout + r.stderr


def test_index_examine_les_chemins(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = depot(tmp_path, env)
    (d / "nom-prive.txt").write_text("ok\n", encoding="utf-8")
    git(d, env, "add", "nom-prive.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "nom-prive" not in r.stdout + r.stderr


def test_diff_depuis_base(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a\n", encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    git(d, env, "switch", "-qc", "branche")
    (d / "b.txt").write_text(CLE_AGE + "\n", encoding="utf-8")
    git(d, env, "add", "b.txt")
    git(d, env, "commit", "-qm", "ajout")
    r = lancer(["--diff", "main"], env, d)
    assert r.returncode == 1
    assert "b.txt:1" in r.stderr
    r = lancer(["--diff", "0" * 40], env, d)
    assert r.returncode == 1
    assert "b.txt:1" in r.stderr


def test_fichier_binaire_signale_sans_refus(tmp_path, env_isole):
    f = tmp_path / "b.bin"
    f.write_bytes(b"\0" + CLE_AGE.encode())
    r = lancer(["--fichiers", str(f)], env_isole())
    assert r.returncode == 0
    assert f"confidentialité : fichier binaire non examiné : {f}" in r.stderr
    assert CLE_AGE not in r.stdout + r.stderr


def test_message(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "msg.txt"
    f.write_text("feat: truc valeur-privee-xyz\n", encoding="utf-8")
    assert lancer(["--message", str(f)], env).returncode == 1


@pytest.mark.parametrize(
    "commande",
    [
        "ssh -p 22 " + "u" + "@" + "machine",
        "ssh -i ~/.ssh/cle " + "u" + "@" + "machine",
        "ssh -J saut " + "u" + "@" + "machine",
        "ssh " + "Deploy" + "@" + "machine",
    ],
)
def test_cible_ssh_formes(commande):
    constats = c.examiner([("f:1", commande)], c.MOTIFS_GENERIQUES)
    assert [x.motif for x in constats] == ["cible SSH"]


def test_retour_chariot_isole_ne_cache_rien(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a" + chr(10), encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    git(d, env, "switch", "-qc", "branche")
    (d / "b.txt").write_bytes(b"abc" + bytes([13]) + CLE_AGE.encode() + bytes([10]))
    git(d, env, "add", "b.txt")
    assert lancer(["--index"], env, d).returncode == 1
    git(d, env, "commit", "-qm", "ajout")
    assert lancer(["--diff", "main"], env, d).returncode == 1


@pytest.mark.parametrize("base", ["", "  ", "-x", "nexistepas"])
def test_base_invalide(tmp_path, env_isole, base):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a" + chr(10), encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    assert lancer(["--diff", base], env, d).returncode == 64


def test_chemin_absent_ou_dossier(tmp_path, env_isole):
    r = lancer(["--fichiers", str(tmp_path / "n-existe-pas.txt")], env_isole())
    assert r.returncode == 64
    assert "n-existe-pas" not in r.stdout + r.stderr
    assert lancer(["--fichiers", str(tmp_path)], env_isole()).returncode == 64


# --- revue finale du lot 1 : binaires, UTF-16, textconv (I3, L.13, L.14), BOM en variable (m1) ---

IP = "hote 192.168" + ".1.20"


def utf16(texte, ordre="le"):
    bom = b"\xff\xfe" if ordre == "le" else b"\xfe\xff"
    return bom + texte.encode(f"utf-16-{ordre}")


def test_source_motifs_prives_bom_en_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MOTIFS_INTERDITS", "\ufeffmotif-essai\n")
    m = c.charger_motifs_prives(c.source_motifs_prives(None))
    assert [x.motif for x in c.examiner([("f:1", "un motif-essai ici")], m)] == ["motif privé n°1"]


def test_bom_en_variable_detecte(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "\ufeffmotif-essai"
    f = tmp_path / "f.txt"
    f.write_text("un motif-essai ici\n", encoding="utf-8")
    assert lancer(["--fichiers", str(f)], env).returncode == 1


@pytest.mark.parametrize("ordre", ["le", "be"])
def test_utf16_examine_fichiers(tmp_path, env_isole, ordre):
    f = tmp_path / "reseau.txt"
    f.write_bytes(utf16("entete\r\n" + IP + "\r\n", ordre))
    r = lancer(["--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert f"{f}:2 — adresse IP privée" in r.stderr
    assert "192.168" not in r.stdout + r.stderr


def _depot_avec_base(tmp_path, env):
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a\n", encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    git(d, env, "switch", "-qc", "branche")
    return d


def test_utf16_examine_index_et_diff(tmp_path, env_isole):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    (d / "reseau.txt").write_bytes(utf16(IP + "\n"))
    git(d, env, "add", "reseau.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "reseau.txt:1 — adresse IP privée" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    r = lancer(["--diff", "main"], env, d)
    assert r.returncode == 1
    assert "reseau.txt:1 — adresse IP privée" in r.stderr
    assert lancer(["--diff", "0" * 40], env, d).returncode == 1


def test_binaire_signale_index_et_diff(tmp_path, env_isole):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    (d / "b.dat").write_bytes(b"\0" + IP.encode())
    git(d, env, "add", "b.dat")
    r = lancer(["--index"], env, d)
    assert r.returncode == 0
    assert "confidentialité : fichier binaire non examiné : b.dat" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    r = lancer(["--diff", "main"], env, d)
    assert r.returncode == 0
    assert "fichier binaire non examiné : b.dat" in r.stderr


def test_binaire_au_chemin_prive_masque(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = _depot_avec_base(tmp_path, env)
    (d / "nom-prive.dat").write_bytes(b"\0x")
    git(d, env, "add", "nom-prive.dat")
    r = lancer(["--index"], env, d)
    assert "fichier binaire non examiné : <chemin masqué>" in r.stderr
    assert "nom-prive" not in r.stdout + r.stderr


def test_textconv_ne_vide_rien(tmp_path, env_isole):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    git(d, env, "config", "diff.vide.textconv", "sh -c ':'")
    (d / ".gitattributes").write_text("*.cfg diff=vide\n", encoding="utf-8")
    (d / "c.cfg").write_text(IP + "\n", encoding="utf-8")
    git(d, env, "add", ".gitattributes", "c.cfg")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "c.cfg:1 — adresse IP privée" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    assert lancer(["--diff", "main"], env, d).returncode == 1


@pytest.mark.parametrize("attribut", ["-diff", "binary"])
def test_texte_marque_binaire_examine(tmp_path, env_isole, attribut):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    (d / ".gitattributes").write_text(f"*.txt {attribut}\n", encoding="utf-8")
    (d / "note.txt").write_text("rien\n" + IP + "\n", encoding="utf-8")
    git(d, env, "add", ".gitattributes", "note.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "note.txt:2 — adresse IP privée" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    assert lancer(["--diff", "main"], env, d).returncode == 1


DIFF_PLUSIEURS_HUNKS = [
    "diff --git a/x y.txt b/x y.txt",
    "--- a/x y.txt",
    "+++ b/x y.txt",
    "@@ -1 +1 @@",
    "-ancien",
    "+nouveau",
    "@@ -10,0 +11,2 @@",
    "++double plus",
    "+deux",
    "@@ -20,3 +23 @@",
    "-a",
    "-b",
    "-c",
    "+seul",
    "diff --git a/z b/z",
    "--- a/z",
    "+++ /dev/null",
    "@@ -1 +0,0 @@",
    "-supprimé",
]


def test_lignes_ajoutees():
    diff = chr(10).join(DIFF_PLUSIEURS_HUNKS)
    assert list(c.lignes_ajoutees(diff)) == [
        ("x y.txt:1", "nouveau"),
        ("x y.txt:11", "+double plus"),
        ("x y.txt:12", "deux"),
        ("x y.txt:23", "seul"),
    ]


# --- revue finale du lot 1, section I : un dépôt de données avertit sans refuser ---

AVERTISSEMENT = "1 constat(s), dépôt de données : avertissement, pas de refus"


def lancer_porte(script, args, env, cwd=None):
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
        cwd=cwd,
    )


def test_depot_de_donnees_avertit(rendre, tmp_path, env_isole):
    script = rendre(nature="donnees") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text("rien\n" + IP + "\n", encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env_isole())
    assert r.returncode == 0, r.stderr
    assert f"{f}:2 — adresse IP privée" in r.stderr
    assert f"confidentialité : {AVERTISSEMENT}" in r.stderr
    assert "refus." not in r.stderr


def test_depot_de_code_refuse(rendre, tmp_path, env_isole):
    script = rendre(nature="code") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text(IP + "\n", encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert "confidentialité : 1 constat(s), refus." in r.stderr
    assert "avertissement" not in r.stderr


def test_depot_modele_sans_reglages_refuse(tmp_path, env_isole):
    assert not (SCRIPTS / "reglages.py").exists()
    f = tmp_path / "f.txt"
    f.write_text(IP + "\n", encoding="utf-8")
    r = lancer(["--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert "refus." in r.stderr


def test_depot_de_donnees_ne_divulgue_rien(rendre, tmp_path, env_isole):
    script = rendre(nature="donnees") / "scripts/modele/confidentialite.py"
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "f.txt"
    f.write_text(f"a valeur-privee-xyz\n{CLE_AGE}\n", encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env)
    assert r.returncode == 1  # la clé est un secret : elle refuse même en privé
    sortie = r.stdout + r.stderr
    assert "valeur-privee-xyz" not in sortie
    assert CLE_AGE not in sortie
    assert "motif privé n°1" in sortie
    assert "clé privée age" in sortie
    assert (
        "2 constat(s), refus : 1 secret(s), qui refusent même dans un dépôt de données." in sortie
    )


def test_depot_de_donnees_erreurs_toujours_64(rendre, tmp_path, env_isole):
    script = rendre(nature="donnees") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text(IP + "\n", encoding="utf-8")
    exige = lancer_porte(script, ["--exiger-prives", "--fichiers", str(f)], env_isole())
    assert exige.returncode == 64
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "re:(invalide"
    assert lancer_porte(script, ["--fichiers", str(f)], env).returncode == 64
    absent = str(tmp_path / "absent.txt")
    assert lancer_porte(script, ["--fichiers", absent], env_isole()).returncode == 64


# --- relecture de la vague, n1 : en CI, la visibilité réelle l'emporte sur la nature ---


@pytest.mark.parametrize(
    ("nature", "depot_prive", "attendu"),
    [
        ("donnees", "false", 1),
        ("donnees", "False", 1),
        ("donnees", "", 1),
        ("code", "true", 1),
        ("code", "false", 1),
    ],
)
def test_visibilite_reelle_en_ci(rendre, tmp_path, env_isole, nature, depot_prive, attendu):
    script = rendre(nature=nature) / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text(IP + chr(10), encoding="utf-8")
    env = {**env_isole(), "DEPOT_PRIVE": depot_prive}
    r = lancer_porte(script, ["--fichiers", str(f)], env)
    assert r.returncode == attendu, r.stderr
    assert ("avertissement" in r.stderr) is (attendu == 0)


# --- lot 11 : la nature se lit sur la branche par défaut, jamais dans la PR ---

NATURES_ILLISIBLES = "confidentialité : nature illisible sur la branche par défaut : régime code"


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ('NATURE = "donnees"\n', "donnees"),
        ('NATURE = "code"\n', "code"),
        ('VISIBILITE = "prive"\n', "donnees"),
        ('VISIBILITE = "prive"\nNATURE = "code"\n', "code"),
        ('VISIBILITE = "public"\n', "code"),
        (None, "code"),
        ("", "code"),
        ("NATURE = 'donnees'\n", "code"),
    ],
)
def test_nature_du_texte(texte, attendu):
    assert c.nature_du_texte(texte) == attendu


def depot_de_nature(tmp_path, env, sur_la_branche, dans_la_copie, branche="main"):
    """Un clone dont `origin/<branche>` porte `sur_la_branche` et la copie `dans_la_copie`."""
    origine = tmp_path / "origine.git"
    origine.mkdir()
    git(origine, env, "init", "-q", "--bare", "-b", branche)
    clone = tmp_path / "clone"
    clone.mkdir()
    git(clone, env, "init", "-q", "-b", branche)
    git(clone, env, "config", "core.autocrlf", "false")
    dossier = clone / "scripts/modele"
    dossier.mkdir(parents=True)
    shutil.copy(SCRIPT, dossier / "confidentialite.py")
    reglages = dossier / "reglages.py"
    reglages.write_text(f'NATURE = "{sur_la_branche}"\n', encoding="utf-8")
    git(clone, env, "add", "scripts/modele/confidentialite.py", "scripts/modele/reglages.py")
    git(clone, env, "commit", "-q", "-m", "chore: base")
    git(clone, env, "remote", "add", "origin", str(origine))
    git(clone, env, "push", "-q", "origin", branche)
    reglages.write_text(f'NATURE = "{dans_la_copie}"\n', encoding="utf-8")
    f = clone / "f.txt"
    f.write_text(IP + chr(10), encoding="utf-8")
    return clone, f


def porte_en_ci(clone, f, env, depot_prive="true", **variables):
    env = {**env, "DEPOT_PRIVE": depot_prive}
    env.pop("BRANCHE_DEFAUT", None)
    env.update(variables)
    script = clone / "scripts/modele/confidentialite.py"
    return lancer_porte(script, ["--fichiers", str(f)], env, clone)


def test_nature_en_ci_lue_sur_la_branche_par_defaut(tmp_path, env_isole):
    env = env_isole()
    clone, f = depot_de_nature(tmp_path, env, "donnees", "code")
    r = porte_en_ci(clone, f, env, BRANCHE_DEFAUT="main")
    assert r.returncode == 0, r.stderr
    assert "adresse IP privée" in r.stderr
    assert "dépôt de données : avertissement, pas de refus" in r.stderr


def test_une_pr_ne_change_pas_sa_nature(tmp_path, env_isole):
    env = env_isole()
    clone, f = depot_de_nature(tmp_path, env, "code", "donnees")
    r = porte_en_ci(clone, f, env, BRANCHE_DEFAUT="main")
    assert r.returncode == 1
    assert "constat(s), refus." in r.stderr
    assert "avertissement" not in r.stderr


def test_nature_lue_sur_une_branche_par_defaut_autre_que_main(tmp_path, env_isole):
    env = env_isole()
    clone, f = depot_de_nature(tmp_path, env, "donnees", "code", branche="principal")
    r = porte_en_ci(clone, f, env, BRANCHE_DEFAUT="principal")
    assert r.returncode == 0, r.stderr
    assert "dépôt de données : avertissement, pas de refus" in r.stderr


@pytest.mark.parametrize(
    "variables", [{}, {"BRANCHE_DEFAUT": "--x"}, {"BRANCHE_DEFAUT": "absente"}]
)
def test_nature_illisible_vaut_code(tmp_path, env_isole, variables):
    env = env_isole()
    clone, f = depot_de_nature(tmp_path, env, "donnees", "donnees")
    r = porte_en_ci(clone, f, env, **variables)
    assert r.returncode == 1
    assert NATURES_ILLISIBLES in r.stderr
    assert "constat(s), refus." in r.stderr


def test_depot_public_toujours_code(tmp_path, env_isole):
    env = env_isole()
    clone, f = depot_de_nature(tmp_path, env, "donnees", "donnees")
    r = porte_en_ci(clone, f, env, depot_prive="false", BRANCHE_DEFAUT="main")
    assert r.returncode == 1
    assert "avertissement" not in r.stderr
    assert NATURES_ILLISIBLES not in r.stderr


# --- relecture de la vague : les secrets refusent partout, ce qui identifie avertit en privé ---

SECRETS = {
    "clé privée age",
    "clé privée PEM",
    "jeton GitHub",
    "JWT",
    "jeton de tunnel Cloudflare",
    "adresse de ping Healthchecks",
}


def test_deux_familles():
    familles = {m.nom: m.famille for m in c.MOTIFS_GENERIQUES}
    assert set(familles.values()) == {c.SECRET, c.IDENTIFICATION}
    assert {nom for nom, f in familles.items() if f == c.SECRET} == SECRETS
    assert all(m.famille == c.IDENTIFICATION for m in c.charger_motifs_prives("a\nre:b+\n"))
    constat = c.examiner([("f:1", CLE_AGE)], c.MOTIFS_GENERIQUES)[0]
    assert constat.famille == c.SECRET


def test_depot_de_donnees_les_secrets_refusent(rendre, tmp_path, env_isole):
    """Famille « secret » : chaque motif refuse, même dans un dépôt privé."""
    script = rendre(nature="donnees") / "scripts/modele/confidentialite.py"
    noms = sorted(SECRETS)
    f = tmp_path / "f.txt"
    f.write_text("".join(ECHANTILLONS[nom] + chr(10) for nom in noms), encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env_isole())
    assert r.returncode == 1, r.stderr
    for i, nom in enumerate(noms, start=1):
        assert f"{f}:{i} — {nom}" in r.stderr
        assert ECHANTILLONS[nom] not in r.stdout + r.stderr
    assert f"{len(noms)} secret(s), qui refusent même dans un dépôt de données." in r.stderr


def test_depot_de_donnees_ce_qui_identifie_avertit(rendre, tmp_path, env_isole):
    """Famille « identification » : génériques et motifs privés avertissent dans un dépôt privé."""
    script = rendre(nature="donnees") / "scripts/modele/confidentialite.py"
    env = {**env_isole(), "MOTIFS_INTERDITS": "valeur-privee-xyz"}
    noms = sorted({m.nom for m in c.MOTIFS_GENERIQUES} - SECRETS)
    lignes = [ECHANTILLONS[nom] for nom in noms] + ["a valeur-privee-xyz"]
    f = tmp_path / "f.txt"
    f.write_text("".join(ligne + chr(10) for ligne in lignes), encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env)
    assert r.returncode == 0, r.stderr
    for i, nom in enumerate([*noms, "motif privé n°1"], start=1):
        assert f"{f}:{i} — {nom}" in r.stderr
    assert f"{len(lignes)} constat(s), dépôt de données : avertissement, pas de refus" in r.stderr
    assert "valeur-privee-xyz" not in r.stdout + r.stderr


# --- relecture de la vague, n2 : --public, et l'historique avant un passage en public ---


def test_option_public_refuse_dans_un_depot_de_donnees(rendre, tmp_path, env_isole):
    script = rendre(nature="donnees") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text(IP + chr(10), encoding="utf-8")
    assert lancer_porte(script, ["--fichiers", str(f)], env_isole()).returncode == 0
    r = lancer_porte(script, ["--public", "--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert "confidentialité : 1 constat(s), refus." in r.stderr


def test_historique_avant_un_passage_en_public(rendre, tmp_path, env_isole):
    """Un nom privé ajouté puis retiré, ou cité dans un message : l'arbre est propre, l'historique
    ne l'est pas. La procédure de methode.md le trouve, en mode public."""
    racine = rendre(nature="donnees")
    env = {**env_isole(), "MOTIFS_INTERDITS": "nom-du-serveur"}
    git(racine, env, "init", "-q", "-b", "main")
    git(racine, env, "config", "core.autocrlf", "false")
    git(racine, env, "add", "-A")
    git(racine, env, "commit", "-q", "-m", "chore: base")
    (racine / "note.txt").write_text("hote nom-du-serveur" + chr(10), encoding="utf-8")
    git(racine, env, "add", "note.txt")
    git(racine, env, "commit", "-q", "-m", "docs: note")
    git(racine, env, "rm", "-q", "note.txt")
    git(racine, env, "commit", "-q", "-m", "docs: retire la note")
    git(racine, env, "commit", "-q", "--allow-empty", "-m", "docs: vu sur nom-du-serveur")
    script = racine / "scripts/modele/confidentialite.py"
    suivis = git(racine, env, "ls-files").split()
    arbre = lancer_porte(
        script, ["--exiger-prives", "--public", "--fichiers", *suivis], env, racine
    )
    assert arbre.returncode == 0, arbre.stderr  # l'arbre seul ne voit rien

    historique = tmp_path / "historique.txt"
    sortie = git(
        racine, env, "log", "-p", "--all", "--no-textconv", "--no-ext-diff", "--format=%H%n%B"
    )
    historique.write_text(sortie, encoding="utf-8")
    texte = ["--exiger-prives", "--texte", str(historique)]
    assert lancer_porte(script, texte, env, racine).returncode == 0  # en privé : averti
    r = lancer_porte(script, ["--public", *texte], env, racine)
    assert r.returncode == 1
    assert r.stderr.count("— motif privé n°1") == 3  # ajout, retrait, message
    assert "nom-du-serveur" not in r.stdout + r.stderr


# --- l'historique (--historique, --acceptes) ---------------------------------------------------


def _commit(d, env, message, **fichiers):
    for nom, contenu in fichiers.items():
        chemin = d / nom.replace("__", ".")
        chemin.write_text(contenu, encoding="utf-8")
        git(d, env, "add", chemin.name)
    git(d, env, "commit", "-q", "--allow-empty", "-m", message)
    return git(d, env, "rev-parse", "HEAD").strip()


def _depot_historique(tmp_path, env_isole):
    """Deux commits : un constat dans a.txt, puis un constat dans le message."""
    env = env_isole()
    d = depot(tmp_path, env)
    sha1 = _commit(d, env, "feat: a", a__txt=IP + "\n")
    sha2 = _commit(d, env, "docs: vu " + IP)
    return env, d, sha1, sha2


def test_historique_attribue_commit_et_fichier(tmp_path, env_isole):
    env, d, sha1, sha2 = _depot_historique(tmp_path, env_isole)
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert f"{sha1}:a.txt:1 — adresse IP privée" in r.stderr
    assert f"{sha2}:message:1 — adresse IP privée" in r.stderr
    assert "192.168" not in r.stdout + r.stderr


def test_historique_ne_lit_que_les_ajouts(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    sha1 = _commit(d, env, "feat: a", a__txt=IP + "\n")
    _commit(d, env, "fix: retire", a__txt="propre\n")
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert r.stderr.count("— adresse IP privée") == 1
    assert f"{sha1}:a.txt:1" in r.stderr


def test_historique_ecarte_les_acceptes(tmp_path, env_isole):
    env, d, sha1, sha2 = _depot_historique(tmp_path, env_isole)
    liste = d.parent / "acceptes.txt"
    liste.write_text(f"{sha1} a.txt\n", encoding="utf-8")
    r = lancer(["--historique", "--acceptes", str(liste)], env, d)
    assert r.returncode == 1
    assert f"{sha1}:a.txt" not in r.stderr
    assert f"{sha2}:message:1" in r.stderr
    assert "1 constat(s) accepté(s), écarté(s)" in r.stderr
    liste.write_text(f"{sha1} a.txt\n{sha2} message\n", encoding="utf-8")
    r = lancer(["--historique", "--acceptes", str(liste)], env, d)
    assert r.returncode == 0, r.stderr
    assert "confidentialité : 2 constat(s) accepté(s), écarté(s)" in r.stderr


def test_historique_acceptes_absent_vaut_liste_vide(tmp_path, env_isole):
    env, d, sha1, _ = _depot_historique(tmp_path, env_isole)
    r = lancer(["--historique", "--acceptes", "n-existe-pas.txt"], env, d)
    assert r.returncode == 1
    assert f"{sha1}:a.txt:1" in r.stderr


def test_historique_en_depot_de_donnees(tmp_path, env_isole):
    env = env_isole()
    clone, _ = depot_de_nature(tmp_path, env, "donnees", "donnees")
    git(clone, env, "add", "f.txt")
    git(clone, env, "commit", "-q", "-m", "docs: vu " + IP)
    env = {**env, "DEPOT_PRIVE": "true", "BRANCHE_DEFAUT": "main"}
    r = lancer(["--historique"], env, clone)
    assert r.returncode == 0, r.stderr
    assert "confidentialité : dépôt de données : historique relu par gitleaks seul" in r.stderr
    assert "192.168" not in r.stdout + r.stderr
    assert "adresse IP privée" not in r.stderr


def test_historique_public_force_le_regime_code(tmp_path, env_isole):
    env = env_isole()
    clone, _ = depot_de_nature(tmp_path, env, "donnees", "donnees")
    git(clone, env, "add", "f.txt")
    git(clone, env, "commit", "-q", "-m", "docs: note")
    env = {**env, "DEPOT_PRIVE": "true", "BRANCHE_DEFAUT": "main"}
    r = lancer(["--historique", "--public"], env, clone)
    assert r.returncode == 1
    assert "f.txt:1 — adresse IP privée" in r.stderr


@pytest.mark.parametrize("fin", ["\n", "\r\n"])
def test_liste_des_acceptes_crlf_et_commentaires(tmp_path, env_isole, fin):
    env, d, sha1, sha2 = _depot_historique(tmp_path, env_isole)
    lignes = [
        "# les constats acceptés",
        "",
        f"{sha1.upper()} a.txt   ",
        f"{sha2} message  # vu en revue",
    ]
    liste = d.parent / "acceptes.txt"
    liste.write_bytes(fin.join(lignes).encode() + fin.encode())
    r = lancer(["--historique", "--acceptes", str(liste)], env, d)
    assert r.returncode == 0, r.stderr
    assert "2 constat(s) accepté(s), écarté(s)" in r.stderr


def test_liste_des_acceptes_invalide(tmp_path, env_isole):
    env, d, sha1, _ = _depot_historique(tmp_path, env_isole)
    liste = d.parent / "acceptes.txt"
    liste.write_text(f"# ok\n{sha1} a.txt\npasunsha a.txt\n", encoding="utf-8")
    r = lancer(["--historique", "--acceptes", str(liste)], env, d)
    assert r.returncode == 64
    assert "liste des constats acceptés invalide (ligne n°3)" in r.stderr
    assert "pasunsha" not in r.stdout + r.stderr


def test_historique_binaire_et_chemin_masques(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = depot(tmp_path, env)
    (d / "b.dat").write_bytes(b"\0x")
    (d / "nom-prive.txt").write_text(IP + "\n", encoding="utf-8")
    (d / "nom-prive.dat").write_bytes(b"\0y")
    git(d, env, "add", "b.dat", "nom-prive.txt", "nom-prive.dat")
    git(d, env, "commit", "-q", "-m", "feat: fichiers")
    sha = git(d, env, "rev-parse", "HEAD").strip()
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    sortie = r.stdout + r.stderr
    assert f"fichier binaire non examiné : {sha}:b.dat" in r.stderr
    assert f"fichier binaire non examiné : {sha}:<chemin masqué>" in r.stderr
    assert f"{sha}:<chemin masqué>:1 — adresse IP privée" in r.stderr
    assert "nom-prive" not in sortie
    assert "192.168" not in sortie


def test_historique_binaire_utf16_examine(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "r.txt").write_bytes(utf16(IP + "\n"))
    git(d, env, "add", "r.txt")
    git(d, env, "commit", "-q", "-m", "feat: r")
    sha = git(d, env, "rev-parse", "HEAD").strip()
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert f"{sha}:r.txt:1 — adresse IP privée" in r.stderr


def test_historique_nom_de_fichier_examine(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = depot(tmp_path, env)
    sha = _commit(d, env, "feat: x", **{"nom-prive__txt": "propre\n"})
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert f"{sha}:<chemin masqué>:0 — motif privé n°1" in r.stderr
    assert "nom-prive" not in r.stdout + r.stderr


def test_acceptes_hors_historique_refuse(tmp_path, env_isole):
    f = tmp_path / "t.txt"
    f.write_text("propre\n", encoding="utf-8")
    r = lancer(["--texte", str(f), "--acceptes", "y"], env_isole())
    assert r.returncode == 64
    assert "--acceptes ne vaut qu'avec --historique" in r.stderr


def test_historique_un_nul_tardif_ne_decale_rien(tmp_path, env_isole):
    """Git ne cherche un NUL que dans les 8000 premiers octets : un NUL plus loin reste du texte
    dans le diff. Il ne doit ni décaler l'attribution ni faire imprimer du contenu."""
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = depot(tmp_path, env)
    contenu = "a\n" * 4500 + "x\0nom-prive " + IP + "\n"
    (d / "gros.txt").write_bytes(contenu.encode())
    git(d, env, "add", "gros.txt")
    git(d, env, "commit", "-q", "-m", "feat: gros")
    sha2 = _commit(d, env, "docs: vu " + IP)
    r = lancer(["--historique"], env, d)
    sortie = r.stdout + r.stderr
    assert r.returncode == 1
    assert "nom-prive" not in sortie
    assert "192.168" not in sortie
    assert f"{sha2}:message:1 — adresse IP privée" in r.stderr


def test_historique_fusion_resolue_attribuee_a_la_fusion(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    _commit(d, env, "feat: base", a__txt="1\n")
    git(d, env, "switch", "-qc", "autre")
    _commit(d, env, "feat: autre", a__txt="autre\n")
    git(d, env, "switch", "-q", "main")
    _commit(d, env, "feat: main", a__txt="main\n")
    r = subprocess.run(
        ["git", "merge", "--no-ff", "autre"], cwd=d, env=env, capture_output=True, check=False
    )
    assert r.returncode != 0  # conflit voulu
    (d / "a.txt").write_text("resolu " + IP + "\n", encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-q", "-m", "Merge autre")
    sha = git(d, env, "rev-parse", "HEAD").strip()
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert f"{sha}:a.txt:" in r.stderr
    assert "192.168" not in r.stdout + r.stderr


def test_historique_nom_examine_a_l_ajout_seulement(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = depot(tmp_path, env)
    _commit(d, env, "feat: x", **{"nom-prive__txt": "un\n"})
    _commit(d, env, "feat: y", **{"nom-prive__txt": "deux\n"})
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert r.stderr.count("— motif privé n°1") == 1


def test_historique_lit_le_commit_racine_malgre_show_root(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    git(d, env, "config", "log.showRoot", "false")
    sha = _commit(d, env, "feat: racine", a__txt=IP + "\n")
    r = lancer(["--historique"], env, d)
    assert r.returncode == 1
    assert f"{sha}:a.txt:1 — adresse IP privée" in r.stderr
