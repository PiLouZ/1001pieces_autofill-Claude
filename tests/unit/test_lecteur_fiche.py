"""
Lecteur de description de fiche produit (CDC import fiches site, étape 1)

Fiches d'exemple du § 11, enregistrées dans tests/fixtures/fiches_site/
(pages publiques du site, aucun accès réseau) :
- 7285  : pompe Whirlpool / Indesit, paire en code produit, 4 remplacements,
          2 lignes d'équivalentes, 16 marques, 1 840 lignes, table du site ;
- 20746 : régulateur Electrolux, 831 lignes, pas de table du site ;
- 20744 : balconnet BSH, 4 remplacements, 450 lignes.
"""

import copy
from pathlib import Path

import pytest

from src.services.export_config_service import DEFAULT_CONFIG
from src.services.html_export_service import HtmlExportService
from src.utils.fiche_produit_generator import FicheProduitGenerator
from src.utils.lecteur_fiche import (
    ean13_valide, extraire_description, id_product_depuis_url, lire_description,
    lire_page_publique, modeles_depuis_config, normaliser,
)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'fiches_site'

_CODE = '<div class="class_perso3">Code produit : {reference}</div>'
_REMPLACE = '<div class="class_perso3 class_perso6">Remplace les références : {references}</div>'
_EQUIV = '<div class="class_perso3 class_perso6">Références équivalentes : {references}</div>'
_INFOS = ('<div>&nbsp;</div><div class="alert alert-info"><h3 class="alert-heading">'
          'Informations :</h3><div>&nbsp;</div></div>')
_ENTETE = '<div id="{marque}"><b><u>{marque}</u></b></div>'


def _profil_fiche(nom, titre='H2', details='', infos=False):
    return {'name': nom, 'titre_profile': titre, 'details_profile': details,
            'inclure_informations': infos, 'code_produit_template': _CODE,
            'remplace_template': _REMPLACE, 'equivalentes_template': _EQUIV,
            'informations_template': _INFOS, 'separateur_references': ' ',
            'max_caracteres': 200000}


def _details(nom, wrapper):
    return {'name': nom, 'brand_header_template': _ENTETE,
            'model_line_template': '<div>{modele_complet}</div>',
            'group_separator': '<div>&nbsp;</div>', 'wrapper_template': wrapper,
            'char_limit': 195000}


# Configuration du même genre que celle de l'utilisateur (profils réels résumés)
CONFIG = {
    'titre': {'profiles': [
        {'name': 'H2', 'template': '<h2 class="class_perso1">{libelle} pour {type}</h2>'},
        {'name': 'H2 (photo non contractuelle)',
         'template': '<h2 class="class_perso1">{libelle} pour {type} '
                     '<span class="class_perso6">(photos non contractuelles)</span></h2>'},
    ], 'default_profile': 'H2'},
    'fiche': {'profiles': [
        _profil_fiche('Fiche standard'),
        _profil_fiche('Informations', infos=True),
        _profil_fiche('Photos NC', titre='H2 (photo non contractuelle)'),
        _profil_fiche('Liste NE', details='Liste non exhaustive'),
    ], 'default_profile': 'Fiche standard'},
    'html': {'details_profiles': [
        _details('Format standard',
                 '<div>&nbsp;</div><div class="class_perso4">Appareils compatibles :</div>'
                 '<div>&nbsp;</div><div class="class_perso5"><div>{appareils}</div></div>'),
        _details('Liste non exhaustive',
                 '<div>&nbsp;</div><div class="class_perso4">Appareils compatibles :</div>'
                 '<div class="class_perso6 pl-3">(liste non exhaustive)</div><div>&nbsp;</div>'
                 '<div class="class_perso5"><div>{appareils}</div></div>'),
    ], 'details_default_profile': 'Format standard'},
}
MODELES = modeles_depuis_config(CONFIG)


