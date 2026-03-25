# CyberLab LXC Deployment Summary

**Date:** 2026-03-25  
**Container ID:** 206  
**Container Name:** cyberlab-prod  
**IP Address:** 192.168.0.206  
**OS:** Ubuntu 24.04 LTS

## Resources Allocated

- **CPU:** 2 cores (cpulimit: 2)
- **RAM:** 4096 MB
- **Disk:** 20 GB (local-lvm)
- **Network:** Bridge vmbr0, Static IP 192.168.0.206/24

## Code Location

All CyberLab code transferred to: `/root/cyberlab/`

```
/root/cyberlab/
├── backend/          # FastAPI backend
├── frontend/         # React + Vite frontend
├── challenges/       # Challenge definitions
├── data/             # Data files
├── docker/           # Docker configurations
├── drop/             # Drop zone for files
├── start-backend.sh  # Backend startup script
└── start-frontend.sh # Frontend startup script
```

## Installed Dependencies

### Backend (Python 3.12)
- FastAPI, Uvicorn, SQLModel, SQLAlchemy
- Pydantic, Pydantic-settings
- Docker SDK, HTTPX
- PyMuPDF, python-pptx
- Watchdog, pytest, black, ruff

Virtual environment: `/root/cyberlab/backend/venv/`

### Frontend (Node.js 18)
- React 18, React Router DOM
- Vite, TypeScript
- TailwindCSS, Lucide React

Node modules: `/root/cyberlab/frontend/node_modules/`

### System Tools
- **Docker:** 28.2.2 (available for sandbox containers)
- **OpenCode:** 1.3.2 (AI coding assistant)
- **Git:** 2.43.0
- **curl, wget:** Available

## How to Start Services

### Option 1: Using Startup Scripts

```bash
# SSH into the container
ssh root@192.168.0.206
# Password: cyberlab123

# Start backend (runs on port 8080)
/root/cyberlab/start-backend.sh

# Start frontend (runs on port 5173)
/root/cyberlab/start-frontend.sh
```

### Option 2: Manual Commands

```bash
# Backend
cd /root/cyberlab/backend
source venv/bin/activate
python3 -m uvicorn main:app --host 0.0.0.0 --port 8080

# Frontend (in a separate terminal)
cd /root/cyberlab/frontend
npm run dev -- --host 0.0.0.0
```

### Option 3: Screen/Tmux Sessions

For persistent background operation:

```bash
# Install screen if needed
apt install screen

# Start backend in screen
screen -S backend
/root/cyberlab/start-backend.sh
# Press Ctrl+A, then D to detach

# Start frontend in screen
screen -S frontend
/root/cyberlab/start-frontend.sh
# Press Ctrl+A, then D to detach
```

## Access URLs

Once services are running:

- **Backend API:** http://192.168.0.206:8080
- **Frontend UI:** http://192.168.0.206:5173
- **API Docs:** http://192.168.0.206:8080/docs

## OpenCode Configuration

OpenCode is installed at `/root/.opencode/bin/opencode`.

To configure:
```bash
opencode
# Then run /connect to set up your AI provider
```

## Proxmox Management Commands

From Proxmox host (192.168.0.10):

```bash
# Start/Stop/Reboot container
pct start 206
pct stop 206
pct reboot 206

# Check status
pct status 206

# Enter container shell
pct enter 206

# Execute command
pct exec 206 -- <command>

# View config
pct config 206
```

## Notes

- **No systemd services configured** - Use startup scripts or screen sessions
- **Docker installed** but daemon may need manual start in LXC (requires nesting enabled)
- **Nesting enabled** for Docker support (`features: nesting=1`)
- **Database:** SQLite at `/root/cyberlab/backend/cyberlab.db`

## Troubleshooting

### Docker in LXC
If Docker doesn't work, ensure nesting is enabled:
```bash
# On Proxmox host
pct set 206 --features nesting=1
pct reboot 206
```

### Port Access
If ports aren't accessible, check firewall on Proxmox host and container.

### Missing Dependencies
```bash
cd /root/cyberlab/backend
source venv/bin/activate
pip install -r requirements.txt

cd /root/cyberlab/frontend
npm install
```

---

**SSH Access:** `ssh root@192.168.0.206` (password: `cyberlab123`)  
**SSH Key:** Your public key is authorized at `/root/.ssh/authorized_keys`
