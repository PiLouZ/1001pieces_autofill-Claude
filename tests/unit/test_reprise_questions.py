"""
Moteur de questions de l'import par lots (refonte de la reprise, étape 2)

Sur une base construite et des exports construits, sans réseau :
- chaque cas donne sa question (R1 même réf. dans le groupe, R2 autre type,
  R3 même nom / autre réf., R4 marque hors groupe, R5 réf. produit, Q1 créer,
  Q2 type proposé d'après la base, Q3 marque à choisir, Q4 équivalentes) ;
- rien ne s'enregistre tant qu'une question est sans réponse ; « accepter les
  propositions » ne répond jamais à une question sans proposition ;
- les réponses s'écrivent comme prévu, la relance n'ajoute rien ;
- règles mémorisées dans le fichier de configuration (jamais celui du poste),
  reprises au lot suivant, révocables ; R4 « oui » enrichit les groupes et
  la relecture du lot retrouve l'appareil ;
- lignes sans question (à choisir parmi plusieurs) laissées de côté, fiche à revoir.
"""

import copy
import csv
import json

from src.data.database_manager import DatabaseManager
from src.services.export_config_service import DEFAULT_CONFIG
from src.services.reprise_site_service import RepriseSiteService
from src.utils.lecteur_fiche import modeles_depuis_config
from src.utils.rapprochement_fiche import ConfigurationRapprochement
from src.utils.reprise_site.questions import REGLE

MODELES = modeles_depuis_config(copy.deepcopy(DEFAULT_CONFIG))
ENTETE_P = ['id_produit', 'reference', 'nom_produit', 'marque', 'ean', 'categorie', 'actif',
            'description']
ENTETE_C = ['id_produit', 'reference_appareil', 'modele_appareil', 'marque_appareil',
            'type_appareil']


