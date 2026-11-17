"""
Rapprochement des fiches du site avec la base (CDC import fiches site, étape 2)

- Fiches d'exemple du § 11 sur un extrait de la vraie base
  (tests/fixtures/fiches_site/base_extrait.sql, scripts/extraire_base_fiches_test.py) ;
- un cas construit par niveau, lien, statut et catégorie de doute ;
- lecture seule : la connexion ouverte par AccesBaseLecture refuse toute écriture ;
- lignée identique à celle de DatabaseManager (get_references_liees) ;
- sur une COPIE de la vraie base (variable AUTOFILL_BASE_COPIE, faite avec l'API
  backup de sqlite3) : les 467 collisions normalisées ressortent en « normalisé ambigu ».
"""

import copy
import json
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import pytest

from src.services.export_config_service import DEFAULT_CONFIG
from src.utils.lecteur_fiche import (
    LectureFiche, LigneAppareil, LigneEquivalentes, lire_page_publique, modeles_depuis_config,
)
from src.utils.lecteur_fiche.page_publique import LigneTableSite
from src.utils.rapprochement_fiche import (
    CATEGORIES_DOUTES, CONFIGURATION_PAR_DEFAUT, AccesBaseLecture, ConfigurationRapprochement,
    charger_configuration, forme_normalisee, rapprocher,
)

RACINE = Path(__file__).resolve().parents[2]
FIXTURES = RACINE / 'tests' / 'fixtures' / 'fiches_site'
EXTRAIT = FIXTURES / 'base_extrait.sql'
TABLES = ('appareils', 'pieces', 'piece_associations', 'piece_supersessions',
          'piece_equivalence_groups', 'reference_decisions')
CONFIG = ConfigurationRapprochement()


# =============================================================================
# Outils
# =============================================================================

def _connexion_extrait() -> sqlite3.Connection:
    cnx = sqlite3.connect(':memory:')
    cnx.executescript(EXTRAIT.read_text(encoding='utf-8'))
    return cnx


def _base_vide() -> sqlite3.Connection:
    """Même schéma que l'extrait (tiré de la vraie base), sans aucune ligne."""
    cnx = _connexion_extrait()
    for table in TABLES:
        cnx.execute(f"DELETE FROM {table}")
    return cnx


class Base:
    """Base de test construite : appareils, pièces, liens, relations."""

    def __init__(self):
        self.cnx = _base_vide()
        self._id = 0

    def appareil(self, marque, ref, type_='Lave-linge', nom='') -> int:
        self._id += 1
        self.cnx.execute("INSERT INTO appareils(id, type, manufacturer, ref_modele, commercial_ref) "
                         "VALUES (?, ?, ?, ?, ?)", [self._id, type_, marque, ref, nom])
        return self._id

    def piece(self, ref, fantome=False, obsolete=False) -> int:
        cur = self.cnx.execute("INSERT INTO pieces(ref_piece, is_phantom, is_obsolete) VALUES (?, ?, ?)",
                               [ref, int(fantome), int(obsolete)])
        return cur.lastrowid

    def lien(self, ref_piece, appareil_id):
        (pid,) = self.cnx.execute("SELECT id FROM pieces WHERE ref_piece = ?", [ref_piece]).fetchone()
        self.cnx.execute("INSERT INTO piece_associations(piece_id, appareil_id) VALUES (?, ?)",
                         [pid, appareil_id])

    def remplace(self, ancienne, nouvelle):
        for r in (ancienne, nouvelle):
            self.cnx.execute("INSERT OR IGNORE INTO pieces(ref_piece, is_phantom) VALUES (?, 1)", [r])
        self.cnx.execute("INSERT INTO piece_supersessions VALUES (?, ?)", [ancienne, nouvelle])

    def groupe(self, group_id, *refs):
        for r in refs:
            self.cnx.execute("INSERT OR IGNORE INTO pieces(ref_piece) VALUES (?)", [r])
            self.cnx.execute("INSERT INTO piece_equivalence_groups VALUES (?, ?)", [group_id, r])

    def distinct(self, ref_modele):
        self.cnx.execute("INSERT INTO reference_decisions(ref_modele, decision) VALUES (?, 'DISTINCT')",
                         [ref_modele])

    def acces(self) -> AccesBaseLecture:
        return AccesBaseLecture(self.cnx)


