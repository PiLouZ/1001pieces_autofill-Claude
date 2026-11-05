"""
Ouverture d'un dialogue modal SANS boucle d'événements imbriquée.

Convention du projet : `show()` + callbacks, jamais `exec_()`. `exec_()` fait
tourner Qt dans une boucle d'événements imbriquée ; sur macOS, un dialogue natif
(sélecteur de fichier, Finder…) ouvert par-dessus peut alors figer l'application
(gel corrigé en v3.14).

`ouvrir_modal` garde la modalité d'`exec_()` (le reste de l'application est
bloqué tant que le dialogue est ouvert) mais rend la main tout de suite : la
suite du traitement passe par `sur_accepte` / `sur_fin`.
"""

from typing import Callable, Optional

from .qt_imports import QDialog, QTimer

# Dialogues sans parent Qt : seule cette référence les garde en vie jusqu'à leur
# fermeture (sinon Python les détruirait dès la sortie de la fonction appelante).
_ouverts = set()


def ouvrir_modal(dialogue: QDialog,
                 sur_accepte: Optional[Callable[[], None]] = None,
                 sur_fin: Optional[Callable[[int], None]] = None) -> QDialog:
    """Afficher `dialogue` en modal (comme exec_()) sans bloquer l'appelant.

    Args:
        dialogue: le QDialog (ou QMessageBox) à afficher.
        sur_accepte: appelé sans argument si le dialogue est accepté — c'est la
            place du code qui suivait `if dlg.exec_() == QDialog.Accepted:`.
            Le dialogue est encore lisible à ce moment (selected_ref(), etc.).
        sur_fin: appelé avec le code de retour à toute fermeture.
    Le dialogue est libéré (deleteLater) une fois fermé.
    """
    if sur_accepte is not None:
        dialogue.accepted.connect(sur_accepte)
    if sur_fin is not None:
        dialogue.finished.connect(sur_fin)

    _ouverts.add(dialogue)

    def _liberer(*_):
        # Différé : selon la version de Qt, `accepted` peut être émis APRÈS
        # `finished` ; lâcher la référence ici détruirait un dialogue sans parent
        # avant que sur_accepte ne le lise. deleteLater et le retrait n'agissent
        # qu'au retour dans la boucle d'événements.
        dialogue.deleteLater()
        QTimer.singleShot(0, lambda: _ouverts.discard(dialogue))

    # Connecté en dernier : les callbacks s'exécutent avant la libération.
    dialogue.finished.connect(_liberer)
    dialogue.setModal(True)
    dialogue.show()
    return dialogue
