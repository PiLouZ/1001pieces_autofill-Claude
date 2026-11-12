"""
Reprise en masse des fiches du site par lots (CDC import fiches site, étape 4)

- lecture conjointe des deux exports CSV (jointure par fusion, tri contrôlé,
  reprise après un id, fiches mises de côté), découpage en lots ;
- état de la reprise : avance à la fin du lot seulement, export différent
  détecté (repartir de zéro / continuer) ;
- lots sur une base construite et sur l'extrait de la vraie base : résumé par
  catégorie, doutes regroupés, appareils absents partagés entre fiches,
  relance d'un lot sans doublon, reprise après une interruption ;
- planificateur : choix repris d'une autre ligne de la fiche, provenance des
  lignes déjà couvertes ;
- fenêtre de reprise rendue hors écran.
Aucun accès réseau.
"""

import copy
import csv
import os
import sqlite3
from pathlib import Path

import pytest

from src.data.database_manager import DatabaseManager
from src.services.export_config_service import DEFAULT_CONFIG
from src.services.reprise_site_service import (
    EXPORT_DIFFERENT, EXPORT_IDENTIQUE, EXPORT_NOUVEAU, RepriseSiteService,
)
from src.utils.lecteur_fiche import lire_page_publique, modeles_depuis_config
from src.utils.lecteur_fiche.page_publique import extraire_description
from src.utils.rapprochement_fiche import ConfigurationRapprochement
from src.utils.rapprochement_fiche.decisions import DE_COTE, VALIDEE
from src.utils.reprise_site import (
    PROFILS_AMBIGUS, ExportInvalide, ExportNonTrie, lire_exports, prochain_lot,
)
from src.utils.reprise_site.exports import ligne_compatibilite
from src.utils.reprise_site.lot import forme_ref_interne

RACINE = Path(__file__).resolve().parents[2]
FIXTURES = RACINE / 'tests' / 'fixtures' / 'fiches_site'
CONFIG = ConfigurationRapprochement()
MODELES = modeles_depuis_config(copy.deepcopy(DEFAULT_CONFIG))
ENTETE_P = ['id_produit', 'reference', 'nom_produit', 'marque', 'ean', 'categorie', 'actif',
            'description']
ENTETE_C = ['id_produit', 'reference_appareil', 'modele_appareil', 'marque_appareil',
            'type_appareil']


# =============================================================================
# Outils
# =============================================================================

