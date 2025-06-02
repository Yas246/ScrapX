# ScrapX - Générateur de Fiches Produits et Articles de Blog

ScrapX est une suite d'outils Python qui permet de générer automatiquement du contenu à partir d'articles web. Il utilise l'API Gemini pour analyser le contenu et générer des descriptions détaillées et structurées.

## 🎯 Deux scripts, deux usages

### scriptfiche.py - Fiches Produits

- Génère des fiches produits détaillées au format MDX
- Idéal pour les sites e-commerce et les blogs d'affiliation
- Structure optimisée pour les produits (caractéristiques, bénéfices, etc.)
- Intégration avec Amazon (ASIN et liens d'affiliation)

### scriptblog.py - Articles de Blog

- Génère des articles de blog complets au format MD
- Détection intelligente des articles sur un site web
- Trois modes de fonctionnement :
  1. **Mode Site** : Analyse automatique d'un site pour trouver tous les articles
  2. **Mode Liste** : Traitement d'une liste d'URLs d'articles spécifiques
  3. **Mode Unique** : Traitement d'un seul article
- Parfait pour le content marketing et le SEO
- Structure optimisée pour le contenu éditorial
- Plus de liberté dans le format et le style

## 🚀 Fonctionnalités

- Scraping d'articles web pour extraire les informations produits
- Génération de fiches produits structurées au format MDX
- Support du traitement par lot ou d'une URL unique
- Sauvegarde automatique dans un dossier dédié
- Gestion des erreurs et des timeouts
- Respect des bonnes pratiques de scraping (délais entre requêtes)

## 📋 Prérequis

- Python 3.8 ou supérieur
- Un compte Google Cloud Platform avec l'API Gemini activée
- Une clé API Gemini valide

## ⚙️ Installation

1. Clonez le dépôt :

```bash
git clone https://github.com/votre-username/ScrapX.git
cd ScrapX
```

2. Créez un environnement virtuel et activez-le :

```bash
python -m venv venv
# Sur Windows
venv\Scripts\activate
# Sur Unix ou MacOS
source venv/bin/activate
```

3. Installez les dépendances :

```bash
pip install -r requirements.txt
```

4. Créez un fichier `.env` à la racine du projet et ajoutez votre clé API Gemini :

```
GEMINI_API_KEY=votre_clé_api_ici
```

## 🎯 Utilisation

### Génération de Fiches Produits (scriptfiche.py)

#### Mode URL unique

Pour traiter une seule URL :

```bash
python scriptfiche.py --single-url "https://example.com/article-produit"
```

#### Mode fichier d'URLs

1. Créez un fichier `urlfiche.txt` contenant une URL par ligne :

```
https://example.com/article1
https://example.com/article2
# Les lignes commençant par # sont ignorées
```

2. Exécutez le script :

```bash
python scriptfiche.py
# ou spécifiez un fichier d'URLs différent :
python scriptfiche.py --urls-file mon_fichier.txt
```

### Génération d'Articles de Blog (scriptblog.py)

#### Mode Site (Détection Automatique)

```bash
# Analyse complète d'un site web
python scriptblog.py --site "https://example.com"

# Avec limite du nombre d'articles
python scriptblog.py --site "https://example.com" --limit 10

# Avec profondeur de recherche spécifique
python scriptblog.py --site "https://example.com" --depth 3
```

#### Mode Liste d'Articles

1. Créez un fichier `urlblog.txt` avec vos URLs d'articles :

```
https://example.com/article1
https://example.com/article2
# Les lignes commençant par # sont ignorées
```

2. Exécutez le script :

```bash
python scriptblog.py
# ou avec un fichier personnalisé :
python scriptblog.py --urls-file mon_fichier.txt
```

#### Mode Article Unique

```bash
# Traitement d'un article spécifique
python scriptblog.py --single-url "https://example.com/article-specifique"
```

#### Options Avancées

```bash
# Personnalisation du dossier de sortie
python scriptblog.py --site "https://example.com" --output-dir "mon_dossier"

# Exclusion de certains motifs d'URLs
python scriptblog.py --site "https://example.com" --exclude "category|tag"

# Limitation de la vitesse de crawl
python scriptblog.py --site "https://example.com" --delay 5
```

## 📁 Structure des fichiers générés

### Fiches Produits

Les fiches produits sont générées dans le dossier `./fiche` avec la structure suivante :

```
./fiche/
├── fiche_domain_article_1_timestamp.mdx
└── fiche_domain_article_2_timestamp.mdx
```

### Articles de Blog

Les articles de blog sont générés dans le dossier `./blog` avec la structure suivante :

```
./blog/
├── article_domain_1_timestamp.mdx
└── article_domain_2_timestamp.mdx
```

## 📝 Format des fiches produits

Chaque fiche produit générée contient :

- Informations de base (nom, marque, modèle)
- Image du produit (si disponible)
- ASIN Amazon pour l'affiliation
- Dates de publication et mise à jour
- Titre accrocheur et introduction
- Bénéfices clés (5 points)
- Caractéristiques techniques (8 points)
- Description détaillée
- Appel à l'action (CTA)
- Catégorisation et tags

## ⚠️ Limitations

- Respecte les limites de l'API Gemini
- Pause de 2 secondes entre chaque URL pour éviter la surcharge
- Taille maximale du contenu analysé : 4000 caractères par article

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

- Signaler des bugs
- Proposer des améliorations
- Soumettre des pull requests

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 🙏 Remerciements

- Google pour l'API Gemini
- BeautifulSoup4 pour le parsing HTML
