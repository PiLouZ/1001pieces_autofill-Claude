"""Branchement Agora : fichiers MySpace, quota et cache de l'API, conversion en
lignes d'import, prix et code EMG (src/utils/agora/). Sans réseau ni Qt."""

import json
import zipfile

import pytest

from src.utils.agora.client import (APPAREILS, INFO, ClientAgora, ErreurAgora, QuotaEpuise)
from src.utils.agora.conversion import (ENTETES, code_emg_propose, libelle_piece,
                                        lignes_appareils, marque_canonique,
                                        marque_dans_designation, prix_emg,
                                        type_depuis_designation)
from src.utils.agora.myspace import (COMMANDABLE, FIN_DE_VIE, FamillesMySpace, charger_dossier,
                                     etat_piece, fichiers_myspace)
from src.utils.agora.stockage import BaseAgora, cle_ref


def _piece(ref, liee, designation, cmd, statut):
    return f"{ref:<18}{liee:<18}{designation:<32}{cmd}{statut:<18}"


def _produit(tech, com, code, marque, designation):
    return f"{tech:<18}{com:<18}{code:<4}{marque:<48}FR{designation:<40}"


@pytest.fixture
def base(tmp_path):
    return BaseAgora(str(tmp_path / 'agora.db'))


@pytest.fixture
def myspace(tmp_path, base):
    dossier = tmp_path / 'myspace'
    dossier.mkdir()
    pieces = [
        _piece('481010000001', '481010000002', 'POMPE VIDANGE', 0, 'Remplacée'),
        _piece('481010000002', '481010000003', 'POMPE VIDANGE', 0, 'Abandonnée'),
        _piece('481010000003', '', 'Pompe de vidange', 1, 'Disponible'),
        _piece('481010000009', '481010000002', 'POMPE', 0, 'Abandonnée'),
        _piece('C00999999', '', 'Autre', 1, 'Disponible'),
        _piece('C00111111', '481299999990', 'Joint', 0, 'Abandonnée'),
        _piece('481299999990', '', 'ARTICLE EPUISE', 1, 'Disponible'),
    ]
    with zipfile.ZipFile(dossier / 'Parts_2.zip', 'w') as z:
        z.writestr('Parts_2.txt', '\r\n'.join(pieces).encode('latin-1'))
    (dossier / 'Products_2.txt').write_bytes('\r\n'.join([
        _produit('859991234567', 'AWO 1234', '5', 'Whirlpool', 'Lave-linge frontal'),
        _produit('855555555555', 'CIG546 W', '04', 'SCHOLTES', 'Cuisiniere électrique'),
        _produit('850000000000', 'XYZ', '5', 'Autres marques', 'Divers'),
    ]).encode('latin-1'))
    # Beko (17) : la même référence, remplacée, alors que la ligne Whirlpool est vide
    (dossier / 'Parts_17.txt').write_bytes('\r\n'.join([
        _piece('4346040285', 'C00866459', 'RELAIS', 1, 'Abandonnée'),
        _piece('C00866459', '', 'RELAIS', 1, 'disponible'),
    ]).encode('latin-1'))
    pieces.append(_piece('4346040285', '', '', 0, ''))
    with zipfile.ZipFile(dossier / 'Parts_2.zip', 'w') as z:
        z.writestr('Parts_2.txt', '\r\n'.join(pieces).encode('latin-1'))
    comptes = charger_dossier(base, str(dossier))
    assert comptes == {'Parts_2.zip': 8, 'Parts_17.txt': 2, 'Products_2.txt': 3}
    return FamillesMySpace(base)


def test_fichiers_txt_prioritaire(tmp_path):
    (tmp_path / 'Parts_3.zip').write_bytes(b'')
    (tmp_path / 'Parts_3.txt').write_text('')
    (tmp_path / 'List_Reseller.txt').write_text('')
    assert [(g, n, p.rsplit('/', 1)[-1]) for g, n, p in fichiers_myspace(str(tmp_path))] == [
        ('Parts', 3, 'Parts_3.txt')]


def test_etat_piece():
    assert etat_piece('Disponible', 1) == COMMANDABLE
    assert etat_piece('Abandonnée', 1) == FIN_DE_VIE
    assert cle_ref(' 00 12-3/a ') == '00123A'


