"""secrets.ps1 : refaire sur le poste un fichier de secrets chiffré par sops, valeurs saisies en masqué."""

import os
import shutil
import subprocess

import pytest
from conftest import SCRIPTS, depot, exiger, git

SCRIPT = SCRIPTS / "secrets.ps1"
WINDOWS = os.name == "nt"

# Les valeurs de l'essai sont fabriquées ; elles couvrent tous les caractères admis.
VALEUR_1 = "Ab0+/=_-.:,@%#!*?[]{}^"
VALEUR_2 = "https://hc-ping.com/0f1e2d"

SOPS_YAML = "creation_rules:\n  - path_regex: {regle}\n    age: {pub}\n"
REGLE_BONNE = r"^deploiement[\\/]secrets[\\/][a-z]+\.env\.enc$"
REGLE_SANS_ANTISLASH = r"^deploiement/secrets/[a-z]+\.env\.enc$"

REFUSEES = [
    "",
    "a b",
    "a\tb",
    'a"b',
    "a'b",
    "a\\b",
    "a$b",
    "a`b",
    "a;b",
    "a&b",
    "a|b",
    "a<b",
    "a>b",
    "a(b",
    "a)b",
    "a~b",
    "a\x07b",
]


def nom_powershell():
    return "powershell" if shutil.which("powershell") else "pwsh"


def commande_ps():
    commande = [shutil.which(nom_powershell()), "-NoProfile", "-NonInteractive"]
    if WINDOWS:
        commande += ["-ExecutionPolicy", "Bypass"]
    return commande


def lancer_ps(tmp_path, corps, env=None, cwd=None):
    """Exécute `corps` (PowerShell) après avoir chargé secrets.ps1 par dot-sourcing."""
    exiger(nom_powershell())
    essai = tmp_path / "essai.ps1"
    texte = f". '{SCRIPT}'\n{corps}\n"
    essai.write_bytes(b"\xef\xbb\xbf" + texte.encode("utf-8"))
    r = subprocess.run(
        [*commande_ps(), "-File", str(essai)],
        check=False,
        capture_output=True,
        cwd=cwd or tmp_path,
        env=env,
    )
    sortie = r.stdout.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    erreur = r.stderr.decode("utf-8", errors="replace")
    return r.returncode, sortie, erreur


@pytest.fixture(scope="module")
def verdicts(tmp_path_factory):
    """Test-ValeurSure sur toutes les valeurs, en un seul lancement de PowerShell."""
    lignes = [f"'{v.encode().hex()}'" for v in [*REFUSEES, VALEUR_1, VALEUR_2]]
    corps = (
        "foreach ($h in @(" + ",".join(lignes) + ")) {\n"
        "  $o = New-Object byte[] ($h.Length / 2)\n"
        "  for ($i = 0; $i -lt $o.Length; $i++) { $o[$i] = [Convert]::ToByte($h.Substring(2*$i, 2), 16) }\n"
        "  $v = [Text.Encoding]::UTF8.GetString($o)\n"
        "  Write-Output ('X' + $h + ' ' + (Test-ValeurSure $v))\n"
        "}"
    )
    code, sortie, erreur = lancer_ps(tmp_path_factory.mktemp("verdicts"), corps)
    assert code == 0, erreur
    return dict(ligne[1:].split(" ") for ligne in sortie.split("\n") if ligne.startswith("X"))


@pytest.mark.parametrize("valeur", REFUSEES, ids=[repr(v) for v in REFUSEES])
def test_valeur_sure_refusee(verdicts, valeur):
    assert verdicts[valeur.encode().hex()] == "False"


@pytest.mark.parametrize("valeur", [VALEUR_1, VALEUR_2])
def test_valeur_sure_admise(verdicts, valeur):
    assert verdicts[valeur.encode().hex()] == "True"


