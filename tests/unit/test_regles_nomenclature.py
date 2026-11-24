"""
Règles de nomenclature, lot 3 — moteur sans écran (CDC docs/cdc_regles_nomenclature.md).

- motifs (§ 6.1) : # @ ? * et classes, ancrés au début, forme et spécificité ;
- liste fermée des types (§ 3) et catalogue versionné (§ 9.2) ;
- résolution (§ 6.2) : cas pièges du § 11, marque avant groupe, la plus
  précise gagne, conflit entre clés, règles proposées ignorées ;
- critère du lot 3 : appliqué aux listes figées des lots 1 et 2, le catalogue
  ne propose AUCUN autre type que celui déjà posé ;
- force (§ 7), découverte (§ 6.3, avec test de charge < 30 s) ;
- service sur une base : contrôle à l'enregistrement, propositions rangées
  sans jamais toucher au type des appareils, refus respectés ;
- script : simulation sans écriture.
"""

import csv
import json
import random
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

from src.core.constants import TypesAppareils
from src.data.database_manager import DatabaseManager
from src.services.regle_nomenclature_service import (
    CHEMIN_CATALOGUE, RegleNomenclatureService, lire_catalogue)
from src.utils.filtre_colonne import (
    FORME_GABARIT, FORME_POSITION, FORME_PREFIXE, MotifRegleInvalide, forme_motif_regle,
    longueur_motif_regle, motif_regle_vers_regex)
from src.utils.nomenclature.cles import cle_code, cle_nom
from src.utils.nomenclature.decouverte import decouvrir
from src.utils.nomenclature.force import FORCE_FORTE, FORCE_SIMPLE, force_proposition, sont_voisins
from src.utils.nomenclature.moteur import IndexRegles, Regle
from src.utils.rapprochement_fiche.configuration import ConfigurationRapprochement
from src.utils.lecteur_fiche.lecteur import cle_marque
from src.utils.types_autorises import CHEMIN_TYPES_AUTORISES, charger_types_autorises

RACINE = Path(__file__).resolve().parents[2]
CORRECTIONS = RACINE / 'data' / 'corrections'
_CONFIG = ConfigurationRapprochement()


def groupe_de(marque):
    return _CONFIG.groupe_de.get(cle_marque(marque), '')


def _index(regles):
    return IndexRegles(regles, groupe_de)


def _catalogue_index():
    return _index([Regle.depuis_ligne(l) for l in lire_catalogue()])


def _resoudre(index, marque, ref_modele, ref_com=''):
    return index.resoudre(marque, cle_nom(ref_modele, ref_com), cle_code(ref_modele, ref_com))


# ── Motifs ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('motif,forme', [
    ('AKZ*', FORME_PREFIXE), ('EW?F*', FORME_POSITION), ('HBC8[3-6][KEP]*', FORME_POSITION),
    ('HSG###@@#', FORME_GABARIT), ('akz*', FORME_PREFIXE),
])
def test_forme_du_motif(motif, forme):
    assert forme_motif_regle(motif) == forme


@pytest.mark.parametrize('motif,oui,non', [
    ('AKZ*', ['AKZ', 'AKZ513IX'], ['XAKZ', 'AK']),
    ('AKZ#S*', ['AKZ9S8270NB'], ['AKZ513IX', 'AKZ96230S']),
    ('EW?F*', ['EW6F428B'], ['EW6T4', 'EWF6']),
    ('CM[4-9]##@?@#', ['CM633GBS1', 'CM676G0S1'], ['CM633GBS1B', 'CM333GBS1', 'CM633GB1S']),
    ('HBC8[3-6][KEP]*', ['HBC84K553A', 'HBC86P753'], ['HBC87K553', 'HBC84D553']),
])
def test_motif_ancre_au_debut(motif, oui, non):
    regex = motif_regle_vers_regex(motif)
    assert all(regex.fullmatch(v) for v in oui)
    assert not any(regex.fullmatch(v) for v in non)


@pytest.mark.parametrize('motif', ['', '*', 'A*B', 'AK Z*', 'AKZ|AKP', '!AKZ*', '[9-3]X', '[A-3]', 'A%*'])
def test_motif_invalide(motif):
    with pytest.raises(MotifRegleInvalide):
        motif_regle_vers_regex(motif)