def test_famille_suit_les_remplacements(myspace):
    f = myspace.famille('481010000001')
    assert f.courante.ref == '481010000003'
    assert [p.ref for p in f.chaine] == ['481010000001', '481010000002', '481010000003']
    # anciennes : la chaîne, puis celles qui renvoient vers elle (481010000009)
    assert f.references == ['481010000003', '481010000001', '481010000002', '481010000009']


def test_famille_depuis_la_courante(myspace):
    f = myspace.famille('481010000003')
    assert f.courante.ref == '481010000003'
    assert set(f.anciennes) == {'481010000002', '481010000001', '481010000009'}


def test_famille_article_epuise(myspace):
    f = myspace.famille('C00111111')
    assert f.epuisee and f.courante.ref == 'C00111111'
    assert myspace.famille('481299999990').epuisee


def test_famille_meilleur_constructeur(myspace):
    f = myspace.famille('4346040285')
    assert f.courante.ref == 'C00866459' and f.courante.constructeur == 17
    assert f.anciennes == ['4346040285'] and f.autres_constructeurs == [2]
    # constructeur imposé : on le respecte
    assert myspace.famille('4346040285', 2).courante.constructeur == 2


def test_famille_inconnue(myspace):
    assert not myspace.famille('NOPE').trouvee


def test_lignes_appareils_marque_et_type(myspace):
    cas = [
        {'TechnicalReference': '859991234567', 'CommercialReference': 'AWO 1234'},
        {'TechnicalReference': '859991234567', 'CommercialReference': 'AWO 1234'},   # doublon
        {'TechnicalReference': '855555555555', 'CommercialReference': 'CIG546 W'},
        {'TechnicalReference': '850000000000', 'CommercialReference': 'XYZ'},
        {'TechnicalReference': '25939400000', 'CommercialReference': 'CP059MDXAUSS',
         'Description': 'Cuisiniere électrique'},
        {'TechnicalReference': '', 'CommercialReference': ''},
    ]
    connues = {'whirlpool': 'Whirlpool', 'scholtes': 'Scholtès'}
    r = lignes_appareils(cas, lambda a: myspace.produits(a, 2), connues)
    assert r.avec_entetes()[0] == ENTETES
    assert r.lignes == [['859991234567', 'AWO 1234', 'Whirlpool', 'Lave-linge'],
                        ['855555555555', 'CIG546 W', 'Scholtès', 'Cuisinière'],
                        ['850000000000', 'XYZ', '', ''],
                        ['25939400000', 'CP059MDXAUSS', '', 'Cuisinière']]
    assert (r.sans_marque, r.sans_type) == (2, 1)


def test_marque_canonique():
    connues = {'faure': 'Faure', 'liebherr': 'Liebherr'}
    assert marque_canonique('FAURE ELECTROLUX', connues) == 'Faure'
    assert marque_canonique('LIEBHERR Appliances', connues) == 'Liebherr'
    assert marque_canonique('Autres marques', connues) == ''
    assert marque_canonique('NOUVELLE', connues) == 'Nouvelle'


def test_marque_dans_designation():
    connues = {'altus': 'Altus', 'essentielb': 'Essentiel-B', 'grundig': 'Grundig', 'lg': 'LG'}
    assert marque_dans_designation('Kg1840 ALTUs', connues) == 'Altus'
    assert marque_dans_designation('ECC 351b EssENTIELB_FRANCE(C350)', connues) == 'Essentiel-B'
    assert marque_dans_designation('49 VLE 6523 BLgRUNDIg', connues) == 'Grundig'
    assert marque_dans_designation('OCEALVE1349IX PRIVATE LABEL', connues) == ''
    assert marque_dans_designation('LG 123', connues) == ''          # marque trop courte : ignorée


def test_type_depuis_designation():
    assert type_depuis_designation('COMB. RÉFRIGÉ.-CONGÉL.-ENCASTR') == 'Congélateur'
    assert type_depuis_designation('Four micro-ondes 17 litres') == 'Micro-ondes'
    assert type_depuis_designation('GS60BISM') == ''


