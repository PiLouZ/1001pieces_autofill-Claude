"""
Tests — Trois paires de code dupliqué factorisées

Le graphe de code signalait sept paires de méthodes quasi identiques. Après
relecture, trois seulement méritaient d'être factorisées :

- `mark_obsolete` / `unmark_obsolete` — identiques sauf la valeur écrite ;
- `handle_database_operation_errors` / `handle_ui_operation_errors` — identiques
  sauf le préfixe de log et un mot du message de debug ;
- les quatre handlers de dialogue d'import (`accepted` et `rejected`, chemins
  fichier et drag&drop) — identiques sauf la valeur de `source`.

Les quatre autres paires ont été écartées : deux sont des handlers Qt parallèles
légitimes, et `_setup_config_menu` / `_setup_data_menu` avait un score de
similarité de 1,000 pour **une seule ligne commune sur 58** — le Jaccard mesure
la forme, pas le texte.

Ces tests fixent le comportement observable des trois socles communs.
"""

import io
import logging
import pytest

from src.core.logger import app_logger
from src.utils.error_handler import (
    handle_database_operation_errors, handle_ui_operation_errors,
)


@pytest.fixture
def messages_log():
    """Capture les messages du logger applicatif.

    On n'utilise pas `caplog` : le projet journalise via son propre logger
    (`app_logger.logger`), et la fixture pytest dépend d'un plugin que la suite
    désactive parfois. Un handler explicite fonctionne dans tous les cas.
    """
    tampon = io.StringIO()
    handler = logging.StreamHandler(tampon)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(message)s'))
    niveau_origine = app_logger.logger.level
    app_logger.logger.addHandler(handler)
    app_logger.logger.setLevel(logging.DEBUG)
    try:
        yield lambda: tampon.getvalue().splitlines()
    finally:
        app_logger.logger.removeHandler(handler)
        app_logger.logger.setLevel(niveau_origine)


# ─── Paire 1 : marqueur d'obsolescence ───────────────────────────────────────

class TestObsolescence:

    @pytest.fixture
    def piece(self, test_db_manager):
        test_db_manager.create_piece_standalone('REF_OBS', 'Une pièce')
        return test_db_manager

    def _est_obsolete(self, db, ref='REF_OBS'):
        lignes = db.execute_query(
            "SELECT COALESCE(is_obsolete, 0) FROM pieces WHERE ref_piece = ?", [ref])
        return bool(lignes[0][0]) if lignes else None

    def test_marquer(self, piece):
        assert piece.mark_obsolete('REF_OBS') is True
        assert self._est_obsolete(piece) is True

    def test_demarquer(self, piece):
        piece.mark_obsolete('REF_OBS')
        assert piece.unmark_obsolete('REF_OBS') is True
        assert self._est_obsolete(piece) is False

    def test_idempotence(self, piece):
        assert piece.mark_obsolete('REF_OBS') is True
        assert piece.mark_obsolete('REF_OBS') is True
        assert self._est_obsolete(piece) is True

    def test_reference_inexistante_ne_leve_pas(self, piece):
        """Aucune ligne touchée, mais l'opération reste un succès — comme avant."""
        assert piece.mark_obsolete('REF_ABSENTE') is True

    def test_le_message_d_erreur_nomme_l_appelant(self, piece, monkeypatch, messages_log):
        """Le socle commun reçoit le nom de l'appelant : les messages d'erreur
        restent aussi précis qu'avec les deux méthodes séparées."""
        class CurseurCasse:
            # sqlite3.Cursor.execute est en lecture seule : on substitue l'objet entier
            def execute(self, *a, **k):
                raise RuntimeError('base indisponible')
        monkeypatch.setattr(piece, 'cursor', CurseurCasse())

        assert piece.unmark_obsolete('REF_OBS') is False
        messages = messages_log()
        assert any('unmark_obsolete' in m for m in messages), messages


# ─── Paire 2 : les deux décorateurs ──────────────────────────────────────────

