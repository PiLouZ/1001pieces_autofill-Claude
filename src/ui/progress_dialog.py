"""
ProgressDialog : dialogue de progression custom (drop-in replacement de QProgressDialog).

API publique identique à QProgressDialog pour minimiser les changements côté appelant :
    dlg = ProgressDialog("Titre", "Annuler", 0, total, parent)
    dlg.setLabelText("Étape courante…")
    dlg.setValue(n)
    dlg.wasCanceled() -> bool
    dlg.show() / dlg.close()
"""

from .qt_imports import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                          QPushButton, QProgressBar, Qt, QSize, QSizePolicy,
                          pyqtSignal)
import qtawesome as qta


class ProgressDialog(QDialog):
    """
    Dialogue de progression sobre avec spinner qtawesome animé permanent,
    barre de progression stylisée et étape courante.

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

        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(420)
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
        self._spinner_btn.setStyleSheet("border: none; background: transparent;")
        header.addWidget(self._spinner_btn)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #212529;")
        header.addWidget(self._title_label, 1)
        layout.addLayout(header)

        # ── Étape courante ───────────────────────────────────────────────────
        self._step_label = QLabel("")
        self._step_label.setStyleSheet(
            "color: #6c757d; font-size: 11px;")
        self._step_label.setWordWrap(True)
        layout.addWidget(self._step_label)

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
        self._counter_label.setStyleSheet("color: #adb5bd; font-size: 10px;")
        bottom.addWidget(self._counter_label)
        bottom.addStretch()

        if cancel_button_text:
            self._cancel_btn = QPushButton(cancel_button_text)
            self._cancel_btn.setStyleSheet(
                "QPushButton { font-size: 11px; padding: 3px 12px; }"
            )
            self._cancel_btn.clicked.connect(self._on_cancel)
            bottom.addWidget(self._cancel_btn)
        else:
            self._cancel_btn = None

        layout.addLayout(bottom)

        self._update_counter()

    # ── API publique (compatible QProgressDialog) ────────────────────────────

    def setLabelText(self, text: str):
        self._step_label.setText(text)

    def setValue(self, value: int):
        self._value = max(self._minimum, min(value, self._maximum))
        self._bar.setValue(self._value)
        self._update_counter()
        # Fermeture automatique quand la valeur atteint le maximum
        if self._maximum > 0 and self._value >= self._maximum:
            self.close()

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

    def _on_cancel(self):
        self._canceled = True
        self.canceled.emit()
        self.close()

    def _update_counter(self):
        if self._maximum <= 0:
            # Mode indéfini
            self._bar.setRange(0, 0)
            self._counter_label.setText("")
        else:
            pct = int(self._value / self._maximum * 100) if self._maximum > 0 else 0
            self._counter_label.setText(
                f"{self._value} / {self._maximum}  ({pct} %)")
