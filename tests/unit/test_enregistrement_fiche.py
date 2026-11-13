"""
Aperçu et enregistrement d'une fiche du site (CDC import fiches site, étape 3)

- Schéma du § 9 : tables et colonnes créées par DatabaseManager, migration
  rejouable, colonnes vides pour l'existant, renommage et suppression suivis ;
- mémoires branchées sur rapprocher(memoires=True) ;
- décisions de l'aperçu → plan d'écriture (catégories en bloc, choix individuels,
  lignes à compléter) ;
- enregistrement sur l'extrait de la vraie base : les 3 fiches d'exemple
  enregistrées puis relues sans rien ajouter ; 20744 : la fantôme devient réelle,
  aucun nouveau lien ;
- ajout seul : liens absents de la fiche signalés, rien si la liste est tronquée ;
- aperçu rendu hors écran ;
- sur une COPIE de la vraie base (variable AUTOFILL_BASE_COPIE, API backup) :
  migration mesurée.
Aucun accès réseau.
"""

import copy
import os
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from src.data.database_manager import DatabaseManager
from src.data._db_mixins.fiches_site import fusion_provenance
from src.services.enregistrement_fiche_service import EnregistrementFicheService
from src.services.export_config_service import DEFAULT_CONFIG
from src.utils.lecteur_fiche import (
    LectureFiche, LigneAppareil, LigneEquivalentes, lire_page_publique, modeles_depuis_config,
)
from src.utils.rapprochement_fiche import AccesBaseLecture, ConfigurationRapprochement, rapprocher
from src.utils.rapprochement_fiche.decisions import (
    DE_COTE, VALIDEE, ChoixAppareil, DecisionsFiche, categorie_appareil, elements_par_categorie,
    forme_reference, planifier,
)
from src.utils.rapprochement_fiche.rapprochement import libelle_depuis_titre

RACINE = Path(__file__).resolve().parents[2]
FIXTURES = RACINE / 'tests' / 'fixtures' / 'fiches_site'
CONFIG = ConfigurationRapprochement()
MODELES = modeles_depuis_config(copy.deepcopy(DEFAULT_CONFIG))


# =============================================================================
# Outils
# =============================================================================

def _db_extrait(tmp_path) -> DatabaseManager:
    chemin = tmp_path / 'extrait.db'
    cnx = sqlite3.connect(chemin)
    cnx.executescript((FIXTURES / 'base_extrait.sql').read_text(encoding='utf-8'))
    cnx.close()
    return DatabaseManager(str(chemin))


def _compte(db, table, where='', params=()):
    return db.conn.execute(f"SELECT COUNT(*) FROM {table} {where}", list(params)).fetchone()[0]


def _instantane(db):
    return {t: _compte(db, t) for t in ('appareils', 'pieces', 'piece_associations',
                                        'piece_supersessions', 'piece_equivalence_groups',
                                        'produits_site', 'decisions_ecritures',
                                        'decisions_references')}


def _service(db):
    return EnregistrementFicheService(db, configuration=CONFIG)


def _lire(db, n):
    page = (FIXTURES / f'produit_{n}.html').read_text(encoding='utf-8')
    return _service(db).analyser_page(page, f'https://www.1001pieces.com/{n}-fiche.html')[1]


def _choisir_premier_candidat(r, d):
    """Lignes à compléter : 1er candidat (choix individuel de l'aperçu)."""
    for i, a in enumerate(r.appareils):
        if categorie_appareil(a) == 'a_valider' and a.candidats and \
                a.appareil_id is None and a.proposition is None:
            d.appareils[i] = ChoixAppareil(appareil_id=a.candidats[0].id)


def _tout_valider(r):
    d = DecisionsFiche()
    d.valider_tout(r)
    _choisir_premier_candidat(r, d)
    return d


