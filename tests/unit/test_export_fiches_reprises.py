"""
Export EveryParts des fiches reprises du site (CDC import fiches site, § 10.19)

- les 3 fiches d'exemple reprises sur l'extrait de la vraie base, puis exportées :
  1ʳᵉ colonne = référence produit du site, appareils de la pièce ET de sa lignée
  (20744 : ses 450 appareils sont ceux de ses 4 anciennes références) ;
- un fichier par produit, ou un seul fichier ; la date d'export est retenue et
  « à exporter » ne propose plus que les produits jamais exportés ou relus depuis ;
- la fenêtre, rendue hors écran, exporte la sélection dans un thread.
Aucun accès réseau, aucun réglage du poste écrit.
"""

import csv
import os
from pathlib import Path

from src.services.export_config_service import DEFAULT_CONFIG
from src.services.export_fiches_reprises_service import ExportFichesReprisesService

from tests.unit.test_reprise_site import _db_extrait, _exports_exemples, _service


def _base_reprise(tmp_path):
    db = _db_extrait(tmp_path)
    p, c = _exports_exemples(tmp_path)
    s = _service(db)
    s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
    lot = s.analyser_lot_suivant(100)
    assert s.enregistrer_lot(lot, s.planifier_lot(lot)).ok
    s.fermer()
    return db


def _lire(chemin):
    with open(chemin, encoding=DEFAULT_CONFIG['csv']['encoding'], newline='') as f:
        return list(csv.reader(f, delimiter=DEFAULT_CONFIG['csv']['separator']))


def test_un_fichier_par_produit_avec_la_lignee(tmp_path):
    db = _base_reprise(tmp_path)
    service = ExportFichesReprisesService(db)
    produits = {p['id_product']: p for p in service.produits()}
    assert set(produits) == {7285, 20744, 20746}
    p20744 = produits[20744]
    # La pièce n'a aucun lien à elle : tout vient de ses anciennes références
    assert len(service.references(p20744['ref_piece'])) == 5
    assert len(service.lignes(p20744['ref_piece'])) == 450
    dossier = tmp_path / 'everyparts'
    res = service.exporter(list(produits.values()), str(dossier))
    assert res.produits == 3 and len(res.fichiers) == 3 and not res.sans_appareil
    lignes = _lire(dossier / f"{p20744['ref_interne']}_everyParts.csv")
    assert lignes[0] == [c['header'] for c in DEFAULT_CONFIG['csv']['columns']]
    assert len(lignes) == 451 and {l[0] for l in lignes[1:]} == {p20744['ref_interne']}
    assert len(_lire(dossier / f"{produits[20746]['ref_interne']}_everyParts.csv")) == 832
    # Date d'export retenue : plus rien « à exporter »
    assert service.produits(non_exportes=True) == []
    assert all(p['exporte_le'] for p in service.produits())


def test_un_seul_fichier(tmp_path):
    db = _base_reprise(tmp_path)
    service = ExportFichesReprisesService(db)
    produits = service.produits()
    res = service.exporter(produits, str(tmp_path / 'e'), un_seul_fichier=True)
    assert len(res.fichiers) == 1
    lignes = _lire(res.fichiers[0])
    assert len(lignes) - 1 == res.lignes
    assert {l[0] for l in lignes[1:]} == {p['ref_interne'] for p in produits}


def test_fenetre_export(qapp, qtbot, tmp_path):
    from src.ui.export_fiches_reprises_dialog import ExportFichesReprisesDialog
    db = _base_reprise(tmp_path)
    d = ExportFichesReprisesDialog(db)
    assert d.table.rowCount() == 3 and d.bouton_exporter.text() == "Exporter (3)"
    d._dossier_choisi(str(tmp_path / 'sortie'))
    d.table.selectRow(0)
    assert d.bouton_exporter.text() == "Exporter (1)"
    d.resize(980, 560)
    rendus = Path(os.environ.get('AUTOFILL_RENDUS') or tmp_path)
    rendus.mkdir(parents=True, exist_ok=True)
    d.grab().save(str(rendus / 'export_fiches_reprises.png'))
    d.exporter()
    qtbot.waitUntil(lambda: d._export is None, timeout=30000)
    assert len(os.listdir(tmp_path / 'sortie')) == 1
    assert "1 produit(s)" in d.etat.text()
    assert d.table.rowCount() == 2                   # « à exporter » : l'exporté sort de la liste
    d.close()
