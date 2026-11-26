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


def test_creation_refusee_si_code_existe():
    t = _Transport({'products': (200, {'products': [{'id': 1}]})})
    site = SitePrestaShop(ClientPrestaShop('https://dev.1001pieces.com', 'x', t))
    f = FicheSite(code='SCS866459', nom='x', libelle='x', reference='C00866459', prix_ttc=10)
    with pytest.raises(ValueError, match='existe déjà'):
        site.creer_fiche(f, 157, 6, [], None)
    assert all(m == 'GET' for m, *_ in t.appels)
