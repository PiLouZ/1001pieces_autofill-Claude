"""
Boîtes de dialogue standard SANS boucle d'événements imbriquée.

Les fonctions statiques de Qt (`QMessageBox.question`, `QFileDialog.getSaveFileName`,
`QInputDialog.getText`…) font tourner une boucle d'événements imbriquée, comme
`exec_()`. Sur macOS, un sélecteur de fichiers NATIF ouvert ainsi peut figer
l'application (gel corrigé en v3.14). Ces équivalents gardent la modalité mais
rendent la main tout de suite : la réponse arrive par rappel.

Correspondances :
    QMessageBox.question(...)        → demander_oui_non(..., sur_oui)
    QFileDialog.getExistingDirectory → choisir_dossier(..., sur_chemin)
    QFileDialog.getOpenFileName      → choisir_fichier_a_ouvrir(..., sur_chemin)
    QFileDialog.getSaveFileName      → choisir_fichier_a_enregistrer(..., sur_chemin)
    QInputDialog.getText / getMultiLineText → saisir_texte(..., sur_texte)
    QInputDialog.getItem             → choisir_element(..., sur_element)

Le rappel n'est appelé que si l'utilisateur valide (Oui, un chemin, OK) — jamais
à l'annulation, ce qui correspond au `if not ok: return` des appels statiques.
"""

from typing import Callable, List, Optional

from .ouverture_modale import ouvrir_modal
from .qt_imports import QFileDialog, QInputDialog, QMessageBox


def demander_oui_non(parent, titre: str, message: str,
                     sur_oui: Callable[[], None],
                     sur_non: Optional[Callable[[], None]] = None,
                     defaut=QMessageBox.No,
                     icone=QMessageBox.Question) -> QMessageBox:
    """Équivalent de `QMessageBox.question(parent, titre, message, Yes | No, defaut)`.

    defaut : bouton par défaut (QMessageBox.No par défaut, comme les appels du
    projet) ; None laisse Qt choisir, comme un appel statique sans défaut.
    Échap ou la croix valent « Non ».
    """
    boite = QMessageBox(icone, titre, message, QMessageBox.Yes | QMessageBox.No, parent)
    if defaut is not None:
        boite.setDefaultButton(defaut)
    # Échap = « Non », comme l'appel statique (qui le détecte via le rôle NoRole)
    boite.setEscapeButton(QMessageBox.No)

    def _sur_fin(_code):
        bouton = boite.clickedButton()
        reponse = boite.standardButton(bouton) if bouton is not None else QMessageBox.No
        if reponse == QMessageBox.Yes:
            sur_oui()
        elif sur_non is not None:
            sur_non()

    ouvrir_modal(boite, sur_fin=_sur_fin)
    return boite


def _selecteur(parent, titre: str, dossier: str, filtre: str, mode, accepter,
               sur_chemin: Callable[[str], None]) -> QFileDialog:
    dialogue = QFileDialog(parent, titre, dossier or "", filtre or "")
    dialogue.setFileMode(mode)
    dialogue.setAcceptMode(accepter)
    if mode == QFileDialog.Directory:
        dialogue.setOption(QFileDialog.ShowDirsOnly, True)

    def _sur_accepte():
        fichiers = dialogue.selectedFiles()
        if fichiers and fichiers[0]:
            sur_chemin(fichiers[0])

    ouvrir_modal(dialogue, sur_accepte=_sur_accepte)
    return dialogue


def choisir_dossier(parent, titre: str, dossier: str,
                    sur_chemin: Callable[[str], None]) -> QFileDialog:
    """Équivalent de `QFileDialog.getExistingDirectory(parent, titre, dossier)`."""
    return _selecteur(parent, titre, dossier, "", QFileDialog.Directory,
                      QFileDialog.AcceptOpen, sur_chemin)


def choisir_fichier_a_ouvrir(parent, titre: str, dossier: str, filtre: str,
                             sur_chemin: Callable[[str], None]) -> QFileDialog:
    """Équivalent de `QFileDialog.getOpenFileName(parent, titre, dossier, filtre)`."""
    return _selecteur(parent, titre, dossier, filtre, QFileDialog.ExistingFile,
                      QFileDialog.AcceptOpen, sur_chemin)


def choisir_fichier_a_enregistrer(parent, titre: str, chemin: str, filtre: str,
                                  sur_chemin: Callable[[str], None]) -> QFileDialog:
    """Équivalent de `QFileDialog.getSaveFileName(parent, titre, chemin, filtre)`
    (chemin : dossier ou nom de fichier proposé)."""
    return _selecteur(parent, titre, chemin, filtre, QFileDialog.AnyFile,
                      QFileDialog.AcceptSave, sur_chemin)


def saisir_texte(parent, titre: str, libelle: str, texte: str,
                 sur_texte: Callable[[str], None],
                 multiligne: bool = False) -> QInputDialog:
    """Équivalent de `QInputDialog.getText` (ou `getMultiLineText`) : sur_texte
    reçoit le texte saisi si l'utilisateur valide."""
    dialogue = QInputDialog(parent)
    dialogue.setWindowTitle(titre)
    dialogue.setLabelText(libelle)
    dialogue.setInputMode(QInputDialog.TextInput)
    if multiligne:
        dialogue.setOption(QInputDialog.UsePlainTextEditForTextInput, True)
    dialogue.setTextValue(texte or "")
    ouvrir_modal(dialogue, sur_accepte=lambda: sur_texte(dialogue.textValue()))
    return dialogue


def choisir_element(parent, titre: str, libelle: str, elements: List[str],
                    sur_element: Callable[[str], None],
                    courant: int = 0, modifiable: bool = True) -> QInputDialog:
    """Équivalent de `QInputDialog.getItem(parent, titre, libelle, elements,
    courant, modifiable)` : sur_element reçoit l'élément choisi si validé."""
    dialogue = QInputDialog(parent)
    dialogue.setWindowTitle(titre)
    dialogue.setLabelText(libelle)
    dialogue.setComboBoxItems(list(elements))
    dialogue.setComboBoxEditable(modifiable)
    if elements and 0 <= courant < len(elements):
        dialogue.setTextValue(elements[courant])
    ouvrir_modal(dialogue, sur_accepte=lambda: sur_element(dialogue.textValue()))
    return dialogue
