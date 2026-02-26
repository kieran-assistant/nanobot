# nanobot/meta/staging_manager.py
import shutil
import subprocess
import uuid
import inspect
from pathlib import Path
from nanobot.meta.schemas import SkillDefinition
from nanobot.meta.factory import factory
from loguru import logger

class StagingManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent

    async def propose_skill(self, skill_def: SkillDefinition, pre_promote_check=None):
        staging_id = f"stage_{uuid.uuid4().hex[:8]}"
        staging_path = self.project_root / "temp_staging" / staging_id

        logger.info(f"Starting Staging Environment: {staging_id}")

        try:
            staging_path.mkdir(parents=True, exist_ok=True)

            factory.generate_skill_module(skill_def, staging_path)

            passed = await self._syntax_check(staging_path)

            if passed:
                target_path = self.project_root / "nanobot" / "skills" / skill_def.name
                target_parent = target_path.parent
                generated_skill_path = staging_path / skill_def.name
                temp_deploy_path = target_parent / f".{skill_def.name}.new_{staging_id}"
                backup_path = target_parent / f".{skill_def.name}.bak_{staging_id}"

                if not generated_skill_path.exists():
                    raise FileNotFoundError(f"Generated skill path not found: {generated_skill_path}")

                if pre_promote_check is not None:
                    gate_result = pre_promote_check(generated_skill_path)
                    gate = await gate_result if inspect.isawaitable(gate_result) else gate_result
                    if not gate.get("passed", False):
                        reason = "; ".join(gate.get("reasons", [])) or "Pre-promote security gate failed"
                        return {"status": "failed", "reason": reason}

                target_parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(generated_skill_path), str(temp_deploy_path))

                replaced_existing = False
                try:
                    if target_path.exists():
                        target_path.rename(backup_path)
                        replaced_existing = True
                    temp_deploy_path.rename(target_path)
                except Exception:
                    # Best-effort rollback if promotion fails after backup.
                    if replaced_existing and backup_path.exists() and not target_path.exists():
                        backup_path.rename(target_path)
                    raise
                finally:
                    if backup_path.exists():
                        shutil.rmtree(backup_path)

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