def test_longueur_classe_compte_pour_un():
    assert longueur_motif_regle('HBC8[3-6][KEP]*') == 6
    assert longueur_motif_regle('GKN[12]*') == 4


def test_filtre_de_colonne_inchange():
    """Les fonctions des filtres de colonne gardent leur sens (PR #169)."""
    from src.utils.filtre_colonne import condition_filtre_colonne, motif_vers_like
    assert motif_vers_like('WOI4S') == '%WOI4S%'
    assert motif_vers_like('WOI?S*') == 'WOI_S%'
    sql, params = condition_filtre_colonne('a.[ref_modele]', 'WOI* !WOI9*')
    assert params == ['WOI%', 'WOI9%'] and 'NOT LIKE' in sql


# ── Clés ────────────────────────────────────────────────────────────────────

def test_cles():
    assert cle_nom('HM633GBS1/01', '') == 'HM633GBS1'
    assert cle_nom('HM633GBS1/01', 'HM 633 GBS1') == 'HM633GBS1'
    assert cle_nom('857700329500', '') == ''
    assert cle_code('857700329500', 'AKP003/IX') == '857700329500'
    assert cle_code('9440', '') == ''
    assert cle_code('', '944 188 357') == '944188357'


# ── Liste fermée et catalogue ───────────────────────────────────────────────

def test_types_autorises_versionnes():
    types = charger_types_autorises()
    assert len(types) == len(set(types)) >= 40
    assert TypesAppareils.FOUR_COMBINE_MICRO_ONDES in types
    assert 'Four vapeur' in types and 'Lave-vaisselle' in types
    assert CHEMIN_TYPES_AUTORISES.name == 'types_autorises.json'


def test_types_autorises_illisible(tmp_path):
    assert charger_types_autorises(tmp_path / 'absent.json') == ()
    (tmp_path / 'faux.json').write_text('{"types": "Four"}', encoding='utf-8')
    assert charger_types_autorises(tmp_path / 'faux.json') == ()


def test_catalogue_versionne_valide():
    lignes = lire_catalogue()
    assert CHEMIN_CATALOGUE.name == 'regles_nomenclature.csv'
    service = RegleNomenclatureService(db_manager=None)
    for ligne in lignes:
        assert service.controler_regle(ligne) == [], ligne
        assert ligne['statut'] == 'validee'
    cles = [(l['portee'], l['cible'], l['cle'], l['motif']) for l in lignes]
    assert len(cles) == len(set(cles))
    # Décision du lot 3 : pas de règle HMG8601… (homonymes laissés en Micro-ondes).
    # La zone grise Bauknecht EM* est levée par les doutes du § 9.3 (2026-11-24)
    motifs = {(l['cible'], l['motif']) for l in lignes}
    assert not any(m.startswith('HMG8') for _, m in motifs)
    assert not any(m.startswith('KMR') or m.startswith('KM4') for c, m in motifs if c == 'AEG')



# ── Doutes du § 9.3 tranchés (2026-11-24) ───────────────────────────────────

def test_doutes_hoover_hwc_cave_a_vin():
    index = _catalogue_index()
    assert _resoudre(index, 'Hoover', '', 'HWC 2336 DL').type == 'Cave à vin'
    assert _resoudre(index, 'Hoover', '', 'HWCA 2335').type == 'Cave à vin'
    # Le W de Hoover reste « lave-linge » : aucune règle HW*
    assert _resoudre(index, 'Hoover', '31006834', 'H3W 69TME').type == ''


def test_doutes_aeg_km_combine_mais_pas_les_micro_ondes():
    index = _catalogue_index()
    combine = TypesAppareils.FOUR_COMBINE_MICRO_ONDES
    assert _resoudre(index, 'AEG', '94427026400', 'KM9800E-M').type == combine
    assert _resoudre(index, 'AEG', '94427109300', 'KM7100000M').type == combine
    assert _resoudre(index, 'AEG', '94406648600', 'KMR721000B').type == ''
    assert _resoudre(index, 'AEG', '94406605500', 'KM4400001M').type == ''