def _fiche(code=('REFP',), lignes=(), remplace=(), remplacee_par=(), equivalentes=(),
           refs_marque=(), annoncees=()) -> LectureFiche:
    """LectureFiche construite : lignes = (marque, ref[, nom[, source[, type]]])."""
    appareils = []
    for n, l in enumerate(lignes, 1):
        marque, ref, nom, source, type_ = (tuple(l) + ('', '', ''))[:5]
        if not source:
            source = 'entete' if marque else 'annonces'
        appareils.append(LigneAppareil(n, marque or None, ref, nom, 'ref_nom', n,
                                       source_marque=source, type_ligne=type_))
    return LectureFiche(
        code_produit=list(code), remplace=list(remplace), remplacee_par=list(remplacee_par),
        equivalentes=[LigneEquivalentes(i, list(refs), 0, 'texte')
                      for i, refs in enumerate(equivalentes, 1)],
        references_par_marque=[LigneEquivalentes(i, list(refs), 0, 'texte', origine=o)
                               for i, (o, refs) in enumerate(refs_marque, 1)],
        marques_annoncees=list(annoncees), appareils=appareils)


def _r(base, fiche, **kw):
    return rapprocher(fiche, base.acces(), CONFIG, **kw)


# =============================================================================
# Fiches d'exemple (§ 11) sur l'extrait de la vraie base
# =============================================================================

@pytest.fixture(scope='module')
def exemples():
    acces = AccesBaseLecture(_connexion_extrait())
    modeles = modeles_depuis_config(copy.deepcopy(DEFAULT_CONFIG))
    marques, types = list(acces.marques().values()), list(acces.types().values())
    out = {}
    for i in (7285, 20746, 20744):
        page = lire_page_publique((FIXTURES / f'produit_{i}.html').read_text(encoding='utf-8'),
                                  modeles=modeles, marques_connues=marques, types_connus=types)
        out[i] = rapprocher(page.description, acces, CONFIG, page=page)
    return out


class TestFichesExemple:
    def test_20746_831_lignes_deja_liees(self, exemples):
        r = exemples[20746]
        assert r.identite.ref_piece == '1113161010'
        assert r.identite.statut == 'reelle'
        assert (r.identite.statut_ref_interne, r.identite.prefixe) == ('prefixe', 'EL')
        assert r.identite.statut_ean == 'valide'
        assert len(r.appareils) == 831
        assert {a.niveau for a in r.appareils} == {'exact'}
        assert {a.lien for a in r.appareils} == {'deja_lie'}
        assert r.doutes == []

    def test_20744_450_deja_couverts_par_les_4_predecesseurs(self, exemples):
        r = exemples[20744]
        assert (r.identite.ref_piece, r.identite.statut) == ('11051894', 'fantome')
        assert r.identite.prefixe == 'GAU'
        assert len(r.appareils) == 450
        assert {a.lien for a in r.appareils} == {'deja_couvert'}
        par_ref = defaultdict(int)
        for a in r.appareils:
            for ref in a.couvert_par:
                par_ref[ref] += 1
        assert dict(par_ref) == {'00703010': 306, '00702570': 2, '00701738': 20, '00667780': 122}
        assert {x.statut for x in r.remplacements} == {'deja_present'}
        assert {r.lignee[x] for x in ('00703010', '00702570', '00701738', '00667780')} == {'depart'}

    def test_7285_paire_appariee_par_la_forme(self, exemples):
        r = exemples[7285]
        assert (r.identite.ref_piece, r.identite.statut) == ('481073071153', 'absente')
        assert r.identite.statut_ref_interne == 'egale'
        assert {(x.ancienne, x.nouvelle) for x in r.remplacements} == {
            ('C00535957', 'C00319033'), ('488000535957', '481073071153'),
            ('C00309416', 'C00319033'), ('482000032568', '481073071153')}
        assert {x.appariement for x in r.remplacements} == {'forme'}
        assert all(x.statut == 'nouveau' and x.fantome_a_creer for x in r.remplacements)

    def test_7285_equivalences_et_481949_en_doute(self, exemples):
        r = exemples[7285]
        origines = {e.reference: (e.origine, e.ligne) for e in r.equivalences}
        assert origines == {'C00319033': ('Indesit', 0), '00145522': ('BSH', 1), '481949': ('', 2)}
        doutes = r.doutes_par_categorie()
        assert [d.element for d in doutes['origine_inconnue']] == ['equivalence:481949']

    def test_7285_union_avec_la_table_du_site(self, exemples):
        r = exemples[7285]
        assert sum(a.provenance == 'les_deux' for a in r.appareils) == 20
        assert sum(a.niveau == 'exact' for a in r.appareils) == 1838
        assert {a.lien for a in r.appareils if a.niveau == 'exact'} == {'nouveau'}

    def test_resume(self, exemples):
        res = exemples[20744].resume()
        assert res['niveaux'] == {'exact': 450}
        assert res['liens'] == {'deja_couvert': 450}
        assert res['remplacements'] == {'deja_present': 4}


