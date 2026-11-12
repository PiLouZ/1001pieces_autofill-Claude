"""
« Rien de faux en bloc » (refonte de la reprise, étape 1) : ce que « Tout valider »
écrivait de faux sur le 1er lot réel (produits 7084 à 7191) ne s'écrit plus.

- le type commun d'une catégorie ne remplace jamais un type déjà trouvé
  (1 100 filtres de hotte de la fiche 7188) ;
- un candidat unique trouvé par le seul nom commercial, de réf. différente,
  n'est pas relié en bloc (42 liens faux) ; même réf. → proposé ;
- une réf. présente sous une marque annoncée qui n'est pas celle de l'en-tête
  n'est pas créée en double (Ignis / Whirlpool, 28 doublons) ;
- réf. interne égale au code produit à la ponctuation près : « égale » ;
- équivalente sans chiffre (« Brandt », « : ») jamais écrite en bloc ;
- réf. illisible (« C : », parenthèses, plusieurs codes, marque collée)
  jamais créée en bloc.
Aucun accès réseau.
"""

from src.data.database_manager import DatabaseManager
from src.utils.lecteur_fiche import LectureFiche, LigneAppareil, LigneEquivalentes
from src.utils.rapprochement_fiche import AccesBaseLecture, ConfigurationRapprochement, rapprocher
from src.utils.rapprochement_fiche.decisions import DecisionsFiche, planifier

CONFIG = ConfigurationRapprochement()


class Base:
    def __init__(self, tmp_path):
        self.db = DatabaseManager(str(tmp_path / 'b.db'))

    def appareil(self, marque, ref, type_='Lave-linge', nom=''):
        cur = self.db.conn.execute(
            "INSERT INTO appareils(type, manufacturer, ref_modele, commercial_ref) VALUES (?, ?, ?, ?)",
            [type_, marque, ref, nom])
        self.db.conn.commit()
        return cur.lastrowid

    def rapprocher(self, lecture, **kw):
        return rapprocher(lecture, AccesBaseLecture(self.db.conn), CONFIG, memoires=True, **kw)


def _lecture(lignes, annoncees=(), code=('481010595117',), equivalentes=()):
    """lignes : (marque d'en-tête ou None, réf., nom)."""
    return LectureFiche(
        code_produit=list(code), marques_annoncees=list(annoncees),
        equivalentes=[LigneEquivalentes(i, list(r), 0, 'texte') for i, r in enumerate(equivalentes, 1)],
        appareils=[LigneAppareil(n, m, r, nom, 'ref_nom', n, source_marque='entete' if m else 'annonces')
                   for n, (m, r, nom) in enumerate(lignes, 1)])


def _plan(r):
    d = DecisionsFiche()
    d.valider_tout(r)
    return planifier(r, d)


def test_type_commun_ne_remplace_pas_le_type_trouve(tmp_path):
    b = Base(tmp_path)
    b.appareil('Elica', 'X1', 'Hotte')          # la marque existe ; ZZHOTTE1 est absent
    r = b.rapprocher(_lecture([('Elica', 'ZZHOTTE1', 'Hotte murale')]),
                     categorie='Filtre à graisse - Hotte')
    a = r.appareils[0]
    assert a.niveau == 'absent' and a.type == 'Hotte'
    d = DecisionsFiche()
    d.valider_tout(r)
    d.type_par_categorie['absents'] = 'Lave-linge'
    plan = planifier(r, d)
    assert [x.type for x in plan.appareils_a_creer] == ['Hotte']


def test_nom_commercial_seul_reference_differente_non_relie(tmp_path):
    b = Base(tmp_path)
    b.appareil('Bosch', 'WAE24/01', nom='Maxx 7')
    r = b.rapprocher(_lecture([('Bosch', 'WAE28/09', 'Maxx 7')]))
    a = r.appareils[0]
    assert a.niveau == 'a_valider' and a.proposition is None and len(a.candidats) == 1
    plan = _plan(r)
    assert plan.liens == [] and plan.lignes_a_completer == [0]


def test_nom_commercial_meme_reference_propose(tmp_path):
    b = Base(tmp_path)
    voisin = b.appareil('Ariston', 'ZZ75842', nom='ETW D 61252')   # marque hors groupe
    b.appareil('Ariston', 'ZZ99999', nom='ETW D 61252')
    cfg = ConfigurationRapprochement({'groupes_marques': {'Test': ['Whirlpool', 'Ariston']}})
    b.appareil('Whirlpool', 'AUTRE1')
    r = rapprocher(_lecture([('Whirlpool', 'ZZ 75842', 'ETW D 61252')]),
                   AccesBaseLecture(b.db.conn), cfg, memoires=True)
    a = r.appareils[0]
    assert a.niveau == 'a_valider' and a.proposition == voisin


def test_marque_annoncee_autre_que_l_entete_pas_de_doublon(tmp_path):
    b = Base(tmp_path)
    whirlpool = b.appareil('Whirlpool', '854020013030', 'Sèche-linge')
    b.appareil('Ignis', 'AUTRE', 'Sèche-linge')
    r = b.rapprocher(_lecture([('Ignis', '854020013030', 'AWC207')],
                              annoncees=['Bauknecht', 'Ignis', 'Whirlpool']))
    a = r.appareils[0]
    assert a.niveau == 'a_valider' and [c.id for c in a.candidats] == [whirlpool]
    plan = _plan(r)
    assert plan.appareils_a_creer == [] and plan.liens == [(whirlpool, 'description')]


def test_ref_interne_egale_a_la_ponctuation_pres(tmp_path):
    b = Base(tmp_path)
    r = b.rapprocher(_lecture([], code=('10/2930-5010',)), ref_interne='10-2930-5010')
    assert r.identite.statut_ref_interne == 'egale'
    assert 'ref_interne_differente' not in r.doutes_par_categorie()


def test_equivalente_sans_chiffre_jamais_ecrite_en_bloc(tmp_path):
    b = Base(tmp_path)
    r = b.rapprocher(_lecture([], equivalentes=[['Brandt', ':', '00145522']]))
    plan = _plan(r)
    assert plan.equivalences == ['00145522']


def test_reference_illisible_jamais_creee_en_bloc(tmp_path):
    b = Base(tmp_path)
    b.appareil('Bauknecht', 'X1')
    b.appareil('Ardo', 'Y1')
    lignes = [('Bauknecht', 'C :', 'cm'), ('Bauknecht', 'VF3017 (VF 3017)', ''),
              ('Bauknecht', 'FCSM6 BL2M6100 855620004000', ''), ('Bauknecht', 'ARDO CL60B', ''),
              ('Bauknecht', 'VF3017', 'propre')]
    r = b.rapprocher(_lecture(lignes), categorie='Résistance - Lave-linge')
    assert [bool(a.suspecte) for a in r.appareils] == [True, True, True, True, False]
    plan = _plan(r)
    assert [a.ref_modele for a in plan.appareils_a_creer] == ['VF3017']
    assert plan.lignes_a_completer == [0, 1, 2, 3]