def test_doutes_bauknecht_em_four_sans_toucher_les_micro_ondes():
    index = _catalogue_index()
    for nom in ('EMV6261/IN', 'EMVD7263/IN', 'EMC7253/IN', 'EMCK7145/IN', 'EMCE7263',
                'EME7463', 'EMIE6163IN', 'EMZD5266/WS'):
        assert _resoudre(index, 'Bauknecht', '', nom).type == 'Four', nom
    for nom in ('EMCCD8145', 'EMCHD8145', 'EMWD3', 'EMEK9', 'EMPK7'):
        assert _resoudre(index, 'Bauknecht', '', nom).type == '', nom


def test_doutes_whirlpool_akr0_par_numero_et_akr2_sans_regle():
    index = _catalogue_index()
    assert _resoudre(index, 'Whirlpool', '857800701000', 'AKR007/IX').type == 'Plaque'
    assert _resoudre(index, 'Whirlpool', '857802801000', 'AKR028/IX').type == 'Plaque'
    assert _resoudre(index, 'Whirlpool', '857802901000', 'AKR029IX').type == 'Hotte'
    assert _resoudre(index, 'Ignis', '857803001000', 'AKR030IX').type == 'Hotte'
    assert _resoudre(index, 'Whirlpool', '857804778000', 'AKR047WH').type == ''
    assert _resoudre(index, 'Whirlpool', '857821610000', 'AKR216/AV').type == ''


def test_doutes_whirlpool_amw_par_numeros():
    index = _catalogue_index()
    for nom in ('AMW 582 IX', 'AMW583IX', 'AMW 589', 'AMW 591 IXL', 'AMW 599', 'AMW 882'):
        assert _resoudre(index, 'Whirlpool', '', nom).type == 'Four vapeur', nom
    for nom in ('AMW 508', 'AMW 578', 'AMW 584', 'AMW 588', 'AMW 730', 'AMWR48'):
        assert _resoudre(index, 'Whirlpool', '', nom).type == 'Micro-ondes', nom

# ── Résolution : cas pièges du § 11 ─────────────────────────────────────────

def test_hm_combine_contre_ancienne_hm_cuisiniere():
    index = _catalogue_index()
    assert _resoudre(index, 'Siemens', 'HM633GBS1/01', 'HM633GBS1').type == \
        TypesAppareils.FOUR_COMBINE_MICRO_ONDES
    assert _resoudre(index, 'Siemens', 'HM10220EU/01', 'HM10220EU').type == ''


def test_akz_vapeur_contre_akz_four():
    index = _catalogue_index()
    assert _resoudre(index, 'Whirlpool', '859991544570', 'AKZ9S8270NB').type == 'Four vapeur'
    assert _resoudre(index, 'Whirlpool', '857941201500', 'AKZ513IX').type == 'Four'
    assert _resoudre(index, 'Whirlpool', '', 'AKZ9 6230 S').type == 'Four'   # S final = coloris


def test_awe_lave_linge_malgre_le_z():
    """Pas de règle « contient » : le Z de AWE8230ZEN ne compte pas."""
    index = _index([Regle('marque', 'Whirlpool', 'nom', 'AWE*', 'Lave-linge', 'validee'),
                    Regle('marque', 'Whirlpool', 'nom', 'AKZ*', 'Four', 'validee')])
    assert _resoudre(index, 'Whirlpool', '', 'AWE8230ZEN').type == 'Lave-linge'
    assert _resoudre(_catalogue_index(), 'Whirlpool', '', 'AWE8230ZEN').type == ''


def test_candy_lavante_mais_pas_hoover():
    index = _catalogue_index()
    assert _resoudre(index, 'Candy', '31007456', 'GO4W264').type == 'Lavante-séchante'
    assert _resoudre(index, 'Hoover', '31006834', 'H3W 69TME').type == ''


def test_la_plus_precise_gagne():
    index = _catalogue_index()
    assert _resoudre(index, 'Liebherr', '', 'GN 2153-20C 001').type == 'Congélateur'
    assert _resoudre(index, 'Liebherr', '', 'GKv 6410-23A').type == 'Réfrigérateur'
    assert _resoudre(index, 'Liebherr', '', 'GKN 230-21').type == 'Congélateur'
    assert _resoudre(index, 'Liebherr', '', 'GKN 400').type == 'Réfrigérateur'