def _page(id_product):
    return (FIXTURES / f'produit_{id_product}.html').read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def pages():
    return {i: lire_page_publique(_page(i), modeles=MODELES) for i in (7285, 20746, 20744)}


# =============================================================================
# Fiches d'exemple (§ 11)
# =============================================================================

class TestFichesExemple:
    def test_7285_paire_remplacements_equivalentes(self, pages):
        d = pages[7285].description
        assert d.code_produit == ['481073071153', 'C00319033']
        assert d.reference_principale == '481073071153'
        assert d.remplace == ['C00535957', '488000535957', 'C00309416', '482000032568']
        # 2 lignes d'équivalentes, gardées séparément avec leur n° de ligne
        assert [(e.numero, e.references) for e in d.equivalentes] == \
            [(1, ['00145522']), (2, ['481949'])]

    def test_7285_liste(self, pages):
        d = pages[7285].description
        assert d.nb_lignes == 1840
        assert len(d.marques) == 16
        assert d.marques == d.marques_annoncees      # « Compatible avec » = sections
        premiere = d.appareils[0]
        assert (premiere.marque, premiere.ref_modele, premiere.nom, premiere.format) == \
            ('Balay', '3TL865/02', '3TL865', 'ref_nom')
        assert [a.numero for a in d.appareils[:3]] == [1, 2, 3]

    def test_20746_et_20744(self, pages):
        d = pages[20746].description
        assert d.code_produit == ['1113161010'] and d.nb_lignes == 831
        assert not d.remplace and not d.equivalentes
        d = pages[20744].description
        assert d.code_produit == ['11051894'] and d.nb_lignes == 450
        assert d.remplace == ['00703010', '00702570', '00701738', '00667780']
        assert d.marques == ['Bosch', 'Neff']

    @pytest.mark.parametrize('id_product', [7285, 20746, 20744])
    def test_lecture_complete_par_profil(self, pages, id_product):
        """Fiches produites par l'outil : tout est lu par un profil, rien n'est en doute."""
        d = pages[id_product].description
        assert d.profil is not None and not d.profil_ambigu
        assert set(d.sources.values()) == {'profil'}
        assert d.non_compris == []
        assert not d.liste_tronquee
        assert d.titre_liste == 'Appareils compatibles'

    def test_profil_departage_par_le_titre(self, pages):
        """« (photos non contractuelles) » dans le titre désigne le profil Photos NC."""
        assert pages[20746].description.profil == 'Photos NC'
        assert pages[7285].description.profil == 'Fiche standard'
        scores = {s.nom: s.score for s in pages[7285].description.scores}
        # code produit + remplace + 2 lignes d'équivalentes + titre de liste
        assert scores['Fiche standard'] == 5


class TestPagePublique:
    def test_donnees_du_produit(self, pages):
        attendu = {
            7285: (7285, '481073071153', '8015250275551', 'Pompe de vidange - Lave-linge'),
            20746: (20746, 'EL1113161010', '7321423021278', 'Pompe de vidange - Lave-vaisselle'),
            20744: (20744, 'GAU11051894', '', 'Etagère & balconnet - Réfrigérateur'),
        }
        for i, (id_product, ref, ean, categorie) in attendu.items():
            p = pages[i]
            assert (p.id_product, p.ref_interne, p.ean, p.categorie) == \
                (id_product, ref, ean, categorie)
            assert p.source_ref_interne == 'product-reference'
            assert p.ean_valide is (True if ean else None)
            assert p.non_compris == []

    def test_table_du_site(self, pages):
        p = pages[7285]
        assert p.table_presente and not p.table_complete
        # La page n'affiche que la 1ʳᵉ page de la table EveryParts
        assert (len(p.table_site), p.table_lignes_par_page, p.table_pages) == (20, 20, 92)
        t = p.table_site[0]
        assert (t.type_appareil, t.marque, t.ref_modele, t.nom) == \
            ('Lave-linge', 'Balay', '3TL865/02', '3TL865')
        assert not pages[20746].table_presente and pages[20746].table_site == []

    def test_caracteristiques(self, pages):
        assert pages[7285].caracteristiques["Type d'appareil"] == 'Lave-linge'

    def test_url_fournie_sans_lien_canonique(self):
        html = '<div class="product-description"><div class="class_perso3">Code produit : X1</div></div>'
        p = lire_page_publique(html, url='https://www.1001pieces.com/cat/123-nom.html')
        assert p.id_product == 123
        assert p.description.code_produit == ['X1']
        assert 'référence interne introuvable' in p.non_compris

    def test_description_courte_vide_ignoree(self):
        page = ('<div class="product-description text-muted"></div>'
                '<div class="product-description product-description--main">'
                '<div class="class_perso3">Code produit : 42</div></div>')
        assert 'Code produit : 42' in extraire_description(page)