def _fiche(code=('REFP',), lignes=(), remplace=(), equivalentes=(), titre='') -> LectureFiche:
    appareils = [LigneAppareil(n, l[0], l[1], (l[2] if len(l) > 2 else ''), 'ref_nom', n,
                               source_marque='entete', type_ligne=(l[3] if len(l) > 3 else ''))
                 for n, l in enumerate(lignes, 1)]
    return LectureFiche(titre=titre, code_produit=list(code), remplace=list(remplace),
                        equivalentes=[LigneEquivalentes(i, list(refs), 0, 'texte')
                                      for i, refs in enumerate(equivalentes, 1)],
                        appareils=appareils)


def _rapprocher(db, fiche, **kw):
    return rapprocher(fiche, AccesBaseLecture(db.conn), CONFIG, memoires=True, **kw)


def _enregistrer(db, r, d=None):
    plan = planifier(r, d or _tout_valider(r))
    assert plan.pret, (plan.en_attente, plan.a_completer)
    res = _service(db).enregistrer(plan)
    assert res.ok, res.erreur
    return plan, res


class Construite:
    """Base construite par DatabaseManager (schéma complet de l'application)."""

    def __init__(self, tmp_path):
        self.db = DatabaseManager(str(tmp_path / 'construite.db'))
        self.cnx = self.db.conn

    def appareil(self, marque, ref, type_='Lave-linge', nom=''):
        cur = self.cnx.execute("INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) "
                               "VALUES (?, ?, ?, ?)", [type_, marque, ref, nom])
        self.cnx.commit()
        return cur.lastrowid

    def piece(self, ref, fantome=False, libelle=None):
        self.cnx.execute("INSERT INTO pieces(ref_piece, is_phantom, description) VALUES (?, ?, ?)",
                         [ref, int(fantome), libelle])
        self.cnx.commit()

    def lien(self, ref, appareil_id, provenance=None):
        self.cnx.execute("INSERT INTO piece_associations(piece_id, appareil_id, provenance) "
                         "SELECT id, ?, ? FROM pieces WHERE ref_piece = ?", [appareil_id, provenance, ref])
        self.cnx.commit()


# =============================================================================
# Schéma (§ 9)
# =============================================================================

