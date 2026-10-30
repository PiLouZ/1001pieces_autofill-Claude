"""
Tests — Fiche produit complète (bouton « Fiche complète ») et modèles HTML
colorés / indentés de la configuration des exports

Décisions client du 2026-10-30 : code produit = référence tapée (la plus récente
si elle est remplacée) ; « Remplace » = toute sa lignée ; une ligne par
équivalente avec ses anciennes références, de la plus fournie à la moins
fournie ; lignes vides non écrites ; bloc Informations facultatif ; limite de
caractères sur la fiche entière. Indentation des modèles à l'écran seulement.
"""

import copy
import json
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt, QMimeData
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from src.services.export_config_service import DEFAULT_CONFIG, ExportConfigService
from src.services.html_export_service import HtmlExportService
from src.ui.champ_modele_html import ChampModeleHtml, compacter_html, formater_html
from src.ui.fiche_produit_service import FicheProduitService
from src.utils.fiche_produit_generator import FicheProduitGenerator

STANDARD = DEFAULT_CONFIG['fiche']['profiles'][0]
AVEC_INFOS = DEFAULT_CONFIG['fiche']['profiles'][1]


# ─── Assemblage ─────────────────────────────────────────────────────────────

def _fiche(profil=STANDARD, remplace=(), equivalentes=(), appareils="<div>A</div>", **reglages):
    vus = []

    def appareils_fn(reste):
        vus.append(reste)
        return appareils
    r = FicheProduitGenerator().generer(
        {**profil, **reglages}, "<h2>Titre</h2>", "<div>Marques</div>", "201050694",
        list(remplace), [list(l) for l in equivalentes], appareils_fn)
    return r, vus


def test_ordre_des_blocs_comme_la_fiche_type():
    r, _ = _fiche(AVEC_INFOS, remplace=["201050689"],
                  equivalentes=[["00627364"], ["481236068708", "C00301514"]])
    assert r['html'] == (
        '<h2>Titre</h2><div>Marques</div>'
        '<div class="class_perso3">Code produit : 201050694</div>'
        '<div class="class_perso3 class_perso6">Remplace les références : 201050689</div>'
        '<div class="class_perso3 class_perso6">Références équivalentes : 00627364</div>'
        '<div class="class_perso3 class_perso6">Références équivalentes : 481236068708 C00301514</div>'
        '<div>&nbsp;</div><div class="alert alert-info"><h3 class="alert-heading">Informations :</h3>'
        '<div>&nbsp;</div></div>'
        '<div>A</div>')


def test_lignes_sans_reference_non_ecrites():
    r, _ = _fiche()
    assert "Remplace" not in r['html']
    assert "équivalentes" not in r['html']
    assert "alert" not in r['html']


def test_separateur_et_echappement_des_references():
    r, _ = _fiche(remplace=["A<1>", "B"], separateur_references=", ")
    assert "Remplace les références : A&lt;1&gt;, B</div>" in r['html']


def test_limite_sur_la_fiche_entiere():
    r, vus = _fiche(max_caracteres=1000)
    entete = r['html'][:-len("<div>A</div>")]
    assert vus == [1000 - HtmlExportService.count_non_html_chars(entete)]
    _, vus = _fiche(max_caracteres=0)
    assert vus == [None]  # 0 = limite du profil HTML Détails


def test_limite_transmise_a_html_details():
    donnees = [("Four", "Bosch", "HBA1", "Serie 2", "", "X")] * 3
    complet = HtmlExportService.generate_html_details(donnees)
    assert HtmlExportService.generate_html_details(donnees, char_limit=None) == complet
    assert HtmlExportService.last_strategy_used == 'full'
    assert "Données trop volumineuses" in HtmlExportService.generate_html_details(donnees, char_limit=1)


# ─── Configuration ──────────────────────────────────────────────────────────

@pytest.fixture
def service(tmp_path, monkeypatch):
    chemin = tmp_path / "export_config.json"
    monkeypatch.setattr(ExportConfigService, "_resolve_config_path", staticmethod(lambda: str(chemin)))
    return ExportConfigService, chemin


