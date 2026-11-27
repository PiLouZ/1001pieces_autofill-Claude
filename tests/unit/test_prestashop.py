"""Webservice PrestaShop : client (authentification, User-Agent, erreurs),
référentiels, anti-doublon et corps XML de la création (src/utils/prestashop/).
Sans réseau ni Qt."""

import base64
import json

import pytest

from src.utils.agora.fiche import FicheSite
from src.utils.prestashop.client import USER_AGENT, ClientPrestaShop, ErreurPrestaShop, lire_config
from src.utils.prestashop.site import Referentiels, SitePrestaShop, lien_reecrit, xml_produit


class _Transport:
    """Réponses par ressource (début du chemin après /api/)."""
    def __init__(self, reponses):
        self.reponses, self.appels = reponses, []

    def __call__(self, methode, url, entetes, corps):
        self.appels.append((methode, url, entetes, corps))
        chemin = url.split('/api/', 1)[1]
        for debut, (code, donnees) in self.reponses.items():
            if chemin.startswith(debut):
                return code, json.dumps(donnees).encode() if not isinstance(donnees, bytes) else donnees
        return 200, b'[]'


def test_config(tmp_path):
    (tmp_path / 'prestashop.env').write_text('PS_URL=https://dev.1001pieces.com/\nPS_KEY="ABC"\n')
    assert lire_config(str(tmp_path)) == ('https://dev.1001pieces.com', 'ABC')


def test_client_entetes_et_erreur():
    t = _Transport({'products': (401, {'errors': [{'code': 26, 'message': 'non autorisé'}]})})
    c = ClientPrestaShop('https://dev.1001pieces.com', 'CLE', t)
    with pytest.raises(ErreurPrestaShop, match='non autorisé'):
        c.lister('products')
    _m, url, entetes, _c = t.appels[0]
    assert entetes['User-Agent'] == USER_AGENT                       # Cloudflare refuse « Python-urllib »
    assert entetes['Authorization'] == 'Basic ' + base64.b64encode(b'CLE:').decode()
    assert 'CLE' not in url and 'output_format=JSON' in url
    assert c.environnement == 'dev'
    assert ClientPrestaShop('https://www.1001pieces.com', 'x', t).environnement == 'production'


def test_anti_doublon():
    t = _Transport({'products': (200, {'products': [
        {'id': 19917, 'reference': 'GAU748045', 'active': '1', 'name': 'Balconnet'},
        {'id': 5, 'reference': 'GAU7480451', 'active': '1', 'name': 'Autre'}]})})
    site = SitePrestaShop(ClientPrestaShop('https://dev.1001pieces.com', 'x', t))
    trouves = site.produits_existants(['748045', '748045', 'ABC'])
    assert [(p.id, p.reference, p.actif) for p in trouves] == [(19917, 'GAU748045', True)]
    assert len(t.appels) == 1                       # doublons et références trop courtes écartés
    assert 'filter%5Breference%5D=%[748045]%' in t.appels[0][1] or 'filter[reference]=%[748045]%' in t.appels[0][1]


def test_type_appareil_du_site():
    r = Referentiels(types_appareil={'Plaque de cuisson': 3592, 'Réfrigérateur': 3596, 'Four': 3590})
    assert r.id_type_appareil('Réfrigérateur') == 3596
    assert r.id_type_appareil('Plaque') == 3592
    assert r.id_type_appareil('Hotte') is None


def test_xml_creation():
    f = FicheSite(code='SCS866459', nom='Relais pour réfrigérateur Beko - C00866459', libelle='Relais',
                  reference='C00866459', prix_ttc=29.6, description='<h2>Relais</h2>]]>',
                  meta_title='Relais', meta_description='Relais réfrigérateur')
    xml = xml_produit(f, 157, 6, [(47, 3596), (42, 366)],
                      {'id_tax_rules_group': '9', 'delivery_out_stock': 'Sous 10 jours'})
    assert '<active><![CDATA[0]]></active>' in xml                       # toujours désactivée
    assert '<price><![CDATA[24.666667]]></price>' in xml
    assert '<reference><![CDATA[SCS866459]]></reference>' in xml
    assert '<id_tax_rules_group><![CDATA[9]]></id_tax_rules_group>' in xml
    assert 'relais-pour-refrigerateur-beko-c00866459' in xml
    assert '<category><id>157</id></category>' in xml
    assert '<id>47</id><id_feature_value>3596</id_feature_value>' in xml
    assert ']]]]><![CDATA[>' in xml                                       # CDATA protégé
    assert 'Sous 10 jours' in xml


def test_lien_reecrit():
    assert lien_reecrit("Étagère porte-bouteilles pour réfrigérateur - 00748045") == \
        'etagere-porte-bouteilles-pour-refrigerateur-00748045'


