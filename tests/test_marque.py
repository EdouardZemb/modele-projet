"""Les retouches du relais qui marque le staging (`scripts/modele/marque.py`, cible `serveur`).

Le fichier du modèle porte un nom de gabarit, sans `.jinja` : Copier en rend le nom, jamais le
contenu. Le test le charge donc par un `SourceFileLoader`, sans quoi un nom qui ne finit pas par
`.py` rend `None`. Les valeurs de la spec sont écrites ici en littéraux, jamais par les constantes
du module : un mutant de la constante doit faire échouer le test.
"""

import base64
import gzip
import hashlib
import http.server
import importlib.machinery
import importlib.util
import inspect
import json
import os
import queue
import random
import socket
import struct
import subprocess
import sys
import threading
import time
import tracemalloc
import zlib
from urllib.parse import quote

import pytest
from conftest import RACINE

CHEMIN = RACINE / "template/scripts/modele/{% if cible == 'serveur' %}marque.py{% endif %}"


def _charger():
    chargeur = importlib.machinery.SourceFileLoader("marque", str(CHEMIN))
    spec = importlib.util.spec_from_file_location("marque", CHEMIN, loader=chargeur)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


marque = _charger()

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def bloc(nom, donnees):
    crc = zlib.crc32(nom + donnees) & 0xFFFFFFFF
    return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", crc)


def filtrer(type_filtre, ligne, precedente, bpp):
    """La ligne `ligne` filtrée par le filtre `type_filtre` (0 à 4), d'après la spec PNG."""
    sortie = bytearray()
    for i, x in enumerate(ligne):
        a = ligne[i - bpp] if i >= bpp else 0
        b = precedente[i]
        c = precedente[i - bpp] if i >= bpp else 0
        if type_filtre == 0:
            p = 0
        elif type_filtre == 1:
            p = a
        elif type_filtre == 2:
            p = b
        elif type_filtre == 3:
            p = (a + b) >> 1
        else:
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            p = a if pa <= pb and pa <= pc else b if pb <= pc else c
        sortie.append((x - p) & 255)
    return bytes([type_filtre]) + bytes(sortie)


