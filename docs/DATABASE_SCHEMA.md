# 📊 Schéma de Base de Données - 1001pieces_autofill

## Structure Optimisée v2.4.0

### 🔧 Tables Principales

#### **appareils** (358,870 enregistrements)
```sql
CREATE TABLE appareils (
    id INTEGER PRIMARY KEY,
    type TEXT,
    manufacturer TEXT,
    ref_modele TEXT,
    commercial_ref TEXT,
    other_ref TEXT,
    category TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### **pieces** (Structure normalisée)
```sql
CREATE TABLE pieces (
    id INTEGER PRIMARY KEY,
    ref_piece TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### **piece_associations** (Table de liaison)
```sql
CREATE TABLE piece_associations (
    id INTEGER PRIMARY KEY,
    piece_id INTEGER NOT NULL,
    appareil_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(piece_id) REFERENCES pieces(id) ON DELETE CASCADE,
    FOREIGN KEY(appareil_id) REFERENCES appareils(id) ON DELETE CASCADE,
    UNIQUE(piece_id, appareil_id)
);
```

#### **categories** (Gestion des catégories)
```sql
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 🚀 Index de Performance

```sql
-- Appareils
CREATE INDEX idx_appareils_type ON appareils(type);
CREATE INDEX idx_appareils_manufacturer ON appareils(manufacturer);
CREATE INDEX idx_appareils_ref_modele ON appareils(ref_modele);
CREATE INDEX idx_appareils_commercial_ref ON appareils(commercial_ref);
CREATE INDEX idx_appareils_other_ref ON appareils(other_ref);
CREATE INDEX idx_appareils_category ON appareils(category);
CREATE INDEX idx_appareils_id_desc ON appareils(id DESC);

-- Pièces
CREATE INDEX idx_pieces_ref ON pieces(ref_piece);
CREATE INDEX idx_piece_associations_piece ON piece_associations(piece_id);
CREATE INDEX idx_piece_associations_appareil ON piece_associations(appareil_id);
```

### 🔄 Avantages de la Nouvelle Structure

1. **Normalisation** : Élimination des doublons de pièces
2. **Intégrité référentielle** : Contraintes FK pour cohérence
3. **Performance** : Index optimisés pour recherches rapides
4. **Flexibilité** : Une pièce peut être associée à plusieurs appareils
5. **Maintenance** : Structure claire et extensible

### 📈 Statistiques Actuelles

- **Appareils** : 358,870 enregistrements
- **Pièces** : 0 (prêt pour import)
- **Associations** : 0 (prêt pour import)
- **Catégories** : À configurer selon besoins

### 🧹 Nettoyage Effectué

- ✅ Suppression table `pieces_old` (obsolète)
- ✅ Restructuration table `pieces` (normalisée)
- ✅ Recréation table `piece_associations` (FK correctes)
- ✅ Index de performance optimisés
- ✅ Contraintes d'intégrité activées

---

**📅 Dernière mise à jour :** 18 juillet 2025  
**🚀 Version :** 2.4.0 - Structure optimisée  
**💾 Taille BDD :** ~94 MB