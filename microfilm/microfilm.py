# Internal dependencies
import config
import newspaper as np
from newspaper.mthreading import fetch_news

# External dependencies
import feedparser
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    def sync_playwright(*args, **kwargs):
        raise ImportError(
            "Playwright is not installed. Install it with:\n"
            "  pip install playwright\n"
            "Then install browser binaries with:\n"
            "  playwright install chromium\n"
            "Read more: https://playwright.dev/python/docs/intro"
        )
from jinja2 import Environment, FileSystemLoader

# Module imports
import time
import logging
import re
import os
import unicodedata
from pathlib import Path
import json


cfg = config.load_config()

# Define module and project roots
MODULE_ROOT = Path(__file__).resolve().parent
logging.debug(f"MODULE ROOT: {MODULE_ROOT}")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
logging.debug(f"PROJECT ROOT: {PROJECT_ROOT}")
SITE_DIRECTORY = Path.joinpath(PROJECT_ROOT, cfg.output_directory)
logging.debug(f"SITE DIRECTORY: {SITE_DIRECTORY}")

class Microfilm():
    def __init__(self):
        self.etag = None
        self.modified = None
        self.rss = cfg.rss
        self.filter = self._filter_author
        
    def generate(self):
        articles = []
        newsgather = Newsgather(self.rss)
        feed = newsgather.gather()

        results = fetch_news(list(feed), threads=cfg.thread_count)

        filtered_articles = []
        for article in results:
            if self._filter_author(article):
                downloaded = ArticleDownloader(article.url).download()
                if downloaded:
                    filtered_articles.append(downloaded)
        Typeset().generator(filtered_articles)
             
    def regenerate(self):
        for file in cfg.output_directory.rglob('*.json'):
            with open(file, 'r', encoding='utf-8') as file:
                data = json.load(file)
                Typeset().html(data)

    def download_articles(self, file: str):  
        formats = [".txt"] # add more later
        file_path = Path.joinpath(PROJECT_ROOT, file)
        
        if file_path.suffix in formats:
            with open(file_path, mode="r") as f:
                urls = [line.strip() for line in f]
                
                if urls:
                    saved_urls = set(self._load_json_articles())
                    new_urls = [url for url in urls if url not in saved_urls]

                    logging.info(f"Found {len(urls)} total URLs, {len(new_urls)} new URLs to process")
                    typeset = Typeset()
                    for url in new_urls:
                        logging.info(f"Processing URL: {url}")
                        article = ArticleDownloader(url).download()

                        if article:
                            data = typeset._store_data(article)
                            typeset.generators()(data)
                            logging.info("Article processed successfully!")
                        else:
                            logging.warning(f"Failed to download article from {url}")
        else:
            logging.error(f"File format \"{file_path.suffix}\" is not supported")
            raise ValueError
        
    def _filter_author(self, a):
        filter = cfg.author_filter
        
        if not filter or filter == "":
            return True

        elif a.authors:
            for author in a.authors:
                if filter.lower() in author.lower():
                    logging.debug(f"Article matched author filter: {author}")
                    return True
            logging.debug(f"Article rejected by author filter (looking for: {filter})")
        else:
            logging.debug(f"Article rejected by author filter (looking for: {filter})")
            return False
    def _load_json_articles(self) -> list[str]:
        stored_urls = []
        json_path = Path.joinpath(SITE_DIRECTORY, "json")
        try:
            # Iterate through all JSON files in the directory
            for json_file in SITE_DIRECTORY.glob('*.json'):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        url = data.get("url")
                        if url:
                            stored_urls.append(url)
                except (json.JSONDecodeError, IOError) as e:
                    logging.warning(f"Could not read JSON file {json_file}: {e}")
                    continue
        except Exception as e:
            logging.error(f"Error loading JSON articles: {e}")
        
        logging.info(f"Loaded {len(stored_urls)} existing URLs")
        return stored_urls