def png(
    largeur,
    hauteur,
    type_couleur,
    pixels,
    profondeur=8,
    entrelace=0,
    filtres=None,
    palette=None,
    trns=None,
    taille_idat=None,
):
    """Un PNG : `pixels` porte les échantillons de toutes les lignes, filtrés ligne à ligne."""
    long_ligne = len(pixels) // hauteur
    bpp = max(1, {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[type_couleur] * profondeur // 8)
    brut = bytearray()
    precedente = bytes(long_ligne)
    for y in range(hauteur):
        ligne = bytes(pixels[y * long_ligne : (y + 1) * long_ligne])
        brut += filtrer(filtres[y % len(filtres)] if filtres else 0, ligne, precedente, bpp)
        precedente = ligne
    entete = struct.pack(">IIBBBBB", largeur, hauteur, profondeur, type_couleur, 0, 0, entrelace)
    sortie = SIGNATURE + bloc(b"IHDR", entete)
    if palette is not None:
        sortie += bloc(b"PLTE", palette)
    if trns is not None:
        sortie += bloc(b"tRNS", trns)
    comprime = zlib.compress(bytes(brut), 6)
    pas = taille_idat or len(comprime)
    for debut in range(0, len(comprime), pas):
        sortie += bloc(b"IDAT", comprime[debut : debut + pas])
    return sortie + bloc(b"IEND", b"")


def lire(donnees):
    """(largeur, hauteur, type, pixels, blocs) d'un PNG de sortie : filtre 0 partout, profondeur 8."""
    assert donnees.startswith(SIGNATURE)
    blocs = {}
    pos = 8
    while pos < len(donnees):
        (taille,) = struct.unpack_from(">I", donnees, pos)
        blocs.setdefault(donnees[pos + 4 : pos + 8], []).append(donnees[pos + 8 : pos + 8 + taille])
        pos += 12 + taille
    largeur, hauteur, profondeur, type_couleur, _, _, entrelace = struct.unpack(
        ">IIBBBBB", blocs[b"IHDR"][0]
    )
    assert (profondeur, entrelace) == (8, 0)
    brut = zlib.decompress(b"".join(blocs[b"IDAT"]))
    canaux = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[type_couleur]
    long_ligne = largeur * canaux
    pixels = bytearray()
    for y in range(hauteur):
        assert brut[y * (long_ligne + 1)] == 0
        pixels += brut[y * (long_ligne + 1) + 1 : (y + 1) * (long_ligne + 1)]
    return largeur, hauteur, type_couleur, bytes(pixels), blocs


def pixels_rgba(n):
    sortie = bytearray()
    for i in range(n):
        sortie += bytes([(i * 37) % 256, (i * 91) % 256, (i * 53) % 256, (i * 17) % 256])
    return bytes(sortie)


# --- les valeurs --------------------------------------------------------------------------------


def test_valeurs_de_la_spec():
    assert marque.RAMPE == (
        (0, (0x5C, 0x1A, 0x00)),
        (128, (0xE8, 0x59, 0x0C)),
        (255, (0xFF, 0xE3, 0xC2)),
    )
    assert marque.ORANGE == (0xE8, 0x59, 0x0C)
    assert marque.PLAFOND_PAGE == 5 * 1024 * 1024
    assert marque.COTE_MAX == 1024
    assert marque.ICONE_MAX == 4 * 1024 * 1024
    assert marque.LECTURE_ICONE_MAX == 5 * 1024 * 1024
    assert marque.ICONES_GARDEES == 32
    assert marque.CACHE_OCTETS == 16 * 1024 * 1024
    assert marque.LECTURES_ICONE == 2
    assert marque.DELAI_AMONT == 120
    assert marque.DELAI_INACTIF == 75
    assert marque.HOTE_ECOUTE == "0.0.0.0"
    assert marque.CHEMIN_RESERVE == "/.marque/"
    assert marque.PREFIXE_TITRE == b"test &middot; "
    assert marque.PREFIXE_NOM == "test · "
    assert marque.PREFIXE_NOM_COURT == "test "
    assert marque.LIEN_FEUILLE == b'<link rel="stylesheet" href="/.marque/marque.css">'


def test_rampe_aux_trois_arrets():
    assert marque.couleur_de(0) == (0x5C, 0x1A, 0x00)
    assert marque.couleur_de(128) == (0xE8, 0x59, 0x0C)
    assert marque.couleur_de(255) == (0xFF, 0xE3, 0xC2)
    assert marque.couleur_de(64) == (0xA2, 0x3A, 0x06)
    assert marque.couleur_de(192) == (0xF4, 0x9F, 0x68)
    suite = [marque.couleur_de(i) for i in range(256)]
    for canal in range(3):
        valeurs = [c[canal] for c in suite]
        assert valeurs == sorted(valeurs)
    assert marque.luminance(255, 255, 255) == 255
    assert marque.luminance(255, 0, 0) == 53
    assert marque.luminance(0, 255, 0) == 182
    assert marque.luminance(0, 0, 255) == 18
    assert marque.luminance(0, 0, 0) == 0


# --- le PNG -------------------------------------------------------------------------------------


def test_png_rgba_recolore():
    brut = pixels_rgba(25)
    sortie = marque.recolorer_png(png(5, 5, 6, brut, filtres=[0, 1, 2, 3, 4]))
    largeur, hauteur, type_couleur, pixels, _ = lire(sortie)
    assert (largeur, hauteur, type_couleur) == (5, 5, 6)
    for i in range(25):
        r, g, b, a = brut[4 * i : 4 * i + 4]
        attendu = marque.couleur_de(marque.luminance(r, g, b)) + (a,)
        assert tuple(pixels[4 * i : 4 * i + 4]) == attendu
    blanc = marque.recolorer_png(png(1, 1, 6, bytes([255, 255, 255, 77])))
    assert lire(blanc)[3] == bytes([0xFF, 0xE3, 0xC2, 77])


def test_png_types_0_2_4_recolores():
    gris = marque.recolorer_png(png(2, 1, 0, bytes([0, 255])))
    assert lire(gris)[2:4] == (2, bytes([0x5C, 0x1A, 0x00, 0xFF, 0xE3, 0xC2]))
    gris_alpha = marque.recolorer_png(png(2, 1, 4, bytes([0, 9, 255, 200])))
    assert lire(gris_alpha)[2:4] == (6, bytes([0x5C, 0x1A, 0x00, 9, 0xFF, 0xE3, 0xC2, 200]))
    rvb = marque.recolorer_png(png(1, 2, 2, bytes([255, 255, 255, 0, 0, 0]), filtres=[2]))
    assert lire(rvb)[2:4] == (2, bytes([0xFF, 0xE3, 0xC2, 0x5C, 0x1A, 0x00]))


def test_png_trns_cle_gardee():
    gris = marque.recolorer_png(png(3, 1, 0, bytes([10, 20, 10]), trns=b"\x00\x0a"))
    type_couleur, pixels = lire(gris)[2:4]
    assert type_couleur == 6
    assert [pixels[4 * i + 3] for i in range(3)] == [0, 255, 0]
    rvb = marque.recolorer_png(
        png(2, 1, 2, bytes([1, 2, 3, 1, 2, 4]), trns=b"\x00\x01\x00\x02\x00\x03")
    )
    type_couleur, pixels = lire(rvb)[2:4]
    assert type_couleur == 6
    assert [pixels[4 * i + 3] for i in range(2)] == [0, 255]


def test_png_palette_recoloree():
    palette = bytes([255, 255, 255, 0, 0, 0, 10, 20, 30])
    indices = bytes([0, 1, 2, 2, 1, 0])
    sortie = marque.recolorer_png(
        png(3, 2, 3, indices, filtres=[1, 2], palette=palette, trns=b"\xff\x80")
    )
    _, _, type_couleur, pixels, blocs = lire(sortie)
    assert type_couleur == 3
    assert pixels == indices
    assert blocs[b"tRNS"] == [b"\xff\x80"]
    plte = blocs[b"PLTE"][0]
    assert plte[:6] == bytes([0xFF, 0xE3, 0xC2, 0x5C, 0x1A, 0x00])
    assert len(plte) == 9


def test_png_generique():
    pixel = bytes([1, 2, 3, 4])
    assert marque.recolorer_png(png(1, 1, 6, pixel * 1, profondeur=16)) is None
    assert marque.recolorer_png(png(2, 1, 3, bytes([0x1B]), profondeur=4, palette=b"\0" * 12)) is None
    assert marque.recolorer_png(png(1, 1, 6, pixel, entrelace=1)) is None
    assert marque.recolorer_png(png(1025, 1, 6, pixel * 1025)) is None
    assert marque.recolorer_png(png(1, 1025, 6, pixel * 1025)) is None
    assert marque.recolorer_png(b"\x00\x00\x01\x00" + b"\x00" * 100) is None
    assert marque.recolorer_png(b"quelconque") is None
    assert marque.recolorer_png(b"") is None
    entier = png(4, 4, 6, pixels_rgba(16))
    assert marque.recolorer_png(entier) is not None
    for coupe in (len(entier) - 1, len(entier) - 12, 40, 20, 9):
        assert marque.recolorer_png(entier[:coupe]) is None


def test_png_bombe_generique():
    entete = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    bombe = zlib.compress(b"\x00" * (50 * 1024 * 1024), 9)
    donnees = (
        SIGNATURE + bloc(b"IHDR", entete) + bloc(b"IDAT", bombe) + bloc(b"IEND", b"")
    )
    tracemalloc.start()
    try:
        assert marque.recolorer_png(donnees) is None
        _, pic = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # la décompression est bornée : le surplus de la bombe n'est jamais décompressé
    assert pic < 1024 * 1024
    court = SIGNATURE + bloc(b"IHDR", entete) + bloc(b"IDAT", zlib.compress(b"\x00" * 5)) + bloc(
        b"IEND", b""
    )
    assert marque.recolorer_png(court) is None


def test_png_1024_admis():
    # un bruit déterministe, incompressible : l'IDAT pèse environ 4 Mio, en blocs de 64 Kio
    pixels = random.Random(0).randbytes(1024 * 1024 * 4)
    donnees = png(1024, 1024, 6, pixels, taille_idat=64 * 1024)
    tracemalloc.start()
    try:
        sortie = marque.recolorer_png(donnees)
        _, pic = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert sortie is not None
    assert lire(sortie)[:3] == (1024, 1024, 6)
    assert pic < 48 * 1024 * 1024


# --- le SVG -------------------------------------------------------------------------------------


def test_svg_enveloppe():
    original = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 48"><path d="M0 0"/></svg>'
    sortie = marque.envelopper_svg(original)
    assert sortie.startswith(b"<svg")
    assert b"feColorMatrix" in sortie
    assert base64.b64encode(original) in sortie
    assert b'viewBox="0 0 24 48"' in sortie
    assert b'x="0" y="0" width="24" height="48"' in sortie
    assert b'filter="url(#m)"' in sortie
    sans = marque.envelopper_svg(b'<svg width="32px" height="16"></svg>')
    assert b'viewBox="0 0 32 16"' in sans
    rien = marque.envelopper_svg(b"<svg></svg>")
    assert b'viewBox="0 0 100 100"' in rien
    assert marque.envelopper_svg(b"<svg/>" + b" " * (4194304 - 6)) is not None
    assert marque.envelopper_svg(b"<svg/>" + b" " * (4194304 - 5)) is None


def test_svg_gabarit_entier():
    original = b'<svg viewBox="0 0 2 3"/>'
    attendu = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 3"><defs>'
        '<filter id="m" color-interpolation-filters="sRGB">'
        '<feColorMatrix type="matrix" values="0.2109 0.7148 0.0742 0 0 0.2109 0.7148 0.0742 0 0 '
        '0.2109 0.7148 0.0742 0 0 0 0 0 1 0"/>'
        '<feComponentTransfer><feFuncR type="table" tableValues="0.3608 0.9098 1"/>'
        '<feFuncG type="table" tableValues="0.1020 0.3490 0.8902"/>'
        '<feFuncB type="table" tableValues="0 0.0471 0.7608"/></feComponentTransfer></filter></defs>'
        '<image href="data:image/svg+xml;base64,'
        + base64.b64encode(original).decode()
        + '" x="0" y="0" width="2" height="3" filter="url(#m)"/></svg>'
    )
    assert marque.envelopper_svg(original) == attendu.encode()


def test_icone_generique():
    largeur, hauteur, type_couleur, pixels, _ = lire(marque.icone_generique())
    assert (largeur, hauteur, type_couleur) == (512, 512, 2)
    assert pixels == bytes([0xE8, 0x59, 0x0C]) * (512 * 512)


# --- la feuille ---------------------------------------------------------------------------------


def test_feuille_texte_entier():
    decl = (
        'content: "TEST"; position: fixed; top: 0; left: 0; right: 0; box-sizing: content-box; '
        "height: 20px; padding-top: env(safe-area-inset-top, 0px); background: #e8590c; "
        "color: #ffffff; font: 700 12px/20px system-ui, sans-serif; letter-spacing: 0.2em; "
        "text-align: center; pointer-events: none; z-index: 2147483647;"
    )
    attendu = (
        "/* La marque du staging, posée par le relais du modèle (scripts/modele/marque.py). */\n"
        f"html::before {chr(123)} {decl} {chr(125)}\n"
        f"dialog[open]::before {chr(123)} {decl} {chr(125)}\n"
        f":popover-open::before {chr(123)} {decl} {chr(125)}\n"
    )
    assert marque.FEUILLE.decode("utf-8") == attendu


def test_feuille_trois_regles():
    feuille = marque.FEUILLE.decode("utf-8")
    ouvertures = ["html::before {", "dialog[open]::before {", ":popover-open::before {"]
    assert feuille.count("::before {") == 3
    for i, ouverture in enumerate(ouvertures):
        assert feuille.count(ouverture) == 1
        debut = feuille.index(ouverture)
        fin = feuille.index("}", debut)
        regle = feuille[debut:fin]
        for morceau in (
            'content: "TEST"',
            "height: 20px",
            "env(safe-area-inset-top",
            "#e8590c",
            "pointer-events: none",
            "z-index: 2147483647",
        ):
            assert morceau in regle, (ouverture, morceau)
    assert "," not in feuille.split("{")[0].split("*/")[-1]


# --- la page ------------------------------------------------------------------------------------


def test_page_lien_insere():
    lien = b'<link rel="stylesheet" href="/.marque/marque.css">'
    favicon = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'
    avec = marque.retoucher_page(b"<html><head><meta></head><body>x</body></html>", "/", None)
    assert avec == b"<html><head><meta>" + lien + favicon + b"</head><body>x</body></html>"
    sans_fin = marque.retoucher_page(b"<html><meta><body>x", "/", None)
    assert sans_fin == b"<html><meta>" + lien + favicon + b"<body>x"
    rien = marque.retoucher_page(b"<p>x</p>", "/", None)
    assert rien == b"<p>x</p>" + lien + favicon
    majuscules = marque.retoucher_page(b"<HEAD></HEAD><BODY>", "/", None)
    assert majuscules == b"<HEAD>" + lien + favicon + b"</HEAD><BODY>"


def test_page_ignore_les_commentaires():
    page = b"<head><!-- </head> <title>x</title> --><title>Vrai</title></head>"
    sortie = marque.retoucher_page(page, "/", None)
    lien = b'<link rel="stylesheet" href="/.marque/marque.css">'
    favicon = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'
    assert sortie == (
        b"<head><!-- </head> <title>x</title> --><title>test &middot; Vrai</title>"
        + lien
        + favicon
        + b"</head>"
    )
    ouvert = marque.retoucher_page(b"<head><!-- </head><title>x</title>", "/", None)
    assert ouvert.count(b"test &middot; ") == 0
    assert ouvert.endswith(lien + favicon)


def test_titre_prefixe():
    page = marque.retoucher_page(b"<head><title>Veille emploi</title></head>", "/", None)
    assert b"<title>test &middot; Veille emploi</title>" in page
    majuscules = marque.retoucher_page(b'<head><TITLE lang="fr">Veille</TITLE></head>', "/", None)
    assert b'<TITLE lang="fr">test &middot; Veille</TITLE>' in majuscules
    sans = marque.retoucher_page(b"<head></head>", "/", None)
    assert b"<title" not in sans and b"&middot;" not in sans
    deux = marque.retoucher_page(b"<head><title>A</title><title>B</title></head>", "/", None)
    assert deux.count(b"&middot;") == 1


def test_liens_icone_reecrits():
    page = (
        b"<html><head>"
        b'<link rel="icon" href="/icone.svg">'
        b"<link href='/a.png' rel='shortcut icon'>"
        b"<link rel=icon href=/b.png>"
        b'<link rel="apple-touch-icon-precomposed" href="c.png">'
        b'<link rel="mask-icon" href="/m.svg">'
        b'<link rel="icon" href="https://autre.exemple/i.png">'
        b'<link rel="icon" href="//autre.exemple/i.png">'
        b'<link rel="icon" href="https://hote.exemple/i.png">'
        b"</head><body>"
        b'<link rel="icon" href="/z.png">'
    )
    sortie = marque.retoucher_page(page, "/x/y", "hote.exemple")
    assert b'<link rel="icon" href="/.marque/icone?de=/icone.svg">' in sortie
    assert b"<link href='/.marque/icone?de=/a.png' rel='shortcut icon'>" in sortie
    assert b'<link rel=icon href="/.marque/icone?de=/b.png">' in sortie
    assert b'<link rel="apple-touch-icon-precomposed" href="/.marque/icone?de=/x/c.png">' in sortie
    assert b'<link rel="mask-icon" href="/m.svg">' in sortie
    assert b'<link rel="icon" href="/z.png">' in sortie
    assert b'<link rel="icon" href="https://hote.exemple/i.png">' not in sortie
    assert b'<link rel="icon" href="/.marque/icone?de=/i.png">' in sortie
    assert sortie.count(b'href="/.marque/icone">') == 2
    assert b"autre.exemple" not in sortie
    # des liens d'icône sont là : le favicon par défaut n'est pas ajouté
    assert b"favicon.ico" not in sortie
    # une valeur sans guillemets garde `=`, `?` et l'accent grave, que HTML admet
    nu = marque.retoucher_page(b"<head><link rel=icon href=/a.png?v=1></head>", "/", None)
    assert b'<link rel=icon href="/.marque/icone?de=/a.png%3Fv%3D1">' in nu


def test_lien_icone():
    assert marque.lien_icone("/i.png?v=1&a=2", "/", "h") == "/.marque/icone?de=/i.png%3Fv%3D1%26a%3D2"
    assert marque.lien_icone("i.png", "/m/app.webmanifest", None) == "/.marque/icone?de=/m/i.png"
    assert marque.lien_icone("https://h/i.png", "/", None) == "/.marque/icone"
    assert marque.lien_icone("data:image/png;base64,AAAA", "/", "h") == "/.marque/icone"
    # le chemin résolu est encodé, comme le navigateur le demanderait : l'espace devient `%20`
    assert marque.lien_icone("/a b.png", "/", "h") == "/.marque/icone?de=/a%2520b.png"
    # les sous-délimiteurs, `:` et `@` restent tels quels, comme dans la demande du navigateur
    assert marque.lien_icone("/a+b(1)=c:d@e.png", "/", "h") == (
        "/.marque/icone?de=/a%2Bb%281%29%3Dc%3Ad%40e.png"
    )
    # la requête est encodée comme le navigateur l'encode : `&` et `=` restent
    assert marque.lien_icone("/i.png?v=é&a=b c", "/", "h") == (
        "/.marque/icone?de=/i.png%3Fv%3D%25C3%25A9%26a%3Db%2520c"
    )
    # une barre oblique inverse, que le navigateur lirait comme `/`, donne l'icône générique
    assert marque.lien_icone("/a\\b.png", "/", "h") == "/.marque/icone"
    assert marque.lien_icone("/a.png?b=\\", "/", "h") == "/.marque/icone"
    # 1024 caractères au plus, comme pour `de`
    assert marque.lien_icone("/" + "a" * 1023, "/", None) == "/.marque/icone?de=/" + "a" * 1023
    assert marque.lien_icone("/" + "a" * 1024, "/", None) == "/.marque/icone"
    # le relais ne demande jamais à l'application un chemin qui est le sien
    assert marque.lien_icone("/.marque/icone?de=/i.png", "/", "h") == "/.marque/icone"
    assert marque.lien_icone("https://h/.marque/sante", "/", "h") == "/.marque/icone"
    assert marque.lien_icone("/%2Emarque/sante", "/", "h") == "/.marque/icone"
    assert marque.lien_icone("/.marque%2Fsante", "/", "h") == "/.marque/icone"
    # `^`, que WHATWG encode dans le chemin, et non dans la requête
    assert marque.lien_icone("/p^.png?q=^", "/", "h") == (
        "/.marque/icone?de=/p%255E.png%3Fq%3D%5E"
    )


def test_lien_icone_autre_schema():
    # à l'hôte de la page, un schéma autre qu'`http` ou `https` reste une autre origine
    assert marque.lien_icone("ftp://h/i.png", "/", "h") == "/.marque/icone"
    assert marque.lien_icone("https://h/i.png", "/", "h") == "/.marque/icone?de=/i.png"


def test_icone_au_chemin_non_ascii():
    # le chemin résolu est encodé en UTF-8 avant d'être admis : la forme déjà encodée est la même
    attendu = "/.marque/icone?de=/ic%25C3%25B4ne.png"
    for src in ("/icône.png", "/ic%C3%B4ne.png"):
        corps = json.dumps({"name": "A", "icons": [{"src": src}]}, ensure_ascii=False).encode()
        sortie = json.loads(marque.retoucher_manifeste(corps, "/manifest.json", None))
        assert sortie["icons"] == [{"src": attendu}], src
        page = f'<head><link rel="icon" href="{src}"></head>'.encode()
        assert f'<link rel="icon" href="{attendu}">'.encode() in marque.retoucher_page(page, "/", None)
    relatif = "/.marque/icone?de=/m/ic%25C3%25B4nes/app-192.png"
    corps = json.dumps({"icons": [{"src": "icônes/app-192.png"}]}, ensure_ascii=False).encode()
    sortie = json.loads(marque.retoucher_manifeste(corps, "/m/app.webmanifest", None))
    assert sortie["icons"] == [{"src": relatif}]
    page = '<head><link rel="icon" href="icônes/app-192.png"></head>'.encode()
    assert f'href="{relatif}"'.encode() in marque.retoucher_page(page, "/m/page", None)
    # un `%` reste tel quel, qu'il ouvre un `%XX` ou non, comme dans la demande du navigateur
    assert marque.lien_icone("/a%zz%41.png", "/", None) == "/.marque/icone?de=/a%25zz%2541.png"
    # un caractère qu'UTF-8 n'encode pas, venu du JSON, donne l'icône générique
    assert marque.lien_icone("/\ud800.png", "/", None) == "/.marque/icone"
    assert marque.lien_icone("/i.png?v=\ud800", "/", None) == "/.marque/icone"


def test_icone_demandee_comme_le_navigateur(app, relais):
    # ce que l'application reçoit pour chaque `href`, celui que le navigateur lui demanderait
    attendus = {
        "/a+b(1)=c:d@e.png": "/a+b(1)=c:d@e.png",
        "/icône.png": "/ic%C3%B4ne.png",
        "/a b.png": "/a%20b.png",
        "/a%zz%41.png": "/a%zz%41.png",
        "/i.png?v=é&a=b c": "/i.png?v=%C3%A9&a=b%20c",
        "/i.png?v=1&a=2": "/i.png?v=1&a=2",
        # la requête garde l'accent grave, `{`, `}` et `^`, que WHATWG n'y encode pas
        '/i.png?q="<x>`{}|^': "/i.png?q=%22%3Cx%3E`{}|^",
        # le chemin les encode, `|` excepté
        "/p`{}|^.png": "/p%60%7B%7D|%5E.png",
    }
    app.repondre = lambda r: reponse_brute(200, petit_png(5), "Content-Type: image/png")
    for href, attendu in attendus.items():
        lien = marque.lien_icone(href, "/", "app.exemple")
        assert obtenir(relais, lien).corps == marque.recolorer_png(petit_png(5)), href
        assert app.requetes[-1].chemin == attendu, href


def test_page_sans_lien_recoit_favicon():
    sortie = marque.retoucher_page(b"<head><link rel=stylesheet href=/a.css></head>", "/", None)
    assert (
        b'<link rel="stylesheet" href="/.marque/marque.css">'
        b'<link rel="icon" href="/.marque/icone?de=/favicon.ico"></head>'
    ) in sortie


def test_formes_voisines_ignorees():
    # `<titles>` et `<linker>` ne sont ni un titre ni un lien
    page = b"<head><titles>x</titles><title>T</title><linker rel=icon href=/a.png></head>"
    lien = b'<link rel="stylesheet" href="/.marque/marque.css">'
    favicon = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'
    assert marque.retoucher_page(page, "/", None) == (
        b"<head><titles>x</titles><title>test &middot; T</title><linker rel=icon href=/a.png>"
        + lien
        + favicon
        + b"</head>"
    )


def test_balises_lues_valeurs_sautees():
    # une valeur entre guillemets garde son `>`, dans un titre comme dans un lien
    page = b'<head><title lang="a>b">T</title><link rel="icon" title=\'c>d\' href="/i.png"></head>'
    sortie = marque.retoucher_page(page, "/", None)
    assert b'<title lang="a>b">test &middot; T</title>' in sortie
    assert b"<link rel=\"icon\" title='c>d' href=\"/.marque/icone?de=/i.png\">" in sortie
    # une valeur jamais fermée court jusqu'à la fin : rien de ce qui la suit n'est une balise
    ouverte = b'<head><link a="<link rel=icon href=/i.png></head>'
    lien = b'<link rel="stylesheet" href="/.marque/marque.css">'
    favicon = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'
    assert marque.retoucher_page(ouverte, "/", None) == (
        b'<head><link a="<link rel=icon href=/i.png>' + lien + favicon + b"</head>"
    )
    titre = marque.retoucher_page(b'<head><title x="a>T</title></head>', "/", None)
    assert b"&middot;" not in titre


def test_guillemet_hors_d_une_valeur():
    # comme pour le tokeniseur HTML, un guillemet n'ouvre une valeur que juste après le `=` qui suit
    # un nom, blancs admis autour ; ailleurs, c'est un caractère comme un autre
    icone = b'<link rel=icon href="/.marque/icone?de=/i.png">'
    for avant in (
        b"<link rel=preload href=/fonts/O'Reilly.woff2>",  # dans une valeur sans guillemets
        b'<link rel=stylesheet x" href=/a.css>',  # dans un nom
        b'<link =" rel=stylesheet>',  # un `=` en tête d'un nom en fait partie
        b'<link a==" rel=stylesheet>',  # un second `=` ouvre une valeur sans guillemets
    ):
        page = b"<head>" + avant + b"<link rel=icon href=/i.png></head>"
        sortie = marque.retoucher_page(page, "/", None)
        assert avant + icone in sortie, avant
        assert b"/favicon.ico" not in sortie, avant
    titre = marque.retoucher_page(b"<head><title data-x=l'a>T</title></head>", "/", None)
    assert b"<title data-x=l'a>test &middot; T</title>" in titre
    # après `=`, blancs admis autour, il ouvre une valeur, qui garde son `>`
    page = b"<head><link title = 'a>b' rel=icon href=/i.png></head>"
    assert b"<link title = 'a>b' rel=icon href=\"/.marque/icone?de=/i.png\">" in (
        marque.retoucher_page(page, "/", None)
    )


# Un enfant chronomètre `retoucher_page` : une recherche quadratique tiendrait le GIL des heures,
# et le délai de `subprocess.run` l'arrête.
SONDE_DUREE = """
import importlib.machinery, importlib.util, sys, time
chargeur = importlib.machinery.SourceFileLoader("marque", sys.argv[1])
module = importlib.util.module_from_spec(importlib.util.spec_from_loader("marque", chargeur))
chargeur.exec_module(module)
motif = bytes.fromhex(sys.argv[2])
page = b"<head>" + motif * (1024 * 1024 // len(motif))
debut = time.perf_counter()
module.retoucher_page(page, "/", "h")
print(time.perf_counter() - debut)
"""


def duree_de_la_retouche(motif):
    """La durée de `retoucher_page` sur 1 Mio de `motif`, mesurée dans un enfant."""
    try:
        fini = subprocess.run(
            [sys.executable, "-B", "-c", SONDE_DUREE, str(CHEMIN), motif.hex()],
            capture_output=True,
            timeout=30,
            check=True,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"1 Mio de {motif!r} : plus de 30 s")
    return float(fini.stdout)


@pytest.mark.parametrize("motif", [b"<link ", b"<title ", b'<link a="'])
def test_balise_jamais_fermee_lineaire(motif):
    assert duree_de_la_retouche(motif) < 2, motif


def test_liens_d_icone_fermes_lineaires():
    # chaque lien est retouché, et la page n'est construite qu'une fois
    assert duree_de_la_retouche(b"<link rel=icon href=/i.png>") < 2


def test_retouches_qui_se_touchent():
    # un `<title>` lu dans la valeur d'un lien chevauche sa retouche : seule celle du lien se pose
    sortie = marque.retoucher_page(b'<head><link rel=icon href="/i<title>.png"></head>', "/", None)
    assert sortie == (
        b'<head><link rel=icon href="/.marque/icone?de=/i%253Ctitle%253E.png">'
        b'<link rel="stylesheet" href="/.marque/marque.css"></head>'
    )
    # deux retouches à la même place : la dernière ajoutée d'abord, comme avant
    assert marque.retoucher_page(b"<head><title></head>", "/", None) == (
        b'<head><title><link rel="stylesheet" href="/.marque/marque.css">'
        b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">test &middot; </head>'
    )


# --- le manifeste -------------------------------------------------------------------------------


def test_manifeste_noms_prefixes():
    corps = (
        b'{"name": "Veille", "short_name": "V", '
        b'"icons": [{"src": "i.png", "sizes": "1x1"}, {"src": 5}, "x"]}'
    )
    sortie = marque.retoucher_manifeste(corps, "/m/app.webmanifest", "h")
    assert sortie is not None
    assert "test · Veille".encode() in sortie
    assert b'"short_name": "test V"' in sortie
    assert b'"src": "/.marque/icone?de=/m/i.png"' in sortie
    assert b'"src": 5' in sortie
    assert json.loads(sortie)["name"] == "test · Veille"
    sans = marque.retoucher_manifeste(b'{"display": "standalone"}', "/manifest.json", None)
    assert b'"name": "test"' in sans
    entier = marque.retoucher_manifeste(b'{"name": 5}', "/manifest.json", None)
    assert json.loads(entier) == {"name": "test"}
    court = marque.retoucher_manifeste(b'{"short_name": "V"}', "/manifest.json", None)
    assert b'"short_name": "test V"' in court and b'"name"' not in court


def test_manifeste_avec_bom():
    corps = b"\xef\xbb\xbf" + b'{"name": "App"}'
    assert "test · App".encode() in marque.retoucher_manifeste(corps, "/m.webmanifest", None)


def test_manifeste_illisible():
    assert marque.retoucher_manifeste(b"{", "/m.webmanifest", None) is None
    assert marque.retoucher_manifeste(b"[]", "/m.webmanifest", None) is None
    assert marque.retoucher_manifeste(b'{"name": "\xff\xfe"}', "/m.webmanifest", None) is None
    assert marque.retoucher_manifeste(b'{"name": "\\ud800"}', "/m.webmanifest", None) is None


def test_est_manifeste():
    assert marque.est_manifeste("/manifest.webmanifest", "application/json")
    assert marque.est_manifeste("/x/app.webmanifest?v=1", None)
    assert marque.est_manifeste("/manifest.json", None)
    assert marque.est_manifeste("/m", "application/manifest+json; charset=utf-8")
    assert not marque.est_manifeste("/api/manifest", "application/json")
    assert marque.est_page("text/html; charset=utf-8")
    assert marque.est_page("TEXT/HTML")
    assert not marque.est_page("application/json")
    assert not marque.est_page(None)


# --- le chemin ----------------------------------------------------------------------------------


# Les `de` refusés : `test_de_refuse_sans_requete` les demande aussi au relais.
REFUSES = (
    *("", "a", "//x", "http://x/", "/a\\b", "/a b", "/a\x01", "/é", "/" + "a" * 1024),
    *("/.marque/", "/.marque/icone?de=/i.png", "/.marque/sante"),
)


def test_chemin_admis():
    assert marque.chemin_admis("/a")
    assert marque.chemin_admis("/a?b=c")
    assert marque.chemin_admis("/" + "a" * 1023)
    assert marque.chemin_admis("/.marque")
    assert marque.chemin_admis("/.marques/i.png")
    for refuse in REFUSES:
        assert not marque.chemin_admis(refuse), refuse


@pytest.mark.parametrize("nom", ["{{", "{%"])
def test_aucun_reste_de_jinja(nom):
    assert nom not in CHEMIN.read_text(encoding="utf-8")


# --- le banc du relais --------------------------------------------------------------------------
#
# Une fausse application, un `ThreadingHTTPServer` sur 127.0.0.1:0, sert les octets bruts que
# chaque test lui donne et note chaque requête reçue. Le relais tourne dans le test, devant elle,
# et sa sortie d'erreur est capturée ; le client lui parle par une socket.

LIEN = b'<link rel="stylesheet" href="/.marque/marque.css">'
SANTE = b'{"statut":"ok"}'
SECRET = "jeton-secret-151"
JETON = f"X-Jeton: {SECRET}"
GENERIQUE = "marque : icône remplacée par la générique : "
UPGRADE = ("Connection: Upgrade", "Upgrade: websocket")
CAS_SANS_CORPS = (("GET", "/204", 204), ("GET", "/304", 304), ("HEAD", "/tete", 200))


def octets_requete(methode, cible, *entetes, corps=None, version="HTTP/1.1", hote="app.exemple"):
    """Une requête brute : cible en UTF-8, en-têtes en latin-1, `Content-Length` d'office."""
    if isinstance(cible, str):
        cible = cible.encode("utf-8")
    lignes = ([f"Host: {hote}"] if hote is not None else []) + list(entetes)
    cadre = any(e.lower().startswith(("content-length:", "transfer-encoding:")) for e in entetes)
    if corps is not None and not cadre:
        lignes.append(f"Content-Length: {len(corps)}")
    tete = methode.encode() + b" " + cible + b" " + version.encode() + b"\r\n"
    tete += "".join(e + "\r\n" for e in lignes).encode("latin-1") + b"\r\n"
    return tete + (corps or b"")


def reponse_brute(statut, corps=b"", *entetes, raison="OK", longueur=True):
    lignes = [f"HTTP/1.1 {statut} {raison}", *entetes]
    if longueur:
        lignes.append(f"Content-Length: {len(corps)}")
    return ("\r\n".join(lignes) + "\r\n\r\n").encode("latin-1") + corps


def morceaux(*blocs):
    return b"".join(b"%x\r\n%s\r\n" % (len(b), b) for b in blocs) + b"0\r\n\r\n"


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Reponse:
    def __init__(self, ligne, entetes):
        self.ligne = ligne
        self.statut = int(ligne.split()[1])
        self.entetes = entetes
        self.corps = b""
        self.cadre = b""  # le corps tel qu'il est arrivé, cadrage des morceaux compris

    def tous(self, nom):
        return [v for n, v in self.entetes if n.lower() == nom.lower()]

    def un(self, nom):
        valeurs = self.tous(nom)
        assert len(valeurs) == 1, (nom, valeurs)
        return valeurs[0]


class Connexion:
    """Une connexion brute au relais, qui lit ses réponses une à une."""

    def __init__(self, port, delai=10):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=delai)
        self.tampon = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.s.close()

    def envoyer(self, octets):
        self.s.sendall(octets)

    def _remplir(self):
        bloc = self.s.recv(65536)
        if not bloc:
            raise EOFError("connexion fermée par le relais")
        self.tampon += bloc

    def lire_jusqu_a(self, marque_de_fin):
        while (i := self.tampon.find(marque_de_fin)) < 0:
            self._remplir()
        fin = i + len(marque_de_fin)
        sortie = bytes(self.tampon[:fin])
        del self.tampon[:fin]
        return sortie

    def lire(self, n):
        while len(self.tampon) < n:
            self._remplir()
        sortie = bytes(self.tampon[:n])
        del self.tampon[:n]
        return sortie

    def lire_tout(self):
        try:
            while True:
                self._remplir()
        except (EOFError, ConnectionResetError):
            pass
        sortie = bytes(self.tampon)
        self.tampon.clear()
        return sortie

    def fermee(self, delai=3):
        """Vrai si le relais ferme la connexion sans rien envoyer de plus."""
        self.s.settimeout(delai)
        try:
            return not self.tampon and self.s.recv(1) == b""
        except ConnectionResetError:
            return True
        except TimeoutError:
            return False

    def couper(self):
        """Ferme par RST : `SO_LINGER` à 0."""
        forme = "HH" if sys.platform == "win32" else "ii"
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack(forme, 1, 0))
        self.s.close()

    def reponse(self, methode="GET"):
        tete = self.lire_jusqu_a(b"\r\n\r\n").decode("latin-1")
        ligne, *lignes = tete[:-4].split("\r\n")
        entetes = []
        for brute in lignes:
            nom, _, valeur = brute.partition(":")
            entetes.append((nom, valeur.strip()))
        rep = Reponse(ligne, entetes)
        if methode == "HEAD" or rep.statut in (204, 304) or rep.statut < 200:
            return rep
        if rep.tous("Transfer-Encoding"):
            assert rep.tous("Transfer-Encoding") == ["chunked"]
            corps, cadre = bytearray(), bytearray()
            while True:
                taille = self.lire_jusqu_a(b"\r\n")
                cadre += taille
                if int(taille, 16) == 0:
                    fin = self.lire_jusqu_a(b"\r\n")
                    assert fin == b"\r\n"
                    cadre += fin
                    break
                donnees = self.lire(int(taille, 16) + 2)
                assert donnees.endswith(b"\r\n")
                cadre += donnees
                corps += donnees[:-2]
            rep.corps, rep.cadre = bytes(corps), bytes(cadre)
        elif rep.tous("Content-Length"):
            rep.corps = rep.cadre = self.lire(int(rep.un("Content-Length")))
        else:
            rep.corps = rep.cadre = self.lire_tout()
        return rep


