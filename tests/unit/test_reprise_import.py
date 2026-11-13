"""
La reprise des fiches du site devient un import comme les autres (CDC import fiches
site, § 10.12, PR 1 : moteur)

- import de plusieurs fichiers : un appareil créé par un fichier et cité par un
  fichier suivant est relié dès le 1er passage (défaut mesuré : 418 liens sur le
  1er lot réel, posés seulement par une relance) ;
- une fiche est écrite par `ImportManager` (fichier `FICHE_SITE`) : auto-complétion
  et suggestions de l'import, récapitulatif comme après un import ;
- règles de l'import à la place des questions : même réf. sous une marque du
  groupe reliée, appareil inconnu créé même sans type, fiche sans code produit
  mise de côté ;
- aller-retour des 3 fiches d'exemple et relance d'un lot sans ajout.
Aucun accès réseau, aucun réglage du poste écrit.
"""

from pathlib import Path

from src.core.import_manager import (FileType, ImportConfiguration, ImportFile, ImportManager,
                                     ImportType)
from src.services.enregistrement_fiche_service import EnregistrementFicheService
from src.utils.lecteur_fiche.page_publique import extraire_description

from tests.unit.test_reprise_site import (
    CONFIG, FIXTURES, MODELES, Construite, _db_extrait, _ecrire_csv, ENTETE_C, ENTETE_P,
    _exports_exemples, _instantane, _produit, _service,
)


# =============================================================================
# Import de plusieurs fichiers : appareil créé par un fichier précédent
# =============================================================================

def _fichier(nom, refs):
    return ImportFile(path=nom, type=FileType.CLIPBOARD, suggested_reference=nom,
                      data=[[r, ''] for r in refs])


def test_doublon_inter_fichiers_relie_des_le_premier_passage(tmp_path):
    b = Construite(tmp_path)
    # Chemin batch (≥ 50 lignes) ; X050 à X054 sont créés par A et cités par B
    a = _fichier('A', [f'X{i:03d}' for i in range(55)])
    c = _fichier('B', [f'X{i:03d}' for i in range(50, 105)])
    config = ImportConfiguration(files=[a, c], import_type=ImportType.MULTI_FILE,
                                 individual_references={'A': 'PIECEA', 'B': 'PIECEB'},
                                 column_mapping={2: ['ref_modele', 'commercial_ref']})
    res = ImportManager(b.db)._run_import_files(config)
    assert res['new_entries'] == 105

    def liens(ref):
        return b.db.conn.execute(
            "SELECT COUNT(*) FROM piece_associations pa JOIN pieces p ON p.id = pa.piece_id "
            "WHERE p.ref_piece = ?", [ref]).fetchone()[0]
    assert liens('PIECEA') == 55
    assert liens('PIECEB') == 55            # 50 avant la correction
    # Relance : rien de plus
    res = ImportManager(b.db)._run_import_files(config)
    assert res['new_entries'] == 0 and res['associations_created'] == 0


# =============================================================================
# Fiches par les règles de l'import
# =============================================================================

class _Fenetre:
    """Fenêtre principale réduite à la fin d'import (récapitulatif, suggestions)."""
    def __init__(self):
        self.imports = []

    def _on_import_complete(self, results):
        self.imports.append(results)


def test_fiche_seule_ecrite_par_l_import_puis_relue_sans_ajout(tmp_path):
    db = _db_extrait(tmp_path)
    fenetre = _Fenetre()
    service = EnregistrementFicheService(db, parent_window=fenetre, configuration=CONFIG)
    service._modeles = lambda: MODELES
    page = (FIXTURES / 'produit_7285.html').read_text(encoding='utf-8')
    _, r = service.analyser_page(page, url='https://www.1001pieces.com/7285-fiche.html')
    plan = service.planifier_par_regles(r)
    assert plan.pret, plan.a_completer
    res = service.enregistrer(plan)
    assert res.ok, res.erreur
    assert res.piece == 'creee' and res.relations.get('successions', 0) > 0
    # Comme après un import : un fichier, ses comptages, ses suggestions
    assert len(fenetre.imports) == 1
    resultats = fenetre.imports[0]
    assert resultats['total_files'] == 1 and 'similarity_suggestions' in resultats
    assert resultats['associations_created'] == res.liens_crees
    apres = _instantane(db)
    # Relue : rien n'est ajouté
    _, r = service.analyser_page(page, url='https://www.1001pieces.com/7285-fiche.html')
    res = service.enregistrer(service.planifier_par_regles(r))
    assert res.ok and (res.appareils_crees, res.liens_crees, res.liens_completes) == (0, 0, 0)
    assert _instantane(db) == apres


def test_lot_des_fiches_exemples_par_les_regles(tmp_path):
    db = _db_extrait(tmp_path)
    p, c = _exports_exemples(tmp_path)
    s = _service(db)
    s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
    lot = s.analyser_lot_suivant(100)
    plan = lot.planifier_par_regles()
    assert plan.pret and lot.questionnaire is None
    res = s.enregistrer_lot(lot, plan)
    assert res.ok, res.erreur
    assert res.fiches_ecrites == 3 and res.resultats_import['total_files'] == 3
    piece = db.conn.execute("SELECT is_phantom FROM pieces WHERE ref_piece = '11051894'").fetchone()
    assert piece == (0,)                                    # 20744 : fantôme → réelle
    apres = _instantane(db)
    # Relance du lot : rien n'est ajouté
    db.conn.execute("UPDATE reprise_site_etat SET dernier_id = 0")
    db.conn.commit()
    lot = s.analyser_lot_suivant(100)
    res = s.enregistrer_lot(lot, lot.planifier_par_regles())
    assert res.ok and (res.appareils_crees, res.liens_crees, res.liens_completes) == (0, 0, 0)
    assert _instantane(db) == apres
    s.fermer()