class Newsgather():
    def __init__(self, etag=None, modified=None):
        self.etag = etag
        self.modified = modified
        
    def gather(self) -> list[str]:
        fetch = self.fetch
        status = self._get_status
        articles = []
        
        feed = fetch(cfg.rss)
        
        if status(feed) and feed is not None:
            feed_title = getattr(feed.feed, 'title', 'Unknown Feed')
            logging.info(f"Processing feed: {feed_title}")
            for entry in feed.entries:
                if hasattr(entry, 'link') and entry.link:
                    articles.append(str(entry.link))  # Store just the URL string
                else:
                    entry_title = getattr(entry, 'title', 'Unknown Title')
                    logging.warning(f"Entry missing link: {entry_title}")
                
        return articles
                
    def fetch(self, url:str) -> feedparser.FeedParserDict:
        try:
            feed = feedparser.parse(url,
                                    etag=self.etag,
                                    modified=self.modified)
            return feed
        except Exception as e:
            logging.warning(f"Could not scrape feed: {e}")
            raise
        
    def _get_status(self, feed):
        if feed is None:
            logging.warning(f"Feed is not valid")
            return False
        else:
            if feed.bozo:
                e = feed.bozo_exception
                logging.warning(f"Feed is not valid: {e}")
                return False
            logging.debug(f"Feed status code: {feed.status}")
            if feed.status == 304:
                logging.debug("Feed has not been updated")
                return False
            if feed.status in [200, 301, 302, 307, 308]:
                if hasattr(feed, "etag"):
                    self.etag = feed.etag
                if hasattr(feed, "modified"):
                    self.modified = feed.modified
                return True
            
class ArticleDownloader():
    def __init__(self, url) -> None:
        self.url = url
        #TODO Accept list[str] for batch processing?

    def _create_article(self, url: str, html: str = None) -> np.Article:
        """Create and parse an article from URL or HTML."""
        article = np.Article(url=url, input_html=html, language='en', config=cfg.newspaper)
        if not html:
            article.download()
        article.parse()
        return article if article.text else None

    def _get_url_context(self, url):
        """Extract domain and path info for better error reporting."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.netloc} ({parsed.scheme}://{parsed.hostname})"
        except:
            return url[:50] + ("..." if len(url) > 50 else "")
    def download(self):
        url = self.url
        try:
            a = self._create_article(url)

            if a:
                logging.info(f"Article downloaded successfully: {a.title}")
                return a
            else:
                logging.info(f"No text found in: {url}")
                # Try fulltext extraction as fallback
                article = self._fulltext(url)
                return article

        except np.ArticleException as e:
            logging.error(f"ArticleException downloading [{self._get_url_context(url)}]: {e}")
            return self._fulltext(url)
        except Exception as e:
            logging.error(f"Unexpected error processing article [{self._get_url_context(url)}]: {type(e).__name__}: {e}", exc_info=True)
            return None

    def _validate_entry(self, entry):
        try:
            if not hasattr(entry, 'link') or not entry.link:
                return False
            if not hasattr(entry, 'title') or not entry.title:
                return False
            else:
                return True
        except IndexError:
            logging.warning(f"Could not access entry")
    
    def _is_valid(self, a:np.Article) -> bool:
        if a.text and a.text.strip() and a.is_valid_body:
            return True
        else:
            logging.info(f"No text found in: {a.title}")
            return False
        
    def _fulltext(self, url):
        """Extract article text from page using Playwright browser."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.set_default_timeout(cfg.timeout)
                    return self._fetch_page_content(page, url)
                finally:
                    browser.close()
        except TimeoutError:
            logging.warning(f"[TIMEOUT] Fulltext extraction timed out [{self._get_url_context(url)}]")
            return self._retry_fulltext_with_backoff(url)
        except Exception as e:
            logging.warning(f"[{type(e).__name__}] Fulltext extraction failed [{self._get_url_context(url)}]: {e}")
            return None

    def _fetch_page_content(self, page, url, wait_strategy="networkidle"):
        """Fetch page content with specified wait strategy."""
        try:
            logging.info(f"[FETCH] Loading {url} with {wait_strategy} strategy")
            page.goto(url, timeout=cfg.timeout)

            # Use appropriate wait strategy
            if wait_strategy == "networkidle":
                page.wait_for_load_state("networkidle", timeout=cfg.timeout)
            else:
                page.wait_for_load_state("domcontentloaded", timeout=cfg.timeout)

            html = page.content()
            article = self._create_article(url, html)
            if article:
                logging.info(f"[SUCCESS] Fulltext extraction succeeded [{self._get_url_context(url)}]")
            else:
                logging.info(f"[EMPTY] No extractable text in page [{self._get_url_context(url)}]")
            return article
        except TimeoutError:
            # Try to extract whatever loaded before timeout
            try:
                html = page.content()
                logging.debug(f"[PARTIAL] Got partial content before timeout [{self._get_url_context(url)}]")
                article = self._create_article(url, html)
                return article
            except:
                raise

    def _retry_fulltext_with_backoff(self, url, attempt=1, max_attempts=None):
        """Retry fulltext extraction with simpler strategies."""
        if max_attempts is None:
            max_attempts = cfg.playwright_retry_attempts
        if attempt >= max_attempts:
            logging.error(f"[EXHAUSTED] Max retry attempts ({max_attempts-1}) reached [{self._get_url_context(url)}]")
            return None

        logging.debug(f"[RETRY {attempt}/{max_attempts-1}] Attempting simpler extraction strategy")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.set_default_timeout(cfg.timeout * 2)
                    # Use simpler wait strategy on retry
                    return self._fetch_page_content(page, url, wait_strategy="domcontentloaded")
                finally:
                    browser.close()
        except Exception as e:
            logging.warning(f"[RETRY_FAILED {attempt}] {type(e).__name__}: {e}")
            return self._retry_fulltext_with_backoff(url, attempt + 1, max_attempts)
           
