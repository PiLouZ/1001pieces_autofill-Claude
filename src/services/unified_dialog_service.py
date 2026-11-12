"""
Service de dialogues unifié - Refactorisation Phase 2
Consolidation de DialogService (simple) et DialogService (complexe)

RESPONSABILITÉS UNIFIÉES :
- Dialogues simples : Catégories, Notes (méthodes statiques)
- Dialogues complexes : Import, Autocomplétion, Références (méthodes d'instance)
- Factory pattern pour création optimisée
- Interface cohérente pour toute l'application

ARCHITECTURE :
- UnifiedDialogService : Service principal avec factory et instances
- Dialogues simples : Méthodes statiques sans dépendances
- Dialogues complexes : Méthodes d'instance avec accès à main_window
"""

from typing import Callable, Optional, Dict, Any, List
from ..utils.qt_imports import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QFrame,
    QSize,
    QComboBox
)
from ..utils.qt_imports import Qt
from ..utils.qt_imports import QFont
from ..utils.boites import saisir_texte

from ..core.logger import app_logger
from functools import wraps
from ..ui.style_manager import StyleManager

def _handle_dialog_errors(default_return=None, context="Dialogue"):
    """
    Décorateur pour gérer les erreurs des dialogues Qt
    Pattern: Log l'erreur et retourne une valeur par défaut
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                app_logger.error(f"Erreur {context}: {e}")
                return default_return
        return wrapper
    return decorator

class SimpleDialogs:
    """
    Dialogues simples - Méthodes statiques sans dépendances UI complexes
    
    Ces dialogues peuvent être utilisés partout sans instanciation
    """
    
    @staticmethod
    @_handle_dialog_errors(default_return=None, context="dialogue catégories")
    def get_categories(parent, current_categories: List[str],
                       sur_categories: Callable[[List[str]], None]) -> None:
        """
        Dialogue de gestion des catégories (modal non bloquant, jamais de boucle
        imbriquée).

        Args:
            parent: Widget parent
            current_categories: Liste des catégories actuelles
            sur_categories: appelé avec la nouvelle liste si l'utilisateur valide
        """
        def _valider(text):
            categories = [line.strip() for line in text.split('\n') if line.strip()]
            app_logger.debug(f"Catégories sélectionnées: {categories}")
            sur_categories(categories)

        saisir_texte(parent, "Gestion des Catégories",
                     "Entrez les catégories (une par ligne) :",
                     '\n'.join(current_categories) if current_categories else "",
                     _valider, multiligne=True)
    
class ComplexDialogs:
    """
    Dialogues complexes - Méthodes d'instance avec accès à l'application
    
    Ces dialogues nécessitent une instance et accès à main_window
    """
    
    def __init__(self, main_window):
        self.main_window = main_window
    
    @_handle_dialog_errors(default_return=None, context="dialogue sélection référence")
    def show_reference_selection_dialog(self, title: str, message: str,
                                      default_reference: str = "",
                                      destination: Optional[Dict[str, Any]] = None,
                                      bouton_valider: str = "OK",
                                      produits: Optional[List[Dict[str, Any]]] = None,
                                      choix: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Dialogue de saisie de la référence d'export.

        Args:
            title: Titre de la fenêtre
            message: Phrase d'aide affichée sous le champ
            default_reference: Référence pré-remplie et pré-sélectionnée
            destination: Pour les exports qui écrivent un fichier, un dict
                {'dossier': str, 'nom_fichier': callable(ref) -> str,
                 'changer': callable() -> str | None}. Affiche le dossier et le
                nom du fichier qui sera écrit, recalculé à chaque frappe.
                None pour les exports sans fichier (HTML → presse-papier).
            bouton_valider: Libellé du bouton de validation
            produits: Produits du site de la pièce ({'ref_interne', 'id_product'}) ;
                plusieurs → liste « Produit du site » qui remplit le champ
            choix: Reçoit le produit retenu sous 'produit'

        Returns:
            Référence saisie, ou None si annulé
        """
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(520)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 12)

        # ── Le champ d'abord : c'est la seule action de cette fenêtre ────────
        titre_champ = QLabel("Référence d'export")
        police = QFont()
        police.setBold(True)
        titre_champ.setFont(police)
        layout.addWidget(titre_champ)

        ref_input = QLineEdit(default_reference)
        ref_input.setPlaceholderText("Entrez la référence…")
        ref_input.setStyleSheet("QLineEdit { padding: 6px; font-size: 13px; }")

        # Plusieurs produits du site pour la pièce : le choix remplit le champ
        if produits and len(produits) > 1:
            liste = QComboBox()
            liste.setObjectName("produits_site")
            for p in produits:
                numero = f"  ·  n° {p['id_product']} sur le site" if p.get('id_product') else ""
                liste.addItem(f"{p['ref_interne']}{numero}", p)
            liste.setToolTip("Produit du site qui sert à cet export")

            def _produit_choisi(index):
                produit = liste.itemData(index)
                if choix is not None:
                    choix['produit'] = produit
                if produit:
                    ref_input.setText(produit['ref_interne'])
            liste.currentIndexChanged.connect(_produit_choisi)
            ligne_produit = QHBoxLayout()
            ligne_produit.addWidget(QLabel("Produit du site :"))
            ligne_produit.addWidget(liste, 1)
            layout.addLayout(ligne_produit)
        layout.addWidget(ref_input)

        if message:
            aide = QLabel(message)
            aide.setWordWrap(True)
            aide.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
            layout.addWidget(aide)

        # ── Bloc destination (exports fichier uniquement) ────────────────────
        if destination:
            layout.addWidget(self._separateur_horizontal())
            bloc, maj_nom_fichier = self._bloc_destination(destination, ref_input)
            layout.addWidget(bloc)
            ref_input.textChanged.connect(maj_nom_fichier)

        # ── Boutons ──────────────────────────────────────────────────────────
        pied = QHBoxLayout()
        pied.addStretch()
        annuler = QPushButton("Annuler")
        annuler.clicked.connect(dialog.reject)
        valider = QPushButton(bouton_valider)
        valider.setDefault(True)
        valider.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        valider.clicked.connect(dialog.accept)
        pied.addWidget(annuler)
        pied.addWidget(valider)
        layout.addLayout(pied)

        dialog.setLayout(layout)
        ref_input.setFocus()
        ref_input.selectAll()

        if dialog.exec_() == QDialog.Accepted:
            reference = ref_input.text().strip()
            if reference:
                app_logger.debug(f"Référence sélectionnée: {reference}")
                return reference

        return None

    @staticmethod
    def _separateur_horizontal() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(StyleManager.TEXTE_SEPARATEUR)
        return sep

    def _bloc_destination(self, destination: Dict[str, Any], ref_input: QLineEdit):
        """Bloc « où ira le fichier » : dossier, nom réel, et lien pour changer.

        Retourne (widget, callback de mise à jour du nom de fichier).
        """
        import qtawesome as qta

        bloc = QWidget()
        bloc.setStyleSheet(
            "QWidget { background: #f8f9fa; border: 1px solid #e9ecef;"
            " border-radius: 4px; }"
        )
        ligne = QHBoxLayout(bloc)
        ligne.setContentsMargins(10, 8, 10, 8)
        ligne.setSpacing(8)

        icone = QLabel()
        icone.setPixmap(qta.icon('fa5s.folder-open', color='#6c757d').pixmap(QSize(16, 16)))
        icone.setStyleSheet(StyleManager.SANS_BORDURE)
        icone.setAlignment(Qt.AlignTop)
        ligne.addWidget(icone)

        colonne = QVBoxLayout()
        colonne.setSpacing(2)
        lbl_dossier = QLabel(destination.get('dossier', ''))
        lbl_dossier.setStyleSheet("color: #6c757d; font-size: 11px; border: none;")
        lbl_fichier = QLabel()
        police = QFont()
        police.setBold(True)
        lbl_fichier.setFont(police)
        lbl_fichier.setStyleSheet("color: #212529; font-size: 12px; border: none;")
        colonne.addWidget(lbl_dossier)
        colonne.addWidget(lbl_fichier)
        ligne.addLayout(colonne, 1)

        nom_pour = destination.get('nom_fichier')

        def maj_nom_fichier(texte=None):
            ref = (texte if texte is not None else ref_input.text()).strip()
            lbl_fichier.setText(nom_pour(ref or '…') if nom_pour else '')

        maj_nom_fichier()

        changer = destination.get('changer')
        if changer:
            btn = QPushButton("Changer…")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { border: none; background: transparent;"
                " color: #0066cc; font-size: 11px; }"
                "QPushButton:hover { text-decoration: underline; }"
            )

            def _changer():
                nouveau = changer()
                if nouveau:
                    lbl_dossier.setText(nouveau)

            btn.clicked.connect(_changer)
            ligne.addWidget(btn, 0, Qt.AlignTop)

        return bloc, maj_nom_fichier
    