def test_config_existante_sans_fiche_recoit_les_defauts(service):
    cls, chemin = service
    chemin.write_text(json.dumps({"titre": copy.deepcopy(DEFAULT_CONFIG['titre'])}), encoding="utf-8")
    svc = cls()
    assert svc.get_fiche_profile_names() == ["Fiche standard", "Fiche avec informations"]
    assert svc.get_default_fiche_profile_name() == "Fiche standard"
    assert svc.get_fiche_profile()['max_caracteres'] == 200000
    assert svc.get_fiche_profile("inconnue")['name'] == "Fiche standard"


def test_profils_fiche_nettoyes(service):
    cls, chemin = service
    chemin.write_text(json.dumps({"fiche": {"profiles": [
        {"name": "A", "max_caracteres": "abc", "inclure_informations": 1, "titre_profile": None},
        {"name": "A"}, {"pas": "de nom"},
    ], "default_profile": "absente"}}), encoding="utf-8")
    svc = cls()
    p = svc.get_fiche_profile("A")
    assert svc.get_fiche_profile_names() == ["A"]
    assert svc.get_default_fiche_profile_name() == "A"
    assert p['max_caracteres'] == 200000
    assert p['inclure_informations'] is True
    assert p['titre_profile'] == ""
    assert p['code_produit_template'] == STANDARD['code_produit_template']


# ─── Références liées ───────────────────────────────────────────────────────

class _Base:
    """201050694 ← 201050689 ; 481236068708 ← C00301514 ; 00627364 ; X (ancienne
    version isolée, remplaçante hors groupe) ; groupe d'équivalence commun."""
    PRED = {"201050694": ["201050689"], "481236068708": ["C00301514"]}
    HORS_CHAINE = {"201050694": ["481236068708", "00627364", "X"]}

    def get_all_predecessors(self, ref):
        return list(self.PRED.get(ref, []))

    def get_equivalents_hors_chaine(self, ref):
        return list(self.HORS_CHAINE.get(ref, []))


def _service(nb_appareils):
    fenetre = SimpleNamespace(
        db_manager=_Base(),
        seo_service=SimpleNamespace(
            _count_compatible_models=lambda refs: sum(nb_appareils.get(r, 0) for r in refs)))
    return FicheProduitService(fenetre)


def test_lignees_classees_par_nombre_d_appareils():
    svc = _service({"00627364": 227, "481236068708": 15, "C00301514": 5, "X": 20})
    remplace, lignees = svc.references_liees("201050694")
    assert remplace == ["201050689"]
    assert lignees == [["00627364"], ["481236068708", "C00301514"], ["X"]]


def test_egalite_par_ordre_alphabetique():
    svc = _service({})
    _, lignees = svc.references_liees("201050694")
    assert [l[0] for l in lignees] == ["00627364", "481236068708", "X"]


def test_reference_sans_lien():
    assert _service({}).references_liees("AUTRE") == ([], [])


# ─── Modèles HTML : indentation à l'écran, enregistrement inchangé ──────────

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def champ(app):
    c = ChampModeleHtml()
    c.resize(430, 30)
    c.show()
    app.processEvents()
    yield c
    c.close()


MODELES = (
    '<div>&nbsp;</div><div class="class_perso4">Appareils compatibles :</div>'
    '<div>&nbsp;</div><div class="class_perso5"><div>{appareils}</div></div>',
    '<div id="{marque}"><b><u>{marque}</u></b></div>',
    '<div class="class_perso2">Compatible avec {liens}</div>',
    '<div> </div><br><img src="x"/><p>a  b</p>',
    '{libelle} pour {type} {marques} - {reference}',
    '<h2 class="class_perso1">{libelle} pour {type} <span class="class_perso6">(photos non contractuelles)</span></h2>',
    *[p[k] for p in DEFAULT_CONFIG['fiche']['profiles'] for k in p if k.endswith('_template')],
)


@pytest.mark.parametrize("modele", MODELES)
def test_aller_retour_exact(champ, modele):
    assert compacter_html(formater_html(modele)) == modele
    champ.setText(modele)
    assert champ.text() == modele


def test_indentation_affichee(champ):
    champ.setText(MODELES[0])
    assert champ.toPlainText() == (
        '<div>&nbsp;</div>\n'
        '<div class="class_perso4">Appareils compatibles :</div>\n'
        '<div>&nbsp;</div>\n'
        '<div class="class_perso5">\n'
        '  <div>{appareils}</div>\n'
        '</div>')


