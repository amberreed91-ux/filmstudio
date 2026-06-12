#!/bin/bash

# AI Film Studio - Backend Quick Start Script
# ===========================================

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI Film Studio - Backend Quick Start${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/studio-backend"

# Check if backend directory exists
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}✗ Backend directory not found: $BACKEND_DIR${NC}"
    exit 1
fi

cd "$BACKEND_DIR"

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
python3 --version
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python OK${NC}\n"

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
    echo -e "${GREEN}✓ Virtual environment activated${NC}\n"
else
    echo -e "${YELLOW}⚠ No virtual environment found${NC}"
    echo -e "${YELLOW}  Consider creating one: python3 -m venv .venv${NC}\n"
fi

# Check dependencies
echo -e "${YELLOW}Checking dependencies...${NC}"
if ! python3 -c "import fastapi, uvicorn, pydantic, aiohttp" 2>/dev/null; then
    echo -e "${RED}✗ Missing dependencies${NC}"
    echo -e "${YELLOW}Installing from requirements.txt...${NC}"
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Failed to install dependencies${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ Dependencies OK${NC}\n"

# Check database
echo -e "${YELLOW}Checking database...${NC}"
if [ ! -f "data/studio.db" ]; then
    echo -e "${YELLOW}⚠ Database not found, will be created on first run${NC}"
else
    echo -e "${GREEN}✓ Database found${NC}"
    # Check database size
    DB_SIZE=$(du -h data/studio.db | cut -f1)
    echo -e "  Database size: $DB_SIZE"
fi
echo ""

# Check .env file
echo -e "${YELLOW}Checking configuration...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}✗ .env file not found${NC}"
    echo -e "${YELLOW}  Create one from .env.example if available${NC}"
else
    echo -e "${GREEN}✓ .env file found${NC}"
    
    # Check Runway API key
    if grep -q "RUNWAYML_API_SECRET=key_" .env 2>/dev/null; then
        echo -e "  ${GREEN}Runway API key configured${NC}"
    else
        echo -e "  ${YELLOW}⚠ Runway API key not configured${NC}"
    fi
fi
echo ""

# Check if port 8010 is available
echo -e "${YELLOW}Checking port 8010...${NC}"
if lsof -Pi :8010 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}✗ Port 8010 is already in use${NC}"
    echo -e "${YELLOW}  Kill the process using: lsof -ti :8010 | xargs kill -9${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Port 8010 is available${NC}"
fi
echo ""

# Start the server
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Starting FastAPI Backend Server...${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "Server will be available at: ${BLUE}http://localhost:8010${NC}"
echo -e "Health check: ${BLUE}http://localhost:8010/health${NC}"
echo -e "API docs: ${BLUE}http://localhost:8010/docs${NC}\n"

echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}\n"

# Start with uvicorn if available, otherwise use python
if command -v uvicorn &> /dev/null; then
    uvicorn main:app --reload --host 0.0.0.0 --port 8010 --log-level info
else
    python3 main.py
fi