class TestDecorateurs:

    class Cobaye:
        @handle_database_operation_errors(return_value='repli_db')
        def echoue_db(self):
            raise ValueError('boum')

        @handle_ui_operation_errors(return_value='repli_ui')
        def echoue_ui(self):
            raise ValueError('boum')

        @handle_database_operation_errors(return_value='jamais')
        def reussit(self):
            return 'valeur'

    def test_valeur_de_repli_db(self):
        assert self.Cobaye().echoue_db() == 'repli_db'

    def test_valeur_de_repli_ui(self):
        assert self.Cobaye().echoue_ui() == 'repli_ui'

    def test_le_succes_passe_a_travers(self):
        assert self.Cobaye().reussit() == 'valeur'

    def test_les_messages_restent_distincts(self, messages_log):
        """Le socle commun ne doit pas avoir uniformisé les messages : les deux
        décorateurs se distinguaient par leur préfixe et le mot « UI »."""
        self.Cobaye().echoue_db()
        self.Cobaye().echoue_ui()
        messages = messages_log()
        assert any(m.startswith('Erreur base de données:') for m in messages), messages
        assert any(m.startswith('Erreur opération UI:') for m in messages), messages
        assert any('Erreur dans Cobaye.echoue_db' in m for m in messages), messages
        assert any('Erreur UI dans Cobaye.echoue_ui' in m for m in messages), messages

    def test_prefixe_personnalise(self, messages_log):
        class Autre:
            @handle_database_operation_errors(return_value=None, log_prefix="Erreur maison")
            def echoue(self):
                raise ValueError('boum')

        Autre().echoue()
        assert any(m.startswith('Erreur maison:') for m in messages_log())


# ─── Paire 3 : les handlers de dialogue d'import ─────────────────────────────

class TestHandlersDeDialogue:

    @pytest.fixture
    def manager(self, qapp, test_db_manager):
        from src.core.import_manager import ImportManager
        return ImportManager(db_manager=test_db_manager, parent_widget=None)

    @staticmethod
    def _faux_dialogue(config=None, nettoyages=None):
        from src.core.import_manager import (
            ImportConfiguration, ImportFile, ImportType, FileType)

        class FauxDialogue:
            def get_configuration(self):
                if config is not None:
                    return config
                return ImportConfiguration(
                    files=[ImportFile(path='/tmp/x.csv', type=FileType.CSV,
                                      suggested_reference='R', data=[['a', 'b']])],
                    import_type=ImportType.SINGLE_FILE, show_preview=False)

            def deleteLater(self):
                if nettoyages is not None:
                    nettoyages.append('nettoyé')

        return FauxDialogue()

    @pytest.mark.parametrize("source", ['import', 'drag_drop'])
    def test_la_source_est_propagee(self, manager, source):
        """C'est la seule chose qui différait entre les deux handlers d'origine."""
        recues = []
        manager._launch_real_import = (
            lambda cfg, cb, t0, dialog=None, source=None: recues.append(source))
        manager._on_dialog_accepted(self._faux_dialogue(), None, source)
        assert recues == [source]

    def test_l_apercu_recoit_aussi_la_source(self, manager):
        from src.core.import_manager import (
            ImportConfiguration, ImportFile, ImportType, FileType)
        config = ImportConfiguration(
            files=[ImportFile(path='/tmp/x.csv', type=FileType.CSV,
                              suggested_reference='R', data=[['a', 'b']])],
            import_type=ImportType.SINGLE_FILE, show_preview=True)
        recues = []
        manager._launch_preview = (
            lambda cfg, cb, t0, dialog=None, source=None: recues.append(source))
        manager._on_dialog_accepted(self._faux_dialogue(config), None, 'drag_drop')
        assert recues == ['drag_drop']

    def test_configuration_absente_annule_proprement(self, manager):
        nettoyages, retours = [], []

        class SansConfig:
            def get_configuration(self):
                return None

            def deleteLater(self):
                nettoyages.append('nettoyé')

        manager._on_dialog_accepted(SansConfig(), retours.append, 'import')
        assert retours == [None]
        assert nettoyages == ['nettoyé']

    def test_annulation_rappelle_puis_nettoie(self, manager):
        """L'ordre compte : le callback d'abord, le nettoyage ensuite."""
        evenements = []

        class DialogueAnnule:
            def deleteLater(self):
                evenements.append('nettoyage')

        manager._on_dialog_rejected(
            DialogueAnnule(), lambda r: evenements.append(f'callback({r})'))
        assert evenements == ['callback(None)', 'nettoyage']

    def test_annulation_sans_callback(self, manager):
        nettoyages = []
        manager._on_dialog_rejected(self._faux_dialogue(nettoyages=nettoyages), None)
        assert nettoyages == ['nettoyé']
