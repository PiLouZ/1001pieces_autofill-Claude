"""
Tests — Les alertes « [!] » sont surlignées dans le détail de l'historique persistant

Suite de la v3.80.1 (panneau Historique). Dans le popup de détail
(HistoryDetailPopup), une ligne « [!] » ouvre une section : elle est rendue en
jaune avertissement, avec retour à la ligne, et reste visible même sans ligne
« ==> » sous elle (l'alerte de mapping disparaissait jusqu'ici).
"""

import pytest
from PyQt5.QtWidgets import QLabel

from src.core.config import Config
from src.ui.history_view_dialog import HistoryDetailPopup


PAGES_VIDES = [
    "Fichier PDF : 357 lignes extraites", "==> Lignes traitées : 357",
    "[!] 805101.pdf : 4 pages vides — appareils peut-être manquants entre :",
    "==> p.3 : DFI544BXXL-04 → DFI544D-02",
    "Appareils :", "==> Créés : 0",
]
MAPPING = [
    "==> Lignes traitées : 2",
    "[!] 2 lignes n'ont produit que 1 identité(s) d'appareil — vérifiez le mapping des colonnes",
    "Appareils :", "==> Créés : 0",
]


def _label(popup, texte):
    return next(l for l in popup.findChildren(QLabel) if texte in l.text())


@pytest.fixture
def popup(qapp):
    crees = []

    def _creer(details):
        p = HistoryDetailPopup("Import x", details, 'import')
        crees.append(p)
        return p
    yield _creer
    for p in crees:
        p.deleteLater()


def test_section_alerte_en_jaune(popup):
    p = popup(PAGES_VIDES)
    titre = _label(p, "4 pages vides")
    assert Config.Colors.WARNING_BG in titre.parentWidget().styleSheet()
    assert Config.Colors.WARNING_TEXT in titre.styleSheet()
    assert Config.Colors.WARNING_TEXT in _label(p, "p.3 : DFI544BXXL-04").styleSheet()


def test_alerte_avec_retour_a_la_ligne(popup):
    p = popup(PAGES_VIDES)
    assert _label(p, "4 pages vides").wordWrap()
    assert _label(p, "p.3 : DFI544BXXL-04").wordWrap()


def test_sections_ordinaires_inchangees(popup):
    p = popup(PAGES_VIDES)
    appareils = _label(p, "Appareils")
    assert Config.Colors.WARNING_BG not in appareils.parentWidget().styleSheet()
    assert not appareils.wordWrap()
    assert "#2c3e50" in _label(p, "Créés : 0").styleSheet()


def test_alerte_sans_detail_affichee(popup):
    """L'alerte de mapping n'a pas de ligne « ==> » : elle doit quand même apparaître."""
    p = popup(MAPPING)
    titre = _label(p, "vérifiez le mapping")
    assert Config.Colors.WARNING_BG in titre.parentWidget().styleSheet()


# ── Imports multi-fichiers : toutes les lignes de fichiers sont affichées ──

from src.ui.history_view_dialog import _regrouper_fichiers

MULTI = [
    "Fichier PDF SS-8030002362.pdf : 15 lignes extraites",
    "Fichier PDF MS-5A21289.pdf : 206 lignes extraites",
    "Fichier PDF 1763070234.pdf : 1 lignes extraites",
    "==> Lignes traitées : 222",
    "Appareils :", "==> Créés : 220",
]


def test_regroupement_des_fichiers():
    details, titres = _regrouper_fichiers(MULTI)
    assert titres == {"3 fichiers"}
    assert details == [
        "3 fichiers",
        "==> SS-8030002362.pdf : 15 lignes extraites",
        "==> MS-5A21289.pdf : 206 lignes extraites",
        "==> 1763070234.pdf : 1 ligne extraite",
        "==> Lignes traitées : 222",
        "Appareils :", "==> Créés : 220",
    ]


def test_import_un_seul_fichier_inchange():
    simple = ["Fichier PDF : 357 lignes extraites", "==> Lignes traitées : 357"]
    assert _regrouper_fichiers(simple) == (simple, set())
    un_nomme = ["Fichier PDF a.pdf : 3 lignes extraites", "==> Lignes traitées : 3"]
    assert _regrouper_fichiers(un_nomme) == (un_nomme, set())


def test_popup_affiche_tous_les_fichiers_et_le_total(popup):
    p = popup(MULTI)
    textes = [l.text() for l in p.findChildren(QLabel)]
    for nom in ("SS-8030002362.pdf", "MS-5A21289.pdf", "1763070234.pdf"):
        assert any(nom in t for t in textes)
    section = _label(p, "3 fichiers").parentWidget()
    assert _label(p, "Lignes traitées : 222").parentWidget() is section
    assert _label(p, "MS-5A21289.pdf").wordWrap()
    assert not _label(p, "Créés : 220").wordWrap()
