"""
Tests — La provenance d'une suggestion survit dans l'historique

`grouped_history_service` ajoute « (source : suggestion réf. X (score Y)) » à
l'édition d'un appareil complété par suggestion. `_parse_entry` reconstruisait
les éditions avec les seules lignes « ==> » : pour une suggestion Type + Fabricant
(le cas normal), la provenance disparaissait du panneau ET de la base.

Constaté le 2026-10-15 : aucune trace de suggestion acceptée depuis le
2026-07-02, alors que l'utilisateur s'en sert — ~1 100 appareils validés depuis
le 2026-09-15, estimés par signature (plusieurs marques écrites la même seconde).
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

from src.services.history_service import HistoryService
from src.ui.user_interaction_service import (
    UserInteractionService, _inserer_entree, _parse_entry,
)

SOURCE = "(source : suggestion réf. HB978GNM1/K2 (score 100%))"
AUTRE_SOURCE = "(source : suggestion réf. HB978GNM1/K3 (score 92%))"


def _msg(ref, champs, source=None):
    lignes = [f"Modification de l'appareil {ref}"]
    lignes += [f"     ==> {f} : '{o}' → '{n}'" for f, o, n in champs]
    if source:
        lignes.append(f"     {source}")
    return "\n".join(lignes)


DEUX = [("Type", "", "Four"), ("Fabricant", "", "Siemens")]
UN = [("Fabricant", "", "Siemens")]


class TestParsing:

    def test_multi_champs_garde_la_source(self):
        e = _parse_entry(_msg("R1", DEUX, SOURCE), datetime.now())
        assert e['title'] == "[Type + Fabricant]"
        assert e['details'] == ["==> Type : '' → 'Four'", "==> Fabricant : '' → 'Siemens'", SOURCE]
        assert e['devices'] == ["R1"]

    def test_mono_champ_garde_la_source_et_son_titre_concis(self):
        e = _parse_entry(_msg("R1", UN, SOURCE), datetime.now())
        assert e['title'] == "[Fabricant]  '' → 'Siemens'"
        assert e['details'] == [SOURCE]

    def test_edition_manuelle_inchangee(self):
        e = _parse_entry(_msg("R1", DEUX), datetime.now())
        assert e['details'] == ["==> Type : '' → 'Four'", "==> Fabricant : '' → 'Siemens'"]
        assert e['agg_key'] == (("Fabricant", "Siemens"), ("Type", "Four"))


class TestRegroupement:

    def _inserer(self, *messages):
        entrees = []
        for m in messages:
            _inserer_entree(entrees, _parse_entry(m, datetime.now()))
        return entrees

    def test_suggestion_et_manuelle_ne_se_regroupent_pas(self):
        entrees = self._inserer(_msg("R1", DEUX), _msg("R2", DEUX, SOURCE))
        assert len(entrees) == 2

    def test_suggestions_identiques_se_regroupent(self):
        entrees = self._inserer(_msg("R1", DEUX, SOURCE), _msg("R2", DEUX, SOURCE))
        assert len(entrees) == 1 and entrees[0]['count'] == 2
        assert entrees[0]['details'][-1] == SOURCE

    def test_sources_differentes_deviennent_generiques(self):
        entrees = self._inserer(_msg("R1", DEUX, SOURCE), _msg("R2", DEUX, AUTRE_SOURCE))
        assert len(entrees) == 1 and entrees[0]['count'] == 2
        assert entrees[0]['details'][-1] == "(source : suggestions par similarité)"
        assert entrees[0]['devices'] == ["R1", "R2"]


class TestPersistance:

    def _persister(self, message):
        service = HistoryService.__new__(HistoryService)
        service.db_manager = MagicMock()
        service.persist(_parse_entry(message, datetime(2026, 10, 15, 10, 0, 0)))
        sql, valeurs = service.db_manager.execute_insert.call_args[0]
        return dict(zip(["timestamp", "action_type", "title", "details",
                         "device_ref", "field_name", "old_value", "new_value"], valeurs))

    def test_source_ecrite_en_base(self):
        ligne = self._persister(_msg("R1", DEUX, SOURCE))
        assert SOURCE in json.loads(ligne["details"])

    def test_mono_champ_garde_son_champ_en_base(self):
        """La clé enveloppée (clé, marque source) ne doit pas faire perdre field_name."""
        ligne = self._persister(_msg("R1", UN, SOURCE))
        assert ligne["field_name"] == "Fabricant"
        assert ligne["old_value"] == "" and ligne["new_value"] == "Siemens"


class TestRechargement:

    def _service(self, lignes):
        fenetre = MagicMock()
        fenetre.history_service.get_recent_rows.return_value = lignes
        return UserInteractionService(fenetre)

    def test_suggestions_rechargees_regroupees_et_separees_des_manuelles(self):
        details_sugg = json.dumps(["==> Type : '' → 'Four'", "==> Fabricant : '' → 'Siemens'", SOURCE],
                                  ensure_ascii=False)
        details_man = json.dumps(["==> Type : '' → 'Four'", "==> Fabricant : '' → 'Siemens'"],
                                 ensure_ascii=False)
        s = self._service([
            ('2026-10-15 10:00:02', 'edit', '[Type + Fabricant]', details_sugg, 'R3', None, None),
            ('2026-10-15 10:00:01', 'edit', '[Type + Fabricant]', details_sugg, 'R2', None, None),
            ('2026-10-15 10:00:00', 'edit', '[Type + Fabricant]', details_man, 'R1', None, None),
        ])
        s.restaurer_historique()
        assert [e['count'] for e in s._history_entries] == [2, 1]
        assert s._history_entries[0]['details'][-1] == SOURCE


class TestMessageReel:
    """Le message réel de grouped_history_service mêle un « \\\\n » littéral
    (entre les lignes ==>) et un vrai saut de ligne (avant la source)."""

    def test_de_bout_en_bout_depuis_grouped_history_service(self):
        from src.services.grouped_history_service import GroupedHistoryService
        service = GroupedHistoryService.__new__(GroupedHistoryService)
        service.main_window = MagicMock()
        service.user_interaction_service = MagicMock()
        service.stats = {'single_modifications': 0, 'grouped_modifications': 0,
                         'total_devices_modified': 0}
        service._get_appareil_reference = lambda db_id: "R1"
        service._flush_device_modifications(1, {
            'modifications': DEUX, 'timestamp': datetime.now(), 'source': SOURCE[10:-1]})
        message = service.user_interaction_service.add_to_history.call_args[0][0]

        e = _parse_entry(message, datetime.now())
        assert e['title'] == "[Type + Fabricant]"
        assert e['details'][-1] == SOURCE
        assert e['devices'] == ["R1"]
