"""Configuration des exports en trois colonnes : liste des variantes, renommage,
gabarits d'autres onglets, redirection avec retour, disposition mémorisée."""

import pytest
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QMessageBox

from src.ui.colonne_variantes import ColonneVariantes


NOMS = ['Défaut', 'Zèbre', 'profil 10', 'Profil 2', 'alpha']


@pytest.fixture
def colonne(qapp):
    charges = []
    c = ColonneVariantes(
        'fiche', lambda p: p.update({'valeur': c.valeur_editeur}),
        lambda p: (charges.append(p['name']), setattr(c, 'valeur_editeur', p.get('valeur'))),
        lambda: {'valeur': 'défaut'}, "Fiche complète")
    c.valeur_editeur = None
    c.load([{'name': n, 'valeur': n.upper()} for n in NOMS], 'Défaut')
    c.charges = charges
    yield c
    c.deleteLater()


def _affiches(colonne):
    return [colonne.liste.item(i).text() for i in range(colonne.liste.count())]


# ─── Liste ────────────────────────────────────────────────────────────────────

def test_defaut_en_tete_puis_ordre_naturel(colonne):
    assert _affiches(colonne) == ['Défaut', 'alpha', 'Profil 2', 'profil 10', 'Zèbre']
    assert colonne.titre_label.text() == "Variantes (5)"
    assert colonne.nom_courant == 'Défaut'


def test_filtre_des_six_variantes(colonne):
    assert colonne.filtre.isHidden()
    colonne.ajouter()
    assert not colonne.filtre.isHidden()
    colonne.filtre.setText("PROFIL")
    visibles = [colonne.liste.item(i).text() for i in range(colonne.liste.count())
                if not colonne.liste.item(i).isHidden()]
    assert visibles == ['Profil 2', 'profil 10']


def test_changer_de_variante_reporte_les_champs(colonne):
    colonne.valeur_editeur = 'modifiée'
    colonne.selectionner('alpha')
    assert colonne.valeur_editeur == 'ALPHA'
    profils, _ = colonne.collect()
    assert next(p for p in profils if p['name'] == 'Défaut')['valeur'] == 'modifiée'


# ─── Renommer ─────────────────────────────────────────────────────────────────

def test_renommer_par_le_champ_nom(colonne):
    renommes = []
    colonne.renommages.append(lambda a, n: renommes.append((a, n)))
    colonne.nom_input.setText("Défaut long")
    colonne._on_nom_saisi("Défaut long")
    assert colonne.nom_courant == colonne.nom_defaut == 'Défaut long'
    assert renommes == [('Défaut', 'Défaut long')]
    colonne._fin_saisie_nom()
    assert _affiches(colonne)[0] == 'Défaut long'


def test_nom_deja_pris_ou_vide_refuse(colonne):
    colonne._on_nom_saisi("alpha")
    assert colonne.nom_courant == 'Défaut'
    assert "existe déjà" in colonne.erreur_nom.text() and not colonne.erreur_nom.isHidden()
    colonne._on_nom_saisi("   ")
    assert colonne.nom_courant == 'Défaut'
    assert "vide" in colonne.erreur_nom.text()
    colonne._fin_saisie_nom()
    assert colonne.nom_input.text() == 'Défaut' and colonne.erreur_nom.isHidden()


def test_renommer_en_place_dans_la_liste(colonne):
    item = colonne._item('alpha')
    item.setText('Bêta')  # comme une édition en place validée
    assert 'Bêta' in colonne.noms() and 'alpha' not in colonne.noms()
    item = colonne._item('Bêta')
    item.setText('Zèbre')  # refusé : l'ancien nom revient
    assert colonne._item('Bêta').text() == 'Bêta'
    assert "existe déjà" in colonne.erreur_nom.text()


# ─── Actions ──────────────────────────────────────────────────────────────────

def test_nouvelle_puis_doublon_de_nom(colonne):
    colonne.ajouter()
    colonne.ajouter()
    assert {'Nouvelle variante', 'Nouvelle variante (2)'} <= set(colonne.noms())
    assert colonne.nom_courant == 'Nouvelle variante (2)'
    assert colonne.profil_courant()['valeur'] == 'défaut'


def test_dupliquer(colonne):
    colonne.selectionner('alpha')
    colonne.dupliquer()
    assert colonne.nom_courant == 'alpha (copie)'
    assert colonne.profil_courant()['valeur'] == 'ALPHA'


def test_definir_defaut_et_supprimer(colonne, monkeypatch):
    import src.ui.colonne_variantes as module
    monkeypatch.setattr(module, 'demander_oui_non', lambda p, t, m, sur_oui, defaut=None: sur_oui())
    colonne.selectionner('Zèbre')
    colonne.definir_defaut()
    assert colonne.nom_defaut == 'Zèbre' and _affiches(colonne)[0] == 'Zèbre'
    assert colonne.defaut_btn.isChecked()
    colonne.supprimer()
    assert 'Zèbre' not in colonne.noms()
    assert colonne.nom_defaut == colonne.nom_courant