# =============================================================================
# Lecture seule et lignée
# =============================================================================

class TestLectureSeule:
    def test_aucune_ecriture_possible(self, tmp_path):
        chemin = tmp_path / 'base.db'
        cnx = sqlite3.connect(chemin)
        cnx.executescript(EXTRAIT.read_text(encoding='utf-8'))
        cnx.close()
        with AccesBaseLecture.ouvrir(chemin) as acces:
            assert acces.marques()
            with pytest.raises(sqlite3.OperationalError, match='readonly'):
                acces.cnx.execute("DELETE FROM appareils")

    def test_rapprochement_ne_modifie_pas_la_base(self):
        cnx = _connexion_extrait()
        avant = [cnx.execute(f"SELECT COUNT(*) FROM {t}").fetchone() for t in TABLES]
        modifications = cnx.total_changes            # chargement de l'extrait
        rapprocher(_fiche(code=('NOUVELLE',), lignes=[('Bosch', 'XYZ123')],
                          remplace=('ANC1',), equivalentes=[('00145522',)]),
                   AccesBaseLecture(cnx), CONFIG)
        assert cnx.total_changes == modifications
        assert [cnx.execute(f"SELECT COUNT(*) FROM {t}").fetchone() for t in TABLES] == avant


class TestLignee:
    def test_meme_lignee_que_database_manager(self, test_db_manager, temp_db_path):
        db = test_db_manager
        assert db.add_supersession('A1', 'A2')[0]
        assert db.add_supersession('A2', 'A3')[0]
        assert db.add_supersession('B1', 'A3')[0]
        assert db.add_equivalence('A3', 'E1')[0]
        assert db.add_supersession('E0', 'E1')[0]
        db.conn.commit()
        liees = db.get_references_liees('A2')
        attendu = {'A2', *liees['nouvelles'], *liees['anciennes'], *liees['autres'],
                   *liees['equivalentes']}
        with AccesBaseLecture.ouvrir(temp_db_path) as acces:
            assert acces.chaine('A1') == db.get_supersession_chain('A1')
            assert set(acces.predecesseurs('A3')) == set(db.get_all_predecessors('A3'))
            lignee = acces.lignee(['A2'])
        assert attendu <= set(lignee)
        assert lignee['A2'] == 'depart'
        assert {lignee[r] for r in ('A1', 'A3', 'B1')} == {'succession'}
        assert lignee['E1'] == 'equivalence'
        assert lignee['E0'] == 'equivalence'   # ancienne version d'une équivalente


# =============================================================================
# Appareils (§ 5.2)
# =============================================================================

