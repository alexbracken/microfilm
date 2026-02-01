from config import Config

import newspaper as np
import feedparser
from playwright.sync_api import sync_playwright
from jinja2 import Environment, FileSystemLoader
import xml.etree.ElementTree as ET

import time
import logging
import re
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as xml
import json
from dataclasses import dataclass

config = Config()

class Microfilm():
    def __init__(self):
        self.etag = None
        self.modified = None
        
    def watch(self):
        newsgather = Newsgather(config.rss, etag=self.etag, modified=self.modified)
        feed = newsgather.feed
        if feed:
            # Update persistent etag and modified for next conditional GET
            self.etag = newsgather.etag
            self.modified = newsgather.modified
            articles = ArticleDownloader().download(feed)
            Typeset().generator(articles)

class Newsgather():
    def __init__(self, url:str, etag=None, modified=None):
        self.config = Config()
        self.url = url
        self.etag = etag
        self.modified = modified
        self.feed = self.parse()

    def fetch(self):
        '''
        Fetch the RSS feed
        
        :param feed: RSS feed URL
        :return: FeedParserDict object
        '''
        try:
            feed = feedparser.parse(self.config.rss, 
                                    etag=self.etag, 
                                    modified=self.modified)
            logging.info("Successfully fetched feed")
            return feed
        except Exception as e:
            logging.warning(f"Could not scrape feed: {e}")
            return None
            
    def parse(self):
        try:
            feed = self.fetch()
        except Exception as e:
            logging.warning(f"Could not scrape feed: {e}")
            return None
            
        if feed and isinstance(feed, feedparser.FeedParserDict):
            if feed.bozo:
                e = feed.bozo_exception
                logging.warning(f"Feed is not valid: {e}")
            logging.info(f"Feed status code: {feed.status}")
            if feed.status == 304:
                logging.info("Feed has not been updated")
                return None
            if feed.status in [200, 301, 302, 307, 308]:
                logging.info("Feed has been updated")
                if hasattr(feed, "etag"):
                    self.etag = feed.etag
                if hasattr(feed, "modified"):
                    self.modified = feed.modified
                return feed
        logging.warning("Feed is None or not a valid FeedParserDict")
        return None

class ArticleDownloader():
    def __init__(self):
        self.npconfig = np.Config()
        self.config = Config()
        
    def download(self, feed):
        config = self.config
        author_filter = config.author_filter
        articles = []
        
        if not feed.entries:
            logging.warning("Feed has no entries")
            return articles
        
        logging.info(f"Found {len(feed.entries)} articles in feed")
        
        for i in range(min(config.max_articles, len(feed.entries))):
            try:
                entry = feed.entries[i]
                if not hasattr(entry, 'link') or not entry.link:
                    logging.warning(f"Article {i+1} missing link, skipping")
                    continue
                if not hasattr(entry, 'title') or not entry.title:
                    logging.warning(f"Article {i+1} missing title, skipping")
                    continue
            except IndexError:
                logging.error(f"IndexError accessing entry {i}")
                break
            
            url = entry.link
            try:
                logging.info(f"Processing article ({i+1}/{min(config.max_articles, len(feed.entries))}): \"{entry.title}\"")
                a = np.article(url = url, config = config.np_config).download().parse()
                has_text = self._is_valid
                filter = self._filter
                
                if filter(a):
                    if has_text(a):
                        articles.append(a)
                    else:
                        a = self._fulltext(url)
                        articles.append(a)
                else:
                    logging.info(f"Author does not match filter")
            except np.ArticleException as e: 
                logging.error(f"ArticleException downloading {url}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error processing article {url}: {type(e).__name__}: {e}", exc_info=True)

        logging.info(f"Successfully downloaded {len(articles)} articles")
        return articles
    def _is_valid(self, a:np.Article) -> bool:
        if a.text or not a.text.strip() or not a.is_valid_body:
            logging.info(f"No text found in: {a.title}")
            return True
        else:
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
                        article = np.article(url=url, input_html=content, language='en', config=self.npconfig)
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
        filter = self.config.author_filter
        
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
                    continue
                
                d = self._store_data(a)
                generate = self.generators()
                files = generate(d)
                generated_count += 1
                logging.debug(f"Generated output for article: {a.title[:50]}...")
            except Exception as e:
                logging.error(f"Error generating page for {a.url}: {type(e).__name__}: {e}", exc_info=True)
        
        logging.info(f"Successfully generated {generated_count}/{len(articles)} articles")
                
    def _store_data(self, a:np.Article) -> dict[str, str]:
        data = {
            "text": a.text,
            "html": a.article_html,
            "author": a.authors,
            "date": a.publish_date.isoformat() if a.publish_date else "",
            "title": a.title or "",
            "url": a.url or "",
            "source": a.source_url or "",
            "summary": a.summary or "",
        }
        return data
        
    def generators(self):
        formats = config.output_formats
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
            if not Path(config.template_dir).exists():
                logging.error(f"Template directory does not exist: {config.template_dir}")
                raise FileNotFoundError(f"Template directory not found: {config.template_dir}")
            
            loader = FileSystemLoader(config.template_dir)
            env = Environment(loader=loader)
            
            try:
                template = env.get_template("article.html")
            except Exception as e:
                logging.error(f"Template 'article.html' not found in {config.template_dir}: {e}")
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
        file_path = Path.joinpath(Path(config.output_dir), filename)
        
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