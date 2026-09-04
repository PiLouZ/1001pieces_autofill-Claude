"""
Tests — L'alerte de mapping remonte jusqu'à la synthèse d'import

Un collage ou un CSV dont les colonnes sont mal alignées produit un import
silencieusement faux : les lignes s'écrasent sur une seule identité d'appareil.
La détection existait depuis longtemps mais n'écrivait qu'une ligne de log —
25 des 495 imports de l'historique la déclenchaient sans que rien ne s'affiche.

Le message est désormais calculé une seule fois dans `_log_resume_import` et
transporté dans `results['alerte_mapping']`, que les deux constructeurs de
synthèse (import CSV/collage et import PDF) consomment tel quel.
"""

import pytest

from src.core.import_manager import ImportManager


@pytest.fixture
def manager(qapp, test_db_manager):
    im = ImportManager(db_manager=test_db_manager, parent_widget=None)
    im._log_counters = im._nouveaux_compteurs_log()
    return im


def _resume(manager, traitees, doublons, cles):
    """Rejouer _log_resume_import avec des compteurs donnés."""
    results = {'total_imported': traitees, 'duplicates_in_file': doublons}
    manager._log_resume_import(results, set(f"cle{i}" for i in range(cles)))
    return results


class TestDetection:

    def test_alerte_quand_une_seule_identite(self, manager):
        """Le cas vécu : 3 lignes collées, 1 seule identité d'appareil."""
        r = _resume(manager, traitees=2, doublons=1, cles=1)
        assert 'alerte_mapping' in r
        assert '3 lignes' in r['alerte_mapping']
        assert 'mapping' in r['alerte_mapping']

    def test_alerte_quand_aucune_identite(self, manager):
        r = _resume(manager, traitees=5, doublons=0, cles=0)
        assert 'alerte_mapping' in r

    def test_pas_d_alerte_quand_identites_multiples(self, manager):
        """Import sain : autant d'identités que de lignes."""
        r = _resume(manager, traitees=3, doublons=0, cles=3)
        assert 'alerte_mapping' not in r

    def test_pas_d_alerte_sur_une_ligne_unique(self, manager):
        """Une ligne pour une identité est normal, pas suspect."""
        r = _resume(manager, traitees=1, doublons=0, cles=1)
        assert 'alerte_mapping' not in r

    def test_cles_distinctes_toujours_exposees(self, manager):
        """Le compte est transporté même sans alerte — utile pour diagnostiquer."""
        r = _resume(manager, traitees=3, doublons=0, cles=3)
        assert r['cles_distinctes'] == 3


class TestMessageUnique:
    """La règle ne doit exister qu'à un seul endroit : le message est calculé
    dans _log_resume_import, les synthèses ne font que le lire."""

    def test_le_message_est_pret_a_afficher(self, manager):
        r = _resume(manager, traitees=59, doublons=1, cles=1)
        message = r['alerte_mapping']
        assert message.startswith("60 lignes")
        assert message.endswith("vérifiez le mapping des colonnes")
        # Ni préfixe de log, ni ponctuation finale : c'est l'UI qui décore
        assert not message.startswith("[")
        assert not message.endswith(".")