def brut(port, octets, lire_jusqu_a=None):
    """Envoie `octets` au relais, puis lit jusqu'à `lire_jusqu_a`, ou jusqu'à la fermeture."""
    with Connexion(port) as c:
        c.envoyer(octets)
        return c.lire_tout() if lire_jusqu_a is None else c.lire_jusqu_a(lire_jusqu_a)


class Requete:
    def __init__(self, methode, chemin, entetes, corps, empreinte):
        self.methode = methode
        self.chemin = chemin
        self.entetes = entetes
        self.corps = corps
        self.empreinte = empreinte

    def tous(self, nom):
        return [v for n, v in self.entetes if n.lower() == nom.lower()]


class FausseApp:
    """L'application derrière le relais : `repondre(requete)` rend des octets, ou une fonction qui
    écrit elle-même sur la connexion."""

    def __init__(self):
        self.requetes = []
        self.garder = True
        self.repondre = lambda requete: reponse_brute(200, b"ok", "Content-Type: text/plain")
        self._evenements = []
        app = self

        class Gestionnaire(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def __getattr__(self, nom):
                if nom.startswith("do_"):
                    return self.servir
                raise AttributeError(nom)

            def servir(self):
                corps, empreinte = app.lire_corps(self)
                entetes = list(self.headers.items())
                app.requetes.append(Requete(self.command, self.path, entetes, corps, empreinte))
                sortie = app.repondre(app.requetes[-1])
                if callable(sortie):
                    sortie(self.wfile)
                else:
                    self.wfile.write(sortie)
                self.close_connection = True

        class Serveur(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass  # le relais coupe parfois l'application : seul son journal est lu

        self.serveur = Serveur(("127.0.0.1", 0), Gestionnaire)
        self.port = self.serveur.server_address[1]
        self.amont = f"http://127.0.0.1:{self.port}"
        self._fil = threading.Thread(target=self.serveur.serve_forever, args=(0.05,))
        self._fil.start()

    def evenement(self):
        """Un événement que l'application attend, levé d'office à l'arrêt du banc."""
        evenement = threading.Event()
        self._evenements.append(evenement)
        return evenement

    def lire_corps(self, gestionnaire):
        empreinte = hashlib.sha256()
        lus = []
        rfile = gestionnaire.rfile

        def prendre(bloc):
            empreinte.update(bloc)
            if self.garder:
                lus.append(bloc)

        if gestionnaire.headers.get("Transfer-Encoding", "").lower() == "chunked":
            while (taille := int(rfile.readline().split(b";")[0], 16)) > 0:
                while taille:
                    bloc = rfile.read1(min(taille, 65536))
                    prendre(bloc)
                    taille -= len(bloc)
                rfile.readline()
            while rfile.readline() not in (b"\r\n", b"\n", b""):
                pass
        else:
            restant = int(gestionnaire.headers.get("Content-Length") or 0)
            while restant and (bloc := rfile.read1(min(restant, 65536))):
                prendre(bloc)
                restant -= len(bloc)
        return b"".join(lus), empreinte.hexdigest()

    def lever(self):
        for evenement in self._evenements:
            evenement.set()

    def arreter(self):
        self.lever()
        self.serveur.shutdown()
        self.serveur.server_close()
        self._fil.join()


class RelaisDuBanc:
    """Le relais, servi dans un fil ; il compte les connexions qu'il a fermées."""

    def __init__(self, amont, **delais):
        self.serveur = marque.creer_serveur("127.0.0.1", 0, amont, **delais)
        self.port = self.serveur.server_address[1]
        self._fermees = threading.Semaphore(0)
        fermer = self.serveur.shutdown_request

        def noter(requete):
            # après `handle_error` : une ligne d'incident est écrite avant que la fermeture compte
            fermer(requete)
            self._fermees.release()

        self.serveur.shutdown_request = noter
        self._fil = threading.Thread(target=self.serveur.serve_forever, args=(0.05,))
        self._fil.start()

    def attendre_fermetures(self, n=1, delai=10):
        for _ in range(n):
            assert self._fermees.acquire(timeout=delai), "connexion du relais jamais fermée"

    def arreter(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        self._fil.join()


class AppBrute:
    """Une application qui garde les octets bruts de chaque connexion. Elle lit une requête, la
    cadre par son seul `Content-Length`, répond, puis lit ce qui suit jusqu'à la fermeture."""

    def __init__(self):
        self.connexions = queue.Queue()
        self.ecoute = socket.create_server(("127.0.0.1", 0))
        # une attente courte : l'arrêt se voit sans fermer la socket sous un `accept` en cours
        self.ecoute.settimeout(0.05)
        self.amont = f"http://127.0.0.1:{self.ecoute.getsockname()[1]}"
        self._fin = threading.Event()
        self._fil = threading.Thread(target=self._accepter)
        self._fil.start()

    def _accepter(self):
        while not self._fin.is_set():
            try:
                connexion, _ = self.ecoute.accept()
            except TimeoutError:
                continue
            recu = bytearray()
            with connexion:
                connexion.settimeout(10)
                try:
                    self._servir(connexion, recu)
                except OSError:
                    pass  # le test lit ce qui est arrivé
            self.connexions.put(bytes(recu))

    @staticmethod
    def _servir(connexion, recu):
        while b"\r\n\r\n" not in recu and (bloc := connexion.recv(65536)):
            recu += bloc
        tete, _, reste = bytes(recu).partition(b"\r\n\r\n")
        # la première longueur, comme une application qui admet deux longueurs égales
        longueurs = [
            int(ligne.partition(b":")[2])
            for ligne in tete.split(b"\r\n")[1:]
            if ligne.partition(b":")[0].strip().lower() == b"content-length"
        ]
        while len(reste) < (longueurs or [0])[0] and (bloc := connexion.recv(65536)):
            recu += bloc
            reste += bloc
        connexion.sendall(reponse_brute(200, b"ok", "Content-Type: text/plain"))
        while bloc := connexion.recv(65536):
            recu += bloc

    def arreter(self):
        self._fin.set()
        self._fil.join(10)
        self.ecoute.close()


def requetes_lues(brut):
    """Les requêtes qu'une application lirait dans `brut`, chacune cadrée par `Content-Length`."""
    lues = []
    while brut:
        tete, _, reste = brut.partition(b"\r\n\r\n")
        ligne, *entetes = tete.split(b"\r\n")
        longueurs = [
            int(e.partition(b":")[2]) for e in entetes if e.lower().startswith(b"content-length:")
        ]
        longueur = (longueurs or [0])[0]
        lues.append((ligne, entetes, reste[:longueur]))
        brut = reste[longueur:]
    return lues


@pytest.fixture
def app_brute():
    brute = AppBrute()
    yield brute
    brute.arreter()


@pytest.fixture(autouse=True)
def aucun_fil_restant():
    avant = set(threading.enumerate())
    yield
    restants = [f for f in threading.enumerate() if f not in avant]
    for fil in restants:
        fil.join(2)
    assert [f.name for f in restants if f.is_alive()] == []


@pytest.fixture
def app():
    fausse = FausseApp()
    yield fausse
    fausse.arreter()


@pytest.fixture
def lancer_relais(app, capsys):
    lances = []

    # 30 s d'inactivité : une connexion que le relais garderait à tort fait expirer le client (10 s),
    # au lieu de se fermer d'elle-même avant lui.
    def _lancer(amont=None, delai_inactif=30, **delais):
        relais = RelaisDuBanc(amont or app.amont, delai_inactif=delai_inactif, **delais)
        lances.append(relais)
        return relais

    yield _lancer
    app.lever()
    for relais in lances:
        relais.arreter()


@pytest.fixture
def relais(lancer_relais):
    return lancer_relais()


def obtenir(relais, cible, *entetes, methode="GET", corps=None):
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete(methode, cible, *entetes, corps=corps))
        return c.reponse(methode)


def icone(relais, de):
    return obtenir(relais, "/.marque/icone?de=" + quote(de, safe="/"))


def petit_png(k):
    return png(1, 1, 2, bytes([k, k, k]))


def png_de(taille):
    """Un PNG admis de `taille` octets exactement, complété par un bloc annexe."""
    base = png(2, 1, 2, bytes([10, 200, 30, 40, 50, 60]))
    annexe = taille - len(base) - 12
    return base[:33] + bloc(b"tEXt", b"x" * annexe) + base[33:]


# --- le serveur ---------------------------------------------------------------------------------


def test_valeurs_par_defaut_du_serveur():
    parametres = inspect.signature(marque.creer_serveur).parameters
    assert parametres["delai_inactif"].default == 75
    assert parametres["delai_amont"].default == 120
    serveur = marque.creer_serveur("127.0.0.1", 0, "http://127.0.0.1:9")
    try:
        assert serveur.RequestHandlerClass is marque.Relais
        assert marque.Relais.protocol_version == "HTTP/1.1"
        assert serveur.delai_inactif == 75
        assert serveur.delai_amont == 120
        assert serveur.amont == ("127.0.0.1", 9)
    finally:
        serveur.server_close()
    faux_amonts = ("ftp://x:21", "http://x", "http://x:0", "http://x:80/a", "http://u@x:80", "")
    for faux in (*faux_amonts, "x:80"):
        with pytest.raises(ValueError):
            marque.creer_serveur("127.0.0.1", 0, faux)


def test_aucune_resolution_au_demarrage(monkeypatch):
    def interdite(*args):
        raise AssertionError("résolution de nom au démarrage")

    monkeypatch.setattr(socket, "getfqdn", interdite)
    marque.creer_serveur("127.0.0.1", 0, "http://127.0.0.1:9").server_close()


def test_page_retouchee(app, relais):
    page = b"<html><head><title>Veille</title></head><body>x</body></html>"
    app.repondre = lambda r: reponse_brute(
        200,
        page,
        "Content-Type: text/html; charset=utf-8",
        'ETag: "v1"',
        "Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT",
        "Cache-Control: max-age=600",
    )
    rep = obtenir(relais, "/accueil")
    assert rep.statut == 200
    assert LIEN in rep.corps
    assert b"<title>test &middot; Veille</title>" in rep.corps
    assert rep.corps == marque.retoucher_page(page, "/accueil", "app.exemple")
    assert rep.tous("ETag") == [] and rep.tous("Last-Modified") == []
    assert rep.tous("Cache-Control") == ["no-cache"]
    assert rep.un("Content-Length") == str(len(rep.corps))
    assert rep.un("Content-Type") == "text/html; charset=utf-8"


def test_page_au_plafond(app, relais, capsys):
    debut = b"<html><head><title>T</title></head><body>"
    au_plafond = debut + b"x" * (5242880 - len(debut))
    app.repondre = lambda r: reponse_brute(200, au_plafond, "Content-Type: text/html")
    rep = obtenir(relais, "/grande")
    assert rep.corps.startswith(b"<html><head><title>test &middot; T</title>")
    assert LIEN in rep.corps
    assert capsys.readouterr().err == ""

    trop = debut + b"x" * (5242881 - len(debut))
    app.repondre = lambda r: reponse_brute(200, trop, "Content-Type: text/html", 'ETag: "t"')
    rep = obtenir(relais, "/grande")
    assert rep.corps == trop
    assert rep.un("Content-Length") == "5242881"
    assert rep.un("ETag") == '"t"'
    assert capsys.readouterr().err == "marque : page trop grande, transmise sans marque\n"

    # par morceaux : ce qui est lu part, puis le reste suit
    app.repondre = lambda r: (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nTransfer-Encoding: chunked\r\n\r\n"
        + morceaux(trop[:3000000], trop[3000000:])
    )
    rep = obtenir(relais, "/grande")
    assert rep.corps == trop
    assert rep.tous("Content-Length") == []
    assert capsys.readouterr().err == "marque : page trop grande, transmise sans marque\n"


def test_pages_non_retouchees(app, relais):
    page = b"<html><head><title>T</title></head></html>"
    cas = [
        ("GET", reponse_brute(404, page, "Content-Type: text/html", 'ETag: "a"', raison="Absente")),
        (
            "GET",
            reponse_brute(
                206, page, "Content-Type: text/html", "Content-Range: bytes 0-41/99",
                raison="Partial Content",
            ),
        ),
        (
            "GET",
            reponse_brute(
                200, gzip.compress(page), "Content-Type: text/html", "Content-Encoding: gzip"
            ),
        ),
        ("POST", reponse_brute(200, page, "Content-Type: text/html", 'ETag: "b"')),
    ]
    for methode, brute in cas:
        app.repondre = lambda r, brute=brute: brute
        rep = obtenir(relais, "/p", methode=methode, corps=b"x" if methode == "POST" else None)
        tete, _, corps = brute.partition(b"\r\n\r\n")
        lignes = tete.decode().split("\r\n")[1:]
        attendus = [tuple(x.strip() for x in e.split(":", 1)) for e in lignes]
        assert rep.corps == corps
        assert rep.entetes == attendus


def test_manifeste_retouche(app, relais):
    manifeste = json.dumps({"name": "Veille", "short_name": "V", "icons": [{"src": "/i/a.png"}]})
    app.repondre = lambda r: reponse_brute(
        200, manifeste.encode(), "Content-Type: application/manifest+json", 'ETag: "m"'
    )
    rep = obtenir(relais, "/manifest.webmanifest")
    lu = json.loads(rep.corps)
    assert lu["name"] == "test · Veille"
    assert lu["short_name"] == "test V"
    assert lu["icons"] == [{"src": "/.marque/icone?de=/i/a.png"}]
    assert rep.tous("ETag") == []
    assert rep.tous("Cache-Control") == ["no-cache"]
    assert rep.un("Content-Length") == str(len(rep.corps))


def test_manifeste_illisible_transmis(app, relais, capsys):
    app.repondre = lambda r: reponse_brute(
        200, b"{pas du json", "Content-Type: application/manifest+json", 'ETag: "m"'
    )
    rep = obtenir(relais, "/manifest.json")
    assert rep.corps == b"{pas du json"
    assert rep.un("ETag") == '"m"'
    assert capsys.readouterr().err == "marque : manifeste illisible, transmis sans marque\n"


def test_manifeste_trop_grand(app, relais, capsys):
    # un manifeste lisible, mais au-delà de 5 Mio : il passe tel quel, et le journal dit pourquoi
    grand = json.dumps({"name": "A", "x": "y" * 5242880}).encode()
    app.repondre = lambda r: reponse_brute(
        200, grand, "Content-Type: application/manifest+json", 'ETag: "g"'
    )
    rep = obtenir(relais, "/manifest.json")
    assert rep.corps == grand
    assert rep.un("ETag") == '"g"'
    assert capsys.readouterr().err == "marque : manifeste trop grand, transmis sans marque\n"
    assert "une page trop grande, un manifeste trop grand" in " ".join(marque.__doc__.split())


def test_cache_prive_garde(app, relais):
    page = b"<html><head></head></html>"
    app.repondre = lambda r: reponse_brute(
        200, page, "Content-Type: text/html", "Cache-Control: no-store, private, max-age=60"
    )
    assert obtenir(relais, "/p").tous("Cache-Control") == ["no-cache, no-store, private"]
    manifeste = json.dumps({"name": "A"}).encode()
    app.repondre = lambda r: reponse_brute(
        200,
        manifeste,
        "Content-Type: application/manifest+json",
        "Cache-Control: public, max-age=60",
        'Cache-Control: Private="Set-Cookie"',
    )
    assert obtenir(relais, "/manifest.json").tous("Cache-Control") == ["no-cache, private"]


def test_cache_directive_entre_guillemets(app, relais):
    # une directive dans une valeur entre guillemets n'est pas une directive
    page = b"<html><head></head></html>"
    app.repondre = lambda r: reponse_brute(
        200, page, "Content-Type: text/html", 'Cache-Control: x="a, private, no-store, b"'
    )
    assert obtenir(relais, "/p").tous("Cache-Control") == ["no-cache"]


def test_icone_par_le_relais(app, relais, capsys, monkeypatch):
    appels = []
    vraie = marque.recolorer_png
    monkeypatch.setattr(marque, "recolorer_png", lambda d: appels.append(len(d)) or vraie(d))
    icone_png = png(3, 2, 6, pixels_rgba(6))
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4"/>'
    icones = {
        "/icone.png": reponse_brute(200, icone_png, "Content-Type: image/png"),
        "/icone.svg": reponse_brute(200, svg, "Content-Type: image/svg+xml"),
        "/absente.png": reponse_brute(404, b"absente", raison="Not Found"),
        "/au-plafond.png": reponse_brute(200, png_de(5242880), "Content-Type: image/png"),
        "/trop-lue.png": reponse_brute(200, png_de(5242881), "Content-Type: image/png"),
        "/favicon.ico": reponse_brute(200, b"\x00\x00\x01\x00" + bytes(60), "Content-Type: x"),
        "/large.png": reponse_brute(200, png(1025, 1, 2, bytes(3075)), "Content-Type: image/png"),
    }
    app.repondre = lambda r: icones[r.chemin]
    generique = marque.icone_generique()

    rep = obtenir(
        relais,
        "/.marque/icone?de=/icone.png",
        'If-None-Match: "x"',
        "If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT",
        "Range: bytes=0-10",
        "Accept-Encoding: gzip",
        "Cookie: s=1",
    )
    assert rep.statut == 200
    assert rep.un("Content-Type") == "image/png"
    assert rep.un("Cache-Control") == "no-cache"
    assert rep.corps == vraie(icone_png)
    (requete,) = app.requetes
    assert (requete.methode, requete.chemin) == ("GET", "/icone.png")
    assert requete.entetes == [("Host", "app.exemple"), ("Cookie", "s=1")]
    assert len(appels) == 1
    assert capsys.readouterr().err == ""

    # une seconde demande ne recolore pas de nouveau
    assert icone(relais, "/icone.png").corps == vraie(icone_png)
    assert len(appels) == 1

    rep = icone(relais, "/icone.svg")
    assert rep.un("Content-Type") == "image/svg+xml"
    assert rep.corps == marque.envelopper_svg(svg)

    for chemin, raison in (
        ("/absente.png", "réponse 404"),
        ("/favicon.ico", "format"),
        ("/large.png", "taille"),
    ):
        assert icone(relais, chemin).corps == generique, chemin
        assert capsys.readouterr().err == f"{GENERIQUE}{raison}\n"

    assert icone(relais, "/au-plafond.png").corps == vraie(png_de(5242880))
    assert capsys.readouterr().err == ""
    assert icone(relais, "/trop-lue.png").corps == generique
    assert capsys.readouterr().err == f"{GENERIQUE}taille\n"


def test_cache_borne(app, lancer_relais, monkeypatch):
    appels = []
    vraie_png, vraie_svg = marque.recolorer_png, marque.envelopper_svg
    monkeypatch.setattr(marque, "recolorer_png", lambda d: appels.append("png") or vraie_png(d))
    monkeypatch.setattr(marque, "envelopper_svg", lambda d: appels.append("svg") or vraie_svg(d))
    corps = {f"/i{k}.png": petit_png(k) for k in range(33)}
    corps.update(
        {
            f"/s{k}.svg": b'<svg viewBox="0 0 1 1">' + b" " * 4000000 + b"<!--%d--></svg>" % k
            for k in range(4)
        }
    )

    def repondre(r):
        sorte = "image/svg+xml" if r.chemin.endswith(".svg") else "image/png"
        return reponse_brute(200, corps[r.chemin], f"Content-Type: {sorte}")

    app.repondre = repondre

    # 32 icônes au plus : après 33, la première est sortie, la deuxième reste
    relais = lancer_relais()
    for k in range(33):
        assert icone(relais, f"/i{k}.png").corps == vraie_png(petit_png(k))
    assert appels.count("png") == 33
    icone(relais, "/i1.png")
    assert appels.count("png") == 33
    icone(relais, "/i0.png")
    assert appels.count("png") == 34
    icone(relais, "/i32.png")
    assert appels.count("png") == 34

    # 16 Mio au plus : trois enveloppes y tiennent, la quatrième fait sortir la plus ancienne
    relais = lancer_relais()
    taille = len(vraie_svg(corps["/s0.svg"]))
    assert 3 * taille <= 16 * 1024 * 1024 < 4 * taille
    for k in range(4):
        icone(relais, f"/s{k}.svg")
    assert appels.count("svg") == 4
    icone(relais, "/s0.svg")
    assert appels.count("svg") == 5
    # s0 a fait sortir s1 : s2 et s3 restent
    icone(relais, "/s2.svg")
    assert appels.count("svg") == 5
    icone(relais, "/s3.svg")
    assert appels.count("svg") == 5


def test_lectures_icone_bornees(app, relais):
    etat = {"en_cours": 0, "max": 0, "arrivees": 0}
    condition = threading.Condition()
    liberer = app.evenement()

    def repondre(r):
        with condition:
            etat["en_cours"] += 1
            etat["arrivees"] += 1
            etat["max"] = max(etat["max"], etat["en_cours"])
            condition.notify_all()
        liberer.wait(10)
        with condition:
            etat["en_cours"] -= 1
        return reponse_brute(200, petit_png(int(r.chemin[2:-4])), "Content-Type: image/png")

    app.repondre = repondre
    fils = [threading.Thread(target=icone, args=(relais, f"/i{k}.png")) for k in range(3)]
    for fil in fils:
        fil.start()
    with condition:
        assert condition.wait_for(lambda: etat["arrivees"] >= 2, timeout=10)
        # la troisième attend sa place tant que les deux premières lisent
        assert not condition.wait_for(lambda: etat["arrivees"] >= 3, timeout=0.5)
    liberer.set()
    for fil in fils:
        fil.join(10)
    assert etat == {"en_cours": 0, "max": 2, "arrivees": 3}


def test_une_recoloration_a_la_fois(app, relais, monkeypatch):
    etat = {"en_cours": 0, "max": 0, "appels": 0}
    condition = threading.Condition()
    vraie = marque.recolorer_png

    def lente(donnees):
        with condition:
            etat["en_cours"] += 1
            etat["appels"] += 1
            etat["max"] = max(etat["max"], etat["en_cours"])
            condition.notify_all()
            # elle attend la seconde, que le verrou retient dehors
            condition.wait_for(lambda: etat["appels"] >= 2, timeout=1)
            etat["en_cours"] -= 1
        return vraie(donnees)

    monkeypatch.setattr(marque, "recolorer_png", lente)
    app.repondre = lambda r: reponse_brute(
        200, petit_png(int(r.chemin[2:-4])), "Content-Type: image/png"
    )
    fils = [threading.Thread(target=icone, args=(relais, f"/i{k}.png")) for k in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(10)
    assert etat == {"en_cours": 0, "max": 1, "appels": 2}


def test_lecture_tenue_jusqu_a_la_recoloration(app, relais, monkeypatch):
    commencee = threading.Event()
    finir = app.evenement()
    vraie = marque.recolorer_png

    def lente(donnees):
        commencee.set()
        finir.wait(10)
        return vraie(donnees)

    monkeypatch.setattr(marque, "recolorer_png", lente)
    condition = threading.Condition()

    def repondre(r):
        with condition:
            condition.notify_all()
        return reponse_brute(200, petit_png(int(r.chemin[2:-4])), "Content-Type: image/png")

    app.repondre = repondre
    fils = [threading.Thread(target=icone, args=(relais, f"/i{k}.png")) for k in range(3)]
    try:
        fils[0].start()
        assert commencee.wait(10)
        fils[1].start()
        with condition:
            assert condition.wait_for(lambda: len(app.requetes) >= 2, timeout=10)
        # i0 se recolore, i1 attend le verrou : leurs deux places sont tenues, i2 attend la sienne
        fils[2].start()
        with condition:
            assert not condition.wait_for(lambda: len(app.requetes) >= 3, timeout=0.5)
    finally:
        finir.set()
        for fil in fils:
            if fil.ident is not None:
                fil.join(10)
    assert [r.chemin for r in app.requetes] == ["/i0.png", "/i1.png", "/i2.png"]


def test_sante_pendant_une_recoloration(app, relais, monkeypatch):
    commencee = threading.Event()
    finir = app.evenement()
    vraie = marque.recolorer_png

    def lente(donnees):
        commencee.set()
        finir.wait(10)
        return vraie(donnees)

    monkeypatch.setattr(marque, "recolorer_png", lente)
    app.repondre = lambda r: reponse_brute(200, petit_png(7), "Content-Type: image/png")
    fil = threading.Thread(target=icone, args=(relais, "/i.png"))
    fil.start()
    try:
        assert commencee.wait(10)
        debut = time.monotonic()
        rep = obtenir(relais, "/.marque/sante")
        duree = time.monotonic() - debut
    finally:
        finir.set()
        fil.join(10)
    assert (rep.statut, rep.corps) == (200, SANTE)
    assert duree < 5


def test_de_refuse_sans_requete(app, relais, capsys):
    generique = marque.icone_generique()
    for de in REFUSES:
        rep = obtenir(relais, "/.marque/icone?de=" + quote(de, safe=""))
        assert rep.corps == generique, de
        assert capsys.readouterr().err == f"{GENERIQUE}chemin refusé\n"
    autre = marque.lien_icone("https://autre.exemple/i.png", "/", "app.exemple")
    for cible in ("/.marque/icone", autre):
        assert obtenir(relais, cible).corps == generique
        assert capsys.readouterr().err == f"{GENERIQUE}autre origine\n"
    assert app.requetes == []


def test_icone_sans_conditionnels(app, relais):
    app.repondre = lambda r: reponse_brute(200, petit_png(3), "Content-Type: image/png")
    obtenir(
        relais,
        "/.marque/icone?de=/i.png",
        'If-Match: "x"',
        "If-Unmodified-Since: Wed, 18 Nov 2026 10:00:00 GMT",
        'If-Range: "x"',
        "Expect: x-autre",
        "X-Garde: oui",
    )
    (requete,) = app.requetes
    assert requete.entetes == [("Host", "app.exemple"), ("X-Garde", "oui")]


def test_icone_application_injoignable(lancer_relais, capsys):
    mort = lancer_relais(amont=f"http://127.0.0.1:{port_libre()}")
    rep = obtenir(mort, "/.marque/icone?de=/i.png")
    assert (rep.statut, rep.corps) == (502, b"application injoignable\n")
    assert capsys.readouterr().err == "marque : application injoignable\n"


def test_svg_trop_grand_par_le_relais(app, relais, capsys):
    app.repondre = lambda r: reponse_brute(
        200, b"<svg/>" + b" " * (4194304 - 5), "Content-Type: image/svg+xml"
    )
    assert icone(relais, "/grand.svg").corps == marque.icone_generique()
    assert capsys.readouterr().err == f"{GENERIQUE}taille\n"


def test_icone_compressee_generique(app, relais, capsys):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4"/>'
    reponses = {
        "/gzip.svg": reponse_brute(
            200, gzip.compress(svg), "Content-Type: image/svg+xml", "Content-Encoding: gzip"
        ),
        "/identite.svg": reponse_brute(
            200, svg, "Content-Type: image/svg+xml", "Content-Encoding: identity"
        ),
    }
    app.repondre = lambda r: reponses[r.chemin]
    assert icone(relais, "/gzip.svg").corps == marque.icone_generique()
    assert capsys.readouterr().err == f"{GENERIQUE}format\n"
    assert icone(relais, "/identite.svg").corps == marque.envelopper_svg(svg)
    assert capsys.readouterr().err == ""


def test_icone_apres_une_reponse_informative(app, relais, capsys):
    def ecrire(sortie):
        sortie.write(b"HTTP/1.1 103 Early Hints\r\nLink: </x.css>; rel=preload\r\n\r\n")
        sortie.write(reponse_brute(200, petit_png(9), "Content-Type: image/png"))

    app.repondre = lambda r: ecrire
    assert icone(relais, "/i.png").corps == marque.recolorer_png(petit_png(9))
    assert capsys.readouterr().err == ""


def test_chemin_reserve_normalise(app, relais, capsys):
    with Connexion(relais.port) as c:
        for cible in ("/%2Emarque/sante", "/%2emarque/sante", "/a/../.marque/sante"):
            c.envoyer(octets_requete("GET", cible))
            rep = c.reponse()
            assert (rep.statut, rep.corps) == (200, SANTE), cible
        c.envoyer(octets_requete("GET", "/x/%2E%2E/%2Emarque/./marque.css"))
        assert c.reponse().corps == marque.FEUILLE
        c.envoyer(octets_requete("GET", "/%2Emarque/autre"))
        assert c.reponse().statut == 404
        # sous `/.marque/` telle qu'elle arrive, normalisée hors de lui : elle reste au relais
        c.envoyer(octets_requete("GET", "/.marque/../x"))
        assert c.reponse().statut == 404
        c.envoyer(octets_requete("GET", "/.marque/icone?de=/%252Emarque/sante"))
        assert c.reponse().corps == marque.icone_generique()
    assert app.requetes == []
    assert capsys.readouterr().err == f"{GENERIQUE}chemin refusé\n"
    # toute autre cible part telle qu'elle est arrivée, sans normalisation
    obtenir(relais, "/a/./b/../c%2Ex")
    assert [r.chemin for r in app.requetes] == ["/a/./b/../c%2Ex"]
    for refuse in ("/%2Emarque/sante", "/%2e%2E/.marque/x", "/a/../.marque/", "/.marque/."):
        assert not marque.chemin_admis(refuse), refuse
    assert marque.chemin_admis("/a/../b") and marque.chemin_admis("/%2Emarques/i.png")


def test_barre_encodee_sous_le_chemin_reserve(app, relais, capsys):
    # l'application lit `%2F` comme `/` (uvicorn le décode) : la cible reste au relais
    with Connexion(relais.port) as c:
        for cible in ("/.marque%2Fsante", "/%2Emarque%2Fsante", "/.marque%2fsante"):
            c.envoyer(octets_requete("GET", cible))
            rep = c.reponse()
            assert (rep.statut, rep.corps) == (200, SANTE), cible
        c.envoyer(octets_requete("GET", "/.marque/icone?de=/.marque%252Fsante"))
        assert c.reponse().corps == marque.icone_generique()
    assert app.requetes == []
    assert capsys.readouterr().err == f"{GENERIQUE}chemin refusé\n"
    # le décodage ne sert qu'à ce test : toute autre cible part telle qu'elle est arrivée
    obtenir(relais, "/a%2Fb/%2F%2e")
    assert [r.chemin for r in app.requetes] == ["/a%2Fb/%2F%2e"]


def test_point_final_sous_le_chemin_reserve(app, relais):
    # un `.` final laisse un `/` final : `/%2Emarque/.` est `/.marque/`, servi par le relais
    assert obtenir(relais, "/%2Emarque/.").statut == 404
    assert app.requetes == []


def test_head_sur_une_page(app, relais):
    def repondre(r):
        if r.methode == "HEAD":
            return b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 1234\r\n\r\n"
        return reponse_brute(200, b"ok", "Content-Type: text/plain")

    app.repondre = repondre
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("HEAD", "/"))
        rep = c.reponse("HEAD")
        assert rep.statut == 200
        assert rep.tous("Content-Length") == [] and rep.tous("Transfer-Encoding") == []
        c.envoyer(octets_requete("GET", "/suite"))
        assert c.reponse().corps == b"ok"


def test_chemin_reserve(app, relais):
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/.marque/sante"))
        rep = c.reponse()
        assert (rep.statut, rep.corps) == (200, SANTE)
        assert rep.un("Content-Type") == "application/json"
        assert rep.un("Cache-Control") == "no-cache"
        c.envoyer(octets_requete("GET", "/.marque/marque.css"))
        rep = c.reponse()
        assert (rep.statut, rep.corps) == (200, marque.FEUILLE)
        assert rep.un("Content-Type") == "text/css; charset=utf-8"
        assert rep.un("Cache-Control") == "no-cache"
        c.envoyer(octets_requete("GET", "/.marque/autre"))
        assert c.reponse().statut == 404
    assert app.requetes == []


# --- la transmission, par la socket brute -------------------------------------------------------


def test_http11_deux_requetes(app, lancer_relais):
    relais = lancer_relais()
    mort = lancer_relais(amont=f"http://127.0.0.1:{port_libre()}")
    kilo = bytes(range(256)) * 4
    premieres = (
        (mort, octets_requete("POST", "/x", corps=kilo), 502),
        (relais, octets_requete("POST", "/ws", *UPGRADE, corps=kilo), 501),
        (relais, octets_requete("POST", b"/a\x01", corps=kilo), 400),
        (relais, octets_requete("POST", "/.marque/sante", corps=kilo), 200),
    )
    for serveur, premiere, code in premieres:
        with Connexion(serveur.port) as c:
            c.envoyer(premiere)
            rep = c.reponse()
            assert rep.statut == code
            assert rep.ligne.startswith("HTTP/1.1 ")
            assert rep.tous("Connection") == []
            seconde = "/.marque/sante" if serveur is mort else "/suite"
            c.envoyer(octets_requete("GET", seconde))
            rep = c.reponse()
            assert rep.statut == 200
            assert rep.corps == (SANTE if serveur is mort else b"ok")
            assert rep.tous("Connection") == []
    assert [(r.methode, r.chemin) for r in app.requetes] == [("GET", "/suite")] * 3


def test_client_http10(app, relais):
    flux = b"flux " * 1000
    app.repondre = lambda r: b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n" + flux
    # `Connection: keep-alive` : `http.server` garderait la connexion d'un client HTTP/1.0 qui le
    # demande, et la fin du corps n'y serait jamais dite
    for entetes in ((), ("Connection: keep-alive",)):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("GET", "/flux", *entetes, version="HTTP/1.0"))
            rep = c.reponse()
            assert rep.corps == flux
            assert rep.tous("Transfer-Encoding") == [] and rep.tous("Content-Length") == []
            assert c.fermee()


def test_reponse_par_morceaux(app, relais):
    reponses = {
        "/morceaux": b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + morceaux(b"un ", b"deux ", b"trois"),
        # sans longueur ni morceaux, la fin du corps est la fin de la connexion de l'application
        "/sans-longueur": b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nun deux trois",
    }
    app.repondre = lambda r: reponses[r.chemin]
    with Connexion(relais.port) as c:
        for chemin in reponses:
            c.envoyer(octets_requete("GET", chemin))
            rep = c.reponse()
            assert sum(n.lower() == "transfer-encoding" for n, _ in rep.entetes) == 1
            assert rep.un("Transfer-Encoding") == "chunked"
            assert rep.tous("Content-Length") == []
            assert rep.corps == b"un deux trois"
            assert rep.cadre.endswith(b"\r\n0\r\n\r\n")
        c.envoyer(octets_requete("GET", "/.marque/sante"))
        assert c.reponse().corps == SANTE


def test_entetes_de_la_reponse(app, relais):
    app.repondre = lambda r: reponse_brute(
        200,
        b"ok",
        "Server: fausse-app",
        "Date: Wed, 18 Nov 2026 10:00:00 GMT",
        "Connection: X-Foo",
        "X-Foo: 1",
        "Keep-Alive: timeout=5",
        "Trailer: X-Bar",
        "Proxy-Authenticate: Basic",
        "Content-Type: text/plain",
        "X-Garde: oui",
    )
    rep = obtenir(relais, "/x")
    for nom in ("Connection", "X-Foo", "Keep-Alive", "Trailer", "Proxy-Authenticate"):
        assert rep.tous(nom) == [], nom
    assert rep.tous("Server") == ["fausse-app"]
    assert rep.tous("Date") == ["Wed, 18 Nov 2026 10:00:00 GMT"]
    assert rep.tous("X-Garde") == ["oui"]


def test_sans_corps(app, relais):
    reponses = {
        "/204": b"HTTP/1.1 204 No Content\r\nX-A: 1\r\n\r\n",
        "/304": b'HTTP/1.1 304 Not Modified\r\nETag: "e"\r\n\r\n',
        "/tete": b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 50\r\n\r\n",
    }
    app.repondre = lambda r: reponses[r.chemin]
    with Connexion(relais.port) as c:
        for methode, chemin, code in CAS_SANS_CORPS:
            c.envoyer(octets_requete(methode, chemin))
            rep = c.reponse(methode)
            assert rep.statut == code
            assert rep.tous("Transfer-Encoding") == []
        # le `HEAD` d'un type que le relais ne retouche pas garde sa longueur
        assert rep.un("Content-Length") == "50"
        c.envoyer(octets_requete("GET", "/.marque/sante"))
        assert c.reponse().corps == SANTE


def test_expect_100_continue(app, relais):
    corps = b"x" * 5000
    with Connexion(relais.port) as c:
        attente = ("Expect: 100-continue", f"Content-Length: {len(corps)}")
        c.envoyer(octets_requete("POST", "/envoi", *attente))
        assert c.reponse().statut == 100
        c.envoyer(corps)
        assert c.reponse().statut == 200
    (requete,) = app.requetes
    assert requete.corps == corps
    assert requete.tous("Expect") == []


def test_corps_par_morceaux_transmis(app, relais):
    envoi = morceaux(b"premier ", b"second ", b"x" * 100000)
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("POST", "/envoi", "Transfer-Encoding: chunked") + envoi)
        assert c.reponse().statut == 200
    (requete,) = app.requetes
    assert requete.corps == b"premier second " + b"x" * 100000
    assert requete.tous("Content-Length") == []
    assert requete.tous("Transfer-Encoding") == ["chunked"]