def test_lire_cles(tmp_path):
    bon = tmp_path / "bon.cles"
    bon.write_text("# une note\n\nZETA\nALPHA_1\n  \n# fin\nMILIEU\n", encoding="utf-8")
    minuscule = tmp_path / "minuscule.cles"
    minuscule.write_text("HC_OK\nhc_sonde\n", encoding="utf-8")
    double = tmp_path / "double.cles"
    double.write_text("A\nB\nA\n", encoding="utf-8")
    corps = f"""
(Lire-Cles '{bon}') -join ','
foreach ($f in @('{minuscule}', '{double}')) {{
  try {{ Lire-Cles $f | Out-Null; 'PAS D ERREUR' }} catch {{ 'ERREUR ' + $_.Exception.Message }}
}}
"""
    code, sortie, erreur = lancer_ps(tmp_path, corps)
    assert code == 0, erreur
    lignes = sortie.splitlines()
    assert lignes[0] == "ZETA,ALPHA_1,MILIEU"
    assert lignes[1].startswith("ERREUR") and "ligne 2" in lignes[1]
    assert lignes[2].startswith("ERREUR") and "A" in lignes[2]


def test_dotenv_utf8_lf(tmp_path):
    corps = """
$o = [ordered]@{ A = '1'; B = '2' }
$b = ConvertTo-Dotenv $o
Write-Output ($b.GetType().Name + ' ' + (($b | ForEach-Object { $_.ToString('x2') }) -join ''))
$e = ConvertTo-Dotenv ([ordered]@{ ACCENT = ([string][char]0xE9) })
Write-Output (($e | ForEach-Object { $_.ToString('x2') }) -join '')
"""
    code, sortie, erreur = lancer_ps(tmp_path, corps)
    assert code == 0, erreur
    lignes = sortie.splitlines()
    assert lignes[0] == "Byte[] " + b"A=1\nB=2\n".hex()
    assert lignes[1] == "ACCENT=é\n".encode().hex()


def monter(tmp_path, env, *, regle=REGLE_BONNE, sops_yaml=True, enc=b"ancien contenu\n"):
    """Un dépôt temporaire avec une clé jetable, un .sops.yaml, un .cles et un .enc déjà commités."""
    exiger("sops", "age-keygen")
    d = depot(tmp_path, env)
    cle = tmp_path / "jetable.txt"
    subprocess.run(["age-keygen", "-o", str(cle)], check=True, capture_output=True)
    pub = subprocess.run(
        ["age-keygen", "-y", str(cle)], check=True, capture_output=True, text=True
    ).stdout.strip()
    dossier = d / "deploiement" / "secrets"
    dossier.mkdir(parents=True)
    if sops_yaml:
        (d / ".sops.yaml").write_text(SOPS_YAML.format(regle=regle, pub=pub), encoding="utf-8")
    (dossier / "prod.cles").write_text("HC_SONDE\nAUTRE\n", encoding="utf-8")
    (dossier / "prod.env.enc").write_bytes(enc)
    git(d, env, "add", "-A")
    git(d, env, "commit", "-q", "-m", "chore: décor")
    return d, cle, dossier / "prod.env.enc"


def appeler(tmp_path, d, env, valeurs, fichier):
    """Invoke-Refaire avec un $LireValeur qui rend les valeurs données (clé -> valeur)."""
    table = "; ".join(f"'{k}' = '{v}'" for k, v in valeurs.items())
    corps = f"""
$jeu_essai = @{{ {table} }}
$code = Invoke-Refaire '{fichier}' {{ param($cle) $jeu_essai[$cle] }}
Write-Output "CODE=$code"
"""
    code, sortie, erreur = lancer_ps(tmp_path, corps, env=env, cwd=d)
    assert code == 0, erreur
    lignes = sortie.splitlines()
    assert lignes[-1].startswith("CODE="), sortie
    return int(lignes[-1][5:]), sortie, erreur