def test_creation_cover_refusee():
    def t(methode, url, entetes, corps):
        if '/images/' in url:
            return 500, b'<message><![CDATA[Erreur image]]></message>'
        return (201, json.dumps({'product': {'id': 77}}).encode()) if methode == 'POST' else (200, b'[]')
    site = SitePrestaShop(ClientPrestaShop('https://dev.1001pieces.com', 'x', t))
    site._referentiels = Referentiels(modele={'id_tax_rules_group': '9'})
    f = FicheSite(code='SCS866459', nom='x', libelle='x', reference='C00866459', prix_ttc=10)
    assert site.creer_fiche(f, 157, 6, [], b'jpg') == (77, 'POST images/products/77 : Erreur image')


def test_creation_refusee_si_code_existe():
    t = _Transport({'products': (200, {'products': [{'id': 1}]})})
    site = SitePrestaShop(ClientPrestaShop('https://dev.1001pieces.com', 'x', t))
    f = FicheSite(code='SCS866459', nom='x', libelle='x', reference='C00866459', prix_ttc=10)
    with pytest.raises(ValueError, match='existe déjà'):
        site.creer_fiche(f, 157, 6, [], None)
    assert all(m == 'GET' for m, *_ in t.appels)


# --- Mise à jour d'une fiche en ligne -------------------------------------------------------

import xml.etree.ElementTree as ET  # noqa: E402

from src.utils.prestashop.site import appliquer_blocs, comparer  # noqa: E402

_XML_PRODUIT = """<?xml version="1.0" encoding="UTF-8"?>
<prestashop xmlns:xlink="http://www.w3.org/1999/xlink"><product>
<id><![CDATA[19923]]></id><manufacturer_name><![CDATA[Electrolux]]></manufacturer_name>
<quantity><![CDATA[0]]></quantity><id_category_default><![CDATA[105]]></id_category_default>
<price><![CDATA[36.250000]]></price><active><![CDATA[1]]></active>
<name><language id="1"><![CDATA[Ancien nom]]></language></name>
<link_rewrite><language id="1"><![CDATA[ancien-nom]]></language></link_rewrite>
<description><language id="1"><![CDATA[<p>retouchée à la main</p>]]></language></description>
<meta_title><language id="1"><![CDATA[Ancien titre]]></language></meta_title>
<meta_description><language id="1"><![CDATA[Ancienne desc]]></language></meta_description>
<associations><categories><category><id><![CDATA[105]]></id></category><category><id><![CDATA[2]]></id></category></categories></associations>
</product></prestashop>"""


def _fiche_maj():
    return FicheSite(code='EL140005565027', nom='Nouveau nom', libelle='Fermeture', reference='140005565027',
                     prix_ttc=45.0, categorie='Divers - Lave-linge', description='<p>outil</p>',
                     meta_title='Nouveau titre', meta_description='Ancienne desc')


def test_comparer_blocs():
    produit = {'name': 'Ancien nom', 'description': '<p>outil</p>', 'meta_title': 'Ancien titre',
               'meta_description': 'Ancienne desc', 'price': '37.500000'}
    blocs = {b.cle: b for b in comparer(produit, _fiche_maj(), 'Divers - Lave-linge')}
    assert blocs['nom'].different and blocs['metas'].different
    assert not blocs['description'].different and not blocs['prix'].different
    assert not blocs['categorie'].different
    assert blocs['prix'].avant == '45,00 € TTC (37,50 € HT)'


def test_appliquer_blocs_choisis_seulement():
    racine = ET.fromstring(_XML_PRODUIT)
    appliquer_blocs(racine, _fiche_maj(), ['nom', 'prix', 'categorie'], 109)
    p = racine.find('product')
    assert p.findtext('name/language') == 'Nouveau nom'
    assert p.findtext('link_rewrite/language') == 'ancien-nom'                  # l'URL ne bouge pas
    assert p.findtext('description/language') == '<p>retouchée à la main</p>'  # bloc non coché
    assert p.findtext('meta_title/language') == 'Ancien titre'
    assert p.findtext('price') == '37.500000' and p.findtext('active') == '1'
    assert p.findtext('id_category_default') == '109'
    assert [c.findtext('id') for c in p.find('associations/categories')] == ['2', '109']


def test_modifier_retire_les_champs_en_lecture_seule():
    envois = []

    def t(methode, url, entetes, corps):
        envois.append((methode, url, corps))
        return 200, b''
    c = ClientPrestaShop('https://dev.1001pieces.com', 'x', t)
    c.modifier('products', 19923, ET.fromstring(_XML_PRODUIT))
    methode, url, corps = envois[0]
    assert methode == 'PUT' and url.endswith('/api/products/19923')
    assert b'manufacturer_name' not in corps and b'<quantity>' not in corps and b'Ancien nom' in corps
