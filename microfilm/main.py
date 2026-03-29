import logging
logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.DEBUG
)

import microfilm
import typer
import config

import time

logger = logging.getLogger(__name__)


app = typer.Typer(no_args_is_help=True)
micro = microfilm.Microfilm()
cfg = config.load_config()

# Validate playwright installation if needed
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        browser.close()
    logging.debug("Playwright validation: chromium binaries available")
except ImportError:
    logging.error(
        "Playwright is not installed. Install it with:\n"
        "  pip install playwright\n"
        "Then install browser binaries with:\n"
        "  playwright install chromium"
    )
    raise
except Exception as e:
    logging.error(f"Playwright validation failed: {type(e).__name__}: {e}\nFix with: playwright install chromium")
    raise


@app.command()
def watch():
    '''
    Watch RSS feed for changes and generate site
    '''
    try:
        while True:
            try:
                micro.generate()
            except Exception as e:
                logging.error(f"Error in watch cycle: {type(e).__name__}: {e}", exc_info=True)
            logging.info(f"Sleeping for {cfg.update_frequency} seconds")
            time.sleep(cfg.update_frequency)
    except KeyboardInterrupt:
        logging.info('Manual break by user')
    
@app.command()
def scrape():
    '''
    Scrape RSS feed and generate files
    '''
    try:
        micro.generate()
    except Exception as e:
        logging.error(f"Scrape failed: {type(e).__name__}: {e}", exc_info=True)
    except KeyboardInterrupt:
        logging.info('Manual break by user')
        
@app.command()
def build():
    '''
    Build static site from existing articles
    '''
    try:
        micro.regenerate()
    except Exception as e:
        logging.error(f"Build failed: {type(e).__name__}: {e}", exc_info=True)
        
@app.command()
def download(f: str):
    try:
        micro.download_articles(f)
    except Exception as e:
        logging.error(f"Failed to download articles from {f}: {type(e).__name__}: {e}", exc_info=True)
if __name__ == "__main__":
    app()