import newspaper as np
import feedparser
from playwright.sync_api import sync_playwright
from jinja2 import Environment, FileSystemLoader
from tqdm import tqdm

from typing import List
import time
import logging
import os
import re
import unicodedata
import yaml
from pathlib import Path


class Microfilm():
    def __init__(self):
        MODULE_ROOT = Path(__file__).resolve().parent # Find project directory
        PROJECT_ROOT = Path(__file__).resolve().parent.parent
        
        # Initialize etag and modified for conditional GET
        self.etag = None
        self.modified = None
        
        # Load config
        config = yaml.safe_load(open("config.yaml"))
        
        # Set config variables
        self.npconfig = np.Config()
        if 'author_filter' in config:
            self.author_filter = config.get('author_filter')
        if 'watch' in config:
            self.watch = config.get('watch')
        if 'rss' in config:
            self.url = config.get('rss')
        if 'update_frequency' in config:
            self.frequency = config.get('update_frequency')
        
        # Configure directories
        dir_config = config.get('directories')
        if 'output_dir' in dir_config:
            output_dir = Path(dir_config.get('output_dir').lstrip("/"))
            site_path = (PROJECT_ROOT / output_dir).resolve()
            os.makedirs(site_path, exist_ok=True)
            self.output_dir = site_path
        self.template_dir = PROJECT_ROOT.joinpath("templates")
        
        while self.watch == True:
            self.watch_feed()

    def watch_feed(self):
        try:
            seconds = self.frequency
            logging.info("Starting watch mode. Press Ctrl+C to exit.")
            while True:
                self.scrape()
                logging.info(f"Sleeping for {seconds} seconds")
                time.sleep(seconds)
        except KeyboardInterrupt:
            logging.info('Manual break by user')
        
    def scrape(self):
        url = self.url
        logging.info(f"Scraping feed: {url}")
        etag = None
        modified = None
        
        try:
            feed = feedparser.parse(url, etag=etag, modified=modified)
        except Exception as e:
            logging.warning(f"Could not scrape feed: {e}")
        else:
            if feed.bozo:
                e = feed.bozo_exception
                logging.warn(f"Feed is not valid: {e}")
                return None
            if feed.status == 304:
                logging.info("Feed has not been updated")
                return None
            if feed.status == 200:
                logging.info("Feed has been updated")
                self.etag = getattr(feed, 'etag', None)
                self.modified = getattr(feed, 'modified', None)
                self._download_articles(feed)
        
    def _download_articles(self, feed):
        filter = self.author_filter
        for entry in feed.entries:
            url = entry.link
            logging.info(f"Processing article: \"{entry.title}\"")
            
            try:
                article = np.article(url = url, config = self.npconfig).download().parse()
                authors = article.authors if article.authors else []
                
                if self.author_filter and self.author_filter in authors:  # Changed 'not filter' to 'filter'
                    self._get_fulltext(url)
                    logging.info("Article matched filter")
                elif self.author_filter:   
                    logging.info("Article did not match filter.")
                else:
                    self._get_fulltext(url)  # No filter, process all articles

            except Exception as e:
                logging.error(f"Error processing {url}: {e}")
                
    def _filter_articles(self, article:np.Article):
        '''
        Docstring for _filter_articles
        
        :param self: Description
        :param article: Article object
        :type article: np.Article
        '''
        authors = article.authors if article.authors else []
        logging.debug(f"Filtering authors: {authors}")
        if self.author_filter in authors:
            return True
        else:
            return False
        
    def _get_fulltext(self, url:str):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(url)
                time.sleep(1) # Allow the javascript to render
                content = page.content()
                browser.close()

            logging.info(f"Downloading article from {url}")
            article = np.article(url = url, input_html=content, language='en', config=self.npconfig)
            self._generate_site(article)

        except Exception as e:
            logging.error(f"Error downloading {url}: {e}")

    def _generate_site(self, article:np.Article):
        template_dir = self.template_dir

        # Create the Jinja environment and specify the loader
        template = Environment(loader=FileSystemLoader(template_dir)).get_template("article.html")

        data = {
            "text": article.text,
            "html": article.article_html,
            "author": article.authors,
            "date": article.publish_date
        }
        try:
            html = template.render(data)
            self._create_file(article, html)
            logging.info("HTML rendered")
        except Exception as e:
            logging.error(f"Error generating page {article.url}: {e}")
        
    def _create_file(self, article:np.Article, html:str):
        def _slugify(text: str) -> str:
            text = unicodedata.normalize("NFKD", text)
            text = text.encode("ascii", "ignore").decode("ascii")
            text = re.sub(r"[^\w\s-]", "", text).strip().lower()
            slug = re.sub(r"[-\s]+", "_", text)
            return slug or "article"

        filename = _slugify(article.title) + ".html"
        file_path = os.path.join(self.output_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        logging.info(f"Saved article: {filename}")