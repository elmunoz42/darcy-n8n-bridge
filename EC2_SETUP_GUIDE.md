# EC2 Setup Guide for n8n MCP Bridge

Complete step-by-step guide for deploying the n8n MCP Bridge on AWS EC2.

---

## Prerequisites
- EC2 instance running (Ubuntu 22.04 LTS recommended)
- Security group with ports 22 (SSH), 80 (HTTP), 443 (HTTPS), and 8080 (MCP Bridge) open
- SSH access to EC2 instance
- GitHub account with access to the repository
- n8n instance with API access and API key

---

## Step 1: Connect to EC2 Instance
```bash
ssh -i your-key.pem ubuntu@your-ec2-public-ip
```

---

## Step 2: Update System & Install Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

---

## Step 3: Configure SSH Key for GitHub

### Generate SSH Key
```bash
cd ~/.ssh
ssh-keygen -t ed25519 -C "your_email@example.com" -f id_n8n_mcp_gh
```
Press Enter twice for no passphrase (or set one if you prefer security).

### Set Correct Permissions
```bash
chmod 700 id_n8n_mcp_gh
chmod 644 id_n8n_mcp_gh.pub
```

### Display Public Key
```bash
cat id_n8n_mcp_gh.pub
```
Copy the entire output starting with `ssh-ed25519`.

### Add SSH Key to GitHub
1. Go to: https://github.com/settings/keys
2. Click **"New SSH key"**
3. Title: `EC2 n8n MCP Bridge`
4. Key type: `Authentication Key`
5. Paste your public key
6. Click **"Add SSH key"**

### Start SSH Agent & Add Key
```bash
eval "$(ssh-agent -s)"
ssh-add id_n8n_mcp_gh
```

### Test GitHub Connection
```bash
ssh -T git@github.com
```
You should see: `Hi username! You've successfully authenticated, but GitHub does not provide shell access.`

---

## Step 4: Clone Repository
```bash
cd ~
git clone git@github.com:your-username/n8n-mcp.git
cd n8n-mcp
```

---

## Step 5: Create Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## Step 6: Install Requirements
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 7: Configure Environment Variables

### Generate Strong MCP Auth Token
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
Copy this token and paste it as your `MCP_API_KEY`.

**IMPORTANT:** Save this token somewhere secure - you'll need it for DarcyIQ configuration!

### Create .env File
```bash
cp .env.example .env
nano .env
```

Edit the file with these values:
```bash
# MCP Bridge API Key - REQUIRED
MCP_API_KEY=your_generated_token_here

# n8n Instance Configuration
N8N_BASE_URL=https://your-n8n-instance.com
N8N_API_KEY=your_n8n_api_key_here

# Optional: restrict workflows that can be used through this bridge
# N8N_WORKFLOW_ALLOWLIST=123,456

# Optional: tune outbound request timeout in seconds (default is 10)
# HTTP_TIMEOUT_SECONDS=10
```

Save and exit: `Ctrl+X`, then `Y`, then `Enter`

### Get n8n API Key
1. Log into your n8n instance
2. Go to **Settings** → **API**
3. Click **Create API Key**
4. Copy the generated key
5. Paste into `.env` file as `N8N_API_KEY`

---

## Step 8: Run Pre-flight Tests (Optional)
```bash
pytest tests/ -v
```
Verify all tests pass.

---

## Step 9: Test Server Manually
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```
You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8080
```

In another terminal (or use `curl` from your local machine):
```bash
# From EC2
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }'
```

Expected response should include:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {...}
}
```

Press `Ctrl+C` to stop the server.

---

## Step 10: Create Systemd Service (Auto-start on Boot)
```bash
sudo nano /etc/systemd/system/n8n-mcp-bridge.service
```

Paste this configuration:
```ini
[Unit]
Description=n8n MCP Bridge
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/n8n-mcp
EnvironmentFile=/home/ubuntu/n8n-mcp/.env
Environment="PATH=/home/ubuntu/n8n-mcp/.venv/bin"
ExecStart=/home/ubuntu/n8n-mcp/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Save and exit: `Ctrl+X`, then `Y`, then `Enter`

### Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable n8n-mcp-bridge.service
sudo systemctl start n8n-mcp-bridge.service
```

### Check Service Status
```bash
sudo systemctl status n8n-mcp-bridge.service
```
Should show: `Active: active (running)`

---

## Step 11: Configure Security Group & Firewall

### Configure EC2 Security Group (AWS Console)

**IMPORTANT:** Before testing from outside the EC2 instance, you must configure the Security Group:

1. Go to **EC2 Dashboard** → **Security Groups**
2. Select the security group attached to your EC2 instance
3. Click **Edit inbound rules**
4. Click **Add rule**
5. Configure the new rule:
   - **Type**: Custom TCP
   - **Port range**: 8080
   - **Source**:
     - `0.0.0.0/0` (allow from anywhere - for testing)
     - Or `your-ip-address/32` (recommended for production - restrict to your IP)
   - **Description**: n8n MCP Bridge
6. Click **Save rules**

### Configure UFW Firewall (On EC2 Instance)

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8080/tcp  # MCP Bridge
sudo ufw enable
sudo ufw status
```

