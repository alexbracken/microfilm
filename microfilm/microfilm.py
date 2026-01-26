from config import Config

import newspaper as np
import feedparser
from playwright.sync_api import sync_playwright
from jinja2 import Environment, FileSystemLoader

import time
import logging
import re
import unicodedata
from pathlib import Path


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
            if feed.status == 304:
                logging.info("Feed has not been updated")
                return None
            if feed.status == 200:
                logging.info("Feed has been updated")
                if hasattr(feed, "etag"):
                    self.etag = feed.etag
                if hasattr(feed, "modified"):
                    self.modified = feed.modified
                else:
                    pass
                return feed
        return None

class ArticleDownloader():
    def __init__(self):
        self.npconfig = np.Config()
        self.config = Config()
        
    def download(self, feed):
        config = self.config
        author_filter = config.author_filter
        articles = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch()
            
            count = 0
            for entry in feed.entries:
                if count >= config.max_articles:
                    break
                    
                url = entry.link
                try:
                    logging.info(f"Processing article ({count}/{config.max_articles}): \"{entry.title}\"")
                    article = np.article(url = url, config = config.np_config).download().parse()
                except np.ArticleException as e: 
                    logging.error(f"Error downloading article {url}: {e}")
                    continue

                if self._filter(article):
                    # Fetch fulltext if needed
                    if article.text is None or article.text == "":
                        page = browser.new_page()
                        page.goto(url)
                        time.sleep(1)
                        content = page.content()
                        article = np.article(url=url, input_html=content, language='en', config=self.npconfig)
                        page.close()
                    
                    articles.append(article)
                    count += 1
            
            browser.close()

        return articles
        
    def _filter(self, article:np.Article):
        '''
        Docstring for _filter
        
        :param article: Article object to filter
        :type article: np.Article
        '''
        filter = self.config.author_filter
        
        if filter and filter in article.authors:
            logging.info("Article matched filter")
            return True
        elif config.author_filter:   
            logging.info("Article did not match filter.")
            return False
        else:
            return True
        

            
class Typeset():
    def generator(self, articles:list[np.Article]):
        # Create the Jinja environment and specify the loader
        loader = FileSystemLoader(config.template_dir)
        template = Environment(loader = loader).get_template("article.html")
        
        for article in articles:
            try:
                data = {
                    "text": article.text,
                    "html": article.article_html,
                    "author": article.authors,
                    "date": article.publish_date
                }
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
        file_path = Path.joinpath(Path(config.output_dir), filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        logging.info(f"Saved article: {filename}")