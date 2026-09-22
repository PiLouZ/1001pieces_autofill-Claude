"""
Tests — Filtre « Sans libellé » du gestionnaire de pièces (lot 2)

« Fantôme » et « sans libellé » se recoupent sans se confondre, et les confondre
était précisément le défaut : une réf jamais importée peut porter un libellé
hérité d'une voisine, et une pièce bien réelle peut n'en avoir aucun si le
fichier source n'en fournissait pas. Relevé en base le 2026-09-22 : 98 fantômes
nommées, 76 pièces réelles sans libellé.

`_get_filtered_data` ne lit que quatre attributs de son instance : on l'appelle
détachée plutôt que de monter la QDialog entière (chargement différé par
QTimer, panneaux latéraux, etc.).
"""

import pytest

from src.ui.pieces_manager import PiecesManagerWindow


class _Recherche:
    """Double du QLineEdit de recherche."""
    def __init__(self, texte=""):
        self._texte = texte

    def text(self):
        return self._texte


class _Fenetre:
    """Porteur minimal des attributs lus par `_get_filtered_data`."""
    def __init__(self, lignes, filtre='all', recherche=""):
        # (ref, description, nb_appareils, types, is_phantom)
        self.all_pieces_data = lignes
        self._active_filter = filtre
        self.search_input = _Recherche(recherche)
        self.all_statuses = {}


# ref, libellé, nb appareils, types, fantôme
NOMMEE           = ("AAA", "Pompe de cyclage", 3, None, 0)
ANONYME          = ("BBB", None, 2, None, 0)
FANTOME_NOMME    = ("CCC", "Carte de puissance", 0, None, 1)
FANTOME_ANONYME  = ("DDD", None, 0, None, 1)
LIBELLE_ESPACES  = ("EEE", "   ", 1, None, 0)

TOUTES = [NOMMEE, ANONYME, FANTOME_NOMME, FANTOME_ANONYME, LIBELLE_ESPACES]


def _filtrer(filtre, lignes=None, recherche=""):
    fenetre = _Fenetre(lignes if lignes is not None else TOUTES, filtre, recherche)
    return PiecesManagerWindow._get_filtered_data(fenetre)


class TestFiltreSansLibelle:

    def test_ne_retient_que_les_refs_sans_libelle(self):
        refs = [r[0] for r in _filtrer('unlabeled')]
        assert refs == ["BBB", "DDD", "EEE"]

    def test_un_fantome_nomme_est_exclu(self):
        """Le cœur de la distinction : « fantôme » ne veut pas dire « anonyme »."""
        assert FANTOME_NOMME not in _filtrer('unlabeled')

    def test_une_piece_reelle_anonyme_est_incluse(self):
        """Symétrique : ces 76 pièces n'apparaissaient sous aucun filtre."""
        assert ANONYME in _filtrer('unlabeled')

    def test_un_libelle_d_espaces_compte_comme_vide(self):
        assert LIBELLE_ESPACES in _filtrer('unlabeled')

    def test_se_combine_avec_la_recherche(self):
        refs = [r[0] for r in _filtrer('unlabeled', recherche="dd")]
        assert refs == ["DDD"]


class TestFiltresExistantsInchanges:
    """Garde de non-régression : le nouveau filtre ne déplace pas les autres."""

    def test_fantomes(self):
        assert [r[0] for r in _filtrer('phantom')] == ["CCC", "DDD"]

    def test_orphelines(self):
        assert [r[0] for r in _filtrer('orphan')] == ["CCC", "DDD"]

    def test_toutes(self):
        assert len(_filtrer('all')) == len(TOUTES)
