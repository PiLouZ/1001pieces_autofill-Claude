"""
Tests — recollage des lignes éclatées par une cellule haute (extracteur PDF)

Certains PDF (ex. 805101, imprimé via « Microsoft: Print To PDF ») ont des cellules
trop étroites : le texte passe sur 2 lignes et le contenu des autres colonnes est
centré verticalement. Camelot rend alors 3 lignes pour un seul appareil :

    [∅,  ∅, D1]          [R1-, ∅, ∅]
    [R,  C, ∅ ]   ou     [∅,   C, D]
    [∅,  ∅, D2]          [R2,  ∅, ∅]

Sans recollage, `DBI545IKXXLS-` et `01` partaient à l'import comme deux appareils.

Le recollage n'agit que sur ces motifs complets. Les PDF bien formés ne contiennent
que des lignes complètes ou sans description (légitimes : 258 dans 52X5020) : ils
doivent ressortir strictement inchangés — c'est l'objet du filet en fin de fichier.
"""

from pathlib import Path

import pytest

from src.data.pdf_extractor_camelot import CamelotPDFExtractor

DOSSIER_PDF = Path(__file__).resolve().parents[1] / 'fixtures' / 'pdf_samples'


@pytest.fixture
def extracteur():
    return CamelotPDFExtractor()


# ── Motifs reconnus ──────────────────────────────────────────────────────────

def test_description_scindee_recollee(extracteur):
    lignes = [
        ['', '', '16/02/2018 728572 VERS01 LV 86CM 14COUV A+++ 42DB 9SPRAY'],
        ['DFI644GXXL-01', 'DFI644GXXL', ''],
        ['', '', 'STY'],
    ]
    assert extracteur._recoller_fragments(lignes) == [
        ['DFI644GXXL-01', 'DFI644GXXL', '16/02/2018 728572 VERS01 LV 86CM 14COUV A+++ 42DB 9SPRAY STY'],
    ]
    assert extracteur._fragments_recolles_page == 1


def test_reference_technique_coupee_recollee_sans_espace(extracteur):
    lignes = [
        ['DBI545IKXXLS-', '', ''],
        ['', 'DBI545IKXXL.S', '08/07/2022 739489 VERS01 LV ench 86cm Classic blanc'],
        ['01', '', ''],
    ]
    assert extracteur._recoller_fragments(lignes) == [
        ['DBI545IKXXLS-01', 'DBI545IKXXL.S', '08/07/2022 739489 VERS01 LV ench 86cm Classic blanc'],
    ]


def test_en_tete_fragmente_retire(extracteur):
    lignes = [['', 'Réf.', ''], ['', 'commerciale', ''], ['A-01', 'A', 'desc']]
    assert extracteur._recoller_fragments(lignes) == [['A-01', 'A', 'desc']]


def test_motifs_enchaines_et_lignes_saines_conservees(extracteur):
    lignes = [
        ['A-01', 'A', 'desc a'],
        ['', '', 'debut'], ['B-01', 'B', ''], ['', '', 'fin'],
        ['C-', '', ''], ['', 'C', 'desc c'], ['02', '', ''],
        ['D-01', 'D', 'desc d'],
    ]
    assert extracteur._recoller_fragments(lignes) == [
        ['A-01', 'A', 'desc a'],
        ['B-01', 'B', 'debut fin'],
        ['C-02', 'C', 'desc c'],
        ['D-01', 'D', 'desc d'],
    ]
    assert extracteur._fragments_recolles_page == 2


# ── Ce qui ne doit PAS être recollé ──────────────────────────────────────────

def test_lignes_sans_description_consecutives_inchangees(extracteur):
    """Cas réel de 52X5020 : appareils légitimes sans description."""
    lignes = [
        ['3TL961A/05', '3TL961A', ''],
        ['4TL750A/04', '4TL750A', ''],
        ['4TL750B/01', '4TL750B', ''],
    ]
    assert extracteur._recoller_fragments(lignes) == lignes
    assert extracteur._fragments_recolles_page == 0


def test_reference_finissant_par_tiret_mais_complete_inchangee(extracteur):
    """Cas réel de 52X5020 : `FET-3106D-X/02-` est une vraie référence."""
    lignes = [
        ['FET-3106D-X/02-', 'FET-3106D', ''],
        ['', 'X', 'desc'],
        ['01', '', ''],
    ]
    assert extracteur._recoller_fragments(lignes) == lignes


