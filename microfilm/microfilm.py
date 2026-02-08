import config

import newspaper as np
import feedparser
from playwright.sync_api import sync_playwright
from jinja2 import Environment, FileSystemLoader

import time
import logging
import re
import unicodedata
from pathlib import Path
import json
from dataclasses import dataclass

cfg = config.load_config()

class Microfilm():
    def __init__(self):
        self.etag = None
        self.modified = None
        self.rss = cfg.rss
        
    def generate(self):
        newsgather = Newsgather(self.rss, etag=self.etag, modified=self.modified)
        feed = newsgather.gather()
        if feed is not None:
            articles = ArticleDownloader().download(feed)
            Typeset().generator(articles)
            
    def regenerate(self):
        for file in cfg.output_directory.rglob('*.json'):
            with open(file, 'r', encoding='utf-8') as file:
                data = json.load(file)
                Typeset()._generate_html(data)
        
class Newsgather():
    def __init__(self, url:str, etag=None, modified=None):
        self.etag = etag
        self.modified = modified
        
    def gather(self):
        fetch = self._fetch
        valid = self._validate
        
        feed = fetch(cfg.rss)
        if valid(feed) and feed is not None:
            logging.info(f"Feed at {feed.url}")
            return feed
            
    def _fetch(self, url:str):
        try:
            feed = feedparser.parse(url, 
                                    etag=self.etag, 
                                    modified=self.modified)
            logging.info("Successfully fetched feed")
            return feed
        except Exception as e:
            logging.warning(f"Could not scrape feed: {e}")
        
    def _validate(self, feed):
        if feed is None:
            logging.warning(f"Feed is not valid")
            return False
        else:
            if feed.bozo:
                e = feed.bozo_exception
                logging.warning(f"Feed is not valid: {e}")
                return False
            logging.info(f"Feed status code: {feed.status}")
            if feed.status == 304:
                logging.info("Feed has not been updated")
                return False
            if feed.status in [200, 301, 302, 307, 308]:
                if hasattr(feed, "etag"):
                    self.etag = feed.etag
                if hasattr(feed, "modified"):
                    self.modified = feed.modified
                return True

class ArticleDownloader():
        
    def download(self, feed: feedparser.FeedParserDict):
        valid = self._validate_entry
        articles = []
        
        logging.info(f"Found {len(feed.entries)} articles in feed")
        
        for i in range(min(cfg.max_articles, len(feed.entries))):
            entry = feed.entries[i]
            if valid(entry) == True:
                a = self._download_article(entry.link)
                if a is not None:
                    articles.append(a)
            
            
        logging.info(f"Successfully downloaded {len(articles)} articles")
        return articles
    
    def _download_article(self, url):
        has_text = self._is_valid
        filter = self._filter
        
        try:
            a = np.article(url = url, config = cfg.newspaper)
            if filter(a):
                if has_text(a):
                    return a
                else:
                    fulltext_article = self._fulltext(url)
                    if fulltext_article:
                        return fulltext_article
            else:
                logging.info(f"Author does not match filter")
        except np.ArticleException as e: 
            logging.error(f"ArticleException downloading {url}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error processing article {url}: {type(e).__name__}: {e}", exc_info=True)

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
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    try:
                        logging.debug(f"Fetching fulltext via Playwright for {url}")
                        page.goto(url, timeout=10000)
                        time.sleep(1)
                        content = page.content()
                        article = np.article(url=url, input_html=content, language='en', config = cfg.newspaper).parse()
                        logging.info(f"Fulltext extraction successful for {url}")
                        return article
                    finally:
                        page.close()
                finally:
                    browser.close()
        except Exception as e:
            logging.warning(f"Fulltext extraction failed for {url}: {type(e).__name__}: {e}")
            return None
        
    def _filter(self, a) -> bool:
        filter = cfg.author_filter
        
        # If no filter configured, accept all articles
        if not filter or filter == "":
            return True

        if a.authors:
            for author in a.authors:
                if filter.lower() in author.lower():
                    logging.debug(f"Article matched author filter: {author}")
                    return True
        
        # No match found
        logging.debug(f"Article rejected by author filter (looking for: {filter})")
        return False
           
class Typeset():
    def generator(self, articles:list[np.Article]):
        if not articles:
            logging.warning("No articles to generate")
            return
        
        logging.info(f"Generating output for {len(articles)} articles")
        generated_count = 0
        
        for idx, a in enumerate(articles, 1):
            try:
                if not a.title or not a.title.strip():
                    logging.warning(f"Article {idx} missing title, skipping generation")
                    break
                else:
                    d = self._store_data(a)
                    generate = self.generators()
                    files = generate(d)
                    generated_count += 1
                    logging.debug(f"Generated output for article: {a.title[:50]}...")
            except Exception as e:
                logging.error(f"Error generating page for {a.url}: {type(e).__name__}: {e}", exc_info=True)
        
        logging.info(f"Successfully generated {generated_count}/{len(articles)} articles")


    def _store_data(self, a:np.Article) -> dict[str, str]:
        def _check(d):
            if d:
                return True
            else:
                return None
        data = {
            "text": _check(a.text),
            "html": _check(a.article_html),
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
            "json": self._generate_json,
            "html": self._generate_html,
        }
        
        selected_methods = [format_methods[fmt] for fmt in formats if fmt in format_methods]
        
        if not selected_methods:
            raise ValueError("No valid output formats specified.")
        
        def generate_files(data):
            for method in selected_methods:
                method(data)
        
        return generate_files
        
    def _generate_json(self, data):
        content = json.dumps(data, indent=4)
        title = data.get("title")
        self._create_file(content, title, format="json")
        
    def _generate_html(self, data):
        try:
            if not Path(cfg.output_directory).exists():
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
        file_path = Path.joinpath(Path(cfg.output_directory), filename)
        
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