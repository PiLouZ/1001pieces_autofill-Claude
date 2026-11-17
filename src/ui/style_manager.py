"""
Style Manager - Phase 2 Refactoring
Gestion centralisée des styles et thèmes de l'application
"""

import os
import tempfile

_combo_arrow_path: str = ""


def _generate_combo_arrow() -> str:
    """Génère une icône chevron-down via qtawesome, la sauve en PNG et retourne son chemin."""
    global _combo_arrow_path
    if _combo_arrow_path:
        return _combo_arrow_path
    try:
        import qtawesome as qta
        icon = qta.icon('fa5s.chevron-down', color='#6c757d')
        pixmap = icon.pixmap(10, 10)
        path = os.path.join(tempfile.gettempdir(), '1001pieces_combo_arrow.png')
        pixmap.save(path)
        _combo_arrow_path = path
    except Exception:
        _combo_arrow_path = ""
    return _combo_arrow_path


_spin_arrow_paths: dict = {}


def _generate_spin_arrow(sens: str) -> str:
    """Petit chevron haut/bas (qtawesome) des champs numériques ; chemin du PNG, ou ""."""
    if sens in _spin_arrow_paths:
        return _spin_arrow_paths[sens]
    try:
        import qtawesome as qta
        pixmap = qta.icon(f'fa5s.chevron-{sens}', color='#6c757d').pixmap(8, 8)
        path = os.path.join(tempfile.gettempdir(), f'1001pieces_spin_{sens}.png')
        pixmap.save(path)
        _spin_arrow_paths[sens] = path
    except Exception:
        _spin_arrow_paths[sens] = ""
    return _spin_arrow_paths[sens]


_check_mark_path: str = ""


def _generate_check_mark() -> str:
    """Coche blanche (qtawesome) pour les cases cochées ; chemin du PNG, ou ""."""
    global _check_mark_path
    if _check_mark_path:
        return _check_mark_path
    try:
        import qtawesome as qta
        pixmap = qta.icon('fa5s.check', color='#ffffff').pixmap(12, 12)
        path = os.path.join(tempfile.gettempdir(), '1001pieces_check_mark.png')
        pixmap.save(path)
        _check_mark_path = path
    except Exception:
        _check_mark_path = ""
    return _check_mark_path


_inline_icon_paths: dict = {}


def icon_png_path(icon_name: str, color: str, size: int = 11) -> str:
    """Chemin d'un PNG 2× de l'icône qtawesome (rendu une fois par nom, couleur,
    taille), pour un `<img>` ou un `image: url(...)` de feuille de style ; "" si
    qtawesome échoue."""
    key = (icon_name, color, size)
    path = _inline_icon_paths.get(key)
    if path is None:
        try:
            import qtawesome as qta
            pixmap = qta.icon(icon_name, color=color).pixmap(size * 2, size * 2)
            safe = f"{icon_name}_{color}_{size}".replace('.', '_').replace('#', '')
            path = os.path.join(tempfile.gettempdir(), f'1001pieces_icone_{safe}.png')
            pixmap.save(path)
        except Exception:
            path = ""
        _inline_icon_paths[key] = path
    return path


def inline_icon_html(icon_name: str, color: str, size: int = 11) -> str:
    """Icône qtawesome insérable dans le texte riche d'un QLabel (`<img>`).

    Remplace les glyphes (⚠, ✓…) dans les libellés, comme le chevron des listes
    déroulantes. Chaîne vide si qtawesome échoue (le texte reste lisible).
    """
    path = icon_png_path(icon_name, color, size)
    if not path:
        return ""
    # Image 2× affichée à `size` : nette sur écran Retina
    return f'<img src="{path}" width="{size}" height="{size}" style="vertical-align: middle;">'


