import microfilm
import config
import logging
import time

logger = logging.getLogger(__name__)
cfg = config.load_config()

def main():
    logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.INFO
    )
    logging.info("Initializing Microfilm with config.")
    
    app = microfilm.Microfilm()
    
    while cfg.mode == "watch":
        logging.info("Starting watch mode. Press Ctrl+C to exit.")
        try:
            app.generate()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            break
        except KeyboardInterrupt:
            logging.info('Manual break by user')
            break

        logging.info(f"Sleeping for {cfg.update_frequency} seconds")
        time.sleep(cfg.update_frequency)

    while cfg.mode == "cron":
        try:
            app.generate()
            break
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            break
        except KeyboardInterrupt:
            logging.info('Manual break by user')
            break

if __name__ == "__main__":
    main()