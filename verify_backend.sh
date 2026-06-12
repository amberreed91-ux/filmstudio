#!/bin/bash

# Quick Backend Verification Script
# ==================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================"
echo "Backend Quick Verification"
echo "======================================"
echo ""

# Check if backend is running on port 8010
if lsof -Pi :8010 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is running on port 8010${NC}\n"
    
    # Test health endpoint
    echo "Testing /health endpoint..."
    if command -v curl &> /dev/null; then
        RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/health_response.json http://localhost:8010/health)
        
        if [ "$RESPONSE" = "200" ]; then
            echo -e "${GREEN}✓ Health endpoint responding${NC}"
            
            # Pretty print if jq is available
            if command -v jq &> /dev/null; then
                echo ""
                cat /tmp/health_response.json | jq '.'
            else
                cat /tmp/health_response.json
            fi
            echo ""
        else
            echo -e "${RED}✗ Health endpoint returned status $RESPONSE${NC}"
        fi
        
        rm -f /tmp/health_response.json
    else
        echo -e "${YELLOW}⚠ curl not found, cannot test endpoints${NC}"
    fi
    
    echo ""
    echo "Access the backend at:"
    echo "  Health: http://localhost:8010/health"
    echo "  API Docs: http://localhost:8010/docs"
    echo "  Root: http://localhost:8010/"
    
else
    echo -e "${RED}✗ Backend is NOT running on port 8010${NC}"
    echo ""
    echo "To start the backend:"
    echo "  ./run_backend.sh"
    echo ""
    echo "Or manually:"
    echo "  cd studio-backend"
    echo "  python3 main.py"
fi

echo ""
