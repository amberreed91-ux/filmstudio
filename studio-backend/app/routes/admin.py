import os
import signal
import subprocess
import sys

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/f51/studio/admin", tags=["admin"])

ADMIN_TOKEN = "studio-restart-2026"


@router.post("/restart")
async def restart_server(x_admin_token: str = Header(...)):
    """Restart the backend server. Protected by X-Admin-Token header."""
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--reload", "--host", "0.0.0.0", "--port", "8010",
        "--log-level", "info",
    ]
    subprocess.Popen(cmd, cwd=os.getcwd())

    # Release the current process so the new one can bind the port
    os.kill(os.getpid(), signal.SIGTERM)

    return {"message": "Restarting server"}
