import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import yaml
from datetime import datetime
import re
import argparse
import sys
from urllib.parse import urlparse, urljoin
import json
import time
import os
from dotenv import load_dotenv

class ProductScraper:
    def __init__(self):
        
        load_dotenv()
        
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not self.gemini_api_key:
            raise ValueError("❌ GEMINI_API_KEY non trouvée dans le fichier .env")
        
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Headers pour les requêtes HTTP
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def load_urls_from_file(self, filename='urlfiche.txt'):
        
        try:
            if not os.path.exists(filename):
                print(f"❌ Fichier {filename} non trouvé.")
                return []
            
            with open(filename, 'r', encoding='utf-8') as f:
                urls = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Ignorer les lignes vides et les commentaires
                    if not line or line.startswith('#'):
                        continue
                    
                    
                    try:
                        result = urlparse(line)
                        if all([result.scheme, result.netloc]):
                            urls.append(line)
                            print(f"✅ URL {line_num}: {line}")
                        else:
                            print(f"⚠️  URL {line_num} invalide ignorée : {line}")
                    except Exception:
                        print(f"⚠️  URL {line_num} invalide ignorée : {line}")
                
                return urls
                
        except Exception as e:
            print(f"❌ Erreur lors de la lecture du fichier {filename}: {e}")
            return []

    def scrape_article(self, url):
        
        try:
            print(f"📥 Scraping de l'article : {url}")
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraction du contenu principal
            content = self._extract_main_content(soup)
            title = self._extract_title(soup)
            image_url = self._extract_product_image(soup)
            
            return {
                'url': url,
                'title': title,
                'content': content,
                'image_url': image_url,
                'raw_html': str(soup)
            }
            
        except requests.RequestException as e:
            print(f"❌ Erreur lors du scraping de {url}: {e}")
            return None
        except Exception as e:
            print(f"❌ Erreur inattendue pour {url}: {e}")
            return None

    def _extract_title(self, soup):
        
        selectors = ['h1', 'title', '.article-title', '.post-title', '#title']
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element and element.get_text().strip():
                return element.get_text().strip()
        
        return "Titre non trouvé"

    def _extract_main_content(self, soup):
        
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'advertisement']):
            element.decompose()
        
        content_selectors = [
            'article', '.article-content', '.post-content', '.entry-content',
            '.content', 'main', '#content', '.article-body', '.post-body'
        ]
        
        for selector in content_selectors:
            content_element = soup.select_one(selector)
            if content_element:
                return content_element.get_text(separator=' ', strip=True)
        
        body = soup.find('body')
        if body:
            return body.get_text(separator=' ', strip=True)
        
        return soup.get_text(separator=' ', strip=True)

    def _extract_product_image(self, soup):
        """Extrait l'URL de l'image principale du produit."""
        # Sélecteurs spécifiques aux images de produits
        image_selectors = [
            # Sélecteurs Open Graph et Twitter
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            # Sélecteurs spécifiques aux sites e-commerce
            '#landingImage',  # Amazon
            '#main-image',    # Commun
            '.product-image-main img',
            '.product-featured-image',
            '.gallery-image--default',
            '[data-main-image]',
            # Sélecteurs génériques pour images de produits
            '.product-image img',
            '.primary-image',
            '.main-product-image',
            # Fallback sur première image pertinente
            'img[itemprop="image"]',
            '.product img:first-of-type'
        ]
        
        for selector in image_selectors:
            element = soup.select_one(selector)
            if element:
                # Extraire l'URL selon le type d'élément
                if element.name == 'meta':
                    image_url = element.get('content')
                else:
                    # Chercher d'abord data-src pour les images lazy-loaded
                    image_url = element.get('data-src') or element.get('src')
                
                if image_url:
                    # Nettoyer l'URL
                    image_url = image_url.split('?')[0]  # Retirer les paramètres
                    # S'assurer que l'URL est absolue
                    if not image_url.startswith(('http://', 'https://')):
                        base_url = soup.find('base', href=True)
                        if base_url:
                            image_url = urljoin(base_url['href'], image_url)
                    return image_url
        
        return None

    def generate_product_sheet(self, article_data):
        """Génère une fiche produit à partir d'UN SEUL article"""
        try:
            print(f"🤖 Génération de la fiche produit avec Gemini pour: {article_data['url']}")
            
            prompt = self._create_gemini_prompt(article_data)
            
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                raise Exception("Réponse vide de l'API Gemini")
            
            product_data = self._parse_gemini_response(response.text)
            markdown_content = self._generate_markdown(product_data)
            
            return markdown_content
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération avec Gemini: {e}")
            return None

    def _create_gemini_prompt(self, article_data):
        """Crée le prompt pour UN SEUL article"""
        
        prompt = f"""
Tu es un expert en rédaction de fiches produits techniques. À partir de l'article suivant, tu dois extraire les informations d'un produit et créer une fiche produit EXACTEMENT dans ce format JSON (respecte scrupuleusement la structure) :

{{
    "name": "Nom complet du produit avec toutes ses caractéristiques",
    "brand": "Marque du produit",
    "model": "Modèle exact du produit",
    "image": "{article_data.get('image_url', '')}",
    "amazonASIN": "ASIN_PLACEHOLDER",
    "publishDate": "{datetime.now().strftime('%Y-%m-%d')}",
    "updateDate": "{datetime.now().strftime('%Y-%m-%d')}",
    "draft": false,
    "title": "Titre accrocheur pour le test/avis du produit",
    "hookIntro": "Introduction accrocheuse décrivant les points forts du produit",
    "keyBenefits": [
        "Bénéfice 1 : Description détaillée du premier avantage",
        "Bénéfice 2 : Description détaillée du deuxième avantage",
        "Bénéfice 3 : Description détaillée du troisième avantage",
        "Bénéfice 4 : Description détaillée du quatrième avantage",
        "Bénéfice 5 : Description détaillée du cinquième avantage"
    ],
    "keyFeatures": [
        "Caractéristique technique 1",
        "Caractéristique technique 2", 
        "Caractéristique technique 3",
        "Caractéristique technique 4",
        "Caractéristique technique 5",
        "Caractéristique technique 6",
        "Caractéristique technique 7",
        "Caractéristique technique 8"
    ],
    "detailedSpecs": "Description détaillée et technique du produit mettant en avant ses spécifications et performances",
    "ctaText": "Voir les Offres pour le [Nom du Produit]",
    "affiliateLink": "https://www.amazon.fr/dp/ASIN_PLACEHOLDER?tag=votretag-21",
    "category": "Catégorie appropriée du produit",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"]
}}

ARTICLE À ANALYSER:
URL: {article_data['url']}
Titre: {article_data['title']}
Contenu: {article_data['content'][:4000]}...

INSTRUCTIONS IMPORTANTES:
1. Extrait UNIQUEMENT les informations du produit principal mentionné dans cet article
2. Assure-toi que le nom du produit soit complet et détaillé
3. Les keyBenefits doivent suivre le format "Titre : Description"
4. Les keyFeatures doivent être des caractéristiques techniques précises
5. La catégorie doit être pertinente (ex: "Moniteurs Gaming", "Smartphones", "Casques Audio", etc.)
6. Les tags doivent inclure la marque, le modèle et des mots-clés pertinents
7. Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire
"""
        
        return prompt

    def _parse_gemini_response(self, response_text):
        try:
            response_text = response_text.strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise Exception("Aucun JSON trouvé dans la réponse")
            
            json_text = response_text[json_start:json_end]
            product_data = json.loads(json_text)
            
            return product_data
            
        except json.JSONDecodeError as e:
            print(f"❌ Erreur de parsing JSON: {e}")
            print(f"Réponse brute: {response_text[:500]}...")
            return None
        except Exception as e:
            print(f"❌ Erreur lors du parsing: {e}")
            return None

    def _generate_markdown(self, product_data):
        if not product_data:
            return None
        
        # Template markdown exact selon le format spécifié
        markdown_template = f"""---
# --- Informations de Base sur le Produit ---
name: '{product_data.get("name", "")}'
brand: '{product_data.get("brand", "")}'
model: '{product_data.get("model", "")}'
image: '{product_data.get("image", "https://via.placeholder.com/600x400")}' # Placeholder image
amazonASIN: '{product_data.get("amazonASIN", "PRODUCT_ASIN_PLACEHOLDER")}' # Placeholder ASIN
publishDate: {product_data.get("publishDate", datetime.now().strftime('%Y-%m-%d'))}
updateDate: {product_data.get("updateDate", datetime.now().strftime('%Y-%m-%d'))}
draft: {str(product_data.get("draft", False)).lower()}

# --- Étape 2 : Accroche ---
title: '{product_data.get("title", "")}'
hookIntro: '{product_data.get("hookIntro", "")}'

# --- Étape 3 : Bénéfices Clés ---
keyBenefits:"""
        
        # Ajouter les bénéfices
        for benefit in product_data.get("keyBenefits", []):
            markdown_template += f"\n  - '{benefit}'"
        
        markdown_template += f"""

# --- Étape 4 : Caractéristiques Pertinentes ---
keyFeatures:"""
        
        # Ajouter les caractéristiques
        for feature in product_data.get("keyFeatures", []):
            markdown_template += f"\n  - '{feature}'"
        
        markdown_template += f"""
detailedSpecs: '{product_data.get("detailedSpecs", "")}'

# --- Étape 6 : Appel à l'Action ---
ctaText: '{product_data.get("ctaText", "")}'
affiliateLink: '{product_data.get("affiliateLink", "")}' # Placeholder link

# --- Étape 7 : Optimisation & Catégorisation ---
category: '{product_data.get("category", "")}'
tags: {product_data.get("tags", [])}

---

## Le {product_data.get("brand", "")} {product_data.get("model", "")} : Immersion et Performance au Rendez-vous

Plongez au cœur de l'action avec le **{{frontmatter.name}}**. Ce produit est une invitation à redécouvrir vos expériences avec une qualité et une performance époustouflantes. Comme nous l'avons souligné : **{{frontmatter.hookIntro}}**

### Atouts Majeurs pour une Expérience Inégalée

Le {product_data.get("brand", "")} {product_data.get("model", "")} est conçu pour la performance :

{{frontmatter.keyBenefits.map((benefit) => (
  - **${{benefit.split(':')[0].trim()}} :** ${{benefit.split(':')[1].trim()}}
))}}

### Spécifications Techniques Détaillées

Les caractéristiques techniques de ce produit parlent d'elles-mêmes :

{{frontmatter.keyFeatures.map((feature) => (
  - ${{feature}}
))}}

**{{frontmatter.detailedSpecs}}**

### Prêt à Transformer Votre Expérience ?

Le {product_data.get("brand", "")} {product_data.get("model", "")} est plus qu'un simple produit, c'est une pièce maîtresse pour tout setup sérieux. Il allie design, performance et technologies de pointe pour satisfaire les utilisateurs les plus exigeants.

{{/* Le bouton CTA principal - Stylez-le via CSS */}}
<a href={{frontmatter.affiliateLink}} target="_blank" rel="sponsored noopener noreferrer" class="cta-button">
  {{frontmatter.ctaText}}
</a>

*En tant que Partenaire Amazon, je réalise un bénéfice sur les achats remplissant les conditions requises.*"""

        return markdown_template

    def process_single_url(self, url):
        """Traite UNE SEULE URL et génère UNE fiche produit."""
        print(f"🚀 Traitement de l'URL : {url}")
        
        # Scraper l'article
        article_data = self.scrape_article(url)
        
        if article_data is None:
            print(f"❌ Impossible de récupérer l'article de {url}")
            return None
        
        print(f"✅ Article récupéré avec succès : {article_data['title']}")
        
        # Générer la fiche produit
        product_sheet = self.generate_product_sheet(article_data)
        
        return product_sheet

    def process_all_urls(self, urls):
        """Traite TOUTES les URLs et génère UNE fiche par URL."""
        print(f"🚀 Démarrage du traitement de {len(urls)} URL(s)...")
        
        results = []
        
        for i, url in enumerate(urls, 1):
            print(f"\n--- Traitement {i}/{len(urls)} ---")
            
            # Traiter chaque URL individuellement
            product_sheet = self.process_single_url(url)
            
            if product_sheet:
                # Laisser save_to_file générer le nom basé sur brand et model
                filepath = self.save_to_file(product_sheet)
                
                if filepath:
                    results.append({
                        'url': url,
                        'filename': filepath,
                        'success': True
                    })
                else:
                    results.append({
                        'url': url,
                        'filename': None,
                        'success': False
                    })
            else:
                print(f"❌ Impossible de générer la fiche produit pour {url}")
                results.append({
                    'url': url,
                    'filename': None,
                    'success': False
                })
            
            # Pause entre les URLs pour éviter de surcharger les serveurs
            if i < len(urls):
                print("⏳ Pause de 2 secondes avant l'URL suivante...")
                time.sleep(2)
        
        return results

    def _slugify(self, text):
        """Convertit un texte en slug (caractères simples, sans accents, avec tirets)."""
        # Convertir en minuscules
        text = text.lower()
        # Remplacer les caractères accentués
        text = re.sub(r'[àáâãäçèéêëìíîïñòóôõöùúûüýÿ]', 
                     lambda m: 'aaaaaceeeeiiiinooooouuuuyy'['àáâãäçèéêëìíîïñòóôõöùúûüýÿ'.index(m.group())], 
                     text)
        # Remplacer tout ce qui n'est pas alphanumérique par des tirets
        text = re.sub(r'[^a-z0-9]+', '-', text)
        # Supprimer les tirets en début et fin
        text = text.strip('-')
        # Réduire les tirets multiples
        text = re.sub(r'-+', '-', text)
        return text

    def save_to_file(self, content, filename=None):
        """Sauvegarde le contenu dans un fichier."""
        # Créer le dossier de sortie s'il n'existe pas
        output_dir = "./fiche"
        os.makedirs(output_dir, exist_ok=True)
        
        if not filename:
            try:
                # Extraire la marque et le modèle du contenu markdown
                brand_match = re.search(r"brand: '([^']+)'", content)
                model_match = re.search(r"model: '([^']+)'", content)
                
                if brand_match and model_match:
                    brand = brand_match.group(1)
                    model = model_match.group(1)
                    
                    # Slugifier la marque et le modèle
                    brand_slug = self._slugify(brand)
                    model_slug = self._slugify(model)[:40]  # Limiter la longueur du modèle si nécessaire
                    
                    # Créer le nom de fichier
                    filename = f"fiche-{brand_slug}-{model_slug}.mdx"
                else:
                    # Fallback si on ne trouve pas la marque ou le modèle
                    timestamp = datetime.now().strftime("%Y%m%d")
                    filename = f"fiche-{timestamp}.mdx"
            except Exception as e:
                print(f"⚠️ Impossible d'extraire la marque ou le modèle: {e}")
                timestamp = datetime.now().strftime("%Y%m%d")
                filename = f"fiche-{timestamp}.mdx"
        
        # Construire le chemin complet
        filepath = os.path.join(output_dir, os.path.basename(filename))
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Fiche produit sauvegardée : {filepath}")
            return filepath
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde : {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description='Génère des fiches produits à partir d\'articles web')
    parser.add_argument('--urls-file', '-f', default='urlfiche.txt', help='Fichier contenant les URLs (défaut: urlfiche.txt)')
    parser.add_argument('--single-url', '-u', help='Traiter une seule URL directement')
    
    args = parser.parse_args()
    
    # Initialiser le scraper
    try:
        scraper = ProductScraper()
    except ValueError as e:
        print(e)
        sys.exit(1)
    
    # Déterminer les URLs à traiter
    if args.single_url:
        urls = [args.single_url]
        print(f"🎯 Mode URL unique : {args.single_url}")
    else:
        # Charger les URLs depuis le fichier
        urls = scraper.load_urls_from_file(args.urls_file)
        
        if not urls:
            print(f"❌ Aucune URL valide trouvée dans {args.urls_file}")
            print(f"💡 Créez le fichier {args.urls_file} avec une URL par ligne.")
            sys.exit(1)
    
    # Traiter les URLs
    try:
        results = scraper.process_all_urls(urls)
        
        # Afficher le résumé
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        print(f"\n🎉 Traitement terminé !")
        print(f"✅ Fiches générées avec succès : {len(successful)}")
        print(f"❌ Échecs : {len(failed)}")
        
        if successful:
            print(f"\n📄 Fichiers générés :")
            for result in successful:
                print(f"  - {result['filename']}")
        
        if failed:
            print(f"\n⚠️  URLs ayant échoué :")
            for result in failed:
                print(f"  - {result['url']}")
            
    except KeyboardInterrupt:
        print("\n⏹️  Arrêt demandé par l'utilisateur.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erreur inattendue : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()