def test_id_product_et_ean():
    assert id_product_depuis_url('https://x/cat/20746-regulateur-1113161010.html') == 20746
    assert id_product_depuis_url('https://x/index.php?controller=product&id_product=7285') == 7285
    assert id_product_depuis_url('https://x/contact') is None
    assert ean13_valide('8015250275551') and ean13_valide('7321423021278')
    assert not ean13_valide('8015250275552') and not ean13_valide('123')


# =============================================================================
# Normalisation (§ 4.3)
# =============================================================================

class TestNormalisation:
    def test_mise_en_forme_ignoree(self):
        a = normaliser('<div class="c">Code <b>produit</b> :&nbsp;&nbsp;<span style="x">A1</span></div>')
        b = normaliser('<div class="c"><strong>Code   produit :</strong> A1</div>')
        assert [(x.classes, x.texte) for x in a] == [(x.classes, x.texte) for x in b] == \
            [(frozenset({'c'}), 'Code produit : A1')]

    def test_br_coupe_les_blocs_et_parents(self):
        blocs = normaliser('<div class="class_perso5"><p>A - 1<br>B - 2</p></div>')
        assert [b.texte for b in blocs] == ['A - 1', 'B - 2']
        assert all('class_perso5' in b.classes_parents for b in blocs)

    def test_texte_colle(self):
        assert [b.texte for b in normaliser('Code produit : 1\n\nAEG\nX1 - Y')] == \
            ['Code produit : 1', 'AEG', 'X1 - Y']

    def test_scripts_ignores(self):
        assert [b.texte for b in normaliser('<div>A<script>var x="<div>"</script></div>')] == ['A']


# =============================================================================
# Repérage par texte, anciens formats (§ 4.5)
# =============================================================================

