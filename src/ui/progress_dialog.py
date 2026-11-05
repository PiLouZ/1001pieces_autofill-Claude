"""
ProgressDialog : dialogue de progression custom (drop-in replacement de QProgressDialog).

API publique identique à QProgressDialog pour minimiser les changements côté appelant :
    dlg = ProgressDialog("Titre", "Annuler", 0, total, parent)
    dlg.setLabelText("Étape courante…")
    dlg.setValue(n)
    dlg.wasCanceled() -> bool
    dlg.show() / dlg.close()
"""

import re
import time

from ..utils.qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
                          QPushButton, QProgressBar, QScrollArea, QFrame, QTimer,
                          Qt, QSize, QSizePolicy, pyqtSignal)
import qtawesome as qta
from .style_manager import StyleManager
from ..core.config import pluralize


# ── Journal d'étapes : découpage des libellés (fonctions pures, testées) ─────

_RE_PAGE = re.compile(r"\s*:\s*page\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_RE_COMPTEUR = re.compile(r"\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)")
# « Import de X.pdf », « Extraction de X.pdf » → sujet = nom de fichier
_RE_SUJET_FICHIER = re.compile(r"^\S+\s+de\s+(.+\.\w{2,4})$")

_MAX_LIGNES_VISIBLES = 8