def test_marque_avant_groupe():
    regles = [Regle('groupe', 'BSH', 'nom', 'SM*', 'Lave-vaisselle', 'validee'),
              Regle('marque', 'Neff', 'nom', 'SMX*', 'Four', 'validee'),
              Regle('marque', 'Siemens', 'nom', 'SM*', 'Lave-linge', 'rejetee')]
    index = _index(regles)
    assert _resoudre(index, 'Bosch', '', 'SMS46GI01E').type == 'Lave-vaisselle'
    assert _resoudre(index, 'Neff', '', 'SMX1234').type == 'Four'
    # Une règle de marque sur le même motif, même rejetée, retire la marque du groupe
    assert _resoudre(index, 'Siemens', '', 'SMS46GI01E').type == ''
    # Hors du groupe : rien
    assert _resoudre(index, 'Miele', '', 'SMS46GI01E').type == ''


def test_regles_proposees_ignorees():
    index = _index([Regle('marque', 'Bosch', 'nom', 'WA*', 'Lave-linge', 'proposee')])
    assert _resoudre(index, 'Bosch', '', 'WAT28400FF').type == ''


def test_conflit_entre_les_deux_cles():
    regles = [Regle('marque', 'Electrolux', 'nom', 'EW?F*', 'Lave-linge', 'validee'),
              Regle('marque', 'Electrolux', 'code', '914*', 'Sèche-linge', 'validee'),
              Regle('marque', 'Electrolux', 'code', '913*', 'Lave-linge', 'validee')]
    index = _index(regles)
    conflit = _resoudre(index, 'Electrolux', '914550123', 'EW6F428B')
    assert conflit.conflit and conflit.type == ''
    accord = _resoudre(index, 'Electrolux', '913550123', 'EW6F428B')
    assert accord.type == 'Lave-linge' and accord.deux_cles_d_accord


# ── Critère du lot 3 : les lots 1 et 2 ne bougent pas ───────────────────────

def _lots():
    for nom in ('nomenclature_lot1.csv', 'nomenclature_lot2.csv'):
        with (CORRECTIONS / nom).open(encoding='utf-8', newline='') as f:
            for ligne in csv.DictReader(f, delimiter=';'):
                yield nom, ligne


def test_catalogue_ne_propose_rien_sur_les_lots_1_et_2():
    index = _catalogue_index()
    contraires = []
    vus = Counter()
    for nom, l in _lots():
        vus[nom] += 1
        res = _resoudre(index, l['marque'], l['ref_modele'], l['ref_commerciale'])
        if res.type and res.type != l['nouveau_type']:
            contraires.append((l['id'], l['marque'], l['ref_commerciale'], res.type, l['nouveau_type']))
        assert not res.conflit
    assert vus == {'nomenclature_lot1.csv': 2512, 'nomenclature_lot2.csv': 6104}
    assert contraires == []


def test_catalogue_retrouve_la_liste_du_lot_2():
    """Les règles du combiné reproduisent la liste figée, sauf les 4 HMG8601/8621/
    8701/8721 (décision ponctuelle du lot 2, sans règle)."""
    index = _catalogue_index()
    sans_regle = [l['ref_commerciale'] for nom, l in _lots() if nom.endswith('lot2.csv')
                  and _resoudre(index, l['marque'], l['ref_modele'], l['ref_commerciale']).type
                  != TypesAppareils.FOUR_COMBINE_MICRO_ONDES]
    assert sorted(sans_regle) == ['HMG8601', 'HMG8621', 'HMG8701', 'HMG8721']


# ── Force ───────────────────────────────────────────────────────────────────

def test_force_des_propositions():
    assert sont_voisins('Four', 'Cuisinière') and not sont_voisins('Four', 'Plaque')
    assert force_proposition('Four', 'Cuisinière', True, 0.9, True) == FORCE_SIMPLE
    assert force_proposition('Four', 'Plaque', False, None, True) == FORCE_FORTE
    assert force_proposition('Lave-linge', 'Lave-vaisselle', False, 0.61, False) == FORCE_FORTE
    assert force_proposition('Lave-linge', 'Lave-vaisselle', False, 0.60, False) == FORCE_SIMPLE
    assert force_proposition('Lave-linge', 'Lave-vaisselle', True, None, False) == FORCE_FORTE


