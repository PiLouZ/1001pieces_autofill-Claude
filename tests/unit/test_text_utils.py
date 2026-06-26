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