class TestNiveaux:
    def test_exact_normalise_absent(self):
        b = Base()
        b.appareil('Bosch', 'WOR20154/02')
        b.appareil('Bosch', 'WAE24410FF/01')
        r = _r(b, _fiche(lignes=[('Bosch', 'WOR20154/02'), ('BOSCH', 'WOR 20154/02'),
                                 ('Bosch', 'WAE2441-0FF01'), ('Bosch', 'INCONNU1')]))
        assert [a.niveau for a in r.appareils] == ['exact', 'normalise', 'normalise', 'absent']
        assert r.appareils[1].marque == 'Bosch'          # casse de l'outil
        assert r.appareils[1].appareil_id == 1           # l'écriture de la base est gardée
        assert r.appareils[3].lien == 'nouveau'

    def test_collision_existante_normalise_ambigu(self):
        b = Base()
        b.appareil('Beko', 'MBW61SW/1')
        b.appareil('Beko', 'MBW61SW1')
        r = _r(b, _fiche(lignes=[('Beko', 'MBW61SW/1'), ('Beko', 'MBW 61SW1-')]))
        assert [a.niveau for a in r.appareils] == ['normalise_ambigu'] * 2
        assert r.appareils[0].proposition == 1           # l'écriture exacte est proposée
        assert r.appareils[1].proposition is None
        assert len(r.doutes_par_categorie()['normalise_ambigu']) == 2

    def test_pas_de_creation_si_candidat_normalise(self):
        b = Base()
        b.appareil('Bosch', 'FN4957SED-1')
        r = _r(b, _fiche(lignes=[('Bosch', 'FN4957SED1')]))
        assert r.appareils[0].niveau == 'normalise'

    def test_decisions_sur_paires(self):
        b = Base()
        b.appareil('Beko', 'MBW61SW/1')
        b.appareil('Beko', 'MBW61SW1')
        b.appareil('Bosch', 'CHW200G.')
        decisions = {('beko', frozenset(('MBW61SW/1', 'MBW61SW1'))): 'distinct',
                     ('bosch', frozenset(('CHW200G', 'CHW200G.'))): 'distinct'}
        r = _r(b, _fiche(lignes=[('Beko', 'MBW61SW/1'), ('Bosch', 'CHW200G')]),
               decisions_paires=decisions)
        assert r.appareils[0].niveau == 'exact'          # l'autre écriture est un autre appareil
        assert r.appareils[1].niveau == 'absent'         # distinct décidé : création permise
        decisions = {('beko', frozenset(('MBW 61SW1', 'MBW61SW1'))): 'meme'}
        r = _r(b, _fiche(lignes=[('Beko', 'MBW 61SW1')]), decisions_paires=decisions)
        assert (r.appareils[0].niveau, r.appareils[0].appareil_id) == ('normalise', 2)

    def test_exact_multiple_departage_par_le_type(self):
        b = Base()
        b.appareil('Bosch', 'SMS50E02', 'Lave-vaisselle')
        b.appareil('Bosch', 'SMS50E02', 'Four')
        b.distinct('SMS50E02')
        r = _r(b, _fiche(lignes=[('Bosch', 'SMS50E02')]), categorie='Pompe - Lave-vaisselle')
        a = r.appareils[0]
        assert (a.niveau, a.appareil_id, a.type) == ('exact_multiple', 1, 'Lave-vaisselle')
        assert 'distincts' in a.raison
        assert r.doutes == []
        r = _r(b, _fiche(lignes=[('Bosch', 'SMS50E02')]))
        assert r.appareils[0].appareil_id is None
        assert set(r.doutes_par_categorie()) == {'exact_multiple', 'type_ambigu'}

    def test_a_valider_autre_marque_du_groupe(self):
        b = Base()
        b.appareil('Siemens', 'WM14E425')
        b.appareil('Candy', 'WM14E426')
        r = _r(b, _fiche(lignes=[('Bosch', 'WM14E425'), ('Bosch', 'WM14E426')]))
        assert r.appareils[0].niveau == 'a_valider'
        assert 'Siemens' in r.appareils[0].raison
        assert r.appareils[1].niveau == 'absent'          # Candy n'est pas du groupe BSH

    def test_a_valider_par_le_nom_commercial(self):
        b = Base()
        b.appareil('Whirlpool', '858420018050', nom='ETW D 61252 W (ES)')
        r = _r(b, _fiche(lignes=[('Whirlpool', '758420018050', 'ETW D 61252 W (ES)')]))
        assert r.appareils[0].niveau == 'a_valider'
        assert 'nom commercial' in r.appareils[0].raison