def _ecrire_csv(chemin, entete, lignes):
    with open(chemin, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
        w.writerow(entete)
        w.writerows(lignes)
    return str(chemin)


def _description(code, marque, lignes, remplace=()):
    html = f'<h2 class="class_perso1">Pièce {code}</h2>'
    html += f'<div class="class_perso3">Code produit : {code}</div>'
    if remplace:
        html += f'<div class="class_perso3 class_perso6">Remplace les références : {" ".join(remplace)}</div>'
    html += '<div class="class_perso4">Appareils compatibles :</div><div class="class_perso5">'
    html += f'<div id="{marque}"><b><u>{marque}</u></b></div>'
    html += ''.join(f'<div>{ref} - {nom}</div>' for ref, nom in lignes)
    return html + '</div>'


def _service(db, regles=None):
    s = RepriseSiteService(db, configuration=CONFIG, chemin_configuration=regles)
    s._modeles = MODELES
    return s


def _instantane(db):
    q = lambda t: db.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    return {t: q(t) for t in ('appareils', 'pieces', 'piece_associations', 'piece_supersessions',
                              'piece_equivalence_groups', 'produits_site')}


def _decider(lot):
    lot.tout_valider()
    for g in lot.groupes_doutes():
        lot.choisir_groupe(g, g.choix[0])
    lot.lignes_a_completer_de_cote()
    plan = lot.planifier()
    assert plan.pret, (plan.en_attente, plan.fiches_a_completer)
    return plan


class Construite:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.db = DatabaseManager(str(tmp_path / 'construite.db'))

    def appareil(self, marque, ref, type_='Lave-linge'):
        cur = self.db.conn.execute(
            "INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) VALUES (?, ?, ?, '')",
            [type_, marque, ref])
        self.db.conn.commit()
        return cur.lastrowid

    def exports(self, produits, compat=(), nom='p'):
        p = _ecrire_csv(self.tmp / f'{nom}_produits.csv', ENTETE_P, produits)
        c = _ecrire_csv(self.tmp / f'{nom}_compat.csv', ENTETE_C, compat)
        return p, c


def _produit(ident, code, marque, lignes, ref_interne=None, remplace=()):
    return [ident, ref_interne or code, f"Pièce {code}", marque, '', 'Pompe - Lave-linge', '1',
            _description(code, marque, lignes, remplace)]


# =============================================================================
# Lecture des exports
# =============================================================================

class TestExports:

    def test_jointure_par_fusion(self, tmp_path):
        p = _ecrire_csv(tmp_path / 'p.csv', ENTETE_P, [
            [10, 'A', 'a', 'M', '', '', '1', 'desc A'],
            [12, 'B', 'b', 'M', '', '', '1', ''],          # sans contenu
            [15, 'C', 'c', 'M', '', '', '0', ''],          # compatibilités seules
            [20, 'D', 'd', 'M', '', '', '1', 'desc D']])
        c = _ecrire_csv(tmp_path / 'c.csv', ENTETE_C, [
            [5, 'X1', 'X1 - x', 'Bosch', 'Four'],          # produit absent de l'export : passé
            [10, 'R1/01', 'R1/01 - NOM 1', 'Bosch', 'Lave-linge'],
            [10, 'R2', 'R2', 'Bosch', 'Lave-linge'],       # sans « - » : pas de nom
            [15, 'R3', 'R3 - N3', 'Siemens', 'Four'],
            [17, 'R4', 'R4 - N4', 'Siemens', 'Four']])     # produit absent : passé
        produits = list(lire_exports(p, c))
        assert [x.id_produit for x in produits] == [10, 12, 15, 20]
        assert [(l.ref_modele, l.nom) for l in produits[0].compatibilites] == [('R1/01', 'NOM 1'), ('R2', '')]
        assert not produits[1].a_contenu and produits[2].a_contenu and not produits[2].actif
        assert produits[3].compatibilites == []
        assert [x.id_produit for x in lire_exports(p, c, apres_id=12)] == [15, 20]
        assert [x.id_produit for x in lire_exports(p, c, seulement={20, 10})] == [10, 20]
        assert [x.id_produit for x in lire_exports(p)] == [10, 12, 15, 20]

    def test_lots_et_dernier_id(self, tmp_path):
        p = _ecrire_csv(tmp_path / 'p.csv', ENTETE_P,
                        [[i, '', '', '', '', '', '1', 'd' if i % 3 else ''] for i in range(1, 11)])
        lecteur = lire_exports(p)
        lot1 = prochain_lot(lecteur, 3)
        assert [x.id_produit for x in lot1.produits] == [1, 2, 4]
        assert (lot1.premier_id, lot1.dernier_id, lot1.sans_contenu) == (1, 4, 1)
        lot2 = prochain_lot(lecteur, 3)
        assert [x.id_produit for x in lot2.produits] == [5, 7, 8]
        lot3 = prochain_lot(lecteur, 3)
        assert [x.id_produit for x in lot3.produits] == [10] and lot3.fin_export
        assert lot3.dernier_id == 10 and prochain_lot(lecteur, 3) is None

    def test_tri_et_colonnes_controles(self, tmp_path):
        p = _ecrire_csv(tmp_path / 'p.csv', ENTETE_P, [[2, '', '', '', '', '', '1', 'd'],
                                                     [1, '', '', '', '', '', '1', 'd']])
        with pytest.raises(ExportNonTrie):
            list(lire_exports(p))
        p = _ecrire_csv(tmp_path / 'p2.csv', ENTETE_P, [[1, '', '', '', '', '', '1', 'd'],
                                                      [2, '', '', '', '', '', '1', 'd']])
        c = _ecrire_csv(tmp_path / 'c.csv', ENTETE_C, [[2, 'A', 'A', 'M', 'T'], [1, 'B', 'B', 'M', 'T']])
        with pytest.raises(ExportNonTrie):
            list(lire_exports(p, c))
        mauvais = _ecrire_csv(tmp_path / 'm.csv', ['id', 'reference'], [[1, 'x']])
        with pytest.raises(ExportInvalide):
            list(lire_exports(mauvais))

    def test_ligne_compatibilite(self):
        l = ligne_compatibilite({'reference_appareil': 'SL204/FR', 'modele_appareil': 'SL204/FR - SL204',
                                 'marque_appareil': 'Brandt', 'type_appareil': 'Sèche-linge'})
        assert (l.type_appareil, l.marque, l.ref_modele, l.nom) == ('Sèche-linge', 'Brandt', 'SL204/FR', 'SL204')

    def test_forme_ref_interne(self):
        assert forme_ref_interne('ES10028') == 'ES99999'
        assert forme_ref_interne('el1113161010') == 'EL9999999999'


# =============================================================================
# Lots sur une base construite
# =============================================================================

class TestLotsConstruits:

    def _base(self, tmp_path):
        b = Construite(tmp_path)
        b.appareil('Bosch', 'WAE24/01')
        produits = [
            _produit(101, '481010595117', 'Bosch', [('WAE24/01', 'Maxx'), ('ZZNEUF01/02', 'Neuf')]),
            _produit(102, '481010595118', 'Bosch', [('ZZNEUF 01/02', 'Neuf bis'), ('WAE24/01', 'Maxx')]),
            _produit(103, '481010595119', 'Bosch', [('WAE24/01', 'Maxx')], ref_interne='ES10028'),
            _produit(104, '481010595120', 'Bosch', [('WAE24/01', 'Maxx')], ref_interne='ES10029',
                     remplace=['481010590001']),
        ]
        compat = [[101, 'ZZNEUF01/02', 'ZZNEUF01/02 - Neuf', 'Bosch', 'Lave-linge'],
                  [102, 'ZZNEUF01/02', 'ZZNEUF01/02 - Neuf', 'Bosch', 'Lave-linge']]
        return b, b.exports(produits, compat)

    def test_lot_resume_groupes_et_creation_partagee(self, tmp_path):
        b, (p, c) = self._base(tmp_path)
        s = _service(b.db)
        signature, statut = s.examiner_export(p, c)
        assert statut == EXPORT_NOUVEAU
        s.adopter_export(signature, repartir_de_zero=True)
        lot = s.analyser_lot_suivant(10)
        assert [f.id_produit for f in lot.fiches] == [101, 102, 103, 104]
        resume = {l.cle: l for l in lot.resume()}
        assert resume['exacts'].fiches == 4
        assert 'absents' in resume
        # Réf. internes ES… : un groupe de doutes, traitable en bloc
        groupes = {g.cle: g for g in lot.groupes_doutes()}
        g = groupes[('ref_interne_differente', 'ES99999')]
        assert g.fiches == 2 and g.choix == ('enregistrer', 'ignorer')
        # Tant qu'une catégorie est en attente, rien ne s'écrit
        assert not lot.planifier().pret
        lot.tout_valider()
        lot.choisir_groupe(g, 'ignorer')
        plan = lot.planifier()
        assert plan.pret
        # ZZNEUF01/02 et « ZZNEUF 01/02 » (2 fiches) : UN appareil à créer
        assert len(plan.creations) == 1
        avant = _instantane(b.db)
        res = s.enregistrer_lot(lot, plan)
        assert res.ok, res.erreur
        apres = _instantane(b.db)
        assert apres['appareils'] - avant['appareils'] == 1
        assert apres['produits_site'] == 2          # les 2 ES… ignorés
        assert s.dernier_id() == 104
        assert b.db.lots_reprise_site()[0]['fiches'] == 4
        neuf = b.db.conn.execute("SELECT id FROM appareils WHERE ref_modele = 'ZZNEUF01/02'").fetchone()[0]
        liens = b.db.conn.execute("SELECT COUNT(*), GROUP_CONCAT(provenance) FROM piece_associations "
                                  "WHERE appareil_id = ?", [neuf]).fetchone()
        assert liens[0] == 2 and set(liens[1].split(',')) == {'les_deux'}
        assert s.analyser_lot_suivant(10) is None      # export épuisé

    def test_relance_sans_doublon_et_reprise_apres_interruption(self, tmp_path):
        b, (p, c) = self._base(tmp_path)
        s = _service(b.db)
        s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
        # Interruption au milieu de l'écriture (après la 1re fiche)
        lot = s.analyser_lot_suivant(10)
        plan = _decider(lot)
        appels = []
        res = s.enregistrer_lot(lot, plan, annule=lambda: (appels.append(1), len(appels) > 1)[1])
        assert res.annule and s.dernier_id() == 0 and b.db.lots_reprise_site() == []
        # Reprise : le même lot revient, il s'écrit sans doublon
        lot = s.analyser_lot_suivant(10)
        assert [f.id_produit for f in lot.fiches] == [101, 102, 103, 104]
        res = s.enregistrer_lot(lot, _decider(lot))
        assert res.ok and s.dernier_id() == 104
        complet = _instantane(b.db)
        # Relance du lot déjà écrit (état remis au début) : rien n'est ajouté
        b.db.conn.execute("UPDATE reprise_site_etat SET dernier_id = 0")
        b.db.conn.commit()
        lot = s.analyser_lot_suivant(10)
        res = s.enregistrer_lot(lot, _decider(lot))
        assert res.ok and res.appareils_crees == 0 and res.liens_crees == 0
        assert res.liens_completes == 0
        assert _instantane(b.db) == complet
        # Même résultat qu'un passage sans interruption, sur une autre base
        (tmp_path / 'b2').mkdir()
        b2 = Construite(tmp_path / 'b2')
        b2.appareil('Bosch', 'WAE24/01')
        s2 = _service(b2.db)
        s2.adopter_export(s2.examiner_export(p, c)[0], repartir_de_zero=True)
        lot = s2.analyser_lot_suivant(10)
        assert s2.enregistrer_lot(lot, _decider(lot)).ok
        assert _instantane(b2.db) == complet

    def test_fermer_et_reprendre_au_lot_suivant(self, tmp_path):
        b, (p, c) = self._base(tmp_path)
        s = _service(b.db)
        s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
        lot = s.analyser_lot_suivant(2)
        assert [f.id_produit for f in lot.fiches] == [101, 102]
        assert s.enregistrer_lot(lot, _decider(lot)).ok
        s.fermer()
        # Nouvelle session (application relancée) : même export, on continue
        s = _service(b.db)
        signature, statut = s.examiner_export(p, c)
        assert statut == EXPORT_IDENTIQUE
        s.adopter_export(signature)
        lot = s.analyser_lot_suivant(2)
        assert [f.id_produit for f in lot.fiches] == [103, 104]

    def test_export_different_repartir_ou_continuer(self, tmp_path):
        b, (p, c) = self._base(tmp_path)
        s = _service(b.db)
        s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
        lot = s.analyser_lot_suivant(2)
        assert s.enregistrer_lot(lot, _decider(lot)).ok
        with open(p, 'a', encoding='utf-8') as f:     # export plus récent : une ligne de plus
            f.write('"105";"X";"x";"Bosch";"";"";"1";"d"\n')
        os.utime(p, (os.path.getmtime(p) + 60,) * 2)
        signature, statut = s.examiner_export(p, c)
        assert statut == EXPORT_DIFFERENT
        s.adopter_export(signature, repartir_de_zero=False)
        assert s.dernier_id() == 102
        s.adopter_export(signature, repartir_de_zero=True)
        assert s.dernier_id() == 0
        assert s.examiner_export(p, c)[1] == EXPORT_IDENTIQUE

    def test_fiches_mises_de_cote_puis_reprises(self, tmp_path):
        b, (p, c) = self._base(tmp_path)
        s = _service(b.db)
        s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
        lot = s.analyser_lot_suivant(10)
        lot.mettre_de_cote(1, "à revoir")
        plan = _decider(lot)
        assert plan.de_cote == [1]
        assert s.enregistrer_lot(lot, plan).ok
        assert [f['id_produit'] for f in b.db.fiches_de_cote_reprise_site()] == [102]
        assert s.dernier_id() == 104
        lot = s.analyser_fiches_de_cote()
        assert [f.id_produit for f in lot.fiches] == [102]
        assert s.enregistrer_lot(lot, _decider(lot)).ok
        assert b.db.fiches_de_cote_reprise_site() == [] and s.dernier_id() == 104

    def test_profils_ambigus_laisses_de_cote(self, tmp_path):
        b, (p, c) = self._base(tmp_path)
        s = _service(b.db)
        s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
        lot = s.analyser_lot_suivant(10)
        lot.fiches[0].profil_ambigu = True
        lot.tout_valider()
        assert lot.etat(PROFILS_AMBIGUS) == VALIDEE
        lot.definir_etat(PROFILS_AMBIGUS, DE_COTE)
        plan = lot.planifier()
        assert 0 in plan.de_cote and plan.pret


# =============================================================================
# Planificateur : règles apportées par le lot
# =============================================================================

class TestPlanificateur:

    def test_candidat_lie_par_une_autre_ligne(self, tmp_path):
        """Ligne « à valider » parmi plusieurs candidats : celui que lie une autre ligne
        de la fiche (la table, sous la bonne marque) est retenu dès le 1er passage."""
        from src.utils.rapprochement_fiche.acces_base import AppareilBase
        from src.utils.rapprochement_fiche.decisions import DecisionsFiche, planifier
        from src.utils.rapprochement_fiche.resultat import AppareilRapproche, Identite, Rapprochement
        cands = [AppareilBase(7, 'Ignis', 'R1', 'Four'), AppareilBase(8, 'Ignis', 'R1B', 'Four')]
        r = Rapprochement(Identite(ref_piece='P', statut='reelle'), appareils=[
            AppareilRapproche(1, 'Whirlpool', 'R1', '', 'description', niveau='a_valider',
                              candidats=cands, lien='', doutes=['a_valider']),
            AppareilRapproche(0, 'Ignis', 'R1', '', 'table', niveau='exact', appareil_id=7,
                              lien='nouveau', candidats=cands[:1]),
            AppareilRapproche(0, 'Ignis', 'R9', '', 'table', niveau='exact', appareil_id=9,
                              lien='deja_couvert'),
            AppareilRapproche(2, 'Ignis', 'R9', '', 'description', niveau='exact', appareil_id=9,
                              lien='nouveau'),
        ])
        d = DecisionsFiche()
        d.valider_tout(r)
        plan = planifier(r, d)
        assert plan.a_completer == []
        assert (7, 'description') in plan.liens and (7, 'table') in plan.liens
        # la ligne couverte (table) porte sa provenance sur le lien posé par l'autre
        assert (9, 'table') in plan.liens and (9, 'description') in plan.liens


# =============================================================================
# Extrait de la vraie base : les 3 fiches d'exemple en un lot
# =============================================================================

def _db_extrait(tmp_path) -> DatabaseManager:
    chemin = tmp_path / 'extrait.db'
    cnx = sqlite3.connect(chemin)
    cnx.executescript((FIXTURES / 'base_extrait.sql').read_text(encoding='utf-8'))
    cnx.close()
    return DatabaseManager(str(chemin))


def _exports_exemples(tmp_path):
    produits, compat = [], []
    for n in (7285, 20744, 20746):
        page = (FIXTURES / f'produit_{n}.html').read_text(encoding='utf-8')
        pp = lire_page_publique(page, url=f'https://www.1001pieces.com/{n}-fiche.html')
        produits.append([n, pp.ref_interne, pp.nom, pp.marque, pp.ean, pp.categorie, '1',
                         extraire_description(page)])
        compat += [[n, l.ref_modele, f"{l.ref_modele} - {l.nom}", l.marque, l.type_appareil]
                   for l in pp.table_site]
    return (_ecrire_csv(tmp_path / 'p.csv', ENTETE_P, produits),
            _ecrire_csv(tmp_path / 'c.csv', ENTETE_C, compat))


def test_lot_des_fiches_exemples_sur_extrait(tmp_path):
    db = _db_extrait(tmp_path)
    p, c = _exports_exemples(tmp_path)
    s = _service(db)
    s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
    lot = s.analyser_lot_suivant(100)
    assert [f.id_produit for f in lot.fiches] == [7285, 20744, 20746]
    par_id = {f.id_produit: f for f in lot.fiches}
    assert par_id[20744].rapprochement.resume()['liens'].get('deja_couvert') == 450
    assert par_id[20746].rapprochement.resume()['liens'].get('deja_lie') == 831
    res = s.enregistrer_lot(lot, _decider(lot))
    assert res.ok, res.erreur
    apres = _instantane(db)
    assert s.dernier_id() == 20746
    # Relance : rien n'est ajouté
    db.conn.execute("UPDATE reprise_site_etat SET dernier_id = 0")
    db.conn.commit()
    lot = s.analyser_lot_suivant(100)
    res = s.enregistrer_lot(lot, _decider(lot))
    assert res.ok and (res.appareils_crees, res.liens_crees, res.liens_completes) == (0, 0, 0)
    assert _instantane(db) == apres
    s.fermer()


# =============================================================================
# Fenêtre (hors écran)
# =============================================================================

def test_fenetre_reprise_rendue_et_fiche_du_lot(qapp, tmp_path):
    """Fenêtre « Importer les fiches du site » par questions (refonte, étape 4)."""
    from src.ui.fiche_site_dialog import FicheSiteDialog
    from src.ui.reprise_site_dialog import RepriseSiteDialog
    from src.utils.rapprochement_fiche.decisions import ChoixAppareil
    b = Construite(tmp_path)
    b.appareil('Bosch', 'WAE24/01')
    p, c = b.exports([
        _produit(101, '481010595117', 'Bosch', [('WAE24/01', 'Maxx'), ('ZZNEUF01/02', 'Neuf')]),
        _produit(102, '481010595118', 'Bosch', [('WAE24/01', 'Maxx')], ref_interne='ES10028')])
    s = _service(b.db, tmp_path / 'regles.json')
    d = RepriseSiteDialog(b.db, service=s)
    d.setWindowTitle(d.windowTitle())
    assert d.windowTitle() == "Importer les fiches du site"
    d.champ_produits.setText(p)
    d.champ_compat.setText(c)
    d._examiner_export()
    assert s.signature is not None
    d.afficher_lot(s.analyser_lot_suivant(10))
    d.show()
    qapp.processEvents()
    q = d.lot.questionnaire
    assert {'Q1', 'R5'} <= set(q.questions) and set(d.panneau.cartes) == set(q.questions)
    assert d.onglets.tabText(0) == f"À décider ({len(q.sans_reponse())})"
    assert d.modele_fiches.rowCount() == 2 and d.modele_detail.rowCount() == 3
    assert not d.bouton_enregistrer.isEnabled() and d.bouton_propositions.isEnabled()
    # Toutes les lignes, filtrées sur une question (« Voir les lignes »)
    d._voir_lignes('Q1')
    assert d.onglets.currentIndex() == 2 and d.filtre_detail.rowCount() == 1
    # Fiche du lot : un choix ligne par ligne revient au lot et sort la ligne de Q1
    d._ouvrir_fiche(0)
    fiche = d._fiche_ouverte
    assert isinstance(fiche, FicheSiteDialog) and fiche.bouton_enregistrer.isEnabled()
    k = next(i for i, a in enumerate(fiche.rapprochement.appareils) if a.ref_modele == 'ZZNEUF01/02')
    fiche.individuels.appareils[k] = ChoixAppareil(ignorer=True)
    fiche._enregistrer()
    assert 0 in q.individuels and 'Q1' not in q.questions
    # Propositions acceptées : plus rien en attente
    d._propositions_acceptees()
    assert not q.sans_reponse() and d.bouton_enregistrer.isEnabled(), d.etat.text()
    assert d.grab().width() > 0
    assert not (RACINE / 'data' / 'reprise_fiches.json').exists()
    # Réglages : ceux du test, jamais ceux de l'application (chemins temporaires)
    from PyQt5.QtCore import QSettings
    import src.ui.reprise_site_dialog as fenetre
    assert fenetre._reglages().value('reprise_site/export_produits') == p
    assert 'pytest' not in str(QSettings("1001pieces", "autofill").value('reprise_site/export_produits', ''))
    d.close()


def test_chemins_disparus_jamais_proposes(qapp, tmp_path):
    """Un export mémorisé (état de l'import, dernier choix) qui n'existe plus n'est pas
    proposé : la fenêtre passe au suivant (cas d'un chemin temporaire de test)."""
    from src.ui.reprise_site_dialog import RepriseSiteDialog, _reglages
    b = Construite(tmp_path)
    b.db.definir_export_reprise_site(
        {'date_export': '2026-11-12T12:13:31', 'taille_produits': 1, 'taille_compatibilites': 1,
         'chemin_produits': str(tmp_path / 'disparu_p.csv'),
         'chemin_compatibilites': str(tmp_path / 'disparu_c.csv')}, True, '2026-11-12T12:20:42')
    existant = _ecrire_csv(tmp_path / 'p.csv', ENTETE_P, [])
    _reglages().setValue('reprise_site/export_produits', existant)
    _reglages().setValue('reprise_site/export_compatibilites', str(tmp_path / 'disparu2.csv'))
    d = RepriseSiteDialog(b.db, service=_service(b.db, tmp_path / 'regles.json'))
    assert d.champ_produits.text() == existant
    assert 'disparu' not in d.champ_compat.text()
    d.close()
