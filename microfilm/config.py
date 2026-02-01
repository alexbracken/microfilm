import newspaper as np
from pathlib import Path

class Config:
    
    # RSS feed URL to monitor
    rss: str = "http://rss.cnn.com/rss/cnn_topstories.rss"
    
    # Enable watch mode (continuous feed monitoring)
    watch: bool = True
    
    max_articles: int = 10
    
    # Filter articles by author name/byline
    author_filter: str = ""
    
    # How often to check the feed in seconds
    # Example: 3600 (1 hour), 1800 (30 minutes)
    update_frequency: int = 1800
    
    # Output directory for generated HTML files (relative to project root)
    output_dir = "site"
    
    output_formats: list = ["html", "json"]
    
    # Template directory for Jinja2 templates (relative to project root)
    template_dir = "templates"
    
    # np config
    np_config = np.Config()

    
    MODULE_ROOT = Path(__file__).resolve().parent
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    output_dir = Path.joinpath(PROJECT_ROOT, output_dir)
    Path.mkdir(output_dir, parents=True, exist_ok=True)
    
    template_dir = Path.joinpath(PROJECT_ROOT, template_dir)
    Path.mkdir(template_dir, parents=True, exist_ok=True)