---

## Step 12: Configure SSH Agent to Persist (Optional)

This ensures the SSH key is loaded automatically on login:

```bash
nano ~/.bashrc
```

Add at the end:
```bash
# Start SSH agent and add GitHub key
if [ -z "$SSH_AUTH_SOCK" ]; then
    eval "$(ssh-agent -s)" > /dev/null
    ssh-add ~/.ssh/id_n8n_mcp_gh 2>/dev/null
fi
```

Save and apply:
```bash
source ~/.bashrc
```

---

## Step 13: Verify Deployment

### Check Service Status
```bash
sudo systemctl status n8n-mcp-bridge.service
```

### View Real-time Logs
```bash
sudo journalctl -u n8n-mcp-bridge.service -f
```
Press `Ctrl+C` to exit.

### Test Health Check
```bash
# Health check (no auth required)
curl http://your-ec2-public-ip:8080/health

# Service info (no auth required)
curl http://your-ec2-public-ip:8080/
```

### Test Initialize Endpoint
```bash
# From your local machine
curl -X POST http://your-ec2-public-ip:8080/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }'
```

### Test Tools List Endpoint
```bash
curl -X POST http://your-ec2-public-ip:8080/ \
  -H "Content-Type: application/json" \
  -H "api_key: YOUR_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

### Test n8n Workflow Listing
```bash
curl -X POST http://your-ec2-public-ip:8080/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "n8n_list_workflows",
      "arguments": {
        "limit": 10
      }
    }
  }'
```

---

## Step 14: Configure DarcyIQ Integration

In DarcyIQ settings, add your MCP server:

**Server Configuration:**
- Name: `n8n Workflow Manager`
- URL: `http://your-ec2-public-ip:8080/`
- Auth Type: `API Key`
- Auth Header: `X-API-Key` or `api_key`
- Auth Token: `YOUR_MCP_API_KEY` (from `.env` file)

**Available Tools:**
1. `n8n_list_workflows` - List n8n workflows with pagination
2. `n8n_get_workflow` - Get specific workflow by ID
3. `n8n_run_workflow` - Execute a workflow with optional payload
4. `n8n_list_executions` - List workflow executions
5. `n8n_get_execution` - Get execution details by ID
6. `darcy_tracking_list` - List executions started through this bridge

**Security Features:**
- CORS protection (restricts origins to DarcyIQ domains)
- Rate limiting (60 requests/minute per IP)
- API key authentication
- Health check endpoint for monitoring

---

## Optional: Setup Nginx Reverse Proxy + HTTPS

If you have a domain name and want HTTPS:

### Install Nginx
```bash
sudo apt install nginx -y
```

### Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/n8n-mcp-bridge
```

Paste:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Preserve API key headers
        proxy_pass_request_headers on;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/n8n-mcp-bridge /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Setup SSL with Let's Encrypt
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

Follow prompts. Certbot will auto-configure HTTPS.

Update firewall:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

---

## Maintenance Commands

### View Logs
```bash
# Real-time logs
sudo journalctl -u n8n-mcp-bridge.service -f

# Last 100 lines
sudo journalctl -u n8n-mcp-bridge.service -n 100

# Since specific time
sudo journalctl -u n8n-mcp-bridge.service --since "1 hour ago"
```

### Restart Service
```bash
sudo systemctl restart n8n-mcp-bridge.service
```

### Stop Service
```bash
sudo systemctl stop n8n-mcp-bridge.service
```

### Update Application
```bash
cd ~/n8n-mcp
git pull origin master
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart n8n-mcp-bridge.service
```

### Check Server Resources
```bash
# CPU and memory
htop

# Disk usage
df -h

# Network connections
sudo netstat -tulpn | grep :8080
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
sudo journalctl -u n8n-mcp-bridge.service -n 50

# Test manually
cd ~/n8n-mcp
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Git Authentication Fails
```bash
# Test connection
ssh -T git@github.com

# If fails, restart SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_n8n_mcp_gh
```

### Port Already in Use
```bash
# Find process using port 8080
sudo lsof -i :8080

# Kill process (replace <PID> with actual PID)
sudo kill -9 <PID>
```

### Can't Access Server from Outside
- Check EC2 Security Group allows inbound traffic on port 8080
- Verify firewall: `sudo ufw status`
- Test locally first: `curl http://localhost:8080/`