class TestMarquesAnnoncees:
    def test_marque_deduite(self):
        b = Base()
        b.appareil('Ignis', 'AWV500')
        b.appareil('Whirlpool', 'AWM8000')
        b.appareil('Laden', 'EV 1047')
        fiche = _fiche(lignes=[('', 'AWV500'), ('', 'AWM8000'), ('', 'EV1047'), ('', 'ZZZ1')],
                       annoncees=('Whirlpool', 'Laden', 'Ignis', 'Bauknecht'))
        r = _r(b, fiche)
        assert [(a.marque, a.source_marque, a.niveau) for a in r.appareils] == [
            ('Ignis', 'deduite', 'exact'), ('Whirlpool', 'deduite', 'exact'),
            ('Laden', 'deduite', 'normalise'), ('', 'a_choisir', 'absent')]
        assert r.resume()['marques_deduites'] == 3
        assert r.resume()['marques_a_deduire'] == 4

    def test_plusieurs_marques_possibles(self):
        b = Base()
        b.appareil('Ignis', 'AWV500')
        b.appareil('Laden', 'AWV500')
        r = _r(b, _fiche(lignes=[('', 'AWV500')], annoncees=('Laden', 'Ignis')))
        a = r.appareils[0]
        assert (a.niveau, a.source_marque, len(a.candidats)) == ('a_valider', 'a_choisir', 2)
        assert 'marque_a_choisir' in r.doutes_par_categorie()


class TestLiens:
    def test_deja_lie_deja_couvert_nouveau(self):
        b = Base()
        a1, a2, a3, a4 = (b.appareil('Bosch', f'R{i}') for i in range(1, 5))
        b.piece('P')
        b.remplace('OLD', 'P')
        b.groupe(1, 'P', 'EQ')
        b.lien('P', a1)
        b.lien('OLD', a2)
        b.lien('EQ', a3)
        r = _r(b, _fiche(code=('P',), lignes=[('Bosch', f'R{i}') for i in range(1, 5)]))
        assert [(a.lien, a.couvert_par) for a in r.appareils] == [
            ('deja_lie', []), ('deja_couvert', ['OLD']), ('deja_couvert', ['EQ']), ('nouveau', [])]

    def test_references_de_la_fiche_comptent_dans_la_lignee(self):
        b = Base()
        a1 = b.appareil('Bosch', 'R1')
        b.piece('ANC')
        b.lien('ANC', a1)
        r = _r(b, _fiche(code=('P',), lignes=[('Bosch', 'R1')], remplace=('ANC',)))
        assert (r.appareils[0].lien, r.appareils[0].couvert_par) == ('deja_couvert', ['ANC'])


class TestType:
    def test_ordre_table_ligne_base_categorie(self):
        b = Base()
        b.appareil('Bosch', 'R1', 'Lave-linge')
        b.appareil('Bosch', 'R2', '')
        b.appareil('Bosch', 'R3', 'Lave-linge')
        b.appareil('Bosch', 'AUTRE', 'Lave-vaisselle')     # type connu de l'outil
        fiche = _fiche(lignes=[('Bosch', 'R1'), ('Bosch', 'R2'), ('Bosch', 'NEUF', '', '', 'Four'),
                               ('Bosch', 'NEUF2'), ('Bosch', 'R3')])
        table = [LigneTableSite('Sèche-linge', 'Bosch', 'R3', '')]
        r = _r(b, fiche, categorie='Pompe - Lave-vaisselle', table_site=table)
        assert [(a.type, a.source_type) for a in r.appareils] == [
            ('Lave-linge', 'base'), ('Lave-vaisselle', 'categorie'), ('Four', 'ligne'),
            ('Lave-vaisselle', 'categorie'), ('Lave-linge', 'base')]
        # Type explicite contraire à la base : relié, type de l'outil gardé, écart proposé
        a = r.appareils[4]
        assert a.niveau == 'exact' and not a.doutes and a.type_site == 'Sèche-linge'
        assert [(e.champ, e.outil, e.site) for e in a.ecarts] == [('type', 'Lave-linge', 'Sèche-linge')]
        assert a.provenance == 'les_deux'

    def test_type_manquant_et_categorie_non_mono_type(self):
        b = Base()
        b.appareil('Bosch', 'X', 'Four')
        r = _r(b, _fiche(lignes=[('Bosch', 'NEUF')]), categorie='Machine à café & bouilloire')
        assert 'type_manquant' in r.doutes_par_categorie()

    def test_lignes_de_la_table_seule(self):
        b = Base()
        b.appareil('Bosch', 'R1')
        table = [LigneTableSite('Lave-linge', 'Bosch', 'R1', 'Maxx'),
                 LigneTableSite('Lave-linge', 'Bosch', 'R9', '')]
        r = _r(b, _fiche(lignes=[]), table_site=table)
        assert [(a.provenance, a.niveau, a.numero) for a in r.appareils] == [
            ('table', 'exact', 0), ('table', 'absent', 0)]


