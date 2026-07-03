"""
Prompt Registry

Central registry for all versioned prompt templates.
Loads from YAML files at application startup. Prompts are code - version them!
"""
import yaml
from pathlib import Path
from typing import Dict
import structlog

logger = structlog.get_logger()


class PromptRegistry:
    """Central registry for all versioned prompt templates."""
    
    _templates: Dict[str, Dict] = {}
    _templates_dir = Path(__file__).parent / "templates"
    
    @classmethod
    def load_all(cls) -> None:
        """Load all prompt templates from disk at startup."""
        count = 0
        for yaml_file in cls._templates_dir.rglob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            key = f"{data['name']}:{data['version']}"
            cls._templates[key] = data
            count += 1
            
        logger.info("Prompt registry loaded", template_count=count)
    
    @classmethod
    def get(cls, name: str, version: str = "latest") -> Dict:
        """Retrieve a prompt template by name and version."""
        if version == "latest":
            matching = [
                (k, v) for k, v in cls._templates.items() 
                if v["name"] == name
            ]
            if not matching:
                raise KeyError(f"No prompt template found with name: {name}")
            # Return the highest version available
            latest = sorted(matching, key=lambda x: x[1]["version"])[-1]
            return latest[1]
        
        key = f"{name}:{version}"
        if key not in cls._templates:
            raise KeyError(f"Prompt template not found: {name} v{version}")
        return cls._templates[key]