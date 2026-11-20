"""
Gestionnaire de pièces : chargement des comptages en arrière-plan et fenêtre
« Modifier la pièce » à la mesure de son texte (2026-11-20).

Avant : la requête des comptages (2 à 3 s sur la base de production) tournait
sur le fil de l'interface — fenêtre figée, curseur d'attente, à chaque
ouverture ET à chaque réouverture. Et « Modifier la pièce », figée à
420 × 140 px, faisait se chevaucher les lignes des références liées.
"""

import time

import pytest

from src.ui.chargement_pieces import (ChargementComptages, comptages_par_id,
                                      fichier_base_lisible, fusionner_comptages)

# La requête d'avant (une seule, sur le fil de l'interface) : l'oracle — le
# tableau doit montrer exactement les mêmes lignes, dans le même ordre.
REQUETE_D_AVANT = """
        SELECT p.ref_piece, p.description, COUNT(DISTINCT pa.appareil_id) as nb_appareils,
               GROUP_CONCAT(DISTINCT NULLIF(TRIM(a.type), '')), COALESCE(p.is_phantom, 0)
        FROM pieces p
        LEFT JOIN piece_associations pa ON p.id = pa.piece_id
        LEFT JOIN appareils a ON pa.appareil_id = a.id
        GROUP BY p.id, p.ref_piece, p.description, p.is_phantom
        ORDER BY nb_appareils DESC, p.ref_piece ASC
        """


def _attendu(db):
    return db.execute_query(REQUETE_D_AVANT)


@pytest.fixture
def db(test_db_manager):
    return test_db_manager


def _vider_boucle(qapp, duree=0.05):
    fin = time.monotonic() + duree
    while time.monotonic() < fin:
        qapp.processEvents()


