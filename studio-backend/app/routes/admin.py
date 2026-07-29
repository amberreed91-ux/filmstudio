import os
import signal
import subprocess
import sys

from fastapi import APIRouter, Header, HTTPException

from app.config import settings

router = APIRouter(prefix="/api/f51/studio/admin", tags=["admin"])


def _get_admin_token() -> str:
    return settings.admin_token


@router.post("/restart")
async def restart_server(x_admin_token: str = Header(...)):
    """Restart the backend server. Protected by X-Admin-Token header."""
    token = _get_admin_token()
    if not token:
        raise HTTPException(status_code=404, detail="Admin endpoints disabled")
    if x_admin_token != token:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--reload", "--host", "0.0.0.0", "--port", "8010",
        "--log-level", "info",
    ]
    subprocess.Popen(cmd, cwd=os.getcwd())

    os.kill(os.getpid(), signal.SIGTERM)

    return {"message": "Restarting server"}
