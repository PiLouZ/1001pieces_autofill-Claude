"""Libellé de pièce tiré du titre d'une fiche : coupe à « pour <type> » (CDC § 10.11)."""

import pytest

from src.utils.rapprochement_fiche.coupe_titre import couper_au_type, termes_appareils
from src.utils.rapprochement_fiche.rapprochement import libelle_depuis_titre


@pytest.mark.parametrize("titre, attendu", [
    # Exemple de la demande (fiche 7285)
    ("Pompe de vidange R2.5Y pour machine à laver (pièce générique)", "Pompe de vidange R2.5Y"),
    ("Pompe pour lave-vaisselle Bosch", "Pompe"),
    ("Filtres à charbon pour hotte (lot de 2)", "Filtres à charbon"),
    ("Résistance de voûte pour four et cuisinière", "Résistance de voûte"),
    ("Joint pour réfrigérateur et congélateur", "Joint"),
    ("Grille pour plaques de cuisson", "Grille"),                 # pluriel
    ("Tuyau pour sèche linge", "Tuyau"),                          # espace au lieu du tiret
    ("Bac pour refrigerateur", "Bac"),                            # accents absents
    ("Panier pour MACHINE A LAVER LA VAISSELLE", "Panier"),       # appellation, casse
    ("Etagère pour bouteilles pour réfrigérateur", "Etagère pour bouteilles"),
    # Caractéristique chiffrée après le type : gardée (choix B du 2026-11-12)
    ("Résistance pour sèche linge 1900W", "Résistance 1900W"),
    ("Ampoule pour four et micro-ondes 300°", "Ampoule 300°"),
    ("Bouton poussoir pour Machine à laver, Clavier WA 548", "Bouton poussoir, Clavier WA 548"),
    ("Vis pour hotte 4x20 (prix à l'unité)", "Vis 4x20"),
    # Pas de type juste après « pour » : inchangé
    ("Joint pour porte de four", "Joint pour porte de four"),
    ("Palier pour panier inférieur de lave-vaisselle", "Palier pour panier inférieur de lave-vaisselle"),
    ("Filtre à eau pour PUF100", "Filtre à eau pour PUF100"),
    ("Thermostat", "Thermostat"),
    # « four » n'est pas reconnu dans « fourche », ni en tête du titre
    ("Pièce pour fourche", "Pièce pour fourche"),
    ("Four pour rien", "Four pour rien"),
])
def test_coupe(titre, attendu):
    assert couper_au_type(titre) == attendu


def test_mentions_retirees_et_titre_vide():
    assert libelle_depuis_titre("Balconnet (photos non contractuelles)") == "Balconnet"
    assert libelle_depuis_titre("Pompe pour four (photo non contractuelle)") == "Pompe"
    assert libelle_depuis_titre("") == ""


def test_appellations_de_l_onglet():
    # Un type retiré de l'onglet n'est plus reconnu ; une appellation ajoutée l'est
    config = {"appareils": [{"type": "lave-linge", "genre": "m",
                             "variantes": [{"terme": "lessiveuse", "genre": "f"}]}]}
    assert "lessiveuse" in termes_appareils(config)
    assert libelle_depuis_titre("Courroie pour lessiveuse", config) == "Courroie"
    assert libelle_depuis_titre("Courroie pour four", config) == "Courroie pour four"
    # Les appellations inactives comptent aussi (« cocotte-minute » est désactivée)
    assert libelle_depuis_titre("Joint pour cocotte-minute") == "Joint"