def test_regles_groupe_creation_sans_type_et_sans_code_produit(tmp_path):
    b = Construite(tmp_path)
    whirlpool = b.appareil('Whirlpool', '859205612010')
    b.appareil('Ikea', 'ZZFOUR 01', type_='Four')           # même réf., marque hors du groupe
    b.appareil('Bauknecht', 'WAK1234', type_='Lave-linge')  # marque connue de l'outil
    sans_code = ('<div class="class_perso4">Appareils compatibles :</div>'
                 '<div class="class_perso5"><div id="Bosch"><b><u>Bosch</u></b></div>'
                 '<div>WAE99/01 - Maxx</div></div>')
    fiche = _produit(201, '481010595117', 'Bauknecht',
                     [('859205612010', 'PRIMO1407UM'), ('ZZFOUR 01', 'Z900')])
    fiche[5] = ''                       # sans catégorie : aucun type tiré de la fiche
    produits = [
        fiche,
        [202, 'ES20202', 'Pièce sans code', 'Bosch', '', 'Pompe - Lave-linge', '1', sans_code],
    ]
    p = _ecrire_csv(tmp_path / 'p.csv', ENTETE_P, produits)
    c = _ecrire_csv(tmp_path / 'c.csv', ENTETE_C, [])
    s = _service(b.db)
    s.adopter_export(s.examiner_export(p, c)[0], repartir_de_zero=True)
    lot = s.analyser_lot_suivant(10)
    plan = lot.planifier_par_regles()
    assert plan.pret
    # Fiche sans code produit : mise de côté, référence à saisir
    assert [lot.fiches[i].id_produit for i in plan.de_cote] == [202]
    assert 'code produit' in lot.fiches[plan.de_cote[0]].raison_de_cote
    res = s.enregistrer_lot(lot, plan)
    assert res.ok, res.erreur
    piece = b.db.conn.execute("SELECT id FROM pieces WHERE ref_piece = '481010595117'").fetchone()[0]
    lies = {r[0] for r in b.db.conn.execute(
        "SELECT appareil_id FROM piece_associations WHERE piece_id = ?", [piece])}
    # Même réf. sous Whirlpool (groupe de Bauknecht) : relié, rien de créé
    assert whirlpool in lies
    assert b.db.conn.execute("SELECT COUNT(*) FROM appareils WHERE ref_modele = '859205612010'"
                             ).fetchone()[0] == 1
    # Réf. connue seulement hors du groupe : créée sous la marque de la fiche, sans
    # type sur la fiche → type auto-complété par l'import, à vérifier
    cree = b.db.conn.execute("SELECT id, type FROM appareils WHERE manufacturer = 'Bauknecht' "
                             "AND ref_modele = 'ZZFOUR 01'").fetchone()
    assert cree is not None and cree[0] in lies
    assert cree[1] == 'Four'
    assert b.db.conn.execute("SELECT COUNT(*) FROM appareils_autocompletes WHERE appareil_id = ?",
                             [cree[0]]).fetchone()[0] == 1
    assert res.resultats_import.get('autocompletes_a_verifier') == 1
    s.fermer()


def test_lignes_identifiees_ne_changent_pas_l_appareil_connu(tmp_path):
    """Un appareil reconnu par la fiche garde ses champs : la ligne ne complète
    qu'un type ou une marque vides (règle de l'import)."""
    b = Construite(tmp_path)
    connu = b.appareil('Bosch', 'WAE24/01', type_='')
    autre = b.appareil('Bosch', 'WAE25/01', type_='Lave-linge')
    fichier = ImportFile(path='fiche', type=FileType.FICHE_SITE, suggested_reference='P1', data=[
        {ImportManager.CLE_APPAREIL: connu, ImportManager.CLE_IDENTITE: f'id:{connu}',
         'type': 'Lave-vaisselle', 'manufacturer': 'Siemens'},
        {ImportManager.CLE_APPAREIL: autre, ImportManager.CLE_IDENTITE: f'id:{autre}',
         'type': 'Four'},
    ])
    config = ImportConfiguration(files=[fichier], import_type=ImportType.SINGLE_FILE,
                                 individual_references={'fiche': 'P1'})
    res = ImportManager(b.db)._run_import_files(config)
    assert res['matches_found'] == 2 and res['new_entries'] == 0
    lignes = dict(b.db.conn.execute(
        "SELECT id, type || '|' || manufacturer FROM appareils").fetchall())
    assert lignes == {connu: 'Lave-vaisselle|Bosch', autre: 'Lave-linge|Bosch'}


def test_appareil_a_creer_sans_marque_non_importe():
    """Créé sans marque, un appareil ne serait jamais retrouvé (identité = marque +
    réf.) et l'auto-complétion lui donnerait la marque d'un autre appareil de même
    réf. : la ligne n'est pas importée, elle est comptée."""
    from src.utils.rapprochement_fiche.regles_import import choix_ligne
    from src.utils.rapprochement_fiche.resultat import AppareilRapproche
    a = AppareilRapproche(numero=3, marque_fiche='', ref_modele='857911429000', nom='',
                          provenance='description', niveau='absent', motif='marque_a_choisir')
    choix, raison = choix_ligne(a)
    assert choix.ignorer and 'marque inconnue' in raison
    a = AppareilRapproche(numero=4, marque_fiche='Bosch', ref_modele='WAE99/01', nom='',
                          provenance='description', niveau='absent')
    assert choix_ligne(a) == (None, '')             # créé, même sans type
