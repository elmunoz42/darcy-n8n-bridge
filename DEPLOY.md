# n8n MCP Bridge - Deployment Guide

Complete deployment instructions for production deployment on EC2 or other cloud platforms.

---

## Prerequisites

- Python 3.11+
- Git
- Linux server (Ubuntu 22.04+ recommended)
- Domain name (optional, for HTTPS)
- n8n instance with API access and API key

---

## 1. Server Setup (EC2 or VPS)

### Launch EC2 Instance (AWS)

```bash
# Recommended: t2.micro or t2.small
# OS: Ubuntu 22.04 LTS
# Security Group: Open ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 8080 (MCP Bridge)
```

### Connect to Server

```bash
ssh ubuntu@your-server-ip
```

### Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### Install Python and Dependencies

```bash
sudo apt install python3-pip python3-venv git -y
```

---

## 2. Application Installation

### Clone Repository

```bash
cd /home/ubuntu
git clone <your-repo-url>
cd n8n-mcp
```

### Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Requirements

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Environment Configuration

### Create .env File

```bash
cp .env.example .env
nano .env
```

### Configure Environment Variables

```bash
# MCP Bridge API Key - REQUIRED
MCP_API_KEY=generate_a_strong_random_token_here

# n8n Instance Configuration
N8N_BASE_URL=https://your-n8n-instance.com
N8N_API_KEY=your_n8n_api_key_here

# Optional: restrict workflows that can be used through this bridge
# N8N_WORKFLOW_ALLOWLIST=123,456

# Optional: tune outbound request timeout in seconds (default is 10)
# HTTP_TIMEOUT_SECONDS=10
```

**Generate a strong auth token:**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save this token - you'll need it for DarcyIQ configuration.

---

## 4. n8n API Key Setup

### Create API Key in n8n

1. Log into your n8n instance
2. Go to **Settings** → **API**
3. Click **Create API Key**
4. Enter a name: `MCP Bridge`
5. Copy the generated key
6. Paste into `.env` file as `N8N_API_KEY`

### Test n8n Connection

```bash
# Test from your server
curl -H "X-N8N-API-KEY: your_n8n_api_key" \
  https://your-n8n-instance.com/api/v1/workflows
```

You should see a JSON response with your workflows.

---

## 5. Security Hardening

### 5.1 Enable Authentication

Ensure `MCP_API_KEY` is set in `.env`:

```bash
# In .env
MCP_API_KEY=your_strong_random_token_here
```

**IMPORTANT:** The bridge requires `MCP_API_KEY` for authentication.

### 5.2 Configure Workflow Allowlist (Optional)

For extra security, restrict which workflows can be accessed:

```bash
# In .env
N8N_WORKFLOW_ALLOWLIST=123,456,789
```

This will filter all workflow and execution listings to only show allowed workflows.

### 5.3 Configure Firewall

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8080/tcp  # MCP Bridge
sudo ufw enable
```

### 5.4 File Permissions

```bash
chmod 600 .env  # Restrict .env to owner only
chmod 755 app/  # Ensure app directory is readable
```

---

## 6. Systemd Service (Auto-start on Boot)

### Create Service File

```bash
sudo nano /etc/systemd/system/n8n-mcp-bridge.service
```

### Service Configuration

```ini
[Unit]
Description=n8n MCP Bridge
After=network.target

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
```

### Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable n8n-mcp-bridge.service
sudo systemctl start n8n-mcp-bridge.service
```

### Check Service Status

```bash
sudo systemctl status n8n-mcp-bridge.service
sudo journalctl -u n8n-mcp-bridge.service -f  # View logs
```

---

## 7. Nginx Reverse Proxy (Recommended)

### Install Nginx

```bash
sudo apt install nginx -y
```

### Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/n8n-mcp-bridge
```

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain or IP

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

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

        # Timeouts
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/n8n-mcp-bridge /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

---

## 8. HTTPS with Let's Encrypt (Recommended)

### Install Certbot

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### Obtain SSL Certificate

```bash
sudo certbot --nginx -d your-domain.com
```

Follow the prompts. Certbot will automatically:
- Obtain SSL certificate
- Configure Nginx for HTTPS
- Set up auto-renewal

### Test Auto-Renewal

```bash
sudo certbot renew --dry-run
```

---

## 9. DarcyIQ Integration

### Configure DarcyIQ MCP Connection

In DarcyIQ settings, add MCP server:

**Server Configuration:**
- **Name:** `n8n Workflow Manager`
- **URL:** `https://your-domain.com` (or `http://your-ec2-ip:8080`)
- **Auth Type:** `API Key`
- **Header Name:** `X-API-Key` or `api_key` (both work)
- **Auth Token:** `YOUR_MCP_API_KEY` (from `.env` file)

### Test Connection

```bash
# Test initialize
curl -X POST https://your-domain.com/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }'

# List available tools
curl -X POST https://your-domain.com/ \
  -H "Content-Type: application/json" \
  -H "api_key: your_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

---

## 10. Monitoring and Logs

### View Application Logs

```bash
# Real-time logs
sudo journalctl -u n8n-mcp-bridge.service -f

# Last 100 lines
sudo journalctl -u n8n-mcp-bridge.service -n 100