def test_deux_set_cookie(app, relais):
    app.repondre = lambda r: reponse_brute(
        200, b"ok", "Set-Cookie: a=1; Path=/", "Content-Type: text/plain", "Set-Cookie: b=2; Path=/"
    )
    assert obtenir(relais, "/x").tous("Set-Cookie") == ["a=1; Path=/", "b=2; Path=/"]


def test_entetes_passes_tels_quels(app, relais):
    obtenir(
        relais,
        "/x?y=1",
        "Cookie: s=1; t=2",
        "Cf-Connecting-Ip: 203.0.113.7",
        "X-Forwarded-For: 203.0.113.7",
    )
    (requete,) = app.requetes
    assert requete.chemin == "/x?y=1"
    # `http.client` n'ajoute ni son `Host` ni son `Accept-Encoding`
    assert requete.entetes == [
        ("Host", "app.exemple"),
        ("Cookie", "s=1; t=2"),
        ("Cf-Connecting-Ip", "203.0.113.7"),
        ("X-Forwarded-For", "203.0.113.7"),
    ]


def test_entetes_retires(app, relais):
    retires = (
        "Accept-Encoding: gzip, br",
        "Keep-Alive: 300",
        "TE: trailers",
        "Upgrade: h2c",
        "Connection: X-Saut",
        "X-Saut: 1",
        'If-None-Match: "v1"',
        "If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT",
        "Proxy-Authorization: Basic eA==",
    )
    for methode in ("GET", "HEAD"):
        obtenir(relais, "/x", *retires, "X-Garde: oui", methode=methode)
        assert app.requetes[-1].entetes == [("Host", "app.exemple"), ("X-Garde", "oui")], methode
    # les conditionnels d'une autre méthode passent
    obtenir(relais, "/x", 'If-None-Match: "v1"', methode="POST", corps=b"z")
    assert app.requetes[-1].tous("If-None-Match") == ['"v1"']


