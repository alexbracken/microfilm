from newspaper import Config as NewspaperConfig
from pathlib import Path
import yaml
from dataclasses import dataclass

@dataclass
class Config:
    rss: str
    mode: str
    max_articles: int
    author_filter: str
    update_frequency: int
    formats: list[str]
    output_directory: Path
    template_directory: Path
    newspaper: NewspaperConfig

# Define module and project roots
MODULE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_config(config_path='config.yaml') -> Config:
    try:
        with open(config_path, 'r') as file:
            data = yaml.safe_load(file)
            
        # Convert directory strings to paths
        data['output_directory'] = Path.joinpath(PROJECT_ROOT, data['output_directory'])
        data['template_directory'] = Path.joinpath(PROJECT_ROOT, data['template_directory'])
        
        # Add newspaper config
        data['newspaper'] = NewspaperConfig()
        
        config = Config(**data)
        return config

    except FileNotFoundError:
        print(f"Error: Config file not found at {config_path}")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return None

if __name__ == "__main__":
    config = load_config()
