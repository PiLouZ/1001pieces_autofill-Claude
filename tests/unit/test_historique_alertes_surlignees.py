"""
Tests — Les alertes « [!] » de l'historique sont surlignées en jaune avertissement

Demande de l'utilisateur (2026-10-13) : le bloc « pages vides » d'un import PDF se
perdait au milieu de la synthèse. Le bloc d'alerte = la ligne « [!] » et les lignes
« ==> » qui la suivent directement ; il s'arrête à la première ligne d'un autre type.
"""

import re

from src.core.config import Config
from src.ui.user_interaction_service import UserInteractionService


class _Fenetre:
    pass


SYNTHESE = """Import 805101.pdf:
Fichier PDF : 357 lignes extraites
     ==> Lignes traitées : 357
     [!] 805101.pdf : 4 pages vides — appareils peut-être manquants entre :
     ==> p.3 : DFI544BXXL-04 → DFI544D-02
     ==> Conseil : régénérez le PDF avec le tri inversé
Appareils :
     ==> Créés : 0"""


def _lignes_html(message):
    service = UserInteractionService(_Fenetre())
    service.add_to_history(message)
    return service._build_history_html().splitlines()


def _surlignee(lignes_html, texte):
    ligne = next(l for l in lignes_html if texte in l)
    return f'bgcolor="{Config.Colors.WARNING_BG}"' in ligne


def test_bloc_alerte_surligne():
    html = _lignes_html(SYNTHESE)
    assert _surlignee(html, "4 pages vides")
    assert _surlignee(html, "p.3 : DFI544BXXL-04")
    assert _surlignee(html, "Conseil")


def test_bloc_alerte_s_arrete_a_la_ligne_suivante():
    html = _lignes_html(SYNTHESE)
    assert not _surlignee(html, "Appareils :")
    assert not _surlignee(html, "Créés : 0")


def test_lignes_avant_l_alerte_inchangees():
    html = _lignes_html(SYNTHESE)
    assert not _surlignee(html, "Lignes traitées : 357")


def test_ligne_alerte_en_gras_detail_non():
    html = _lignes_html(SYNTHESE)
    alerte = next(l for l in html if "4 pages vides" in l)
    detail = next(l for l in html if "p.3 : DFI544BXXL-04" in l)
    assert "font-weight:bold" in alerte
    assert "font-weight:bold" not in detail
    assert Config.Colors.WARNING_TEXT in detail


def test_sans_alerte_aucun_surlignage():
    html = "\n".join(_lignes_html(
        "Import a.csv:\nFichier CSV : 2 lignes extraites\n     ==> Lignes traitées : 2"))
    assert Config.Colors.WARNING_BG not in html


def test_texte_echappe_dans_l_alerte():
    html = "\n".join(_lignes_html("Import a.csv:\n     [!] colonne <ref> & marque"))
    assert re.search(r"colonne &lt;ref&gt; &amp; marque", html)
