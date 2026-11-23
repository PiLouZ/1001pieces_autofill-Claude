"""
Gestionnaire d'importation unifié pour l'application de gestion d'appareils
Factorisation du code d'importation avec support des libellés hiérarchiques
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
from enum import Enum
import os
import time as _time
from datetime import datetime

from ..utils.qt_imports import QApplication, QThread, pyqtSignal

from .logger import app_logger
from ..utils.error_handler import handle_ui_operation_errors, handle_database_operation_errors
from ..utils.text_utils import decouper_refs



class ImportType(Enum):
    """Types d'import supportés"""
    SINGLE_FILE = "single_file"
    MULTI_FILE = "multi_file"
    

class FileType(Enum):
    """Types de fichiers supportés"""
    CSV = "csv"
    PDF = "pdf"
    CLIPBOARD = "clipboard"  # Données issues du presse-papiers (v3.31.0)
    # Fiche du site 1001pieces.com (CDC fiches du site § 10.12) : lignes déjà lues et
    # identifiées (dict par ligne, cf. ImportManager.CLE_APPAREIL / CLE_IDENTITE)
    FICHE_SITE = "fiche_site"


@dataclass
class ImportFile:
    """Représente un fichier à importer"""
    path: str
    type: FileType
    suggested_reference: str
    suggested_label: str = None
    data: List[List[str]] = None
    # Fiche du site (FileType.FICHE_SITE) : lecture et plan, pour la fenêtre d'import
    # (aperçu, Succession préremplie) ; cf. EnregistrementFicheService.FicheAImporter
    fiche: Any = None
    
    @property
    def filename(self) -> str:
        return os.path.basename(self.path)
    
    @property
    def name_without_ext(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]


@dataclass
class LabelConfiguration:
    """Configuration pour les libellés"""
    use_common_label: bool = False
    common_label: str = ""
    individual_labels: Dict[str, str] = None  # {file_path: label}
    
    def __post_init__(self):
        if self.individual_labels is None:
            self.individual_labels = {}


@dataclass
class ImportConfiguration:
    """Configuration complète d'un import"""
    files: List[ImportFile]
    import_type: ImportType
    common_reference: Optional[str] = None
    use_common_reference: bool = False
    label_config: LabelConfiguration = None
    
    # Nouveau: séparation claire références vs libellés
    individual_references: Dict[str, str] = None  # {file_path: reference} - toujours nom fichier
    individual_labels: Dict[str, str] = None      # {file_path: label} - ce que tape l'utilisateur
    common_label: str = ""                        # Libellé de la référence commune
    
    # Options d'import technique
    csv_import_mode: int = 2  # 1, 2, 3+ colonnes
    third_column_choice: str = "ignore"
    has_headers: bool = False

    # Aperçu (dry-run) avant import définitif — désactivé par défaut (trop lent)
    show_preview: bool = False

    # Succession déclarée lors de l'import (optionnel)
    # `succession_replaces` et `equivalence_ref` acceptent PLUSIEURS réfs (v3.91.0) :
    # liste, ou chaîne à réfs séparées par des espaces (normalisées par decouper_refs).
    # `succession_replaced_by` reste UNIQUE : piece_supersessions.ref_old est clé
    # primaire, une réf ne peut être remplacée que par une seule autre.
    succession_replaces: Optional[Union[str, List[str]]] = None  # Réfs existantes que cette réf remplace (ref_old=existing, ref_new=imported)
    succession_replaced_by: Optional[str] = None    # Réf existante qui remplace cette réf (ref_old=imported, ref_new=existing)
    equivalence_ref: Optional[Union[str, List[str]]] = None      # Fichier unique : réfs existantes équivalentes à cette réf

    # Références à marquer obsolètes lors de l'import
    obsolete_refs: Optional[List[str]] = None       # Réfs à marquer comme obsolètes après import

    # Modèle « par groupes » (nouveau panneau de relations) — si renseigné, il PRIME
    # sur les champs succession_*/equivalence_ref/obsolete_refs ci-dessus.
    relations_groups: Optional[List] = None         # List[import_relations.Group]
    relations_cards: Optional[List] = None           # List[import_relations.CardData]

    # Mapping personnalisé des colonnes (v3.30.0)
    # None = comportement positionnel actuel (défaut, zéro régression)
    # Clé   : nombre de colonnes du groupe de fichiers
    # Valeur : liste de N destinations (une par colonne détectée)
    # Exemple : {3: ["commercial_ref", "ref_modele", "ignore"]}
    column_mapping: Optional[Dict[int, List[str]]] = None

    # Écritures propres à une source, faites après les appareils, les liens et les
    # relations, dans le même thread : apres_ecriture(import_manager, results).
    # Jamais appelé en simulation. Les fiches du site y écrivent leur provenance,
    # leurs origines et leur produit du site (CDC fiches du site § 10.12).
    apres_ecriture: Optional[Callable[['ImportManager', Dict[str, Any]], None]] = None
    # Lot de fiches du site (cartes) : saisies de chaque carte, par chemin de fichier
    # (importer, ref, libelle, remplace, remplacee_par, equivalentes, obsolete)
    saisies_fiches: Optional[Dict[str, Dict[str, Any]]] = None
    # Référence associée Whirlpool / Indesit / Beko répondue dans la fenêtre :
    # réf. de pièce → référence associée, ou None (« aucune ») ; CDC fiches § 10.17
    references_associees: Optional[Dict[str, Optional[str]]] = None
    # Groupe déclaré (Whirlpool / Indesit / Beko) des réf. hors des formats connus
    origines_declarees: Optional[Dict[str, str]] = None

    def __post_init__(self):
        if self.label_config is None:
            self.label_config = LabelConfiguration()
        if self.individual_references is None:
            self.individual_references = {}
        if self.individual_labels is None:
            self.individual_labels = {}
        if self.obsolete_refs is None:
            self.obsolete_refs = []


@dataclass
class _LotBatch:
    """État du classement d'un fichier (ÉTAPE 2 de l'import par lots), transmis à
    l'écriture (ÉTAPE 3). first_occurrence_by_key et processed_line_index sont
    locaux au fichier, contrairement à seen_device_refs partagé entre fichiers."""
    new_devices_batch: List[Dict[str, Any]] = field(default_factory=list)
    cles_nouveaux: List[str] = field(default_factory=list)   # clé d'identité, parallèle à new_devices_batch
    existing_updates: List[Tuple[int, Dict[str, Any]]] = field(default_factory=list)
    completions: List[Tuple[int, Dict[str, Any], Dict[str, str]]] = field(default_factory=list)  # Type/Fabricant vides en base
    associations_batch: List[Tuple] = field(default_factory=list)
    processed_line_index: int = 0  # lignes réellement traitées (hors continue)
    # 1ʳᵉ occurrence de chaque clé DANS CE FICHIER : {device_key: (data_index, existing_id)}
    first_occurrence_by_key: Dict[Any, Tuple[int, Optional[int]]] = field(default_factory=dict)


