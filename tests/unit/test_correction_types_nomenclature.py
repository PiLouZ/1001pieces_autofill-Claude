"""
Corrections de type en lot — règles de nomenclature, lot 1 (CDC § 9.1).

- liste figée : lecture contrôlée (en-tête, doublons, types), et la liste
  versionnée correspond exactement à ce que le client a validé (2 512 lignes) ;
- préparation : rien n'est écrit, chaque ligne est classée ;
- garde : un appareil dont le type a changé depuis la liste n'est pas écrasé ;
- exécution : types écrits, comptage par type conforme, une ligne d'historique
  par appareil au format d'une modification de Type à la main ;
- retour arrière : même liste à l'envers, rejouable sans effet ;
- fenêtre présente : l'écriture passe par la sauvegarde événementielle ;
- panneau d'historique : entrées regroupées sans perdre leur provenance ;
- script : simulation sans écriture, écriture avec sauvegarde à côté de la base.
"""

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data.database_manager import DatabaseManager
from src.services.correction_types_service import (
    ENTETES, SENS_ANNULER, CorrectionType, CorrectionTypesService, lire_liste)

RACINE = Path(__file__).resolve().parents[2]
LISTE_LOT1 = RACINE / 'data' / 'corrections' / 'nomenclature_lot1.csv'


def _csv(chemin, lignes, entete=ENTETES):
    contenu = [';'.join(entete)] + [';'.join(str(x) for x in l) for l in lignes]
    chemin.write_text('\n'.join(contenu) + '\n', encoding='utf-8')
    return chemin


@pytest.fixture
def base(tmp_path):
    """Base neuve : 5 appareils, dont 3 visés par la liste."""
    db = DatabaseManager(str(tmp_path / 'test.db'))
    cnx = sqlite3.connect(str(tmp_path / 'test.db'))
    appareils = [
        (1, 'Four vapeur', 'Whirlpool', '857700329500', 'AKP003/IX'),
        (2, 'Four', 'Bosch', 'HSG636BB1/01', 'HSG636BB1'),
        (3, 'Lave-linge', 'Haier', '32901926', 'XS 4A4M4BB-80'),
        (4, 'Four', 'Bosch', 'HBG635BS1/01', 'HBG635BS1'),       # hors liste
        (5, 'Cuisinière', 'Bosch', 'HSG122020E/01', 'HSG122020E'),  # hors liste
    ]
    cnx.executemany("INSERT INTO appareils(id, type, manufacturer, ref_modele, commercial_ref, "
                    "updated_at) VALUES (?, ?, ?, ?, ?, '2026-01-01 00:00:00')", appareils)
    cnx.commit()
    cnx.close()
    yield db
    db.close()


@pytest.fixture
def liste(tmp_path):
    return _csv(tmp_path / 'lot.csv', [
        (1, 1, 'Whirlpool', '857700329500', 'AKP003/IX', 'Four Vapeur', 'Four vapeur', 'Four'),
        (3, 2, 'Bosch', 'HSG636BB1/01', 'HSG636BB1', '', 'Four', 'Four vapeur'),
        (4, 3, 'Haier', '32901926', 'XS 4A4M4BB-80', 'XS 4A4M4BB-80', 'Lave-linge', 'Lave-vaisselle'),
    ])


def _types(db):
    return dict(db.execute_query("SELECT id, type FROM appareils"))


def _historique(db):
    return db.execute_query("SELECT action_type, title, details, device_ref, field_name, "
                            "old_value, new_value FROM modifications_history ORDER BY id")