def _milliers(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")


def analyser_etape(texte: str):
    """Découpe un libellé de progression en (étape, détail, total_pages).

    - « Extraction de a.pdf : page 560/1667 (1/1) » → ("Extraction de a.pdf",
      "page 560 / 1 667", 1667)
    - « Recherche de suggestions… (12/17) » → ("Recherche de suggestions", "12 / 17", None)
    - « Pré-chargement du cache… » → ("Pré-chargement du cache", "", None)

    L'étape sert de clé : tant qu'elle ne change pas, seule la ligne courante est
    mise à jour (pas une nouvelle ligne par page ou par élément traité).
    """
    t = (texte or "").strip()
    detail, total_pages = "", None
    page = _RE_PAGE.search(t)
    if page:
        detail = f"page {_milliers(int(page.group(1)))} / {_milliers(int(page.group(2)))}"
        total_pages = int(page.group(2))
        t = t[:page.start()] + t[page.end():]
    compteurs = _RE_COMPTEUR.findall(t)
    t = _RE_COMPTEUR.sub("", t)
    if not detail and compteurs:
        a, b = compteurs[-1]
        detail = f"{_milliers(int(a))} / {_milliers(int(b))}"
    # Convention « Étape — détail » : le détail (fichier en cours…) n'ouvre pas de
    # nouvelle ligne ; sans elle, un message par fichier copié en créait des centaines.
    if " — " in t:
        t, _, suite = t.partition(" — ")
        if not detail:
            detail = _abreger(suite.strip())
    etape = t.strip().rstrip("…. :").strip()
    return etape, detail, total_pages


def _abreger(texte: str, maxi: int = 40) -> str:
    """Raccourcit par la gauche (« …/ui/fichier.py ») : la fin d'un chemin est
    la partie parlante."""
    return texte if len(texte) <= maxi else "…" + texte[-(maxi - 1):]


def meme_fichier(etape_a: str, etape_b: str) -> bool:
    """« Import de X.pdf » puis « Extraction de X.pdf » : une seule et même étape
    (l'extraction EST l'import de ce fichier) → pas de ligne en double."""
    ma, mb = _RE_SUJET_FICHIER.match(etape_a or ""), _RE_SUJET_FICHIER.match(etape_b or "")
    return bool(ma and mb and ma.group(1) == mb.group(1))


def formater_duree(secondes: float) -> str:
    """0.42 → « 0,4 s » ; 48.3 → « 48 s » ; 125 → « 2 min 05 s »."""
    if secondes < 10:
        return f"{secondes:.1f} s".replace(".", ",")
    if secondes < 60:
        return f"{int(round(secondes))} s"
    m, s = divmod(int(round(secondes)), 60)
    return f"{m} min {s:02d} s"


class ProgressDialog(QDialog):
    """
    Dialogue de progression sobre avec spinner qtawesome animé permanent,
    journal des étapes (une ligne par étape : terminées cochées avec leur durée,
    étape courante en gras avec son détail) et barre de progression.

    Le journal se construit seul à partir des setLabelText() successifs : un
    changement d'étape (libellé hors compteurs) ajoute une ligne, un simple
    changement de compteur met à jour la ligne courante. Aucun appelant à adapter.

    Remplace QProgressDialog partout dans l'app avec une API compatible.
    """

    canceled = pyqtSignal()   # émis quand l'utilisateur clique Annuler

    def __init__(self, title: str, cancel_button_text: str | None,
                 minimum: int, maximum: int, parent=None):
        super().__init__(parent)

        self._canceled = False
        self._minimum  = minimum
        self._maximum  = maximum
        self._value    = minimum

        # Journal : [{'etape', 'debut', 'pages', 'widgets'}] ; dernière = courante
        self._etapes = []
        self._t0 = time.monotonic()

        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(460)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QDialog {
                background: #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # ── En-tête : spinner + titre ────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        self._spinner_btn = QPushButton()
        self._spinner_btn.setFlat(True)
        self._spinner_btn.setEnabled(False)
        self._spinner_btn.setFixedSize(28, 28)
        self._spinner_btn.setIconSize(QSize(20, 20))
        self._spinner_btn.setIcon(
            qta.icon('fa5s.circle-notch', color='#495057',
                     animation=qta.Spin(self._spinner_btn)))
        self._spinner_btn.setStyleSheet(StyleManager.FLAT_TRANSPARENT)
        header.addWidget(self._spinner_btn)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #212529;")
        header.addWidget(self._title_label, 1)
        layout.addLayout(header)

        # ── Journal des étapes (défile au-delà de _MAX_LIGNES_VISIBLES) ──────
        self._journal_scroll = QScrollArea()
        self._journal_scroll.setWidgetResizable(True)
        self._journal_scroll.setFrameShape(QFrame.NoFrame)
        self._journal_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._journal_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._journal_scroll.viewport().setAutoFillBackground(False)
        journal = QWidget()
        journal.setStyleSheet("background: transparent;")
        self._journal_layout = QVBoxLayout(journal)
        self._journal_layout.setContentsMargins(0, 0, 0, 0)
        self._journal_layout.setSpacing(4)
        self._journal_layout.setAlignment(Qt.AlignTop)
        self._journal_scroll.setWidget(journal)
        self._journal_scroll.setVisible(False)   # jusqu'à la 1re étape
        layout.addWidget(self._journal_scroll)

        # ── Barre de progression ─────────────────────────────────────────────
        self._bar = QProgressBar()
        self._bar.setRange(minimum, maximum)
        self._bar.setValue(minimum)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background: #e9ecef;
            }
            QProgressBar::chunk {
                border-radius: 3px;
                background: #495057;
            }
        """)
        layout.addWidget(self._bar)

        # ── Ligne compteur + bouton Annuler ──────────────────────────────────
        bottom = QHBoxLayout()

        self._counter_label = QLabel("")
        self._counter_label.setStyleSheet("color: #adb5bd; font-size: 11px;")
        bottom.addWidget(self._counter_label)
        bottom.addStretch()

        if cancel_button_text:
            self._cancel_btn = QPushButton(cancel_button_text)
            self._cancel_btn.clicked.connect(self._on_cancel)
            bottom.addWidget(self._cancel_btn)
        else:
            self._cancel_btn = None

        layout.addLayout(bottom)

        # Rafraîchit chaque seconde le temps écoulé (étapes longues et muettes,
        # ex. préparation de l'index de suggestions)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_counter)
        self._tick.start(1000)

        self._update_counter()

    # ── API publique (compatible QProgressDialog) ────────────────────────────

    def setLabelText(self, text: str):
        etape, detail, pages = analyser_etape(text)
        if not etape:
            return
        courante = self._etapes[-1] if self._etapes else None
        if courante and (courante['etape'] == etape or meme_fichier(courante['etape'], etape)):
            courante['etape'] = etape            # « Import de X » → « Extraction de X »
            if pages:
                courante['pages'] = pages
            self._peindre_ligne(courante, detail=detail)
        else:
            if courante:
                courante['fin'] = time.monotonic()
                self._peindre_ligne(courante)
            self._ajouter_ligne(etape, detail, pages)
        self._update_counter()

    def setValue(self, value: int):
        self._value = max(self._minimum, min(value, self._maximum))
        self._bar.setValue(self._value)
        self._update_counter()
        # PAS de fermeture automatique à value == maximum (contrairement à
        # QProgressDialog) : ce dialogue est réutilisé sur plusieurs phases
        # successives à échelles différentes (ex. import de N fichiers, puis
        # recherche de suggestions sur M candidats, puis mise à jour de
        # l'affichage) via des setRange()/setValue() distincts. Une fermeture
        # ici masquait le dialogue dès la fin de la 1ère phase alors que les
        # phases suivantes (invisibles pour l'utilisateur) tournaient encore.
        # Chaque appelant ferme explicitement via close() à la toute fin.

    def setRange(self, minimum: int, maximum: int):
        self._minimum = minimum
        self._maximum = maximum
        self._bar.setRange(minimum, maximum)
        self._update_counter()

    def setMinimumDuration(self, ms: int):
        """Compatibilité QProgressDialog — ignoré (affichage immédiat via show())."""
        pass

    def wasCanceled(self) -> bool:
        return self._canceled

    def reset(self):
        self._canceled = False
        self._value = self._minimum
        self._bar.setValue(self._minimum)
        self._update_counter()

    # ── Interne ──────────────────────────────────────────────────────────────

    def _ajouter_ligne(self, etape: str, detail: str, pages):
        ligne = QWidget()
        lay = QHBoxLayout(ligne)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        icone = QLabel()
        icone.setFixedSize(14, 14)
        icone.setAlignment(Qt.AlignCenter)
        texte = QLabel()
        texte.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # coupe si trop long
        droite = QLabel()
        droite.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(icone)
        lay.addWidget(texte, 1)
        lay.addWidget(droite)
        self._journal_layout.addWidget(ligne)
        entree = {'etape': etape, 'debut': time.monotonic(), 'fin': None,
                  'pages': pages, 'detail': detail, 'widgets': (icone, texte, droite)}
        self._etapes.append(entree)
        self._peindre_ligne(entree, detail=detail)
        self._ajuster_journal()

    def _peindre_ligne(self, entree, detail=None):
        """Ligne terminée : coche verte + durée. Courante : point bleu, gras, détail."""
        icone, texte, droite = entree['widgets']
        if detail is not None:
            entree['detail'] = detail
        libelle = entree['etape']
        if entree['fin'] is not None:
            if entree['pages']:
                libelle += f" · {_milliers(entree['pages'])} {'page' if entree['pages'] == 1 else 'pages'}"
            icone.setPixmap(qta.icon('fa5s.check', color='#198754').pixmap(11, 11))
            texte.setStyleSheet("color: #495057; font-size: 12px;")
            droite.setStyleSheet("color: #adb5bd; font-size: 11px;")
            droite.setText(formater_duree(entree['fin'] - entree['debut']))
        else:
            icone.setPixmap(qta.icon('fa5s.circle', color='#0d6efd').pixmap(7, 7))
            texte.setStyleSheet("color: #212529; font-size: 12px; font-weight: bold;")
            droite.setStyleSheet("color: #0d6efd; font-size: 11px;")
            droite.setText(entree['detail'] or formater_duree(time.monotonic() - entree['debut']))
        texte.setText(libelle)
        texte.setToolTip(libelle)

    def _ajuster_journal(self):
        """Hauteur du journal = ses lignes, plafonnée ; défilement vers la dernière."""
        self._journal_scroll.setVisible(True)
        n = min(len(self._etapes), _MAX_LIGNES_VISIBLES)
        hauteur_ligne = 20
        self._journal_scroll.setFixedHeight(n * hauteur_ligne + (n - 1) * 4)
        # Méthode liée à la fenêtre (et non lambda) : Qt annule l'appel différé si
        # la fenêtre est détruite entre-temps (fermeture juste après la dernière étape)
        QTimer.singleShot(0, self._defiler_en_bas)
        self.adjustSize()

    def _defiler_en_bas(self):
        bar = self._journal_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_cancel(self):
        self._canceled = True
        self.canceled.emit()
        self.close()

    def _update_counter(self):
        """Pied : « Étape N · 22 s au total » (+ % si la barre est déterminée).

        L'ancien « 335 / 1000 (33 %) » exposait l'échelle interne de la barre
        (sous-graduation des pages PDF), sans signification pour l'utilisateur.
        """
        if self._maximum <= 0:
            self._bar.setRange(0, 0)   # mode indéfini
        morceaux = []
        if self._etapes:
            morceaux.append(f"Étape {len(self._etapes)}")
        if self._maximum > 0:
            morceaux.append(f"{int(self._value / self._maximum * 100)} %")
        morceaux.append(f"{formater_duree(time.monotonic() - self._t0)} au total")
        self._counter_label.setText(" · ".join(morceaux))
        # Étape courante sans compteur : son temps écoulé avance aussi
        if self._etapes and self._etapes[-1]['fin'] is None and not self._etapes[-1]['detail']:
            self._peindre_ligne(self._etapes[-1])

    def done(self, r):
        self._tick.stop()
        super().done(r)

    def closeEvent(self, event):
        self._tick.stop()
        super().closeEvent(event)