def dechiffrer(enc, cle, env):
    env = {**env, "SOPS_AGE_KEY_FILE": str(cle)}
    r = subprocess.run(
        ["sops", "decrypt", "--input-type", "dotenv", "--output-type", "dotenv", str(enc)],
        check=False,
        capture_output=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_refaire_aller_retour(tmp_path, env_isole):
    env = env_isole()
    d, cle, enc = monter(tmp_path, env)
    code, sortie, erreur = appeler(
        tmp_path, d, env, {"HC_SONDE": VALEUR_1, "AUTRE": VALEUR_2}, enc
    )
    assert code == 0, sortie + erreur
    attendu = f"HC_SONDE={VALEUR_1}\nAUTRE={VALEUR_2}\n".encode()
    assert dechiffrer(enc, cle, env) == attendu
    statut = git(d, env, "status", "--porcelain").splitlines()
    assert [ligne[3:] for ligne in statut] == ["deploiement/secrets/prod.env.enc"]
    assert VALEUR_1 not in sortie + erreur
    assert VALEUR_2 not in sortie + erreur
    assert "HC_SONDE : 22 caractères" in sortie
    assert "AUTRE : 26 caractères" in sortie
    assert "réécrit :" in sortie and "(2 clés)" in sortie
    assert not list(enc.parent.glob("*.tmp-*"))


def test_usage(tmp_path):
    """L'appel de la ligne de commande sans argument : usage, 64."""
    exiger(nom_powershell())
    r = subprocess.run(
        [*commande_ps(), "-File", str(SCRIPT)], check=False, capture_output=True, cwd=tmp_path
    )
    assert r.returncode == 64


def test_refaire_sans_sops_yaml(tmp_path, env_isole):
    env = env_isole()
    d, _cle, enc = monter(tmp_path, env, sops_yaml=False)
    code, sortie, _ = appeler(tmp_path, d, env, {"HC_SONDE": VALEUR_1, "AUTRE": VALEUR_2}, enc)
    assert code == 64
    assert ".sops.yaml" in sortie
    assert enc.read_bytes() == b"ancien contenu\n"


def test_refaire_sans_cles(tmp_path, env_isole):
    env = env_isole()
    d, _cle, enc = monter(tmp_path, env)
    (enc.parent / "prod.cles").unlink()
    code, _sortie, _ = appeler(tmp_path, d, env, {"HC_SONDE": VALEUR_1}, enc)
    assert code == 64


def test_refaire_valeur_dangereuse(tmp_path, env_isole):
    env = env_isole()
    d, _cle, enc = monter(tmp_path, env)
    avant = enc.read_bytes()
    code, sortie, erreur = appeler(tmp_path, d, env, {"HC_SONDE": VALEUR_2, "AUTRE": "a$b"}, enc)
    assert code == 64
    assert enc.read_bytes() == avant
    assert "AUTRE" in sortie
    assert "a$b" not in sortie + erreur
    assert VALEUR_2 not in sortie + erreur
    assert not list(enc.parent.glob("*.tmp-*"))


@pytest.mark.skipif(not WINDOWS, reason="le chemin en \\ ne concerne que Windows")
def test_chemin_windows_et_regle(tmp_path, env_isole):
    """Sous Windows sops voit des « \\ » : une règle écrite avec « / » seul ne correspond plus."""
    env = env_isole()
    d, cle, enc = monter(tmp_path, env, regle=REGLE_SANS_ANTISLASH)
    avant = enc.read_bytes()
    code, sortie, erreur = appeler(tmp_path, d, env, {"HC_SONDE": VALEUR_1, "AUTRE": VALEUR_2}, enc)
    assert code == 1, sortie + erreur
    assert enc.read_bytes() == avant
    assert not list(enc.parent.glob("*.tmp-*"))
    assert VALEUR_1 not in sortie + erreur
    # Avec [\\/], la même installation réussit.
    sops_yaml = d / ".sops.yaml"
    sops_yaml.write_text(
        sops_yaml.read_text(encoding="utf-8").replace(REGLE_SANS_ANTISLASH, REGLE_BONNE),
        encoding="utf-8",
    )
    code, sortie, erreur = appeler(tmp_path, d, env, {"HC_SONDE": VALEUR_1, "AUTRE": VALEUR_2}, enc)
    assert code == 0, sortie + erreur
    assert dechiffrer(enc, cle, env).startswith(f"HC_SONDE={VALEUR_1}\n".encode())


def test_bom_et_lf():
    octets = SCRIPT.read_bytes()
    assert octets.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in octets
    octets[3:].decode("utf-8")