def test_chemin_refuse_400(app, relais):
    # une espace coupe la ligne en quatre mots : `http.server` répond 400 et ferme, corps non lu
    with Connexion(relais.port) as c:
        c.envoyer(b"GET /a b HTTP/1.1\r\nHost: app.exemple\r\n\r\n")
        assert c.reponse().statut == 400
        assert c.fermee()
    for cible in (b"/a\x01", b"/a\x7f", "/é".encode(), b"http://autre/z"):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("GET", cible))
            rep = c.reponse()
            assert rep.statut == 400, cible
            assert rep.tous("Connection") == []
            c.envoyer(octets_requete("GET", "/.marque/sante"))
            assert c.reponse().corps == SANTE
    assert app.requetes == []


def test_methode_refusee(app, relais):
    # `http.server` admet ces méthodes, que `http.client` ne sait pas envoyer
    for methode in ("GET\x01", "GÉT"):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete(methode, "/a", corps=b"abc"))
            rep = c.reponse()
            assert (rep.statut, rep.corps) == (400, "méthode refusée\n".encode()), methode
            assert rep.tous("Connection") == []
            # le corps a été lu : la requête suivante passe
            c.envoyer(octets_requete("GET", "/suite"))
            assert c.reponse().corps == b"ok"
    assert [(r.methode, r.chemin) for r in app.requetes] == [("GET", "/suite")] * 2