def test_balises_de_mise_en_forme_en_ligne(champ):
    champ.setText('<div id="{marque}"><b><u>{marque}</u></b></div>')
    assert champ.toPlainText() == '<div id="{marque}">\n  <b><u>{marque}</u></b>\n</div>'
    champ.setText(MODELES[5])
    assert champ.toPlainText().endswith('(photos non contractuelles)</span>\n</h2>')


def test_entree_seulement_entre_deux_balises(champ):
    champ.setPlainText('<b>x</b><i>y</i>')  # comme tapé, avant réindentation
    champ.setFocus()
    champ.moveCursor(11)  # fin
    QTest.keyClick(champ, Qt.Key_Return)
    assert "\n" not in champ.toPlainText()
    curseur = champ.textCursor()
    curseur.setPosition(len('<b>x</b>'))
    champ.setTextCursor(curseur)
    QTest.keyClick(champ, Qt.Key_Return)
    assert champ.toPlainText() == '<b>x</b>\n<i>y</i>'
    assert champ.text() == '<b>x</b><i>y</i>'


def test_collage_html_indente(champ):
    champ.setText("")
    donnees = QMimeData()
    donnees.setText('<div>\n  <b>Bosch</b>\n</div>\nsuite\ntexte')
    champ.insertFromMimeData(donnees)
    assert champ.text() == '<div><b>Bosch</b></div> suite texte'


def test_indentation_refaite_en_quittant_la_zone(app, champ):
    champ.setText('<p>a</p>')
    champ.setFocus()
    champ.moveCursor(11)
    QTest.keyClicks(champ, '<p>b</p>')
    assert champ.toPlainText() == '<p>a</p><p>b</p>'
    champ.clearFocus()
    app.processEvents()
    assert champ.toPlainText() == '<p>a</p>\n<p>b</p>'
    assert champ.text() == '<p>a</p><p>b</p>'


# ─── Gabarit par défaut depuis l'aperçu ─────────────────────────────────────

def test_definir_profil_par_defaut(service):
    cls, _ = service
    svc = cls()
    assert svc.definir_profil_par_defaut('fiche', "Fiche avec informations")
    assert svc.definir_profil_par_defaut('html_details', "Format standard")
    assert cls().get_default_fiche_profile_name() == "Fiche avec informations"
    assert svc.definir_profil_par_defaut('fiche', "inconnue")  # repli sur le 1er
    assert cls().get_default_fiche_profile_name() == "Fiche standard"


# ─── Flèche des boutons à gabarits : clic = aperçu, ailleurs = export ───────

def test_fleche_clic_ouvre_l_apercu_sans_lancer_l_export(app):
    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QMenu, QToolButton
    from src.ui.ui_component_service import FlecheGabarits
    bouton = QToolButton()
    bouton.setText("Fiche complète")
    bouton.setStyleSheet("QToolButton::menu-button { width: 30px; }")
    bouton.setMenu(QMenu(bouton))
    bouton.setPopupMode(QToolButton.MenuButtonPopup)
    bouton.resize(300, 34)
    bouton.show()
    apercus, exports = [], []
    FlecheGabarits(bouton, lambda: apercus.append(1))
    bouton.clicked.connect(lambda: exports.append(1))
    QTest.mouseClick(bouton, Qt.LeftButton, pos=QPoint(290, 17))
    assert apercus == [1] and exports == []
    QTest.mouseClick(bouton, Qt.LeftButton, pos=QPoint(40, 17))
    assert apercus == [1] and exports == [1]
    bouton.close()


