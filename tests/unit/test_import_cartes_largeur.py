"""
Cartes « Références individuelles par fichier » de l'import multi-fichiers.

Cas réel du 2026-11-17 : trois PDF (264440194, C00871425, 264440188). La carte
Indesit affichait « Réf. associée » ; sa 1ʳᵉ ligne (réf. + réf. associée + nom
de fichier) dépassait la colonne de gauche, plafonnée : toutes les cartes étaient
coupées à droite (case « Obsolète », champ « Remplacée par »). Les deux réfs Beko
de 9 chiffres (en 26) n'avaient pas de champ « Réf. associée ».

- les cartes tiennent dans la zone, sans être coupées ;
- le nom de fichier identique à la référence n'est pas répété ;
- les réfs de 9 chiffres en 16 / 26 sont Beko : elles ont leur champ ;
- une réf. glissée (tuile « Non groupées ») se dépose sur le champ.
"""

import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QMimeData, QPoint, Qt
from PyQt5.QtGui import QDropEvent
from PyQt5.QtWidgets import QLabel, QScrollArea

from src.core.import_manager import FileType, ImportConfiguration, ImportFile, ImportType
from src.ui.fenetre_import import ImportDialog
from src.utils.rapprochement_fiche.associee import origine_associable

from tests.unit.test_fiche_import_ecran import _fenetre
from tests.unit.test_reprise_site import Construite

LOT = ('264440194', 'C00871425', '264440188')


@pytest.fixture
def rendus(tmp_path):
    d = Path(os.environ.get('AUTOFILL_RENDUS') or tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dialogue(qapp, tmp_path, refs=LOT):
    b = Construite(tmp_path)
    fenetre = _fenetre(qapp, b.db)
    fichiers = [ImportFile(path=str(tmp_path / f'{ref}.pdf'), type=FileType.CSV,
                           suggested_reference=ref, data=[['WAE24/01', 'Maxx']])
                for ref in refs]
    config = ImportConfiguration(files=fichiers, import_type=ImportType.MULTI_FILE)
    dialogue = ImportDialog(None, config, import_manager=fenetre.import_manager)
    dialogue._load_data_deferred()
    dialogue.auto_file_references_checkbox.setChecked(True)   # réf. = nom du fichier
    return dialogue


def _zone_cartes(dialogue) -> QScrollArea:
    contenu = dialogue.individual_refs_widget.parentWidget()
    return next(z for z in dialogue.findChildren(QScrollArea) if z.widget() is contenu)


def test_beko_de_9_chiffres_en_16_et_26():
    assert origine_associable('264440194') == 'Beko'
    assert origine_associable('162480007') == 'Beko'
    # Les autres 9 chiffres ne changent pas
    assert origine_associable('611234567') != 'Beko'          # Liebherr
    assert origine_associable('691234567') != 'Beko'          # Smeg


def test_champ_associee_sur_les_trois_cartes(qapp, tmp_path):
    dialogue = _dialogue(qapp, tmp_path)
    champs = {f.suggested_reference: c for f, c in dialogue._champs_associes}
    assert all(not champs[ref].isHidden() for ref in LOT)
    dialogue.close()


@pytest.mark.parametrize('largeur', [1290, 1100])
def test_cartes_non_coupees(qapp, tmp_path, rendus, largeur):
    dialogue = _dialogue(qapp, tmp_path)
    dialogue.resize(largeur, 930)
    dialogue.show()
    qapp.processEvents()
    dialogue.grab().save(str(rendus / f'import_cartes_{largeur}.png'))
    zone = _zone_cartes(dialogue)
    assert zone.widget().width() <= zone.viewport().width(), \
        (zone.widget().width(), zone.viewport().width())
    # La case « Obsolète » de chaque carte est entièrement visible
    for case, _ in dialogue._obsolete_checkboxes:
        droite = case.mapTo(zone.viewport(), QPoint(case.width(), 0)).x()
        assert droite <= zone.viewport().width(), (droite, zone.viewport().width())
    dialogue.close()


def test_nom_de_fichier_pas_repete(qapp, tmp_path):
    dialogue = _dialogue(qapp, tmp_path, refs=('264440194', 'C00871425'))
    fichier = dialogue.import_config.files[0]
    etiquette = dialogue.findChild(QLabel, f"nom_fichier_{fichier.path}")
    assert etiquette is not None and etiquette.isHidden()
    ref = dialogue.findChild(QLabel, f"ref_display_{fichier.path}")
    assert fichier.filename in ref.toolTip()
    dialogue.close()


def test_nom_de_fichier_affiche_si_la_reference_differe(qapp, tmp_path):
    dialogue = _dialogue(qapp, tmp_path, refs=('264440194', 'C00871425'))
    fichier = dialogue.import_config.files[0]
    dialogue.auto_file_references_checkbox.setChecked(False)  # plus de réf. par fichier
    etiquette = dialogue.findChild(QLabel, f"nom_fichier_{fichier.path}")
    assert not etiquette.isHidden()
    dialogue.close()


def test_depot_d_une_reference_sur_le_champ(qapp, tmp_path):
    dialogue = _dialogue(qapp, tmp_path)
    champs = {f.suggested_reference: c for f, c in dialogue._champs_associes}
    cible = champs['264440194'].champ
    assert cible.acceptDrops()
    donnees = QMimeData()
    donnees.setText('C00871425')
    evenement = QDropEvent(QPoint(5, 5), Qt.CopyAction, donnees, Qt.LeftButton, Qt.NoModifier)
    cible.dropEvent(evenement)
    assert cible.refs() == ['C00871425']
    dialogue._validate_and_accept()
    assert dialogue.get_configuration().references_associees['264440194'] == 'C00871425'
    dialogue.close()
