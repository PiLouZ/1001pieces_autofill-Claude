"""
« Fiche PrestaShop et Cogilog » : la fiche de la pièce recherchée, prête pour les
deux imports d'EMG, ajoutée aux fichiers du jour (dossier des exports).

Tout vient des générateurs existants, sur la recherche en cours, comme les
boutons Titre, Fiche complète, Méta Title et Méta Desc (profils par défaut) ;
code produit et prix viennent de l'import Agora de la pièce (src/ui/agora_import.py) ;
la catégorie est proposée d'après data/categories_site.json. Tout reste modifiable.
Non bloquant : show() + callbacks, jamais exec_() (conventions du projet).
"""

import html
from typing import Optional

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from src.core.logger import app_logger
from src.utils.agora.conversion import code_emg_propose, prix_emg
from src.utils.agora.fiche import (CategoriesSite, FicheSite, ajouter_aux_fichiers_du_jour,
                                   fabricant_site)
from src.utils.agora.stockage import BaseAgora
from .style_manager import StyleManager


def _prix(texte: str) -> Optional[float]:
    try:
        return round(float(texte.replace('€', '').replace(',', '.').strip()), 2) or None
    except ValueError:
        return None


def _depuis_le_cache(base: BaseAgora, reference: str) -> dict:
    """Pièce importée avant que l'import ne retienne code et prix : on les
    recalcule d'après la réponse d'Agora gardée en cache (aucun appel)."""
    trouve = base.info_en_cache(reference)
    if not trouve:
        return {}
    constructeur, info = trouve
    p = prix_emg(info, constructeur)
    return {'constructeur': constructeur, 'code': code_emg_propose(reference, constructeur) or '',
            'prix_ttc': p.vente, 'regle_prix': p.regle}


def ouvrir_fiche_site(main_window):
    """Prépare la fiche de la recherche en cours ; les refus (pas de recherche,
    libellé manquant…) sont signalés par les services, comme pour les boutons."""
    relancer = lambda: ouvrir_fiche_site(main_window)
    ctx_titre = main_window.titre_produit_service.contexte(interactif=True, relancer=relancer)
    if not ctx_titre:
        return None
    ctx_fiche = main_window.fiche_produit_service.contexte(interactif=True)
    if not ctx_fiche:
        return None
    donnees = ctx_titre['donnees']
    seo = main_window.seo_service
    reference = donnees['reference']
    base = BaseAgora()
    agora = base.fiche(reference) or _depuis_le_cache(base, reference)
    code = agora.get('code') or code_emg_propose(reference, -1) or ''
    fiche = FicheSite(
        code=code,
        nom=main_window.titre_produit_service.rendre(ctx_titre, None)['html'],
        libelle=donnees.get('description') or '',
        reference=reference,
        prix_ttc=agora.get('prix_ttc'),
        categorie=CategoriesSite().proposer(donnees.get('description') or '',
                                            donnees.get('type_appareil') or ''),
        fabricant=fabricant_site(code, agora.get('constructeur')),
        description=main_window.fiche_produit_service.rendre(ctx_fiche, None)['html'],
        meta_title=seo.calculer_meta_title(donnees)['title'],
        meta_description=seo.calculer_meta_description(donnees)['description'],
    )
    dialogue = FicheSiteDialog(main_window, fiche, agora, ctx_titre, ctx_fiche)
    dialogue.show()
    return dialogue