@pytest.mark.parametrize('lignes', [
    # motif incomplet en fin de page : on ne devine pas
    [['', '', 'debut'], ['B-01', 'B', '']],
    [['C-', '', ''], ['', 'C', 'desc c']],
    # le bas n'a pas la bonne forme
    [['', '', 'debut'], ['B-01', 'B', ''], ['X', '', 'fin']],
    # le haut de la réf. coupée ne finit pas par un tiret
    [['C', '', ''], ['', 'C', 'desc c'], ['02', '', '']],
])
def test_motif_incomplet_ou_ambigu_laisse_tel_quel(extracteur, lignes):
    assert extracteur._recoller_fragments(lignes) == lignes


def test_mot_en_tete_dans_une_vraie_ligne_conserve(extracteur):
    lignes = [['A-01', 'A', 'Description longue']]
    assert extracteur._recoller_fragments(lignes) == lignes


# ── Fichier réel 805101 ──────────────────────────────────────────────────────

def test_pdf_805101_appareils_complets(extracteur):
    lignes = extracteur.extract_data(str(DOSSIER_PDF / '805101.pdf'))

    # 357 appareils présents dans le fichier (370 attendus : 13 perdus à
    # l'impression, sur les pages blanches 3, 6, 8 et 14 — absents du PDF)
    assert len(lignes) == 357
    assert all(all(cellule for cellule in ligne) for ligne in lignes)
    assert not [l for l in lignes if l[0].endswith('-')]
    assert len({l[0] for l in lignes}) == 357
    assert extracteur.last_extraction_info['fragments_recolles'] == 25
    assert ['DBI545IKXXLS-01', 'DBI545IKXXL.S',
            '08/07/2022 739489 VERS01 LV ench 86cm Classic blanc'] in lignes


# ── Filet : les PDF bien formés ressortent inchangés ─────────────────────────

# Nombre de lignes relevé AVANT l'introduction du recollage (sortie comparée
# ligne à ligne : identique sur ces 8 fichiers, extraction complète et aperçu)
LIGNES_AVANT_RECOLLAGE = {
    '00213989.pdf': 291,
    '00680351.pdf': 298,
    '00687173.pdf': 71,
    '00687229.pdf': 7,
    '52X4627.pdf': 1,
    '52X5020.pdf': 709,
    '55X2983.pdf': 1806,
    'AS6015830.pdf': 718,
}


@pytest.mark.parametrize('nom, attendu', sorted(LIGNES_AVANT_RECOLLAGE.items()))
def test_pdf_bien_forme_inchange(extracteur, nom, attendu):
    lignes = extracteur.extract_data(str(DOSSIER_PDF / nom))
    assert len(lignes) == attendu
    assert extracteur.last_extraction_info['fragments_recolles'] == 0


# ── Pages vides : fourchettes de références manquantes ───────────────────────
#
# 805101 a été imprimé via « Microsoft: Print To PDF » : le contenu qui débordait
# des pages 2, 5, 7 et 13 est perdu et les pages 3, 6, 8 et 14 sortent blanches
# (13 appareils absents du fichier, 357 lus sur 370). Irrécupérable, mais la
# dernière référence lue avant le trou et la première après bornent la recherche
# manuelle — signalé dans l'historique des opérations.

FOURCHETTES_805101 = [
    {'pages': [3], 'avant': 'DFI544BXXL-04', 'apres': 'DFI544D-02'},
    {'pages': [6], 'avant': 'DFI646G-01', 'apres': 'DFI655G-03'},
    {'pages': [8], 'avant': 'DFI746U 04', 'apres': 'DFI746U-08'},
    {'pages': [14], 'avant': 'DWCBI331.W-04', 'apres': 'DWCBI331S-03'},
]


def test_detection_trou_simple_et_multiple():
    bornes = {1: ('A1', 'A9'), 2: ('B1', 'B9'), 4: ('D1', 'D9'), 7: ('G1', 'G9')}
    assert CamelotPDFExtractor._detecter_pages_vides(bornes) == [
        {'pages': [3], 'avant': 'B9', 'apres': 'D1'},
        {'pages': [5, 6], 'avant': 'D9', 'apres': 'G1'},
    ]


