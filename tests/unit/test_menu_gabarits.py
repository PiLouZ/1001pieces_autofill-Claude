"""Menu des gabarits : tri, filtre, clavier et récents (v3.99.4)."""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QToolButton

from src.ui.menu_gabarits import MenuGabarits, lire_recents, noter_recent


class ReglagesFactices:
    """Remplace QSettings : value()/setValue() sur un dict."""

    def __init__(self, valeurs=None):
        self.valeurs = dict(valeurs or {})

    def value(self, cle, defaut=None):
        return self.valeurs.get(cle, defaut)

    def setValue(self, cle, valeur):
        self.valeurs[cle] = valeur


NOMS = ['Défaut', 'Zèbre', 'profil 10', 'Profil 2', 'alpha', 'Bonus 3', 'Éco', 'gamma']
CLE = 'exports/recents/test'


@pytest.fixture
def bouton(qapp):
    btn = QToolButton()
    yield btn
    btn.deleteLater()


def _menu(bouton, noms=NOMS, reglages=None):
    reglages = reglages if reglages is not None else ReglagesFactices()
    menu = MenuGabarits(bouton, noms, 'Défaut', lambda: reglages, CLE)
    choisis = []
    menu.triggered.connect(lambda a: choisis.append(a.data()))
    return menu, reglages, choisis


def _ouvrir(menu):
    menu.popup(menu.parent().mapToGlobal(menu.parent().rect().bottomLeft()))
    QTest.qWait(10)


def _visibles(menu):
    return [a.text() for a in menu._actions_choisissables()]


class TestRecentsReglages:

    def test_chaine_seule_lue_comme_liste(self):
        assert lire_recents(ReglagesFactices({CLE: 'A'}), CLE) == ['A']

    def test_noter_sans_doublon_et_borne(self):
        reglages = ReglagesFactices()
        for nom in ['A', 'B', 'A'] + [str(i) for i in range(20)]:
            noter_recent(reglages, CLE, nom)
        recents = lire_recents(reglages, CLE)
        assert recents[0] == '19' and len(recents) == 10 and len(set(recents)) == 10

    def test_reglages_absents(self):
        assert lire_recents(None, CLE) == []
        noter_recent(None, CLE, 'A')  # pas d'erreur


class TestMenuSimple:

    def test_peu_de_gabarits_liste_triee_sans_filtre(self, bouton):
        menu, _, _ = _menu(bouton, ['Défaut', 'b', 'A 10', 'a 2'])
        assert not menu.avec_recherche
        assert [a.text() for a in menu.actions()] == ['a 2', 'A 10', 'b']


class TestMenuAvecRecherche:

    def test_tri_naturel_defaut_exclu(self, bouton):
        menu, _, _ = _menu(bouton)
        assert menu.avec_recherche
        assert [a.text() for a in menu._actions_tous] == \
            ['alpha', 'Bonus 3', 'Éco', 'gamma', 'Profil 2', 'profil 10', 'Zèbre']

    def test_filtre_casse_accents_plusieurs_mots(self, bouton):
        menu, _, _ = _menu(bouton)
        _ouvrir(menu)
        menu.champ_filtre.setText('ECO')
        assert _visibles(menu) == ['Éco']
        menu.champ_filtre.setText('pro 10')
        assert _visibles(menu) == ['profil 10']
        menu.champ_filtre.setText('xyz')
        assert _visibles(menu) == [] and menu._aucun.isVisible()
        menu.close()

    def test_entree_lance_le_premier_resultat_et_note_recent(self, bouton):
        menu, reglages, choisis = _menu(bouton)
        _ouvrir(menu)
        QTest.keyClicks(menu.champ_filtre, 'profil')
        QTest.keyClick(menu.champ_filtre, Qt.Key_Return)
        assert choisis == ['Profil 2']
        assert not menu.isVisible()
        assert lire_recents(reglages, CLE) == ['Profil 2']

    def test_fleches_puis_entree(self, bouton):
        menu, _, choisis = _menu(bouton)
        _ouvrir(menu)
        QTest.keyClicks(menu.champ_filtre, 'profil')
        QTest.keyClick(menu.champ_filtre, Qt.Key_Down)
        assert menu.activeAction().text() == 'profil 10'
        QTest.keyClick(menu.champ_filtre, Qt.Key_Down)  # boucle sur le premier
        QTest.keyClick(menu.champ_filtre, Qt.Key_Down)
        QTest.keyClick(menu.champ_filtre, Qt.Key_Return)
        assert choisis == ['profil 10']

    def test_echap_ferme_sans_lancer(self, bouton):
        menu, _, choisis = _menu(bouton)
        _ouvrir(menu)
        QTest.keyClick(menu.champ_filtre, Qt.Key_Escape)
        assert not menu.isVisible() and choisis == []

    def test_recents_affiches_puis_masques_au_filtrage(self, bouton):
        reglages = ReglagesFactices({CLE: ['gamma', 'Supprimé', 'Défaut', 'alpha', 'Éco', 'Zèbre']})
        menu, _, _ = _menu(bouton, reglages=reglages)
        _ouvrir(menu)
        # Inconnu et défaut écartés, 3 au plus, du plus récent au plus ancien
        assert [a.text() for a in menu._actions_recents] == ['gamma', 'alpha', 'Éco']
        assert menu._entete_recents.isVisible()
        menu.champ_filtre.setText('a')
        assert not menu._entete_recents.isVisible()
        assert all(not a.isVisible() for a in menu._actions_recents)
        menu.close()

    def test_reouverture_vide_le_filtre_et_rafraichit_recents(self, bouton):
        menu, reglages, _ = _menu(bouton)
        _ouvrir(menu)
        QTest.keyClicks(menu.champ_filtre, 'zeb')
        QTest.keyClick(menu.champ_filtre, Qt.Key_Return)
        _ouvrir(menu)
        assert menu.champ_filtre.text() == ''
        assert [a.text() for a in menu._actions_recents] == ['Zèbre']
        assert len(_visibles(menu)) == 8  # 1 récent + 7 gabarits
        menu.close()
