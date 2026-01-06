Deployment Guidance

I can’t reach your EC2 box directly; please run the checks below there. sudo systemctl status n8n fails because n8n likely runs outside systemd (Docker, pm2, or a screen/tmux shell). Confirm the runtime with one of:

ps aux | grep -i n8n
docker ps | grep n8n          # if you used Docker
pm2 list                      # if you used pm2
ls /etc/systemd/system | grep n8n
Once you know the supervisor, keep using it instead of systemd for n8n itself.

Make sure the API stays reachable locally:

Bridge deployment (run inside ~/n8n-mcp):

The bridge doesn’t expose /health; test it with JSON-RPC:

Create a systemd unit only for the bridge (n8n keeps using its existing runtime):

Then run:

sudo systemctl daemon-reload
sudo systemctl enable n8n-mcp-bridge
sudo systemctl start n8n-mcp-bridge
sudo systemctl status n8n-mcp-bridge
sudo journalctl -u n8n-mcp-bridge -f

Open TCP/8080 in the instance security group, test remotely with the same JSON-RPC curl request, and configure DarcyIQ with the bridge URL and the X-API-Key header.