def test_derniere_variante_non_supprimable(qapp, monkeypatch):
    avertis = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: avertis.append(a[2]))
    c = ColonneVariantes('titre', lambda p: None, lambda p: None, dict, "Titre")
    c.load([{'name': 'Seul'}], 'Seul')
    assert not c.supprimer_btn.isEnabled()
    c.supprimer()
    assert c.noms() == ['Seul'] and avertis == ["Au moins un gabarit doit exister."]


# ─── Fenêtre complète ─────────────────────────────────────────────────────────

@pytest.fixture
def dialogue(qapp, tmp_path, monkeypatch):
    from src.services import export_config_service as module
    from src.ui.export_config_dialog import ExportConfigDialog
    monkeypatch.setattr(module.ExportConfigService, '_resolve_config_path',
                        staticmethod(lambda: str(tmp_path / 'export_config.json')))
    ini = str(tmp_path / 'reglages.ini')
    monkeypatch.setattr(ExportConfigDialog, '_reglages',
                        staticmethod(lambda: QSettings(ini, QSettings.IniFormat)))
    d = ExportConfigDialog(module.ExportConfigService())
    yield d
    d.deleteLater()


def test_aller_retour_de_la_config_inchange(dialogue):
    config = dialogue.export_config_service.get_config()
    collecte = dialogue._collect_config()
    for cle in ('titre', 'fiche'):
        assert collecte[cle] == config[cle]
    assert collecte['html']['details_profiles'] == config['html']['details_profiles']
    assert collecte['html']['details_default_profile'] == config['html']['details_default_profile']


def test_renommer_un_gabarit_titre_suit_dans_les_variantes(dialogue):
    titre = dialogue.titre_tab.colonne
    ancien = titre.nom_defaut
    fiche = dialogue.fiche_tab
    fiche.titre_combo.setCurrentIndex(fiche.titre_combo.findData(ancien))
    fiche.colonne.stocker()
    titre.renommer(ancien, "Titre renommé")
    assert fiche.titre_combo.currentData() == "Titre renommé"
    assert dialogue._collect_config()['fiche']['profiles'][0]['titre_profile'] == "Titre renommé"


def test_selecteur_trie_avec_defaut_explicite(dialogue):
    details = dialogue.details_colonne
    details.ajouter()
    details.renommer(details.nom_courant, "A premier")
    dialogue.fiche_tab.rafraichir_gabarits()
    combo = dialogue.fiche_tab.details_combo
    textes = [combo.itemText(i) for i in range(combo.count()) if combo.itemText(i)]
    assert textes[0] == f"Gabarit par défaut ({details.nom_defaut})"
    assert textes[1:] == details.noms_ordonnes()


def test_modifier_ce_gabarit_puis_retour(dialogue):
    fiche = dialogue.fiche_tab
    fiche.colonne.dupliquer()
    variante = fiche.colonne.nom_courant
    dialogue.ouvrir_sur('fiche', variante)
    fiche._modifier_gabarit('titre')
    assert dialogue._nav_stack.currentIndex() == dialogue._ONGLETS['titre']
    assert dialogue.titre_tab.colonne.nom_courant == dialogue.titre_tab.colonne.nom_defaut
    bandeau = dialogue.titre_tab.retour
    assert not bandeau.isHidden() and variante in bandeau.retour_btn.text()
    fiche.colonne.selectionner(fiche.colonne.nom_defaut)
    bandeau.retour_btn.click()
    assert dialogue._nav_stack.currentIndex() == dialogue._ONGLETS['fiche']
    assert fiche.colonne.nom_courant == variante and bandeau.isHidden()


def test_colonnes_alignees_et_disposition_memorisee(dialogue):
    premier, *autres = dialogue._separateurs
    assert len(dialogue._separateurs) == 3
    premier.setSizes([300, 600, 330])
    dialogue._aligner_colonnes(premier)
    assert all(s.sizes() == premier.sizes() for s in autres)
    dialogue.done(0)
    reglages = dialogue._reglages()
    assert reglages.value(dialogue.CLE_GEOMETRIE) is not None
    assert reglages.value(dialogue.CLE_COLONNES) is not None


def test_ouvrir_sur_un_gabarit(dialogue):
    details = dialogue.details_colonne
    details.ajouter()
    nom = details.nom_courant
    details.selectionner(details.nom_defaut)
    dialogue.ouvrir_sur('html_details', nom)
    assert dialogue._nav_stack.currentIndex() == 1 and details.nom_courant == nom
