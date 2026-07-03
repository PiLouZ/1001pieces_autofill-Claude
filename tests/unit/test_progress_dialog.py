"""
Tests unitaires pour ProgressDialog.

NON-RÉGRESSION (bug utilisateur, vidéo du 2026-07-02) : la fenêtre se fermait
d'elle-même dès que setValue() atteignait le maximum courant, alors qu'elle est
réutilisée sur plusieurs phases successives à échelles différentes (import de
fichiers, puis recherche de suggestions, puis mise à jour de l'affichage) —
elle disparaissait après la 1ère phase pendant que les phases suivantes
tournaient encore, invisibles.
"""

import pytest
from src.ui.progress_dialog import ProgressDialog


class TestProgressDialogAutoClose:
    def test_setValue_au_maximum_ne_ferme_pas(self, qapp):
        """NON-RÉGRESSION : atteindre value == maximum ne doit plus fermer la fenêtre."""
        dlg = ProgressDialog("Titre", "Annuler", 0, 2, None)
        dlg.show()
        dlg.setValue(2)  # value == maximum
        assert dlg.isVisible()
        dlg.close()

    def test_reutilisation_multi_phases_reste_visible(self, qapp):
        """Scénario réel : phase import (0..n) atteint son maximum, puis une
        nouvelle phase (suggestions, 0..m) est lancée via setRange — la fenêtre
        doit être restée visible tout du long, jamais fermée entre les deux."""
        dlg = ProgressDialog("Import", "Annuler", 0, 2, None)
        dlg.show()

        # Phase 1 : import de 2 fichiers
        dlg.setValue(1)
        assert dlg.isVisible()
        dlg.setValue(2)  # fin de la phase 1 : ne doit PAS fermer
        assert dlg.isVisible()

        # Phase 2 : recherche de suggestions sur 150 candidats
        dlg.setRange(0, 150)
        dlg.setValue(0)
        assert dlg.isVisible()
        dlg.setValue(150)  # fin de la phase 2 : ne doit PAS fermer non plus
        assert dlg.isVisible()

        # Phase 3 : mise à jour de l'affichage — la fenêtre reste ouverte
        # jusqu'à l'appel explicite de close() par l'appelant.
        dlg.setLabelText("Mise à jour de l'affichage…")
        assert dlg.isVisible()

        dlg.close()
        assert not dlg.isVisible()

    def test_close_explicite_ferme_toujours(self, qapp):
        """La fermeture explicite (chemin normal en fin de traitement) fonctionne toujours."""
        dlg = ProgressDialog("Titre", None, 0, 10, None)
        dlg.show()
        dlg.setValue(10)
        assert dlg.isVisible()
        dlg.close()
        assert not dlg.isVisible()