class FicheSiteDialog(QDialog):
    def __init__(self, main_window, fiche: FicheSite, agora: dict, ctx_titre=None, ctx_fiche=None):
        super().__init__(main_window)
        self.main_window, self.fiche, self.agora = main_window, fiche, agora
        self.ctx_titre, self.ctx_fiche = ctx_titre, ctx_fiche
        self.dossier = ''
        self.setWindowTitle(f"Fiche PrestaShop et Cogilog — {fiche.reference}")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(820, 420)
        self._construire()

    def _construire(self):
        f = self.fiche
        racine = QVBoxLayout(self)
        racine.setContentsMargins(12, 12, 12, 12)
        if not self.agora:
            info = QLabel("Pièce non importée depuis Agora : code et prix à saisir.")
            info.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT)
            racine.addWidget(info)
        formulaire = QFormLayout()
        self.champ_code = QLineEdit(f.code)
        self.champ_code.setToolTip("Référence PrestaShop = code Cogilog (préfixe + référence constructeur)")
        self.champ_nom = QLineEdit(f.nom)
        self.champ_categorie = QComboBox()
        self.champ_categorie.setEditable(True)
        self.champ_categorie.addItems([''] + CategoriesSite().categories)
        self.champ_categorie.setCurrentText(f.categorie)
        self.champ_fabricant = QLineEdit(f.fabricant)
        self.champ_prix = QLineEdit(f"{f.prix_ttc:.2f}".replace('.', ',') if f.prix_ttc else '')
        self.champ_prix.textChanged.connect(self._maj_ht)
        self.prix_ht = QLabel()
        self.prix_ht.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        ligne_prix = QHBoxLayout()
        ligne_prix.addWidget(self.champ_prix)
        ligne_prix.addWidget(self.prix_ht, 1)
        self.champ_meta_title = QLineEdit(f.meta_title)
        self.champ_meta_description = QLineEdit(f.meta_description)
        formulaire.addRow("Code produit :", self.champ_code)
        config = getattr(self.main_window, 'export_config_service', None)
        self.gabarit_titre = self._choix_gabarit(
            config.get_titre_profile_names() if config else [],
            config.get_default_titre_profile_name() if config else '', self._maj_titre)
        self.gabarit_fiche = self._choix_gabarit(
            config.get_fiche_profile_names() if config else [],
            config.get_default_fiche_profile_name() if config else '', self._maj_description)
        formulaire.addRow("Gabarit du nom :", self.gabarit_titre)
        formulaire.addRow("Nom :", self.champ_nom)
        formulaire.addRow("Catégorie :", self.champ_categorie)
        formulaire.addRow("Fabricant :", self.champ_fabricant)
        formulaire.addRow("Prix TTC :", ligne_prix)
        formulaire.addRow("Méta title :", self.champ_meta_title)
        formulaire.addRow("Méta description :", self.champ_meta_description)
        formulaire.addRow("Gabarit de la description :", self.gabarit_fiche)
        self.resume_description = QLabel()
        formulaire.addRow("Description :", self.resume_description)
        self._maj_resume()
        racine.addLayout(formulaire)
        self._maj_ht()

        pied = QHBoxLayout()
        self.etat = QLabel("Fiche inactive dans l'import PrestaShop : elle s'active une fois la photo faite.")
        self.etat.setWordWrap(True)
        self.etat.setStyleSheet(StyleManager.TEXTE_SECONDAIRE)
        pied.addWidget(self.etat, 1)
        fermer = QPushButton("Fermer")
        fermer.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        fermer.clicked.connect(self.close)
        self.bouton_dossier = QPushButton("Ouvrir le dossier")
        self.bouton_dossier.setStyleSheet(StyleManager.SECONDARY_ACTION_BUTTON)
        self.bouton_dossier.setVisible(False)
        self.bouton_dossier.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.dossier)))
        ajouter = QPushButton("Ajouter aux fichiers du jour")
        ajouter.setStyleSheet(StyleManager.PRIMARY_ACTION_BUTTON)
        ajouter.setDefault(True)
        ajouter.clicked.connect(self.ajouter)
        pied.addWidget(fermer)
        pied.addWidget(self.bouton_dossier)
        pied.addWidget(ajouter)
        racine.addLayout(pied)

    @staticmethod
    def _choix_gabarit(noms, defaut, rappel) -> QComboBox:
        choix = QComboBox()
        choix.addItems(list(noms))
        if defaut:
            choix.setCurrentText(defaut)
        choix.currentTextChanged.connect(lambda *_: rappel())
        return choix

    def _maj_titre(self):
        if self.ctx_titre is not None:
            self.champ_nom.setText(self.main_window.titre_produit_service.rendre(
                self.ctx_titre, self.gabarit_titre.currentText() or None)['html'])

    def _maj_description(self):
        if self.ctx_fiche is not None:
            self.fiche.description = self.main_window.fiche_produit_service.rendre(
                self.ctx_fiche, self.gabarit_fiche.currentText() or None)['html']
        self._maj_resume()

    def _maj_resume(self):
        regle = f" · prix : {html.escape(self.agora['regle_prix'])}" if self.agora.get('regle_prix') else ''
        self.resume_description.setText(
            f"{len(self.fiche.description)} caractères · photo : provisoire, à faire au studio{regle}")

    def _maj_ht(self):
        ttc = _prix(self.champ_prix.text())
        self.prix_ht.setText(f"soit {ttc / 1.2:.2f} € HT".replace('.', ',') if ttc else "prix à saisir")

    def ajouter(self):
        f = self.fiche
        f.code = self.champ_code.text().strip()
        f.nom = self.champ_nom.text().strip()
        f.categorie = self.champ_categorie.currentText().strip()
        f.fabricant = self.champ_fabricant.text().strip()
        f.prix_ttc = _prix(self.champ_prix.text())
        f.meta_title = self.champ_meta_title.text().strip()
        f.meta_description = self.champ_meta_description.text().strip()
        if not f.code:
            self.etat.setText("Le code produit est obligatoire : c'est lui qui relie Cogilog et PrestaShop.")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        from src.services.export_config_service import resolve_output_dir
        self.dossier = resolve_output_dir(getattr(self.main_window, 'export_config_service', None))
        try:
            r = ajouter_aux_fichiers_du_jour(f, self.dossier)
        except OSError as e:
            app_logger.error(f"[Agora] fiche {f.code} non écrite : {e}")
            self.etat.setText(f"Écriture impossible : {e}")
            self.etat.setStyleSheet(StyleManager.TEXTE_ERREUR_SOMBRE)
            return
        manques = f.manques()
        texte = (f"Fiche {f.code} ajoutée ({r['fiches']} fiche(s) aujourd'hui)"
                 + (f" — à compléter : {', '.join(manques)}" if manques else "") + ".")
        self.etat.setText(texte)
        self.etat.setStyleSheet(StyleManager.TEXTE_AVERTISSEMENT if manques else StyleManager.TEXTE_SECONDAIRE)
        self.bouton_dossier.setVisible(True)
        historique = getattr(self.main_window, 'user_interaction_service', None)
        if historique is not None:
            historique.add_to_history(
                f"Fiche PrestaShop / Cogilog : {f.code} ({f.reference})\n==> {f.nom}\n"
                f"==> {r['prestashop']}\n==> {r['cogilog']}")
