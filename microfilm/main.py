import microfilm
import logging

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.INFO
    )
    logging.info("Initializing Microfilm with config.")
    
    app = microfilm.Microfilm()
    
    if app.watch:
        app.watch_feed()

if __name__ == "__main__":
    main()