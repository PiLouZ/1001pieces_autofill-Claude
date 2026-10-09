"""
Garde-fou : chaque `StyleManager.X` utilisé dans src/ doit exister.

NON-RÉGRESSION (2026-10-09, v3.78.0) : une modification de style_manager.py a
supprimé `StyleManager.side_card` par erreur. Rien ne l'a signalé : la méthode
n'est appelée qu'à l'ouverture du gestionnaire de pièces, qu'aucun test
n'ouvre — la fenêtre aurait simplement refusé de s'ouvrir en production.
"""

import pathlib
import re

from src.ui.style_manager import StyleManager

_RACINE = pathlib.Path(__file__).resolve().parents[2] / "src"


def test_toutes_les_references_stylemanager_existent():
    references = set()
    for fichier in _RACINE.rglob("*.py"):
        if "theauditor" in fichier.parts:
            continue
        references |= set(re.findall(r"StyleManager\.([A-Za-z_]+)", fichier.read_text(encoding="utf-8")))
    manquants = sorted(r for r in references if not hasattr(StyleManager, r))
    assert references, "aucune référence trouvée : le chemin de recherche est faux"
    assert manquants == [], f"StyleManager n'a pas : {manquants}"