# =============================================================================
# Remplacements (§ 5.4)
# =============================================================================

class TestRemplacements:
    def test_statuts(self):
        b = Base()
        b.piece('P')
        b.remplace('X1', 'P')                 # déjà présent
        b.remplace('X2', 'Z')
        b.remplace('Z', 'P')                  # X2 → Z → P : confirmé par la chaîne
        b.remplace('X3', 'AUTRE')             # conflit
        b.remplace('P', 'X4')                 # cycle : P → X4, la fiche dit X4 → P
        b.piece('X5')                         # sans successeur
        r = _r(b, _fiche(code=('P',), remplace=('X1', 'X2', 'X3', 'X4', 'X5', 'X6')))
        statuts = {x.ancienne: (x.statut, x.fantome_a_creer) for x in r.remplacements}
        assert statuts == {'X1': ('deja_present', False), 'X2': ('confirme_par_chaine', False),
                           'X3': ('conflit', False), 'X4': ('cycle', False),
                           'X5': ('nouveau', False), 'X6': ('nouveau', True)}
        doutes = r.doutes_par_categorie()
        assert [d.element for d in doutes['remplacement_conflit']] == ['remplacement:X3']
        assert [d.element for d in doutes['remplacement_cycle']] == ['remplacement:X4']

    def test_fiche_anterieure_a_la_lignee(self):
        b = Base()
        b.remplace('X', 'Q')
        b.remplace('P', 'Q')                  # la fiche (X → P) est plus ancienne que P → Q
        r = _r(b, _fiche(code=('P',), remplace=('X',)))
        assert r.remplacements[0].statut == 'confirme_par_chaine'

    def test_remplacee_par(self):
        b = Base()
        b.piece('P')
        r = _r(b, _fiche(code=('P',), remplacee_par=('SUIV',)))
        x = r.remplacements[0]
        assert (x.ancienne, x.nouvelle, x.sens, x.statut) == ('P', 'SUIV', 'remplacee_par', 'nouveau')

    def test_paire_sans_forme_commune(self):
        b = Base()
        r = _r(b, _fiche(code=('481073071153', 'C00319033'), remplace=('ABC123',)))
        x = r.remplacements[0]
        assert (x.nouvelle, x.appariement) == ('481073071153', 'a_choisir')
        assert 'appariement' in r.doutes_par_categorie()


# =============================================================================
# Équivalences (§ 5.3)
# =============================================================================

class TestEquivalences:
    def test_statuts_et_origines(self):
        b = Base()
        b.groupe(1, 'P', '00145522')
        b.groupe(2, '11051894')
        b.remplace('00703010', 'P')
        fiche = _fiche(code=('P', 'C00319033'),
                       equivalentes=[('00145522', '11051894'), ('00703010',), ('1522345678',),
                                     ('481949',)],
                       refs_marque=[('EGO', ('55.13059.010',))])
        r = _r(b, fiche, references_ecartees=('481949',))
        e = {x.reference: (x.statut, x.origine, x.source_origine) for x in r.equivalences}
        assert e == {
            'C00319033': ('nouveau', 'Indesit', 'format'),
            '00145522': ('deja_dans_le_groupe', 'BSH', 'format'),
            '11051894': ('fusion_groupes', 'BSH', 'format'),
            '00703010': ('dans_la_succession', 'BSH', 'format'),
            '1522345678': ('nouveau', '', ''),
            '481949': ('ecartee', '', ''),
            '55.13059.010': ('nouveau', 'EGO', 'fiche'),
        }
        doutes = r.doutes_par_categorie()
        assert [d.element for d in doutes['origine_ambigue']] == ['equivalence:1522345678']
        assert 'origine_inconnue' not in doutes         # 481949 écartée : plus demandée

    def test_ligne_melangee(self):
        r = _r(Base(), _fiche(equivalentes=[('481010595139', '00145522')]))
        assert 'ligne_melangee' in r.doutes_par_categorie()
        # Paire Whirlpool / Indesit sur une ligne : même groupe, pas de doute
        r = _r(Base(), _fiche(equivalentes=[('484000008424', 'C00379998')]))
        assert 'ligne_melangee' not in r.doutes_par_categorie()


