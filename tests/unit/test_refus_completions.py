"""
Tests — Refus mémorisés (v3.94.0)

- `refus_completions` : une paire Type/Marque refusée dans « Valider les
  suggestions » n'est plus proposée (import, clic droit, scan global) ;
- un champ auto-complété refusé dans « Auto-complétés à vérifier » est vidé, et
  l'import ne le réécrit plus sur cet appareil — sauf si le fichier lui-même
  porte la valeur ;
- le refus disparaît avec l'appareil.
"""

import types

import pytest

from src.core.import_manager import ImportManager
from src.services.reference_similarity_service import (
    CHAMP_PAIRE, cle_paire, retirer_candidats_refuses,
)
from src.ui.main_refactored import MainWindow


@pytest.fixture
def manager(test_db_manager):
    return ImportManager(db_manager=test_db_manager, parent_widget=None)


def _appareil(manager, ref, type_='', marque=''):
    (appareil_id,) = manager._batch_insert_devices([{
        'type': type_, 'manufacturer': marque, 'ref_modele': ref, 'commercial_ref': '',
        'other_ref': '', 'notes': '', 'category': ''}])
    return appareil_id


# ── Base ──────────────────────────────────────────────────────────────────────

class TestTable:

    def test_enregistrer_et_lire(self, manager):
        db = manager.db_manager
        a = _appareil(manager, 'ZQR1')
        assert db.enregistrer_refus([(a, 'paire', 'Four|BOSCH'), (a, 'type', ' Four '),
                                     (a, 'type', '')]) == 2      # valeur vide ignorée
        assert db.lire_refus([a, 999999]) == {(a, 'paire', 'four|bosch'), (a, 'type', 'four')}

    def test_idempotent(self, manager):
        db = manager.db_manager
        a = _appareil(manager, 'ZQR1')
        db.enregistrer_refus([(a, 'type', 'Four')])
        db.enregistrer_refus([(a, 'type', 'FOUR')])
        assert db.lire_refus([a]) == {(a, 'type', 'four')}

    def test_disparait_avec_l_appareil(self, manager):
        db = manager.db_manager
        a = _appareil(manager, 'ZQR1')
        db.enregistrer_refus([(a, 'type', 'Four')])
        db.get_connection().execute("DELETE FROM appareils WHERE id = ?", (a,))
        assert db.lire_refus([a]) == set()


# ── Suggestions ───────────────────────────────────────────────────────────────

class TestSuggestionsRefusees:

    FOUR_BOSCH = {'type': 'Four', 'manufacturer': 'Bosch'}
    FOUR_SEUL = {'type': 'Four', 'manufacturer': ''}

    def test_cle_paire(self):
        assert cle_paire({'type': ' Four ', 'manufacturer': 'BOSCH'}) == "four|bosch"
        assert cle_paire(self.FOUR_SEUL) == "four|"

    def test_retirer(self):
        suggestions = {1: [self.FOUR_BOSCH, self.FOUR_SEUL], 2: [self.FOUR_BOSCH]}
        refus = {(1, CHAMP_PAIRE, 'four|bosch'), (2, CHAMP_PAIRE, 'four|bosch')}
        assert retirer_candidats_refuses(suggestions, refus) == {1: [self.FOUR_SEUL]}
        assert retirer_candidats_refuses(suggestions, set()) is suggestions

    def test_filtre_de_la_fenetre_principale(self, manager):
        a = _appareil(manager, 'ZQR1')
        manager.db_manager.enregistrer_refus([(a, CHAMP_PAIRE, 'four|bosch')])
        fenetre = types.SimpleNamespace(db_manager=manager.db_manager)
        assert MainWindow._filtrer_suggestions_refusees(
            fenetre, {a: [self.FOUR_BOSCH], a + 1: [self.FOUR_BOSCH]}) == {a + 1: [self.FOUR_BOSCH]}

    def test_lecture_echouee_rien_n_est_retire(self):
        fenetre = types.SimpleNamespace(db_manager=types.SimpleNamespace(lire_refus=lambda ids: None))
        found = {1: [self.FOUR_BOSCH]}
        assert MainWindow._filtrer_suggestions_refusees(fenetre, found) == found

    def test_refuser_memorise_toutes_les_paires_de_la_ligne(self, manager):
        historique, dissipees = [], []
        fenetre = types.SimpleNamespace(
            db_manager=manager.db_manager,
            table_controller=types.SimpleNamespace(
                clear_similarity_suggestion=dissipees.append,
                _update_similarity_indicator=lambda: None),
            user_interaction_service=types.SimpleNamespace(add_to_history=historique.append))
        a = _appareil(manager, 'ZQR1')
        assert MainWindow._refuser_suggestions(fenetre, [(a, [self.FOUR_BOSCH, self.FOUR_SEUL])]) == 1
        assert manager.db_manager.lire_refus([a]) == {
            (a, CHAMP_PAIRE, 'four|bosch'), (a, CHAMP_PAIRE, 'four|')}
        assert dissipees == [a]
        assert historique == ["Suggestions refusées : 1 appareil — elle ne sera plus proposée."]