class _ImportWorker(QThread):
    """Thread d'import — exécute _run_import_files() hors du main thread.
    Émet progress_updated pour mettre à jour la ProgressDialog sur le main thread,
    et finished quand le traitement est terminé."""

    progress_updated = pyqtSignal(int, int, str)   # value, maximum, label
    finished         = pyqtSignal(dict)
    error_occurred   = pyqtSignal(str)

    def __init__(self, manager, config, dry_run=False):
        super().__init__()
        self._manager  = manager
        self._config   = config
        self._canceled = False
        self._dry_run  = dry_run

    def cancel(self):
        self._canceled = True

    def run(self):
        try:
            results = self._manager._run_import_files(
                self._config,
                progress_cb=lambda v, m, lbl: self.progress_updated.emit(v, m, lbl),
                cancel_check=lambda: self._canceled,
                dry_run=self._dry_run,
            )
            self.finished.emit(results or {'total_files': 0, 'successful_files': 0,
                                           'total_imported': 0, 'errors': []})
        except Exception as e:
            app_logger.error(f"_ImportWorker: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class _ImportPreviewWorker(QThread):
    """Thread d'analyse dry-run — même pipeline que _ImportWorker mais sans écriture DB.
    Émet preview_ready avec les comptages simulés pour ImportPreviewDialog."""

    progress_updated = pyqtSignal(int, int, str)
    preview_ready    = pyqtSignal(dict)
    error_occurred   = pyqtSignal(str)

    def __init__(self, manager, config):
        super().__init__()
        self._manager  = manager
        self._config   = config
        self._canceled = False

    def cancel(self):
        self._canceled = True

    def run(self):
        try:
            results = self._manager._run_import_files(
                self._config,
                progress_cb=lambda v, m, lbl: self.progress_updated.emit(v, m, lbl),
                cancel_check=lambda: self._canceled,
                dry_run=True,
            )
            self.preview_ready.emit(results or {})
        except Exception as e:
            app_logger.error(f"_ImportPreviewWorker: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class ImportManager:
    """Gestionnaire unifié pour tous les types d'imports"""
    
    def __init__(self, db_manager, parent_widget=None):
        self.db_manager = db_manager
        self.parent_widget = parent_widget
        self.main_window = parent_widget  # Pour accès aux services

        # PHASE 1.2 OPTIMISATION: Cache des métadonnées fichiers
        # Clé: (file_path, mtime), Valeur: sample_data
        # Évite de recharger les mêmes fichiers
        self._file_metadata_cache = {}

        # Compteurs de log agrégés (v3.66.0) : les messages par-appareil sont
        # comptés puis journalisés en une seule ligne, au lieu d'une ligne chacun.
        # Initialisés ici car _try_auto_complete est aussi appelable hors import.
        self._log_counters = self._nouveaux_compteurs_log()
        # État de session (réinitialisé à chaque import, cf. _reinitialiser_etat_session) ;
        # posé ici aussi pour les appels directs du chemin batch (tests, briques)
        self._ids_session = {}
        self._resultats_par_fichier = {}
        self._index_par_id = None

        # Casse alignée sur la base : marques (v3.82.0, « DELTA » → « Delta ») et
        # types (v3.83.0, « CHAUFFAGE » → « Chauffage »)
        from ..services.casse_normalisation_service import CasseNormalisationService
        self._marques = CasseNormalisationService(db_manager, 'manufacturer')
        self._types = CasseNormalisationService(db_manager, 'type')
        # Typage par les règles de nomenclature validées (CDC § 8.3, lot 5)
        from ..services.typage_import_service import TypageImportService
        self._typage = TypageImportService(db_manager)

    @staticmethod
    def _nouveaux_compteurs_log() -> Dict[str, int]:
        """Compteurs de log remis à zéro (un jeu par import)."""
        return {'autocomplete_type': 0, 'autocomplete_manufacturer': 0}
    
    def load_csv_data(self, file_path: str, max_rows: Optional[int] = None) -> List[List[str]]:
        """
        Méthode unifiée pour le chargement CSV avec limite optionnelle
        
        Args:
            file_path: Chemin vers le fichier CSV
            max_rows: Nombre maximum de lignes à charger (None = toutes)
            
        Returns:
            Liste des lignes (chaque ligne est une liste de cellules)
            
        Raises:
            ValueError: Si le fichier ne peut pas être lu
        """
        import csv
        
        # Détection de l'encodage
        encodings = ['utf-8', 'latin1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    # Détection du séparateur
                    sample = f.read(1024)
                    f.seek(0)
                    
                    sniffer = csv.Sniffer()
                    try:
                        delimiter = sniffer.sniff(sample, delimiters=';,\t').delimiter
                    except csv.Error:
                        delimiter = ';'
                    
                    reader = csv.reader(f, delimiter=delimiter)
                    rows = []
                    
                    for i, row in enumerate(reader):
                        # Appliquer la limite si spécifiée
                        if max_rows is not None and i >= max_rows:
                            break
                        
                        # Ignorer les lignes vides
                        if any(cell.strip() if cell is not None else False for cell in row):
                            rows.append(row)
                    
                    return rows
                    
            except (UnicodeDecodeError, FileNotFoundError, IOError) as e:
                # FileNotFoundError : fichier n'existe pas
                # IOError : problème d'accès au fichier  
                # UnicodeDecodeError : problème d'encodage -> essayer le suivant
                if isinstance(e, FileNotFoundError):
                    # Fichier n'existe pas, arrêter immédiatement
                    break
                elif isinstance(e, UnicodeDecodeError):
                    # Problème d'encodage, essayer le suivant
                    continue
                else:
                    # Autre erreur IO, arrêter
                    break
        
        # Si on arrive ici, aucun encodage n'a fonctionné
        raise ValueError(f"Impossible de lire le fichier CSV: {file_path} (fichier introuvable ou format invalide)")
    
    def load_pdf_data(self, file_path: str, max_rows: Optional[int] = None, preview_mode: bool = False,
                      progress_cb: Optional[Callable] = None, cancel_check: Optional[Callable] = None,
                      pages_vides_out: Optional[List[Dict]] = None) -> List[List[str]]:
        """
        Méthode unifiée pour le chargement PDF avec limite optionnelle

        Args:
            file_path: Chemin vers le fichier PDF
            max_rows: Nombre maximum de lignes à charger (None = toutes)
            preview_mode: Si True, charge seulement la 1ère page (10x plus rapide)
            pages_vides_out: liste à remplir avec les pages vides détectées
                             (fourchettes de références où des appareils manquent).
                             Paramètre de sortie et non attribut : l'aperçu tourne
                             dans un autre thread et ne doit pas écraser l'information
                             d'un import en cours.

        Returns:
            Liste des lignes extraites du PDF

        Raises:
            ValueError: Si le fichier ne peut pas être traité

        Notes:
            PHASE 1 OPTIMISATION: preview_mode=True réduit drastiquement le temps
            de chargement pour les aperçus de dialogue
        """
        try:
            from src.data.pdf_extractor_camelot import CamelotPDFExtractor
            extractor = CamelotPDFExtractor()
            data = extractor.extract_data(file_path, preview_mode=preview_mode,
                                            progress_cb=progress_cb, cancel_check=cancel_check)
            if pages_vides_out is not None:
                pages_vides_out.extend((extractor.last_extraction_info or {}).get('pages_vides', []))

            if not data:
                return []

            # Appliquer la limite si spécifiée
            if max_rows is not None:
                return data[:max_rows]
            else:
                return data

        except ImportError as e:
            raise ValueError(f"Extracteur PDF non disponible: {e}")
        except Exception as e:
            raise ValueError(f"Erreur lors de l'extraction PDF: {e}")
    
    def import_files(self, file_paths: List[str], show_dialog: bool = True, callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """
        Importer un ou plusieurs fichiers

        Args:
            file_paths: Liste des chemins de fichiers
            show_dialog: Afficher l'interface de configuration
            callback: Fonction appelée avec les résultats (pour mode non-bloquant)

        Returns:
            Avec show_dialog : None immédiatement — le dialogue est non bloquant et
            les résultats sont passés au callback. Sans dialogue : les résultats.
        """
        # PHASE 2.1 OPTIMISATION: Lazy loading - NE PAS charger les données ici
        # Les données seront chargées en différé dans le dialogue
        # Ceci élimine complètement le freeze AVANT l'ouverture du dialogue

        # Préparer la configuration RAPIDEMENT (sans chargement de données)
        import_files = []
        for path in file_paths:
            file_type = self._detect_file_type(path)
            if file_type:
                import_file = ImportFile(
                    path=path,
                    type=file_type,
                    suggested_reference=self._extract_reference_from_filename(path),
                    suggested_label=self._extract_reference_from_filename(path),
                    data=None  # PHASE 2.1: Pas de données - chargement lazy dans le dialogue
                )
                import_files.append(import_file)
        
        if not import_files:
            return None
        
        # Déterminer le type d'import
        import_type = ImportType.SINGLE_FILE if len(import_files) == 1 else ImportType.MULTI_FILE
        
        config = ImportConfiguration(
            files=import_files,
            import_type=import_type
        )
        
        if show_dialog:
            # PHASE 2.1: Passer import_manager pour lazy loading
            from ..ui.fenetre_import import ImportDialog
            dialog = ImportDialog(self.parent_widget, config, import_manager=self)

            # Non bloquant (show, jamais exec_) : résultat via callback
            dialog.accepted.connect(lambda: self._on_dialog_accepted(dialog, callback, 'import'))
            dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
            dialog.show()
            return None

        # PHASE 1: Décision intelligente Async vs Sync avec fallback automatique
        return self._execute_import(config)

    def import_from_clipboard(self, rows: List[List[str]], callback: Optional[Callable] = None) -> None:
        """
        Ouvrir ImportDialog alimenté par les données du presse-papiers (v3.31.0).
        Même expérience que l'import de fichier : aperçu, mapping, référence de pièce.

        Args:
            rows: Données déjà parsées du presse-papiers
            callback: Fonction appelée avec les résultats (mode non-bloquant)
        """
        import_file = ImportFile(
            path="Collage",
            type=FileType.CLIPBOARD,
            suggested_reference="",
            suggested_label="",
            data=rows  # Données pré-chargées — le lazy loading les utilisera directement
        )
        config = ImportConfiguration(
            files=[import_file],
            import_type=ImportType.SINGLE_FILE
        )
        from ..ui.fenetre_import import ImportDialog
        dialog = ImportDialog(self.parent_widget, config, import_manager=self)
        # Non bloquant (show, jamais exec_) : résultat via callback
        dialog.accepted.connect(lambda: self._on_dialog_accepted(dialog, callback, 'import'))
        dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
        dialog.show()

    def importer_avec_dialogue(self, config: ImportConfiguration, callback: Optional[Callable] = None,
                               preparer: Optional[Callable] = None, titre: str = '') -> None:
        """Ouvre la fenêtre d'import sur une configuration déjà faite (fiche du site).
        `preparer(configuration validée)` → (configuration de l'import réel, fin) :
        `fin(results)` est appelée sur le thread principal avant `callback`."""
        from ..ui.fenetre_import import ImportDialog
        dialog = ImportDialog(self.parent_widget, config, import_manager=self)
        if titre:
            dialog.setWindowTitle(titre)

        def _acceptee():
            validee = dialog.get_configuration()
            if not validee or preparer is None:
                self._on_dialog_accepted(dialog, callback, 'import')
                return
            try:
                reelle, fin = preparer(validee)
            except Exception as e:
                app_logger.error(f"Préparation de l'import impossible : {e}", exc_info=True)
                if callback:
                    callback(None)
                dialog.deleteLater()
                return

            def _fin(results):
                if results and fin is not None:
                    try:
                        fin(results)
                    except Exception as e:
                        app_logger.error(f"Fin d'import : {e}", exc_info=True)
                if callback:
                    callback(results)
            self._launch_real_import(reelle, _fin, _time.perf_counter(), dialog=dialog,
                                     source='fiche_site')

        dialog.accepted.connect(_acceptee)
        dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
        dialog.show()

    def _launch_real_import(self, config, callback, t0, dialog=None, source='import'):
        """Lance le vrai _ImportWorker après confirmation (ou directement si pas de preview)."""
        from ..ui.progress_dialog import ProgressDialog
        from .constants import DatabaseConfig

        # Filet de sécurité quotidien : copie de la base avant écritures massives
        # (au plus une copie / 24h pour ne pas ralentir les imports répétés)
        backup_service = getattr(getattr(self, 'main_window', None), 'backup_service', None)
        if backup_service:
            backup_service.create_backup(
                reason="import",
                max_age_hours=DatabaseConfig.BACKUP_MIN_INTERVAL_IMPORT_H
            )

        n        = len(config.files)
        progress = ProgressDialog("Importation en cours", "Annuler", 0, n, self.parent_widget)
        progress.show()

        worker = _ImportWorker(self, config)
        self._import_worker = worker

        worker.progress_updated.connect(
            lambda v, m, lbl: (progress.setRange(0, m),
                               progress.setValue(v),
                               progress.setLabelText(lbl),
                               QApplication.processEvents())
        )
        progress.canceled.connect(worker.cancel)

        def _on_finished(results):
            worker.wait()
            results['processing_time_ms'] = int((_time.perf_counter() - t0) * 1000)
            if source == 'drag_drop':
                results['import_source'] = 'drag_drop'
            # Le dialogue reste ouvert pendant le rafraîchissement post-import
            # (callback -> table_controller.load_data(), coûteux sur gros volumes,
            # + historique) : le fermer ici laissait un silence total entre la fin
            # de l'import et le tableau à jour, perçu comme un plantage.
            progress.setLabelText("Mise à jour de l'affichage…")
            QApplication.processEvents()
            if hasattr(self, 'main_window') and self.main_window:
                self._trigger_post_import_updates()
            if callback:
                callback(results)
            progress.close()
            if dialog:
                dialog.deleteLater()
            self._import_worker = None

        def _on_error(msg):
            progress.close()
            worker.wait()
            app_logger.error(f"Import worker ({source}) : {msg}")
            # Sans ce message, l'import interrompu (ex. lecture des appareils
            # existants impossible) ne laissait qu'une ligne de log.
            # show() et non exec_() : convention du projet (gel macOS).
            if self.parent_widget:
                from PyQt5.QtWidgets import QMessageBox
                from PyQt5.QtCore import Qt
                box = QMessageBox(QMessageBox.Critical, "Import interrompu",
                                  f"L'import a été interrompu par une erreur :\n\n{msg}\n\n"
                                  f"Relancez l'import ; le détail est dans le journal.",
                                  QMessageBox.Ok, self.parent_widget)
                box.setAttribute(Qt.WA_DeleteOnClose)
                box.show()
            if callback:
                callback(None)
            if dialog:
                dialog.deleteLater()
            self._import_worker = None

        worker.finished.connect(_on_finished)
        worker.error_occurred.connect(_on_error)
        worker.start()

    def _launch_preview(self, config, callback, t0, dialog=None, source='import'):
        """Étape dry-run : analyse sans écriture, puis ImportPreviewDialog, puis import réel."""
        from ..ui.progress_dialog import ProgressDialog
        n        = len(config.files)
        progress = ProgressDialog("Analyse en cours…", "Annuler", 0, n, self.parent_widget)
        progress.show()

        preview_worker = _ImportPreviewWorker(self, config)
        self._preview_worker = preview_worker

        preview_worker.progress_updated.connect(
            lambda v, m, lbl: (progress.setRange(0, m),
                               progress.setValue(v),
                               progress.setLabelText(lbl),
                               QApplication.processEvents())
        )
        progress.canceled.connect(preview_worker.cancel)

        def _on_preview_ready(results):
            progress.close()
            preview_worker.wait()
            self._preview_worker = None

            from ..ui.fenetre_import import ImportPreviewDialog
            preview_dlg = ImportPreviewDialog(results, config, self.parent_widget)

            def _on_confirmed():
                self._launch_real_import(config, callback, t0, dialog=dialog, source=source)

            def _on_cancelled():
                if callback:
                    callback(None)
                if dialog:
                    dialog.deleteLater()

            preview_dlg.confirmed.connect(_on_confirmed)
            preview_dlg.cancelled.connect(_on_cancelled)
            preview_dlg.show()

        def _on_preview_error(msg):
            progress.close()
            preview_worker.wait()
            self._preview_worker = None
            # Fallback : lancer l'import directement sans preview
            app_logger.warning(f"Preview worker erreur ({msg}) — import direct")
            self._launch_real_import(config, callback, t0, dialog=dialog, source=source)

        preview_worker.preview_ready.connect(_on_preview_ready)
        preview_worker.error_occurred.connect(_on_preview_error)
        preview_worker.start()



    @handle_database_operation_errors(return_value=None, log_prefix="Erreur import drag&drop")
    def import_from_drag_drop(self, file_paths: List[str], callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """
        Import spécialisé pour drag&drop avec paramètres par défaut intelligents

        Args:
            file_paths: Liste des fichiers à importer

        Returns:
            Résultats de l'import ou None si annulé/échoué

        Notes:
            - Utilise le nom de fichier comme référence par défaut
            - Affiche toujours le dialogue d'options (UX cohérente)
            - Gère les imports multi-fichiers PDF
            - Format d'historique spécialisé pour drag&drop
        """
        if not file_paths:
            return None

        # PHASE 2.1: Valider et préparer les fichiers (sans charger les données)
        import_files = []
        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue

            file_type = self._detect_file_type(file_path)
            if not file_type:
                continue

            # Référence par défaut depuis nom fichier
            default_reference = self._extract_reference_from_filename(file_path)

            # PHASE 2.1: Lazy loading - NE PAS charger les données ici
            # Créer un objet ImportFile cohérent avec import_files()
            import_file = ImportFile(
                path=file_path,
                type=file_type,
                suggested_reference=default_reference,
                suggested_label=default_reference,
                data=None  # Chargement lazy dans le dialogue
            )
            import_files.append(import_file)

        if not import_files:
            return None

        # Déterminer le type d'import
        import_type = ImportType.SINGLE_FILE if len(import_files) == 1 else ImportType.MULTI_FILE

        # Configuration avec paramètres par défaut pour drag&drop
        config = ImportConfiguration(
            files=import_files,
            import_type=import_type
        )

        # Pour drag&drop, on propose toujours le premier nom de fichier comme référence
        if import_files:
            config.reference_piece = import_files[0].suggested_reference

        # Dialogue adapté pour drag&drop
        # PHASE 2.1: Utiliser ImportDialog avec import_manager pour lazy loading
        from ..ui.fenetre_import import ImportDialog
        dialog = ImportDialog(self.parent_widget, config, import_manager=self)

        # Titre spécialisé pour drag&drop
        dialog.setWindowTitle("Import par Glisser-Déposer")

        # Non bloquant (show, jamais exec_) : résultat via callback
        dialog.accepted.connect(lambda: self._on_dialog_accepted(dialog, callback, 'drag_drop'))
        dialog.rejected.connect(lambda: self._on_dialog_rejected(dialog, callback))
        dialog.show()
        return None

    def _on_dialog_accepted(self, dialog, callback, source):
        """
        Callback appelé quand un dialogue d'import est accepté (mode non-bloquant).
        Lance d'abord une analyse dry-run (ImportPreviewDialog), puis le vrai import.

        Socle commun des chemins fichier et drag&drop, qui ne différaient que par
        la valeur de `source` transmise en aval.

        Args:
            source: 'import' (fichier ou collage) ou 'drag_drop', propagé tel quel
                    à _launch_preview / _launch_real_import.
        """
        config = dialog.get_configuration()
        if not config:
            if callback:
                callback(None)
            dialog.deleteLater()
            return

        t0 = _time.perf_counter()
        if config.show_preview:
            self._launch_preview(config, callback, t0, dialog=dialog, source=source)
        else:
            self._launch_real_import(config, callback, t0, dialog=dialog, source=source)

    def _on_dialog_rejected(self, dialog, callback):
        """
        Callback appelé quand un dialogue d'import est annulé (mode non-bloquant).

        PHASE 2.2: Gestion propre de l'annulation. Les chemins fichier et
        drag&drop en portaient deux versions strictement identiques.
        """
        try:
            # Import annulé, appeler le callback avec None
            if callback:
                callback(None)
        finally:
            # Nettoyer le dialogue
            dialog.deleteLater()

    def _detect_file_type(self, file_path: str) -> Optional[FileType]:
        """Détecter le type de fichier"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.csv':
            return FileType.CSV
        elif ext == '.pdf':
            return FileType.PDF
        return None
    
    def _extract_reference_from_filename(self, file_path: str) -> str:
        """Extraire une référence depuis le nom de fichier"""
        return os.path.splitext(os.path.basename(file_path))[0]

    def _run_import_files(self, config: ImportConfiguration,
                          progress_cb=None, cancel_check=None,
                          dry_run: bool = False) -> Dict[str, Any]:
        """Moteur d'import pur — aucune opération UI.
        Peut s'exécuter dans un QThread.

        :param progress_cb: callable(value, maximum, label) pour les mises à jour UI
        :param cancel_check: callable() → bool pour l'annulation
        :param dry_run: si True, analyse sans aucune écriture en base
        """
        # Stocker le cancel_check pour les sous-méthodes (_process_data_import_batch, etc.)
        self._import_cancel_check = cancel_check
        self._log_counters = self._nouveaux_compteurs_log()

        cache_service = getattr(self.db_manager, 'cache_invalidation', None)
        if cache_service and not dry_run:
            cache_service.suspend_invalidation(f"import de {len(config.files)} fichier(s)")

        try:
            results = ImportManager._nouveaux_resultats_import(len(config.files))

            app_logger.info(f" Import de {len(config.files)} fichier(s)")
            seen_device_refs = set()
            self._reinitialiser_etat_session()

            n = len(config.files)
            if progress_cb:
                progress_cb(0, n, "Pré-chargement du cache…")

            shared_devices_cache      = self._preload_existing_devices()
            shared_autocomplete_cache = self._build_autocomplete_cache(shared_devices_cache)
            self._marques.charger()
            self._types.charger()
            self._typage.charger()   # index des règles : une fois par import
            app_logger.info(f" Cache prêt : {len(shared_devices_cache)} appareils")

            for i, file in enumerate(config.files):
                if cancel_check and cancel_check():
                    app_logger.info(f"[!] Import annulé à {i}/{n}")
                    break

                if progress_cb:
                    progress_cb(i, n, f"Import de {file.filename}… ({i+1}/{n})")

                file_results = self._safe_import_single_file(
                    file, config, seen_device_refs,
                    shared_devices_cache, shared_autocomplete_cache,
                    dry_run=dry_run,
                    pdf_progress_cb=ImportManager._progression_pdf(progress_cb, file, i, n),
                    errors_out=results['errors'],
                )

                if file_results:
                    self._cumuler_resultats_fichier(results, file, file_results)
                    self._resultats_par_fichier[file.path] = file_results

            if progress_cb:
                progress_cb(n, n, "Finalisation…")

            self._tracer_completions_et_alignements(results)
            self._constats_typage_regles(results, dry_run)
            ImportManager._journaliser_fin_import(results, n)
            self._finaliser_import_en_base(config, results, progress_cb, dry_run)
            results['imported_refs'] = ImportManager._refs_importees(config)

            self._log_resume_import(results, seen_device_refs)
            return results

        finally:
            self._import_cancel_check = None
            if cache_service:
                cache_service.resume_invalidation(force_invalidate=True)

    # ── Étapes de _run_import_files ──────────────────────────────────────────

    @staticmethod
    def _resultats_fichier_vides() -> Dict[str, Any]:
        """Résultat d'un fichier sans ligne à traiter."""
        return {'total_imported': 0, 'matches_found': 0, 'new_entries': 0,
                'associations_created': 0, 'associations_existing': 0,
                'manual_completion': 0, 'duplicates_in_file': 0, 'total_lines_extracted': 0}

    @staticmethod
    def _nouveaux_resultats_import(nb_fichiers: int) -> Dict[str, Any]:
        """Récap vierge d'un import de `nb_fichiers` fichiers."""
        return {
            'total_files': nb_fichiers,
            'successful_files': 0,
            'total_imported': 0,
            'matches_found': 0,
            'new_entries': 0,
            'associations_created': 0,
            'associations_existing': 0,
            'manual_completion': 0,
            'duplicates_in_file': 0,
            'errors': [],
            'file_details': []
        }

    def _reinitialiser_etat_session(self) -> None:
        """État accumulé sur TOUS les fichiers d'une session d'import."""
        # Collecte (niveau session, accumulée sur tous les fichiers) des lignes
        # restées incomplètes après le mécanisme exact, pour suggestions différées.
        self._pending_similarity_candidates = []
        # Frères COMPLETS du même lot (Type+Marque renseignés) : on les ajoutera à
        # l'index de similarité pour que les incomplètes du lot « voient » leurs
        # frères importés en même temps (pas encore en base au moment du calcul).
        self._imported_complete_for_similarity = []
        # Références de pièce de chaque ligne incomplète (clé : id(device_data)),
        # pour la suggestion « type de la pièce importée ».
        self._refs_pieces_candidats = {}
        # Appareils existants dont Type/Fabricant vides ont été complétés
        # (clé : id), pour le bloc d'historique de l'import.
        self._completions_existants = {}
        # Appareils dont un champ auto-complété a été tracé (fenêtre « à vérifier »)
        self._appareils_autocompletes = set()
        self._horodatage_import = datetime.now().isoformat(sep=' ', timespec='seconds')
        # Appareils créés pendant la session, par clé d'identité (les fiches du site
        # y retrouvent l'id de leurs créations), et résultat de chaque fichier
        self._ids_session = {}
        self._resultats_par_fichier = {}
        self._index_par_id = None
        # Typage par règle : constats de la session (typés, contredits, hors liste)
        self._typage.reinitialiser()

    @staticmethod
    def _progression_pdf(progress_cb, file, i: int, n: int):
        """Rappel de progression page par page pour un PDF, ou None (pas de
        barre, ou fichier non PDF).

        Sous-résolution pour faire avancer la barre PENDANT l'extraction d'un
        même fichier (sinon elle reste bloquée sur i/n)."""
        if not progress_cb or file.type != FileType.PDF:
            return None
        PDF_SUBSCALE = 1000

        def pdf_progress_cb(page, total_pages, _i=i, _n=n, _file=file):
            sub_value = _i * PDF_SUBSCALE + int((page / total_pages) * PDF_SUBSCALE)
            progress_cb(sub_value, _n * PDF_SUBSCALE,
                        f"Extraction de {_file.filename} : page {page}/{total_pages} ({_i+1}/{_n})")
        return pdf_progress_cb

    def _cumuler_resultats_fichier(self, results: Dict[str, Any], file,
                                   file_results: Dict[str, Any]) -> None:
        """Ajouter au récap de session le résultat d'un fichier importé."""
        results['successful_files'] += 1
        results['file_details'].append({
            'filename': file.filename,
            'lines_processed': file_results.get('total_lines_extracted', 0),
            'type': 'PDF' if file.type.name == 'PDF' else 'CSV'
        })
        for key in ['total_imported', 'matches_found', 'new_entries',
                    'associations_created', 'associations_existing',
                    'manual_completion', 'duplicates_in_file']:
            results[key] += file_results.get(key, 0)
        if file_results.get('pages_vides'):
            alerte = self._alerte_pages_vides(file.filename, file_results['pages_vides'])
            results.setdefault('alerte_pages_vides', []).append(alerte)
            app_logger.warning(f"[Import] {' | '.join(alerte)}")

    def _tracer_completions_et_alignements(self, results: Dict[str, Any]) -> None:
        """Appareils existants complétés, auto-complétions à vérifier, marques et
        types réécrits (« DELTA → Delta ») : reportés au récap pour l'historique."""
        if self._completions_existants:
            results['appareils_completes'] = list(self._completions_existants.values())
        if self._appareils_autocompletes:
            results['autocompletes_a_verifier'] = len(self._appareils_autocompletes)

        for service, cle, libelle in ((self._marques, 'marques_alignees', 'Marques alignées'),
                                      (self._types, 'types_alignes', 'Types alignés')):
            alignements = service.alignements()
            if alignements:
                results[cle] = alignements
                app_logger.info(f"[Import] {libelle} : {service.resume(alignements)}")

    def _constats_typage_regles(self, results: Dict[str, Any], dry_run: bool) -> None:
        """Typage par règle (lot 5) reporté au récap. À l'aperçu (rien d'écrit),
        les appareils à typer et à contredire sont comptés par identité ; à
        l'import réel, typés = ceux réellement écrits (un type déjà présent en base
        ou refusé n'a rien reçu), et les contredits sont recomptés en propositions
        par _finaliser_import_en_base."""
        typage = self._typage
        typees = len(typage.typees) if dry_run else len(typage.ids_typees)
        if typees:
            results['types_par_regle'] = typees
        if typage.contredites:
            results['types_contredits'] = len(typage.contredites)
        if typage.hors_liste:
            from collections import Counter
            results['types_hors_liste'] = Counter(typage.hors_liste.values()).most_common()
            app_logger.info(f"[Import] Types hors liste : "
                            f"{typage.lignes_hors_liste(results['types_hors_liste'])}")

    @staticmethod
    def _journaliser_fin_import(results: Dict[str, Any], n: int) -> None:
        """Ligne de fin d'import. Les fichiers en échec sont sautés, pas fatals :
        le lot se termine et la liste des refusés part dans results['errors']
        jusqu'à l'UI."""
        echecs = len(results['errors'])
        resume = f"[OK] Import terminé : {results['successful_files']}/{n} fichiers"
        if echecs:
            apercu = " | ".join(results['errors'][:5])
            if echecs > 5:
                apercu += f" | … ({echecs - 5} de plus)"
            app_logger.warning(f"{resume} — {echecs} fichier(s) ignoré(s) : {apercu}")
        else:
            app_logger.info(resume)

    def _finaliser_import_en_base(self, config: ImportConfiguration, results: Dict[str, Any],
                                  progress_cb, dry_run: bool) -> None:
        """Après les fichiers (hors simulation) : suggestions par similarité,
        relations entre références, invalidation du cache."""
        if dry_run:
            return

        # Suggestions Type/Marque par similarité (additif, non bloquant) : calcul
        # en un seul lot sur les lignes incomplètes collectées pendant l'import.
        # On transmet progress_cb pour rendre cette phase visible (sinon la barre
        # reste figée sur « Finalisation… » pendant tout le calcul → effet "planté").
        results['similarity_suggestions'] = \
            self._compute_pending_similarity_suggestions(progress_cb=progress_cb)

        if getattr(config, 'relations_groups', None) is not None or \
                getattr(config, 'relations_cards', None) is not None:
            self._apply_relations_from_config(config, results)
        else:
            self._apply_succession_from_config(config, results)

        self._solder_fiches_a_refaire(config, results)

        # Type du fichier contredit par une règle validée : proposition de type (D18),
        # une fois les appareils écrits (il faut leur id)
        if self._typage.contredites:
            results['types_contredits'] = self._typage.proposer_pour_contredits()

        apres = getattr(config, 'apres_ecriture', None)
        if apres is not None:
            apres(self, results)

        # Après la fiche du site : la réponse de la fenêtre l'emporte sur son code produit
        self._appliquer_references_associees(config, results)

        if hasattr(self.db_manager, 'cache_invalidation'):
            self.db_manager.cache_invalidation.invalidate_after_import(results)

    def _appliquer_references_associees(self, config: ImportConfiguration,
                                        results: Dict[str, Any]) -> None:
        """Référence associée Whirlpool / Indesit / Beko répondue à l'import : mémorisée,
        et équivalente de la pièce si elle est donnée (CDC fiches du site § 10.17)."""
        # Groupes déclarés d'abord : l'origine de l'associée en dépend
        declarees = getattr(config, 'origines_declarees', None)
        declarer = getattr(self.db_manager, 'declarer_origines', None)
        if declarees and declarer is not None:
            try:
                if declarer(declarees, datetime.now().isoformat(timespec='seconds')):
                    results['origines_declarees'] = dict(declarees)
                    app_logger.info("[Import] Groupes déclarés : " + ", ".join(
                        f"{r} = {o}" for r, o in declarees.items()))
            except Exception as e:
                app_logger.warning(f"Groupes déclarés non enregistrés : {e}")
        reponses = getattr(config, 'references_associees', None)
        definir = getattr(self.db_manager, 'definir_references_associees', None)
        if not reponses or definir is None:
            return
        try:
            from ..utils.rapprochement_fiche.associee import origine_associable
            origines = {a: origine_associable(a) or None for a in reponses.values() if a}
            n = definir(reponses.items(), datetime.now().isoformat(timespec='seconds'), origines)
        except Exception as e:
            app_logger.warning(f"Références associées non enregistrées : {e}")
            return
        if n:
            results['references_associees'] = dict(reponses)
            app_logger.info("[Import] Références associées : " + ", ".join(
                f"{r} ≡ {a or 'aucune'}" for r, a in reponses.items()))

    def _solder_fiches_a_refaire(self, config: ImportConfiguration, results: Dict[str, Any]) -> None:
        """Une pièce dont la fiche du site était « à refaire depuis les PDF » sort de
        la liste quand un import PDF, CSV ou collage la concerne (CDC fiches du site
        § 10.14). Non bloquant."""
        retirer = getattr(self.db_manager, 'retirer_fiches_a_refaire', None)
        if retirer is None:
            return
        refs = []
        if config.use_common_reference and config.common_reference:
            refs.append(config.common_reference)
        for file in config.files:
            if file.type == FileType.FICHE_SITE or file.path not in self._resultats_par_fichier:
                continue
            ref = config.individual_references.get(file.path, file.suggested_reference)
            if ref:
                refs.append(ref)
        try:
            refaites = retirer(refs)
        except Exception as e:
            app_logger.warning(f"Fiches à refaire non mises à jour : {e}")
            return
        if refaites:
            results['fiches_refaites'] = refaites
            app_logger.info(f"[Import] Fiches du site refaites, retirées de la liste : "
                            f"{', '.join(refaites)}")

    @staticmethod
    def _refs_importees(config: ImportConfiguration) -> List[str]:
        """Références pièce importées, dans l'ordre des fichiers (sans doublon ni
        vide) — utilisé pour charger automatiquement la recherche sur la
        référence courante."""
        seen_refs = set()
        imported_refs = []
        for ref in config.individual_references.values():
            ref = (ref or '').strip()
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                imported_refs.append(ref)
        return imported_refs

    @staticmethod
    def _alerte_pages_vides(nom_fichier: str, trous: List[Dict]) -> List[str]:
        """
        Message d'alerte « pages vides » d'un fichier : un titre puis une fourchette
        par trou. Calculé ici et transporté dans results, comme alerte_mapping,
        pour que le récap n'ait qu'à l'afficher.

        Ex. ['805101.pdf : 4 pages vides — appareils peut-être manquants entre :',
             'p.3 : DFI544BXXL-04 → DFI544D-02', ...]
        """
        nb_pages = sum(len(t['pages']) for t in trous)
        pluriel = 's' if nb_pages > 1 else ''
        lignes = [f"{nom_fichier} : {nb_pages} page{pluriel} vide{pluriel} — "
                  f"appareils peut-être manquants entre :"]
        for trou in trous:
            pages = trou['pages']
            libelle = f"p.{pages[0]}" if len(pages) == 1 else f"p.{pages[0]}-{pages[-1]}"
            lignes.append(f"{libelle} : {trou['avant']} → {trou['apres']}")
            # Réparations des lignes coupées au bord du trou : jamais silencieuses
            for brute, corrigee in trou.get('corrections', []):
                lignes.append(f"{libelle} : tiret rétabli, {brute} → {corrigee}")
            for ligne in trou.get('ignorees', []):
                lignes.append(f"{libelle} : ligne coupée non importée, {ligne}")
        return lignes

    def _log_resume_import(self, results: Dict[str, Any], seen_device_refs: set) -> None:
        """Une ligne de synthèse en fin d'import, en remplacement des messages
        par-appareil (v3.66.0).

        Le rapport « lignes traitées / clés d'appareil distinctes » est volontairement
        mis en avant : c'est l'indicateur qui aurait rendu immédiatement visible le
        bug de déduplication du 2026-09-01 (310 lignes → 1 seule clé distincte), là
        où il fallait auparavant lire 309 lignes de log identiques pour le repérer.
        """
        traitees = results.get('total_imported', 0)
        doublons = results.get('duplicates_in_file', 0)
        distinctes = len(seen_device_refs)
        compteurs = self._log_counters
        app_logger.info(
            f"[Import] Synthèse : {traitees} lignes traitées, {distinctes} clés "
            f"d'appareil distinctes, {doublons} doublons "
            f"— auto-complétion : {compteurs['autocomplete_type']} types, "
            f"{compteurs['autocomplete_manufacturer']} fabricants, "
            f"{len(results.get('appareils_completes', []))} appareils existants complétés"
        )
        # Signal fort : beaucoup de lignes pour une seule identité d'appareil.
        # Le total inclut les doublons — c'est justement là qu'elles atterrissent
        # quand le mapping écrase l'identité (309 des 310 lignes le 2026-09-01).
        lignes = traitees + doublons
        results['cles_distinctes'] = distinctes
        if lignes > 1 and distinctes <= 1:
            # Message calculé ici et transporté dans results : les deux constructeurs
            # de synthèse (import CSV/collage et import PDF) le consomment tel quel,
            # plutôt que de réévaluer la condition chacun de leur côté.
            results['alerte_mapping'] = (
                f"{lignes} lignes n'ont produit que {distinctes} identité(s) "
                f"d'appareil — vérifiez le mapping des colonnes"
            )
            app_logger.warning(f"[Import] {results['alerte_mapping']}.")

    def _execute_import(self, config: ImportConfiguration) -> Dict[str, Any]:
        """Exécuter l'import de façon synchrone (chemins drag-drop et fallback).
        Affiche une ProgressDialog sur le main thread avec processEvents()."""
        from ..ui.progress_dialog import ProgressDialog

        n        = len(config.files)
        progress = ProgressDialog("Importation en cours", "Annuler", 0, n, self.parent_widget)
        progress.show()

        def _progress_cb(v, m, lbl):
            progress.setRange(0, m)
            progress.setValue(v)
            progress.setLabelText(lbl)
            QApplication.processEvents()

        results = self._run_import_files(
            config,
            progress_cb=_progress_cb,
            cancel_check=lambda: progress.wasCanceled(),
        )

        progress.close()

        if hasattr(self, 'main_window') and self.main_window:
            self._trigger_post_import_updates()

        return results
    
    def _apply_relations_from_config(self, config: ImportConfiguration, results: Dict) -> None:
        """Applique le modèle « par groupes » du nouveau panneau de relations
        (lignées de succession, groupes d'équivalence, courantes externes, obsolètes).
        Non bloquant : un échec ne doit jamais casser un import.
        """
        try:
            from ..services.import_relations import apply_relations
            groups = config.relations_groups or []
            cards = config.relations_cards or []
            journal = []
            counts = apply_relations(groups, cards, self.db_manager, journal=journal)
            for lien in journal:
                if "refusé" in lien:
                    app_logger.warning(f"Relation import : {lien}")
                else:
                    app_logger.info(f"Relation import : {lien}")
            results['succession_created'] = results.get('succession_created', 0) + counts.get('successions', 0)
            results['equivalences_created'] = results.get('equivalences_created', 0) + counts.get('equivalences', 0)
            results['obsoletes_marked'] = results.get('obsoletes_marked', 0) + counts.get('obsoletes', 0)
            app_logger.info(
                f"Relations import appliquées : {counts.get('successions', 0)} succession(s), "
                f"{counts.get('equivalences', 0)} équivalence(s), {counts.get('obsoletes', 0)} obsolète(s)"
                + (f", {counts['errors']} erreur(s)" if counts.get('errors') else ""))
        except Exception as e:
            app_logger.error(f"Application des relations d'import échouée (non bloquant) : {e}")

    def _apply_succession_from_config(self, config: ImportConfiguration, results: Dict) -> None:
        """
        Appliquer les relations déclarées dans le dialogue d'import fichier unique
        (l'import multi-fichiers passe par _apply_relations_from_config).

        Fichier unique :
          - succession_replaces    → (ref_old=existing, ref_new=imported_ref), pour chaque réf
          - succession_replaced_by → (ref_old=imported_ref, ref_new=existing)
          - equivalence_ref        → add_equivalence(imported_ref, réf), pour chaque réf
        Tous modes :
          - obsolete_refs          → mark_obsolete
        """
        if not config.files:
            return

        # --- Fichier unique ---
        if len(config.files) == 1:
            file_ref = config.individual_references.get(config.files[0].path, '') or ''
            if not file_ref:
                return

            # Plusieurs anciennes réfs possibles : chacune est remplacée par la réf
            # importée. Un refus (cycle, réf = elle-même) n'empêche pas les suivantes.
            for ancienne in decouper_refs(config.succession_replaces):
                self._appliquer_relation_import(
                    results, 'succession_created', "Succession import",
                    f"{ancienne} → {file_ref}",
                    self.db_manager.add_supersession(ancienne, file_ref),
                    file_ref, ancienne)

            if config.succession_replaced_by:
                nouvelle = config.succession_replaced_by
                self._appliquer_relation_import(
                    results, 'succession_created', "Succession import",
                    f"{file_ref} → {nouvelle}",
                    self.db_manager.add_supersession(file_ref, nouvelle),
                    file_ref, nouvelle)

            for equivalente in decouper_refs(config.equivalence_ref):
                self._appliquer_relation_import(
                    results, 'equivalences_created', "Équivalence import",
                    f"{file_ref} ≡ {equivalente}",
                    self.db_manager.add_equivalence(file_ref, equivalente),
                    file_ref, equivalente)

        # --- Obsolètes (tous modes) ---
        for ref in (config.obsolete_refs or []):
            if ref:
                ok = self.db_manager.mark_obsolete(ref)
                if ok:
                    results['obsolete_marked'] = results.get('obsolete_marked', 0) + 1
                    app_logger.info(f"Obsolète import : {ref}")
                else:
                    app_logger.warning(f"Obsolète import non appliqué : {ref}")

    def _appliquer_relation_import(self, results: Dict, compteur: str, libelle: str,
                                   lien: str, resultat, file_ref: str, partenaire: str) -> None:
        """Comptabiliser et journaliser une relation créée à l'import fichier unique.

        En cas de succès, le libellé est propagé entre la réf importée et la réf
        citée : celle-ci peut être créée en fantôme, ou exister déjà en base avec
        son propre libellé — la propagation va dans le sens utile, quel que soit
        le type de relation déclarée (succession dans un sens ou l'autre, ou
        équivalence)."""
        ok, msg = resultat
        if ok:
            results[compteur] = results.get(compteur, 0) + 1
            app_logger.info(f"{libelle} : {lien}")
            self.db_manager.propagate_description(file_ref, partenaire)
        else:
            app_logger.warning(f"{libelle} non créée ({lien}) : {msg}")

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur import fichier")
    def _safe_import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set,
                                  shared_devices_cache: Optional[Dict] = None,
                                  shared_autocomplete_cache: Optional[Dict] = None,
                                  dry_run: bool = False,
                                  pdf_progress_cb: Optional[Callable] = None,
                                  errors_out: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Wrapper sécurisé pour _import_single_file avec gestion d'erreur intégrée.

        Un fichier illisible ne doit jamais interrompre le lot. Le try/except
        annoncé par le nom de la méthode manquait (v3.72.1) : l'exception remontait
        la boucle, puis _run_import_files, jusqu'à _ImportWorker qui rapportait
        l'import entier comme échoué. Sur un lot de 192 PDF, un seul alias macOS
        renommé en .pdf faisait ainsi perdre tous les fichiers suivants, sans dire
        lequel avait échoué ni où l'import s'était arrêté.

        L'erreur est journalisée, consignée dans `errors_out`, et None est renvoyé :
        la boucle appelante saute le fichier via son garde `if file_results:`, qui
        anticipait déjà ce retour.

        :param errors_out: liste alimentée d'un libellé par fichier en échec.
                           Des chaînes, pas des dicts : l'UI fait `"\\n".join(...)`
                           dessus (main_refactored._safe_show_import_results_new).
        """
        try:
            return self._import_single_file(file, config, file_seen_device_refs,
                                            shared_devices_cache, shared_autocomplete_cache,
                                            dry_run=dry_run, pdf_progress_cb=pdf_progress_cb)
        except Exception as e:
            # Annulation en cours : l'extraction PDF interrompue renvoie [], puis
            # _import_single_file lève « Aucune donnée trouvée dans le fichier ».
            # Ce n'est pas un fichier défectueux — ne pas le signaler comme tel.
            cancel_check = getattr(self, '_import_cancel_check', None)
            if cancel_check and cancel_check():
                app_logger.info(f"[Import] {file.filename} : interrompu par l'annulation")
                return None

            app_logger.error(f"[Import] Fichier ignoré — {file.filename} : {e}", exc_info=True)
            if errors_out is not None:
                errors_out.append(f"{file.filename} : {e}")
            return None

    def _import_single_file(self, file: ImportFile, config: ImportConfiguration, file_seen_device_refs: set,
                             shared_devices_cache: Optional[Dict] = None,
                             shared_autocomplete_cache: Optional[Dict] = None,
                             dry_run: bool = False,
                             pdf_progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
        """Importer un fichier unique"""
        # Charger les données — clipboard utilise les données pré-chargées, fichiers relus depuis disque
        pages_vides = []
        if file.type == FileType.FICHE_SITE:
            # Une fiche sans appareil (relations seules) n'est pas une erreur
            data = file.data or []
            if not data:
                return ImportManager._resultats_fichier_vides()
        elif file.type == FileType.CLIPBOARD and file.data is not None:
            data = file.data
        elif file.type == FileType.CSV:
            data = self.load_csv_data(file.path)
        elif file.type == FileType.PDF:
            # Import complet : extraction de TOUTES les pages (preview_mode=False par défaut)
            cancel_check = getattr(self, '_import_cancel_check', None)
            data = self.load_pdf_data(file.path, progress_cb=pdf_progress_cb, cancel_check=cancel_check,
                                      pages_vides_out=pages_vides)
        else:
            raise ValueError(f"Type de fichier non supporté: {file.type}")
        
        if not data:
            raise ValueError("Aucune donnée trouvée dans le fichier")

        # Ligne d'en-tête déclarée par l'utilisateur : la retirer avant traitement.
        # Restreint à CSV et collage — l'extracteur PDF supprime déjà l'entête, et
        # config.has_headers est global : sur un import mixte, l'appliquer au PDF
        # supprimerait une vraie ligne de données. La case n'est d'ailleurs proposée
        # que pour ces deux types.
        if config.has_headers and file.type in (FileType.CSV, FileType.CLIPBOARD):
            app_logger.debug(f" En-tête ignorée pour {file.path}: {data[0]}")
            data = data[1:]
            if not data:
                raise ValueError("Le fichier ne contient qu'une ligne d'en-tête")

        # Nouvelle logique: références et libellés séparés
        references_and_labels = []  # Liste de tuples (référence, libellé)
        
        # Référence commune avec son libellé
        if config.use_common_reference and config.common_reference:
            # Utiliser le libellé saisi par l'utilisateur, ou laisser vide si pas de libellé
            common_label = config.common_label if config.common_label else ""
            references_and_labels.append((config.common_reference, common_label))
        
        # Référence individuelle du fichier avec son libellé
        individual_ref = config.individual_references.get(file.path, file.suggested_reference)
        individual_label = config.individual_labels.get(file.path, "")
        
        if references_and_labels and individual_ref == references_and_labels[0][0]:
            # Même référence que la commune : une seule association par ligne. Sans
            # ce garde, la 2ᵈᵉ était retrouvée en base et comptée « déjà associée »
            # (collage de 25 lignes : « Nouvelles : 25 » ET « Déjà associées : 25 »).
            # Libellé du fichier prioritaire s'il est renseigné — c'était déjà l'effet
            # des deux passages, le 2ᵈ remplaçant le libellé du 1ᵉʳ.
            if individual_label:
                references_and_labels[0] = (individual_ref, individual_label)
        else:
            # Garder le libellé vide si l'utilisateur n'a rien saisi
            references_and_labels.append((individual_ref, individual_label))

        # Effectuer l'import des données - Mode batch pour gros volumes
        # Seuil pour activer le mode batch optimisé (réduit pour meilleure performance)
        BATCH_THRESHOLD = 50  # lignes - batch dès 50 lignes pour optimisation immédiate

        # En dry_run, toujours utiliser le batch (chemin propre : classification séparée des écritures)
        # Lignes déjà identifiées (fiche du site) : seul le chemin batch les connaît
        if dry_run or len(data) >= BATCH_THRESHOLD or file.type == FileType.FICHE_SITE:
            file_results = self._process_data_import_batch(
                data,
                references_and_labels,
                config,
                file,
                file_seen_device_refs,
                shared_devices_cache,
                shared_autocomplete_cache,
                dry_run=dry_run,
            )
        else:
            app_logger.debug(f" Mode standard pour {len(data)} lignes (< {BATCH_THRESHOLD})")
            file_results = self._process_data_import(
                data,
                references_and_labels,  # Maintenant liste de tuples (ref, label)
                config,
                file,  # Passer le fichier pour les associations par fichier
                file_seen_device_refs  # CORRECTION: Suivi local par fichier
            )

        if pages_vides and isinstance(file_results, dict):
            file_results['pages_vides'] = pages_vides
        return file_results
    
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur association")
    def _safe_create_association(self, reference: str, device_id: int, label: str):
        """Helper pour créer une association avec gestion d'erreur"""
        # Callback pour gestion intelligente des libellés
        def smart_label_callback(ref_piece, current_desc, new_desc):
            # Si nouveau libellé fourni: l'utiliser (remplace l'ancien)
            if new_desc and new_desc.strip():
                return new_desc.strip()
            # Si pas de nouveau libellé: conserver l'ancien
            else:
                return current_desc

        # Utiliser le libellé spécifique pour cette référence avec callback
        result = self.db_manager.add_or_update_piece_with_description(
            reference, device_id, label, confirm_callback=smart_label_callback
        )
        if result:
            assoc_id, description_updated, association_created = result
            return {'created': association_created, 'assoc_id': assoc_id}
        return None

    def _collecter_candidat_similarite(self, device_data, actif=True, refs_pieces=()):
        """Ranger une ligne importée pour le calcul différé des suggestions Type/Marque.

        Une ligne restée incomplète après le mécanisme exact devient un candidat ;
        une ligne complète devient une référence de comparaison pour ses frères du
        même lot. On stocke la RÉFÉRENCE à device_data : l'id, réinjecté plus tard
        pour les nouveaux appareils, sera visible au moment du calcul.

        Les deux chemins d'import portaient ce bloc à l'identique — le chemin
        standard ne l'avait d'ailleurs reçu qu'en v3.55.0, après qu'on eut constaté
        que les petits imports ne déclenchaient jamais de suggestions.

        Args:
            actif: False en dry-run, où l'on ne collecte rien.
            refs_pieces: références de pièce auxquelles la ligne est rattachée
                (suggestion « type de la pièce importée »).
        """
        from .config import Config

        if not (actif and Config.ENABLE_SIMILARITY_SUGGESTIONS
                and hasattr(self, '_pending_similarity_candidates')):
            return

        complet = ((device_data.get('type') or '').strip()
                   and (device_data.get('manufacturer') or '').strip())
        if complet:
            self._imported_complete_for_similarity.append(device_data)
        else:
            self._pending_similarity_candidates.append(device_data)
            refs = [r for r in refs_pieces if r]
            if refs and hasattr(self, '_refs_pieces_candidats'):
                self._refs_pieces_candidats[id(device_data)] = refs

    # Verdicts rendus par _preparer_ligne
    LIGNE_IGNOREE = 'ignoree'      # vide ou non parsable : rien à faire
    LIGNE_DOUBLON = 'doublon'      # identité déjà vue : rattacher l'association
    LIGNE_A_TRAITER = 'a_traiter'  # identité nouvelle : résoudre l'appareil

    def _preparer_ligne(self, row, config, seen_device_refs, results, prefixe_log=''):
        """Étapes communes aux deux chemins d'import, jusqu'à la décision de traiter.

        `_process_data_import` (standard) et `_process_data_import_batch` portaient
        la même séquence : ignorer les lignes vides, compter la ligne extraite,
        parser selon le mapping, dériver la clé d'identité, décider si c'est un
        doublon. Seule la **résolution** de l'appareil diffère ensuite — SQL
        immédiat d'un côté, cache et écriture différée de l'autre.

        Cette séquence avait déjà divergé trois fois (ordre parse/clé, moment du
        comptage, collecte des suggestions), dont une fois en produisant un bug
        de production. Les tests d'équivalence
        (tests/unit/test_import_paths_equivalence.py) verrouillent le résultat ;
        ce socle commun supprime la possibilité même de la dérive.

        Args:
            prefixe_log: inséré dans les messages de debug pour distinguer les
                deux chemins ('' ou 'BATCH ').

        Returns:
            (verdict, device_data, device_key) — les deux derniers valent None
            pour LIGNE_IGNOREE.
        """
        from .config import Config

        cellules = row.values() if isinstance(row, dict) else (row or ())
        if not row or not any(str(cell).strip() for cell in cellules if cell is not None):
            return self.LIGNE_IGNOREE, None, None

        # Compter chaque ligne non vide comme extraite du fichier
        results['total_lines_extracted'] += 1

        # Parser AVANT tout : la clé de déduplication doit être dérivée du mapping
        # de colonnes réellement appliqué, pas devinée par position.
        device_data = self._parse_row_data(row, config)
        if not device_data:
            return self.LIGNE_IGNOREE, None, None   # Ligne non parsable, ne pas compter

        # Détection des doublons INTER-fichiers (seen_device_refs est partagé)
        ref_modele, commercial_ref, device_key = self._build_device_key(device_data)

        if device_key in seen_device_refs and (ref_modele or commercial_ref):
            results['duplicates_in_file'] += 1
            app_logger.debug(
                f"   {prefixe_log}Doublon inter-fichiers traité: {ref_modele} | {commercial_ref}")
            return self.LIGNE_DOUBLON, device_data, device_key

        if ref_modele or commercial_ref:
            seen_device_refs.add(device_key)
            if Config.LOG_VERBOSE_PER_DEVICE:
                app_logger.debug(
                    f"[OK] {prefixe_log}LIGNE ACCEPTÉE: Ajout {device_key} aux références vues")

        # Compté seulement maintenant : une ligne ignorée ou doublon n'y entre pas
        results['total_imported'] += 1
        return self.LIGNE_A_TRAITER, device_data, device_key

    def _process_data_import(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]],
                           config: ImportConfiguration, file: ImportFile, seen_device_refs: set) -> Dict[str, Any]:
        """Traiter l'import des données avec les références et libellés séparés"""
        # Import hissé en tête : un « from .config import Config » plus bas dans la
        # fonction rendrait Config local à TOUTE la fonction (UnboundLocalError sur
        # les usages antérieurs).

        results = {
            'total_imported': 0,
            'matches_found': 0,
            'new_entries': 0,
            'associations_created': 0,
            'associations_existing': 0,
            'manual_completion': 0,  # Appareils créés/mis à jour sans Type ET Fabricant
            'duplicates_in_file': 0,  # Doublons ref_modele+commercial_ref inter-fichiers
            'total_lines_extracted': 0  # Total lignes du fichier (avant traitement doublons)
        }
        
        # MODIFICATION: Utiliser le set GLOBAL pour détecter les doublons INTER-fichiers
        # Détecter comme doublon des lignes identiques même dans des fichiers différents
        
        for row in data:
            verdict, device_data, device_key = self._preparer_ligne(
                row, config, seen_device_refs, results)

            if verdict == self.LIGNE_IGNOREE:
                continue

            if verdict == self.LIGNE_DOUBLON:
                # Trouver l'appareil existant et créer l'association même pour les doublons
                # Pas de complétion sur un doublon : le chemin batch ne la tente qu'à
                # la 1ʳᵉ occurrence de l'identité (clé = références seules)
                device_id_dup = self._insert_or_find_device(device_data, completer=False)
                if device_id_dup:
                    for reference, label in references_and_labels:
                        if reference:
                            assoc_result = self._safe_create_association(reference, device_id_dup, label)
                            if assoc_result:
                                if assoc_result.get('created'):
                                    results['associations_created'] += 1
                                else:
                                    results['associations_existing'] += 1
                continue  # L'appareil n'est pas recompté dans total_imported

            # Insérer ou trouver l'appareil
            device_id = self._insert_or_find_device(device_data)

            if device_id:
                device_data['id'] = device_id  # pour la collecte des suggestions (ci-dessous)
                if device_data.get('is_new', False):
                    results['new_entries'] += 1
                    # Vérifier si l'appareil CRÉÉ nécessite une complétion manuelle
                    if self._needs_manual_completion(device_data):
                        results['manual_completion'] += 1
                else:
                    results['matches_found'] += 1

                self._collecter_candidat_similarite(
                    device_data, refs_pieces=[r for r, _ in references_and_labels])

                # Associer les références (chaque paire référence-libellé)
                for reference, label in references_and_labels:
                    if reference:
                        assoc_result = self._safe_create_association(reference, device_id, label)
                        if assoc_result:
                            if assoc_result.get('created'):
                                results['associations_created'] += 1
                                app_logger.debug(f"  ✨ Association créée: {reference} → {label} pour appareil {device_id}")
                            else:
                                results['associations_existing'] += 1
        
        return results
    
    def _process_data_import_batch(self, data: List[List[str]], references_and_labels: List[Tuple[str, str]],
                                 config: ImportConfiguration, file: ImportFile, seen_device_refs: set,
                                 shared_devices_cache: Optional[Dict] = None,
                                 shared_autocomplete_cache: Optional[Dict] = None,
                                 dry_run: bool = False) -> Dict[str, Any]:
        """Version optimisée avec batch processing pour les gros imports.
        Si dry_run=True : classification uniquement, aucune écriture en base.

        Trois étapes : caches (ÉTAPE 1), classement des lignes en mémoire
        (ÉTAPE 2, _classer_lignes_batch), puis écriture en base
        (ÉTAPE 3, _ecrire_lot_batch) — ou, en dry_run, comptage des associations
        qui seraient créées (_compter_associations_simulees)."""

        results = {
            'total_imported': 0,
            'matches_found': 0,
            'new_entries': 0,
            'associations_created': 0,
            'associations_existing': 0,
            'manual_completion': 0,
            'duplicates_in_file': 0,
            'total_lines_extracted': 0
        }

        # ÉTAPE 1: Utiliser le cache partagé si fourni, sinon pré-charger (import fichier unique)
        if shared_devices_cache is not None:
            existing_devices_cache = shared_devices_cache
            autocomplete_cache = shared_autocomplete_cache or self._build_autocomplete_cache(existing_devices_cache)
            app_logger.debug(f" BATCH: Cache partagé utilisé ({len(existing_devices_cache)} appareils)")
        else:
            existing_devices_cache = self._preload_existing_devices()
            autocomplete_cache = self._build_autocomplete_cache(existing_devices_cache)

        # ÉTAPE 2: Traitement en mémoire de toutes les lignes
        lot = self._classer_lignes_batch(data, references_and_labels, config, seen_device_refs,
                                         results, existing_devices_cache, autocomplete_cache,
                                         dry_run)

        # ÉTAPE 3: Batch operations sur la base (ignorées en dry_run)
        if not dry_run:
            self._ecrire_lot_batch(lot, results)
            self._retenir_appareils_crees(lot, existing_devices_cache)
        else:
            self._compter_associations_simulees(lot.associations_batch, results)

        app_logger.debug(f"[OK] BATCH: Terminé — {results['total_imported']} lignes traitées")
        return results

    def _classer_lignes_batch(self, data, references_and_labels, config, seen_device_refs,
                              results, existing_devices_cache, autocomplete_cache,
                              dry_run) -> '_LotBatch':
        """ÉTAPE 2 : classer chaque ligne (ignorée, doublon, appareil existant ou
        nouveau) et préparer, sans aucun SQL, les écritures de l'ÉTAPE 3."""
        cancel_check = getattr(self, '_import_cancel_check', None)
        app_logger.debug(f" BATCH: Analyse de {len(data)} lignes…")

        lot = _LotBatch()
        total_rows = len(data)

        for idx, row in enumerate(data):
            # Vérifier si annulation demandée tous les 10 éléments
            if idx > 0 and idx % 10 == 0:
                if cancel_check and cancel_check():
                    app_logger.info(f"[!] Traitement batch annulé à la ligne {idx}/{len(data)}")
                    break

            verdict, device_data, device_key = self._preparer_ligne(
                row, config, seen_device_refs, results, prefixe_log='BATCH ')

            if verdict == self.LIGNE_IGNOREE:
                continue

            if verdict == self.LIGNE_DOUBLON:
                self._rattacher_doublon_batch(lot, device_data, device_key,
                                              references_and_labels, existing_devices_cache)
                continue

            self._ranger_ligne_batch(lot, device_data, device_key, references_and_labels,
                                     results, existing_devices_cache, autocomplete_cache, dry_run)

            if idx > 0 and idx % 100 == 0:
                app_logger.debug(f" BATCH: {idx}/{total_rows} lignes analysées")

        return lot

    def _retenir_appareils_crees(self, lot, existing_devices_cache) -> None:
        """Appareils créés par ce fichier, ajoutés au cache partagé des fichiers
        suivants. Sans cela, un fichier suivant qui cite le même appareil (doublon
        inter-fichiers) ne le trouvait ni en base au chargement du cache, ni dans
        le cache : sa ligne n'était pas rattachée à la pièce, et seul un 2ᵈ import
        posait le lien (418 liens sur le 1ᵉʳ lot des fiches du site, CDC § 10.12)."""
        for device_data, cle in zip(lot.new_devices_batch, lot.cles_nouveaux):
            ident = device_data.get('id')
            if not cle or not ident:
                continue
            existing_devices_cache[cle] = {
                'id': ident,
                'ref_modele': device_data.get('ref_modele', ''),
                'commercial_ref': device_data.get('commercial_ref', ''),
                'type': device_data.get('type', ''),
                'manufacturer': device_data.get('manufacturer', ''),
                'other_ref': device_data.get('other_ref', ''),
                'notes': device_data.get('notes', ''),
            }
            self._ids_session[cle] = ident

    def _rattacher_doublon_batch(self, lot, device_data, device_key, references_and_labels,
                                 existing_devices_cache) -> None:
        """Ligne doublon : rattacher ses associations à la 1ʳᵉ occurrence."""
        # Rattacher l'association à la 1ʳᵉ occurrence. Si elle vient du même
        # fichier, on réutilise son (data_index, existing_id) : la mémoïsation
        # de _batch_create_associations réattribue alors le bon id SANS
        # consommer d'entrée de new_device_ids, y compris quand l'appareil
        # est encore en attente d'insertion. Sinon (doublon inter-fichiers),
        # on ne peut compter que sur un appareil déjà présent en base.
        first_occurrence = lot.first_occurrence_by_key.get(device_key)
        if first_occurrence is not None:
            dup_index, dup_existing_id = first_occurrence
        else:
            dup_index = lot.processed_line_index
            dup_existing_id = self._find_in_cache(device_data, existing_devices_cache)
        if first_occurrence is not None or dup_existing_id:
            for reference, label in references_and_labels:
                if reference:
                    lot.associations_batch.append((reference, label, dup_index, dup_existing_id))

    def _ranger_ligne_batch(self, lot, device_data, device_key, references_and_labels, results,
                            existing_devices_cache, autocomplete_cache, dry_run) -> None:
        """Ligne à traiter : appareil existant (mise à jour, complétion) ou nouvel
        appareil, puis associations. La résolution passe par le cache, pas par SQL
        (le comptage de la ligne traitée est fait par _preparer_ligne)."""
        # Utiliser cache auto-complétion pour améliorer les données (pas de SQL!)
        self._apply_autocomplete_from_cache(device_data, autocomplete_cache)
        # La marque a pu venir du cache : la règle peut maintenant s'appliquer
        # (sans effet si _parse_row_data a déjà typé la ligne)
        self._typer_par_regle(device_data)

        # Vérifier si existe en cache (pas de requête SQL !)
        existing_id = self._find_in_cache(device_data, existing_devices_cache)

        # Mémoriser la résolution de cette ligne pour d'éventuels doublons suivants
        if device_key:
            lot.first_occurrence_by_key.setdefault(device_key, (lot.processed_line_index, existing_id))

        if existing_id:
            # Appareil existant
            results['matches_found'] += 1
            device_data['id'] = existing_id   # pour la collecte des suggestions (ci-dessous)
            if self._needs_update(device_data):
                lot.existing_updates.append((existing_id, device_data))
            # Type/Fabricant vides en base : le cache filtre en amont, pour ne pas
            # émettre un UPDATE par appareil retrouvé sur un import de 90 000 lignes
            entree = existing_devices_cache.get(device_key) if device_key else None
            if entree is None and device_data.get(self.CLE_APPAREIL):
                entree = self._appareil_par_id(existing_id)
            champs = self._champs_a_completer(device_data, entree) if entree else {}
            if champs:
                lot.completions.append((existing_id, device_data, champs))
                if not dry_run:
                    entree.update(champs)  # cache partagé : fichiers suivants du lot
        else:
            # Nouvel appareil à créer (l'id sera réinjecté après insertion batch)
            results['new_entries'] += 1
            if self._needs_manual_completion(device_data):
                results['manual_completion'] += 1
            lot.new_devices_batch.append(device_data)
            lot.cles_nouveaux.append(device_key)

        self._collecter_candidat_similarite(
            device_data, actif=not dry_run,
            refs_pieces=[r for r, _ in references_and_labels])

        # Préparer associations (sera traitée après insertion batch)
        # CORRECTION: Utiliser processed_line_index pour avoir des indices consécutifs
        associations_added_for_line = 0
        for reference, label in references_and_labels:
            if reference:
                # Utiliser processed_line_index pour avoir des indices consécutifs sans trous
                lot.associations_batch.append((reference, label, lot.processed_line_index, existing_id))
                associations_added_for_line += 1

        if associations_added_for_line == 0:
            app_logger.warning(f"Ligne {lot.processed_line_index}: Aucune association créée pour cette ligne (pas de référence valide)")

        # Incrémenter le compteur des lignes réellement traitées
        lot.processed_line_index += 1

    def _ecrire_lot_batch(self, lot, results) -> None:
        """ÉTAPE 3 : insertions, mises à jour, complétions et associations en base."""
        from .config import Config
        new_devices_batch = lot.new_devices_batch
        associations_batch = lot.associations_batch

        app_logger.debug(f" BATCH: Insertion de {len(new_devices_batch)} nouveaux appareils…")
        new_device_ids = self._batch_insert_devices(new_devices_batch) if new_devices_batch else []

        if len(new_devices_batch) != len(new_device_ids):
            app_logger.error(f"Erreur critique: {len(new_devices_batch)} nouveaux appareils -> {len(new_device_ids)} IDs obtenus")

        # Réinjecter l'id généré dans chaque device_data (additif) : nécessaire à la
        # collecte des suggestions par similarité (et sans effet sur le reste du flux).
        # new_device_ids est parallèle à new_devices_batch ; zip tronque si tailles diffèrent.
        for _dev_data, _new_id in zip(new_devices_batch, new_device_ids):
            _dev_data['id'] = _new_id
        self._tracer_autocompletions(
            (d['id'], d, None) for d in new_devices_batch[:len(new_device_ids)])

        app_logger.debug(f" BATCH: Mise à jour de {len(lot.existing_updates)} appareils existants…")
        if lot.existing_updates:
            self._batch_update_devices(lot.existing_updates)
        self._completer_appareils_existants(lot.completions)

        app_logger.debug(f" BATCH: Création de {len(associations_batch)} associations…")

        new_device_associations     = [a for a in associations_batch if not a[3]]
        existing_device_associations = [a for a in associations_batch if a[3]]
        unique_new      = set(a[2] for a in new_device_associations)
        unique_existing = set(a[2] for a in existing_device_associations)
        all_unique      = unique_new | unique_existing
        app_logger.info(f"Associations: {len(associations_batch)} total ({len(new_device_associations)} nouveaux + {len(existing_device_associations)} existants)")
        # Diagnostic, pas une vérification : les deux termes portent sur des
        # populations différentes. `total_imported` ne compte que les lignes
        # NOUVELLES (_preparer_ligne l'incrémente après avoir écarté ignorées et
        # doublons), tandis que `all_unique` recense les indices présents dans
        # associations_batch, doublons compris — rattachés à l'indice de leur 1ʳᵉ
        # occurrence, ou à `processed_line_index` si elle vient d'un autre fichier.
        # Or ce compteur n'avance qu'après les `continue` : sur un fichier 100 %
        # doublons il reste à 0, et la ligne affichait « 0 lignes traitées vs 1 »
        # alors que tout était normal. Sortait 192 fois en INFO sur l'import du
        # 2026-09-10, avec l'allure d'un échec — d'où le passage en debug.
        #
        # Le passage en debug l'a retirée de la console (handler INFO) mais pas de
        # detailed.log, dont le handler accepte DEBUG : le volume y restait inchangé.
        # D'où le garde LOG_VERBOSE_PER_DEVICE, déjà utilisé par _preparer_ligne pour
        # ses logs par-appareil — même intention, même levier : muet par défaut,
        # réactivable pour un diagnostic sans toucher au code.
        if Config.LOG_VERBOSE_PER_DEVICE:
            app_logger.debug(f" BATCH: {results['total_imported']} ligne(s) nouvelle(s), "
                             f"{len(all_unique)} indice(s) de ligne portant des associations")

        if associations_batch:
            batch_results = self._batch_create_associations(associations_batch, new_device_ids)
            results['associations_created'] += batch_results.get('created', 0)
            results['associations_existing'] += batch_results.get('existing', 0)

        if hasattr(self.db_manager, 'cache_invalidation'):
            self.db_manager.cache_invalidation.invalidate_after_import(results)

    def _compter_associations_simulees(self, associations_batch, results) -> None:
        """Dry-run : associations qui seraient créées / déjà présentes, sans écrire."""
        # Dry-run (F7) : compter exactement depuis associations_batch (construit en
        # ÉTAPE 2 dans les deux modes), en répliquant la logique de
        # _batch_create_associations en lecture seule. L'ancienne approximation
        # (nouveaux appareils × refs valides) donnait des comptages faux.
        existing_pairs_in_db = set()
        existing_device_ids = list({a[3] for a in associations_batch if a[3]})
        CHUNK = 500
        for i in range(0, len(existing_device_ids), CHUNK):
            chunk = existing_device_ids[i:i + CHUNK]
            placeholders = ','.join('?' * len(chunk))
            rows = self.db_manager.execute_query(
                f"SELECT p.ref_piece, pa.appareil_id "
                f"FROM piece_associations pa JOIN pieces p ON pa.piece_id = p.id "
                f"WHERE pa.appareil_id IN ({placeholders})",
                chunk
            )
            existing_pairs_in_db.update((r[0], r[1]) for r in rows or [])

        created = existing = 0
        seen_pairs = set(existing_pairs_in_db)
        for reference, _label, data_index, existing_id in associations_batch:
            # Même clé que le chemin réel : appareil existant = id DB,
            # nouvel appareil = index de ligne (l'id n'existe pas encore)
            pair = (reference, existing_id) if existing_id else (reference, f"new_{data_index}")
            if pair in seen_pairs:
                existing += 1
            else:
                created += 1
                seen_pairs.add(pair)

        results['associations_created'] = created
        results['associations_existing'] = existing
    
    def _preload_existing_devices(self) -> Dict[str, Dict]:
        """Pré-charger tous les appareils existants pour éviter les requêtes répétées.

        Lève DatabaseError si la lecture échoue : l'import s'arrête plutôt que de
        tourner sur un cache vide (cf. lire_appareils_pour_import).
        """
        rows = self.db_manager.lire_appareils_pour_import()

        # Conserver les lignes brutes pour le calcul des suggestions par similarité
        # (réutilise la même lecture — pas de requête supplémentaire). Les colonnes
        # (id, ref_modele, commercial_ref, type, manufacturer) suffisent : build_reference_index
        # ne lit que row[:5] et ignore other_ref/notes.
        self._existing_devices_rows_for_similarity = rows

        cache = {}
        for row in rows:
            device_id, ref_modele, commercial_ref, device_type, manufacturer, other_ref, notes = row

            # Indexer par ref_modele + commercial_ref pour recherche rapide.
            #
            # v3.65.1 — la garde était `and` alors que la requête SQL ci-dessus
            # sélectionne en `OR` : tout appareil mono-référence (ref_modele SANS
            # commercial_ref, ou l'inverse) était chargé depuis la base puis jeté
            # ici. Il n'entrait donc JAMAIS dans le cache, et un ré-import du même
            # lot le recréait au lieu de le retrouver (bug constaté le 2026-09-01 :
            # 2ᵉ import de 60 lignes → 60 nouveaux appareils au lieu de 60 matches).
            #
            # La clé reste la composite `ref|commercial_ref` : « WW001| » ne peut pas
            # matcher « WW001|CR001 ». Un appareil partiel ne correspond donc qu'à un
            # autre appareil partiel, jamais à un appareil complet — la sévérité de
            # _insert_or_find_device (« évite 2108002 vs 2108002000 ») est préservée.
            if ref_modele or commercial_ref:
                key = f"{(ref_modele or '').lower()}|{(commercial_ref or '').lower()}"
                cache[key] = {
                    'id': device_id,
                    'ref_modele': ref_modele,
                    'commercial_ref': commercial_ref,
                    'type': device_type,
                    'manufacturer': manufacturer,
                    'other_ref': other_ref,
                    'notes': notes
                }

        return cache

    def _compute_pending_similarity_suggestions(self, progress_cb=None) -> Dict[int, list]:
        """Suggestions Type/Marque des lignes restées incomplètes : similarité de
        référence, complétée par le type de la pièce importée. Jamais d'écriture,
        jamais d'échec d'import (chaque étape attrape ses erreurs)."""
        suggestions = self._suggestions_par_similarite(progress_cb=progress_cb)
        suggestions = self._ajouter_suggestions_type_piece(suggestions)
        return self._ajouter_suggestions_autre_ref(suggestions)

    def _ajouter_suggestions_autre_ref(self, suggestions: Dict[int, list]) -> Dict[int, list]:
        """Ajoute, pour chaque ligne SANS type, le type que portent déjà au moins
        AUTRE_REF_PART_MIN des appareils au même texte « Autre référence » (au
        moins AUTRE_REF_APPAREILS_MIN appareils typés). Même fusion que le type
        de la pièce : en concurrent, jamais en double.
        """
        from .config import Config
        if not Config.ENABLE_AUTRE_REF_SUGGESTION:
            return suggestions
        try:
            from ..services.reference_similarity_service import fusionner_autre_ref
            lignes = [d for d in getattr(self, '_pending_similarity_candidates', [])
                      if d.get('id') and not (d.get('type') or '').strip()
                      and (d.get('other_ref') or '').strip()]
            if not lignes:
                return suggestions
            types_par_texte = self.db_manager.compter_types_par_autre_ref(
                d['other_ref'] for d in lignes)

            ajoutees = 0
            for d in lignes:
                fusion = fusionner_autre_ref(
                    suggestions.get(d['id'], []), d['other_ref'], types_par_texte,
                    Config.AUTRE_REF_PART_MIN, Config.AUTRE_REF_APPAREILS_MIN)
                if fusion is None:
                    continue          # texte inconnu, partagé, ou type déjà proposé
                suggestions[d['id']] = fusion
                ajoutees += 1
            app_logger.info(f"Suggestions « Autre référence » : {ajoutees} appareil(s) "
                            f"sur {len(lignes)} ligne(s) sans type")
            return suggestions
        except Exception as e:
            app_logger.error(f"Suggestions « Autre référence » échouées (non bloquant) : {e}")
            return suggestions

    def _ajouter_suggestions_type_piece(self, suggestions: Dict[int, list]) -> Dict[int, list]:
        """Ajoute, pour chaque ligne SANS type, le type que portent déjà au moins
        TYPE_PIECE_PART_MIN des appareils de sa pièce (au moins
        TYPE_PIECE_APPAREILS_MIN appareils typés).

        Fusion avec la similarité : si un candidat propose déjà ce type, rien
        n'est ajouté ; sinon le candidat « pièce » s'ajoute en concurrent (la
        fenêtre de validation ne pré-coche alors plus la ligne).
        """
        from .config import Config
        if not Config.ENABLE_TYPE_PIECE_SUGGESTION:
            return suggestions
        refs_par_ligne = getattr(self, '_refs_pieces_candidats', None) or {}
        if not refs_par_ligne:
            return suggestions
        try:
            from ..services.reference_similarity_service import fusionner_type_piece
            lignes = [d for d in getattr(self, '_pending_similarity_candidates', [])
                      if d.get('id') and not (d.get('type') or '').strip()
                      and id(d) in refs_par_ligne]
            if not lignes:
                return suggestions
            types_par_ref = self.db_manager.compter_types_par_piece(
                r for d in lignes for r in refs_par_ligne[id(d)])

            ajoutees = 0
            for d in lignes:
                fusion = fusionner_type_piece(
                    suggestions.get(d['id'], []), refs_par_ligne[id(d)], types_par_ref,
                    Config.TYPE_PIECE_PART_MIN, Config.TYPE_PIECE_APPAREILS_MIN)
                if fusion is None:
                    continue          # pas de type dominant, ou déjà proposé
                suggestions[d['id']] = fusion
                ajoutees += 1
            app_logger.info(f"Suggestions « type de la pièce » : {ajoutees} appareil(s) "
                            f"sur {len(lignes)} ligne(s) sans type")
            return suggestions
        except Exception as e:
            app_logger.error(f"Suggestions « type de la pièce » échouées (non bloquant) : {e}")
            return suggestions

    def _suggestions_par_similarite(self, progress_cb=None) -> Dict[int, list]:
        """Calcule les suggestions Type/Marque par similarité pour les lignes
        restées incomplètes après le mécanisme exact (collectées pendant la boucle
        d'import dans self._pending_similarity_candidates).

        ADDITIF, aucune écriture : ne fait que proposer. Ne doit JAMAIS faire
        échouer un import (try/except interne, retourne {} en cas de souci).

        :param progress_cb: callable(value, maximum, label) optionnel — rend la phase
            visible dans la ProgressDialog (sinon la barre semble figée → "planté").

        Returns:
            Dict[db_id, List[dict]] — candidats par appareil (SimilarityCandidate.to_dict()).
        """
        from .config import Config
        if not Config.ENABLE_SIMILARITY_SUGGESTIONS:
            return {}
        if not getattr(self, '_pending_similarity_candidates', None):
            return {}
        try:
            from ..services.reference_similarity_service import ReferenceSimilarityService
            # Index = appareils déjà en base + Levier 1 : frères COMPLETS du lot en
            # cours (id réinjecté après insertion), au format attendu
            # (db_id, ref_modele, commercial_ref, type, manufacturer). Les frères du
            # lot suffisent à eux seuls même si la base est vide pour ce préfixe.
            rows = list(getattr(self, '_existing_devices_rows_for_similarity', None) or [])
            for dev in getattr(self, '_imported_complete_for_similarity', []):
                dev_id = dev.get('id')
                if dev_id:
                    rows.append((dev_id, dev.get('ref_modele', ''),
                                 dev.get('commercial_ref', ''),
                                 dev.get('type', ''), dev.get('manufacturer', '')))
            if not rows:
                return {}
            # Coût réel dominant : construire l'index (tous les appareils de la base,
            # potentiellement plusieurs centaines de milliers de lignes) prend souvent
            # plus longtemps que la boucle de recherche elle-même (quelques lignes
            # incomplètes) — sans ce libellé, cette étape était totalement silencieuse.
            if progress_cb:
                progress_cb(0, len(self._pending_similarity_candidates) or 1,
                            "Préparation de l'index de suggestions…")
            reference_index = ReferenceSimilarityService.build_reference_index(rows)
            service = ReferenceSimilarityService(
                allow_numeric_fuzzy=Config.SIMILARITY_ALLOW_NUMERIC_FUZZY,
                fuzzy_threshold=Config.SIMILARITY_FUZZY_THRESHOLD,
                enable_prefix_consensus=Config.SIMILARITY_PREFIX_CONSENSUS,
                enforce_shape_compatibility=Config.SIMILARITY_ENFORCE_SHAPE,
                enforce_code_group=Config.SIMILARITY_GROUPE_CODE,
            )
            suggestions_by_db_id: Dict[int, list] = {}
            total_pending = len(self._pending_similarity_candidates)
            # Throttle des mises à jour de progression : ~1 % ou tous les 50 items
            # (au moins 1), pour ne pas saturer le signal sur de gros volumes.
            step = max(1, total_pending // 100, 50)
            if progress_cb:
                progress_cb(0, total_pending,
                            f"Recherche de suggestions… (0/{total_pending})")
            for idx, device_data in enumerate(self._pending_similarity_candidates):
                db_id = device_data.get('id')
                if not db_id:
                    continue
                candidates = service.find_candidates(
                    ref_modele=device_data.get('ref_modele', ''),
                    commercial_ref=device_data.get('commercial_ref', ''),
                    reference_index=reference_index,
                    exclude_db_id=db_id,
                )
                if candidates:
                    suggestions_by_db_id[db_id] = [c.to_dict() for c in candidates]
                if progress_cb and (idx % step == 0 or idx == total_pending - 1):
                    done = idx + 1
                    progress_cb(done, total_pending,
                                f"Recherche de suggestions… ({done}/{total_pending})")
            app_logger.info(
                f"Suggestions par similarité : {len(suggestions_by_db_id)} appareil(s) "
                f"sur {len(self._pending_similarity_candidates)} ligne(s) incomplète(s)"
            )
            return suggestions_by_db_id
        except Exception as e:
            app_logger.error(f"Calcul des suggestions de similarité échoué (non bloquant): {e}")
            return {}

    def _build_autocomplete_cache(self, existing_devices_cache: Dict[str, Dict]) -> Dict[str, Dict[str, str]]:
        """Construire un cache pour l'auto-complétion (Type + Fabricant par référence)"""
        autocomplete_cache = {}
        # Même règle que _try_auto_complete : pas d'auto-complété non vérifié comme source
        lignes = self.db_manager.execute_query(
            "SELECT DISTINCT appareil_id FROM appareils_autocompletes") or []
        non_verifies = {ligne[0] for ligne in lignes}

        for key, device in existing_devices_cache.items():
            if device.get('id') in non_verifies:
                continue
            ref_modele = (device.get('ref_modele') or '').strip()
            commercial_ref = (device.get('commercial_ref') or '').strip()
            device_type = (device.get('type') or '').strip()
            manufacturer = (device.get('manufacturer') or '').strip()
            
            # Créer des entrées pour auto-complétion si Type ET/OU Fabricant disponibles
            if device_type or manufacturer:
                # Indexer par ref_modele si disponible
                if ref_modele:
                    autocomplete_cache[ref_modele.lower()] = {
                        'type': device_type,
                        'manufacturer': manufacturer,
                        'source': ref_modele or commercial_ref,
                    }
                
                # Indexer par commercial_ref si disponible et différent
                if commercial_ref and commercial_ref.lower() != ref_modele.lower():
                    autocomplete_cache[commercial_ref.lower()] = {
                        'type': device_type,
                        'manufacturer': manufacturer,
                        'source': ref_modele or commercial_ref,
                    }
        
        return autocomplete_cache
    
    def _apply_autocomplete_from_cache(self, device_data: Dict[str, Any], autocomplete_cache: Dict[str, Dict[str, str]]):
        """Appliquer l'auto-complétion depuis le cache (pas de SQL!)"""
        # Ne compléter que si Type OU Fabricant manquant
        if (device_data.get('type') or '').strip() and (device_data.get('manufacturer') or '').strip():
            return  # Déjà complet
        
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()
        
        # Chercher d'abord par ref_modele
        cache_entry = None
        if ref_modele:
            cache_entry = autocomplete_cache.get(ref_modele.lower())
        
        # Si pas trouvé, chercher par commercial_ref  
        if not cache_entry and commercial_ref:
            cache_entry = autocomplete_cache.get(commercial_ref.lower())
        
        # Appliquer les données trouvées si disponibles
        if cache_entry:
            # Le cache ne garde qu'un appareil par référence : confiance inconnue
            for champ in self.CHAMPS_COMPLETABLES:
                if not (device_data.get(champ) or '').strip() and cache_entry.get(champ):
                    device_data[champ] = cache_entry[champ]
                    self._noter_autocompletion(device_data, champ, cache_entry[champ],
                                               cache_entry.get('source'), None, None)
    
    def _find_in_cache(self, device_data: Dict[str, Any], cache: Dict[str, Dict]) -> Optional[int]:
        """Trouver un appareil dans le cache (pas de SQL!)

        v3.65.1 — garde passée de `and` à `or`, symétriquement à
        _preload_existing_devices : une ligne mono-référence ne tentait même pas la
        recherche. La clé composite est identique à celle de _build_device_key, donc
        les trois notions d'identité (clé de dédup, construction du cache, lecture du
        cache) sont désormais alignées sur la même condition.
        """
        ident = device_data.get(self.CLE_APPAREIL)
        if ident:
            return ident                # identifié par la source (fiche du site)
        ref_modele, commercial_ref, key = self._build_device_key(device_data)

        if ref_modele or commercial_ref:
            if key in cache:
                return cache[key]['id']

        return None
    
    def _needs_update(self, device_data: Dict[str, Any]) -> bool:
        """Vérifier si l'appareil a besoin d'une mise à jour (3ème colonne)"""
        return bool(device_data.get('other_ref') or device_data.get('notes'))

    # Champs qu'un import peut compléter sur un appareil existant — jamais écraser
    CHAMPS_COMPLETABLES = ('type', 'manufacturer')

    def _champs_a_completer(self, device_data: Dict[str, Any],
                            valeurs_base: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Type/Fabricant de la ligne (lus dans le fichier ou auto-complétés) à
        reporter sur un appareil existant.

        Jusqu'en v3.88.1, ils n'étaient jamais écrits : `_update_existing_device`
        et `_batch_update_devices` ne portent que la 3ᵉ colonne. L'appareil vide
        restait vide, et comme la ligne paraissait complète en mémoire, il n'était
        pas non plus proposé en suggestion.

        Args:
            valeurs_base: Type/Fabricant connus en base (cache du chemin batch) ; un
                champ déjà renseigné est écarté. None : la garde SQL tranche seule.
        """
        champs = {}
        for champ in self.CHAMPS_COMPLETABLES:
            valeur = (device_data.get(champ) or '').strip()
            if not valeur:
                continue
            if valeurs_base is not None and (valeurs_base.get(champ) or '').strip():
                continue
            champs[champ] = valeur
        return champs

    # Clé privée de device_data : provenance des champs auto-complétés. Sans effet
    # sur les insertions, qui lisent les colonnes une à une (DB_HEADERS, get).
    CLE_AUTOCOMPLETION = '_autocompletion'

    def _noter_autocompletion(self, device_data: Dict[str, Any], champ: str, valeur: str,
                              source: Optional[str], accord: Optional[int],
                              total: Optional[int]) -> None:
        """Retenir d'où vient un champ auto-complété, en attendant l'id de l'appareil.

        accord/total : appareils sources donnant cette valeur / appareils sources
        trouvés (« 1/2 »). None quand la source n'en dit rien (cache du batch).
        """
        device_data.setdefault(self.CLE_AUTOCOMPLETION, {})[champ] = {
            'valeur': valeur, 'source': source or '', 'accord': accord, 'total': total}

    def _tracer_autocompletions(self, appareils) -> None:
        """Inscrire dans appareils_autocompletes les champs auto-complétés ÉCRITS.

        Args:
            appareils: (appareil_id, device_data, champs_ecrits). champs_ecrits None :
                appareil créé, tous ses champs auto-complétés ont été insérés. Sinon,
                seuls ceux réellement écrits (et de même valeur) sont tracés — un
                champ déjà renseigné en base n'a rien reçu.
        Appelée après l'écriture : le déclencheur effacerait sinon la trace.
        """
        enregistrer = getattr(self.db_manager, 'enregistrer_autocompletions', None)
        if enregistrer is None:
            return
        horodatage = (getattr(self, '_horodatage_import', None)
                      or datetime.now().isoformat(sep=' ', timespec='seconds'))
        lignes = []
        for appareil_id, device_data, champs in appareils:
            for champ, prov in (device_data.get(self.CLE_AUTOCOMPLETION) or {}).items():
                ecrit = (device_data.get(champ) if champs is None else champs.get(champ)) or ''
                if not appareil_id or ecrit.strip() != (prov['valeur'] or '').strip():
                    continue
                lignes.append((appareil_id, champ, prov['valeur'], prov['source'],
                               prov['accord'], prov['total'], horodatage))
        if lignes and enregistrer(lignes):
            traces = getattr(self, '_appareils_autocompletes', None)
            if traces is not None:
                traces.update(ligne[0] for ligne in lignes)
            typage = getattr(self, '_typage', None)
            if typage is not None:
                from ..services.typage_import_service import est_source_de_regle
                typage.ids_typees.update(ligne[0] for ligne in lignes
                                         if ligne[1] == 'type' and est_source_de_regle(ligne[3]))

    def _sans_autocompletions_refusees(self, completions):
        """Retire des complétions les champs AUTO-COMPLÉTÉS que l'utilisateur a
        refusés pour cet appareil (fenêtre « Auto-complétés à vérifier », v3.94.0).
        Une valeur lue dans le fichier lui-même reste écrite : le refus vise
        l'auto-complétion, pas la donnée du fournisseur."""
        lire = getattr(self.db_manager, 'lire_refus', None)
        if lire is None:
            return completions
        refus = lire([device_id for device_id, _, _ in completions])
        if not isinstance(refus, set) or not refus:   # lecture échouée (None) : rien à filtrer
            return completions
        filtrees = []
        for device_id, device_data, champs in completions:
            auto = device_data.get(self.CLE_AUTOCOMPLETION) or {}
            gardes = {champ: valeur for champ, valeur in champs.items()
                      if not (champ in auto and
                              (device_id, champ, valeur.strip().lower()) in refus)}
            if gardes:
                filtrees.append((device_id, device_data, gardes))
        return filtrees

    def _completer_appareils_existants(
            self, completions: List[Tuple[int, Dict[str, Any], Dict[str, str]]]) -> int:
        """Écrire les champs vides des appareils existants, commun aux deux chemins.

        La garde WHERE des requêtes refuse d'écraser une valeur : seules les
        écritures effectives (rowcount) sont tracées dans `_completions_existants`,
        restitué en fin d'import dans results['appareils_completes'] pour le bloc
        d'historique. Un même appareil touché par plusieurs fichiers n'y figure
        qu'une fois.

        Returns:
            Nombre d'appareils effectivement complétés.
        """
        if not completions:
            return 0
        from .config import Config
        requetes = {'type': Config.QUERIES['complete_device_type'],
                    'manufacturer': Config.QUERIES['complete_device_manufacturer']}

        completions = self._sans_autocompletions_refusees(completions)
        if not completions:
            return 0

        faits = []
        conn = self.db_manager.get_connection()
        # _query_lock : accès brut à la connexion partagée depuis _ImportWorker → sérialiser.
        with self.db_manager._query_lock:
            cursor = conn.cursor()
            try:
                for device_id, device_data, champs in completions:
                    ecrits = {}
                    for champ, valeur in champs.items():
                        cursor.execute(requetes[champ], (valeur, device_id))
                        if cursor.rowcount:
                            ecrits[champ] = valeur
                    if ecrits:
                        faits.append((device_id, device_data, ecrits))
                conn.commit()
            except Exception as e:
                conn.rollback()
                app_logger.error(f"Complétion des appareils existants échouée : {e}")
                return 0

        self._tracer_autocompletions(faits)
        if not hasattr(self, '_completions_existants'):
            self._completions_existants = {}
        for device_id, device_data, ecrits in faits:
            trace = self._completions_existants.setdefault(device_id, {
                'id': device_id,
                'ref_modele': (device_data.get('ref_modele') or '').strip(),
                'commercial_ref': (device_data.get('commercial_ref') or '').strip(),
            })
            trace.update(ecrits)
        return len(faits)

    def _batch_insert_devices(self, devices_batch: List[Dict[str, Any]]) -> List[int]:
        """Insertion en lot des nouveaux appareils avec chunking optimisé"""
        if not devices_batch:
            return []
        
        from .config import Config
        query = Config.QUERIES['insert_device_batch']
        chunk_size = Config.BATCH_INSERT_SIZE
        
        
        # Utiliser une transaction globale pour l'efficacité.
        # _query_lock : ce code tourne sur le thread _ImportWorker et accède à la
        # connexion partagée en mode brut (get_connection) — il DOIT être sérialisé
        # avec les accès du thread principal pour éviter la corruption du WAL.
        conn = self.db_manager.get_connection()
        all_new_ids = []

        with self.db_manager._query_lock:
            cursor = conn.cursor()
            try:
                # Traiter par chunks pour optimiser SQLite
                for i in range(0, len(devices_batch), chunk_size):
                    chunk = devices_batch[i:i + chunk_size]

                    # Préparer les données pour ce chunk
                    insert_data = []
                    for device in chunk:
                        insert_data.append((
                            device.get('type', ''),
                            device.get('manufacturer', ''),
                            device.get('ref_modele', ''),
                            device.get('commercial_ref', ''),
                            device.get('other_ref', ''),
                            device.get('notes', ''),
                            device.get('category', '')
                        ))

                    # CORRECTION: Insérer un par un pour récupérer les IDs correctement
                    # executemany() ne garantit pas cursor.lastrowid dans SQLite
                    chunk_ids = []
                    for device_data in insert_data:
                        cursor.execute(query, device_data)
                        if cursor.lastrowid is not None:
                            chunk_ids.append(cursor.lastrowid)
                        else:
                            app_logger.debug(f"[ERR] Chunk {i//chunk_size + 1}: Impossible de récupérer l'ID pour un appareil")
                            conn.rollback()
                            return []

                    all_new_ids.extend(chunk_ids)
                    app_logger.debug(f"[OK] Chunk {i//chunk_size + 1}: {len(chunk_ids)} appareils insérés")

                conn.commit()
                # Insertion en lot via cursor brut (hors des méthodes normales de
                # DatabaseManager) : invalider explicitement le cache de comptage,
                # sinon count_data() sans filtre (utilisé par load_data() post-import)
                # continue de renvoyer le total d'avant import.
                self.db_manager.invalidate_search_cache(invalidate_total_count=True)
                app_logger.debug(f"[OK] BATCH FINAL: {len(all_new_ids)} appareils insérés au total")
                return all_new_ids

            except Exception as e:
                conn.rollback()
                app_logger.debug(f"[ERR] BATCH: Erreur insertion: {e}")
                app_logger.debug(f"[ERR] BATCH: IDs partiels récupérés avant erreur: {len(all_new_ids)}")
                import traceback
                app_logger.debug(f"[ERR] BATCH: Stack trace: {traceback.format_exc()}")
                return []
    
    def _batch_update_devices(self, updates_batch: List[Tuple[int, Dict[str, Any]]]):
        """Mise à jour en lot des appareils existants"""
        if not updates_batch:
            return
        
        # Groupe par type de mise à jour
        other_ref_updates = []
        notes_updates = []
        
        for device_id, device_data in updates_batch:
            if device_data.get('other_ref'):
                other_ref_updates.append((device_data['other_ref'], device_id))
            if device_data.get('notes'):
                notes_updates.append((device_data['notes'], device_id))
        
        conn = self.db_manager.get_connection()

        # _query_lock : accès brut à la connexion partagée depuis _ImportWorker → sérialiser.
        with self.db_manager._query_lock:
            cursor = conn.cursor()
            try:
                if other_ref_updates:
                    from .config import Config
                    cursor.executemany(Config.QUERIES['update_device_other_ref'], other_ref_updates)
                if notes_updates:
                    from .config import Config
                    cursor.executemany(Config.QUERIES['update_device_notes'], notes_updates)
                conn.commit()
            except Exception as e:
                conn.rollback()
                app_logger.debug(f"[ERR] BATCH: Erreur mise à jour: {e}")
    
    def _batch_create_associations(self, associations_batch: List[Tuple], new_device_ids: List[int]) -> Dict[str, int]:
        """Création en lot des associations pièces-appareils"""
        if not associations_batch:
            return {'created': 0, 'existing': 0}
        
        results = {'created': 0, 'existing': 0}
        
        # Mapper les indices de data vers les IDs réels (nouveaux + existants) 
        device_id_mapping = {}
        new_device_counter = 0
        
        # Traiter chaque association: (reference, label, data_index, existing_id)
        for reference, label, data_index, existing_id in associations_batch:
            # Utiliser l'index comme clé pour éviter les doublons d'attribution d'ID
            cache_key = f"{data_index}_{existing_id}"
            
            if cache_key in device_id_mapping:
                # Réutiliser l'ID déjà attribué pour cette ligne de donnée
                device_id = device_id_mapping[cache_key]
            elif existing_id:
                # Appareil existant
                device_id = existing_id
                device_id_mapping[cache_key] = device_id
            else:
                # Nouvel appareil - utiliser l'ID de la liste new_device_ids
                if new_device_counter < len(new_device_ids):
                    device_id = new_device_ids[new_device_counter]
                    device_id_mapping[cache_key] = device_id
                    new_device_counter += 1
                else:
                    app_logger.debug(f"[!] BATCH: Pas assez d'IDs pour les nouveaux appareils (index {data_index})")
                    continue
            
            assoc_result = self._safe_create_association(reference, device_id, label)
            if assoc_result:
                if assoc_result.get('created'):
                    results['created'] += 1
                else:
                    results['existing'] += 1
        
        app_logger.debug(f" BATCH: Associations - Créées: {results['created']}, Existantes: {results['existing']}")
        return results
    
    @staticmethod
    def _build_device_key(device_data: Dict[str, Any]) -> Tuple[str, str, str]:
        """Clé d'identité d'un appareil pour la détection de doublons.

        Dérivée des données DÉJÀ parsées par `_parse_row_data`, donc du mapping de
        colonnes réellement appliqué. Avant v3.64.1 la clé était recalculée par
        position (`row[0]`/`row[1]`) en ignorant le mapping : sur un collage
        « Type | Marque | Référence », toutes les lignes recevaient la même clé
        (ex. « lave-linge|samsung ») et 309 lignes sur 310 étaient jetées comme
        doublons (bug constaté le 2026-09-01).

        Returns:
            (ref_modele, commercial_ref, device_key)
        """
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()
        cle = device_data.get(ImportManager.CLE_IDENTITE)
        if cle:
            return ref_modele, commercial_ref, cle
        return ref_modele, commercial_ref, f"{ref_modele.lower()}|{commercial_ref.lower()}"

    def _parse_row_data(self, row: List[str], config: ImportConfiguration) -> Optional[Dict[str, Any]]:
        """Parser une ligne de données selon la configuration : mapping de colonnes
        s'il est renseigné pour ce nombre de colonnes (v3.30.0), sinon lecture
        positionnelle. Ligne sans aucune valeur → None ; sinon casse alignée
        puis auto-complétion si Type ou Fabricant manque."""
        if not row:
            return None

        n = len(row)
        if isinstance(row, dict):
            data = self._lire_ligne_identifiee(row)
        elif config.column_mapping and n in config.column_mapping:
            data = ImportManager._lire_ligne_par_mapping(row, config.column_mapping[n])
        else:
            data = ImportManager._lire_ligne_par_position(row, config.third_column_choice)

        # Vérifier qu'on a au moins une donnée utile
        if not any(v for v in data.values() if v):
            return None

        self._normaliser_casse(data)

        # Appliquer l'autocomplétion si Type ou Fabricant sont manquants
        if not data.get('type') or not data.get('manufacturer'):
            self._try_auto_complete(data)

        # Puis les règles de nomenclature (il leur faut la marque, éventuellement
        # auto-complétée) — commun aux deux chemins et aux fiches du site
        self._typer_par_regle(data)

        return data

    def _typer_par_regle(self, device_data: Dict[str, Any]) -> None:
        """Règles de nomenclature validées appliquées à une ligne (CDC § 8.3, lot 5).

        - type vide ou auto-complété par référence : la règle le donne, noté comme
          une auto-complétion (« à vérifier ») ;
        - type lu dans le fichier et contredit : gardé, l'appareil recevra une
          proposition de type en fin d'import ;
        - type du fichier hors liste : gardé, signalé au récapitulatif.
        Idempotente : le chemin batch l'appelle une 2ᵉ fois après son cache.
        """
        typage = getattr(self, '_typage', None)
        if typage is None:
            return
        cle = self._build_device_key(device_data)[2]
        type_ligne = (device_data.get('type') or '').strip()
        auto = (device_data.get(self.CLE_AUTOCOMPLETION) or {}).get('type')
        type_auto_complete = bool(auto) and (auto.get('valeur') or '').strip() == type_ligne
        if type_ligne and not type_auto_complete and typage.est_hors_liste(type_ligne):
            typage.hors_liste[cle] = type_ligne
        verdict, resolution = typage.examiner(device_data, type_auto_complete)
        if verdict == typage.CONTREDIT:
            # 1ʳᵉ occurrence : c'est elle qui reçoit l'id (un doublon n'en a pas)
            typage.contredites.setdefault(cle, device_data)
        elif verdict == typage.TYPER:
            from ..services.typage_import_service import source_de_regle
            device_data['type'] = resolution.type
            # « 1/1 » : une seule source, la règle (et non « confiance inconnue »)
            self._noter_autocompletion(device_data, 'type', resolution.type,
                                       source_de_regle(resolution.regle), 1, 1)
            typage.typees[cle] = resolution.type
            typage.contredites.pop(cle, None)

    # Lignes déjà lues et identifiées par leur source (fiche du site, FileType.FICHE_SITE) :
    # - CLE_APPAREIL : id d'un appareil de la base (la source l'a reconnu) ;
    # - CLE_IDENTITE : clé de déduplication à la place de « réf. modèle | nom »
    #   (une fiche identifie un appareil par sa marque et sa réf., CDC § 5.2).
    CLE_APPAREIL = '_appareil_id'
    CLE_IDENTITE = '_cle_identite'
    _CHAMPS_APPAREIL = ('ref_modele', 'commercial_ref', 'type', 'manufacturer',
                        'other_ref', 'notes')

    def _lire_ligne_identifiee(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Ligne fournie en dict par sa source. Appareil reconnu : ses champs sont
        ceux de la base, la ligne ne fait que compléter un type ou une marque vides
        (règle de l'import : jamais écraser)."""
        data = {k: v for k, v in row.items()
                if v is not None and (k.startswith('_') or k in self._CHAMPS_APPAREIL)}
        for champ in self._CHAMPS_APPAREIL:
            if champ in data:
                data[champ] = str(data[champ]).strip()
        ident = data.get(self.CLE_APPAREIL)
        base = self._appareil_par_id(ident) if ident else None
        if base is not None:
            for champ in ('ref_modele', 'commercial_ref', 'other_ref', 'notes'):
                data[champ] = (base.get(champ) or '').strip()
            for champ in self.CHAMPS_COMPLETABLES:
                data[champ] = (base.get(champ) or '').strip() or data.get(champ, '')
            # 3ᵉ colonne : rien à reporter sur l'appareil (_needs_update)
            data['other_ref'] = data['notes'] = ''
        return data

    def _appareil_par_id(self, ident) -> Optional[Dict[str, Any]]:
        """Appareil de la base par son id (lignes chargées pour le cache, sinon SQL)."""
        if not ident:
            return None
        if self._index_par_id is None:
            self._index_par_id = {}
            for row in getattr(self, '_existing_devices_rows_for_similarity', None) or ():
                self._index_par_id[row[0]] = dict(zip(('id',) + self._CHAMPS_APPAREIL, row))
        entree = self._index_par_id.get(ident)
        if entree is None:
            rows = self.db_manager.execute_query(
                "SELECT id, ref_modele, commercial_ref, type, manufacturer, other_ref, notes "
                "FROM appareils WHERE id = ?", [ident]) or []
            if rows:
                entree = self._index_par_id[ident] = dict(zip(('id',) + self._CHAMPS_APPAREIL, rows[0]))
        return entree

    @staticmethod
    def _cellule(row: List[str], i: int) -> str:
        """Valeur de la colonne i, nettoyée ; "" pour une cellule None."""
        return str(row[i]).strip() if row[i] is not None else ""

    @staticmethod
    def _lire_ligne_par_mapping(row: List[str], mapping: List[str]) -> Dict[str, Any]:
        """Mode mapping personnalisé : chaque colonne va au champ désigné, sauf
        « ignore » ; une cellule None ne crée pas de champ."""
        n = len(row)
        data = {}
        for i, champ in enumerate(mapping):
            if i < n and champ != "ignore" and row[i] is not None:
                data[champ] = str(row[i]).strip()
        return data

    @staticmethod
    def _lire_ligne_par_position(row: List[str], third_column_choice: str) -> Dict[str, Any]:
        """Mode positionnel (repli historique, inchangé) :
        - 1-3 colonnes : ref_modele, commercial_ref, puis la 3e vers other_ref ou
          notes selon `third_column_choice` (« ignore » : rien) ;
        - 4 colonnes et plus : type, manufacturer, ref_modele, commercial_ref (les
          deux réfs sont réécrites à leur place d'origine dans le dict) ;
        - 5e colonne : remplace la valeur de la 3e dans other_ref / notes.
        L'ordre des clés est celui de toujours."""
        data = {}
        cellule = ImportManager._cellule

        if len(row) >= 1:
            data['ref_modele'] = cellule(row, 0)

        if len(row) >= 2:
            data['commercial_ref'] = cellule(row, 1)

        if len(row) >= 3:
            ImportManager._ranger_colonne_choisie(data, cellule(row, 2), third_column_choice)

        if len(row) >= 4:
            data['type'] = cellule(row, 0)
            data['manufacturer'] = cellule(row, 1)
            data['ref_modele'] = cellule(row, 2)
            data['commercial_ref'] = cellule(row, 3)

        if len(row) >= 5:
            ImportManager._ranger_colonne_choisie(data, cellule(row, 4), third_column_choice)

        return data

    @staticmethod
    def _ranger_colonne_choisie(data: Dict[str, Any], valeur: str, choix: str) -> None:
        """Ranger la colonne libre dans other_ref ou notes ; « ignore » : rien."""
        if choix == "other_ref":
            data['other_ref'] = valeur
        elif choix == "notes":
            data['notes'] = valeur

    def _normaliser_casse(self, data: Dict[str, Any]) -> None:
        """Marque et type importés réécrits selon la base (« DELTA » → « Delta »),
        avant l'auto-complétion. Commun aux deux modes de parsing, donc aux deux
        chemins."""
        if data.get('manufacturer'):
            data['manufacturer'] = self._marques.normaliser(data['manufacturer'])
        if data.get('type'):
            data['type'] = self._types.normaliser(data['type'])

    def _needs_manual_completion(self, device_data: Dict[str, Any]) -> bool:
        """Vérifier si un appareil a besoin d'une complétion manuelle (ni type ni fabricant)"""
        type_val = device_data.get('type') or ''
        manufacturer_val = device_data.get('manufacturer') or ''
        type_empty = not str(type_val).strip()
        manufacturer_empty = not str(manufacturer_val).strip()
        return type_empty and manufacturer_empty
    
    @handle_database_operation_errors(return_value=None, log_prefix="Erreur mise à jour appareil")
    def _update_existing_device(self, device_id: int, device_data: Dict[str, Any]) -> None:
        """Mettre à jour un appareil existant avec les nouvelles données de la 3ème colonne"""
        # Construire les données de mise à jour pour la 3ème colonne uniquement
        update_data = {}

        # Si les données contiennent other_ref ou notes (depuis 3ème colonne), les ajouter
        if 'other_ref' in device_data and device_data['other_ref'].strip():
            update_data['other_ref'] = device_data['other_ref'].strip()

        if 'notes' in device_data and device_data['notes'].strip():
            update_data['notes'] = device_data['notes'].strip()

        if update_data:
            # Construire la requête de mise à jour
            set_clauses = [f"{field} = ?" for field in update_data.keys()]
            update_query = f"UPDATE appareils SET {', '.join(set_clauses)} WHERE id = ?"
            params = list(update_data.values()) + [device_id]

            # execute_write (commité) et non execute_query : sans commit, la mise
            # à jour était perdue si elle était la dernière écriture avant la fermeture.
            self.db_manager.execute_write(update_query, params)
            app_logger.debug(f" Appareil {device_id} mis à jour avec 3ème colonne: {update_data}")
    
    def _completer_existant(self, device_id: int, device_data: Dict[str, Any]) -> None:
        """Chemin standard : la garde SQL tient lieu du cache du chemin batch."""
        champs = self._champs_a_completer(device_data)
        if champs:
            self._completer_appareils_existants([(device_id, device_data, champs)])

    @handle_database_operation_errors(return_value=None, log_prefix="Erreur insertion appareil")
    def _insert_or_find_device(self, device_data: Dict[str, Any],
                               completer: bool = True) -> Optional[int]:
        """Insérer ou trouver un appareil existant.

        Un appareil retrouvé reçoit la 3ᵉ colonne (other_ref / notes) de la ligne et
        son Type/Fabricant là où il est vide en base — seulement à la 1ʳᵉ occurrence
        de la ligne (`completer`), comme sur le chemin batch : sur un doublon, la
        première valeur l'emporte.

        La résolution reproduit exactement la clé composite du chemin batch
        (_find_in_cache) : une ligne complète ne correspond qu'à un appareil
        complet, une ligne partielle qu'à un appareil partiel de même forme.
        Verrouillé par tests/unit/test_import_paths_equivalence.py.
        """
        # Import hissé en tête : un « from .config import Config » plus bas
        # rendrait Config local à TOUTE la fonction (piège connu du projet).
        from .config import Config

        # Chercher d'abord un appareil existant
        ref_modele = (device_data.get('ref_modele') or '').strip()
        commercial_ref = (device_data.get('commercial_ref') or '').strip()

        if ref_modele or commercial_ref:
            # Recherche stricte : un appareil est identique si TOUTES les références principales correspondent
            # Cela évite les faux positifs comme 2108002 vs 2108002000 avec même commercial_ref
            search_query = """
                SELECT id FROM appareils
                WHERE ref_modele = ? AND commercial_ref = ?
                   AND ref_modele != '' AND commercial_ref != ''
                LIMIT 1
            """
            results = self.db_manager.execute_query(search_query, [ref_modele, commercial_ref])

            existing_id = results[0][0] if results else None

            # Repli « ref_modele seule » — ne s'applique QUE si la ligne entrante est
            # elle-même partielle. Sans cette garde, une ligne COMPLÈTE se rattachait
            # à un appareil partiel existant et sa référence commerciale était perdue :
            # 2 appareils au lieu de 3 sur le chemin standard, 3 sur le chemin batch
            # (divergence B mesurée en v3.69.1). La doctrine v3.66.1 — « un appareil
            # partiel ne correspond qu'à un autre appareil partiel » — est ainsi tenue.
            if existing_id is None and ref_modele and not commercial_ref:
                search_query_ref = """
                    SELECT id FROM appareils
                    WHERE ref_modele = ? AND ref_modele != ''
                       AND (commercial_ref = '' OR commercial_ref IS NULL)
                    LIMIT 1
                """
                results_ref = self.db_manager.execute_query(search_query_ref, [ref_modele])
                if results_ref:
                    existing_id = results_ref[0][0]

            # Cas miroir : seule commercial_ref correspond (v3.65.1).
            #
            # Ce repli n'existait pas : un lot ne renseignant QUE commercial_ref
            # n'était retrouvé par aucune des deux requêtes ci-dessus (la 1ʳᵉ exige
            # les deux références non vides, la 2ᵉ exige ref_modele). Chaque
            # ré-import recréait donc les appareils. Trou symétrique du bug du
            # chemin batch corrigé dans _preload_existing_devices / _find_in_cache.
            #
            # Garde symétrique du repli ci-dessus : les deux sont désormais
            # mutuellement exclusifs (l'un exige commercial_ref vide, l'autre
            # ref_modele vide), il n'y a donc plus de priorité à arbitrer.
            if existing_id is None and commercial_ref and not ref_modele:
                search_query_com = """
                    SELECT id FROM appareils
                    WHERE commercial_ref = ? AND commercial_ref != ''
                       AND (ref_modele = '' OR ref_modele IS NULL)
                    LIMIT 1
                """
                results_com = self.db_manager.execute_query(search_query_com, [commercial_ref])
                if results_com:
                    existing_id = results_com[0][0]

            # Appareil retrouvé, quelle que soit la recherche qui l'a trouvé (v3.88.4).
            # Jusqu'en v3.88.2, seule la recherche stricte écrivait la 3ᵉ colonne : les
            # replis mono-référence la perdaient (le batch l'écrit pour tout appareil
            # existant), et un doublon la réécrivait — dernière valeur gagnante contre
            # première sur le batch, qui ne traite pas les doublons.
            if existing_id is not None:
                if completer:
                    self._update_existing_device(existing_id, device_data)
                    self._completer_existant(existing_id, device_data)
                return existing_id

        # Créer un nouvel appareil.
        # Champs absents complétés à '' — exactement ce que fait _batch_insert_devices
        # avec ses device.get(champ, ''). Sans cela le chemin standard n'insérait que
        # les colonnes présentes et laissait SQLite écrire NULL, si bien que
        # « WHERE type = '' » ne ramenait pas les mêmes lignes selon la taille du
        # fichier importé (divergence A mesurée en v3.69.1).
        # Copie et non mutation : device_data sert ensuite à la collecte des
        # suggestions par similarité, que le chemin batch ne modifie pas non plus.
        donnees_insert = {entete: device_data.get(entete, '') for entete in Config.DB_HEADERS}
        device_id = self.db_manager.insert_appareil(donnees_insert)
        if device_id:
            device_data['is_new'] = True
            self._tracer_autocompletions([(device_id, device_data, None)])
        return device_id
    
    @handle_database_operation_errors(return_value=False, log_prefix="Erreur auto-completion")
    def _try_auto_complete(self, appareil_data: dict) -> bool:
        """Compléter automatiquement Type et Fabricant à partir des références.
        Correspondance exacte uniquement sur les références non vides.
        Sélectionne la combinaison type+fabricant la plus fréquente en base.

        Returns:
            bool: True si au moins un champ a été complété
        """
        from .config import Config
        from ..services.proposition_type_fabricant import proposer_type_fabricant

        # Règle commune avec le bouton « Données → Autocomplétion » : exclusion des
        # auto-complétés non vérifiés comme source, confiance accord/total (v3.89.0).
        propositions = proposer_type_fabricant(self.db_manager, appareil_data)
        if not propositions:
            return False

        # Agrégé plutôt qu'unitaire (v3.66.0) : ces deux messages représentaient
        # à eux seuls ~550 000 lignes de log, soit le premier poste de volume.
        # Le total est journalisé une fois en fin d'import (_log_resume_import).
        libelles = {'type': 'Type', 'manufacturer': 'Fabricant'}
        for champ, proposition in propositions.items():
            appareil_data[champ] = proposition.valeur
            self._noter_autocompletion(
                appareil_data, champ, proposition.valeur, proposition.source,
                proposition.accord, proposition.total)
            self._log_counters[f'autocomplete_{champ}'] += 1
            if Config.LOG_VERBOSE_PER_DEVICE:
                app_logger.debug(f"  [OK] {libelles[champ]} complété: '' -> '{proposition.valeur}'")
        return True

    @handle_ui_operation_errors(return_value=None, log_prefix="Erreur mises à jour post-import")
    def _trigger_post_import_updates(self):
        """Déclencher les mises à jour post-import (Phase 4 - EventDrivenSaveService)"""
        # Déclencher la sauvegarde événementielle
        if hasattr(self.main_window, 'event_driven_save_service') and self.main_window.event_driven_save_service:
            self.main_window.event_driven_save_service.handle_import_completed()
            app_logger.debug("EventDrivenSaveService: Sauvegarde événementielle déclenchée après import")

        # Toujours déclencher la mise à jour du bouton "lignes à compléter"
        if hasattr(self.main_window, '_update_incomplete_button_visibility'):
            from ..utils.qt_imports import QTimer
            QTimer.singleShot(200, self.main_window._update_incomplete_button_visibility)
            app_logger.debug("Mise à jour bouton 'lignes à compléter' programmée")

        # Invalider le cache des doublons après import
        if hasattr(self.main_window, 'duplicate_indicator_service') and self.main_window.duplicate_indicator_service:
            self.main_window.duplicate_indicator_service.invalidate_cache("import")
            app_logger.debug("Cache doublons invalidé après import")