# =============================================================================
# Identité (§ 5.1)
# =============================================================================

class TestIdentite:
    def test_secours_par_la_reference_interne(self):
        b = Base()
        b.piece('11051894', fantome=True)
        r = _r(b, _fiche(code=()), ref_interne='GAU11051894')
        i = r.identite
        assert (i.ref_piece, i.source, i.prefixe, i.statut) == \
            ('11051894', 'ref_interne', 'GAU', 'fantome')
        assert 'code_produit_absent' in r.doutes_par_categorie()

    def test_reference_interne_de_la_lignee_ou_differente(self):
        b = Base()
        b.remplace('00123456', 'P')
        i = _r(b, _fiche(code=('P',)), ref_interne='GAU00123456').identite
        assert (i.statut_ref_interne, i.prefixe) == ('lignee', 'GAU')
        r = _r(b, _fiche(code=('P',)), ref_interne='ES10028')
        assert r.identite.statut_ref_interne == 'differente'
        assert 'ref_interne_differente' in r.doutes_par_categorie()

    def test_ean(self):
        b = Base()
        assert _r(b, _fiche(), ean='8015250275551').identite.statut_ean == 'valide'
        r = _r(b, _fiche(), ean='8015250275552')
        assert r.identite.statut_ean == 'cle_fausse'
        assert 'ean_invalide' in r.doutes_par_categorie()

    def test_categories_de_doute_connues(self, exemples):
        for r in exemples.values():
            assert set(r.doutes_par_categorie()) <= set(CATEGORIES_DOUTES)


# =============================================================================
# Configuration (§ 5.5, 5.6, § 9)
# =============================================================================