def test_fleche_clic_avec_menu_ouvert_au_survol(app):
    """Le survol a ouvert le menu : il capte la souris, le clic sur la flèche
    lui arrive et doit quand même ouvrir l'aperçu (sans exporter)."""
    from PyQt5.QtCore import QEvent, QPoint
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QMenu, QToolButton
    from src.ui.ui_component_service import FlecheGabarits
    bouton = QToolButton()
    bouton.setStyleSheet("QToolButton::menu-button { width: 30px; }")
    menu = QMenu(bouton)
    menu.addAction("Autre").setData("Autre")
    bouton.setMenu(menu)
    bouton.setPopupMode(QToolButton.MenuButtonPopup)
    bouton.resize(300, 34)
    bouton.show()
    apercus, exports = [], []
    fleche = FlecheGabarits(bouton, lambda: apercus.append(1))
    bouton.clicked.connect(lambda: exports.append(1))
    menu.installEventFilter(fleche)   # comme _ouvrir_menu avant showMenu()

    def clic_global(x):
        globale = bouton.mapToGlobal(QPoint(x, 17))
        return QMouseEvent(QEvent.MouseButtonPress, menu.mapFromGlobal(globale), globale,
                           Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    assert fleche.eventFilter(menu, clic_global(290)) is True
    app.processEvents()
    assert apercus == [1] and exports == []
    # Clic sur la partie principale, menu ouvert : laissé au menu (le ferme)
    assert fleche.eventFilter(menu, clic_global(40)) is False
    app.processEvents()
    assert apercus == [1] and exports == []
    bouton.close()


# ─── Préparation silencieuse (aperçu mis à jour pendant la saisie) ──────────

def test_refus_silencieux_sans_historique():
    from src.ui.seo_service import SEOService
    historique = []
    fenetre = SimpleNamespace(
        statusbar=SimpleNamespace(showMessage=lambda *a: historique.append(a)),
        user_interaction_service=SimpleNamespace(add_to_history=lambda *a, **k: historique.append(a)))
    seo = SEOService.__new__(SEOService)
    seo.main_window = fenetre
    seo._refus_silencieux, seo.raison_refus = True, None
    seo._signaler_refus("fiche", "X", "Libellé manquant")
    assert historique == [] and seo.raison_refus == "Libellé manquant"
    seo._refus_silencieux = False
    seo._signaler_refus("fiche", "X", "Libellé manquant")
    assert len(historique) == 2


# ─── Fenêtre d'aperçu ───────────────────────────────────────────────────────

class _SourceFactice:
    genre, libelle = 'fiche', "Fiche complète"

    def __init__(self):
        self.par_defaut, self.copies = "B", []

    def noms(self):
        return ["Profil 10", "B", "Profil 2"]

    def defaut(self):
        return self.par_defaut

    def contexte(self, interactif):
        return {'reference': "201050694"}

    def rendre(self, contexte, nom):
        return {'html': f"<div><b>{nom}</b></div>", 'resume': f"résumé {nom}"}

    def copier(self, contexte, nom):
        self.copies.append(nom)


def _fenetre_apercu(app, monkeypatch):
    from PyQt5.QtWidgets import QLineEdit
    import src.ui.apercu_export_dialog as module
    source = _SourceFactice()
    monkeypatch.setitem(module.SOURCES, 'fiche', lambda mw: source)
    mw = SimpleNamespace(search_input=QLineEdit("201050694"),
                         seo_service=SimpleNamespace(raison_refus=None))
    return module.ApercuExportDialog(mw, 'fiche', parent=None), source, mw


def test_apercu_liste_rendu_et_copie(app, monkeypatch):
    d, source, _ = _fenetre_apercu(app, monkeypatch)
    noms = [d.liste.item(i).text() for i in range(d.liste.count())]
    assert noms == ["★ B", "Profil 2", "Profil 10"]
    assert d.nom_courant() == "B"
    assert d.onglets.currentIndex() == 0  # Rendu
    assert d.code.toPlainText() == "<div>\n  <b>B</b>\n</div>"  # code indenté
    assert d.resume_label.text() == "résumé B"
    assert "201050694" in d.titre_label.text()
    d.filtre.setText("profil 2")
    assert d.nom_courant() == "Profil 2"
    d.filtre.setText("")
    d.liste.setCurrentRow(2)
    assert d.resume_label.text() == "résumé Profil 10"
    d.show()
    d.copier_btn.click()
    # Copier ferme l'aperçu : retour sur la fenêtre principale
    assert source.copies == ["Profil 10"]
    assert not d.isVisible()


def test_apercu_mis_a_jour_a_la_recherche(app, monkeypatch):
    d, source, mw = _fenetre_apercu(app, monkeypatch)
    vus = []
    source.contexte = lambda interactif: vus.append(interactif) or {'reference': mw.search_input.text()}
    mw.search_input.setText("00627364")
    d._minuterie.timeout.emit()
    assert vus == [False]
    assert "00627364" in d.titre_label.text()
    d.close()
