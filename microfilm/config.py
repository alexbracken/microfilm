from newspaper import Config as NewspaperConfig
from pathlib import Path
import yaml
from dataclasses import dataclass, field
import logging

@dataclass
class Config:
    rss: str
    author_filter: str
    update_frequency: int
    formats: list[str]
    output_directory: Path
    template_directory: Path
    timeout: int
    thread_count: int = 4
    newspaper: NewspaperConfig = field(default_factory=lambda: NewspaperConfig())
    playwright_retry_attempts: int = 2
    playwright_wait_strategy: str = "networkidle"

# Define module and project roots
MODULE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent
config_path = Path.joinpath(PROJECT_ROOT, 'config.yaml')

def load_config() -> Config:
    try:
        with open(config_path, 'r') as file:
            data = yaml.safe_load(file) or {}

        # Convert directory strings to paths
        data['output_directory'] = Path.joinpath(PROJECT_ROOT, data.get('output_directory', 'site'))
        data['template_directory'] = Path.joinpath(PROJECT_ROOT, data.get('template_directory', 'templates'))

        config = Config(**{
            'rss': data.get('rss', ''),
            'author_filter': data.get('author_filter', ''),
            'update_frequency': data.get('update_frequency', 1800),
            'formats': data.get('formats', ['html', 'json']),
            'output_directory': data['output_directory'],
            'template_directory': data['template_directory'],
            'timeout': data.get('timeout', 2000),
            'thread_count': data.get('thread_count', 4),
            'playwright_retry_attempts': data.get('playwright_retry_attempts', 2),
            'playwright_wait_strategy': data.get('playwright_wait_strategy', 'networkidle'),
            'newspaper': NewspaperConfig()
        })
        return config

    except FileNotFoundError:
        logging.error(f"Config file not found at {config_path}")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file: {e}")
        raise