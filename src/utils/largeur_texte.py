"""
Largeur affichée d'un texte dans les résultats Google (police Arial)

Google coupe le title et la description selon leur largeur en pixels, pas selon
leur nombre de caractères : « W » est trois fois plus large que « i ». Les
limites de l'affichage ordinateur sont d'environ 580 px pour le title (Arial
20 px) et 920 px pour la description (Arial 14 px).

La table donne l'avance de chaque caractère en unités de la police (2 048 par
cadratin), relevée une fois sur Arial.ttf. Arial n'applique pas de crénage à ces
paires : la somme des caractères donne la largeur de la phrase (569,3 px contre
569,0 px mesurés par le moteur de rendu sur un title réel). L'arrondi au pixel de
chaque avance reproduit exactement le rendu hinté (209 caractères sur 209, à 14 et
20 px). Un caractère absent de la table compte pour un « n ».
"""

UNITES_PAR_CADRATIN = 2048

# Tailles de police de l'affichage Google sur ordinateur
TAILLE_TITLE_PX = 20
TAILLE_DESCRIPTION_PX = 14

_LARGEURS = {
    ' ': 569, '!': 569, '"': 727, '#': 1139, '$': 1139, '%': 1821, '&': 1366, "'": 391,
    '(': 682, ')': 682, '*': 797, '+': 1196, ',': 569, '-': 682, '.': 569, '/': 569, '0': 1139,
    '1': 1139, '2': 1139, '3': 1139, '4': 1139, '5': 1139, '6': 1139, '7': 1139, '8': 1139,
    '9': 1139, ':': 569, ';': 569, '<': 1196, '=': 1196, '>': 1196, '?': 1139, '@': 2079,
    'A': 1366, 'B': 1366, 'C': 1479, 'D': 1479, 'E': 1366, 'F': 1251, 'G': 1593, 'H': 1479,
    'I': 569, 'J': 1024, 'K': 1366, 'L': 1139, 'M': 1706, 'N': 1479, 'O': 1593, 'P': 1366,
    'Q': 1593, 'R': 1479, 'S': 1366, 'T': 1251, 'U': 1479, 'V': 1366, 'W': 1933, 'X': 1366,
    'Y': 1366, 'Z': 1251, '[': 569, '\\': 569, ']': 569, '^': 961, '_': 1139, '`': 682,
    'a': 1139, 'b': 1139, 'c': 1024, 'd': 1139, 'e': 1139, 'f': 569, 'g': 1139, 'h': 1139,
    'i': 455, 'j': 455, 'k': 1024, 'l': 455, 'm': 1706, 'n': 1139, 'o': 1139, 'p': 1139,
    'q': 1139, 'r': 682, 's': 1024, 't': 569, 'u': 1139, 'v': 1024, 'w': 1479, 'x': 1024,
    'y': 1024, 'z': 1024, '{': 684, '|': 532, '}': 684, '~': 1196, '\xa0': 569, '¡': 682,
    '¢': 1139, '£': 1139, '¤': 1139, '¥': 1139, '¦': 532, '§': 1139, '¨': 682, '©': 1509,
    'ª': 758, '«': 1139, '¬': 1196, '\xad': 682, '®': 1509, '¯': 1131, '°': 819, '±': 1124,
    '²': 682, '³': 682, '´': 682, 'µ': 1180, '¶': 1100, '·': 682, '¸': 682, '¹': 682, 'º': 748,
    '»': 1139, '¼': 1708, '½': 1708, '¾': 1708, '¿': 1251, 'À': 1366, 'Á': 1366, 'Â': 1366,
    'Ã': 1366, 'Ä': 1366, 'Å': 1366, 'Æ': 2048, 'Ç': 1479, 'È': 1366, 'É': 1366, 'Ê': 1366,
    'Ë': 1366, 'Ì': 569, 'Í': 569, 'Î': 569, 'Ï': 569, 'Ð': 1479, 'Ñ': 1479, 'Ò': 1593,
    'Ó': 1593, 'Ô': 1593, 'Õ': 1593, 'Ö': 1593, '×': 1196, 'Ø': 1593, 'Ù': 1479, 'Ú': 1479,
    'Û': 1479, 'Ü': 1479, 'Ý': 1366, 'Þ': 1366, 'ß': 1251, 'à': 1139, 'á': 1139, 'â': 1139,
    'ã': 1139, 'ä': 1139, 'å': 1139, 'æ': 1821, 'ç': 1024, 'è': 1139, 'é': 1139, 'ê': 1139,
    'ë': 1139, 'ì': 569, 'í': 569, 'î': 569, 'ï': 569, 'ð': 1139, 'ñ': 1139, 'ò': 1139,
    'ó': 1139, 'ô': 1139, 'õ': 1139, 'ö': 1139, '÷': 1124, 'ø': 1251, 'ù': 1139, 'ú': 1139,
    'û': 1139, 'ü': 1139, 'ý': 1024, 'þ': 1139, 'ÿ': 1024, '—': 2048, '–': 1139, '’': 455,
    '‘': 455, '“': 682, '”': 682, '…': 2048, 'œ': 1933, 'Œ': 2048, '€': 1139, '•': 717,
    'Ÿ': 1366, 'Ł': 1139, 'ł': 455, 'Š': 1366, 'š': 1024, 'Ž': 1251, 'ž': 1024,
}
_LARGEUR_PAR_DEFAUT = _LARGEURS['n']


def largeur_px(texte: str, taille_police: float) -> float:
    """
    Largeur en pixels de `texte` affiché en Arial à `taille_police` px, dans le
    plus large des deux rendus possibles :
    - positions fractionnaires (navigateurs récents) : somme exacte des avances ;
    - avances arrondies au pixel entier (rendu « hinté » de certains systèmes) :
      à 14 px, chaque caractère gagne jusqu'à un demi-pixel, soit ~2 % sur une
      description (918 px contre 898,5 px sur une description réelle).
    Retenir le plus large garantit qu'aucun des deux rendus ne coupe le texte.
    """
    avances = [_LARGEURS.get(c, _LARGEUR_PAR_DEFAUT) * taille_police / UNITES_PAR_CADRATIN
               for c in texte]
    return max(sum(avances), sum(round(a) for a in avances))