@pytest.fixture
def ecoute():
    """Une application muette : la socket d'écoute que le relais joindrait, jamais acceptée."""
    with socket.create_server(("127.0.0.1", 0)) as s:
        yield s


def aucune_connexion(ecoute):
    """Vrai si le relais n'a ouvert aucune connexion vers `ecoute` : ouverte avant sa réponse au
    client, elle attendrait dans la file d'écoute."""
    ecoute.setblocking(False)
    try:
        connexion, _ = ecoute.accept()
    except BlockingIOError:
        return True
    connexion.close()
    return False


MORCEAUX = ("Transfer-Encoding: chunked",)
# qui lirait `Content-Length` y verrait une seconde requête, que `Transfer-Encoding` cache
DESYNCHRONISE = b"0\r\n\r\n" + octets_requete("GET", "/cachee")
CADRAGES_REFUSES = (
    ((*MORCEAUX, f"Content-Length: {len(DESYNCHRONISE)}"), DESYNCHRONISE),
    (("Transfer-Encoding: gzip",), morceaux(b"abc")),
    (("Content-Length: 3", "Content-Length: 4"), b"abcd"),
    (("Content-Length: abc",), b"abc"),
    (MORCEAUX, b"zz\r\nabc\r\n0\r\n\r\n"),
    (MORCEAUX, b"3\r\nabcX\r\n0\r\n\r\n"),
    (MORCEAUX, b"3\r\nabc\r\n0\r\n" + b"X-Fin: 1\r\n" * 101 + b"\r\n"),
)


