"""Écarts outil / site dans les deux fenêtres, rendus hors écran (CDC § 10.11, point 2).

« Lire une fiche du site » et « Importer les fiches du site » : même panneau,
mêmes gestes (un clic sur la valeur à garder, ou les deux boutons du groupe).
Les images sont écrites dans AUTOFILL_RENDUS (sinon dans le dossier du test).
Aucun réseau ; ni les réglages du poste ni data/reprise_fiches.json ne sont écrits.
"""

import os
from pathlib import Path

from src.services.enregistrement_fiche_service import EnregistrementFicheService
from src.utils.lecteur_fiche import lire_description
from src.utils.lecteur_fiche.page_publique import LigneTableSite
from src.utils.rapprochement_fiche import AccesBaseLecture, rapprocher
from tests.unit.test_reprise_site import (
    CONFIG, MODELES, RACINE, Construite, _description, _service,
)

CLE_TYPE = 'E:type:Lave-linge→Sèche-linge'


def _dossier(tmp_path) -> Path:
    d = Path(os.environ.get('AUTOFILL_RENDUS') or tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _base(tmp_path):
    b = Construite(tmp_path)
    ids = {
        'xyz': b.appareil('Bosch', 'XYZ123', 'Lave-linge'),
        'wae': b.appareil('Bosch', 'WAE24/01', 'Lave-linge'),
        'wat': b.appareil('Bosch', 'WAT28/02', 'Lave-linge'),
    }
    b.db.conn.execute("UPDATE appareils SET commercial_ref = 'Serie 4' WHERE id = ?", [ids['xyz']])
    b.db.conn.commit()
    return b, ids


_LIGNES = [('XYZ123', 'Serie 6'), ('WAE2401', 'Maxx 6'), ('WAT28/02', 'Logixx')]
_COMPAT = [('XYZ123', 'Sèche-linge'), ('WAT28/02', 'Sèche-linge')]


def _rendre(widget, chemin):
    image = widget.grab()
    assert not image.isNull() and image.width() > 0
    image.save(str(chemin))


def test_fiche_seule_ecarts_cliques_puis_enregistres(qapp, tmp_path):
    from src.ui.fiche_site_dialog import FicheSiteDialog
    b, ids = _base(tmp_path)
    service = EnregistrementFicheService(b.db, configuration=CONFIG)
    lecture = lire_description(_description('481010595117', 'Bosch', _LIGNES), MODELES,
                               ['Bosch'], ['Lave-linge', 'Sèche-linge'])
    r = rapprocher(lecture, AccesBaseLecture(b.db.conn), CONFIG, memoires=True,
                   table_site=[LigneTableSite(t, 'Bosch', ref, '') for ref, t in _COMPAT])
    dlg = FicheSiteDialog(b.db, service=service, chemin_regles=tmp_path / 'regles.json')
    dlg.resize(1400, 950)
    dlg._outils()
    dlg.afficher(r)
    dlg.show()
    qapp.processEvents()
    q = dlg.panneau.questionnaire
    assert set(q.ecarts) == {CLE_TYPE, 'E:ref', 'E:nom'}
    assert len(q.ecarts[CLE_TYPE].cas) == 2
    carte = dlg.panneau.cartes[CLE_TYPE]
    dlg.panneau.ensureWidgetVisible(carte)
    qapp.processEvents()
    dossier = _dossier(tmp_path)
    _rendre(dlg, dossier / 'fiche_seule_1_avant.png')
    # Un clic sur « Sèche-linge » d'un seul cas ; puis « Prendre le site » pour toutes les réf.
    i, k, _ = q.ecarts[CLE_TYPE].cas[0]
    dlg.panneau.cellules[(f"{CLE_TYPE}@{i}:{k}", 'site')].click()
    qapp.processEvents()
    assert dlg.individuels.champs[(k, 'type')] == 'site'
    bouton = next(b_ for b_ in dlg.panneau.cartes['E:ref'].findChildren(type(dlg.bouton_enregistrer))
                  if b_.property('valeur') == 'site')
    bouton.click()
    qapp.processEvents()
    dlg.panneau.ensureWidgetVisible(dlg.panneau.cartes[CLE_TYPE])
    qapp.processEvents()
    _rendre(dlg, dossier / 'fiche_seule_2_apres_clics.png')
    _rendre(dlg.panneau.cartes[CLE_TYPE], dossier / 'fiche_seule_carte_type.png')
    dlg._tout_valider()
    assert dlg.bouton_enregistrer.isEnabled(), dlg.etat.text()
    assert "prise(s) sur le site" in dlg.etat.text()
    dlg._enregistrer()
    ligne = lambda n: b.db.conn.execute(  # noqa: E731
        "SELECT type, ref_modele, commercial_ref FROM appareils WHERE id = ?", [ids[n]]).fetchone()
    cible = q.lot.fiches[0].rapprochement.appareils[k].appareil_id
    autre = 'wat' if cible == ids['xyz'] else 'xyz'
    assert b.db.conn.execute("SELECT type FROM appareils WHERE id = ?", [cible]).fetchone()[0] \
        == 'Sèche-linge'
    assert ligne(autre)[0] == 'Lave-linge'                    # sans clic : outil gardé
    assert ligne('wae')[1] == 'WAE2401'                       # écriture du site prise
    assert ligne('xyz')[2] == 'Serie 4'                       # nom : outil gardé (sans clic)
    assert not (RACINE / 'data' / 'reprise_fiches.json').exists()
    dlg.close()


def test_lot_ecart_en_bloc_et_fiche_du_lot(qapp, tmp_path):
    from src.ui.reprise_site_dialog import RepriseSiteDialog
    b, ids = _base(tmp_path)
    produits = [[101 + n, code, f"Pièce {code}", 'Bosch', '', 'Pompe - Lave-linge', '1',
                 _description(code, 'Bosch', _LIGNES)]
                for n, code in enumerate(('481010595117', '481010595118'))]
    compat = [[101 + n, ref, ref, 'Bosch', t] for n in range(2) for ref, t in _COMPAT]
    p, c = b.exports(produits, compat)
    s = _service(b.db, tmp_path / 'regles.json')
    d = RepriseSiteDialog(b.db, service=s)
    d.resize(1400, 950)
    d.champ_produits.setText(p)
    d.champ_compat.setText(c)
    d._examiner_export()
    d.afficher_lot(s.analyser_lot_suivant(10))
    d.show()
    qapp.processEvents()
    q = d.lot.questionnaire
    g = q.ecarts[CLE_TYPE]
    assert len(g.cas) == 4 and g.fiches == 2                  # 2 appareils × 2 fiches
    d.panneau.ensureWidgetVisible(d.panneau.cartes[CLE_TYPE])
    qapp.processEvents()
    dossier = _dossier(tmp_path)
    _rendre(d, dossier / 'lot_1_avant.png')
    # Fiche du lot : un choix sur un cas revient au lot
    d._ouvrir_fiche(0)
    fiche = d._fiche_ouverte
    i, k, _ = fiche.panneau.questionnaire.ecarts[CLE_TYPE].cas[0]
    fiche.panneau.cellules[(f"{CLE_TYPE}@{i}:{k}", 'site')].click()
    qapp.processEvents()
    fiche.resize(1400, 950)
    fiche.panneau.ensureWidgetVisible(fiche.panneau.cartes[CLE_TYPE])
    qapp.processEvents()
    _rendre(fiche, dossier / 'lot_2_fiche_du_lot.png')
    fiche._enregistrer()
    assert q.individuels[0].champs[(k, 'type')] == 'site'
    assert q.ecarts[CLE_TYPE].decision(0, k) == 'site'
    # Puis « Garder l'outil (4) » pour le groupe : les choix par ligne du lot sont effacés,
    # celui de la fiche (choix individuel de l'aperçu) l'emporte toujours
    d._repondre(CLE_TYPE, 'outil')
    qapp.processEvents()
    g = q.ecarts[CLE_TYPE]
    assert g.reponse == 'outil' and g.decision(0, k) == 'site' and g.decision(1, k) == 'outil'
    d.panneau.ensureWidgetVisible(d.panneau.cartes[CLE_TYPE])
    qapp.processEvents()
    _rendre(d, dossier / 'lot_3_apres_bloc.png')
    _rendre(d.panneau.cartes[CLE_TYPE], dossier / 'lot_carte_type.png')
    d._propositions_acceptees()
    assert d.bouton_enregistrer.isEnabled(), d.etat.text()
    res = s.enregistrer_lot(d.lot, d.lot.planifier())
    assert res.ok, res.erreur
    s.apres_lot(res)
    cible = q.lot.fiches[0].rapprochement.appareils[k].appareil_id
    assert b.db.conn.execute("SELECT type FROM appareils WHERE id = ?", [cible]).fetchone()[0] \
        == 'Sèche-linge'
    autre = ids['wat'] if cible == ids['xyz'] else ids['xyz']
    assert b.db.conn.execute("SELECT type FROM appareils WHERE id = ?", [autre]).fetchone()[0] \
        == 'Lave-linge'
    # « Garder l'outil » mémorisé pour l'appareil gardé tel quel (relecture : plus proposé)
    assert b.db.conn.execute("SELECT valeur_site FROM decisions_champs WHERE appareil_id = ? "
                             "AND champ = 'type'", [autre]).fetchone() == ('Sèche-linge',)
    assert not (RACINE / 'data' / 'reprise_fiches.json').exists()
    d.close()
