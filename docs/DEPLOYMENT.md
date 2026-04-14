# Contract Tool — Deployment guide

This document describes **requirements**, **environment configuration**, and **deployment options** for running the Contract Tool (Streamlit + MySQL) in the cloud or on a server.

---

## 1. Requirements

### 1.1 Runtime

| Component | Version (recommended) |
|-----------|----------------------|
| **Python** | 3.10, 3.11, or 3.12 |
| **MySQL** | 8.0+ (utf8mb4 / utf8mb4_unicode_ci) |
| **Network** | App host must reach MySQL **TCP** (default3306); browser must reach Streamlit **HTTP** (default 8501) or HTTPS via reverse proxy |

### 1.2 Python packages

Defined in **`requirements.txt`** at the project root:

- `streamlit` — web UI
- `pandas` — data handling
- `mysql-connector-python` — database driver
- `openpyxl` — Excel import/export
- `bcrypt` — password hashing (users)
- `python-dotenv` — optional `.env` loading for secrets

Install:

```bash
pip install -r requirements.txt
```

### 1.3 Database

- **Fresh environment:** load **`database/schema.sql`** with the MySQL client, or start the app once against an empty database so **`initialize_database()`** in `core/db.py` can `CREATE TABLE`.
- **Existing environment (upgrade):** see **`database/migrations/README.md`**. Numbered `.sql` migrations are no longer in the repo; use app startup **`initialize_database()`** for additive columns (**`ensure_v2_distribution_payment_schema()`** via **`ensure_monthly_distribution_and_payment_schema()`**) and align the database with **`database/schema.sql`** using your own process, or recover historical scripts from git if needed.
- Character set: **utf8mb4** (see `DB_CONFIG` in `conf/database.py`).

### 1.4 Static assets

- `static/style.css` — loaded by `app.py`; ensure it is deployed with the app.
- Brand logo: add `static/logo.png` (or `.jpg` / `.jpeg` / `.svg`) — resolved via `core.paths.resolve_static_logo_path`.

---

## 2. Configuration (environment variables)

Secrets must **not** be committed. Use your platform’s secret store or a **`.env`** file (see **`.env.example`**).

### 2.1 MySQL (read by `conf/database.py` → `DB_CONFIG`)

| Variable | Description | Example |
|----------|-------------|---------|
| `MYSQL_HOST` | Database hostname | `db.example.com` or `127.0.0.1` |
| `MYSQL_PORT` | Port | `3306` |
| `MYSQL_USER` | Application user | `contract_app` |
| `MYSQL_PASSWORD` | Application password | (strong secret) |
| `MYSQL_DATABASE` | Database name | `contract_db` |
| `MYSQL_SSL_CA` | Path to CA bundle (optional, for TLS to managed MySQL) | `/etc/ssl/certs/rds-ca.pem` |
| `MYSQL_SSL_DISABLED` | Set to `true` only if required for local/dev | `true` |

If `python-dotenv` is installed, variables can be loaded from a **`.env`** file in the working directory.

### 2.2 Login session cookie (optional but recommended for production)

| Variable | Description |
|----------|-------------|
| `SESSION_SECRET` | Secret key used to sign the **8-hour** browser session cookie. Set a long random value in production so session tokens cannot be forged. If unset, a development default is used (not safe for production). |

The app uses `extra-streamlit-components` (CookieManager) and `itsdangerous` so a **full page reload** can restore the logged-in user until the token expires or the user clicks **Logout**.

### 2.3 Email (optional — `tabs/email_notifications.py`)

| Variable | Description |
|----------|-------------|
| `EMAIL_SMTP_SERVER` | SMTP host |
| `EMAIL_SMTP_PORT` | Usually `587` (STARTTLS) |
| `EMAIL_USERNAME` | SMTP login |
| `EMAIL_PASSWORD` | SMTP password or app password |
| `EMAIL_FROM_NAME` | Display name |

If unset, the code falls back to defaults in the repository (override in production via env).

### 2.4 Streamlit (optional)

You can set standard Streamlit server options, for example:

| Variable | Purpose |
|----------|---------|
| `STREAMLIT_SERVER_PORT` | Listen port (default 8501) |
| `STREAMLIT_SERVER_ADDRESS` | Bind address (`0.0.0.0` for containers/VMs) |
| `STREAMLIT_SERVER_HEADLESS` | `true` on servers without a desktop |

Or pass flags: `streamlit run app.py --server.port=8501 --server.address=0.0.0.0`.

---

## 3. Local run (without Docker)

```bash
cd /path/to/Contract-tool
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
copy .env.example .env         # edit MYSQL_* and optional EMAIL_*
streamlit run app.py --server.port=8501 --server.address=127.0.0.1
```

---

## 4. Docker (single image)

**`Dockerfile`** builds a production-oriented image (Python 3.11, Streamlit on `0.0.0.0:8501`).

```bash
docker build -t contract-tool .
docker run --rm -p 8501:8501 --env-file .env contract-tool
```

