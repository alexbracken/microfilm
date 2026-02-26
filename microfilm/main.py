import microfilm
import typer
import config

import logging
import time

logger = logging.getLogger(__name__)


app = typer.Typer(no_args_is_help=True)
micro = microfilm.Microfilm()
cfg = config.load_config()

logging.basicConfig(
format='[%(levelname)s] %(message)s',
level=logging.INFO
)


@app.command()
def watch():
    '''
    Watch RSS feed for changes and generate site
    '''
    try:
        micro.generate()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    except KeyboardInterrupt:
        logging.info('Manual break by user')

    logging.info(f"Sleeping for {cfg.update_frequency} seconds")
    time.sleep(cfg.update_frequency)
    
@app.command()
def scrape():
    '''
    Scrape RSS feed and generate files
    '''
    try:
        micro.generate()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    except KeyboardInterrupt:
        logging.info('Manual break by user')
        
@app.command()
def build():
    '''
    Build static site from existing articles
    '''
    try: 
        micro.regenerate()
    except:
        print("Something went wrong")
        
@app.command()
def download(f: str):
    try:
        micro.download_articles(f)
    except:
        pass #TODO add exceptions
if __name__ == "__main__":
    app()