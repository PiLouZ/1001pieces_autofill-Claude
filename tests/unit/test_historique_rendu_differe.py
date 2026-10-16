"""Historique : rendu du panneau différé pendant une rafale d'entrées (v3.91.1).

1858 suggestions validées d'un coup : le vidage de l'historique groupé appelait
`add_to_history` 1858 fois, et chaque appel remettait en page les 100 entrées du
panneau (`setHtml`). Mesuré sur une copie de la base réelle : 28,8 s gelées
(~55 s dans l'application), dont 94 % dans `setHtml`. Après : 0,17 s.
Entrées, persistance et contenu final du panneau doivent rester identiques.
"""
from unittest.mock import MagicMock

import pytest

from src.services.grouped_history_service import GroupedHistoryService
from src.ui.user_interaction_service import UserInteractionService


def _service():
    fenetre = MagicMock()
    fenetre.table = None   # pas de tableau : la référence retombe sur l'id
    return UserInteractionService(fenetre), fenetre


def _remplir(groupe, n):
    for db_id in range(1, n + 1):
        groupe.add_modification(db_id, "Type", "", "Plaque",
                                source="suggestion réf. X (score 100%)",
                                reference=f"REF{db_id}")
        groupe.add_modification(db_id, "Fabricant", "", "Balay")


class TestDiffererAffichage:
    def test_un_seul_rendu_a_la_sortie(self):
        service, fenetre = _service()
        with service.differer_affichage():
            for i in range(5):
                service.add_to_history(f"Message {i}")
            fenetre.history_list.setHtml.assert_not_called()
        assert fenetre.history_list.setHtml.call_count == 1
        # La persistance n'est PAS différée : une entrée par appel, comme avant
        assert fenetre.history_service.persist.call_count == 5

    def test_reentrant_rendu_au_bloc_externe(self):
        service, fenetre = _service()
        with service.differer_affichage():
            with service.differer_affichage():
                service.add_to_history("A")
            fenetre.history_list.setHtml.assert_not_called()
            service.add_to_history("B")
        assert fenetre.history_list.setHtml.call_count == 1

    def test_aucun_rendu_si_rien_ajoute(self):
        service, fenetre = _service()
        with service.differer_affichage():
            pass
        fenetre.history_list.setHtml.assert_not_called()

    def test_rendu_meme_si_exception(self):
        service, fenetre = _service()
        with pytest.raises(RuntimeError):
            with service.differer_affichage():
                service.add_to_history("A")
                raise RuntimeError("boum")
        assert fenetre.history_list.setHtml.call_count == 1
        # Hors bloc, le rendu redevient immédiat
        service.add_to_history("B")
        assert fenetre.history_list.setHtml.call_count == 2


class TestVidageGroupe:
    def test_vidage_en_masse_un_seul_rendu_resultat_identique(self, qapp):
        # Référence : même lot, rendu à chaque entrée (comportement d'avant)
        avant, fen_avant = _service()
        groupe_avant = GroupedHistoryService(avant)
        _remplir(groupe_avant, 300)
        for db_id, data in list(groupe_avant.pending_modifications.items()):
            groupe_avant._flush_device_modifications(db_id, data)
        assert fen_avant.history_list.setHtml.call_count == 300

        apres, fen_apres = _service()
        groupe_apres = GroupedHistoryService(apres)
        _remplir(groupe_apres, 300)
        groupe_apres.flush_all_pending_modifications()

        assert fen_apres.history_list.setHtml.call_count == 1
        assert groupe_apres.pending_modifications == {}
        # Mêmes entrées persistées, dans le même ordre
        persistees = lambda f: [(c.args[0]['title'], c.args[0]['details'], c.args[0]['devices'])
                                for c in f.history_service.persist.call_args_list]
        assert persistees(fen_apres) == persistees(fen_avant)
        assert len(persistees(fen_apres)) == 300
        # Même panneau final (horodatages mis à part)
        sans_heure = lambda f: [(e['title'], e['details'], e.get('count'))
                                for e in f]
        assert sans_heure(apres._history_entries) == sans_heure(avant._history_entries)
        assert fen_apres.history_list.setHtml.call_args.args[0].count("REF") \
            == fen_avant.history_list.setHtml.call_args.args[0].count("REF")

    def test_service_sans_differer_affichage(self, qapp):
        # Appelant minimal (ancien service ou doublure) : le vidage fonctionne toujours
        class Minimal:
            def __init__(self):
                self.main_window = MagicMock(table=None)
                self.messages = []

            def add_to_history(self, message):
                self.messages.append(message)

        minimal = Minimal()
        groupe = GroupedHistoryService(minimal)
        _remplir(groupe, 3)
        groupe.flush_all_pending_modifications()
        assert len(minimal.messages) == 3
        assert "(source : suggestion réf. X (score 100%))" in minimal.messages[0]
