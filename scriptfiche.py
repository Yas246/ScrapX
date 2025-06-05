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

    @staticmethod
    def _escape_yaml_string(text_input):
        if not isinstance(text_input, str):
            return text_input # Return non-strings as is
        return text_input.replace("'", "''")

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
        # Image par défaut si aucune image n'est trouvée
        default_image = "https://images.unsplash.com/photo-1611224923853-80b023f02d71?ixlib=rb-4.0.3&auto=format&fit=crop&w=2070&q=80"
        
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
        
        # Si aucune image n'est trouvée, retourner l'image par défaut
        return default_image

    def generate_product_sheet(self, article_data):
        """Génère une fiche produit à partir d'UN SEUL article"""
        try:
            print(f"🤖 Génération de la fiche produit avec Gemini pour: {article_data['url']}")
            
            prompt = self._create_gemini_prompt(article_data)
            
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                raise Exception("Réponse vide de l'API Gemini")
            
            product_data = self._parse_gemini_response(response.text)
            
            if product_data:
                # Ajouter l'URL de l'article original à product_data pour le canonical link
                product_data['original_article_url'] = article_data.get('url', '')
            
            markdown_content = self._generate_markdown(product_data) # product_data peut être None
            
            return markdown_content
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération avec Gemini: {e}")
            return None

    def _create_gemini_prompt(self, article_data):
        """Crée le prompt pour UN SEUL article"""
        
        prompt = f"""
Tu es un expert en rédaction de fiches produits techniques. À partir de l'article suivant, tu dois extraire les informations d'un produit et créer une fiche produit EXACTEMENT dans ce format JSON (respecte scrupuleusement la structure et l'ordre des champs) :

{{
    "name": "Nom complet du produit",
    "brand": "Marque du produit",
    "model": "Modèle exact du produit",
    "image": "{article_data.get('image_url', '')}",
    "amazonASIN": "ASIN_PLACEHOLDER",
    "publishDate": "YYYY-MM-DD",
    "updateDate": "YYYY-MM-DD",
    "draft": false,
    "title": "Titre accrocheur pour le test/avis",
    "hookIntro": "Introduction accrocheuse",
    "keyBenefits": [
        "Bénéfice 1 : Description",
        "Bénéfice 2 : Description"
    ],
    "keyFeatures": [
        "Caractéristique 1",
        "Caractéristique 2"
    ],
    "detailedSpecs": "Description technique détaillée",
    "socialProof": "Exemple de preuve sociale (ex: Très populaire auprès des joueurs)",
    "warrantyInfo": "Information sur la garantie (ex: couvert par une garantie constructeur de 2 ans)",
    "ctaText": "Texte pour le bouton d'appel à l'action",
    "affiliateLink": "https://www.amazon.fr/dp/ASIN_PLACEHOLDER?tag=votretag-21",
    "category": "CHOISIR_UNE_CATEGORIE_PARMI_LA_LISTE_AUTORISEE",
    "tags": ["tag1", "tag2", "tag3"]
}}

ARTICLE À ANALYSER:
URL: {article_data['url']}
Titre: {article_data['title']}
Contenu: {article_data['content'][:4000]}...

INSTRUCTIONS IMPORTANTES:
1.  Extrait UNIQUEMENT les informations du produit principal mentionné dans cet article.
2.  `name`: Nom complet et détaillé du produit.
3.  `amazonASIN`: Si un ASIN Amazon est clairement identifiable dans l'article pour le produit principal, utilise-le. Sinon, conserve "ASIN_PLACEHOLDER".
4.  `publishDate` et `updateDate`: Doivent être au format `YYYY-MM-DD`. Tu peux utiliser la date actuelle si non spécifiée.
5.  `draft`: Toujours `false`.
6.  `title`: Titre engageant et SEO-friendly pour la fiche produit, différent du nom du produit.
7.  `hookIntro`: Introduction concise (1-2 phrases) qui capte l'attention.
8.  `keyBenefits`: Liste d'au moins 2 bénéfices clés au format "Titre du Bénéfice : Description".
9.  `keyFeatures`: Liste d'au moins 2 caractéristiques techniques importantes.
10. `detailedSpecs`: Description technique détaillée.
11. `socialProof`: Fournis un exemple de preuve sociale (ex: "Très populaire auprès des joueurs", "Recommandé par les experts", "Noté 4.5/5 étoiles par plus de 1000 utilisateurs"). Si non disponible, indique "Non spécifié".
12. `warrantyInfo`: Fournis des informations sur la garantie (ex: "Couvert par une garantie constructeur de 2 ans", "Garantie limitée de 1 an"). Si non disponible, indique "Non spécifié".
13. `ctaText`: Texte pour le bouton d'appel à l'action (ex: "Voir le Prix sur Amazon", "Comparer les Offres").
14. `category`: DOIT être l'une des suivantes : "Moniteur", "Console", "PC", "Manette", "Jeux Vidéo". Ne pas inventer d'autres catégories.
15. `tags`: Liste d'au moins 3 tags pertinents incluant marque, modèle et mots-clés.
16. Ta réponse ne doit contenir QUE l'objet JSON. N'ajoute aucun commentaire, explication, ou texte conversationnel avant ou après l'objet JSON.
17. Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire avant ou après.
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

        # Fallback pour les dates si non fournies par l'IA ou si le format est incorrect
        default_date_str = datetime.now().strftime('%Y-%m-%d')
        publish_date_str = product_data.get("publishDate", default_date_str)
        update_date_str = product_data.get("updateDate", default_date_str)
        try:
            datetime.strptime(publish_date_str, '%Y-%m-%d')
        except ValueError:
            publish_date_str = default_date_str
        try:
            datetime.strptime(update_date_str, '%Y-%m-%d')
        except ValueError:
            update_date_str = default_date_str


        image_url = product_data.get("image")
        if not image_url: # Assurer un placeholder si vide
            image_url = "https://via.placeholder.com/600x400.png"
        
        # Construction du frontmatter YAML
        # L'ordre des champs est important ici.
        frontmatter_lines = [
            f"name: '{ProductScraper._escape_yaml_string(product_data.get('name', ''))}'",
            f"brand: '{ProductScraper._escape_yaml_string(product_data.get('brand', ''))}'",
            f"model: '{ProductScraper._escape_yaml_string(product_data.get('model', ''))}'",
            f"image: '{ProductScraper._escape_yaml_string(image_url)}'",
            f"amazonASIN: '{ProductScraper._escape_yaml_string(product_data.get('amazonASIN', 'ASIN_PLACEHOLDER'))}'",
            f"publishDate: {publish_date_str}", 
            f"updateDate: {update_date_str}",   
            f"draft: {str(product_data.get('draft', False)).lower()}", 
            f"title: '{ProductScraper._escape_yaml_string(product_data.get('title', ''))}'",
            f"hookIntro: '{ProductScraper._escape_yaml_string(product_data.get('hookIntro', ''))}'",
        ]

        frontmatter_lines.append("keyBenefits:")
        for benefit in product_data.get("keyBenefits", []):
            frontmatter_lines.append(f"  - '{ProductScraper._escape_yaml_string(benefit)}'")

        frontmatter_lines.append("keyFeatures:")
        for feature in product_data.get("keyFeatures", []):
            frontmatter_lines.append(f"  - '{ProductScraper._escape_yaml_string(feature)}'")
        
        frontmatter_lines.extend([
            f"detailedSpecs: '{ProductScraper._escape_yaml_string(product_data.get('detailedSpecs', ''))}'",
            f"ctaText: '{ProductScraper._escape_yaml_string(product_data.get('ctaText', ''))}'",
            f"affiliateLink: '{ProductScraper._escape_yaml_string(product_data.get('affiliateLink', ''))}'",
            f"category: '{ProductScraper._escape_yaml_string(product_data.get('category', ''))}'",
        ])

        frontmatter_lines.append("tags:")
        for tag in product_data.get("tags", []):
            frontmatter_lines.append(f"  - '{ProductScraper._escape_yaml_string(tag)}'")

        markdown_template = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n"

        # Corps MDX
        # Utilisation de product_data.get() pour la robustesse, et _escape_yaml_string pour les chaînes insérées.
        # Note: l'utilisation de product_data.get("image", "") directement dans le texte est inhabituelle
        # et pourrait nécessiter un post-traitement ou une variable spécifique si l'URL doit être affichée.
        # Ici, on suit la demande de mettre l'URL de l'image directement.
        
        # Construction des éléments JSX pour keyFeatures
        key_features_list_items = ""
        if product_data.get("keyFeatures"):
            for feature in product_data.get("keyFeatures"):
                # S'assurer que le contenu de la feature est bien échappé pour JSX si besoin,
                # mais ici on suppose qu'il s'agit de texte simple.
                # Pour être sûr, on pourrait échapper les caractères spéciaux JSX comme { } < >
                # mais pour des strings simples, ce n'est souvent pas nécessaire.
                # L'échappement YAML a déjà géré les apostrophes.
                clean_feature = str(feature).replace('{', '{{').replace('}', '}}') # Basic JSX escaping for text nodes
                key_features_list_items += f"      <li key={{{repr(clean_feature[:20])}}}>{clean_feature}</li>\n" # key simple pour l'exemple

        key_features_mdx = f"""{{frontmatter.keyFeatures && (
  <ul>
    {{frontmatter.keyFeatures.map((feature, index) => (
      <li key={{index}}>
        {{feature}}
      </li>
    ))}}
  </ul>
)}}"""
        # Correction: Le template JSX doit utiliser les variables du frontmatter, pas celles construites en Python.
        # Donc, la construction de key_features_list_items n'est pas utilisée directement ici si on suit le modèle JSX.
        # Le template JSX pour keyFeatures est correct en utilisant frontmatter.keyFeatures.

        social_proof_text = ProductScraper._escape_yaml_string(product_data.get("socialProof", "Information non disponible"))
        warranty_info_text = ProductScraper._escape_yaml_string(product_data.get("warrantyInfo", "Information non disponible"))


        markdown_template += f"## Pourquoi choisir le {product_data.get('brand', '')} {product_data.get('model', '')} ?\n\n"
        # Attention à product_data.get('image', '') directement dans le texte.
        # Si c'est une URL, elle sera juste imprimée. Si le MDX doit la traiter comme une image, il faudrait un ![]().
        # La demande est de mettre `product_data.get("image", "")` donc on le fait.
        hook_intro_escaped_for_body = ProductScraper._escape_yaml_string(product_data.get("hookIntro", ""))
        markdown_template += f"Si vous cherchez à améliorer votre expérience de jeu sans vous ruiner, le **{product_data.get('brand', '')} {product_data.get('model', '')}** mérite toute votre attention. Comme mentionné dans notre introduction : **{hook_intro_escaped_for_body}**\n\n"
        
        markdown_template += "### Atouts Majeurs pour une Expérience Inégalée\n\n"
        # keyBenefits rendering (inchangé, utilise le JSX fourni précédemment)
        markdown_template += """{frontmatter.keyBenefits && (
  <ul>
    {frontmatter.keyBenefits.map((benefit, index) => (
      <li key={index}>
        <strong>{benefit.split(':')[0].trim()} :</strong> {benefit.split(':')[1].trim()}
      </li>
    ))}
  </ul>
)}