Point **`MYSQL_HOST`** in `.env` to a reachable MySQL instance (not `localhost` from inside the container unless using host networking).

---

## 5. Docker Compose (app + MySQL for dev / small deployments)

**`docker-compose.yml`** runs:

- **db** — MySQL 8 with a named volume for data  
- **app** — Contract Tool, `MYSQL_HOST=db`

Steps:

1. Copy **`.env.example`** to **`.env`** and set at least:
   - `MYSQL_ROOT_PASSWORD` (for the DB container)
   - `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` (must match between `db` service and `app` service — compose wires defaults)
2. Run:

```bash
docker compose up --build
```

3. Open **http://localhost:8501**

For **production**, prefer a **managed MySQL** (RDS, Azure Database for MySQL, Cloud SQL, etc.): remove the `db` service, set `MYSQL_HOST` to the managed endpoint, enable TLS if required (`MYSQL_SSL_CA`).

---

## 6. Cloud deployment patterns

### 6.1 Streamlit Community Cloud

- Connect a **Git** repository; set **Secrets** in TOML format for env vars.
- **Limitation:** Community Cloud is not ideal if you need a **private MySQL** on a VPC only; often you use a **public** DB endpoint with TLS + IP allow list, or a different host.

Example secrets (conceptual):

```toml
MYSQL_HOST = "..."
MYSQL_USER = "..."
MYSQL_PASSWORD = "..."
MYSQL_DATABASE = "contract_db"
```

Main file: **`app.py`**.

### 6.2 Virtual machine (AWS EC2, Azure VM, GCP Compute Engine)

1. Install Docker **or** Python 3.11 + `pip install -r requirements.txt`.
2. Run MySQL on the same VM **or** use managed MySQL.
3. Run the app (Docker or `streamlit run` under **systemd**).
4. Put **Nginx**, **Caddy**, or **Azure Application Gateway** in front for **HTTPS** and optional **basic auth** / SSO (Streamlit does not replace enterprise IAM by itself).

### 6.3 Container platforms (AWS ECS/Fargate, Azure Container Apps, Google Cloud Run)

1. Build and push the image from **`Dockerfile`**.
2. Set **secrets** / environment variables for `MYSQL_*`.
3. Map container port **8501** to HTTPS on the load balancer.
4. Scale to **1+** instances; note: Streamlit **session state** is per instance — sticky sessions help; for strict consistency, run a single replica or externalize session storage (advanced).

### 6.4 Azure App Service (Web App for Containers)

- Deploy the same Docker image.
- Configure **Application Settings** for `MYSQL_*`.
- Enable **HTTPS** and **always on** if the plan supports it.

---

## 7. Security checklist (production)

- [ ] Replace default MySQL passwords; use a dedicated DB user with **least privilege**.
- [ ] Restrict MySQL **firewall** to app IPs only.
- [ ] Use **TLS** to MySQL when the provider recommends it (`MYSQL_SSL_CA`).
- [ ] Do **not** commit **`.env`**; add **`.env`** to **`.gitignore`** (included in this repo).
- [ ] Rotate **`EMAIL_PASSWORD`** and SMTP credentials; prefer app-specific passwords.
- [ ] Serve the app over **HTTPS** and set secure cookies / headers at the reverse proxy if exposed to the internet.
- [ ] Review hardcoded fallbacks in `conf/database.py` and email defaults — in production, **require** env vars (optional hardening: fail fast if `MYSQL_PASSWORD` is missing).

---

## 8. Operations

- **Logs:** Streamlit prints to stdout; container platforms collect logs from the app container.
- **Backups:** Back up MySQL on a schedule (managed services offer automated backups).
- **Updates:** Rebuild image / redeploy; apply schema changes via `database/schema.sql` and/or `initialize_database()` additive logic, or your own DBA upgrade path.

---

## 9. Troubleshooting

| Symptom | Things to check |
|---------|------------------|
| Cannot connect to MySQL | `MYSQL_HOST`/`PORT`, security group / firewall, user grants, SSL settings |
| App starts but blank/errors | DB schema not initialized; check app logs for `initialize_database` / connection errors |
| Email fails | `EMAIL_*` vars, SMTP allow list, modern auth (OAuth) vs basic auth for your provider |

---

## 10. File reference

| File | Role |
|------|------|
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for secrets |
| `Dockerfile` | Container image for Streamlit |
| `docker-compose.yml` | App + MySQL for local/small setups |
| `.dockerignore` | Keeps image small |
| `conf/database.py` | `DB_CONFIG` from environment |
| `database/schema.sql` | Full MySQL DDL for new installs |
| `database/migrations/README.md` | Notes on upgrades (numbered SQL scripts removed; use `schema.sql` + startup DDL) |
| `core/db.py` | Connections, CRUD, `initialize_database()`, runtime schema sync |
| `app.py` | Streamlit entrypoint |

---

*Last updated to match the repository layout and `conf/database.py` environment-based configuration.*
