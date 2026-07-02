# Playbook 2 — Deploying FIAA to Production (Azure VM + CI/CD)

**Purpose:** Deploy the FIAA stack to an Azure virtual machine and keep it updated via CI/CD.
**Audience:** DevOps / deployment engineer.
**Prerequisites:** An Azure subscription, SSH key, the FIAA repo in Git.

---

## 1. Provision the Azure VM

1. Azure Portal → **Create a resource → Virtual machine**.
2. Settings:
   - Image: **Ubuntu Server 22.04 LTS**
   - Size: **Standard_D2s_v3** (2 vCPU / 8 GB RAM minimum — the embedding model needs the RAM)
   - Authentication: **SSH public key**
   - Public IP: enabled (needed to reach the app)
3. Networking (creation step): NSG = **Basic**, open **SSH (22)** only for now.
4. Create the VM and download the SSH key.

## 2. Open inbound ports (Network Security Group)

After the VM is created, go to the VM → **Networking** → **Add inbound port rule** for each service:

| Port | Service | Source |
|---|---|---|
| 22 | SSH | My IP |
| 8501 | Streamlit dashboard | My IP (or Any for a shared demo) |
| 8001 | FastAPI webhook | My IP |
| 3000 | Grafana | My IP (optional) |
| 9090 | Prometheus | My IP (optional) |

- Each rule: Protocol **TCP**, Action **Allow**, unique priority (e.g. 310, 320…).
- Use **My IP** as Source where possible.

## 3. Install Docker on the VM

SSH in:
```
ssh -i <key.pem> azureuser@<VM_PUBLIC_IP>
```
Then:
```
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
exit            # log out/in so the docker group applies
```
Reconnect and verify: `docker --version` and `docker compose version`.

## 4. Get the code and secrets onto the VM

1. Clone the repo:
   ```
   git clone https://github.com/<org>/fiaa.git
   cd fiaa
   ```
2. Create the `.env` (never commit it):
   ```
   nano .env
   ```
   Add: `GROQ_API_KEY`, `TAVILY_API_KEY`, `LANGCHAIN_*`, `FIAA_API_KEY`, and any DB/queue vars.


## 5. Build and run

```
docker compose up -d --build
docker compose ps          # all services Up
docker compose logs -f app # watch startup
```

## 6. Verify from your browser

- Dashboard: `http://<VM_PUBLIC_IP>:8501`
- Webhook: `http://<VM_PUBLIC_IP>:8001/health`
- Fire a test alert (from your laptop) to `http://<VM_PUBLIC_IP>:8001/api/analyse`.

## 7. CI/CD (automated deploys)

The pipeline (`.github/workflows/ci.yml`) runs on every push to `main`:
1. **Test** — installs deps, compiles, runs a smoke test.
2. **Build & push** — builds the Docker image and pushes it to the registry.
3. **Deploy** — updates the running service with the new image.

To update production after a code change:
- Push to `main` → CI/CD builds and deploys automatically, **or**
- On the VM manually: `git pull && docker compose up -d --build`.

## 8. Operational notes

- **Cost:** Stop/Deallocate the VM in the Portal when idle to avoid 24/7 billing.
- **Secrets:** `.env` on the VM is acceptable for a prototype; production hardening uses **Azure Key Vault**.
- **HTTPS:** For real production, put **nginx + Let's Encrypt** in front and restrict Grafana/Prometheus to a private network.

## Rollback

- Redeploy the previous image tag:
  ```
  docker compose down
  # set the previous image SHA, then:
  docker compose up -d
  ```
- Or `git checkout <previous-commit>` and `docker compose up -d --build`.