class TestConfiguration:
    @pytest.mark.parametrize('ref, origine', [
        ('481073071153', 'Whirlpool'), ('C00319033', 'Indesit'), ('00145522', 'BSH'),
        ('11051894', 'BSH'), ('49012345', 'Candy'), ('1113161010', 'Electrolux'),
        ('1712345678', 'Beko'), ('50123456789', 'Electrolux'), ('140012345678', 'Electrolux'),
        ('611234567', 'Liebherr'), ('691234567', 'Smeg'), ('1234567', 'Miele'),
        ('012345', 'Atlantic / Thermor'), ('92X6108', 'Brandt'), ('AS0012345', 'Brandt'),
        ('DD82-01234A', 'Samsung'), ('ADQ12345678', 'LG'),
        ('1522345678', ''), ('42123456', ''), ('32123456', ''), ('161234567', 'Beko'), ('264440194', 'Beko'),
        ('71S7962', ''), ('481949', ''),
    ])
    def test_formats(self, ref, origine):
        assert CONFIG.origine(ref).etiquette == origine

    def test_cas_melanges_signales(self):
        assert CONFIG.origine('1522345678').doute == 'Electrolux ou Beko'
        assert not CONFIG.origine('481949').doute

    @pytest.mark.parametrize('ref, origine', [
        # Débuts Beko où la base ne compte que des pièces Beko (2026-11-13)
        ('2466300203', 'Beko'), ('2448000100', 'Beko'), ('2912345600', 'Beko'),
        ('4331234500', 'Beko'), ('5781234500', 'Beko'), ('6101234500', 'Beko'),
        ('1511234500', 'Beko'), ('1911234500', 'Beko'), ('2711234500', 'Beko'),
        ('9181234500', 'Beko'),
        # Débuts Electrolux voisins ou mélangés : inchangés
        ('2426000100', 'Electrolux'), ('4051234500', 'Electrolux'), ('5561234500', 'Electrolux'),
        ('1461234500', 'Electrolux'), ('2271234500', 'Electrolux'), ('9161234500', 'Electrolux'),
    ])
    def test_formats_beko(self, ref, origine):
        assert CONFIG.origine(ref).etiquette == origine

    def test_prefixes(self):
        assert CONFIG.sans_prefixe('EL1113161010', '1113161010') == ('1113161010', 'EL')
        assert CONFIG.sans_prefixe('STN012345') == ('12345', 'STN0')
        assert CONFIG.sans_prefixe('DD82-1', 'D82-1') == ('D82-1', 'D')
        assert CONFIG.sans_prefixe('ES10028', '10028') == ('ES10028', '')

    def test_categorie_vers_type(self):
        types = {'lave-linge': 'Lave-linge', 'micro-ondes': 'Micro-ondes'}
        assert CONFIG.type_de_categorie('Pompe de vidange - Lave-linge', types) == 'Lave-linge'
        assert CONFIG.type_de_categorie('Divers - MO', types) == 'Micro-ondes'
        assert CONFIG.type_de_categorie('Machine à café & bouilloire', types) == ''
        assert CONFIG.type_de_categorie('ACCESSOIRES LAVAGE', types) == ''

    def test_fichier_remplace_cle_par_cle(self, tmp_path):
        chemin = tmp_path / 'reprise_fiches.json'
        chemin.write_text(json.dumps({'prefixes_ref_interne': ['XY']}), encoding='utf-8')
        c = charger_configuration(chemin)
        assert c.prefixes == ('XY',)
        assert c.origine('481073071153').etiquette == 'Whirlpool'   # défaut conservé
        chemin.write_text('{illisible', encoding='utf-8')
        assert charger_configuration(chemin).prefixes == CONFIG.prefixes

    def test_exemple_conforme_aux_defauts(self):
        exemple = json.loads((RACINE / 'data' / 'reprise_fiches.example.json')
                             .read_text(encoding='utf-8'))
        assert exemple == CONFIGURATION_PAR_DEFAUT

    def test_motifs_compilables(self):
        for regle in CONFIGURATION_PAR_DEFAUT['formats_references']:
            re.compile(regle['motif'])


# =============================================================================
# Copie de la vraie base (facultatif)
# =============================================================================

COPIE = os.environ.get('AUTOFILL_BASE_COPIE')


@pytest.mark.skipif(not COPIE, reason="AUTOFILL_BASE_COPIE : copie de appareils.db (API backup)")
def test_467_collisions_normalisees_en_ambigu():
    acces = AccesBaseLecture.ouvrir(COPIE)
    formes = defaultdict(set)
    for marque, ref in acces.cnx.execute("SELECT manufacturer, ref_modele FROM appareils"):
        formes[(marque or '', forme_normalisee(ref))].add(ref or '')
    collisions = {k: v for k, v in formes.items() if len(v) > 1}
    assert len(collisions) == 467
    par_marque = defaultdict(list)
    for (marque, _), ecritures in collisions.items():
        par_marque[marque] += sorted(ecritures)
    niveaux = set()
    for marque, ecritures in par_marque.items():
        r = rapprocher(_fiche(code=('ZZTEST',), lignes=[(marque, e) for e in ecritures]), acces, CONFIG)
        niveaux |= {a.niveau for a in r.appareils}
    assert niveaux == {'normalise_ambigu'}


class TestEcrituresDeMarque:
    def test_singulier_pluriel_et_alias(self):
        b = Base()
        b.appareil('Rosières', '33000076')
        b.appareil('Hotpoint-Ariston', 'AQ7L')
        config = ConfigurationRapprochement({'alias_marques': {'Ariston': 'Hotpoint-Ariston'}})
        r = rapprocher(_fiche(lignes=[('', '33000076'), ('Ariston', 'AQ7L')],
                              annoncees=('Rosière', 'Candy')), b.acces(), config)
        assert [(a.marque, a.niveau) for a in r.appareils] == [
            ('Rosières', 'exact'), ('Hotpoint-Ariston', 'exact')]
        assert r.appareils[0].source_marque == 'deduite'