def test_corps_mal_cadre_400(lancer_relais, ecoute, capsys):
    relais = lancer_relais(amont=f"http://127.0.0.1:{ecoute.getsockname()[1]}", delai_amont=1)
    for entetes, corps in CADRAGES_REFUSES:
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("POST", "/envoi", *entetes, corps=corps))
            rep = c.reponse()
            assert (rep.statut, rep.corps) == (400, "corps mal cadré\n".encode()), corps
            assert rep.un("Connection") == "close"
            assert c.fermee()
        assert aucune_connexion(ecoute), corps
    assert capsys.readouterr().err == ""


def test_cent_champs_de_fin_admis(app, relais):
    corps = b"3\r\nabc\r\n0\r\n" + b"X-Fin: 1\r\n" * 100 + b"\r\n"
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("POST", "/envoi", *MORCEAUX, corps=corps))
        assert c.reponse().statut == 200
        c.envoyer(octets_requete("GET", "/suite"))
        assert c.reponse().corps == b"ok"
    assert [(r.chemin, r.corps) for r in app.requetes] == [("/envoi", b"abc"), ("/suite", b"")]


MAL_FORMES = (
    # des défauts qu'`email.feedparser` note
    *("X-A 1", "X-A : 1", "X-A: 1\rB"),
    # des CR qu'il prend, sans défaut, pour une fin de ligne : il perd ce qui les suit
    *("X-A: 1\r", "\rX-B: 2", "\r"),
    # un CR nu qu'il garde dans la valeur, un en-tête qu'il voit injecté
    *("X-A: 1\r 2", "X-A: 1\rX-B: 2"),
    # des replis, qu'il garderait dans la valeur, dont un qui cache `Transfer-Encoding`
    *("X-A: 1\r\n suite", "X-A: 1\n\tsuite", "X-A: 1\r\n Transfer-Encoding: chunked"),
    # un octet nul dans un nom, puis dans une valeur
    *("X\x00A: 1", "X-A: 1\x002"),
)


def test_entetes_mal_formes_400(app, relais, capsys):
    # perdus, `Content-Length` et ce qui le suit feraient du corps une seconde requête
    cachee = octets_requete("GET", "/cachee")
    longueur = f"Content-Length: {len(cachee)}"
    for ligne in MAL_FORMES:
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("POST", "/a", ligne, longueur, JETON, corps=cachee))
            rep = c.reponse()
            assert (rep.statut, rep.corps) == (400, "en-têtes mal formés\n".encode()), ligne
            assert rep.un("Connection") == "close"
            assert c.fermee()
    assert app.requetes == []
    assert capsys.readouterr().err == ""
    regle = (
        "une ligne d'en-tête porte un CR ailleurs qu'avant son LF final, porte un octet nul, ou"
        " commence par une espace ou une tabulation (un repli)"
    )
    assert regle in " ".join(marque.__doc__.split())


def test_entetes_bien_formes_admis(app, relais):
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("POST", "/sain", "X-A: 1", "Cookie: s=1; t=2", corps=b"abc"))
        assert c.reponse().statut == 200
        # une espace et des tabulations au milieu d'une ligne, jamais en tête
        c.envoyer(octets_requete("POST", "/milieu", "X-A:\t1 2\t3", corps=b"abc"))
        assert c.reponse().statut == 200
        c.envoyer(b"POST /lf HTTP/1.1\nHost: app.exemple\nX-A: 1\nContent-Length: 3\n\nabc")
        assert c.reponse().statut == 200
    recues = [(r.chemin, r.corps, r.tous("X-A")) for r in app.requetes]
    assert recues == [
        ("/sain", b"abc", ["1"]),
        ("/milieu", b"abc", ["1 2\t3"]),
        ("/lf", b"abc", ["1"]),
    ]


def test_double_barre_refusee(app, relais):
    # `http.server` réécrirait `//x` en `/x` : le relais lit la cible brute de la ligne de requête
    for cible in ("//x/y", "///x", "//"):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("POST", cible, corps=b"abc"))
            rep = c.reponse()
            assert (rep.statut, rep.corps) == (400, "cible refusée\n".encode()), cible
            assert rep.tous("Connection") == []
            # le corps a été lu : la connexion sert encore
            c.envoyer(octets_requete("GET", "/.marque/sante"))
            assert c.reponse().corps == SANTE
    assert app.requetes == []


CONTREBANDE = octets_requete("GET", "/.marque/sante", "X-Injecte: oui", hote="x")


@pytest.mark.parametrize("connexion", ["Content-Length", "keep-alive, content-length"])
def test_connection_ne_retire_pas_la_longueur(app_brute, lancer_relais, connexion):
    # le corps porte une seconde requête : sans sa longueur, l'application la lirait et l'exécuterait
    relais = lancer_relais(amont=app_brute.amont)
    with Connexion(relais.port) as c:
        c.envoyer(
            octets_requete("POST", "/formulaire", f"Connection: {connexion}", corps=CONTREBANDE)
        )
        assert c.reponse().corps == b"ok"
    longueur = f"Content-Length: {len(CONTREBANDE)}".encode()
    assert requetes_lues(app_brute.connexions.get(timeout=10)) == [
        (b"POST /formulaire HTTP/1.1", [b"Host: app.exemple", longueur], CONTREBANDE)
    ]


def test_longueur_remise_une_fois(app_brute, lancer_relais):
    relais = lancer_relais(amont=app_brute.amont)
    for entetes, attendue in (
        (("Content-Length: 3", "Content-Length: 3"), b"Content-Length: 3"),
        (("Content-Length: 003",), b"Content-Length: 3"),
    ):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("POST", "/p", *entetes, corps=b"abc"))
            assert c.reponse().corps == b"ok"
        (requete,) = requetes_lues(app_brute.connexions.get(timeout=10))
        assert requete == (b"POST /p HTTP/1.1", [b"Host: app.exemple", attendue], b"abc"), entetes
    # une requête sans longueur n'en reçoit pas
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/g"))
        assert c.reponse().corps == b"ok"
    assert app_brute.connexions.get(timeout=10) == b"GET /g HTTP/1.1\r\nHost: app.exemple\r\n\r\n"


def test_connection_ne_retire_pas_host(app, relais):
    obtenir(relais, "/h", "Connection: host", "X-Garde: oui")
    (requete,) = app.requetes
    assert requete.entetes == [("Host", "app.exemple"), ("X-Garde", "oui")]


def test_client_http10_ferme_apres_la_reponse(app, relais):
    # `Connection: keep-alive` ne garde pas la connexion d'un client HTTP/1.0 : la réponse ne le
    # lui dirait pas
    for cible in ("/x", "/.marque/sante"):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("GET", cible, "Connection: keep-alive", version="HTTP/1.0"))
            rep = c.reponse()
            assert rep.statut == 200
            assert rep.tous("Content-Length") == [str(len(rep.corps))]
            assert c.fermee(), cible


@pytest.mark.parametrize(
    "informative, entete",
    [("103 Early Hints", ("Link", "</s.css>; rel=preload")), ("102 Processing", ("X-Etape", "1"))],
)
def test_reponse_informative(app, relais, informative, entete):
    def ecrire(sortie):
        sortie.write(f"HTTP/1.1 {informative}\r\n{entete[0]}: {entete[1]}\r\n\r\n".encode())
        sortie.write(reponse_brute(200, b"finale", "Content-Type: text/plain"))

    app.repondre = lambda r: (
        ecrire if r.chemin == "/informe" else reponse_brute(200, b"ok", "Content-Type: text/plain")
    )
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/informe"))
        rep = c.reponse()
        assert rep.ligne == f"HTTP/1.1 {informative}"
        assert rep.tous(entete[0]) == [entete[1]]
        rep = c.reponse()
        assert (rep.statut, rep.corps) == (200, b"finale")
        # la connexion sert encore : la requête suivante reçoit sa propre réponse
        c.envoyer(octets_requete("GET", "/suite"))
        assert c.reponse().corps == b"ok"
    # un client HTTP/1.0 ne reçoit jamais une réponse informative
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/informe", version="HTTP/1.0"))
        rep = c.reponse()
        assert (rep.statut, rep.corps) == (200, b"finale")


def test_informative_sans_entetes_d_un_saut(app, relais):
    def ecrire(sortie):
        sortie.write(
            b"HTTP/1.1 103 Early Hints\r\nConnection: X-Saut\r\nX-Saut: 1\r\n"
            b"Keep-Alive: timeout=5\r\nProxy-X: 1\r\nLink: </s.css>\r\n\r\n"
        )
        sortie.write(reponse_brute(200, b"finale", "Content-Type: text/plain"))

    app.repondre = lambda r: ecrire
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/informe"))
        rep = c.reponse()
        assert (rep.statut, rep.entetes) == (103, [("Link", "</s.css>")])
        assert c.reponse().corps == b"finale"


def test_client_parti_avant_l_informative(app, relais, capsys):
    recue, parti = threading.Event(), app.evenement()

    def ecrire(sortie):
        parti.wait(10)
        # jusqu'à ce que le relais ferme : sa première écriture au client parti échoue
        for _ in range(100):
            sortie.write(b"HTTP/1.1 103 Early Hints\r\nLink: </s.css>\r\n\r\n")
            time.sleep(0.01)
        sortie.write(reponse_brute(200, b"finale", "Content-Type: text/plain"))

    def repondre(r):
        recue.set()
        return ecrire

    app.repondre = repondre
    c = Connexion(relais.port)
    c.envoyer(octets_requete("GET", "/informe"))
    assert recue.wait(10)
    c.couper()
    parti.set()
    relais.attendre_fermetures()
    # le client est parti : ce n'est pas l'application qui est injoignable
    assert capsys.readouterr().err == ""