# ── Découverte ──────────────────────────────────────────────────────────────

def _app(ident, marque, type_app, ref):
    return ident, marque, type_app, cle_nom('', ref), cle_code(ref, '')


def test_decouverte_prefixe_pur_zone_grise_et_position():
    appareils, i = [], 0
    for n in range(40):                       # pur : AKP → Four
        i += 1; appareils.append(_app(i, 'Whirlpool', 'Four', f'AKP{n:03d}IX'))
    for n in range(40):                       # zone grise : moitié/moitié
        i += 1; appareils.append(_app(i, 'Whirlpool', 'Four' if n % 2 else 'Hotte', f'AKR{n:03d}'))
    for n in range(30):                       # deux sous-familles pures sous une zone grise
        i += 1; appareils.append(_app(i, 'Electrolux', 'Lave-linge', f'EW6F{n:03d}'))
    for n in range(30):
        i += 1; appareils.append(_app(i, 'Electrolux', 'Sèche-linge', f'EW6H{n:03d}'))
    for n in range(180):                      # 90 % : départagé par le 4e caractère
        i += 1; appareils.append(_app(i, 'Bosch', 'Lave-linge', f'WT{n % 10}F{n:03d}'))
    for n in range(20):
        i += 1; appareils.append(_app(i, 'Bosch', 'Sèche-linge', f'WT5H{n:03d}'))
    for n in range(30):                       # accessoires : ignorés
        i += 1; appareils.append(_app(i, 'Whirlpool', 'Accessoires', f'ACC{n:03d}'))
    regles, zones = decouvrir(appareils, groupe_de)
    marque = {(r.cible, r.motif): r for r in regles if r.portee == 'marque'}
    assert marque[('Whirlpool', 'AKP*')].type_resultat == 'Four'
    assert not any(m.startswith('AKR') for _, m in marque)
    assert any(z.prefixe == 'AKR' and z.cible == 'Whirlpool' for z in zones)
    # « AK » mélangé (Four 75 %) n'empêche pas « AKP » pur, mais la règle le signale
    assert any(z.prefixe == 'AK' for z in zones)
    assert marque[('Whirlpool', 'AKP*')].zone_grise == 'AK'
    assert not any(r.type_resultat in TypesAppareils.ACCESSOIRES for r in regles)
    assert not any(m.startswith('ACC') for _, m in marque)
    assert marque[('Electrolux', 'EW6F*')].type_resultat == 'Lave-linge'
    assert marque[('Electrolux', 'EW6H*')].type_resultat == 'Sèche-linge'
    assert marque[('Bosch', 'WT?F*')].type_resultat == 'Lave-linge'
    assert marque[('Bosch', 'WT?H*')].type_resultat == 'Sèche-linge'


def test_decouverte_validation_croisee():
    """Une pureté obtenue sur une seule moitié des identifiants ne suffit pas."""
    appareils = [_app(i, 'Bosch', 'Four' if i % 2 else 'Lave-linge', f'XY{i:04d}')
                 for i in range(1, 61)]
    # 60 « XY » : 50 % — zone grise, aucune règle
    regles, _ = decouvrir(appareils, groupe_de)
    assert not [r for r in regles if r.motif.startswith('XY')]


def test_decouverte_charge_720000_appareils():
    """Découverte complète < 30 s sur 720 000 appareils (CDC § 11)."""
    rnd = random.Random(7)
    marques = ['Bosch', 'Siemens', 'Whirlpool', 'Electrolux', 'Candy', 'Beko', 'Liebherr', 'Miele']
    types = ['Four', 'Lave-linge', 'Lave-vaisselle', 'Réfrigérateur', 'Sèche-linge', 'Hotte']
    lettres = 'ABCDEFGHJKLMNPRSTVWXZ'
    appareils = []
    for i in range(720_000):
        marque = marques[i % len(marques)]
        prefixe = lettres[rnd.randrange(len(lettres))] + lettres[rnd.randrange(len(lettres))]
        type_app = types[hash((marque, prefixe)) % len(types)] if rnd.random() < 0.97 else rnd.choice(types)
        ref = f'{prefixe}{rnd.randrange(100, 999)}{lettres[rnd.randrange(len(lettres))]}{rnd.randrange(10)}'
        code = str(rnd.randrange(10 ** 8, 10 ** 9)) if i % 3 == 0 else ''
        appareils.append((i, marque, type_app, ref, code))
    debut = time.perf_counter()
    regles, _ = decouvrir(appareils, groupe_de)
    duree = time.perf_counter() - debut
    assert regles
    assert duree < 30, f"découverte en {duree:.1f} s"