# ── Auto-complétions ──────────────────────────────────────────────────────────

class TestAutocompletionsRefusees:

    def _completion(self, manager, appareil_id, auto=True):
        donnees = {'ref_modele': 'ZQR1', 'commercial_ref': '', 'type': 'Four'}
        if auto:
            manager._noter_autocompletion(donnees, 'type', 'Four', 'S1', 1, 1)
        return [(appareil_id, donnees, {'type': 'Four'})]

    def _type(self, manager, appareil_id):
        return manager.db_manager.execute_query(
            "SELECT COALESCE(type, '') FROM appareils WHERE id = ?", [appareil_id])[0][0]

    def test_sans_refus_le_champ_vide_est_complete(self, manager):
        a = _appareil(manager, 'ZQR1')
        assert manager._completer_appareils_existants(self._completion(manager, a)) == 1
        assert self._type(manager, a) == 'Four'

    def test_auto_completion_refusee_non_reecrite(self, manager):
        a = _appareil(manager, 'ZQR1')
        manager.db_manager.enregistrer_refus([(a, 'type', 'four')])
        assert manager._completer_appareils_existants(self._completion(manager, a)) == 0
        assert self._type(manager, a) == ''

    def test_valeur_du_fichier_ecrite_malgre_le_refus(self, manager):
        """Le refus vise l'auto-complétion, pas la donnée du fournisseur."""
        a = _appareil(manager, 'ZQR1')
        manager.db_manager.enregistrer_refus([(a, 'type', 'four')])
        assert manager._completer_appareils_existants(self._completion(manager, a, auto=False)) == 1
        assert self._type(manager, a) == 'Four'

    def test_refuser_vide_et_memorise(self, manager):
        historique, appliquees, rafraichi = [], [], []
        fenetre = types.SimpleNamespace(
            db_manager=manager.db_manager,
            _apply_suggestion_decisions=lambda d: appliquees.extend(d) or len(d),
            _rafraichir_bouton_autocompletes=lambda: rafraichi.append(1),
            user_interaction_service=types.SimpleNamespace(add_to_history=historique.append))
        a = _appareil(manager, 'ZQR1', 'Four', 'Bosch')
        MainWindow._refuser_autocompletions(fenetre, [(a, {'type': 'Four', 'manufacturer': 'Bosch'})])
        assert manager.db_manager.lire_refus([a]) == {(a, 'type', 'four'), (a, 'manufacturer', 'bosch')}
        assert appliquees == [(a, {'vider': ['type', 'manufacturer'],
                                   'provenance': "refus d'auto-complétion"})]
        assert rafraichi == [1] and "champ vidé" in historique[0]