def test_upgrade_501(app, relais):
    rep = obtenir(relais, "/ws", *UPGRADE)
    assert rep.statut == 501
    assert app.requetes == []


def test_101_non_sollicite_502(app, relais, capsys):
    # le relais répond 501 à toute demande d'`Upgrade` : un 101 de l'application n'est jamais
    # sollicité, et le client reçoit 502, HTTP/1.1 comme HTTP/1.0
    bascule = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: x\r\nConnection: Upgrade\r\n\r\n"
    app.repondre = lambda r: (
        bascule if r.chemin == "/bascule" else reponse_brute(200, b"ok", "Content-Type: text/plain")
    )
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/bascule"))
        rep = c.reponse()
        assert (rep.statut, rep.corps) == (502, b"application injoignable\n")
        # la connexion sert encore
        c.envoyer(octets_requete("GET", "/suite"))
        assert c.reponse().corps == b"ok"
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/bascule", version="HTTP/1.0"))
        assert c.reponse().statut == 502
    assert capsys.readouterr().err == "marque : application injoignable\n" * 2


def test_amont_injoignable(app, lancer_relais, capsys):
    mort = lancer_relais(amont=f"http://127.0.0.1:{port_libre()}")
    assert obtenir(mort, "/x").statut == 502
    assert capsys.readouterr().err == "marque : application injoignable\n"

    with socket.socket() as muette:
        muette.bind(("127.0.0.1", 0))
        muette.listen(1)
        lente = lancer_relais(amont=f"http://127.0.0.1:{muette.getsockname()[1]}", delai_amont=0.5)
        debut = time.monotonic()
        assert obtenir(lente, "/x").statut == 502
        assert time.monotonic() - debut < 5
    assert capsys.readouterr().err == "marque : application injoignable\n"

    # coupée après ses en-têtes : la connexion du client se ferme, sans 502 ni ligne
    relais = lancer_relais()
    coupees = {
        "/longueur": b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n0123456789",
        "/morceaux": b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\na\r\n0123456789\r\n",
    }
    app.repondre = lambda r: coupees[r.chemin]
    for chemin, reste in (("/longueur", b"0123456789"), ("/morceaux", b"a\r\n0123456789\r\n")):
        with Connexion(relais.port) as c:
            c.envoyer(octets_requete("GET", chemin))
            assert c.lire_jusqu_a(b"\r\n\r\n").startswith(b"HTTP/1.1 200 ")
            assert c.lire_tout() == reste
    # une page ou une icône, lue avant tout envoi au client : rien ne lui parvient
    coupees = {
        "/page": b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 100\r\n\r\n<html>",
        "/i.png": b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 100\r\n\r\n\x89PNG",
    }
    for cible in ("/page", "/.marque/icone?de=/i.png"):
        assert brut(relais.port, octets_requete("GET", cible)) == b"", cible
    relais.attendre_fermetures(4)
    assert capsys.readouterr().err == ""


def test_connexion_inactive_fermee(lancer_relais):
    relais = lancer_relais(delai_inactif=0.5)
    with Connexion(relais.port) as c:
        debut = time.monotonic()
        assert c.fermee(delai=5)
        assert time.monotonic() - debut < 2


def test_gros_corps_transmis(app, relais):
    app.garder = False
    app.repondre = lambda r: reponse_brute(200, r.empreinte.encode(), "Content-Type: text/plain")
    base = random.Random(151).randbytes(64 * 1024)
    attendu = hashlib.sha256()
    tracemalloc.start()
    try:
        with Connexion(relais.port, delai=60) as c:
            c.envoyer(octets_requete("PUT", "/document", f"Content-Length: {20 * 1024 * 1024}"))
            for i in range(320):
                bloc_envoye = bytes([i % 256]) + base[1:]
                attendu.update(bloc_envoye)
                c.envoyer(bloc_envoye)
            rep = c.reponse()
        _, pic = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert rep.corps.decode() == attendu.hexdigest()
    # les 20 Mio passent par blocs : ni le relais ni l'application ne les gardent
    assert pic < 8 * 1024 * 1024


def test_client_qui_coupe(app, relais, capsys):
    liberer = [app.evenement(), app.evenement()]

    def repondre(r):
        if r.chemin == "/vite":
            return reponse_brute(200, b"ok", "Content-Type: text/plain")

        def lente(sortie):
            sortie.write(b"HTTP/1.1 200 OK\r\nContent-Length: 4194304\r\n\r\n")
            liberer[int(r.chemin[-1])].wait(10)
            for _ in range(64):
                sortie.write(b"x" * 65536)

        return lente

    app.repondre = repondre
    # le client ferme après les en-têtes d'une réponse lente
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/lente/0"))
        assert c.lire_jusqu_a(b"\r\n\r\n").startswith(b"HTTP/1.1 200 ")
    liberer[0].set()
    relais.attendre_fermetures()
    # un autre ferme par RST
    c = Connexion(relais.port)
    c.envoyer(octets_requete("GET", "/lente/1"))
    assert c.lire_jusqu_a(b"\r\n\r\n").startswith(b"HTTP/1.1 200 ")
    c.couper()
    liberer[1].set()
    relais.attendre_fermetures()
    # un troisième ferme par RST une connexion gardée, entre deux requêtes
    c = Connexion(relais.port)
    c.envoyer(octets_requete("GET", "/vite"))
    assert c.reponse().corps == b"ok"
    c.couper()
    relais.attendre_fermetures()

    assert obtenir(relais, "/vite").corps == b"ok"
    relais.attendre_fermetures()
    assert capsys.readouterr().err == ""


def test_incident_sans_trace(app, relais, capsys, monkeypatch):
    def cassee(*args):
        raise RuntimeError("retouche cassée")

    monkeypatch.setattr(marque, "retoucher_page", cassee)
    app.repondre = lambda r: reponse_brute(200, b"<html></html>", "Content-Type: text/html")
    assert brut(relais.port, octets_requete("GET", "/page-secrete-151")) == b""
    relais.attendre_fermetures()
    journal = capsys.readouterr().err
    assert journal == "marque : incident interne, connexion fermée\n"
    for interdit in ("127.0.0.1", "Traceback", "page-secrete-151", "retouche cassée"):
        assert interdit not in journal


def test_reponse_au_fil(app, relais):
    suite = app.evenement()
    attente_finie = threading.Event()

    def repondre(r):
        def ecrire(sortie):
            sortie.write(b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\n")
            sortie.write(b"premier-morceau|")
            suite.wait(10)
            attente_finie.set()
            sortie.write(b"fin.")

        return ecrire

    app.repondre = repondre
    with Connexion(relais.port) as c:
        c.envoyer(octets_requete("GET", "/fil"))
        c.lire_jusqu_a(b"premier-morceau|")
        # le premier morceau est arrivé pendant que l'application attendait encore
        assert not attente_finie.is_set()
        suite.set()
        assert c.lire(4) == b"fin."


# --- le script lancé ----------------------------------------------------------------------------


def env_du_relais(**variables):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MARQUE_")}
    env.update(variables)
    return env


class Script:
    """Le relais lancé par `python -B`, sa sortie d'erreur lue en UTF-8, ligne à ligne."""

    def __init__(self, env):
        self.proc = subprocess.Popen(
            [sys.executable, "-B", str(CHEMIN)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.lignes = queue.Queue()
        self._fin = False
        self._fil = threading.Thread(target=self._lire)
        self._fil.start()

    def _lire(self):
        for brute in self.proc.stderr:
            self.lignes.put(brute.decode("utf-8", "replace").rstrip("\r\n"))
        self.lignes.put(None)

    def ligne(self, delai=20):
        """La ligne suivante, ou `None` à la fin de la sortie d'erreur."""
        ligne = self.lignes.get(timeout=delai)
        self._fin = ligne is None
        return ligne

    def arreter(self):
        """Arrête le processus et rend les lignes qu'il a écrites depuis la dernière lue."""
        if self.proc.poll() is None:
            self.proc.terminate()
        self.proc.wait(20)
        self._fil.join(20)
        self.proc.stderr.close()
        reste = []
        while not self._fin and (ligne := self.ligne(1)) is not None:
            reste.append(ligne)
        return reste

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.proc.stderr and not self.proc.stderr.closed:
            self.arreter()


def lancer_script(**variables):
    return subprocess.run(
        [sys.executable, "-B", str(CHEMIN)],
        env=env_du_relais(**variables),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_refus_hors_du_staging(app):
    valides = {
        "MARQUE_AMONT": app.amont,
        "MARQUE_PORT": str(port_libre()),
        "MARQUE_HOTE": "127.0.0.1",
    }
    refus = (
        (None, "MARQUE_ENV absente"),
        ("", "MARQUE_ENV="),
        ("prod", "MARQUE_ENV=prod"),
        ("dev", "MARQUE_ENV=dev"),
    )
    for env, etat in refus:
        variables = dict(valides) if env is None else {**valides, "MARQUE_ENV": env}
        r = lancer_script(**variables)
        assert r.returncode == 64, etat
        assert r.stderr.decode("utf-8").splitlines() == [f"marque : refus hors du staging ({etat})"]
    for nom, valeur in (
        ("MARQUE_AMONT", "ftp://x"),
        ("MARQUE_AMONT", "http://x"),
        ("MARQUE_PORT", "0"),
        ("MARQUE_PORT", "65536"),
        ("MARQUE_PORT", "abc"),
    ):
        r = lancer_script(**{**valides, "MARQUE_ENV": "staging", nom: valeur})
        assert r.returncode == 64, (nom, valeur)
        (ligne,) = r.stderr.decode("utf-8").splitlines()
        assert ligne.startswith("marque : refus : ") and nom in ligne
        assert "hors du staging" not in ligne


def test_ecoute_par_defaut_sur_toutes_les_adresses(monkeypatch, capsys):
    recus = []

    class Faux:
        def serve_forever(self):
            raise KeyboardInterrupt

    def faux_serveur(hote, port, amont):
        recus.append((hote, port, amont))
        return Faux()

    monkeypatch.setattr(marque, "creer_serveur", faux_serveur)
    monkeypatch.delenv("MARQUE_HOTE", raising=False)
    monkeypatch.setenv("MARQUE_ENV", "staging")
    monkeypatch.setenv("MARQUE_PORT", "8080")
    monkeypatch.setenv("MARQUE_AMONT", "http://app.exemple:3000")
    assert marque.main() == 0
    # la valeur écrite, et non `HOTE_ECOUTE`, qu'un mutant changerait avec elle
    assert recus == [("0.0.0.0", 8080, "http://app.exemple:3000")]
    assert capsys.readouterr().err == "marque : relais du staging prêt sur le port 8080\n"


def test_demarrage_en_staging(app):
    port = port_libre()
    env = env_du_relais(
        MARQUE_ENV="staging", MARQUE_AMONT=app.amont, MARQUE_PORT=str(port), MARQUE_HOTE="127.0.0.1"
    )
    with Script(env) as script:
        assert script.ligne() == f"marque : relais du staging prêt sur le port {port}"
        with Connexion(port) as c:
            c.envoyer(octets_requete("GET", "/.marque/sante"))
            rep = c.reponse()
        assert (rep.statut, rep.corps) == (200, SANTE)
        assert script.arreter() == []


def test_journal_sans_adresse(app):
    def repondre(r):
        if r.chemin.startswith("/coupe/"):
            return b""  # l'application coupe sans répondre
        if r.chemin.startswith("/grande/"):
            return reponse_brute(200, b"<html>" + b"x" * 5242880, "Content-Type: text/html")
        return reponse_brute(200, b"ok", "Content-Type: text/plain")

    app.repondre = repondre
    port = port_libre()
    env = env_du_relais(
        MARQUE_ENV="staging", MARQUE_AMONT=app.amont, MARQUE_PORT=str(port), MARQUE_HOTE="127.0.0.1"
    )
    with Script(env) as script:
        assert "prêt" in script.ligne()
        with Connexion(port) as c:
            c.envoyer(octets_requete("GET", f"/invitation/{SECRET}?x={SECRET}", JETON))
            assert c.reponse().statut == 200
            c.envoyer(octets_requete("GET", f"/{SECRET}\x01", JETON))
            assert c.reponse().statut == 400
            c.envoyer(octets_requete("GET", f"/coupe/{SECRET}", JETON))
            assert c.reponse().statut == 502
            c.envoyer(octets_requete("GET", f"/grande/{SECRET}", JETON))
            assert c.reponse().statut == 200
        with Connexion(port) as c:
            c.envoyer(f"GET /{SECRET} x HTTP/1.1\r\nHost: app.exemple\r\n{JETON}\r\n\r\n".encode())
            assert c.reponse().statut == 400
            assert c.fermee()
        journal = script.arreter()
    assert journal == [
        "marque : application injoignable",
        "marque : page trop grande, transmise sans marque",
    ]
    for ligne in journal:
        assert SECRET not in ligne and "127.0.0.1" not in ligne
