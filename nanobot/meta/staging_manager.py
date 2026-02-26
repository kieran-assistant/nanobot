# nanobot/meta/staging_manager.py
import shutil
import subprocess
import uuid
from pathlib import Path
from nanobot.meta.schemas import SkillDefinition
from nanobot.meta.factory import factory
from loguru import logger

class StagingManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent

    async def propose_skill(self, skill_def: SkillDefinition):
        staging_id = f"stage_{uuid.uuid4().hex[:8]}"
        staging_path = self.project_root / "temp_staging" / staging_id
        
        logger.info(f"Starting Staging Environment: {staging_id}")

        try:
            staging_path.mkdir(parents=True, exist_ok=True)
            
            factory.generate_skill_module(skill_def, staging_path)
            
            passed = await self._syntax_check(staging_path)
            
            if passed:
                target_path = self.project_root / "nanobot" / "skills" / skill_def.name
                if target_path.exists():
                    shutil.rmtree(target_path)
                
                shutil.move(str(staging_path), str(target_path))
                logger.success(f"Skill '{skill_def.name}' promoted to Production.")
                return {"status": "deployed", "path": str(target_path)}
            else:
                return {"status": "failed", "reason": "Syntax check failed"}

        except Exception as e:
            logger.error(f"Staging failed: {e}")
            return {"status": "error", "reason": str(e)}
        finally:
            if staging_path.exists():
                shutil.rmtree(staging_path)
                logger.info(f"Cleaned up staging environment: {staging_id}")

    async def _syntax_check(self, path: Path):
        for file in path.rglob("*.py"):
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(file)],
                capture_output=True
            )
            if result.returncode != 0:
                logger.error(f"Syntax error in {file}: {result.stderr.decode()}")
                return False
        return True

staging_manager = StagingManager()
