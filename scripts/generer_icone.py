#!/usr/bin/env python3
"""
Génère l'icône de l'application : `app_icon.png` (1024 × 1024, fond transparent).

Gabarit des icônes macOS : carré arrondi de 824 px centré dans 1024, ombre
douce dessous. Couleurs reprises du logo 1001pieces (bleu marine #09376e,
bleu #4d7ac1) ; la clé vient de qtawesome (`fa5s.wrench`), déjà utilisé par l'UI.

`app_icon.png` sert à trois endroits :
  - l'icône du lanceur `1001pieces_autofill.app` (via `export_app._inject_icon`) ;
  - l'application exportée pour une autre machine (même fonction) ;
  - le Dock et les fenêtres pendant l'exécution (`QApplication.setWindowIcon`).

Usage :
    QT_QPA_PLATFORM=offscreen python3 scripts/generer_icone.py
"""

from pathlib import Path

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath
from PyQt5.QtWidgets import QApplication

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "app_icon.png"

COTE = 1024
CARRE = QRectF(100, 100, 824, 824)
RAYON = 185
MARINE = QColor("#09376e")
BLEU_HAUT = QColor("#2f63ad")


def _police(taille_px: int, graisse: int) -> QFont:
    police = QFont("Helvetica Neue")
    police.setPixelSize(taille_px)
    police.setWeight(graisse)
    return police


def generer(sortie: Path = SORTIE) -> Path:
    import qtawesome as qta

    image = QImage(COTE, COTE, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                     | QPainter.SmoothPixmapTransform)

    # Ombre douce (trois couches décalées vers le bas)
    for i, alpha in enumerate((18, 12, 7)):
        ombre = QPainterPath()
        ombre.addRoundedRect(CARRE.translated(0, 8 + i * 6), RAYON, RAYON)
        p.fillPath(ombre, QColor(0, 0, 0, alpha))

    # Fond : dégradé bleu → marine
    fond = QPainterPath()
    fond.addRoundedRect(CARRE, RAYON, RAYON)
    degrade = QLinearGradient(QPointF(0, CARRE.top()), QPointF(0, CARRE.bottom()))
    degrade.setColorAt(0, BLEU_HAUT)
    degrade.setColorAt(1, MARINE)
    p.fillPath(fond, degrade)

    # « 1001 »
    police = _police(300, QFont.Black)
    police.setLetterSpacing(QFont.PercentageSpacing, 92)
    p.setFont(police)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(100, 205, 824, 330), Qt.AlignHCenter | Qt.AlignVCenter, "1001")

    # Clé + « pièces »
    cle = qta.icon("fa5s.wrench", color=QColor(255, 255, 255, 200)).pixmap(190, 190).toImage()
    p.drawImage(QRectF(205, 560, 170, 170), cle)
    p.setFont(_police(150, QFont.Bold))
    p.setPen(QColor("#cfe0f7"))
    p.drawText(QRectF(385, 545, 460, 200), Qt.AlignLeft | Qt.AlignVCenter, "pièces")

    p.end()
    if not image.save(str(sortie)):
        raise OSError(f"Écriture impossible : {sortie}")
    return sortie


if __name__ == "__main__":
    app = QApplication([])
    print(f"Icône écrite : {generer()}")
