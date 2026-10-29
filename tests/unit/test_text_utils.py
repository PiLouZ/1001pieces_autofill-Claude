"""
Tests des utilitaires de texte — normalisation d'accents pour la recherche.
Pur Python, aucune dépendance Qt.
"""

from src.utils.text_utils import strip_accents


class TestStripAccents:
    def test_voyelles_accentuees(self):
        assert strip_accents("Jünker") == "Junker"
        assert strip_accents("Crémaillère") == "Cremaillere"
        assert strip_accents("élève") == "eleve"
        assert strip_accents("Noël") == "Noel"
        assert strip_accents("août") == "aout"

    def test_cedille_et_divers(self):
        assert strip_accents("français") == "francais"
        assert strip_accents("çà") == "ca"

    def test_sans_accent_inchange(self):
        assert strip_accents("Juno") == "Juno"
        assert strip_accents("Bosch") == "Bosch"

    def test_vide_ou_none(self):
        assert strip_accents("") == ""
        assert strip_accents(None) == ""


class TestFiltrageInsensibleAuxAccents:
    """Reproduit la logique de filtrage du dialogue d'auto-complétion :
    `filter_norm in strip_accents(value.lower())`."""

    @staticmethod
    def _match(saisie, valeur):
        return strip_accents(saisie.lower()) in strip_accents(valeur.lower())

    def test_ju_retrouve_junker_et_juno(self):
        # Le cœur de la demande : « Ju » doit retrouver la marque accentuée.
        assert self._match("Ju", "Jünker") is True
        assert self._match("Ju", "Juno") is True

    def test_saisie_accentuee_retrouve_aussi(self):
        # Symétrie : taper l'accent fonctionne également.
        assert self._match("Jü", "Jünker") is True
        assert self._match("Jü", "Juno") is True

    def test_non_correspondance(self):
        assert self._match("Bo", "Jünker") is False


class TestCleTriNaturel:
    """Tri alphanumérique des menus de gabarits (v3.99.3)."""

    def test_nombres_par_valeur(self):
        from src.utils.text_utils import cle_tri_naturel
        assert sorted(['Profil 10', 'Profil 2', 'Profil 1'], key=cle_tri_naturel) == \
            ['Profil 1', 'Profil 2', 'Profil 10']

    def test_casse_et_accents_ignores(self):
        from src.utils.text_utils import cle_tri_naturel
        assert sorted(['zeta', 'Étendu', 'beta', 'Alpha'], key=cle_tri_naturel) == \
            ['Alpha', 'beta', 'Étendu', 'zeta']

    def test_vide_et_none(self):
        from src.utils.text_utils import cle_tri_naturel
        assert cle_tri_naturel(None) == ()
        assert cle_tri_naturel('') == ()
