"""
Webservice PrestaShop du site 1001pieces.com : lecture (anti-doublon,
catégories, fabricants, caractéristiques) et création de fiches.

Adresse et clé dans `data/prestashop.env` (PS_URL=…, PS_KEY=…, non suivi par
git) : la dev d'abord, la production en changeant ces deux lignes. Droits de la
clé : lecture des référentiels, ajout et modification des produits et des
images, jamais de suppression.
"""