def test_pages_vides_en_debut_et_fin_ignorees():
    """Page de garde, saut final : aucune suite de données interrompue."""
    assert CamelotPDFExtractor._detecter_pages_vides({3: ('C1', 'C9'), 4: ('D1', 'D9')}) == []
    assert CamelotPDFExtractor._detecter_pages_vides({}) == []


def test_pdf_805101_fourchettes(extracteur):
    extracteur.extract_data(str(DOSSIER_PDF / '805101.pdf'))
    assert extracteur.last_extraction_info['pages_vides'] == FOURCHETTES_805101


def test_apercu_ne_signale_rien(extracteur):
    extracteur.extract_data(str(DOSSIER_PDF / '805101.pdf'), preview_mode=True)
    assert extracteur.last_extraction_info['pages_vides'] == []


@pytest.mark.parametrize('nom', sorted(LIGNES_AVANT_RECOLLAGE))
def test_pdf_bien_forme_sans_page_vide(extracteur, nom):
    extracteur.extract_data(str(DOSSIER_PDF / nom))
    assert extracteur.last_extraction_info['pages_vides'] == []


def test_message_alerte():
    from src.core.import_manager import ImportManager
    assert ImportManager._alerte_pages_vides('805101.pdf', FOURCHETTES_805101[:1] + [
        {'pages': [8, 9], 'avant': 'X', 'apres': 'Y'}]) == [
        '805101.pdf : 3 pages vides — appareils peut-être manquants entre :',
        'p.3 : DFI544BXXL-04 → DFI544D-02',
        'p.8-9 : X → Y',
    ]
    assert ImportManager._alerte_pages_vides('a.pdf', FOURCHETTES_805101[:1])[0] == \
        'a.pdf : 1 page vide — appareils peut-être manquants entre :'


def _importer_puis_recap(qapp, nom_pdf):
    """Import réel (base jetable) puis récap tel qu'écrit dans l'historique."""
    import os
    import tempfile
    from unittest.mock import Mock
    from src.core.config import Config
    from src.data.database_manager import DatabaseManager
    from src.core.import_manager import (ImportManager, ImportConfiguration, ImportFile,
                                         ImportType, LabelConfiguration, FileType)
    from src.ui.main_refactored import MainWindow

    chemin = str(DOSSIER_PDF / nom_pdf)
    chemin_db = tempfile.mktemp(suffix='.db')
    db_origine = Config.DB_FILE
    Config.DB_FILE = chemin_db
    try:
        db = DatabaseManager()
        manager = ImportManager(db_manager=db, parent_widget=None)
        fichier = ImportFile(path=chemin, type=FileType.PDF, suggested_reference='REF_TEST')
        config = ImportConfiguration(
            files=[fichier], import_type=ImportType.SINGLE_FILE, common_reference='',
            use_common_reference=False, label_config=LabelConfiguration(),
            individual_references={chemin: 'REF_TEST'}, individual_labels={},
            csv_import_mode=2, has_headers=False)
        resultats = manager._run_import_files(config)
        db.close()
    finally:
        Config.DB_FILE = db_origine
        if os.path.exists(chemin_db):
            os.remove(chemin_db)

    fenetre = Mock()
    MainWindow._safe_show_import_results_new(fenetre, resultats)
    return resultats, fenetre.user_interaction_service.add_to_history.call_args[0][0]


def test_recap_historique_signale_les_fourchettes(qapp):
    resultats, recap = _importer_puis_recap(qapp, '805101.pdf')
    assert resultats['new_entries'] == 357
    assert ("     [!] 805101.pdf : 4 pages vides — appareils peut-être manquants entre :\n"
            "     ==> p.3 : DFI544BXXL-04 → DFI544D-02\n"
            "     ==> p.6 : DFI646G-01 → DFI655G-03\n"
            "     ==> p.8 : DFI746U 04 → DFI746U-08\n"
            "     ==> p.14 : DWCBI331.W-04 → DWCBI331S-03\n"
            "     ==> Conseil : régénérez le PDF avec le tri inversé et importez-le "
            "en complément — ses coupures tombent ailleurs\n") in recap
    assert recap.count('Conseil') == 1


def test_recap_historique_pdf_sain_inchange(qapp):
    resultats, recap = _importer_puis_recap(qapp, '00687229.pdf')
    assert 'alerte_pages_vides' not in resultats
    assert '[!]' not in recap
    assert 'Conseil' not in recap
