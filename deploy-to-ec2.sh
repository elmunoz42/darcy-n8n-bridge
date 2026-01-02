#!/bin/bash
# n8n MCP Bridge Deployment Script for Same-Server Setup
# Run this on your EC2 instance where n8n is already running

set -e  # Exit on error

echo "=========================================="
echo "n8n MCP Bridge Deployment Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Check if n8n is running
echo -e "${YELLOW}Step 1: Checking n8n status...${NC}"
if systemctl is-active --quiet n8n 2>/dev/null; then
    echo -e "${GREEN}✓ n8n is running${NC}"
elif pgrep -f n8n > /dev/null; then
    echo -e "${GREEN}✓ n8n process found${NC}"
else
    echo -e "${RED}✗ Warning: n8n doesn't appear to be running${NC}"
    echo "Please start n8n before continuing"
    read -p "Press enter to continue anyway, or Ctrl+C to exit..."
fi

# Check n8n port
echo ""
echo -e "${YELLOW}Checking n8n port...${NC}"
N8N_PORT=$(sudo netstat -tulpn 2>/dev/null | grep n8n | grep -oP ':\K[0-9]+' | head -1)
if [ -z "$N8N_PORT" ]; then
    N8N_PORT=5678
    echo -e "${YELLOW}Using default port: ${N8N_PORT}${NC}"
else
    echo -e "${GREEN}✓ n8n is running on port: ${N8N_PORT}${NC}"
fi

# Step 2: Test n8n API
echo ""
echo -e "${YELLOW}Step 2: Testing n8n API...${NC}"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:${N8N_PORT}/api/v1/workflows | grep -q "200\|401"; then
    echo -e "${GREEN}✓ n8n API is accessible${NC}"
else
    echo -e "${RED}✗ Warning: n8n API may not be accessible${NC}"
    echo "This could be normal - some n8n setups require authentication"
fi

# Step 3: Clone repository
echo ""
echo -e "${YELLOW}Step 3: Cloning n8n-mcp repository...${NC}"
cd ~
if [ -d "n8n-mcp" ]; then
    echo -e "${YELLOW}Directory n8n-mcp already exists. Updating...${NC}"
    cd n8n-mcp
    git pull origin master || git pull origin main
else
    # You'll need to update this with your actual repo URL
    echo -e "${RED}Please enter your repository URL:${NC}"
    read -p "Repository URL: " REPO_URL
    git clone "$REPO_URL" n8n-mcp
    cd n8n-mcp
fi

# Step 4: Create virtual environment
echo ""
echo -e "${YELLOW}Step 4: Creating virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists${NC}"
else
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Step 5: Install dependencies
echo ""
echo -e "${YELLOW}Step 5: Installing dependencies...${NC}"
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Step 6: Configure environment
echo ""
echo -e "${YELLOW}Step 6: Configuring environment...${NC}"

if [ -f ".env" ]; then
    echo -e "${YELLOW}.env file already exists${NC}"
    read -p "Do you want to reconfigure it? (y/n): " RECONFIG
    if [ "$RECONFIG" != "y" ]; then
        echo "Skipping environment configuration"
    else
        rm .env
    fi
fi

if [ ! -f ".env" ]; then
    # Generate MCP API key
    echo ""
    echo -e "${GREEN}Generating MCP API key...${NC}"
    MCP_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo -e "${GREEN}Generated MCP_API_KEY: ${MCP_KEY}${NC}"
    echo -e "${YELLOW}SAVE THIS KEY! You'll need it for DarcyIQ configuration.${NC}"

    # Get n8n API key
    echo ""
    echo -e "${YELLOW}Please enter your n8n API key:${NC}"
    echo "To get this:"
    echo "1. Open n8n in browser (http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:${N8N_PORT})"
    echo "2. Go to Settings → API"
    echo "3. Create API Key"
    read -p "n8n API Key: " N8N_KEY

    # Create .env file
    cat > .env << EOF
# MCP Bridge API Key - REQUIRED
MCP_API_KEY=${MCP_KEY}

# n8n Instance Configuration - LOCALHOST (same server)
N8N_BASE_URL=http://localhost:${N8N_PORT}
N8N_API_KEY=${N8N_KEY}

# Optional: restrict workflows that can be used through this bridge
# N8N_WORKFLOW_ALLOWLIST=123,456

# Optional: tune outbound request timeout in seconds (default is 10)
# HTTP_TIMEOUT_SECONDS=10
EOF

    chmod 600 .env
    echo -e "${GREEN}✓ .env file created and secured${NC}"

    # Save MCP key to a backup file
    echo "$MCP_KEY" > ~/mcp_api_key_backup.txt
    chmod 600 ~/mcp_api_key_backup.txt
    echo -e "${GREEN}✓ MCP API key backed up to ~/mcp_api_key_backup.txt${NC}"
fi

# Step 7: Test the bridge
echo ""
echo -e "${YELLOW}Step 7: Testing the bridge...${NC}"
echo "Starting test server on port 8080..."
echo "Press Ctrl+C after seeing startup messages (we'll test in background)"

# Start in background for testing
uvicorn app.main:app --host 0.0.0.0 --port 8080 > /tmp/n8n-mcp-test.log 2>&1 &
TEST_PID=$!

sleep 3

# Test health endpoint
echo ""
echo -e "${YELLOW}Testing health endpoint...${NC}"
if curl -s http://localhost:8080/health | grep -q "healthy"; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${RED}✗ Health check failed${NC}"
    echo "Check logs at /tmp/n8n-mcp-test.log"
fi

# Kill test server
kill $TEST_PID 2>/dev/null || true
sleep 1

# Step 8: Create systemd service
echo ""
echo -e "${YELLOW}Step 8: Creating systemd service...${NC}"

sudo tee /etc/systemd/system/n8n-mcp-bridge.service > /dev/null << EOF
[Unit]
Description=n8n MCP Bridge
After=network.target n8n.service
Requires=n8n.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/n8n-mcp
Environment="PATH=/home/ubuntu/n8n-mcp/.venv/bin"
EnvironmentFile=/home/ubuntu/n8n-mcp/.env
ExecStart=/home/ubuntu/n8n-mcp/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}✓ Systemd service created${NC}"

# Step 9: Enable and start service
echo ""
echo -e "${YELLOW}Step 9: Starting n8n-mcp-bridge service...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable n8n-mcp-bridge.service
sudo systemctl start n8n-mcp-bridge.service

sleep 2

# Check service status
if systemctl is-active --quiet n8n-mcp-bridge; then
    echo -e "${GREEN}✓ Service is running!${NC}"
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u n8n-mcp-bridge.service -n 50"
fi

# Step 10: Final instructions
echo ""
echo "=========================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. Configure Security Group:"
echo "   - Go to EC2 Console → Security Groups"
echo "   - Add inbound rule for port 8080 (Custom TCP)"
echo ""
echo "2. Test from outside:"
echo "   curl http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:8080/health"
echo ""
echo "3. Configure DarcyIQ:"
echo "   - URL: http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:8080/"
echo "   - Header: X-API-Key"
echo "   - Token: (see ~/mcp_api_key_backup.txt)"
echo ""
echo "4. View logs:"
echo "   sudo journalctl -u n8n-mcp-bridge.service -f"
echo ""
echo -e "${GREEN}Your MCP API Key (save this!): ${NC}"
if [ -f ~/mcp_api_key_backup.txt ]; then
    cat ~/mcp_api_key_backup.txt
fi
echo ""
echo "=========================================="