class Typeset():
    def generator(self, articles):
        if not articles:
            logging.warning("No articles to generate")
            return
        
        logging.info(f"Generating output for {len(articles)} articles")
        generated_count = 0

        for idx, a in enumerate(articles, 1):
            try:
                if not a.title or not a.title.strip():
                    logging.warning(f"Article {idx} missing title, skipping generation")
                    continue
                d = self._store_data(a)
                generate = self.generators()
                files = generate(d)
                generated_count += 1
                logging.debug(f"Generated output for article: {a.title[:50]}...")
            except Exception as e:
                logging.error(f"Error generating page for {a.url}: {type(e).__name__}: {e}", exc_info=True)
        
        logging.info(f"Successfully generated {generated_count}/{len(articles)} articles")

    def _store_data(self, a) -> dict[str, str]:
        def _check(d):
            if d:
                return d
            else:
                return None
        def _raw_html(raw_html:str):
            idx = raw_html.lower().find("<p")
            if idx == -1:
                return raw_html.strip()
            return raw_html[idx:].strip()

        data = {
            "text": _check(a.text),
            "html": _raw_html(a.article_html),
            "author": a.authors,
            "date": a.publish_date.isoformat() if a.publish_date else "",
            "title": a.title or "",
            "url": a.url or "",
            "source": a.source_url or "",
            "summary": a.summary or "",
        }
        return data
        
    def generators(self):
        formats = cfg.formats
        format_methods = {
            "json": self.json,
            "html": self.html,
        }
        
        selected_methods = [format_methods[fmt] for fmt in formats if fmt in format_methods]
        
        if not selected_methods:
            raise ValueError("No valid output formats specified.")
        
        def generate_files(data):
            for method in selected_methods:
                method(data)
        
        return generate_files
        
    def json(self, data):
        content = json.dumps(data, indent=4)
        title = data["title"]
        self._create_file(content, title, format="json")
        
    def html(self, data):
        try:
            if not Path(cfg.template_directory).exists():
                logging.error(f"Template directory does not exist: {cfg.template_directory}")
                raise FileNotFoundError(f"Template directory not found: {cfg.template_directory}")

            loader = FileSystemLoader(cfg.template_directory)
            env = Environment(loader=loader)
            
            try:
                template = env.get_template("article.html")
            except Exception as e:
                logging.error(f"Template 'article.html' not found in {cfg.template_directory}: {e}")
                raise
            
            html = template.render(data)
            title = data.get("title")
            return self._create_file(html, title, format="html")
        except Exception as e:
            logging.error(f"Error rendering HTML template: {type(e).__name__}: {e}", exc_info=True)
            raise
    
    def _create_file(self, content: str, title:str, format: str):
        def _slugify(text: str) -> str:
            text = unicodedata.normalize("NFKD", text)
            text = text.encode("ascii", "ignore").decode("ascii")
            text = re.sub(r"[^\w\s-]", "", text).strip().lower()
            slug = re.sub(r"[-\s]+", "_", text)
            return slug or "article"
        
        if not content or not content.strip():
            logging.error(f"Cannot save file for '{title}': content is empty")
            raise ValueError("File content cannot be empty")
        
        filename = _slugify(title) + "." + format
        format_path = Path.joinpath(Path(cfg.output_directory), format)
        format_path.mkdir(exist_ok=True)
        file_path = Path.joinpath(format_path, filename)
        
        if file_path.exists():
            logging.info(f"File already exists, overwriting: {filename}")
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            if file_path.stat().st_size == 0:
                logging.warning(f"File saved but is empty: {filename}")
            
            logging.info(f"Saved article [{format}]: {filename} ({file_path.stat().st_size} bytes)")
        except IOError as e:
            logging.error(f"Failed to write file {file_path}: {type(e).__name__}: {e}", exc_info=True)
            raise