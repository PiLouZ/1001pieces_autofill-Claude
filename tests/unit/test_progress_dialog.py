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


# ── Journal d'étapes (v3.78.0) ───────────────────────────────────────────────

from src.ui.progress_dialog import analyser_etape, meme_fichier, formater_duree


class TestAnalyserEtape:
    def test_extraction_pdf_page_et_compteur_fichier(self):
        assert analyser_etape("Extraction de a.pdf : page 560/1667 (1/1)") == \
            ("Extraction de a.pdf", "page 560 / 1 667", 1667)

    def test_compteur_entre_parentheses(self):
        assert analyser_etape("Recherche de suggestions… (12/17)") == \
            ("Recherche de suggestions", "12 / 17", None)

    def test_libelle_simple(self):
        assert analyser_etape("Pré-chargement du cache…") == ("Pré-chargement du cache", "", None)

    def test_vide(self):
        assert analyser_etape("") == ("", "", None)

    def test_nom_de_fichier_numerique_conserve(self):
        """Les chiffres du NOM de fichier ne sont pas pris pour un compteur."""
        assert analyser_etape("Import de 00611388.pdf… (2/3)")[0] == "Import de 00611388.pdf"


class TestEtapeTiretDetail:
    def test_copie_fichier_par_fichier_reste_une_etape(self, qapp):
        """Export de l'application : un message par fichier copié ne doit pas
        créer une ligne par fichier dans le journal."""
        dlg = ProgressDialog("Export de l'application", None, 0, 0, None)
        dlg.setLabelText("Copie du code source…")
        for f in ("src/a.py", "src/ui/b.py", "src/ui/c.py"):
            dlg.setLabelText(f"Copie du code source — {f}")
        dlg.setLabelText("Génération de requirements_frozen.txt…")
        assert [e['etape'] for e in dlg._etapes] == ["Copie du code source",
                                                     "Génération de requirements_frozen.txt"]
        dlg.close()

    def test_detail_long_abrege_par_la_gauche(self):
        etape, detail, _ = analyser_etape("Copie du code source — " + "x/" * 30 + "fin.py")
        assert etape == "Copie du code source"
        assert detail.startswith("…") and detail.endswith("fin.py") and len(detail) == 40


class TestMemeFichier:
    def test_import_puis_extraction_du_meme_fichier(self):
        assert meme_fichier("Import de 00611388.pdf", "Extraction de 00611388.pdf")

    def test_fichiers_differents(self):
        assert not meme_fichier("Extraction de a.pdf", "Extraction de b.pdf")

    def test_etapes_sans_fichier(self):
        assert not meme_fichier("Recherche de suggestions", "Préparation de l'index de suggestions")


class TestFormaterDuree:
    def test_formats(self):
        assert formater_duree(0.42) == "0,4 s"
        assert formater_duree(48.3) == "48 s"
        assert formater_duree(125) == "2 min 05 s"


class TestJournal:
    def test_sequence_import_reelle(self, qapp):
        """Séquence émise par un import PDF : une ligne par étape, l'extraction
        fusionnée avec « Import de », compteurs mis à jour sans nouvelle ligne."""
        dlg = ProgressDialog("Importation en cours", "Annuler", 0, 1, None)
        for lbl in ["Pré-chargement du cache…",
                    "Import de a.pdf… (1/1)",
                    "Extraction de a.pdf : page 1/3 (1/1)",
                    "Extraction de a.pdf : page 3/3 (1/1)",
                    "Finalisation…",
                    "Préparation de l'index de suggestions…",
                    "Recherche de suggestions… (0/17)",
                    "Recherche de suggestions… (17/17)",
                    "Mise à jour de l'affichage…"]:
            dlg.setLabelText(lbl)
        etapes = [e['etape'] for e in dlg._etapes]
        assert etapes == ["Pré-chargement du cache", "Extraction de a.pdf", "Finalisation",
                          "Préparation de l'index de suggestions", "Recherche de suggestions",
                          "Mise à jour de l'affichage"]
        # Toutes terminées sauf la dernière ; total de pages retenu pour l'extraction
        assert [e['fin'] is not None for e in dlg._etapes] == [True] * 5 + [False]
        assert dlg._etapes[1]['pages'] == 3
        assert dlg._etapes[1]['widgets'][1].text() == "Extraction de a.pdf · 3 pages"
        dlg.close()
