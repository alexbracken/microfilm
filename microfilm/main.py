import microfilm
from config import Config
import logging
import time

logger = logging.getLogger(__name__)
config = Config()

def main():
    logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.INFO
    )
    logging.info("Initializing Microfilm with config.")
    
    app = microfilm.Microfilm()
    
    while config.watch:
        logging.info("Starting watch mode. Press Ctrl+C to exit.")
        try:
            app.watch()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            break
        except KeyboardInterrupt:
            logging.info('Manual break by user')

        logging.info(f"Sleeping for {config.update_frequency} seconds")
        time.sleep(config.update_frequency)

if __name__ == "__main__":
    main()