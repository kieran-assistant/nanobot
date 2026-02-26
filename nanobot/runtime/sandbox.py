# nanobot/runtime/sandbox.py
import asyncio
import json
import resource
from typing import Dict, Any
from loguru import logger

class Sandbox:
    @staticmethod
    def _set_limits():
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (100 * 1024 * 1024, 100 * 1024 * 1024))

    async def execute_script(self, script_path: str, args: Dict[str, Any]) -> Dict:
        cmd = ["python3", script_path]
        
        payload = json.dumps({"args": args}).encode('utf-8')
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._set_limits
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=payload),
                timeout=10.0
            )
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8')
                logger.error(f"Sandbox Error [{script_path}]: {error_msg}")
                return {"success": False, "error": error_msg}
            
            result = json.loads(stdout.decode('utf-8'))
            return {"success": True, "data": result}

        except asyncio.TimeoutError:
            return {"success": False, "error": "Execution timed out (10s)"}
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON output from script"}
        except Exception as e:
            return {"success": False, "error": str(e)}

sandbox = Sandbox()