# ── Service sur une base ────────────────────────────────────────────────────

@pytest.fixture
def base(tmp_path):
    chemin = tmp_path / 'test.db'
    db = DatabaseManager(str(chemin))
    cnx = sqlite3.connect(str(chemin))
    appareils = [
        (1, 'Four', 'Gaggenau', 'BS270100/01', 'BS270100', 'COMBIVAP'),         # → Four vapeur
        (2, 'Four vapeur', 'Gaggenau', 'BS450110/01', 'BS450110', ''),           # déjà juste
        (3, 'Four', 'Whirlpool', '857331012000', 'AKR331IX', 'Plaque Email Gaz'),  # → Plaque (forte)
        (4, 'Lave-linge', 'Candy', '31007456', 'GVW 285TC-12', ''),              # → refusé
        (5, 'Accessoires', 'Gaggenau', 'BS999/01', 'BS999', ''),                 # accessoire : ignoré
        (6, 'Cuisinière', 'Siemens', 'HM10220EU/01', 'HM10220EU', ''),           # aucune règle
        (7, 'Four', 'Gaggenau', 'BSP220100/01', 'BSP220100', ''),                # → Four vapeur
        (8, 'Four', 'Gaggenau', 'BS270100/02', 'BS270100', ''),                  # → Four vapeur
    ]
    cnx.executemany("INSERT INTO appareils(id, type, manufacturer, ref_modele, commercial_ref, "
                    "other_ref) VALUES (?, ?, ?, ?, ?, ?)", appareils)
    cnx.execute("INSERT INTO pieces(id, ref_piece) VALUES (1, 'P1')")
    cnx.executemany("INSERT INTO piece_associations(piece_id, appareil_id) VALUES (1, ?)",
                    [(1,), (2,), (7,)])
    cnx.execute("INSERT INTO refus_completions(appareil_id, champ, valeur, refuse_le) "
                "VALUES (4, 'type', 'lavante-séchante', '2026-11-23')")
    cnx.commit()
    cnx.close()
    yield db
    db.close()


def _types(db):
    return dict(db.execute_query("SELECT id, type FROM appareils"))


def test_tables_creees_et_idempotentes(base):
    base._setup_nomenclature_tables()
    tables = {r[0] for r in base.execute_query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'regles_nomenclature', 'propositions_type'} <= tables


def test_controle_a_l_enregistrement(base):
    service = RegleNomenclatureService(base)
    ok = {'portee': 'marque', 'cible': 'Bosch', 'cle': 'nom', 'motif': 'WA*',
          'type_resultat': 'Lave-linge', 'statut': 'validee', 'origine': 'saisie'}
    mauvaises = [
        dict(ok, type_resultat='Lave linge'),          # hors liste
        dict(ok, type_resultat='Accessoires'),         # accessoire (D9)
        dict(ok, portee='groupe', cible='Inconnu'),    # groupe inconnu
        dict(ok, motif='W*A'),                         # motif invalide
        dict(ok, cle='code', motif='94@*'),            # lettre dans une clé code
        dict(ok, statut='peut-etre'),
    ]
    bilan = service.enregistrer_regles([ok] + mauvaises)
    assert bilan.ajoutees == 1 and len(bilan.refusees) == len(mauvaises)
    # Rejouer : rien n'est écrasé
    assert service.enregistrer_regles([dict(ok, type_resultat='Lave-vaisselle')]).ajoutees == 0
    regle = base.lister_regles_nomenclature()[0]
    assert regle['type_resultat'] == 'Lave-linge' and regle['forme'] == 'prefixe'
    assert regle['valide_le']


def test_catalogue_idempotent(base):
    service = RegleNomenclatureService(base)
    simulation = service.charger_catalogue(ecrire=False)
    assert simulation.ajoutees == simulation.lues and not base.lister_regles_nomenclature()
    premier = service.charger_catalogue()
    assert premier.ajoutees == premier.lues and not premier.refusees
    second = service.charger_catalogue()
    assert second.ajoutees == 0 and second.deja_presentes == second.lues


