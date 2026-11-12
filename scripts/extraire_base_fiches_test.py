#!/usr/bin/env python3
"""
Extrait de la base pour les tests du rapprochement des fiches (CDC § 10, étape 2)

Rejoue le rapprochement des fiches d'exemple (tests/fixtures/fiches_site/) sur
la base RÉELLE ouverte en lecture seule, en enregistrant tout ce qu'il lit :
appareils candidats (y compris les autres écritures d'une même forme), liens
de la lignée, pièces, remplacements, groupes d'équivalence, décisions. Ces
lignes, et elles seules, sont écrites dans un script SQL autonome
(tests/fixtures/fiches_site/base_extrait.sql) : les tests rejouent alors le
rapprochement sans la vraie base et obtiennent les mêmes résultats.

Usage :
    python3.13 scripts/extraire_base_fiches_test.py data/appareils.db \\
        [--sortie tests/fixtures/fiches_site/base_extrait.sql]
"""

import argparse
import copy
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from src.services.export_config_service import DEFAULT_CONFIG  # noqa: E402
from src.utils.lecteur_fiche import lire_page_publique, modeles_depuis_config  # noqa: E402
from src.utils.rapprochement_fiche import (  # noqa: E402
    AccesBaseLecture, ConfigurationRapprochement, rapprocher,
)

FIXTURES = RACINE / 'tests' / 'fixtures' / 'fiches_site'
TABLES = ('appareils', 'pieces', 'piece_associations', 'piece_supersessions',
          'piece_equivalence_groups', 'reference_decisions')


class AccesEnregistreur(AccesBaseLecture):
    """Accès en lecture qui retient les appareils et les pièces lus."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.appareils = set()
        self.refs = set()

    def index_marque(self, marque):
        index = super().index_marque(marque)
        return _IndexEnregistre(index, self.appareils)

    def appareils_par_ref(self, refs):
        out = super().appareils_par_ref(refs)
        self.appareils.update(a.id for v in out.values() for a in v)
        return out

    def appareils_par_nom(self, marques, nom):
        out = super().appareils_par_nom(marques, nom)
        self.appareils.update(a.id for a in out)
        return out

    def lignee(self, refs_depart):
        out = super().lignee(refs_depart)
        self.refs.update(out)
        return out

    def liens(self, refs):
        out = super().liens(refs)
        self.appareils.update(out)
        return out


class _IndexEnregistre:
    def __init__(self, index, vus):
        self._index, self._vus = index, vus

    def candidats(self, ref):
        out = self._index.candidats(ref)
        self._vus.update(a.id for a in out)
        return out


def _pages(acces):
    modeles = modeles_depuis_config(copy.deepcopy(DEFAULT_CONFIG))
    marques, types = list(acces.marques().values()), list(acces.types().values())
    for chemin in sorted(FIXTURES.glob('produit_*.html')):
        yield lire_page_publique(chemin.read_text(encoding='utf-8'), modeles=modeles,
                                 marques_connues=marques, types_connus=types)


def extraire(base: str, sortie: Path):
    acces = AccesEnregistreur(sqlite3.connect(f"file:{Path(base).resolve()}?mode=ro", uri=True),
                              fermer=True)
    config = ConfigurationRapprochement()
    for page in _pages(acces):
        r = rapprocher(page.description, acces, config, page=page)
        acces.refs.update(x for rem in r.remplacements for x in (rem.ancienne, rem.nouvelle))
        acces.refs.update(e.reference for e in r.equivalences)
        if r.identite.ref_piece:
            acces.refs.add(r.identite.ref_piece)

    src = acces.cnx
    refs = sorted(acces.refs)
    q = lambda n: ','.join('?' * n)  # noqa: E731
    groupes = [g for (g,) in src.execute(
        f"SELECT DISTINCT group_id FROM piece_equivalence_groups WHERE ref_piece IN ({q(len(refs))})",
        refs)]
    membres = [r for (r,) in src.execute(
        f"SELECT ref_piece FROM piece_equivalence_groups WHERE group_id IN ({q(len(groupes))})",
        groupes)] if groupes else []
    refs = sorted(set(refs) | set(membres))
    pieces = src.execute(f"SELECT * FROM pieces WHERE ref_piece IN ({q(len(refs))})", refs).fetchall()
    ids_pieces = [p[0] for p in pieces]
    associations = src.execute(
        f"SELECT * FROM piece_associations WHERE piece_id IN ({q(len(ids_pieces))})",
        ids_pieces).fetchall() if ids_pieces else []
    ids_appareils = sorted(acces.appareils | {a[2] for a in associations})
    appareils = []
    for i in range(0, len(ids_appareils), 500):
        lot = ids_appareils[i:i + 500]
        appareils += src.execute(f"SELECT * FROM appareils WHERE id IN ({q(len(lot))})", lot).fetchall()
    supersessions = src.execute(
        f"SELECT * FROM piece_supersessions WHERE ref_old IN ({q(len(refs))}) "
        f"OR ref_new IN ({q(len(refs))})", refs + refs).fetchall()
    equivalences = src.execute(
        f"SELECT * FROM piece_equivalence_groups WHERE ref_piece IN ({q(len(refs))})",
        refs).fetchall()
    refs_modeles = sorted({a[3] for a in appareils if a[3]})
    decisions = []
    for i in range(0, len(refs_modeles), 500):
        lot = refs_modeles[i:i + 500]
        decisions += src.execute(
            f"SELECT * FROM reference_decisions WHERE ref_modele IN ({q(len(lot))})", lot).fetchall()

    cible = sqlite3.connect(':memory:')
    for table in TABLES:
        (sql,) = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                             [table]).fetchone()
        cible.execute(sql)
    for table, lignes in (('appareils', appareils), ('pieces', pieces),
                          ('piece_associations', associations),
                          ('piece_supersessions', supersessions),
                          ('piece_equivalence_groups', equivalences),
                          ('reference_decisions', decisions)):
        if lignes:
            cible.executemany(f"INSERT INTO {table} VALUES ({q(len(lignes[0]))})", lignes)
    cible.commit()
    entete = ("-- Extrait de appareils.db pour les tests du rapprochement des fiches\n"
              "-- Généré par scripts/extraire_base_fiches_test.py : ne pas modifier à la main.\n")
    sortie.write_text(entete + '\n'.join(cible.iterdump()) + '\n', encoding='utf-8')
    acces.fermer()
    print(f"{sortie} : {len(appareils)} appareils, {len(pieces)} pièces, "
          f"{len(associations)} liens, {len(supersessions)} remplacements, "
          f"{len(equivalences)} équivalences, {len(decisions)} décisions")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('base')
    parser.add_argument('--sortie', default=str(FIXTURES / 'base_extrait.sql'))
    args = parser.parse_args()
    extraire(args.base, Path(args.sortie))


if __name__ == '__main__':
    main()