def _csv(chemin, entete, lignes):
    with open(chemin, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(entete)
        w.writerows(lignes)
    return str(chemin)


def _description(code, sections, annonce=(), equivalentes=()):
    html = f'<h2 class="class_perso1">Pièce {code}</h2>'
    if annonce:
        html += '<div class="class_perso2">Compatible avec ' + ' '.join(
            f'<a href="#{m}">{m}</a>' for m in annonce) + '</div>'
    html += f'<div class="class_perso3">Code produit : {code}</div>'
    for refs in equivalentes:
        html += f'<div class="class_perso3 class_perso6">Références équivalentes : {refs}</div>'
    html += '<div class="class_perso4">Appareils compatibles :</div><div class="class_perso5">'
    for marque, lignes in sections:
        if marque:
            html += f'<div id="{marque}"><b><u>{marque}</u></b></div>'
        html += ''.join(f'<div>{r} - {n}</div>' for r, n in lignes)
    return html + '</div>'


class Monde:
    """Base et exports construits couvrant chaque genre de question."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.db = DatabaseManager(str(tmp_path / 'b.db'))
        self.regles = tmp_path / 'reprise_fiches.json'
        a = self.appareil
        a('Bosch', 'X0')
        self.siemens = a('Siemens', 'WAE24/01')                      # R1
        self.seche = a('Bosch', 'WAT28/01', 'Sèche-linge')           # R2
        a('Bosch', 'WAQ1', nom='Serie 4')                            # R3
        self.elica = a('Elica', 'ZZE123', 'Hotte')                   # R4
        for ref in ('HD7800', 'HD7818/50', 'HD7820'):                # Q2 : type proposé
            a('Philips', ref, 'Machine à café')
        a('Zanussi', 'ZAN1')
        a('Zoppas', 'ZOP1')
        a('Bosch', 'AMB/01', nom='Duo')                              # à choisir parmi plusieurs
        a('Bosch', 'AMB/02', nom='Duo')
        produits = [
            [101, 'ES10028', 'Pompe A', 'Bosch', '', 'Pompe - Lave-linge', '1', _description(
                '481010595117', [('Bosch', [('WAE24/01', 'Maxx'), ('WAT28/01', 'Sec'),
                                           ('WAQ9', 'Serie 4'), ('ZZE123', 'Hotte'),
                                           ('ZZNEW1', 'Neuf'), ('AMB/09', 'Duo')])],
                equivalentes=['Brandt'])],
            [102, '481010595118', 'Support', 'Philips', '', '', '1', _description(
                '481010595118', [('Philips', [('HD7801', 'Senseo'), ('HD7802', 'Senseo')])])],
            [103, '481010595119', 'Courroie', 'Zanussi', '', 'Courroie - Lave-linge', '1', _description(
                '481010595119', [(None, [('Z714', 'Z 714')])], annonce=['Zanussi', 'Zoppas'],
                equivalentes=['685444099'])],
        ]
        compat = [[101, 'WAT28/01', 'WAT28/01 - Sec', 'Bosch', 'Lave-linge']]
        self.p = _csv(tmp_path / 'p.csv', ENTETE_P, produits)
        self.c = _csv(tmp_path / 'c.csv', ENTETE_C, compat)

    def appareil(self, marque, ref, type_='Lave-linge', nom=''):
        cur = self.db.conn.execute(
            "INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) VALUES (?, ?, ?, ?)",
            [type_, marque, ref, nom])
        self.db.conn.commit()
        return cur.lastrowid

    def service(self):
        s = RepriseSiteService(self.db, configuration=self.configuration(),
                               chemin_configuration=self.regles)
        s._modeles = MODELES
        return s

    def configuration(self):
        donnees = json.loads(self.regles.read_text('utf-8')) if self.regles.exists() else {}
        return ConfigurationRapprochement(donnees)

    def lot(self, s, depart=True):
        s.adopter_export(s.examiner_export(self.p, self.c)[0], repartir_de_zero=depart)
        lot = s.analyser_lot_suivant(10)
        return lot, s.questionnaire(lot)

    def compte(self, table, where='', params=()):
        return self.db.conn.execute(f"SELECT COUNT(*) FROM {table} {where}", list(params)).fetchone()[0]

    def instantane(self):
        return {t: self.compte(t) for t in ('appareils', 'pieces', 'piece_associations',
                                            'piece_equivalence_groups', 'produits_site')}


def _repondre_tout(q):
    q.accepter_propositions()
    for x in q.sans_reponse():
        valeur = {'R4': 'non', 'Q3': 'marque:Zanussi', 'Q4': 'sans'}.get(x.cle.split(':')[0], x.choix[0][0])
        q.repondre(x.cle, valeur)


def test_une_question_par_genre_et_propositions(tmp_path):
    m = Monde(tmp_path)
    lot, q = m.lot(m.service())
    cles = {x.cle: x for x in q.liste()}
    assert {'R1', 'R2', 'R3', 'R4:Bosch|Elica', 'R5', 'Q1', 'Q2:102', 'Q3:103'} <= set(cles)
    assert cles['R1'].genre == REGLE and cles['R1'].proposition == 'oui'
    assert cles['R2'].proposition == 'oui' and cles['R3'].proposition == 'creer'
    assert cles['R4:Bosch|Elica'].proposition is None
    assert cles['Q2:102'].proposition == 'type:Machine à café' and cles['Q2:102'].cas == 2
    assert cles['Q3:103'].proposition is None
    q4 = {k: x for k, x in cles.items() if k.startswith('Q4:')}
    assert any(x.proposition == 'ecarter' for x in q4.values())       # « Brandt »
    assert any(x.proposition is None for x in q4.values())            # 685444099, 2 marques annoncées
    assert q.resume()['lignes_a_revoir'] == 1                         # AMB/09 : 2 candidats « Duo »
    # Exemple lisible : la marque sous laquelle l'appareil a été retrouvé
    assert any('trouvé sous Siemens' in e for e in cles['R1'].exemples)


def test_rien_ne_s_ecrit_sans_reponse_et_propositions_partielles(tmp_path):
    m = Monde(tmp_path)
    lot, q = m.lot(m.service())
    assert not lot.planifier().pret
    q.accepter_propositions()
    restantes = {x.cle for x in q.sans_reponse()}
    assert {'R4:Bosch|Elica', 'Q3:103'} <= restantes       # jamais répondues à la place de l'utilisateur
    assert not lot.planifier().pret


def test_reponses_ecrites_relance_sans_ajout(tmp_path):
    m = Monde(tmp_path)
    s = m.service()
    lot, q = m.lot(s)
    _repondre_tout(q)
    plan = lot.planifier()
    assert plan.pret, plan.en_attente
    avant = m.instantane()
    res = s.enregistrer_lot(lot, plan)
    assert res.ok, res.erreur
    liens = lambda app: m.compte('piece_associations', 'WHERE appareil_id = ?', [app])  # noqa: E731
    assert liens(m.siemens) == 1 and liens(m.seche) == 1               # R1, R2 reliés
    assert m.compte('appareils', "WHERE ref_modele = 'WAQ9'") == 1     # R3 créé
    assert m.compte('appareils', "WHERE ref_modele = 'ZZE123'") == 2   # R4 « non » : créé sous Bosch
    assert m.db.conn.execute("SELECT type FROM appareils WHERE ref_modele = 'HD7801'").fetchone()[0] \
        == 'Machine à café'                                            # Q2 proposé
    assert m.db.conn.execute("SELECT manufacturer FROM appareils WHERE ref_modele = 'Z714'").fetchone()[0] \
        == 'Zanussi'                                                   # Q3
    assert m.compte('appareils', "WHERE ref_modele = 'AMB/09'") == 0   # à revoir : rien
    assert m.compte('piece_equivalence_groups', "WHERE ref_piece = 'Brandt'") == 0
    assert m.compte('produits_site', "WHERE ref_interne = 'ES10028'") == 1   # R5 « garder »
    assert plan.a_revoir and any('AMB/09' in r for r in sum(plan.a_revoir.values(), []))
    complet = m.instantane()
    assert complet != avant
    # Relance immédiate : les règles sont mémorisées, il ne reste que les questions du lot
    m.db.conn.execute("UPDATE reprise_site_etat SET dernier_id = 0")
    m.db.conn.commit()
    s2 = m.service()
    lot, q = m.lot(s2, depart=False)
    # (R1 et R3 ne se posent plus : leurs lignes sont maintenant reliées / créées)
    memorisees = {x.cle for x in q.liste() if x.memorisee}
    assert {'R2', 'R5'} <= memorisees and 'R1' not in q.questions and 'R3' not in q.questions
    assert all(x.repondue for x in q.liste() if x.genre == REGLE and x.cle != 'R4:Bosch|Elica')
    _repondre_tout(q)
    res = s2.enregistrer_lot(lot, lot.planifier())
    assert res.ok and (res.appareils_crees, res.liens_crees) == (0, 0)
    assert m.instantane() == complet


def test_regles_memorisees_revocables_et_fichier_du_test(tmp_path):
    m = Monde(tmp_path)
    lot, q = m.lot(m.service())
    q.repondre('R1', 'oui')
    donnees = json.loads(m.regles.read_text('utf-8'))
    assert donnees['regles_reprise'] == {'R1': 'oui'}
    q.repondre('R1', None)                                             # révoquée
    assert json.loads(m.regles.read_text('utf-8'))['regles_reprise'] == {}
    assert q.questions['R1'].reponse is None


def test_r4_oui_enrichit_le_groupe_et_relit_le_lot(tmp_path):
    m = Monde(tmp_path)
    s = m.service()
    lot, q = m.lot(s)
    q.repondre('R4:Bosch|Elica', 'oui')
    assert q.relire and any('Relire' in t for t in q.en_attente())
    groupes = json.loads(m.regles.read_text('utf-8'))['groupes_marques']
    bsh = next(g for g, membres in groupes.items() if 'Bosch' in membres)
    assert 'Elica' in groupes[bsh]
    lot = s.relire_lot(lot)
    q = lot.questionnaire
    assert 'R4:Bosch|Elica' not in q.questions
    hotte = next(a for a in lot.fiches[0].rapprochement.appareils if a.ref_modele == 'ZZE123')
    assert hotte.motif == 'meme_ref_groupe' and hotte.candidats[0].id == m.elica
    assert q.lignes[(0, lot.fiches[0].rapprochement.appareils.index(hotte))] == 'R1'


def test_fiche_partielle_a_revoir_puis_complete(tmp_path):
    """Étape 3 : une fiche écrite avec des lignes laissées de côté est inscrite « à
    revoir » ; relue, elle n'ajoute aucun doublon ; complétée, elle est retirée."""
    from src.utils.rapprochement_fiche.decisions import ChoixAppareil
    m = Monde(tmp_path)
    s = m.service()
    lot, q = m.lot(s)
    _repondre_tout(q)
    res = s.enregistrer_lot(lot, lot.planifier())
    assert res.ok and res.partielles == 1
    a_revoir = m.db.fiches_de_cote_reprise_site()
    assert [(f['id_produit'], f['raison']) for f in a_revoir] == [(101, 'partielle : 1 appareil(s) à revoir')]
    avant = m.instantane()
    # Relue : seule la ligne AMB/09 reste à revoir, rien n'est doublé
    lot = s.analyser_fiches_de_cote()
    q = s.questionnaire(lot)
    _repondre_tout(q)
    res = s.enregistrer_lot(lot, lot.planifier())
    assert res.ok and (res.appareils_crees, res.liens_crees) == (0, 0)
    assert m.instantane() == avant and len(m.db.fiches_de_cote_reprise_site()) == 1
    # Complétée dans l'aperçu de la fiche : l'appareil choisi, elle est retirée
    lot = s.analyser_fiches_de_cote()
    f = lot.fiches[0]
    k = next(i for i, a in enumerate(f.rapprochement.appareils) if a.ref_modele == 'AMB/09')
    d = copy.deepcopy(lot.decisions_effectives(0))
    d.valider_tout(f.rapprochement)
    d.appareils[k] = ChoixAppareil(appareil_id=f.rapprochement.appareils[k].candidats[0].id)
    for genre in ('ref_interne_differente', 'libelle_different'):
        d.identite.setdefault(genre, {'ref_interne_differente': 'enregistrer'}.get(genre, 'garder'))
    lot.personnaliser(0, d)
    res = s.enregistrer_lot(lot, lot.planifier())
    assert res.ok and res.partielles == 0 and res.liens_crees == 1
    assert m.db.fiches_de_cote_reprise_site() == []