def test_prix_emg():
    assert prix_emg({'PublicPrice': 100.0}, 3).vente == 134.0          # Electrolux : −33 % × 2
    p = prix_emg({'DiscountPrice': 10.0, 'PublicPrice': 12.0}, 2)
    assert (p.achat_ht, p.vente) == (10.0, 20.0) and p.alerte
    assert prix_emg({}, 2).vente is None
    assert prix_emg({'DiscountPrice': 14.784}, 17).vente == 29.6          # arrondi au dixième


def test_code_et_libelle():
    from src.utils.agora.codes import REGLES_PAR_DEFAUT as R
    assert code_emg_propose('140005565027', 3, R) == 'EL140005565027'
    assert code_emg_propose('481011015524', 2, R) == '481011015524'
    assert code_emg_propose('123', 10, R) is None
    assert code_emg_propose('C00866459', 17, R) == 'SCS866459'      # C00 + 6 chiffres : SCS, même chez Beko
    assert code_emg_propose('00611323', 4, R) == 'GAU611323'        # BSH : sans le 00 de tête
    assert code_emg_propose('11051894', 4, R) == 'GAU11051894'
    assert code_emg_propose('0078216', 5, R) == 'MIE0078216'
    assert libelle_piece('panneau,blanc') == 'Panneau'
    assert libelle_piece('POMPE DE VIDANGE') == 'Pompe de vidange'
    assert libelle_piece('Serrure electro-ma. 0437 220/240') == 'Serrure'
    assert libelle_piece('Relais zbt1114cy\\jiaxipera') == 'Relais'
    assert libelle_piece('Plafonnier+led pcb gw') == 'Plafonnier + led pcb gw'


class _Transport:
    def __init__(self, *reponses):
        self.reponses, self.urls = list(reponses), []

    def __call__(self, url, cle):
        self.urls.append(url)
        return self.reponses.pop(0)


def test_client_cache_et_quota(base):
    t = _Transport((200, json.dumps([{'TechnicalReference': 'A'}]).encode()), (404, b''), (200, b'[]'))
    c = ClientAgora(base, cle='x', transport=t, quota=2)
    r = c.appareils(2, '481010000003')
    assert not r.depuis_cache and r.donnees == [{'TechnicalReference': 'A'}]
    assert t.urls[0].endswith('getsparepartusecases/2/481010000003/250/English')
    assert c.appareils(2, '4810-1000 0003').depuis_cache          # même clé, pas d'appel
    assert c.restants(APPAREILS) == 1 and c.restants(INFO) == 2
    assert c.info(2, 'X').absente                                  # 404 : gardé en cache
    assert c.appareils(2, 'AUTRE').absente                         # 2e appel du service
    with pytest.raises(QuotaEpuise):
        c.appareils(2, 'ENCORE')
    assert len(t.urls) == 3


def _enveloppe(donnees, statut='S', erreur=None):
    return json.dumps({'ResponseStatus': statut, 'IsValid': statut == 'S', 'ResponseMessage': None,
                       'ResponseErrorMessage': erreur, 'ResponseData': donnees}).encode()


def test_client_enveloppe(base):
    t = _Transport((200, _enveloppe({'PartRef': 'R1', 'DiscountPrice': 5.0})),
                   (200, _enveloppe(None, 'E', 'Daily call limit exceeded')),
                   (200, _enveloppe(None, 'E', 'Unknown manufacturer')))
    c = ClientAgora(base, cle='x', transport=t)
    assert c.info(2, 'R1').donnees == {'PartRef': 'R1', 'DiscountPrice': 5.0}
    with pytest.raises(QuotaEpuise):
        c.appareils(2, 'R1')
    assert c.restants(APPAREILS) == 0
    with pytest.raises(ErreurAgora):
        c.info(99, 'R2')
    assert not c.en_cache(INFO, 99, 'R2') and not c.en_cache(APPAREILS, 2, 'R1')


def test_info_en_cache(base):
    t = _Transport((200, _enveloppe({'PartRef': 'C00866459', 'DiscountPrice': 14.784})))
    ClientAgora(base, cle='x', transport=t).info(17, 'C00866459')
    assert base.info_en_cache('c00866459') == (17, {'PartRef': 'C00866459', 'DiscountPrice': 14.784})
    assert base.info_en_cache('AUTRE') is None


