"""
Tests — Compléter vite le libellé d'une pièce (lien de l'historique et ⌘⇧L)

Demande de l'utilisateur (2026-09-25) : quand les boutons Méta refusent une pièce
sans libellé, pouvoir le compléter tout de suite. Deux accès, un seul chemin :
- le refus inscrit dans l'historique porte un lien « Compléter le libellé » ;
- ⌘⇧L ouvre la même édition pour la référence tapée dans la recherche.
Les deux ouvrent « Modifier la pièce » du gestionnaire de pièces, curseur dans le
champ Libellé : l'enregistrement reste celui du gestionnaire (historique,
propagation aux équivalents, garde contre l'effacement).
"""

from datetime import datetime
from urllib.parse import quote, unquote

import pytest
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeyEvent

from src.core.constants import UIConfig
from src.services.keyboard_shortcut_service import KeyboardShortcutService
from src.ui.piece_management_service import PieceManagementService
from src.ui.user_interaction_service import UserInteractionService


# ── Historique : rendu du lien ──

class _Fenetre:
    pass


def test_lien_rendu_dans_l_historique():
    service = UserInteractionService(_Fenetre())
    service.add_to_history("SEO: Méta titre non généré pour 'AS6018811'\n==> Libellé manquant",
                           lien=("libelle:AS6018811", "Compléter le libellé de AS6018811"))
    html = service._build_history_html()
    assert '<a href="libelle:AS6018811">Compléter le libellé de AS6018811</a>' in html


def test_texte_du_lien_echappe():
    service = UserInteractionService(_Fenetre())
    service.add_to_history("SEO: x", lien=('libelle:A%26B', 'Compléter <A&B>'))
    html = service._build_history_html()
    assert '<a href="libelle:A%26B">Compléter &lt;A&amp;B&gt;</a>' in html


def test_entree_sans_lien_inchangee():
    service = UserInteractionService(_Fenetre())
    service.add_to_history("SEO: Méta titre généré pour 'R1'")
    assert '<a ' not in service._build_history_html()


@pytest.mark.parametrize("ref", ["AS6018811", "AB/12 #3", "réf?x=1&y", "100%"])
def test_reference_aller_retour_dans_le_lien(ref):
    """Encodée à l'écriture, décodée une seule fois au clic : « / », « # », « ? »,
    « & », « % » et espaces ne cassent pas le lien."""
    href = UIConfig.LIEN_HISTORIQUE_LIBELLE + quote(ref, safe="")
    assert unquote(href[len(UIConfig.LIEN_HISTORIQUE_LIBELLE):]) == ref


# ── ⌘⇧L ──

class _Service:
    def __init__(self):
        self.appels = 0

    def completer_libelle_recherche(self):
        self.appels += 1


class _Parent:
    def __init__(self):
        self.piece_management_service = _Service()


def _touche(cle, modificateurs):
    return QKeyEvent(QEvent.KeyPress, cle, modificateurs)


@pytest.fixture
def raccourcis(qapp):
    service = KeyboardShortcutService(_Parent())
    service.initialize_services()
    return service


def test_cmd_maj_l_ouvre_l_edition_du_libelle(raccourcis):
    for cmd in (Qt.ControlModifier, Qt.MetaModifier):
        assert raccourcis.handle_key_press_event(_touche(Qt.Key_L, cmd | Qt.ShiftModifier))
    assert raccourcis.parent_window.piece_management_service.appels == 2


def test_cmd_l_seul_ne_declenche_rien(raccourcis):
    assert not raccourcis.handle_key_press_event(_touche(Qt.Key_L, Qt.ControlModifier))
    assert not raccourcis.handle_key_press_event(_touche(Qt.Key_L, Qt.ShiftModifier))
    assert raccourcis.parent_window.piece_management_service.appels == 0


def test_raccourcis_existants_intacts(raccourcis):
    """Cmd+N reste « nouvelle ligne », avec ou sans Maj comme avant."""
    assert raccourcis.shortcut_actions[Qt.Key_N][0] == "new_row"
    assert Qt.Key_N not in raccourcis.shift_shortcut_actions


# ── Résolution de la référence tapée ──

class _Texte:
    def __init__(self, t):
        self.t = t

    def text(self):
        return self.t


class _Barre:
    def __init__(self):
        self.messages = []

    def showMessage(self, m, d=0):
        self.messages.append(m)


class _Seo:
    def trouver_piece(self, ref):
        return {"as6018811": ("AS6018811", "")}.get(ref.lower())


def _fenetre(recherche):
    f = _Fenetre()
    f.search_input = _Texte(recherche)
    f.statusbar = _Barre()
    f.seo_service = _Seo()
    return f


def test_raccourci_ouvre_la_reference_ecrite_comme_en_base(monkeypatch):
    service = PieceManagementService(_fenetre("as6018811"))
    ouvertes = []
    monkeypatch.setattr(service, "completer_libelle", ouvertes.append)
    service.completer_libelle_recherche()
    assert ouvertes == ["AS6018811"]


@pytest.mark.parametrize("recherche,message", [
    ("6018811", "Libellé : aucune pièce ne correspond exactement à « 6018811 »"),
    ("", "Libellé : tapez d'abord une référence de pièce dans la recherche"),
])
def test_raccourci_sans_piece_exacte_explique(monkeypatch, recherche, message):
    fenetre = _fenetre(recherche)
    service = PieceManagementService(fenetre)
    monkeypatch.setattr(service, "completer_libelle", lambda ref: pytest.fail("ne doit pas ouvrir"))
    service.completer_libelle_recherche()
    assert fenetre.statusbar.messages == [message]
