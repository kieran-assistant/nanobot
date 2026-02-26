# nanobot/meta/factory.py
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from nanobot.meta.schemas import ToolDefinition, SkillDefinition
from loguru import logger

class CodeFactory:
    def __init__(self):
        self.template_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(loader=FileSystemLoader(self.template_dir))

    def generate_tool_script(self, tool_def: ToolDefinition, output_dir: Path) -> Path:
        template = self.env.get_template("tool_template.py.j2")
        
        content = template.render(tool=tool_def)
        
        output_file = output_dir / f"tool_{tool_def.name}.py"
        output_file.write_text(content)
        
        logger.info(f"Generated tool script: {output_file}")
        return output_file

    def generate_skill_module(self, skill_def: SkillDefinition, output_dir: Path):
        module_dir = output_dir / skill_def.name
        module_dir.mkdir(parents=True, exist_ok=True)
        
        (module_dir / "__init__.py").touch()
        
        for tool in skill_def.tools:
            self.generate_tool_script(tool, module_dir)
            
        logger.success(f"Generated skill module '{skill_def.name}' at {module_dir}")

factory = CodeFactory()