# ---------------------------------------------------------------------------
# Liste figée
# ---------------------------------------------------------------------------
class TestLireListe:
    def test_lecture(self, liste):
        corrections = lire_liste(liste)
        assert [c.appareil_id for c in corrections] == [1, 2, 3]
        assert corrections[0] == CorrectionType('1', 1, 'Whirlpool', '857700329500', 'AKP003/IX',
                                                'Four vapeur', 'Four')

    @pytest.mark.parametrize('lignes, message', [
        ([(1, 'x', 'M', 'r', 'c', '', 'Four', 'Hotte')], 'identifiant'),
        ([(1, 7, 'M', 'r', 'c', '', 'Four', '')], 'type vide'),
        ([(1, 7, 'M', 'r', 'c', '', 'Four', 'Four')], 'inchangé'),
        ([(1, 7, 'M', 'r', 'c', '', 'Four', 'Hotte'), (1, 7, 'M', 'r', 'c', '', 'Four', 'Hotte')], 'double'),
        ([(1, 7, 'M', 'r', 'c', 'Four', 'Hotte')], 'colonnes'),
    ])
    def test_refus(self, tmp_path, lignes, message):
        with pytest.raises(ValueError, match=message):
            lire_liste(_csv(tmp_path / 'l.csv', lignes))

    def test_entete_inattendu(self, tmp_path):
        with pytest.raises(ValueError, match='en-tête'):
            lire_liste(_csv(tmp_path / 'l.csv', [], entete=('id', 'type')))

    def test_liste_lot1_validee_par_le_client(self):
        """La liste versionnée est celle relue famille par famille le 2026-11-23."""
        corrections = lire_liste(LISTE_LOT1)
        assert len(corrections) == 2512
        assert Counter(c.famille for c in corrections) == Counter({
            '1': 1891, '3': 550, '10': 46, '4': 8, '2': 5, '6': 3,
            '5': 2, '7': 2, '8': 2, '11': 2, '9': 1})
        assert Counter((c.type_avant, c.type_apres) for c in corrections) == Counter({
            ('Four vapeur', 'Four'): 1891, ('Four', 'Four vapeur'): 599,
            ('Lave-linge', 'Lave-vaisselle'): 8, ('Lave-linge', 'Sèche-linge'): 4,
            ('Réfrigérateur', 'Sèche-linge'): 3, ('Lave-linge', 'Réfrigérateur'): 2,
            ('Four', 'Cuisinière'): 2, ('Four', 'Micro-ondes'): 2, ('Four', 'Hotte'): 1})
        # Pièges tranchés : vrais fours vapeur AKZ9S hors famille 1, « S » final = coloris
        f1 = [c for c in corrections if c.famille == '1']
        assert not any(c.ref_commerciale.replace(' ', '').upper().startswith('AKZ9S') for c in f1)
        assert any(c.ref_commerciale == 'AKZ9 6230 S' for c in f1)


# ---------------------------------------------------------------------------
# Préparation, exécution, garde, retour arrière
# ---------------------------------------------------------------------------
class TestCorrection:
    def test_preparer_n_ecrit_rien(self, base, liste):
        avant = _types(base)
        bilan = CorrectionTypesService(base).preparer(lire_liste(liste))
        assert [c.appareil_id for c in bilan.a_corriger] == [1, 2, 3]
        assert not bilan.ignorees and not bilan.deja_faites
        assert _types(base) == avant
        assert _historique(base) == []
        # Four vapeur → Four puis Four → Four vapeur : s'annulent
        assert bilan.ecart_attendu() == {'Lave-linge': -1, 'Lave-vaisselle': 1}

    def test_executer(self, base, liste):
        bilan = CorrectionTypesService(base).executer(lire_liste(liste), provenance='règles de nomenclature, lot1')
        assert bilan.ecrit and bilan.historique_ecrit and bilan.comptage_conforme
        types = _types(base)
        assert types == {1: 'Four', 2: 'Four vapeur', 3: 'Lave-vaisselle', 4: 'Four', 5: 'Cuisinière'}
        # Hors liste : pas touchés (date de modification intacte)
        intacts = dict(base.execute_query("SELECT id, updated_at FROM appareils WHERE id IN (4, 5)"))
        assert set(intacts.values()) == {'2026-01-01 00:00:00'}

        histo = _historique(base)
        assert len(histo) == 3
        action, titre, details, appareil, champ, ancien, nouveau = histo[0]
        assert (action, champ, ancien, nouveau) == ('edit', 'Type', 'Four vapeur', 'Four')
        assert titre == "[Type]  'Four vapeur' → 'Four'"
        assert appareil == '857700329500 - AKP003/IX'
        assert json.loads(details) == ['(source : règles de nomenclature, lot1)']
        # Même provenance partout (regroupement ×N du panneau)
        assert len({h[2] for h in histo}) == 1

    def test_garde_type_change_depuis_la_liste(self, base, liste):
        base.update_multiple_cells_batch({2: {'type': 'Cuisinière'}})   # décision plus récente
        base.execute_write("DELETE FROM appareils WHERE id = 3")
        bilan = CorrectionTypesService(base).executer(lire_liste(liste))
        assert [c.appareil_id for c in bilan.a_corriger] == [1]
        assert {(c.appareil_id, t) for c, t in bilan.ignorees} == {(2, 'Cuisinière'), (3, None)}
        assert _types(base)[2] == 'Cuisinière'
        assert bilan.comptage_conforme
        assert len(_historique(base)) == 1

    def test_rejouer_ne_fait_rien(self, base, liste):
        service = CorrectionTypesService(base)
        service.executer(lire_liste(liste))
        bilan = service.executer(lire_liste(liste))
        assert not bilan.a_corriger and len(bilan.deja_faites) == 3
        assert not bilan.ecrit and len(_historique(base)) == 3

    def test_retour_arriere(self, base, liste):
        service = CorrectionTypesService(base)
        avant = _types(base)
        comptage = service.comptage_par_type()
        service.executer(lire_liste(liste))
        bilan = service.executer(lire_liste(liste), SENS_ANNULER)
        assert bilan.comptage_conforme
        assert _types(base) == avant
        assert service.comptage_par_type() == comptage
        histo = _historique(base)
        assert len(histo) == 6
        assert histo[3][1] == "[Type]  'Four' → 'Four vapeur'"
        assert json.loads(histo[3][2])[0].endswith('— retour arrière)')
        # Annuler deux fois : rien
        assert not service.executer(lire_liste(liste), SENS_ANNULER).a_corriger

    def test_retour_arriere_respecte_la_garde(self, base, liste):
        service = CorrectionTypesService(base)
        service.executer(lire_liste(liste))
        base.update_multiple_cells_batch({1: {'type': 'Four vapeur'}})  # repris à la main
        bilan = service.preparer(lire_liste(liste), SENS_ANNULER)
        assert 1 in {c.appareil_id for c in bilan.deja_faites}

    def test_sens_inconnu(self, base, liste):
        with pytest.raises(ValueError):
            CorrectionTypesService(base).preparer(lire_liste(liste), 'effacer')

    def test_fenetre_passe_par_la_sauvegarde_evenementielle(self, base, liste):
        fenetre = MagicMock()
        fenetre.event_driven_save_service.enregistrer_champs_appareils.side_effect = \
            lambda maj: base.update_multiple_cells_batch(maj)
        bilan = CorrectionTypesService(base, parent_window=fenetre).executer(lire_liste(liste))
        fenetre.event_driven_save_service.enregistrer_champs_appareils.assert_called_once_with(
            {1: {'type': 'Four'}, 2: {'type': 'Four vapeur'}, 3: {'type': 'Lave-vaisselle'}})
        assert bilan.comptage_conforme

    def test_echec_d_ecriture(self, base, liste):
        fenetre = MagicMock()
        fenetre.event_driven_save_service.enregistrer_champs_appareils.return_value = False
        bilan = CorrectionTypesService(base, parent_window=fenetre).executer(lire_liste(liste))
        assert not bilan.ecrit and not bilan.historique_ecrit
        assert _historique(base) == []