# Logs from specific time
sudo journalctl -u n8n-mcp-bridge.service --since "1 hour ago"
```

### Monitor Server Resources

```bash
# CPU and memory usage
htop

# Disk usage
df -h

# Network connections
sudo netstat -tulpn | grep :8080
```

---

## 11. Backup and Updates

### Backup Configuration

```bash
# Backup .env file
cp .env .env.backup

# Backup entire directory
tar -czf n8n-mcp-backup-$(date +%Y%m%d).tar.gz \
  /home/ubuntu/n8n-mcp
```

### Update Application

```bash
cd /home/ubuntu/n8n-mcp
git pull origin master
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart n8n-mcp-bridge.service
```

---

## 12. Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u n8n-mcp-bridge.service -n 50

# Test manually
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Port Already in Use

```bash
# Find process using port 8080
sudo lsof -i :8080

# Kill process
sudo kill -9 <PID>
```

### Authentication Failures

```bash
# Verify .env file exists
cat .env | grep MCP_API_KEY

# Ensure token matches in DarcyIQ configuration
```

### n8n Connection Fails

```bash
# Test n8n connection
curl -H "X-N8N-API-KEY: your_n8n_api_key" \
  https://your-n8n-instance.com/api/v1/workflows

# Common issues:
# - Wrong N8N_BASE_URL (ensure no trailing slash)
# - Invalid N8N_API_KEY
# - n8n instance not accessible
# - API key not created in n8n
```

### Workflow Execution Fails

**Error: "workflow is missing a trigger node"**
- n8n workflows must have a trigger node to be executed via API
- Add a manual trigger or webhook trigger to the workflow
- Or use the n8n UI to execute the workflow

**Error: "Workflow is not permitted by the allowlist"**
- Add the workflow ID to `N8N_WORKFLOW_ALLOWLIST` in `.env`
- Or remove the allowlist restriction entirely

---

## 13. Docker Deployment (Alternative)

### Using Docker Compose

```bash
# Ensure .env file is configured
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

### Update

```bash
git pull origin master
docker-compose down
docker-compose up -d --build
```

---

## 14. Production Checklist

- [ ] Server provisioned and accessible
- [ ] Python 3.11+ installed
- [ ] All dependencies installed
- [ ] `.env` configured with production values
- [ ] n8n API key created and tested
- [ ] `MCP_API_KEY` set to strong random value
- [ ] Systemd service running
- [ ] Firewall rules applied
- [ ] Nginx reverse proxy configured
- [ ] HTTPS/SSL enabled
- [ ] DarcyIQ integration tested
- [ ] Monitoring set up
- [ ] Backup scheduled
- [ ] Tests passing (`pytest`)
- [ ] Logging verified
- [ ] Auto-start on boot tested

---

## 15. Available Tools

Once deployed, the following tools are available via DarcyIQ:

### Workflow Management
1. **n8n_list_workflows** - List workflows with pagination
   - Arguments: `limit` (1-200), `offset` (0+), `active` (true/false/null)

2. **n8n_get_workflow** - Get specific workflow by ID
   - Arguments: `workflow_id` (string)

3. **n8n_run_workflow** - Execute a workflow
   - Arguments: `workflow_id` (string), `payload` (object), `track` (boolean)
   - Returns execution details

### Execution Management
4. **n8n_list_executions** - List workflow executions
   - Arguments: `limit` (1-200), `offset` (0+), `workflow_id` (optional)

5. **n8n_get_execution** - Get execution details by ID
   - Arguments: `execution_id` (string)

### Tracking
6. **darcy_tracking_list** - List executions started through this bridge
   - Returns executions tracked during current runtime
   - Useful for monitoring DarcyIQ-initiated workflows

---

## 16. Security Best Practices

### Authentication
- ✅ Always use strong random tokens for `MCP_API_KEY`
- ✅ Keep n8n API key secure in `.env`
- ✅ Never commit `.env` to git (already in `.gitignore`)

### Network Security
- ✅ Use HTTPS in production
- ✅ Configure firewall to only allow necessary ports
- ✅ Restrict EC2 security group to known IPs if possible

### Application Security
- ✅ Run service as non-root user (ubuntu)
- ✅ Set `.env` permissions to 600
- ✅ Use workflow allowlist to restrict access
- ✅ Monitor logs for suspicious activity

### Operational Security
- ✅ Regular system updates
- ✅ Backup configuration files
- ✅ Monitor resource usage
- ✅ Set up CloudWatch alarms (AWS)

---

## Support

For detailed setup instructions, see:
- **EC2 Setup:** [EC2_SETUP_GUIDE.md](EC2_SETUP_GUIDE.md) - Comprehensive step-by-step guide
- **Implementation Review:** [IMPLEMENTATION_REVIEW.md](IMPLEMENTATION_REVIEW.md) - Code analysis and recommendations
- **README:** [README.md](README.md) - Feature documentation and usage

For issues:
- **Logs:** `sudo journalctl -u n8n-mcp-bridge.service -f`
- **Testing:** Run `pytest -v`
- **Environment:** Verify variables in `.env` file
- **n8n Docs:** https://docs.n8n.io/api/

---

**Last Updated:** January 2, 2026