class TestRepliTexte:
    def test_ancienne_fiche_sans_classes(self):
        fiche = """<p><strong>Code produit:</strong> 00145522</p>
        <p>Remplace la référence : 00123456</p>
        <p><b>Appareils employant cette pièce :</b></p>
        <p><b>Bosch</b></p>
        <p>WFL2060/01 Maxx WFL2060</p>
        <p>WAE24420FF/23 - Maxx 7</p>
        <p><b>AEG</b></p>
        <p>91138401000 91138401001 91138401002</p>"""
        d = lire_description(fiche, MODELES, marques_connues=['Bosch', 'AEG'])
        assert d.code_produit == ['00145522']
        assert d.remplace == ['00123456']
        assert d.titre_liste == 'Appareils employant cette pièce'
        assert d.sources == {'code_produit': 'texte', 'remplace': 'texte',
                             'titre_liste': 'texte'}
        # Libellés tels que lus : variantes à rapporter par la mesure
        assert d.libelles == {'code_produit': 'Code produit:',
                              'remplace': 'Remplace la référence :',
                              'titre_liste': 'Appareils employant cette pièce :'}
        assert [(a.marque, a.ref_modele, a.nom, a.format) for a in d.appareils] == [
            ('Bosch', 'WFL2060/01', 'Maxx WFL2060', 'bsh'),
            ('Bosch', 'WAE24420FF/23', 'Maxx 7', 'ref_nom'),
            ('AEG', '91138401000', '', 'pnc'),
            ('AEG', '91138401001', '', 'pnc'),
            ('AEG', '91138401002', '', 'pnc'),
        ]
        assert d.non_compris == []

    def test_sans_modele(self):
        d = lire_description('<div>Code produit : A B</div><div>Appareils compatibles :</div>'
                             '<div id="Rex">Rex</div><div>X - Y</div>')
        assert d.profil is None and d.scores == []
        assert d.code_produit == ['A', 'B'] and d.appareils[0].marque == 'Rex'

    def test_configuration_par_defaut_sans_titre_de_liste(self):
        """Profil par défaut (enveloppe {appareils} seule) : titre trouvé par le texte."""
        modeles = modeles_depuis_config(copy.deepcopy(DEFAULT_CONFIG))
        d = lire_description(_page_description(7285), modeles)
        assert d.nb_lignes == 1840 and d.sources['titre_liste'] == 'texte'
        assert d.sources['code_produit'] == 'profil'

    def test_marque_inconnue_et_lignes_non_lues(self):
        d = lire_description('<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div>X1 - avant marque</div><div>Zanussi</div><div>Z1 - Z</div>'
                             '<div>???</div>')
        natures = [n.nature for n in d.non_compris]
        assert 'appareil_sans_marque' in natures
        assert 'marque_inconnue' in natures       # ni id, ni annoncée, ni connue
        assert d.appareils[1].marque == 'Zanussi'

    def test_bloc_entete_non_lu(self):
        """Texte libre de l'en-tête gardé à part ; signalé seulement s'il parle de références."""
        d = lire_description('<div class="class_perso1">Pompe</div><div>Code produit : 1</div>'
                             '<div class="class_perso6">Longueur : 120 mm</div>'
                             '<table class="ve"><tr><td>AFC221</td></tr></table>'
                             '<div>Référence fournisseur 2024</div>'
                             '<div>Appareils compatibles :</div>')
        assert d.titre == 'Pompe'
        assert d.textes_libres == ['Longueur : 120 mm', 'AFC221']
        assert [(n.nature, n.texte) for n in d.non_compris] == \
            [('bloc_non_lu', 'Référence fournisseur 2024')]

    def test_marque_annoncee_absente(self):
        d = lire_description('<div class="class_perso2">Compatible avec <a>AEG</a> <a>Rex</a></div>'
                             '<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div id="AEG">AEG</div><div>A - B</div>')
        assert [(n.nature, n.texte) for n in d.non_compris] == [('marque_annoncee_absente', 'Rex')]


def _page_description(id_product):
    return extraire_description(_page(id_product))


# =============================================================================
# Profils (§ 4.2)
# =============================================================================

class TestProfils:
    def test_profil_ambigu(self):
        """Deux profils de lecture différente, même score : ambigu, signalé."""
        config = copy.deepcopy(CONFIG)
        autre = _profil_fiche('Autre remplace')
        autre['remplace_template'] = '<div class="class_perso3">Anciennes réf. : {references}</div>'
        config['fiche']['profiles'] = [config['fiche']['profiles'][0], autre]
        d = lire_description(_page_description(20746), modeles_depuis_config(config))
        assert d.profil_ambigu
        assert 'profil_ambigu' in [n.nature for n in d.non_compris]
        assert 'lecture_divergente' not in [n.nature for n in d.non_compris]

    def test_liste_non_exhaustive(self):
        fiche = ('<div class="class_perso3">Code produit : 1</div>'
                 '<div class="class_perso4">Appareils compatibles :</div>'
                 '<div class="class_perso6 pl-3">(liste non exhaustive)</div>'
                 '<div class="class_perso5"><div><div id="AEG">AEG</div><div>A - B</div></div></div>')
        d = lire_description(fiche, MODELES, marques_connues=['AEG'])
        assert d.liste_non_exhaustive and d.profil == 'Liste NE'
        assert d.non_compris == []

    def test_informations(self):
        fiche = ('<div class="class_perso3">Code produit : 1</div>' + _INFOS.replace(
            '<div>&nbsp;</div></div>', '<div>Largeur : 3 cm</div></div>') +
            '<div class="class_perso4">Appareils compatibles :</div>'
            '<div class="class_perso5"><div id="AEG">AEG</div><div>A - B</div></div>')
        d = lire_description(fiche, MODELES, marques_connues=['AEG'])
        assert d.profil == 'Informations'
        assert d.informations == ['Informations :', 'Largeur : 3 cm']
        assert d.nb_lignes == 1 and d.non_compris == []