"""
        markdown_template += f"### Caractéristiques Techniques qui Comptent\n\n{key_features_mdx}\n\n"
        
        detailed_specs_escaped_for_body = ProductScraper._escape_yaml_string(product_data.get('detailedSpecs', ''))
        markdown_template += f"**{detailed_specs_escaped_for_body}**\n\n"

        markdown_template += f"### Ce qu'il Faut Savoir Avant d'Acheter\n\nCe modèle est **{social_proof_text}**. De plus, la tranquillité d'esprit est souvent assurée car il **{warranty_info_text}** (vérifiez les conditions spécifiques lors de l'achat).\n\n"

        markdown_template += "### Verdict et Où l'Acheter\n\n"
        markdown_template += f"Le {product_data.get('brand', '')} {product_data.get('model', '')} est plus qu'un simple produit, c'est une pièce maîtresse pour tout setup sérieux. Il allie design, performance et technologies de pointe pour satisfaire les utilisateurs les plus exigeants.\n\n"
        markdown_template += "{/* Le bouton CTA principal - Stylez-le via CSS */}\n"
        markdown_template += "<a href={frontmatter.affiliateLink} target=\"_blank\" rel=\"sponsored noopener noreferrer\" class=\"cta-button\">\n"
        markdown_template += "  {frontmatter.ctaText}\n"
        markdown_template += "</a>\n\n"
        markdown_template += "*En tant que Partenaire Amazon, je réalise un bénéfice sur les achats remplissant les conditions requises.*\n"

        return markdown_template

    def process_single_url(self, url):
        """Traite UNE SEULE URL et génère UNE fiche produit."""
        print(f"🚀 Traitement de l'URL : {url}")
        
        # Scraper l'article
        article_data = self.scrape_article(url) # Contient 'url', 'title', 'content', 'image_url', 'raw_html'
        
        if article_data is None:
            print(f"❌ Impossible de récupérer l'article de {url}")
            return None
        
        print(f"✅ Article récupéré avec succès : {article_data['title']}")
        
        # Générer la fiche produit
        # On doit s'assurer que article_data['url'] est passé pour le canonical link
        product_sheet = self.generate_product_sheet(article_data) # article_data est passé ici
        
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
                time.sleep(5)
        
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
                    filename = f"{brand_slug}-{model_slug}.mdx"
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