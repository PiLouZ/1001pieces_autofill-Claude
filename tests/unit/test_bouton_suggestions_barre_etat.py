"""Bouton « Suggestions à valider (N) » de la barre d'état (v3.92.0).

Il remplace le bandeau ambre au-dessus de la recherche : même compteur (nombre
d'appareils ayant une suggestion en attente), masqué à zéro, clic = fenêtre de
validation.
"""

import types

from src.ui.main_refactored import MainWindow
from src.ui.qt_imports import QPushButton
from src.ui.table_controller import TableController


def _fenetre(n):
    bouton = QPushButton()
    modele = types.SimpleNamespace(pending_suggestions_count=n)
    return types.SimpleNamespace(
        suggestions_btn=bouton,
        table_controller=types.SimpleNamespace(model=modele),
    ), bouton


def test_compteur_et_visibilite(qapp):
    fenetre, bouton = _fenetre(70)
    MainWindow._rafraichir_bouton_suggestions(fenetre)
    assert bouton.text() == "Suggestions à valider (70)"
    assert not bouton.isHidden()


def test_masque_a_zero(qapp):
    fenetre, bouton = _fenetre(0)
    bouton.setVisible(True)
    MainWindow._rafraichir_bouton_suggestions(fenetre)
    assert bouton.isHidden()


def test_sans_bouton_ni_modele_aucune_erreur():
    MainWindow._rafraichir_bouton_suggestions(types.SimpleNamespace())
    fenetre = types.SimpleNamespace(
        suggestions_btn=None, table_controller=types.SimpleNamespace(model=None))
    MainWindow._rafraichir_bouton_suggestions(fenetre)


def test_le_tableau_relaie_au_bouton():
    appels = []
    controleur = types.SimpleNamespace(parent_window=types.SimpleNamespace(
        _rafraichir_bouton_suggestions=lambda: appels.append(1)))
    TableController._update_similarity_indicator(controleur)
    assert appels == [1]


def test_relais_sans_fenetre_aucune_erreur():
    controleur = types.SimpleNamespace(parent_window=types.SimpleNamespace())
    TableController._update_similarity_indicator(controleur)