class TestSchema:
    def test_tables_et_colonnes(self, tmp_path):
        db = _db_extrait(tmp_path)
        tables = {r for (r,) in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'produits_site', 'decisions_ecritures', 'decisions_references'} <= tables
        cols = lambda t: {r[1] for r in db.conn.execute(f"PRAGMA table_info({t})")}
        assert 'provenance' in cols('piece_associations')
        assert {'origine', 'ligne_fiche'} <= cols('piece_equivalence_groups')
        assert {'ref_interne', 'id_product', 'ref_piece', 'ean', 'lu_le'} <= cols('produits_site')

    def test_existant_vide_et_migration_rejouable(self, tmp_path):
        db = _db_extrait(tmp_path)
        avant = _instantane(db)
        assert _compte(db, 'piece_associations', 'WHERE provenance IS NOT NULL') == 0
        assert _compte(db, 'piece_equivalence_groups', 'WHERE origine IS NOT NULL') == 0
        chemin = db.db_path if hasattr(db, 'db_path') else str(tmp_path / 'extrait.db')
        db.conn.close()
        db2 = DatabaseManager(chemin)
        assert _instantane(db2) == avant

    def test_renommage_suivi(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('A1')
        with b.db._query_lock:
            b.db._enregistrer_produit_site('XA1', 12, 'A1', None, 'maintenant')
            b.db._enregistrer_decisions_references([('A1', 'Z9', 'ecartee', None, '99')], 'maintenant')
            b.db.conn.commit()
        assert b.db.rename_piece_catalog('A1', 'A2', '')
        assert b.cnx.execute("SELECT ref_piece FROM produits_site").fetchone() == ('A2',)
        assert b.cnx.execute("SELECT ref_piece FROM decisions_references").fetchone() == ('A2',)
        assert b.db.produits_site_de('A2')[0]['id_product'] == 12

    def test_suppression_suivie(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('A1')
        with b.db._query_lock:
            b.db._enregistrer_produit_site('XA1', 12, 'A1', None, 'maintenant')
            b.db.conn.commit()
        b.db.delete_piece_catalog('A1')
        assert _compte(b.db, 'produits_site') == 0

    def test_fusion_de_groupes_garde_les_origines(self, tmp_path):
        b = Construite(tmp_path)
        b.db.add_equivalence('A', 'B')
        with b.db._query_lock:
            b.db._definir_origines([('B', 'BSH', 2)])
            b.db.conn.commit()
        b.db.add_equivalence('C', 'D')
        b.db.add_equivalence('A', 'C')
        assert b.cnx.execute("SELECT origine, ligne_fiche FROM piece_equivalence_groups "
                             "WHERE ref_piece = 'B'").fetchone() == ('BSH', 2)
        assert len({g for (g,) in b.cnx.execute("SELECT group_id FROM piece_equivalence_groups")}) == 1

    def test_fusion_provenance(self):
        assert fusion_provenance(None, 'description') == 'description'
        assert fusion_provenance('description', 'table') == 'les_deux'
        assert fusion_provenance('les_deux', 'table') == 'les_deux'
        assert fusion_provenance('table', 'table') == 'table'


# =============================================================================
# Les 3 fiches d'exemple sur l'extrait de la vraie base
# =============================================================================

class TestFichesExemple:
    def test_20744_fantome_devient_reelle_sans_nouveau_lien(self, tmp_path):
        db = _db_extrait(tmp_path)
        liens_avant = _compte(db, 'piece_associations')
        r = _lire(db, 20744)
        assert r.identite.statut == 'fantome'
        plan, res = _enregistrer(db, r)
        assert res.piece == 'promue' and res.liens_crees == 0 and res.appareils_crees == 0
        assert _compte(db, 'piece_associations') == liens_avant
        assert db.conn.execute("SELECT is_phantom FROM pieces WHERE ref_piece = '11051894'"
                               ).fetchone() == (0,)
        assert db.produits_site_de('11051894')[0]['ref_interne'] == 'GAU11051894'
        assert _lire(db, 20744).identite.statut == 'reelle'

    def test_20746_provenance_completee(self, tmp_path):
        db = _db_extrait(tmp_path)
        plan, res = _enregistrer(db, _lire(db, 20746))
        assert res.liens_crees == 0 and res.liens_completes == 831
        assert _compte(db, 'piece_associations', "WHERE provenance = 'description'") == 831
        produit = db.produits_site_de('1113161010')[0]
        assert (produit['ref_interne'], produit['id_product'], produit['ean']) == \
            ('EL1113161010', 20746, '7321423021278')

    def test_7285_piece_creee_relations_et_origines(self, tmp_path):
        db = _db_extrait(tmp_path)
        r = _lire(db, 7285)
        d = _tout_valider(r)
        d.ecartees.add('481949')
        plan, res = _enregistrer(db, r, d)
        assert res.piece == 'creee'
        assert db.conn.execute("SELECT is_phantom, description FROM pieces WHERE ref_piece = ?",
                               ['481073071153']).fetchone() == \
            (0, 'Pompe de vidange R2.5Y')      # coupé avant « pour machine à laver »
        succ = dict(db.conn.execute("SELECT ref_old, ref_new FROM piece_supersessions"))
        assert succ['C00535957'] == 'C00319033' and succ['488000535957'] == '481073071153'
        origines = dict(db.conn.execute(
            "SELECT ref_piece, origine FROM piece_equivalence_groups WHERE origine IS NOT NULL"))
        assert origines['00145522'] == 'BSH' and origines['C00319033'] == 'Indesit'
        assert db.conn.execute("SELECT ligne_fiche FROM piece_equivalence_groups "
                               "WHERE ref_piece = '00145522'").fetchone() == (1,)
        assert _compte(db, 'piece_equivalence_groups', "WHERE ref_piece = '481949'") == 0
        assert db.conn.execute("SELECT nature, forme FROM decisions_references "
                               "WHERE reference = '481949'").fetchone() == ('ecartee', '999999')
        assert _compte(db, 'piece_associations', "WHERE provenance = 'les_deux'") == 20
        relue = _lire(db, 7285)
        assert next(e for e in relue.equivalences if e.reference == '481949').statut == 'ecartee'
        assert 'origine_inconnue' not in relue.doutes_par_categorie()

    def test_les_3_fiches_relues_sans_rien_ajouter(self, tmp_path):
        db = _db_extrait(tmp_path)
        for n in (7285, 20746, 20744):
            _enregistrer(db, _lire(db, n))
        apres = _instantane(db)
        for n in (7285, 20746, 20744):
            r = _lire(db, n)
            plan = planifier(r, _tout_valider(r))
            assert plan.vide, (n, plan.resume())
            assert not r.absents_de_la_fiche
            res = _service(db).enregistrer(plan)
            assert res.ok and res.liens_crees == 0 and res.liens_completes == 0
        assert _instantane(db) == apres


# =============================================================================
# Mémoires branchées sur rapprocher()
# =============================================================================

class TestMemoires:
    def test_choix_dans_un_normalise_ambigu_memorise(self, tmp_path):
        b = Construite(tmp_path)
        a1 = b.appareil('Bosch', 'WOR20154/02')
        b.appareil('Bosch', 'WOR2015402')
        b.piece('REFP')
        fiche = _fiche(lignes=[('Bosch', 'WOR 20154/02')])
        r = _rapprocher(b.db, fiche)
        assert r.appareils[0].niveau == 'normalise_ambigu'
        d = DecisionsFiche()
        d.valider_tout(r)
        d.appareils[0] = ChoixAppareil(appareil_id=a1)
        plan, _ = _enregistrer(b.db, r, d)
        assert plan.decisions_ecritures == [('bosch', 'WOR 20154/02', 'WOR20154/02', 'meme')]
        relue = _rapprocher(b.db, fiche)
        assert relue.appareils[0].niveau == 'normalise'
        assert relue.appareils[0].appareil_id == a1 and relue.appareils[0].lien == 'deja_lie'

    def test_creer_malgre_ecriture_proche_memorise_distinct(self, tmp_path):
        b = Construite(tmp_path)
        b.appareil('Bosch', 'WOR20154/02')
        b.piece('REFP')
        fiche = _fiche(lignes=[('Bosch', 'WOR 20154-02')])
        r = _rapprocher(b.db, fiche)
        assert r.appareils[0].niveau == 'normalise'
        d = DecisionsFiche()
        d.valider_tout(r)
        d.appareils[0] = ChoixAppareil(creer=True)
        _enregistrer(b.db, r, d)
        relue = _rapprocher(b.db, fiche)
        assert relue.appareils[0].niveau == 'exact' and relue.appareils[0].lien == 'deja_lie'
        assert _compte(b.db, 'appareils') == 2

    def test_origine_saisie_reprise_a_la_relecture(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        fiche = _fiche(equivalentes=[('ZZ123',)])
        r = _rapprocher(b.db, fiche)
        assert 'origine_inconnue' in r.doutes_par_categorie()
        d = DecisionsFiche()
        d.valider_tout(r)
        d.origines['ZZ123'] = 'Maison'
        _enregistrer(b.db, r, d)
        relue = _rapprocher(b.db, fiche)
        e = relue.equivalences[0]
        assert (e.origine, e.source_origine, e.statut) == ('Maison', 'decision', 'deja_dans_le_groupe')
        assert 'origine_inconnue' not in relue.doutes_par_categorie()

    def test_ean_et_reference_interne(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        b.piece('AUTRE')
        with b.db._query_lock:
            b.db._enregistrer_produit_site('XREFP', 5, 'REFP', '8015250275551', 'hier')
            b.db._enregistrer_produit_site('XAUTRE', 6, 'AUTRE', None, 'hier')
            b.db.conn.commit()
        r = _rapprocher(b.db, _fiche(), ref_interne='XREFP', id_product=5, ean='8015250275551')
        assert r.identite.statut_ean_outil == 'identique'
        r = _rapprocher(b.db, _fiche(), ref_interne='XREFP', id_product=5, ean='7321423021278')
        assert r.identite.statut_ean_outil == 'different'
        assert 'ean_different' in r.doutes_par_categorie()
        r = _rapprocher(b.db, _fiche(), ref_interne='XAUTRE', id_product=6)
        assert r.identite.piece_du_produit == 'AUTRE'
        assert 'ref_interne_autre_piece' in r.doutes_par_categorie()
        # Référence interne changée sur le site : même id_product
        r = _rapprocher(b.db, _fiche(), ref_interne='NOUVREFP', id_product=5)
        assert r.identite.ref_interne_precedente == 'XREFP'
        _enregistrer(b.db, r)
        assert [p['ref_interne'] for p in b.db.produits_site_de('REFP')] == ['NOUVREFP']

    def test_ean_garde_ou_pris(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        with b.db._query_lock:
            b.db._enregistrer_produit_site('XREFP', 5, 'REFP', '8015250275551', 'hier')
            b.db.conn.commit()
        r = _rapprocher(b.db, _fiche(), ref_interne='XREFP', id_product=5, ean='7321423021278')
        d = _tout_valider(r)
        d.identite['ean_different'] = 'outil'
        _enregistrer(b.db, r, d)
        assert b.db.produits_site_de('REFP')[0]['ean'] == '8015250275551'
        d.identite['ean_different'] = 'site'
        _enregistrer(b.db, r, d)
        assert b.db.produits_site_de('REFP')[0]['ean'] == '7321423021278'

    def test_libelle_depuis_le_titre(self, tmp_path):
        assert libelle_depuis_titre("Balconnet (photos non contractuelles)") == "Balconnet"
        b = Construite(tmp_path)
        b.piece('REFP', libelle='Ancien')
        r = _rapprocher(b.db, _fiche(titre='Nouveau libellé (photos non contractuelles)'))
        assert r.identite.statut_libelle == 'different'
        _enregistrer(b.db, r)
        assert b.db.conn.execute("SELECT description FROM pieces").fetchone() == ('Ancien',)
        d = _tout_valider(r)
        d.identite['libelle_different'] = 'prendre'
        _enregistrer(b.db, r, d)
        assert b.db.conn.execute("SELECT description FROM pieces").fetchone() == ('Nouveau libellé',)

    def test_libelle_ecrit_avant_la_coupe_remplace_sans_question(self, tmp_path):
        # Reprise antérieure : le titre entier était devenu le libellé
        b = Construite(tmp_path)
        b.piece('REFP', libelle='Pompe pour lave-vaisselle (pièce générique)')
        r = _rapprocher(b.db, _fiche(titre='Pompe pour lave-vaisselle (pièce générique)'))
        assert r.identite.libelle == 'Pompe'
        assert r.identite.statut_libelle == 'ancienne_regle'
        assert 'libelle_different' not in r.doutes_par_categorie()
        _enregistrer(b.db, r)
        assert b.db.conn.execute("SELECT description FROM pieces").fetchone() == ('Pompe',)
        # Relecture : identique, plus rien à écrire
        r = _rapprocher(b.db, _fiche(titre='Pompe pour lave-vaisselle (pièce générique)'))
        assert r.identite.statut_libelle == 'identique'

    def test_base_non_migree_rend_du_vide(self):
        cnx = sqlite3.connect(':memory:')
        cnx.executescript((FIXTURES / 'base_extrait.sql').read_text(encoding='utf-8'))
        acces = AccesBaseLecture(cnx)
        assert acces.decisions_paires() == {} and acces.liens_site('11051894') == []
        assert acces.produit_site('GAU11051894', 20744) == []


# =============================================================================
# Décisions et plan
# =============================================================================

class TestPlan:
    def test_rien_sans_validation(self, tmp_path):
        db = _db_extrait(tmp_path)
        r = _lire(db, 20746)
        plan = planifier(r, DecisionsFiche())
        assert not plan.pret and plan.en_attente
        avant = _instantane(db)
        res = _service(db).enregistrer(plan)
        assert not res.ok and _instantane(db) == avant

    def test_categorie_de_cote_rien_ecrit(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'NEUF1', '', 'Lave-linge')]))
        d = DecisionsFiche()
        d.valider_tout(r)
        d.etats['absents'] = DE_COTE
        plan, res = _enregistrer(b.db, r, d)
        assert res.appareils_crees == 0 and _compte(b.db, 'appareils') == 0

    def test_absent_cree_puis_relu_exact(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        fiche = _fiche(lignes=[('Bosch', 'NEUF1', 'Série 4', 'Lave-linge')])
        r = _rapprocher(b.db, fiche)
        assert elements_par_categorie(r)['absents']['appareils'] == [0]
        plan, res = _enregistrer(b.db, r)
        assert res.appareils_crees == 1 and res.liens_crees == 1
        assert b.cnx.execute("SELECT type, manufacturer, ref_modele, commercial_ref FROM appareils"
                             ).fetchone() == ('Lave-linge', 'Bosch', 'NEUF1', 'Série 4')
        assert b.cnx.execute("SELECT provenance FROM piece_associations").fetchone() == ('description',)
        relue = _rapprocher(b.db, fiche)
        assert (relue.appareils[0].niveau, relue.appareils[0].lien) == ('exact', 'deja_lie')
        assert planifier(relue, _tout_valider(relue)).vide

    def test_type_manquant_a_completer(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'NEUF1')]))
        d = DecisionsFiche()
        d.valider_tout(r)
        plan = planifier(r, d)
        assert not plan.pret and 'type' in plan.a_completer[0]
        d.type_par_categorie['types_manquants'] = 'Lave-vaisselle'
        plan = planifier(r, d)
        assert plan.pret and plan.appareils_a_creer[0].type == 'Lave-vaisselle'

    def test_deja_couvert_sans_lien_sauf_rattachement(self, tmp_path):
        b = Construite(tmp_path)
        a = b.appareil('Bosch', 'X1')
        b.piece('REFP')
        b.piece('ANC')
        b.lien('ANC', a)
        b.db.add_supersession('ANC', 'REFP')
        r = _rapprocher(b.db, _fiche(lignes=[('Bosch', 'X1')]))
        assert r.appareils[0].lien == 'deja_couvert'
        assert planifier(r, _tout_valider(r)).liens == []
        d = _tout_valider(r)
        d.appareils[0] = ChoixAppareil(rattacher=True)
        assert planifier(r, d).liens == [(a, 'description')]

    def test_remplacement_en_conflit(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        b.db.add_supersession('X', 'Z')
        r = _rapprocher(b.db, _fiche(remplace=['X']))
        assert r.remplacements[0].statut == 'conflit'
        assert planifier(r, _tout_valider(r)).remplacements == []
        d = _tout_valider(r)
        d.remplacements['X'] = 'prendre'
        _enregistrer(b.db, r, d)
        assert b.cnx.execute("SELECT ref_new FROM piece_supersessions WHERE ref_old = 'X'"
                             ).fetchone() == ('REFP',)

    def test_liens_absents_signales_sauf_liste_tronquee(self, tmp_path):
        b = Construite(tmp_path)
        b.piece('REFP')
        _enregistrer(b.db, _rapprocher(b.db, _fiche(
            lignes=[('Bosch', 'A1', '', 'Four'), ('Bosch', 'A2', '', 'Four')])))
        b.lien('REFP', b.appareil('Bosch', 'PDF1'))      # lien sans provenance (PDF)
        courte = _fiche(lignes=[('Bosch', 'A1')])
        r = _rapprocher(b.db, courte)
        assert [a.ref_modele for a in r.absents_de_la_fiche] == ['A2']
        assert planifier(r, _tout_valider(r)).informations
        courte.liste_tronquee = True
        assert _rapprocher(b.db, courte).absents_de_la_fiche == []
        assert _compte(b.db, 'piece_associations') == 3          # rien n'est retiré

    def test_forme_reference(self):
        assert forme_reference('C00319033') == 'A99999999'
        assert forme_reference('DD82-01') == 'AA99-99'


# =============================================================================
# Aperçu rendu hors écran
# =============================================================================

def test_apercu_rendu_et_enregistrement(qapp, tmp_path):
    from src.ui.fiche_site_dialog import FicheSiteDialog
    db = _db_extrait(tmp_path)
    recus = []
    dlg = FicheSiteDialog(db, on_enregistre=lambda ref, res: recus.append((ref, res.ok)),
                          service=_service(db), chemin_regles=tmp_path / 'regles.json')
    dlg.analyser_page((FIXTURES / 'produit_7285.html').read_text(encoding='utf-8'),
                      'https://www.1001pieces.com/7285-fiche.html')
    dlg.show()
    qapp.processEvents()
    # À décider : récapitulatif et questions (moteur de l'import par lots)
    q = dlg.panneau.questionnaire
    assert q is not None and q.questions and set(dlg.panneau.cartes) == set(q.questions)
    assert dlg.modele.rowCount() == len(dlg.rapprochement.appareils)
    assert not dlg.bouton_enregistrer.isEnabled()
    image = dlg.grab()
    assert not image.isNull() and image.width() > 800
    # Filtre par catégorie
    dlg.filtre_categorie.setCurrentIndex(dlg.filtre_categorie.findData('a_valider'))
    assert dlg.filtre.rowCount() == 2
    # Choix individuel sur les lignes à valider, via le panneau
    for ligne in range(dlg.filtre.rowCount()):
        dlg.table.selectRow(ligne)
        dlg.choix_appareil.setCurrentIndex(1)            # 1er candidat
        dlg._appliquer_choix()
    dlg._tout_valider()                                  # propositions acceptées
    for x in q.sans_reponse():                           # sans proposition : 1er choix
        dlg._repondre(x.cle, x.choix[0][0])
    assert not (RACINE / 'data' / 'reprise_fiches.json').exists()   # jamais le fichier du poste
    assert dlg.bouton_enregistrer.isEnabled(), dlg.etat.text()
    dlg._enregistrer()
    assert recus == [('481073071153', True)]
    dlg.close()


# =============================================================================
# Copie de la vraie base : migration mesurée
# =============================================================================

@pytest.mark.skipif(not os.environ.get('AUTOFILL_BASE_COPIE'),
                    reason="AUTOFILL_BASE_COPIE : copie de la vraie base (API backup)")
def test_migration_sur_copie_de_la_vraie_base(tmp_path):
    source = sqlite3.connect(f"file:{os.environ['AUTOFILL_BASE_COPIE']}?mode=ro", uri=True)
    chemin = tmp_path / 'copie.db'
    cible = sqlite3.connect(chemin)
    source.backup(cible)
    cible.close()
    source.close()
    taille = chemin.stat().st_size
    debut = time.perf_counter()
    db = DatabaseManager(str(chemin))
    duree = time.perf_counter() - debut
    assert _compte(db, 'piece_associations', 'WHERE provenance IS NOT NULL') == 0
    assert duree < 30
    print(f"migration : {duree:.2f} s, {taille} → {chemin.stat().st_size} octets")