def _attendre(qapp, condition, delai=10.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def _peupler(db):
    db.create_piece_standalone('P_DEUX', 'Pièce à deux appareils')
    db.create_piece_standalone('P_UNE', 'Pièce à un appareil')
    db.create_piece_standalone('P_ZERO', 'Orpheline')
    conn = db.conn
    conn.executemany("INSERT INTO appareils (id, type, manufacturer, ref_modele) VALUES (?, ?, ?, ?)",
                     [(1, 'Four', 'X', 'M1'), (2, 'Lave-linge', 'X', 'M2')])
    for ref, appareils in (('P_DEUX', (1, 2)), ('P_UNE', (1,))):
        pid = conn.execute("SELECT id FROM pieces WHERE ref_piece = ?", [ref]).fetchone()[0]
        conn.executemany("INSERT INTO piece_associations (piece_id, appareil_id) VALUES (?, ?)",
                         [(pid, a) for a in appareils])
    conn.commit()


# ── Fonctions pures ──────────────────────────────────────────────────────────

def test_fusion_trie_comme_la_requete_et_garde_les_refs_nouvelles():
    apercu = [('A', 'a', 0, None, 0, 1), ('B', 'b', 0, None, 0, 2),
              ('C', 'c', 0, None, 1, 3), ('NOUVELLE', 'n', 0, None, 0, 4)]
    comptages = {1: (1, 'Four'), 2: (5, 'Four,Hotte'), 3: (1, None)}
    assert fusionner_comptages(apercu, comptages) == [
        ('B', 'b', 5, 'Four,Hotte', 0),
        ('A', 'a', 1, 'Four', 0),
        ('C', 'c', 1, None, 1),               # le fantôme reste fantôme
        ('NOUVELLE', 'n', 0, None, 0),        # inconnue des comptages : 0
    ]


def test_fichier_base_lisible(tmp_path):
    class Faux:
        pass
    faux = Faux()
    assert fichier_base_lisible(faux) is None
    faux.db_file = ':memory:'
    assert fichier_base_lisible(faux) is None
    faux.db_file = str(tmp_path / 'absente.db')
    assert fichier_base_lisible(faux) is None
    (tmp_path / 'base.db').write_bytes(b'')
    faux.db_file = str(tmp_path / 'base.db')
    assert fichier_base_lisible(faux) == faux.db_file


def test_la_tache_rend_le_meme_resultat_que_la_connexion_partagee(qapp, db):
    _peupler(db)
    attendu = db.lister_comptages_pieces()
    recu = []
    tache = ChargementComptages(db.db_file)
    tache.termine.connect(lambda lignes, erreur: recu.append((lignes, erreur)))
    tache.start()
    assert _attendre(qapp, lambda: recu)
    tache.wait()
    lignes, erreur = recu[0]
    assert erreur is None
    assert sorted(lignes) == sorted(attendu)
    id_deux = db.execute_query("SELECT id FROM pieces WHERE ref_piece = 'P_DEUX'")[0][0]
    assert comptages_par_id(lignes)[id_deux][0] == 2
    assert fusionner_comptages(db.lister_pieces_apercu(), comptages_par_id(lignes)) == _attendu(db)


def test_la_tache_signale_une_base_illisible(qapp, tmp_path):
    chemin = tmp_path / 'pas_une_base.db'
    chemin.write_bytes(b'ceci n est pas sqlite' * 100)
    recu = []
    tache = ChargementComptages(str(chemin))
    tache.termine.connect(lambda lignes, erreur: recu.append((lignes, erreur)))
    tache.start()
    assert _attendre(qapp, lambda: recu)
    tache.wait()
    assert recu[0][0] is None and recu[0][1]


# ── La fenêtre ───────────────────────────────────────────────────────────────

@pytest.fixture
def fenetre(qapp, db):
    import src.ui.pieces_manager as pm
    _peupler(db)
    fen = pm.PiecesManagerWindow(None, db)
    fen.show()
    assert _attendre(qapp, lambda: fen._data_loaded and not fen._loading_phase
                     and not (fen._tache_comptages and fen._tache_comptages.isRunning()))
    yield fen
    fen.close()
    _vider_boucle(qapp)


def test_ouverture_affiche_les_comptages(fenetre, db):
    assert fenetre._table_stack.currentIndex() == 1
    assert fenetre.all_pieces_data == _attendu(db)
    assert fenetre._tache_comptages is not None      # calcul fait hors du fil de l'interface
    assert '3 références' in fenetre.stats_label.text()
    assert '3 associations' in fenetre.stats_label.text()


def test_rechargement_immediat_avec_les_comptages_connus(fenetre, db, qapp):
    """Après une modification : le tableau reste affiché, la réf. renommée
    apparaît tout de suite, avec ses comptages."""
    assert db.rename_piece_catalog('P_UNE', 'P_UNE_BIS', 'Renommée')
    fenetre._load_pieces_data()
    assert fenetre._table_stack.currentIndex() == 1       # pas de retour au spinner
    lignes = {r[0]: r for r in fenetre.all_pieces_data}
    assert 'P_UNE' not in lignes
    assert lignes['P_UNE_BIS'][1:3] == ('Renommée', 1)
    assert _attendre(qapp, lambda: not fenetre._tache_comptages.isRunning())
    _vider_boucle(qapp)
    assert fenetre.all_pieces_data == _attendu(db)


def test_repli_synchrone_si_le_calcul_echoue(fenetre, db, qapp, monkeypatch):
    import src.ui.pieces_manager as pm
    db.create_piece_standalone('P_NEUVE', 'Neuve')
    monkeypatch.setattr(pm, 'fichier_base_lisible', lambda _db: None)
    fenetre._load_pieces_data()
    _vider_boucle(qapp)
    assert fenetre.all_pieces_data == _attendu(db)
    assert 'P_NEUVE' in {r[0] for r in fenetre.all_pieces_data}


def test_fermer_arrete_le_calcul(fenetre, qapp):
    fenetre._load_pieces_data()
    _vider_boucle(qapp, 0.01)
    fenetre.hide()
    assert not (fenetre._tache_comptages and fenetre._tache_comptages.isRunning())


# ── « Modifier la pièce » ────────────────────────────────────────────────────

def test_modifier_la_piece_a_la_mesure_du_texte(qapp):
    from src.ui.pieces_manager import PieceEditDialog
    liees = {'equivalentes': [f'REF{i:08d}' for i in range(7)]}
    libelles = {r: 'Un libellé tout à fait différent' for r in liees['equivalentes']}
    dlg = PieceEditDialog(None, 'REF_X', 'Libellé', liees, libelles, focus_field='desc')
    dlg.show()
    _vider_boucle(qapp)
    assert dlg.width() >= PieceEditDialog.LARGEUR
    assert dlg.remplaces_label.isVisible()
    layout = dlg.layout()
    assert dlg.height() >= layout.heightForWidth(dlg.width())
    # Chaque libellé tient dans sa hauteur (pas de chevauchement)
    for label in (dlg.detail_label, dlg.remplaces_label):
        assert label.height() >= label.heightForWidth(label.width())
    # Le champ Libellé occupe la largeur disponible
    assert dlg.desc_input.width() > dlg.width() // 2
    # Libellé identique à tous : l'avertissement disparaît, la fenêtre raccourcit
    haute = dlg.height()
    dlg.desc_input.setText('Un libellé tout à fait différent')
    _vider_boucle(qapp)
    assert not dlg.remplaces_label.isVisible()
    assert dlg.height() < haute
    dlg.close()