# =============================================================================
# Liste tronquée (§ 4.6)
# =============================================================================

class TestListeTronquee:
    def _tete(self):
        return ('<div class="class_perso3">Code produit : 1</div>'
                '<div class="class_perso4">Appareils compatibles :</div>')

    def test_message_trop_volumineux(self):
        d = lire_description(self._tete() + "<p>Données trop volumineuses pour l'affichage</p>",
                             MODELES)
        assert d.liste_tronquee and 'message_trop_volumineux' in d.motifs_troncature

    def test_lignes_sans_nom(self):
        """Repli de l'export « réf. seule » : toutes les lignes sans nom commercial."""
        lignes = ''.join(f'<div>REF{i}</div>' for i in range(25))
        d = lire_description(self._tete() + '<div id="AEG">AEG</div>' + lignes, MODELES)
        assert d.nb_lignes == 25 and d.liste_tronquee
        assert d.motifs_troncature == ['lignes_sans_nom']

    def test_derniere_marque_vide_et_limite(self):
        config = copy.deepcopy(CONFIG)
        for p in config['fiche']['profiles']:
            p['max_caracteres'] = 82        # fiche de 80 caractères visibles
        fiche = self._tete() + '<div id="AEG">AEG</div>' + '<div>A1 - B1</div>' * 5 + \
            '<div id="Rex">Rex</div>'
        d = lire_description(fiche, modeles_depuis_config(config))
        assert d.liste_tronquee
        assert set(d.motifs_troncature) == {'derniere_marque_vide', 'longueur_proche_limite'}

    def test_fiche_complete_non_tronquee(self, pages):
        assert not pages[7285].description.liste_tronquee


# =============================================================================
# Aller-retour avec l'export « Fiche complète »
# =============================================================================

def test_aller_retour_fiche_complete():
    """Une fiche produite par l'outil se relit à l'identique."""
    profil = CONFIG['fiche']['profiles'][0]
    details = CONFIG['html']['details_profiles'][0]
    donnees = {'Whirlpool': [{'ref_modele': '8573', 'commercial_ref': 'AWE 6222', 'other_ref': ''},
                             {'ref_modele': '8574', 'commercial_ref': '', 'other_ref': ''}],
               'Indesit': [{'ref_modele': 'IWC 71252', 'commercial_ref': 'IWC', 'other_ref': ''}]}

    def appareils(_limite):
        contenu = HtmlExportService._generate_html_content_with_strategy(donnees, 'full', details)
        return HtmlExportService.wrap_details(contenu, details['wrapper_template'])

    fiche = FicheProduitGenerator().generer(
        profil, '<h2 class="class_perso1">Pompe pour lave-linge</h2>',
        '<div class="class_perso2">Compatible avec <a href="#Indesit">Indesit</a> '
        '<a href="#Whirlpool">Whirlpool</a></div>',
        '481073071153', ['C00535957', '488000535957'], [['00145522'], ['C00319033']],
        appareils)['html']
    d = lire_description(fiche, MODELES)
    assert d.profil == 'Fiche standard' and d.non_compris == []
    assert d.code_produit == ['481073071153']
    assert d.remplace == ['C00535957', '488000535957']
    # Aujourd'hui l'export met toutes les équivalentes sur UNE ligne (§ 8.1)
    assert [e.references for e in d.equivalentes] == [['00145522', 'C00319033']]
    assert [(a.marque, a.ref_modele, a.nom, a.format) for a in d.appareils] == [
        ('Indesit', 'IWC 71252', 'IWC', 'ref_nom'),
        ('Whirlpool', '8573', 'AWE 6222', 'ref_nom'),
        ('Whirlpool', '8574', '', 'ref_seule'),
    ]


