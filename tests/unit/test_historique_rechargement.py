"""
Tests — Le panneau Historique recharge les 100 dernières entrées au lancement

Demande de l'utilisateur (2026-10-13) : le panneau était vide à chaque ouverture
(session seulement depuis la v3.24.0), alors que tout est persisté en base.
Points sensibles : ne jamais re-persister une entrée rechargée (sinon chaque
lancement dupliquerait l'historique), et garder la session en cours séparée.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.ui.user_interaction_service import UserInteractionService, _MAX_HISTORY


def _ligne(ts, action='edit', title='', details=None, device=None, field=None, new=None):
    """Ligne au format de HistoryService.get_recent_rows."""
    return (ts, action, title, json.dumps(details, ensure_ascii=False) if details else None,
            device, field, new)


class _Fenetre:
    def __init__(self, lignes):
        self.history_service = MagicMock()
        # get_recent_rows : de la plus récente à la plus ancienne
        self.history_service.get_recent_rows.return_value = lignes


def _service(lignes):
    return UserInteractionService(_Fenetre(lignes))


def test_entrees_rechargees_dans_l_ordre():
    s = _service([
        _ligne('2026-10-12 10:05:00', 'import', 'Import b.csv:', ['==> Lignes traitées : 2']),
        _ligne('2026-10-12 10:00:00', 'import', 'Import a.csv:', ['==> Lignes traitées : 1']),
    ])
    s.restaurer_historique()
    assert [e['title'] for e in s._history_entries] == ['Import b.csv:', 'Import a.csv:']
    assert all(e['restauree'] for e in s._history_entries)
    assert s._history_entries[0]['details'] == ['==> Lignes traitées : 2']


def test_aucune_entree_re_persistee():
    s = _service([_ligne('2026-10-12 10:00:00', 'import', 'Import a.csv:')])
    s.restaurer_historique()
    s.main_window.history_service.persist.assert_not_called()


def test_regroupement_xN_reconstruit_avec_tous_les_appareils():
    titre = "[Fabricant]  '' → 'Whirlpool'"
    s = _service([
        _ligne('2026-10-12 10:00:02', title=titre, device='R3', field='Fabricant', new='Whirlpool'),
        _ligne('2026-10-12 10:00:01', title=titre, device='R2', field='Fabricant', new='Whirlpool'),
        _ligne('2026-10-12 10:00:00', title=titre, device='R1', field='Fabricant', new='Whirlpool'),
    ])
    s.restaurer_historique()
    assert len(s._history_entries) == 1
    entree = s._history_entries[0]
    assert entree['count'] == 3
    assert entree['devices'] == ['R1', 'R2', 'R3']
    assert entree['timestamp_str'] == '10:00:02'


def test_regroupement_multi_champs_reconstruit():
    details = ["==> Type : 'a' → 'b'", "==> Fabricant : '' → 'X'"]
    s = _service([
        _ligne('2026-10-12 10:00:01', title='[Type + Fabricant]', details=details, device='R2'),
        _ligne('2026-10-12 10:00:00', title='[Type + Fabricant]', details=details, device='R1'),
    ])
    s.restaurer_historique()
    assert len(s._history_entries) == 1
    assert s._history_entries[0]['count'] == 2


def test_session_en_cours_au_dessus_et_jamais_regroupee():
    titre = "[Fabricant]  '' → 'Whirlpool'"
    s = _service([_ligne('2026-10-12 10:00:00', title=titre, device='R1',
                         field='Fabricant', new='Whirlpool')])
    s.add_to_history("Modification de l'appareil R9\n     ==> Fabricant : '' → 'Whirlpool'")
    s.restaurer_historique()
    assert len(s._history_entries) == 2
    assert not s._history_entries[0].get('restauree')
    assert s._history_entries[1]['restauree']
    # Une nouvelle modification identique se regroupe avec la session, pas avec l'ancienne
    s.add_to_history("Modification de l'appareil R8\n     ==> Fabricant : '' → 'Whirlpool'")
    assert s._history_entries[0]['count'] == 2
    assert s._history_entries[1]['count'] == 1


def test_limite_de_100_entrees():
    base = datetime(2026, 10, 12, 8, 0, 0)
    lignes = [_ligne((base + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S'),
                     'import', f'Import {i}.csv:') for i in range(250, 0, -1)]
    s = _service(lignes)
    s.restaurer_historique()
    assert len(s._history_entries) == _MAX_HISTORY
    assert s._history_entries[0]['title'] == 'Import 250.csv:'


def test_separateur_sessions_precedentes():
    s = _service([_ligne('2026-10-12 10:00:00', 'import', 'Import a.csv:')])
    s.add_to_history("Import b.csv:\n     ==> Lignes traitées : 1")
    s.restaurer_historique()
    html = s._build_history_html()
    assert html.count('Sessions précédentes') == 1
    assert html.index('Import b.csv') < html.index('Sessions précédentes') < html.index('Import a.csv')


def test_ligne_illisible_ignoree():
    s = _service([
        _ligne('date invalide', 'import', 'Cassée'),
        ('2026-10-12 10:00:00', 'import', 'Import a.csv:', '{pas du json', None, None, None),
    ])
    s.restaurer_historique()
    assert [e['title'] for e in s._history_entries] == ['Import a.csv:']
    assert s._history_entries[0]['details'] == []


def test_base_indisponible_sans_erreur():
    s = _service([])
    s.main_window.history_service.get_recent_rows.side_effect = RuntimeError("base fermée")
    s.restaurer_historique()
    assert s._history_entries == []


def test_libelles_de_date():
    maintenant = datetime.now()
    hier = maintenant - timedelta(days=1)
    assert UserInteractionService._time_label(hier.replace(hour=16, minute=48)) == "Hier à 16:48"
    ancien = datetime(maintenant.year, 1, 5, 9, 7) if maintenant.month > 1 or maintenant.day > 6 \
        else datetime(maintenant.year - 1, 12, 5, 9, 7)
    attendu_mois = 'janv.' if ancien.month == 1 else 'déc.'
    assert UserInteractionService._time_label(ancien) == f"{ancien.day} {attendu_mois} à 09:07"
    assert UserInteractionService._time_label(datetime(2020, 8, 3, 14, 0)) == "3 août 2020 à 14:00"
