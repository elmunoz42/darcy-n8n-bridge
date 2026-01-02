# Deploying n8n MCP Bridge on Same Server as n8n

This guide covers deploying the MCP bridge on the same EC2 instance where n8n is already running. This is the recommended setup for optimal performance and simplified networking.

---

## Advantages of Same-Server Deployment

✅ **Performance:** No network latency between bridge and n8n (localhost communication)
✅ **Security:** n8n API doesn't need to be exposed publicly
✅ **Simplicity:** Single server to manage and monitor
✅ **Cost:** No additional EC2 instance costs

---

## Prerequisites

- EC2 instance with n8n already installed and running
- SSH access to the server
- n8n API enabled (we'll verify this)
- Port 8080 available for the MCP bridge

---

## Quick Deployment Steps

### 1. Connect to Your Server

```bash
ssh -i "SenN8n.pem" ubuntu@ec2-3-135-16-112.us-east-2.compute.amazonaws.com
```

### 2. Verify n8n is Running

```bash
# Check if n8n is running
sudo systemctl status n8n
# or
ps aux | grep n8n

# Check which port n8n is using (usually 5678)
sudo netstat -tulpn | grep n8n
```

### 3. Enable n8n API (if not already enabled)

n8n API is usually available at `http://localhost:5678/api/v1/` by default.

To verify n8n API is working:
```bash
curl http://localhost:5678/api/v1/workflows
```

If you get a response (even if it's an auth error), the API is enabled.

### 4. Create n8n API Key

1. Open n8n in your browser: `http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:5678`
2. Log in to your n8n instance
3. Go to **Settings** → **API**
4. Click **Create API Key**
5. Name it: `MCP Bridge`
6. Copy the generated key (save it securely)

### 5. Clone the MCP Bridge Repository

```bash
cd ~
git clone <your-repo-url> n8n-mcp
cd n8n-mcp
```

### 6. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 7. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 8. Configure Environment

Generate a strong API key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Create `.env` file:
```bash
cp .env.example .env
nano .env
```

Configure for same-server deployment:
```bash
# MCP Bridge API Key - REQUIRED
MCP_API_KEY=<paste-generated-token-here>

# n8n Instance Configuration - LOCALHOST since n8n is on same server
N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=<paste-n8n-api-key-here>

# Optional: restrict workflows that can be used through this bridge
# N8N_WORKFLOW_ALLOWLIST=123,456

# Optional: tune outbound request timeout in seconds (default is 10)
# HTTP_TIMEOUT_SECONDS=10
```

**IMPORTANT:**
- Use `http://localhost:5678` for `N8N_BASE_URL` (same server, no SSL needed)
- Save the `MCP_API_KEY` - you'll need it for DarcyIQ configuration

Save and exit: `Ctrl+X`, then `Y`, then `Enter`

### 9. Test the Bridge

```bash
# Start manually to test
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

In another terminal:
```bash
# Test health check
curl http://localhost:8080/health

# Test n8n connection through bridge
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "n8n_list_workflows",
      "arguments": {"limit": 5}
    }
  }'
```

If you see your workflows listed, it's working! Press `Ctrl+C` to stop the test server.

### 10. Create Systemd Service

```bash
sudo nano /etc/systemd/system/n8n-mcp-bridge.service
```

Paste this configuration:
```ini
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
```

**Note:** The `After=n8n.service` and `Requires=n8n.service` ensures the bridge starts after n8n.

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable n8n-mcp-bridge.service
sudo systemctl start n8n-mcp-bridge.service
```

Check status:
```bash
sudo systemctl status n8n-mcp-bridge.service
```

### 11. Configure Security Group

Ensure your EC2 security group allows inbound traffic on port 8080:

1. Go to **EC2 Dashboard** → **Security Groups**
2. Select your instance's security group
3. Click **Edit inbound rules**
4. Add rule:
   - Type: Custom TCP
   - Port: 8080
   - Source: 0.0.0.0/0 (or restrict to your IP/DarcyIQ IP)
   - Description: n8n MCP Bridge

### 12. Configure Firewall (if UFW is enabled)

```bash
sudo ufw allow 8080/tcp
sudo ufw status
```

### 13. Test from Outside

From your local machine:
```bash
# Health check
curl http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:8080/health

# Service info
curl http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:8080/

# Test with auth
curl -X POST http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:8080/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_MCP_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }'
```

---

## DarcyIQ Configuration

In DarcyIQ, add the MCP server:

**Server Configuration:**
- **Name:** `n8n Workflow Manager`
- **URL:** `http://ec2-3-135-16-112.us-east-2.compute.amazonaws.com:8080/`
- **Auth Type:** `API Key`
- **Header Name:** `X-API-Key` or `api_key`
- **Auth Token:** `<your-MCP_API_KEY-from-env>`

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│         EC2 Instance (Same Server)              │
│                                                 │
│  ┌──────────────┐         ┌─────────────────┐  │
│  │              │ :5678   │                 │  │
│  │     n8n      │◄────────┤  n8n MCP Bridge │  │
│  │   Instance   │         │   (port 8080)   │  │
│  │              │         │                 │  │
│  └──────────────┘         └────────▲────────┘  │
│                                    │            │
└────────────────────────────────────┼────────────┘
                                     │
                                     │ HTTP
                                     │
                              ┌──────▼──────┐
                              │             │
                              │  DarcyIQ    │
                              │             │
                              └─────────────┘
```

**Communication Flow:**
1. DarcyIQ → MCP Bridge (port 8080, external)
2. MCP Bridge → n8n API (localhost:5678, internal)
3. n8n API → MCP Bridge (response)
4. MCP Bridge → DarcyIQ (response)

---

## Maintenance

### View Logs
```bash
# MCP Bridge logs
sudo journalctl -u n8n-mcp-bridge.service -f

# n8n logs (if using systemd)
sudo journalctl -u n8n.service -f
```

### Restart Services
```bash
# Restart bridge only
sudo systemctl restart n8n-mcp-bridge.service

# Restart both (if needed)
sudo systemctl restart n8n.service n8n-mcp-bridge.service
```

### Update Bridge
```bash
cd ~/n8n-mcp
git pull origin master
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart n8n-mcp-bridge.service
```

### Check Both Services
```bash
sudo systemctl status n8n.service
sudo systemctl status n8n-mcp-bridge.service
```

---

## Troubleshooting

### Bridge Can't Connect to n8n

```bash
# Verify n8n is running
sudo systemctl status n8n

# Check n8n port
sudo netstat -tulpn | grep n8n

# Test n8n API directly
curl http://localhost:5678/api/v1/workflows

# Check bridge logs
sudo journalctl -u n8n-mcp-bridge.service -n 50
```

### Common Issues

**Error: "Unable to reach n8n API"**
- Ensure n8n is running: `sudo systemctl status n8n`
- Verify `N8N_BASE_URL=http://localhost:5678` in `.env`
- Check n8n API is enabled

**Error: "n8n API rejected the credentials"**
- Verify `N8N_API_KEY` in `.env` is correct
- Create a new API key in n8n settings if needed

**Bridge not accessible from outside**
- Check EC2 security group allows port 8080
- Verify UFW allows port 8080: `sudo ufw status`
- Test locally first: `curl http://localhost:8080/health`

**Port 8080 already in use**
- Find what's using it: `sudo lsof -i :8080`
- Choose a different port and update:
  - Systemd service file
  - DarcyIQ configuration
  - Security group rules

---

## Security Considerations

### Same-Server Security Benefits

✅ **n8n API stays private** - Only accessible via localhost
✅ **Reduced attack surface** - n8n doesn't need public API exposure
✅ **Single firewall configuration** - Only port 8080 needs to be open for MCP bridge

### Security Checklist

- [x] n8n API only accessible on localhost (not exposed publicly)
- [ ] Strong `MCP_API_KEY` set in bridge `.env`
- [ ] Strong `N8N_API_KEY` created in n8n
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] Firewall configured (ports 22, 5678 restricted, 8080 for bridge)
- [ ] CORS configured for trusted domains only
- [ ] Rate limiting enabled (60 req/min)
- [ ] Regular system updates scheduled
- [ ] Logs monitored regularly

---

## Optional: Add HTTPS with Nginx

If you want to access the bridge via HTTPS:

### 1. Install Nginx
```bash
sudo apt install nginx -y
```

### 2. Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/n8n-mcp-bridge
```

```nginx
server {
    listen 80;
    server_name mcp.your-domain.com;

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
        proxy_pass_request_headers on;
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/n8n-mcp-bridge /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. Add SSL
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d mcp.your-domain.com
```

---

## Production Checklist

- [ ] n8n is running and accessible
- [ ] n8n API key created
- [ ] MCP bridge repository cloned
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] `.env` configured with localhost n8n URL
- [ ] Manual test successful
- [ ] Systemd service created and running
- [ ] Security group allows port 8080
- [ ] Firewall configured
- [ ] Health check accessible externally
- [ ] DarcyIQ integration tested
- [ ] Logs verified
- [ ] Auto-start on boot tested

---

**Last Updated:** January 2, 2026