# ---------------------------------------------------------------------------
# Panneau d'historique de la fenêtre principale
# ---------------------------------------------------------------------------
def test_panneau_historique_regroupe_sans_perdre_la_provenance(base, liste):
    from src.ui.user_interaction_service import _entree_depuis_base, _inserer_entree
    CorrectionTypesService(base).executer(lire_liste(liste), provenance='règles de nomenclature, lot1')
    # Deux appareils de plus vers « Four » : regroupés ×N
    base.update_multiple_cells_batch({4: {'type': 'Four vapeur'}, 5: {'type': 'Four vapeur'}})
    autres = [CorrectionType('1', 4, 'Bosch', '', '', 'Four vapeur', 'Four'),
              CorrectionType('1', 5, 'Bosch', '', '', 'Four vapeur', 'Four')]
    CorrectionTypesService(base).executer(autres, provenance='règles de nomenclature, lot1')
    entrees = []
    for ligne in reversed(base.historique_recent(100)):
        e = _entree_depuis_base(ligne)
        assert e is not None
        _inserer_entree(entrees, e)
    groupe = entrees[0]
    assert groupe['count'] == 2 and groupe['title'] == "[Type]  'Four vapeur' → 'Four'"
    assert groupe['details'] == ['(source : règles de nomenclature, lot1)']


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------
def _lancer_script(monkeypatch, *args):
    sys.path.insert(0, str(RACINE / 'scripts'))
    import corriger_types_nomenclature as script
    monkeypatch.setattr(sys, 'argv', ['corriger_types_nomenclature.py', *args])
    return script.main()


def test_script_simulation_puis_ecriture(base, liste, monkeypatch, tmp_path, capsys):
    chemin = base.db_file
    avant = _types(base)
    assert _lancer_script(monkeypatch, '--liste', str(liste), '--base', chemin) == 0
    assert 'rien n\'a été écrit' in capsys.readouterr().out
    assert _types(base) == avant

    assert _lancer_script(monkeypatch, '--liste', str(liste), '--base', chemin, '--ecrire', '--oui') == 0
    sortie = capsys.readouterr().out
    assert 'conforme' in sortie
    assert list((Path(chemin).parent / 'backups').glob('*nomenclature_lot*'))
    assert _types(base)[3] == 'Lave-vaisselle'

    assert _lancer_script(monkeypatch, '--liste', str(liste), '--base', chemin,
                          '--annuler', '--ecrire', '--oui') == 0
    assert _types(base) == avant


def test_script_liste_illisible(monkeypatch, tmp_path, base):
    mauvaise = _csv(tmp_path / 'm.csv', [], entete=('a',))
    assert _lancer_script(monkeypatch, '--liste', str(mauvaise), '--base', base.db_file) == 1