class StyleManager:
    """Gestionnaire centralisé des styles CSS modernes

    Palette de référence : `Config.Colors` (src/core/config.py) — PRIMARY #0d6efd,
    SUCCESS #198754, DANGER #dc3545, WARNING #fd7e14 et leurs variantes survol /
    fond / texte. Toute nouvelle couleur de rôle (bouton principal, validation,
    erreur, focus) doit en reprendre la valeur. Les couleurs de CATÉGORIE (types
    d'action de l'historique, relations Remplace / Remplacée par / Équivalence)
    sont volontairement distinctes et ne s'y rattachent pas.
    """

    # === Styles QSS réutilisables (boutons plats / transparents) ===
    # Centralisés ici pour éviter la duplication de ces littéraux dans les
    # multiples fenêtres (cf. audit structure 2026-06-11, point 9).

    # Style nu pour un widget plat sans bord ni fond (ex: bouton-spinner)
    FLAT_TRANSPARENT = "border: none; background: transparent;"

    # Texte d'appoint sous un contrôle (détail, récapitulatif) : gris, petit
    TEXTE_SECONDAIRE = "color: #6c757d; font-size: 11px;"

    # Même gabarit, en orange : ce qui va être écrasé ou perdu
    TEXTE_AVERTISSEMENT = "color: #b45309; font-size: 11px;"

    # === Styles QSS partagés entre fenêtres (dédoublonnés, audit 2026-11-05) ===
    # Chacun était recopié à l'identique dans plusieurs fichiers.

    # Texte en gras, sans autre réglage
    TEXTE_GRAS = 'font-weight: bold;'
    # Séparateur discret entre éléments d'une ligne (« | », « · »)
    TEXTE_SEPARATEUR = 'color: #dee2e6;'
    # Fond transparent seul
    FOND_TRANSPARENT = 'background: transparent;'
    # Fond blanc seul
    FOND_BLANC = 'background: white;'
    # Aucune bordure
    SANS_BORDURE = 'border: none;'
    # Zone blanche bordée de gris clair (aperçus, champs)
    CHAMP_BLANC_BORDE = 'background: white; border: 1px solid #dee2e6;'
    # Libellé gras posé sur un fond (sans fond ni bordure propres)
    TEXTE_GRAS_TRANSPARENT = 'font-weight: bold; background: transparent; border: none;'
    # Titre de section ou de fenêtre (13 px, gras)
    TITRE_SECTION = 'font-weight: bold; font-size: 13px; color: #212529;'
    # Barre de progression fine et sobre (gris)
    BARRE_PROGRESSION_DISCRETE = (
        '\n            QProgressBar { border: none; border-radius: 3px; background: #e9ecef; }\n            QProgressBar::chunk { border-radius: 3px; background: #495057; }\n        '
    )
    # Texte d'appoint estompé (gris clair, petit)
    TEXTE_ESTOMPE = 'color: #adb5bd; font-size: 11px;'
    # Texte gris moyen (12 px)
    TEXTE_GRIS_MOYEN = 'color: #555555; font-size: 12px;'
    # Comme TEXTE_SECONDAIRE, en italique (indications, états vides)
    TEXTE_SECONDAIRE_ITALIQUE = 'color: #6c757d; font-size: 11px; font-style: italic;'
    # Indicateur de succès (vert)
    TEXTE_SUCCES = 'color: green;'
    # Zone de défilement sans fond ni bordure
    ZONE_DEFILEMENT_NUE = 'QScrollArea { background: transparent; border: none; }'
    # Cadre gris clair arrondi (4 px) autour d'un groupe
    CADRE_GRIS_CLAIR = 'QWidget { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }'
    # Contenu posé dans un cadre stylé : ni fond ni bordure hérités du cadre
    CONTENU_SANS_CADRE = 'QWidget { background: transparent; border: none; }'
    # Petit libellé gris foncé posé sur un cadre
    LIBELLE_PETIT_TRANSPARENT = 'font-size: 11px; color: #495057; background: transparent; border: none;'
    # Carte gris clair arrondie (6 px)
    CARTE_GRIS_CLAIR = 'background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px;'
    # Message d'erreur sous un champ (rouge, petit)
    TEXTE_ERREUR_PETIT = 'color: #dc3545; font-size: 11px; padding: 1px 0;'
    # Message d'erreur rouge sombre, petit
    TEXTE_ERREUR_SOMBRE = 'color: #c0392b; font-size: 11px;'
    # Petit libellé gris moyen posé sur un cadre
    LIBELLE_PETIT_GRIS_TRANSPARENT = 'font-size: 11px; color: #555; background: transparent; border: none;'
    # Texte gris moyen, petit (11 px)
    TEXTE_GRIS_PETIT = 'color: #555555; font-size: 11px;'
    # Zone de défilement à fond transparent
    ZONE_DEFILEMENT_TRANSPARENTE = 'QScrollArea { background: transparent; }'
    # Petit bouton-outil à bascule (bleu quand coché)
    BOUTON_OUTIL_BASCULE = (
        'QToolButton { border: 1px solid #ced4da; border-radius: 4px; background: #f8f9fa; padding: 2px; }QToolButton:checked { background: #e7f1ff; border-color: #0d6efd; }'
    )
    # Fenêtre surgissante blanche arrondie (8 px)
    POPUP_CADRE = (
        '\n            QDialog {\n                background: white;\n                border: 1px solid #ced4da;\n                border-radius: 8px;\n            }\n        '
    )
    # En-tête d'une fenêtre surgissante (bandeau gris clair arrondi en haut)
    POPUP_ENTETE = (
        'background: #f8f9fa;border-bottom: 1px solid #e9ecef;border-top-left-radius: 8px;border-top-right-radius: 8px;'
    )
    # Titre moyen (14 px) avec petite marge basse
    TITRE_MOYEN = 'font-size: 14px; margin-bottom: 4px;'
    # Indicateur « en cours / en attente » (orange)
    TEXTE_EN_COURS = 'color: orange;'
    # Bandeau d'information bleu pâle
    BANDEAU_INFO = (
        'font-size: 11px; padding: 6px 10px; color: #495057; background-color: #e7f3ff; border-radius: 4px;'
    )
    # Bandeau d'avertissement ambre (fiche du site à refaire depuis les PDF)
    BANDEAU_AVERTISSEMENT = (
        'font-size: 12px; padding: 8px 12px; color: #7c2d12; background-color: #fff4e5;'
        ' border: 1px solid #f5c88a; border-radius: 4px;'
    )

    # Idem mais ciblé sur QPushButton
    FLAT_TRANSPARENT_BUTTON = "QPushButton { border: none; background: transparent; }"

    # Bouton-icône compact sans marge ni contour (ex: icônes d'action inline)
    ICON_BUTTON = (
        "QPushButton { border: none; background: transparent; "
        "padding: 0; margin: 0; outline: none; }"
    )

    # Bouton de rafraîchissement plat avec survol discret
    REFRESH_BUTTON = (
        "QPushButton { border: none; background: transparent; } "
        "QPushButton:hover { background: rgba(0,0,0,0.08); border-radius: 3px; }"
    )

    # === Cluster "santé des données" — boutons toolbar (lignes incomplètes / doublons) ===
    # Géométrie UNIQUE et partagée par les deux boutons (cf. IncompleteButtonService et
    # DuplicateIndicatorService) : même padding/bordure/rayon/police → les deux boutons
    # restent rigoureusement de même taille par construction ; seule la couleur change
    # selon l'état (neutre au repos, orange en alerte). Toute modif de ces styles se fait
    # ICI uniquement, jamais en dupliquant le littéral dans les services.
    HEALTH_BTN_NEUTRAL = (
        "QPushButton { background-color: #f8f9fa; color: #495057;"
        " border: 2px solid #ced4da; border-radius: 4px; padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #e9ecef; }"
    )
    HEALTH_BTN_ALERT = (
        "QPushButton {"
        " background-color: #ff6b35; color: white; font-weight: bold;"
        " border: 2px solid #e55a2b; border-radius: 4px; padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #e55a2b; }"
    )

    # « Auto-complétés à vérifier (N) | Tout valider » (v3.89.2) : deux moitiés
    # accolées, même géométrie que le cluster ci-dessus (même hauteur dans la barre
    # d'état). Bleu = consulter (couleur principale), vert = valider (comme les
    # actions finales des fenêtres) : deux gestes, deux couleurs.
    AUTOCOMPLETES_OUVRIR_BTN = (
        "QPushButton { background-color: #0d6efd; color: white; font-weight: bold;"
        " border: 2px solid #0d6efd; border-top-left-radius: 4px; border-bottom-left-radius: 4px;"
        " border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
        " padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #0b5ed7; border-color: #0b5ed7; }"
    )
    AUTOCOMPLETES_VALIDER_BTN = (
        "QPushButton { background-color: #198754; color: white; font-weight: bold;"
        " border: 2px solid #198754; border-left: 1px solid white;"
        " border-top-right-radius: 4px; border-bottom-right-radius: 4px;"
        " border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
        " padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #157347; border-color: #157347;"
        " border-left: 1px solid white; }"
    )

    # « Suggestions à valider (N) » (v3.92.0) : même géométrie que le cluster, en
    # ambre (couleur historique de l'ancien bandeau) — distinct de l'orange des
    # incomplètes. Texte foncé : le blanc sur ambre serait illisible.
    SUGGESTIONS_BTN = (
        "QPushButton { background-color: #ffc107; color: #4e342e; font-weight: bold;"
        " border: 2px solid #e0a800; border-radius: 4px; padding: 3px 9px; font-size: 11px; }"
        "QPushButton:hover { background-color: #e0a800; }"
    )

    # Flèches ▲/▼ qui encadrent « Lignes à traiter » : même bordure 2px et même
    # rayon que les boutons du cluster → même hauteur, alignées sans retouche.
    HEALTH_NAV_BTN = (
        "QToolButton { background-color: #f8f9fa; border: 2px solid #ced4da;"
        " border-radius: 4px; padding: 3px 4px; }"
        "QToolButton:hover { background-color: #e9ecef; }"
        "QToolButton:disabled { background-color: #f8f9fa; border-color: #e9ecef; }"
    )

    # === Boutons d'export (fenêtre principale) — état inactif commun ===
    # Chaque bouton garde sa couleur active propre (CSV sarcelle, Méta Title orange,
    # Méta Desc jaune, HTML blancs) ; seul l'état inactif est partagé, pour qu'on
    # distingue d'un coup d'œil ce qui est cliquable. Avant : les HTML inactifs
    # ressemblaient à leur état actif, et CSV/Méta inactifs étaient gris foncé.
    # Pas de propriété `border` ici : chaque bouton garde l'épaisseur de bordure de
    # son état actif (aucune pour CSV/Méta, 1 px pour HTML), sinon le bouton
    # changerait de taille en s'activant.
    EXPORT_BTN_DISABLED_RULES = "background: #f1f3f5; color: #adb5bd;"

    # ── Boutons d'export de la barre (CSV, Méta, HTML, Titre, Fiche) ──────────
    # Couleurs (fond, survol[, appui]) des boutons à fond plein.
    COULEURS_EXPORT_CSV = ("#134c4d", "#11403f")
    COULEURS_META_TITLE = ("#fd7e14", "#e5711f")
    COULEURS_META_DESC = ("#ffc107", "#e5a801")
    COULEURS_TITRE = ("#6f42c1", "#5e37a6", "#512f8f")    # violet
    COULEURS_FICHE = ("#0b5ed7", "#0a53be", "#094ba8")    # bleu

    @staticmethod
    def bouton_export_plein(fond: str, survol: str) -> str:
        """QPushButton à fond coloré plein, texte blanc gras (CSV, Méta Title, Méta Desc)."""
        return f"""
            QPushButton {{
                background-color: {fond};
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {survol};
            }}
            QPushButton:disabled {{ {StyleManager.EXPORT_BTN_DISABLED_RULES} }}
        """

    @staticmethod
    def bouton_split_plein(fond: str, survol: str, appui: str) -> str:
        """QToolButton à menu (MenuButtonPopup), fond coloré plein et flèche de menu
        blanche — la noire par défaut ne se lit pas sur fond coloré (Titre, Fiche)."""
        fleche = icon_png_path('fa5s.caret-down', 'white', 10)
        regle_fleche = f"image: url({fleche}); width: 10px; height: 10px;" if fleche else ""
        return f"""
            QToolButton {{
                background-color: {fond};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
            }}
            QToolButton:hover {{
                background-color: {survol};
            }}
            QToolButton:pressed {{
                background-color: {appui};
            }}
            QToolButton:disabled {{
                {StyleManager.EXPORT_BTN_DISABLED_RULES}
            }}
            QToolButton::menu-button {{
                border: none;
                border-left: 1px solid rgba(255, 255, 255, 0.35);
                width: 30px;
            }}
            QToolButton::menu-arrow {{
                {regle_fleche}
            }}
        """

    # QToolButton à menu, fond blanc aligné sur le QPushButton global (HTML Détails).
    BOUTON_SPLIT_NEUTRE = f"""
            QToolButton {{
                background: white;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                color: #343a40;
            }}
            QToolButton:hover {{
                background: #f1f3f5;
                border-color: #adb5bd;
                color: #212529;
            }}
            QToolButton:pressed {{
                background: #e9ecef;
                border-color: #6c757d;
            }}
            QToolButton:disabled {{
                {EXPORT_BTN_DISABLED_RULES}
            }}
            QToolButton::menu-button {{
                /* Mode MenuButtonPopup : la flèche est centrée dans cette zone
                   (::menu-indicator est ignoré dans ce mode). Élargir la zone
                   éloigne la flèche du bord droit → aération. */
                border: none;
                width: 30px;
            }}
        """

    # Gabarit explicite, aligné sur CSV / Méta (8 × 12 px) : le style global des
    # boutons est plus compact (HTML Marques).
    BOUTON_EXPORT_NEUTRE = (
        "QPushButton { padding: 8px 12px; font-weight: 500; }"
        f"QPushButton:disabled {{ {EXPORT_BTN_DISABLED_RULES} }}"
    )

    # Bouton « effacer les filtres » (icône ✕ qtawesome) : gris neutre au repos
    # (vider des champs n'est pas une action destructrice), rouge pâle au survol.
    CLEAR_FILTERS_BUTTON = (
        "QPushButton { background-color: #f8f9fa; color: #868e96;"
        " border: 1px solid #ced4da; border-radius: 3px;"
        " padding: 0px; }"
        "QPushButton:hover { background-color: #f8d7da; border-color: #f1aeb5; }"
        "QPushButton:pressed { background-color: #f1aeb5; border-color: #ea868f; }"
    )

    # Boutons de l'action FINALE d'une fenêtre (Importer, Confirmer l'import,
    # Appliquer le nettoyage) et de son « Annuler » : même hauteur, texte 12 px.
    # Avant : 11 px et padding 3 px — l'action principale de la fenêtre d'import
    # était le plus petit bouton de l'écran.
    PRIMARY_ACTION_BUTTON = (
        "QPushButton { background-color: #198754; color: white; border: 1px solid #198754;"
        " padding: 5px 16px; border-radius: 4px; font-size: 12px; font-weight: bold; }"
        "QPushButton:hover { background-color: #157347; border-color: #157347; }"
        "QPushButton:disabled { background-color: #f1f3f5; color: #adb5bd; border-color: #e9ecef; }"
    )
    SECONDARY_ACTION_BUTTON = (
        "QPushButton { background: white; color: #343a40; border: 1px solid #ced4da;"
        " padding: 5px 14px; border-radius: 4px; font-size: 12px; font-weight: normal; }"
        "QPushButton:hover { background: #f1f3f5; border-color: #adb5bd; }"
    )

    # Rôle « Compact » : outils à l'intérieur d'une fenêtre (Parcourir, Ajouter une
    # colonne, Désélectionner tout, actions groupées) — contour discret, 11 px.
    SECONDARY_COMPACT_BUTTON = (
        "QPushButton { background: white; color: #343a40; border: 1px solid #ced4da;"
        " padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: normal; }"
        "QPushButton:hover { background: #f1f3f5; border-color: #adb5bd; }"
        "QPushButton:disabled { background: #f8f9fa; color: #adb5bd; border-color: #e9ecef; }"
    )

    # Action finale destructive (Restaurer une sauvegarde : remplace la base) :
    # mêmes mesures que PRIMARY / SECONDARY_ACTION_BUTTON, en rouge contour —
    # un vert « valider » serait trompeur.
    DANGER_ACTION_BUTTON = (
        "QPushButton { background: white; color: #c0392b; border: 1px solid #ea868f;"
        " padding: 5px 14px; border-radius: 4px; font-size: 12px; font-weight: bold; }"
        "QPushButton:hover { background: #f8d7da; border-color: #dc3545; }"
        "QPushButton:disabled { background: #f8f9fa; color: #adb5bd; border-color: #e9ecef; font-weight: normal; }"
    )

    # Rôle « Danger » : action destructive (vider, retirer). Texte rouge sur fond
    # blanc plutôt que rouge plein : signale sans crier ; mêmes mesures que Compact.
    DANGER_COMPACT_BUTTON = (
        "QPushButton { background: white; color: #c0392b; border: 1px solid #f1aeb5;"
        " padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: normal; }"
        "QPushButton:hover { background: #f8d7da; border-color: #ea868f; }"
        "QPushButton:disabled { background: #f8f9fa; color: #adb5bd; border-color: #e9ecef; }"
    )

    # Onglets segmentés (CSV / HTML, Logs bruts / Auto-complétion…, onglets du
    # nettoyage) : bouton coché = fond gris foncé.
    SEGMENTED_BUTTON = (
        "QPushButton { padding: 4px 12px; font-size: 11px; border-radius: 4px; }"
        "QPushButton:checked { background-color: #495057; color: white; border-color: #495057; }"
    )

    # Petits boutons-icônes plats (en-tête du panneau des pièces) : sans cadre,
    # fond discret au survol — même famille que le bouton d'ouverture de l'historique.
    PANEL_ICON_BUTTON = (
        "QPushButton { background: transparent; border: none; border-radius: 3px;"
        " min-width: 22px; max-width: 22px; min-height: 20px; max-height: 20px; padding: 0px; }"
        "QPushButton:hover { background-color: #e9ecef; }"
    )

    # Ligne « Réf. associée » en tête de la carte ≡ Équivalences du gestionnaire
    # de pièces (src/ui/ligne_reference_associee.py)
    REF_ASSOCIEE_TITRE = ('color: #8e44ad; font-size: 11px; font-weight: bold;'
                          ' background: transparent; border: none;')
    REF_ASSOCIEE_ETAT = ('color: #adb5bd; font-size: 11px; font-style: italic;'
                         ' background: transparent; border: none;')
    REF_ASSOCIEE_LIEN = ('QPushButton { border: none; background: transparent; color: #8e44ad;'
                         ' font-size: 11px; text-decoration: underline; padding: 0 2px; }')
    REF_ASSOCIEE_CROIX = ('color: #dc3545; font-size: 13px; background: transparent;'
                          ' border: none; padding: 0 2px;')
    REF_ASSOCIEE_ROLE = 'color: #6c757d; font-size: 11px; background: transparent; border: none;'
    REF_ASSOCIEE_PIECE = ('color: #868e96; font-weight: bold; font-size: 11px; font-family: monospace;'
                          ' background: transparent; border: none;')
    # Saisie directe d'une relation dans une carte (src/ui/saisie_relation.py)
    SAISIE_RELATION = ('QLineEdit { background: white; border: 1px solid #ced4da; border-radius: 4px;'
                       ' padding: 2px 6px; font-size: 11px; }'
                       ' QLineEdit:focus { border-color: #80bdff; }'
                       ' QLineEdit:disabled { background: #f1f3f5; color: #adb5bd; }')
    SAISIE_RELATION_BILAN = 'color: #2e7d32; font-size: 11px; padding: 1px 0;'
    REF_ASSOCIEE_TRAIT = 'border: none; border-top: 1px dashed #d7c4e0; margin-top: 2px;'

    @staticmethod
    def ref_associee_puce(couleur: str, italique: bool = False) -> str:
        """Référence de la ligne « Réf. associée » : comme une puce RefTagList."""
        return (f"color: {couleur}; font-weight: bold; font-size: 11px; font-family: monospace;"
                f" background: transparent; border: none;"
                + (" font-style: italic;" if italique else ""))

    # Carte « nouvelle pièce » du panneau des pièces (PieceAddCard) : contour
    # pointillé bleu = élément en cours de création ; champs et boutons compacts
    # (le style global des champs, 8 px de marge, est trop haut pour ce panneau).
    PIECE_ADD_CARD = (
        "QFrame#pieceAddCard { background: white; border: 1px dashed #80bdff; border-radius: 6px; }"
        "QFrame#pieceAddCard QLineEdit { padding: 3px 8px; border: 1px solid #ced4da;"
        " border-radius: 4px; font-size: 12px; background: white; }"
        "QFrame#pieceAddCard QLineEdit:focus { border-color: #80bdff; }"
        "QLineEdit#pieceAddRef { font-weight: bold; }"
        "QLabel#pieceAddTarget { background: #e7f1ff; color: #0b5ed7; border-radius: 3px;"
        " padding: 1px 6px; font-size: 11px; }"
        "QLabel#pieceAddHint { color: #adb5bd; font-size: 11px; }"
        "QPushButton#pieceAddCancel { background: transparent; border: none; color: #6c757d;"
        " padding: 3px 8px; font-size: 12px; font-weight: normal; min-height: 0px; }"
        "QPushButton#pieceAddCancel:hover { color: #212529; background: #e9ecef; border-radius: 4px; }"
        "QPushButton#pieceAddSubmit { background: #0d6efd; color: white; border: none;"
        " border-radius: 4px; padding: 3px 12px; font-size: 12px; font-weight: 600; min-height: 0px; }"
        "QPushButton#pieceAddSubmit:hover { background: #0b5ed7; }"
        "QPushButton#pieceAddSubmit:pressed { background: #0a58ca; }"
    )

    # Barre de filtres des fenêtres secondaires : désormais identique au standard
    # global des champs (conservée pour ses appelants ; rien à surcharger).
    COMPACT_FILTER_BAR = ""

    # Cartes du panneau latéral du gestionnaire de pièces (Équivalences, Remplace,
    # Remplacée par) : fond gris clair arrondi, sans bordure — remplace les cadres
    # gris bordés (QFrame.StyledPanel). Appliqué par objectName pour ne pas
    # descendre sur les widgets enfants.
    @staticmethod
    def side_card(object_name: str) -> str:
        return (f"QFrame#{object_name} {{ background: #f1f3f5; border: none;"
                f" border-radius: 6px; }}")

    @staticmethod
    def side_card_depot(object_name: str) -> str:
        """Carte du panneau des pièces survolée par une réf. glissée."""
        return (f"QFrame#{object_name} {{ background: #e7f1ff; border: 1px dashed #4a90d9;"
                f" border-radius: 6px; }}")

    # Surlignage temporaire d'une pièce tout juste ajoutée (vert pâle, 2 s)
    PIECE_ADDED_HIGHLIGHT = "#d1e7dd"

    @staticmethod
    def get_modern_style() -> str:
        """Retourner le style CSS moderne complet de l'application"""
        arrow_path = _generate_combo_arrow()
        arrow_rule = (
            f"image: url({arrow_path}); width: 10px; height: 10px; margin-right: 4px;"
            if arrow_path else
            "width: 8px; height: 8px; margin-right: 4px;"
        )
        style = """
        /* === RESET ET BASE === */
        QWidget {
            font-family: -apple-system, 'SF Pro Display', system-ui, 'Helvetica Neue', sans-serif;
            font-size: 13px;
        }

        /* === WINDOW PRINCIPALE === */
        QMainWindow {
            background-color: #f8f9fa;
            color: #212529;
        }

        /* === BOUTONS ===
           Style par défaut = rôle « Secondaire » (Annuler, Fermer, tout bouton
           sans style particulier) : blanc, contour gris, 12 px. Mêmes mesures
           que StyleManager.SECONDARY_ACTION_BUTTON et PRIMARY_ACTION_BUTTON →
           un bouton non stylé est aligné sur les boutons d'action. Avant :
           dégradé, 13 px, marge 8 × 16 px (plus gros que les boutons stylés). */
        QPushButton {
            background: white;
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 5px 14px;
            font-size: 12px;
            font-weight: normal;
            color: #343a40;
        }

        QPushButton:hover {
            background: #f1f3f5;
            border-color: #adb5bd;
            color: #212529;
        }

        QPushButton:pressed {
            background: #e9ecef;
            border-color: #6c757d;
        }

        QPushButton:disabled {
            background-color: #f8f9fa;
            color: #adb5bd;
            border-color: #e9ecef;
        }

        /* === BOUTONS PRIMAIRES === */
        QPushButton[class="primary"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0d6efd, stop: 1 #0b5ed7);
            border: 1px solid #0a58ca;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="primary"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0b5ed7, stop: 1 #0a58ca);
            border-color: #0a53be;
        }
        
        QPushButton[class="primary"]:pressed {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0a58ca, stop: 1 #0a53be);
        }

        /* === BOUTONS SUCCESS === */
        QPushButton[class="success"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #198754, stop: 1 #157347);
            border: 1px solid #146c43;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="success"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #157347, stop: 1 #146c43);
            border-color: #13653f;
        }

        /* === BOUTONS WARNING === */
        QPushButton[class="warning"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #fd7e14, stop: 1 #e8680d);
            border: 1px solid #d96c0c;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="warning"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e8680d, stop: 1 #d96c0c);
            border-color: #ca650b;
        }

        /* === BOUTONS DANGER === */
        QPushButton[class="danger"] {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #dc3545, stop: 1 #c82333);
            border: 1px solid #bd2130;
            color: white;
            font-weight: 600;
        }
        
        QPushButton[class="danger"]:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #c82333, stop: 1 #bd2130);
            border-color: #b21e2d;
        }

        /* === CHAMPS DE SAISIE === */
        /* Champs : UNE hauteur pour toute l'application (~30 px). Avant : 36 px
           pour les champs non stylés, 22 à 30 px pour les autres. Les zones de
           texte multilignes gardent une marge plus large (règle suivante). */
        QLineEdit, QComboBox, QDateEdit, QSpinBox {
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 4px 8px;
            min-height: 20px;
            background-color: white;
            color: #495057;
            selection-background-color: #0d6efd;
        }

        QTextEdit {
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 6px 8px;
            background-color: white;
            color: #495057;
            selection-background-color: #0d6efd;
        }
        
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
            border-color: #80bdff;
            outline: 0;
        }
        
        QLineEdit:hover, QTextEdit:hover, QComboBox:hover {
            border-color: #adb5bd;
        }

        /* Éditeur de cellule des tableaux (double-clic / F2) : sans la marge
           intérieure de 8 px des champs de formulaire, qui ne laissait que 7 px au
           texte dans une ligne de 26 px. Bordure bleue = cellule en édition. */
        QTableView QLineEdit {
            padding: 0px 4px;
            border: 1px solid #80bdff;
            border-radius: 0px;
        }

        /* === COMBOBOX SPECIFIQUE === */
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        
        QComboBox::down-arrow {
            %%ARROW_RULE%%
        }

        /* Champs de date à calendrier : même chevron que les listes déroulantes
           (sinon bloc sombre natif) */
        QDateEdit::drop-down {
            border: none;
            width: 20px;
        }

        QDateEdit::down-arrow {
            %%ARROW_RULE%%
        }

        /* Champs numériques : le cadre stylé plus haut fait dessiner les
           boutons ▲▼ par la feuille de style, sans flèche ni séparation si
           on ne les décrit pas (traits isolés sur macOS). */
        QSpinBox {
            padding-right: 20px;
        }

        QSpinBox::up-button, QSpinBox::down-button {
            subcontrol-origin: border;
            width: 18px;
            border: none;
            border-left: 1px solid #e3e6ea;
            background: transparent;
        }

        QSpinBox::up-button {
            subcontrol-position: top right;
            border-top-right-radius: 4px;
        }

        QSpinBox::down-button {
            subcontrol-position: bottom right;
            border-bottom-right-radius: 4px;
        }

        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background: #f1f3f5;
        }

        QSpinBox::up-arrow {
            %%SPIN_UP_RULE%%
        }

        QSpinBox::down-arrow {
            %%SPIN_DOWN_RULE%%
        }
        
        QComboBox QAbstractItemView {
            border: 1px solid #ced4da;
            background-color: white;
            selection-background-color: #e7f1ff;
            selection-color: #0d6efd;
            outline: none;
        }

        /* === TABLEAUX === */
        QTableWidget {
            background-color: white;
            alternate-background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            gridline-color: #e9ecef;
            selection-background-color: #0056b3;
            selection-color: white;
        }
        
        /* Tableau principal (QTableView, non couvert par la règle QTableWidget) :
           une ligne sur deux teintée — le gris par défaut de Qt (#f7f7f7) était
           à peine visible sur fond blanc. */
        CustomTableView {
            alternate-background-color: #f1f4f8;
        }

        QHeaderView::section {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #f8f9fa, stop: 1 #e9ecef);
            border: 1px solid #dee2e6;
            border-left: none;
            padding: 8px 12px;
            font-weight: 600;
            color: #495057;
        }
        
        QHeaderView::section:first {
            border-left: 1px solid #dee2e6;
        }

        /* Numéros de ligne : pas de marge verticale, sinon ils seraient rognés
           avec les hauteurs de ligne réduites (réglage Affichage → Hauteur). */
        QHeaderView::section:vertical {
            padding: 0px 8px;
        }
        
        QHeaderView::section:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e9ecef, stop: 1 #dee2e6);
        }

        /* === ONGLETS === */
        QTabWidget::pane {
            border: 1px solid #dee2e6;
            background-color: white;
            border-radius: 0 6px 6px 6px;
        }
        
        QTabBar::tab {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #f8f9fa, stop: 1 #e9ecef);
            border: 1px solid #dee2e6;
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 2px;
            color: #6c757d;
            border-radius: 6px 6px 0 0;
        }
        
        QTabBar::tab:selected {
            background: white;
            color: #0d6efd;
            font-weight: 600;
            border-bottom: 1px solid white;
        }
        
        QTabBar::tab:hover:!selected {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #e9ecef, stop: 1 #dee2e6);
            color: #495057;
        }

        /* === LISTES === */
        QListWidget {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            outline: none;
        }
        
        QListWidget::item {
            padding: 8px 12px;
            border-bottom: 1px solid #f8f9fa;
        }
        
        QListWidget::item:selected {
            background-color: #e7f1ff;
            color: #0d6efd;
        }
        
        QListWidget::item:hover {
            background-color: #f8f9fa;
        }

        /* === BARRES DE DÉFILEMENT === */
        QScrollBar:vertical {
            border: none;
            background-color: #f8f9fa;
            width: 12px;
            border-radius: 6px;
        }
        
        QScrollBar::handle:vertical {
            background-color: #ced4da;
            border-radius: 6px;
            min-height: 20px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #adb5bd;
        }
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        
        QScrollBar:horizontal {
            border: none;
            background-color: #f8f9fa;
            height: 12px;
            border-radius: 6px;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #ced4da;
            border-radius: 6px;
            min-width: 20px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #adb5bd;
        }
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0;
        }

        /* === BARRE DE STATUT === */
        QStatusBar {
            background-color: #e9ecef;
            border-top: 1px solid #dee2e6;
            color: #495057;
            font-size: 12px;
        }

        /* === TOOLBAR === */
        QToolBar {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #ffffff, stop: 1 #f8f9fa);
            border: none;
            border-bottom: 1px solid #dee2e6;
            spacing: 4px;
            padding: 4px;
        }
        
        QToolBar::separator {
            background-color: #dee2e6;
            width: 1px;
            margin: 4px 8px;
        }

        /* Actions et menus déroulants de la barre d'outils : un seul style plat
           (texte sans cadre, fond discret au survol). Les menus Affichage /
           Données / Configuration ne se distinguent plus que par leur chevron. */
        QToolBar QToolButton {
            background: transparent;
            border: none;
            border-radius: 4px;
            padding: 4px 6px;
            color: #212529;
        }

        QToolBar QToolButton:hover {
            background-color: #e9ecef;
        }

        QToolBar QToolButton:pressed {
            background-color: #dee2e6;
        }

        QToolBar QToolButton:disabled {
            color: #adb5bd;
        }

        QPushButton#menuButton {
            background: transparent;
            border: none;
            border-radius: 4px;
            padding: 4px 22px 4px 6px;
            font-weight: normal;
            color: #212529;
            min-height: 0px;
        }

        QPushButton#menuButton:hover {
            background-color: #e9ecef;
        }

        QPushButton#menuButton:pressed {
            background-color: #dee2e6;
        }

        QPushButton#menuButton::menu-indicator {
            %%MENU_ARROW_RULE%%
            subcontrol-origin: padding;
            subcontrol-position: right center;
            right: 6px;
        }

        /* === PROGRESS BAR === */
        QProgressBar {
            border: 1px solid #dee2e6;
            border-radius: 6px;
            background-color: #f8f9fa;
            text-align: center;
            color: #495057;
            font-weight: 600;
        }
        
        QProgressBar::chunk {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                      stop: 0 #0d6efd, stop: 1 #0b5ed7);
            border-radius: 6px;
        }

        /* === CHECKBOXES === */
        QCheckBox {
            spacing: 8px;
            color: #495057;
        }
        
        /* 15 px (au lieu de 18 px, bordure 2 px) : proportionné aux libellés de
           11 à 13 px, à côté desquels les cases paraissaient énormes. */
        QCheckBox::indicator {
            width: 15px;
            height: 15px;
            border: 1px solid #adb5bd;
            border-radius: 3px;
            background-color: white;
        }
        
        /* Cases intégrées aux arbres, tableaux et listes (validation des
           suggestions, nettoyage des doublons…) : même apparence que les
           QCheckBox — sinon cases sans cadre, seule la coche était visible. */
        QTreeView::indicator, QTableView::indicator, QListView::indicator {
            width: 15px;
            height: 15px;
            border: 1px solid #adb5bd;
            border-radius: 3px;
            background-color: white;
        }

        QTreeView::indicator:checked, QTableView::indicator:checked, QListView::indicator:checked {
            background-color: #0d6efd;
            border-color: #0d6efd;
            %%CHECK_RULE%%
        }

        QCheckBox::indicator:hover {
            border-color: #adb5bd;
        }
        
        QCheckBox::indicator:checked {
            background-color: #0d6efd;
            border-color: #0d6efd;
            %%CHECK_RULE%%
        }

        /* === DIALOG BOXES === */
        QDialog {
            background-color: #ffffff;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }

        /* === SPLITTER === */
        /* Poignées de redimensionnement : UNE règle pour toute l'application.
           8 px transparents = l'espace entre deux blocs (les blocs n'ont pas de
           marge côté poignée) ; teinte au survol pour rester repérable. Avant :
           1, 2 ou 8 px selon la fenêtre, avec des marges de 0 à 22 px — les
           poignées collaient au contenu par endroits. */
        QSplitter::handle {
            background-color: transparent;
        }

        QSplitter::handle:vertical {
            height: 8px;
        }

        QSplitter::handle:horizontal {
            width: 8px;
        }

        QSplitter::handle:hover {
            background-color: #dee2e6;
        }

        /* === GROUPBOX === */
        QGroupBox {
            font-weight: 600;
            color: #495057;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            margin-top: 1ex;
            padding-top: 16px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background-color: #f8f9fa;
        }

        /* === MENU BAR === */
        QMenuBar {
            background-color: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
            color: #495057;
        }
        
        QMenuBar::item {
            padding: 8px 16px;
            background: transparent;
        }
        
        QMenuBar::item:selected {
            background-color: #e9ecef;
            color: #212529;
        }

        /* === CONTEXT MENU === */
        QMenu {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 4px 0;
            color: #495057;
        }
        
        QMenu::item {
            padding: 8px 16px;
            background: transparent;
        }
        
        QMenu::item:selected {
            background-color: #e7f1ff;
            color: #0d6efd;
        }
        
        QMenu::separator {
            height: 1px;
            background-color: #e9ecef;
            margin: 4px 0;
        }

        /* === NOTIFICATIONS INLINE === */
        QLabel[class="alert-success"] {
            background-color: #d1e7dd;
            color: #0a3622;
            border: 1px solid #b3d3c4;
            border-radius: 6px;
            padding: 8px 12px;
        }
        
        QLabel[class="alert-warning"] {
            background-color: #fff3cd;
            color: #664d03;
            border: 1px solid #f1c40f;
            border-radius: 6px;
            padding: 8px 12px;
        }
        
        QLabel[class="alert-danger"] {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f1c2c7;
            border-radius: 6px;
            padding: 8px 12px;
        }

        /* === TOOLTIPS === */
        /* Infobulles claires et compactes.
           Fond CLAIR obligatoire : une feuille de style sans sélecteur posée sur
           un widget (ex. setStyleSheet("color: #495057; …") sur un QLabel) colore
           aussi le texte de SON infobulle — des dizaines de cas dans l'appli. Sur
           fond sombre ce texte devenait illisible ; toutes ces couleurs sont
           pensées pour du blanc.
           Piège mesuré : sur une infobulle, Qt convertit `padding` en UNE marge
           identique sur les 4 côtés (2 px + la plus grande valeur) — « 3px 7px »
           donnait 9 px partout. D'où une valeur unique et petite : 41 px de haut
           pour 2 lignes, contre ~59 px avant. */
        QToolTip {
            background-color: #ffffff;
            color: #212529;
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 2px;
            font-size: 11px;
            font-family: -apple-system, 'SF Pro Display', system-ui, 'Helvetica Neue', sans-serif;
        }

        /* === ANIMATIONS SUBTILES === */
        /* Transitions not supported in PyQt5 */

        /* Transitions not supported in PyQt5 - removed */
        """
        menu_arrow_rule = (
            f"image: url({arrow_path}); width: 10px; height: 10px;"
            if arrow_path else
            "width: 8px; height: 8px;"
        )
        # Coche des cases : l'ancienne image `data:image/svg+xml` n'était pas chargée
        # par Qt → case cochée = carré bleu plein, sans coche. PNG qtawesome à la place.
        check_path = _generate_check_mark()
        check_rule = f"image: url({check_path});" if check_path else ""
        def spin_rule(sens):
            path = _generate_spin_arrow(sens)
            return f"image: url({path}); width: 8px; height: 8px;" if path else "width: 8px; height: 8px;"
        return (style.replace('%%ARROW_RULE%%', arrow_rule)
                     .replace('%%MENU_ARROW_RULE%%', menu_arrow_rule)
                     .replace('%%SPIN_UP_RULE%%', spin_rule('up'))
                     .replace('%%SPIN_DOWN_RULE%%', spin_rule('down'))
                     .replace('%%CHECK_RULE%%', check_rule))