def test_client_refus_non_mis_en_cache(base):
    t = _Transport((403, b'quota'), (500, b''))
    c = ClientAgora(base, cle='x', transport=t)
    with pytest.raises(QuotaEpuise):
        c.appareils(2, 'R1')
    assert c.restants(APPAREILS) == 0 and not c.en_cache(APPAREILS, 2, 'R1')
    with pytest.raises(ErreurAgora):
        c.info(2, 'R1')
    assert not c.en_cache(INFO, 2, 'R1')


# --- Fiche PrestaShop / Cogilog -----------------------------------------------------

from datetime import date  # noqa: E402

from src.utils.agora.fiche import (CategoriesSite, FicheSite, ajouter_aux_fichiers_du_jour,  # noqa: E402
                                   fabricant_site)


def test_fabricant_site():
    assert fabricant_site('SCS866459') == 'Indesit Ariston Scholtès Hotpoint'
    assert fabricant_site('481011015524') == 'Whirlpool Laden Ignis Bauknecht'
    assert fabricant_site('EL140005565027').startswith('Electrolux')
    assert fabricant_site('SCS866459', 17) == 'Beko'


def test_categorie_proposee(tmp_path):
    chemin = tmp_path / 'categories_site.json'
    chemin.write_text(json.dumps({
        'categories': ['Relais - Réfrigérateur', 'Divers - Réfrigérateur', 'Pompe de vidange - Lave-linge'],
        'par_libelle_type': {'relais|refrigerateur': 'Relais - Réfrigérateur'}}), encoding='utf-8')
    c = CategoriesSite(str(chemin))
    assert c.proposer('Relais', 'Réfrigérateur') == 'Relais - Réfrigérateur'
    assert c.proposer('Pompe', 'Lave-linge') == 'Pompe de vidange - Lave-linge'
    assert c.proposer('Joint', 'Réfrigérateur') == 'Divers - Réfrigérateur'
    assert c.proposer('Joint', 'Four') == ''


def test_fichiers_du_jour(tmp_path):
    f = FicheSite(code='SCS866459', nom='Relais pour réfrigérateur Beko - C00866459', libelle='Relais',
                  reference='C00866459', prix_ttc=29.57, categorie='Divers - Réfrigérateur',
                  fabricant='Beko', description='<h2>…</h2>')
    jour = date(2026, 11, 26)
    r = ajouter_aux_fichiers_du_jour(f, str(tmp_path), jour)
    f.prix_ttc = 31.0
    r = ajouter_aux_fichiers_du_jour(f, str(tmp_path), jour)                 # remplace sa ligne
    assert r['fiches'] == 1
    cogilog = (tmp_path / 'fiches_cogilog_20261126.csv').read_bytes().decode('cp1252').splitlines()
    assert cogilog[0] == 'Code;Libellé;Site web1;Internet HT;Internet TTC;Photo;Famille;Code EAN'
    assert cogilog[1] == 'SCS866459;RELAIS C00866459;PrestaShop;25,833333;31,00;pam;Apieces;'
    presta = (tmp_path / 'fiches_prestashop_20261126.csv').read_text(encoding='utf-8').splitlines()
    assert presta[1].startswith('0;Relais pour réfrigérateur Beko - C00866459;Divers - Réfrigérateur;25.833333;1;SCS866459')
    assert FicheSite(code='', nom='', libelle='', reference='X', prix_ttc=None).manques()[:3] == [
        'code produit', 'nom', 'prix']


def test_regles_codes_fichier(tmp_path):
    from src.utils.agora.codes import RegleCode, charger_regles, code_produit, enregistrer_regles
    chemin = str(tmp_path / 'regles_codes.json')
    assert len(charger_regles(chemin)) == 8                          # défauts sans fichier
    enregistrer_regles([RegleCode('Test', 'TT', [3], '14*')], chemin)
    regles = charger_regles(chemin)
    assert code_produit('140005565027', 3, regles) == 'TT140005565027'
    assert code_produit('2262143023', 3, regles) is None
