import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from urllib.parse import urljoin, urlparse
import re
import os
import time
from datetime import datetime
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv

class BlogScraper:
    def __init__(self, gemini_api_key: str):
        
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)
        
        model_names = ['gemini-2.0-flash']
        self.model = None
        
        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                print(f"✅ Modèle Gemini initialisé: {model_name}")
                break
            except Exception as e:
                print(f"❌ Échec du modèle {model_name}: {e}")
                continue
        
        if not self.model:
            raise Exception("Aucun modèle Gemini disponible")
            
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def is_single_article_url(self, url: str) -> bool:

        article_patterns = [
            r'/\d{4}/',  # Année dans l'URL
            r'/\d{4}-\d{2}/',  # Année-mois
            r'/article/',
            r'/post/',
            r'/blog/.+/.+',  # /blog/category/title
            r'-\d+$',  # Se termine par un tiret et des chiffres
            r'/[^/]+$',  # Se termine par un slug sans slash
            r'\d{7}_',  # Pattern Frandroid: 7 chiffres suivi d'underscore
        ]
        
        # Patterns qui indiquent une page d'accueil ou de liste
        homepage_patterns = [
            r'/$',  # Se termine par /
            r'/blog/$',
            r'/articles/$',
            r'/posts/$',
            r'/page/',
            r'/category/',
            r'/tag/',
        ]
        
        for pattern in homepage_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        for pattern in article_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        
        path = urlparse(url).path
        return len(path.strip('/').split('/')) >= 2
    
    def extract_blog_links(self, blog_url: str) -> List[str]:
        
        try:
            response = self.session.get(blog_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            article_links = set()
            base_domain = urlparse(blog_url).netloc
            
            # Différents sélecteurs pour détecter les liens d'articles
            selectors = [
                'a[href*="/blog/"]',
                'a[href*="/article/"]', 
                'a[href*="/post/"]',
                'article a',
                '.post-title a',
                '.entry-title a',
                'h2 a',
                'h3 a',
                '.blog-post a',
                '.article-link',
                'a[href*="/20"]',  
                'a[href*="/marques/"]',  
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href:
                        full_url = urljoin(blog_url, href)
                        if urlparse(full_url).netloc == base_domain:
                            article_links.add(full_url)
            
            filtered_links = []
            exclude_patterns = [
                r'/page/',
                r'/category/',
                r'/tag/',
                r'/author/',
                r'/search/',
                r'#',
                r'\?',
                r'/feed',
                r'/rss',
            ]
            
            for link in article_links:
                if not any(re.search(pattern, link, re.IGNORECASE) for pattern in exclude_patterns):
                    filtered_links.append(link)
            
            print(f"Trouvé {len(filtered_links)} liens d'articles potentiels")
            return list(set(filtered_links))[:20]  # Limiter à 20 articles max
            
        except Exception as e:
            print(f"Erreur lors de l'extraction des liens: {e}")
            return []
    
    def _extract_main_image(self, soup) -> Optional[str]:
        """Extrait l'URL de l'image principale de l'article."""
        # Sélecteurs communs pour les images principales d'articles
        image_selectors = [
            'meta[property="og:image"]',  # Open Graph image
            'meta[name="twitter:image"]',  # Twitter Card image
            '.article-featured-image img',  # Classes communes pour les images à la une
            '.post-thumbnail img',
            '.entry-featured-image img',
            'article img:first-of-type',  # Première image dans l'article
            '.wp-post-image',  # Image à la une WordPress
            'article .image-principale',
            '[itemprop="image"]'
        ]
        
        # Chercher l'image avec les sélecteurs
        for selector in image_selectors:
            element = soup.select_one(selector)
            if element:
                # Selon le type d'élément, extraire l'URL
                if element.name == 'meta':
                    image_url = element.get('content')
                else:
                    image_url = element.get('src')
                
                if image_url:
                    # S'assurer que l'URL est absolue
                    if not image_url.startswith(('http://', 'https://')):
                        base_url = soup.find('base', href=True)
                        if base_url:
                            image_url = urljoin(base_url['href'], image_url)
                    return image_url
        
        return None

    def scrape_article_content(self, url: str) -> Optional[dict]:
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', '.sidebar', '.advertisement']):
                element.decompose()
            
            content_selectors = [
                'article',
                '.post-content',
                '.entry-content', 
                '.article-content',
                '.blog-post',
                '.content',
                'main',
                '.post-body',
                '[role="main"]'
            ]
            
            content = ""
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    content = element.get_text(strip=True)
                    if len(content) > 200:  # Contenu suffisant
                        break
            
            if not content or len(content) < 200:
                body = soup.find('body')
                if body:
                    content = body.get_text(strip=True)
            
            # Extraire l'image principale
            image_url = self._extract_main_image(soup)
            
            return {
                'content': content if len(content) > 100 else None,
                'image_url': image_url
            }
            
        except Exception as e:
            print(f"Erreur lors du scraping de {url}: {e}")
            return None
    
    def _clean_markdown_response(self, text: str) -> str:
        """Nettoie la réponse de l'API en retirant les balises ```markdown``` et ```."""
        # Retire les balises ```markdown au début
        text = re.sub(r'^```markdown\s*\n', '', text, flags=re.MULTILINE)
        # Retire les balises ``` à la fin
        text = re.sub(r'\n```\s*$', '', text, flags=re.MULTILINE)
        # Retire toute autre balise ```markdown qui pourrait être présente
        text = re.sub(r'```markdown\s*', '', text)
        # Retire les balises ``` restantes
        text = re.sub(r'```\s*', '', text)
        return text.strip()

    def generate_blog_article(self, content: str, original_url: str, image_url: Optional[str] = None) -> Optional[str]:
        try:
            # Image par défaut si aucune image n'est trouvée
            default_image = "https://images.unsplash.com/photo-1611224923853-80b023f02d71?ixlib=rb-4.0.3&auto=format&fit=crop&w=2070&q=80"
            
            prompt = f"""
Transforme ce contenu en un article de blog professionnel au format Markdown suivant EXACTEMENT cette structure:

---
publishDate: {datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}
title: '[TITRE_ACCROCHEUR]'
excerpt: [DESCRIPTION_COURTE_ET_ENGAGEANTE]
image: '{image_url if image_url else default_image}'
tags:
  - [tag1]
  - [tag2]
  - [tag3]
metadata:
  canonical: {original_url}
---

[CONTENU_ARTICLE_COMPLET_EN_MARKDOWN]

INSTRUCTIONS:
1. Crée un titre accrocheur et professionnel en français
2. Écris un excerpt de 1-2 phrases qui donne envie de lire
3. Choisis 3 tags pertinents en anglais (ex: web-development, marketing, tutorial)
4. Réécris complètement l'article en français avec:
   - Une introduction engageante
   - Des sections avec des titres ## 
   - Du contenu informatif et utile
   - Une conclusion
   - Format Markdown (gras, italique, listes, etc.)
5. L'article doit faire au minimum 800 mots
6. Utilise l'image fournie (ne pas changer)
7. Garde le format EXACT des métadonnées
8. NE PAS utiliser de balises ```markdown``` ou ``` dans la réponse

Contenu à transformer:
{content[:3000]}
"""

            response = self.model.generate_content(prompt)
            if not response or not response.text:
                return None
                
            # Nettoyer la réponse
            cleaned_content = self._clean_markdown_response(response.text)
            return cleaned_content
            
        except Exception as e:
            print(f"Erreur avec l'API Gemini: {e}")
            return None
    
    def _extract_site_name(self, url: str) -> str:
        """Extrait et nettoie le nom du site depuis l'URL."""
        try:
            # Extraire le domaine sans www. et sans extension
            domain = urlparse(url).netloc.lower()
            domain = re.sub(r'^www\.', '', domain)
            domain = domain.split('.')[0]
            return domain
        except Exception:
            return "site"

    def _extract_tags(self, content: str) -> str:
        """Extrait les tags du contenu markdown."""
        try:
            # Chercher les tags dans le contenu
            tags_match = re.findall(r'tags:\s*\n(?:\s*-\s*\[([^\]]+)\])*', content)
            if tags_match:
                # Prendre le premier tag trouvé
                return tags_match[0].lower()
            return "article"
        except Exception:
            return "article"

    def _slugify(self, text: str) -> str:
        """Convertit un texte en slug."""
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

    def save_article(self, article_content: str, url: str, output_dir: str = "articles"):
        """Sauvegarde l'article avec un nom basé sur le titre slugifié."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Extraire le titre du contenu markdown
            title_match = re.search(r"title: '([^']+)'", article_content)
            if title_match:
                title = title_match.group(1)
                # Slugifier le titre
                filename = f"{self._slugify(title)}.md"
            else:
                # Fallback si on ne trouve pas le titre
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = f"article-{timestamp}.md"
            
            # Construire le chemin complet
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(article_content)
            
            print(f"Article sauvegardé: {filepath}")
            return filepath
            
        except Exception as e:
            print(f"Erreur lors de la sauvegarde: {e}")
            return None
    
    def process_single_article(self, article_url: str, article_number: int = 1) -> Optional[str]:
        
        print(f"🎯 Traitement de l'article {article_number}: {article_url}")
        
        content = self.scrape_article_content(article_url)
        if not content:
            print(f"❌ Impossible de récupérer le contenu de l'article {article_number}")
            return None
        
        print(f"✅ Contenu récupéré ({len(content['content'])} caractères)")
        
        article = self.generate_blog_article(content['content'], article_url, content['image_url'])
        if not article:
            print(f"❌ Impossible de générer l'article {article_number}")
            return None
        
        # Nom de fichier unique avec numéro d'article et timestamp
        filename = f"article_{article_number}_{int(time.time())}"
        filepath = self.save_article(article, article_url)
        
        if filepath:
            print(f"✅ Article {article_number} sauvegardé: {filepath}")
            return filepath
        else:
            print(f"❌ Erreur lors de la sauvegarde de l'article {article_number}")
            return None
    
    def process_multiple_urls(self, urls: List[str]) -> List[str]:
        """
        Traite une liste d'URLs d'articles uniques
        """
        processed_files = []
        total_urls = len(urls)
        
        print(f"📊 Traitement de {total_urls} URL(s)...")
        
        for i, url in enumerate(urls, 1):
            print(f"\n{'='*50}")
            print(f"📝 Article {i}/{total_urls}")
            
            # Vérifier si c'est bien un article unique
            if not self.is_single_article_url(url):
                print(f"⚠️ URL {url} ne semble pas être un article unique, traitement quand même...")
            
            filepath = self.process_single_article(url, i)
            
            if filepath:
                processed_files.append(filepath)
                print(f"✅ Article {i} traité avec succès")
            else:
                print(f"❌ Échec du traitement de l'article {i}")
            
            if i < total_urls:
                print("⏳ Pause de 3 secondes...")
                time.sleep(3)
        
        return processed_files
    
    def process_blog(self, blog_url: str, max_articles: int = 10) -> List[str]:
        
        print(f"🔍 Analyse de l'URL: {blog_url}")
        
        if self.is_single_article_url(blog_url):
            print("📄 URL détectée comme article unique")
            result = self.process_single_article(blog_url)
            return [result] if result else []
        
        print("🏠 URL détectée comme page de blog - recherche d'articles...")
        
        article_links = self.extract_blog_links(blog_url)
        
        if not article_links:
            print("❌ Aucun lien d'article trouvé")
            print("💡 Conseil: Vérifiez que l'URL pointe vers la page d'accueil du blog")
            return []
        
        processed_files = []
        
        for i, link in enumerate(article_links[:max_articles]):
            print(f"\n📝 Traitement de l'article {i+1}/{min(len(article_links), max_articles)}: {link}")
            
            content = self.scrape_article_content(link)
            if not content:
                print("❌ Impossible de récupérer le contenu")
                continue
            
            print(f"✅ Contenu récupéré ({len(content['content'])} caractères)")
            
            article = self.generate_blog_article(content['content'], link, content['image_url'])
            if not article:
                print("❌ Impossible de générer l'article")
                continue
            
            filename = f"article_{i+1}_{int(time.time())}"
            filepath = self.save_article(article, link)
            if filepath:
                processed_files.append(filepath)
                print(f"✅ Article sauvegardé")
            
            time.sleep(2)
        
        print(f"\n🎉 Traitement terminé. {len(processed_files)} articles générés.")
        return processed_files

def load_config():
    
    load_dotenv()
    
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        print("❌ Erreur: GEMINI_API_KEY non trouvée dans le fichier .env")
        print("Créez un fichier .env avec: GEMINI_API_KEY=votre_cle_api")
        return None, []
    
    try:
        with open('urlblog.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        urls = []
        for line in lines:
            url = line.strip()
            if url and not url.startswith('#'):  
                urls.append(url)
        
        if not urls:
            print("❌ Erreur: Aucune URL trouvée dans urlblog.txt")
            print("Ajoutez une ou plusieurs URLs dans le fichier urlblog.txt (une par ligne)")
            return None, []
            
        print(f"📋 {len(urls)} URL(s) trouvée(s) dans urlblog.txt")
        for i, url in enumerate(urls, 1):
            print(f"   {i}. {url}")
            
    except FileNotFoundError:
        print("❌ Erreur: Fichier urlblog.txt non trouvé")
        print("Créez un fichier urlblog.txt avec les URLs des articles à scraper (une par ligne)")
        return None, []
    except Exception as e:
        print(f"❌ Erreur lors de la lecture de urlblog.txt: {e}")
        return None, []
    
    return gemini_api_key, urls

def main():
    
    print("🚀 Démarrage du Blog Scraper Multi-URLs...")
    
    gemini_api_key, urls = load_config()
    
    if not gemini_api_key or not urls:
        return
    
    print(f"\n📝 Configuration chargée:")
    print(f"   - Nombre d'URLs: {len(urls)}")
    print(f"   - API Gemini: {'✅ Configurée' if gemini_api_key else '❌ Manquante'}")
    
    try:
        print(f"\n🔧 Initialisation du scraper...")
        scraper = BlogScraper(gemini_api_key)
        
        single_articles = [url for url in urls if scraper.is_single_article_url(url)]
        blog_pages = [url for url in urls if not scraper.is_single_article_url(url)]
        
        processed_files = []
        
        if single_articles:
            print(f"\n📄 Mode: Articles uniques ({len(single_articles)} URLs)")
            files = scraper.process_multiple_urls(single_articles)
            processed_files.extend(files)
        
        if blog_pages:
            print(f"\n🏠 Mode: Pages de blog ({len(blog_pages)} URLs)")
            try:
                max_articles = int(input("📊 Nombre d'articles à traiter par blog (défaut: 5): ") or "5")
            except ValueError:
                max_articles = 5
            
            for blog_url in blog_pages:
                print(f"\n🔄 Traitement du blog: {blog_url}")
                files = scraper.process_blog(blog_url, max_articles)
                processed_files.extend(files)
        
        if processed_files:
            print(f"\n🎉 Succès! {len(processed_files)} article(s) généré(s):")
            for file in processed_files:
                print(f"  📄 {file}")
        else:
            print("\n❌ Aucun article n'a pu être généré")
            
    except Exception as e:
        print(f"\n💥 Erreur lors de l'initialisation: {e}")
        print("💡 Vérifiez votre clé API Gemini dans le fichier .env")

if __name__ == "__main__":
    main()