class UnifiedDialogService:
    """
    Service de dialogues unifié - Interface principale
    
    Combine dialogues simples (statiques) et complexes (instance)
    Factory pattern pour optimiser l'utilisation
    """
    
    def __init__(self, main_window=None):
        """
        Initialiser le service unifié
        
        Args:
            main_window: Instance optionnelle pour dialogues complexes
        """
        self.main_window = main_window
        self._complex_dialogs = None
    
    @property
    def complex(self) -> ComplexDialogs:
        """Accès lazy aux dialogues complexes"""
        if self._complex_dialogs is None:
            if self.main_window is None:
                raise ValueError("main_window requis pour les dialogues complexes")
            self._complex_dialogs = ComplexDialogs(self.main_window)
        return self._complex_dialogs
    
    # Délégation aux dialogues simples (méthodes statiques)
    @staticmethod
    def get_categories(parent, current_categories: List[str],
                       sur_categories: Callable[[List[str]], None]) -> None:
        """Dialogue de gestion des catégories (non bloquant)"""
        return SimpleDialogs.get_categories(parent, current_categories, sur_categories)
    
    # Délégation aux dialogues complexes (méthodes d'instance)
    def show_reference_selection_dialog(self, title: str, message: str, 
                                      default_reference: str = "",
                                      destination: Optional[Dict[str, Any]] = None,
                                      bouton_valider: str = "OK",
                                      produits: Optional[List[Dict[str, Any]]] = None,
                                      choix: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Dialogue de saisie de la référence d'export"""
        return self.complex.show_reference_selection_dialog(
            title, message, default_reference, destination, bouton_valider,
            produits=produits, choix=choix,
        )
    
    # Factory methods pour compatibilité avec l'ancien code

# Backward compatibility aliases pour migration facile
DialogService = UnifiedDialogService