def test_propositions_sans_toucher_aux_types(base):
    service = RegleNomenclatureService(base)
    service.charger_catalogue()
    avant = _types(base)
    simulation = service.calculer_propositions(ecrire=False)
    assert not base.lire_propositions_type()
    bilan = service.calculer_propositions(ecrire=True)
    assert bilan.ecrit and not bilan.erreur
    assert _types(base) == avant                       # aucun type écrit
    props = {p['appareil_id']: p for p in base.lire_propositions_type()}
    assert set(props) == set(simulation.propositions) == {1, 3, 7, 8}
    assert props[1]['type_propose'] == 'Four vapeur' and props[1]['force'] == FORCE_SIMPLE
    assert props[3]['type_propose'] == 'Plaque' and props[3]['force'] == FORCE_FORTE
    assert json.loads(props[3]['signaux'])['libelle'] is True
    assert bilan.refusees == 1                         # Candy GVW : refus mémorisé
    # Vote des pièces : l'appareil 7 partage P1 avec 1 (Four) et 2 (Four vapeur)
    assert json.loads(props[7]['signaux'])['vote_pieces'] == 0.5
    # Mesures de la règle Gaggenau BS* (accessoire exclu)
    regle_bs = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'BS*')
    assert (regle_bs['couverture'], regle_bs['accord']) == (4, 1)
    # Un nouveau calcul remplace, ne cumule pas
    service.calculer_propositions(ecrire=True)
    assert len(base.lire_propositions_type()) == 4


def _executer(db, sql, params=()):
    cnx = sqlite3.connect(db.db_file)
    cnx.execute(sql, params)
    cnx.commit()
    cnx.close()


def test_suppressions_en_cascade(base):
    service = RegleNomenclatureService(base)
    service.charger_catalogue()
    service.calculer_propositions(ecrire=True)
    _executer(base, "DELETE FROM appareils WHERE id = 1")
    assert 1 not in {p['appareil_id'] for p in base.lire_propositions_type()}
    regle_akr = next(r for r in base.lister_regles_nomenclature() if r['motif'] == 'AKR3*')
    _executer(base, "DELETE FROM regles_nomenclature WHERE id = ?", (regle_akr['id'],))
    assert 3 not in {p['appareil_id'] for p in base.lire_propositions_type()}


def test_decouverte_rangee_en_proposee(base):
    service = RegleNomenclatureService(base)
    cnx = sqlite3.connect(base.db_file)
    cnx.executemany("INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) "
                    "VALUES ('Lave-linge', 'Bosch', ?, ?)",
                    [(f'WAT{n:04d}/01', f'WAT{n:04d}') for n in range(40)])
    cnx.commit()
    cnx.close()
    simulation = service.decouvrir_regles(ecrire=False)
    assert simulation.nouvelles and not base.lister_regles_nomenclature()
    bilan = service.decouvrir_regles(ecrire=True)
    regles = base.lister_regles_nomenclature()
    assert bilan.ajoutees == len(regles) > 0
    assert {r['statut'] for r in regles} == {'proposee'}
    assert {r['origine'] for r in regles} == {'decouverte'}
    # Proposées : elles ne typent rien
    assert not service.calculer_propositions().propositions


def test_script_simulation_n_ecrit_rien(base, tmp_path):
    chemin = base.db_file
    base.close()
    for commande in ('catalogue', 'proposer', 'decouvrir'):
        sortie = subprocess.run(
            [sys.executable, str(RACINE / 'scripts' / 'regles_nomenclature.py'), commande,
             '--base', str(chemin)], capture_output=True, text=True, cwd=str(RACINE))
        assert sortie.returncode == 0, sortie.stdout + sortie.stderr
        assert 'Simulation' in sortie.stdout or commande == 'catalogue'
    cnx = sqlite3.connect(str(chemin))
    assert cnx.execute("SELECT COUNT(*) FROM regles_nomenclature").fetchone()[0] == 0
    assert cnx.execute("SELECT COUNT(*) FROM propositions_type").fetchone()[0] == 0
    cnx.close()