### Import Errors
```bash
# Reinstall requirements
cd ~/n8n-mcp
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### Environment Variables Not Loading
```bash
# Check .env file exists
cat ~/n8n-mcp/.env

# Verify permissions
chmod 600 ~/n8n-mcp/.env

# Restart service
sudo systemctl restart n8n-mcp-bridge.service
```

### n8n API Connection Fails
```bash
# Test n8n connectivity from EC2
curl -H "X-N8N-API-KEY: your_n8n_api_key" \
  https://your-n8n-instance.com/api/v1/workflows
```

Common issues:
- Wrong `N8N_BASE_URL` (ensure no trailing slash)
- Invalid `N8N_API_KEY`
- n8n instance not accessible from EC2
- Firewall blocking outbound connections

### Authentication Fails (401 Unauthorized)
- Verify `MCP_API_KEY` is set in `.env`
- Ensure you're sending either `X-API-Key` or `api_key` header
- Check that the header value matches exactly (no extra spaces)

### Workflow Missing Trigger Error
- n8n workflows must have a trigger node to be executed via API
- Add a manual trigger or webhook trigger to the workflow
- Or run the workflow manually from within n8n UI

---

## Security Checklist

### Quick Security Check

- [ ] `MCP_API_KEY` set in `.env` with strong random value
- [ ] `N8N_API_KEY` properly secured
- [ ] `.env` file permissions set to 600 (owner read/write only)
- [ ] Firewall (UFW) enabled with only necessary ports open
- [ ] SSH key authentication configured (no password login)
- [ ] Systemd service running as non-root user (ubuntu)
- [ ] Regular system updates scheduled
- [ ] Logs monitored for suspicious activity
- [ ] HTTPS enabled (if using domain name)
- [ ] Backup strategy in place for `.env` and configuration
- [ ] `N8N_WORKFLOW_ALLOWLIST` configured (optional, for restricting access)

### Advanced Security (Optional)

1. **Add CORS middleware** (if web clients will connect)
2. **Add rate limiting** (slowapi) - prevents abuse
3. **Add health check endpoint** - for monitoring
4. **Configure fail2ban** - protects against brute force
5. **Enable CloudWatch** - AWS monitoring and alerts

---

## Production Checklist

- [ ] EC2 instance provisioned and accessible
- [ ] Python 3.11+ installed
- [ ] Repository cloned via SSH
- [ ] Virtual environment created
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` configured with production tokens
- [ ] n8n API key created and tested
- [ ] Tests pass (`pytest`)
- [ ] Server starts manually
- [ ] Systemd service configured and running
- [ ] Firewall configured (UFW)
- [ ] Security group configured (AWS)
- [ ] Initialize endpoint working with auth
- [ ] Tools list endpoint working
- [ ] n8n workflow listing working
- [ ] DarcyIQ integration tested
- [ ] Logging verified
- [ ] Auto-start on boot tested (reboot EC2)
- [ ] Nginx + HTTPS configured (optional)
- [ ] Monitoring set up

---

## Docker Deployment (Alternative)

If you prefer Docker deployment on EC2:

### Install Docker
```bash
sudo apt install docker.io docker-compose -y
sudo usermod -aG docker ubuntu
# Log out and back in for group changes to take effect
```

### Build and Run
```bash
cd ~/n8n-mcp
docker-compose up -d
```

### View Logs
```bash
docker-compose logs -f
```

### Stop Container
```bash
docker-compose down
```

### Update Application
```bash
cd ~/n8n-mcp
git pull origin master
docker-compose down
docker-compose up -d --build
```

---

## Quick Reference

### Important File Locations
- Application: `~/n8n-mcp/`
- Virtual Environment: `~/n8n-mcp/.venv/`
- Environment Config: `~/n8n-mcp/.env`
- Service File: `/etc/systemd/system/n8n-mcp-bridge.service`
- Nginx Config: `/etc/nginx/sites-available/n8n-mcp-bridge`
- SSH Key: `~/.ssh/id_n8n_mcp_gh`

### Essential Commands
```bash
# Service management
sudo systemctl status n8n-mcp-bridge.service
sudo systemctl restart n8n-mcp-bridge.service
sudo journalctl -u n8n-mcp-bridge.service -f

# Git operations
cd ~/n8n-mcp
git pull origin master

# Activate virtual environment
source ~/n8n-mcp/.venv/bin/activate
```

---

## Support Resources

- **README:** See [README.md](README.md) for detailed feature documentation
- **Implementation Review:** See [IMPLEMENTATION_REVIEW.md](IMPLEMENTATION_REVIEW.md) for code analysis
- **Test Logs:** Check pytest output
- **Service Logs:** `sudo journalctl -u n8n-mcp-bridge.service`
- **n8n Documentation:** https://docs.n8n.io/api/

---

**Last Updated:** January 2, 2026
