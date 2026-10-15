"""Non-régression : une nouvelle recherche ne doit pas hériter des réf. ajoutées
par les bandeaux de la recherche précédente (anciennes réf., équivalents, bypass).

Bug (3.81.1) : après une réf. à bandeau (ex. une réf. qui en remplace 191),
chercher une réf. inexistante affichait les 471 lignes de la recherche d'avant
au lieu de « Aucun résultat » — la requête était construite avec la liste encore
en mémoire, le bandeau n'étant caché qu'après le remplissage, sans relance.
"""

from unittest.mock import Mock

from src.ui.qt_imports import Qt
from src.ui.table_controller import TableController


def _controleur():
    """TableController minimal : capture le terme effectif envoyé à la base."""
    tc = TableController.__new__(TableController)
    tc.termes_envoyes = []

    db = Mock()
    db.count_data.return_value = 0
    db.load_data.side_effect = lambda term, *a, **k: tc.termes_envoyes.append(term) or []
    tc.db_manager = db

    pw = Mock()
    pw.search_service.parse_advanced_search = lambda t: {'original': t.strip()}
    tc.parent_window = pw

    tc.table = Mock()
    tc.table.currentRow.return_value = 0
    tc.prefetch_timer = Mock()
    tc.prefetch_cache = {}
    tc.filter_widgets = {}
    tc.page_size = 500
    tc.current_page = 1
    tc.current_sort_column = -1
    tc.current_sort_order = Qt.AscendingOrder
    tc._extend_search_active = False
    tc._current_incomplete_filter = lambda: False
    tc._add_to_search_history = lambda term: None
    tc._update_pagination_controls = lambda: None
    tc._update_sort_indicators = lambda: None
    tc._check_supersession_banner = lambda term: None
    return tc


def _bandeaux_de(tc, terme):
    """État laissé par une recherche de `terme` avec les deux bandeaux actifs."""
    tc._supersession_term = terme
    tc._supersession_mode = 'replacing'
    tc._supersession_expand = True
    tc._supersession_bypass = True
    tc._supersession_predecessors = ['ANC_1', 'ANC_2']
    tc._supersession_siblings = []
    tc._supersession_chain = []
    tc._equivalence_term = terme
    tc._equivalence_expand = True
    tc._equivalence_group = ['EQUIV_1']
    tc._equivalence_display = ['EQUIV_1']


CLES_BANDEAUX = ('expand_predecessors', 'expand_equivalents', 'bypass_supersession')


class TestNouvelleRechercheSansHeritage:
    def test_ref_inexistante_apres_ref_a_bandeau(self):
        tc = _controleur()
        _bandeaux_de(tc, 'REF_A')
        tc.load_data('REF_INEXISTANTE', is_search=True)
        envoye = tc.termes_envoyes[-1]
        for cle in CLES_BANDEAUX:
            assert cle not in envoye, f"{cle} hérité de la recherche précédente"
        assert tc._supersession_predecessors == []
        assert tc._equivalence_group == []

    def test_changement_de_terme_sans_is_search(self):
        """Ex. recherche relancée par un autre chemin avec un nouveau terme."""
        tc = _controleur()
        _bandeaux_de(tc, 'REF_A')
        tc.load_data('REF_B')
        for cle in CLES_BANDEAUX:
            assert cle not in tc.termes_envoyes[-1]


class TestMemeTermeConserveLesBandeaux:
    def test_pagination_tri_filtres(self):
        tc = _controleur()
        _bandeaux_de(tc, 'REF_A')
        tc.load_data('REF_A')  # chemin pagination / tri / filtres de colonnes
        envoye = tc.termes_envoyes[-1]
        assert envoye['expand_predecessors'] == ['ANC_1', 'ANC_2']
        assert envoye['expand_equivalents'] == ['EQUIV_1']
        assert envoye['bypass_supersession'] is True

    def test_meme_terme_avec_espaces(self):
        tc = _controleur()
        _bandeaux_de(tc, 'REF_A')
        tc.load_data('  REF_A ', is_search=True)
        assert tc.termes_envoyes[-1]['expand_predecessors'] == ['ANC_1', 'ANC_2']
        assert tc._equivalence_expand is True