def test_script_de_mesure(tmp_path):
    """Le script de mesure lit un export CSV et rapporte la part lue correctement."""
    import csv
    import importlib.util
    import json
    import sys as _sys
    chemin = Path(__file__).resolve().parents[2] / 'scripts' / 'mesurer_lecteur_fiches.py'
    spec = importlib.util.spec_from_file_location('mesurer_lecteur_fiches', chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    export = tmp_path / 'produits.csv'
    with open(export, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
        w.writerow(['id_produit', 'reference', 'nom_produit', 'marque', 'ean', 'categorie',
                    'actif', 'description'])
        w.writerow([20746, 'EL1113161010', 'x', '', '', '', 1, _page_description(20746)])
        w.writerow([2, '', 'x', '', '', '', 1, '<p>Sans liste</p>'])
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(CONFIG), encoding='utf-8')
    rapport_md, detail = tmp_path / 'rapport.md', tmp_path / 'detail.csv'
    argv = _sys.argv
    _sys.argv = ['x', str(export), '--config', str(config), '--rapport', str(rapport_md),
                 '--detail', str(detail)]
    try:
        module.main()
    finally:
        _sys.argv = argv
    texte = rapport_md.read_text(encoding='utf-8')
    assert '**Descriptions avec liste : 1**, 831 lignes' in texte
    assert '**Lues correctement : 1 (100.0 %)**' in texte
    assert 'préfixée 1' in texte


# =============================================================================
# Variantes relevées sur les 13 302 descriptions du site (2026-11-12)
# =============================================================================

class TestVariantesDuSite:
    def test_montage_sur_une_marque_sans_entete(self):
        """Ancienne fiche : « Montage sur Whirlpool », 12NC sans en-tête de marque."""
        d = lire_description(
            '<div class="class_perso2">Montage sur Whirlpool</div>'
            '<div class="class_perso3">Code produit : 481244069288</div>'
            '<div class="class_perso4">Appareils employant cette pièce :</div>'
            '<div class="class_perso5">854970043000<div>854970110002 854970110003</div>'
            '<div>AFG7010</div></div>', MODELES)
        assert d.marques_annoncees == ['Whirlpool']
        assert [(a.marque, a.source_marque, a.ref_modele, a.format) for a in d.appareils] == [
            ('Whirlpool', 'annonce', '854970043000', 'ref_seule'),
            ('Whirlpool', 'annonce', '854970110002', 'pnc'),
            ('Whirlpool', 'annonce', '854970110003', 'pnc'),
            ('Whirlpool', 'annonce', 'AFG7010', 'ref_seule'),
        ]
        assert d.non_compris == [] and not d.liste_tronquee   # ancienne fiche : pas un repli

    def test_montage_sur_plusieurs_marques(self):
        d = lire_description('<div>Montage sur Bosch Siemens, De Dietrich et Sauter</div>'
                             '<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div>WAE1 - X</div>',
                             marques_connues=['Bosch', 'Siemens', 'De Dietrich', 'Sauter'])
        assert d.marques_annoncees == ['Bosch', 'Siemens', 'De Dietrich', 'Sauter']
        # Plusieurs marques annoncées : marque à déduire au rapprochement (étape 2)
        assert (d.appareils[0].marque, d.appareils[0].source_marque) == (None, 'annonces')
        assert [n.nature for n in d.non_compris] == ['marque_a_deduire']

    def test_compatible_toutes_marques(self):
        d = lire_description('<div class="class_perso2">Compatible toutes marques</div>'
                             '<div>Code produit : 1</div>')
        assert d.toutes_marques and d.marques_annoncees == [] and d.textes_libres == []

    def test_references_par_marque(self):
        d = lire_description(
            '<div class="class_perso2">Montage sur Stiebel Eltron</div>'
            '<div class="class_perso3">Code produit : 151967</div>'
            "<div class=\"class_perso4\">Référence(s) de l'article par marque</div>"
            '<div class="class_perso5">Stiebel Eltron Réf. fabricant : 0151967</div>'
            '<div class="class_perso5">Bosch</div><div class="class_perso5">Réf. fabricant : 00123 00456</div>',
            marques_connues=['Stiebel Eltron', 'Bosch'])
        assert [(e.origine, e.references) for e in d.references_par_marque] == [
            ('Stiebel Eltron', ['0151967']), ('Bosch', ['00123', '00456'])]
        assert d.appareils == [] and d.marques == []
        assert d.non_compris == []

    def test_type_en_fin_et_sur_la_ligne_suivante(self):
        d = lire_description(
            '<div>Montage sur Whirlpool</div><div>Code produit : 1</div>'
            '<div>Appareils employant cette pièce</div>'
            '<div>851354038000 KOXS6630 Four Vapeur</div><div>851354038001 KOXS6630</div>'
            '<div>Four Vapeur</div><div>Lave-linge</div><div>WAE1/04 WAE1</div>',
            marques_connues=['Whirlpool'], types_connus=['Four Vapeur', 'Lave-linge'])
        assert [(a.ref_modele, a.nom, a.format, a.type_ligne) for a in d.appareils] == [
            ('851354038000', 'KOXS6630', 'pnc_nom', 'Four Vapeur'),
            ('851354038001', 'KOXS6630', 'pnc_nom', 'Four Vapeur'),
            ('WAE1/04', 'WAE1', 'bsh', 'Lave-linge'),       # type en tête de section
        ]
        assert d.non_compris == []

    def test_bloc_d_extension_de_navigateur_ignore(self):
        d = lire_description('<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div id="AEG">AEG</div><div>A - B</div>'
                             '<div id="sconnect-is-installed">2.12.0.0</div>',
                             marques_connues=['AEG'])
        assert d.nb_lignes == 1 and d.non_compris == []

    def test_dimensions_apres_la_liste(self):
        d = lire_description('<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div id="AEG">AEG</div><div>A - B</div>'
                             '<div class="class_perso4">Dimensions :</div>'
                             '<div>Longueur : 9 mm</div>', marques_connues=['AEG'])
        assert d.textes_libres == ['Dimensions :', 'Longueur : 9 mm']
        assert d.non_compris == []

    def test_decouper_marques_sans_marques_connues(self):
        from src.utils.lecteur_fiche.lecteur import decouper_marques
        assert decouper_marques('Bosch Siemens, Neff', set()) == (['Bosch', 'Siemens', 'Neff'], [])

    @pytest.mark.parametrize('titre', [
        'Appareil compatibles :', 'Appareils compatible :', 'Appareils comaptibles :',
        'Appareil(s) employant cette pièce:', 'Appareils employant ce thermostat :',
        'Appareils utilisant ces sacs :', 'Références commerciales employant cette pièce :',
        "Référence(s) de l'article pour modèles :",
    ])
    def test_variantes_de_titre(self, titre):
        d = lire_description(f'<div>Code produit : 1</div><div>{titre}</div>'
                             '<div id="AEG">AEG</div><div>A - B</div>', marques_connues=['AEG'])
        assert d.titre_liste == titre.rstrip(' :') and d.nb_lignes == 1
        assert d.non_compris == []

    @pytest.mark.parametrize('titre', [
        'Appareils compatibles (liste non-exhaustive) :',
        'Appareils compatibles : (Liste non exhaustive !)',
        'Appareils employant cette pièce (liste non exhaustive)',
    ])
    def test_titre_non_exhaustif(self, titre):
        d = lire_description(f'<div>Code produit : 1</div><div>{titre}</div>'
                             '<div id="AEG">AEG</div><div>A - B</div>', marques_connues=['AEG'])
        assert d.liste_non_exhaustive and d.nb_lignes == 1 and d.non_compris == []

    def test_remplace_produits_suivants_et_reference_ego(self):
        d = lire_description('<div>Compatible Airforce</div><div>Code produit : 1</div>'
                             '<div>Remplace les produits suivants : 11 22</div>'
                             '<div>Référence EGO : 55.13059.010 5513059010</div>')
        assert d.marques_annoncees == ['Airforce']
        assert d.remplace == ['11', '22']
        assert [(e.origine, e.references) for e in d.references_par_marque] == \
            [('EGO', ['55.13059.010', '5513059010'])]
        assert d.non_compris == []

    def test_points_de_suite(self):
        d = lire_description('<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div id="AEG">AEG</div><div>A - B</div><div>...</div>',
                             marques_connues=['AEG'])
        assert d.liste_tronquee and d.motifs_troncature == ['points_de_suite']

    def test_remplacee_par(self):
        d = lire_description('<div>Code produit : 1</div>'
                             '<div>Remplacé par la référence : 4810001</div>')
        assert d.remplacee_par == ['4810001'] and d.remplace == [] and d.non_compris == []

    def test_marques_sans_accents_ni_casse(self):
        d = lire_description('<div>Code produit : 1</div><div>Appareils compatibles :</div>'
                             '<div>Scholtes</div><div>A - B</div>', marques_connues=['Scholtès'])
        assert d.appareils[0].marque == 'Scholtes' and d.non_compris == []

    def test_marque_du_produit_sans_annonce(self):
        """Aucune annonce : les marques connues du produit deviennent les candidates."""
        fiche = '<div>Code produit : 1</div><div>Appareils compatibles :</div><div>G595 - G 595</div>'
        d = lire_description(fiche, marques_connues=['Miele'], marque_produit='Miele')
        assert (d.source_annonce, d.appareils[0].marque, d.appareils[0].source_marque) == \
            ('produit', 'Miele', 'annonce')
        d = lire_description(fiche, marques_connues=['Whirlpool', 'Ignis'],
                             marque_produit='Whirlpool Laden Ignis')
        assert d.marques_annoncees == ['Whirlpool', 'Ignis']
        assert [n.nature for n in d.non_compris] == ['marque_a_deduire']
        # Marque du produit inconnue (« 1001pièces ») : pas une candidate
        d = lire_description(fiche, marques_connues=['Miele'], marque_produit='1001pièces')
        assert d.marques_annoncees == [] and d.appareils[0].marque is None


def test_ref_fabricant_suivie_de_texte():
    """« Réf. fabricant : 10/1863-5010 POUR APPAREILS VN606E » (étape 4, produit 7089) :
    seule la référence de tête est une référence de la pièce ; la suite est signalée."""
    html = ('<div class="class_perso3">Code produit : 481225988048</div>'
            '<div class="class_perso4">Appareils employant cette pièce</div>'
            '<div class="class_perso5">Bauknecht Réf. fabricant : 10/1863-5010 POUR APPAREILS VN606E</div>')
    lecture = lire_description(html, MODELES, ['Bauknecht'])
    assert [e.references for e in lecture.references_par_marque] == [['10/1863-5010']]
    assert [(n.nature, n.detail) for n in lecture.non_compris] == [('bloc_non_lu', 'POUR APPAREILS VN606E')]
