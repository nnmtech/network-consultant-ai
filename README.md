# Network Consultant AI - Production System

## Overview
Enterprise-grade AI agent system for network consulting using CrewAI multi-agent orchestration.

## Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+ (optional but recommended)
- Docker & Docker Compose
- Kubernetes cluster (for production)

## Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/nnmtech/network-consultant-ai.git
cd network-consultant-ai
```

### 2. Create Secrets Folder (OUTSIDE PROJECT)
```bash
# Create secrets directory outside project
mkdir -p ../secrets

# Create secrets file
cat > ../secrets/.env.production << EOF
OPENAI_API_KEY=sk-proj-your-key-here
JWT_SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=postgresql://user:pass@localhost:5432/network_ai
REDIS_URL=redis://localhost:6379/0
EOF

chmod 600 ../secrets/.env.production
```

### 3. Install Dependencies
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Setup Database
```bash
# Start PostgreSQL (Docker)
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=network_ai \
  -p 5432:5432 \
  postgres:15

# Tables are created automatically on first run
```

### 5. Start Redis (Optional)
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 6. Run Application
```bash
# Load secrets
export $(cat ../secrets/.env.production | xargs)

# Start server
uvicorn backend.main:app --host 0.0.0.0 --port 3000 --reload
```

Access UI: http://localhost:3000

## Production Deployment

### Docker Compose
```bash
# Build image
docker build -t network-consultant:2.1.0 .

# Run with secrets
docker-compose -f docker-compose.prod.yml up -d
```

### Kubernetes
```bash
# Create namespace and secrets
kubectl create namespace network-ai

kubectl create secret generic network-ai-secrets \
  --from-env-file=../secrets/.env.production \
  -n network-ai

# Deploy
./launch_production.sh 2.1.0
```

## Generate JWT Token (for API access)
```python
from backend.auth.jwt_handler import create_access_token

token = create_access_token({"sub": "user@example.com", "role": "admin"})
print(f"Bearer {token}")
```

## Monitoring
```bash
# Real-time monitoring
python -m backend.cli.enhanced_monitor monitor --watch

# Cache statistics
python -m backend.cli.enhanced_monitor cache-stats

# Run diagnostics
python -m backend.cli.enhanced_monitor diagnose --full
```

## Testing
```bash
# Run validation
python production_validation.py

# Run lock detection tests
python -m backend.tests.test_robust_lock_detection
```

## Security Best Practices

### Secrets Management
1. **Never commit secrets to Git**
2. Store all credentials in `../secrets/` folder outside project
3. Use environment-specific secret files:
   - `../secrets/.env.development`
   - `../secrets/.env.staging`
   - `../secrets/.env.production`
4. Set restrictive permissions: `chmod 600 ../secrets/*`
5. In Kubernetes, use native Secrets:
   ```bash
   kubectl create secret generic network-ai-secrets \
     --from-literal=OPENAI_API_KEY=... \
     --from-literal=JWT_SECRET_KEY=... \
     -n network-ai
   ```

### JWT Token Generation
```bash
# Generate secure secret key
openssl rand -hex 32
```

### Database Security
- Use strong passwords
- Enable SSL/TLS connections
- Restrict network access
- Regular backups

## Architecture

### Components
- **FastAPI**: REST API server
- **CrewAI**: Multi-agent orchestration
- **PostgreSQL**: Audit logging
- **Redis**: Distributed caching
- **Prometheus**: Metrics collection
- **RobustCache**: Cross-process file cache

### Agents
1. **AD Specialist** - Active Directory issues
2. **Network Analyst** - Connectivity problems
3. **Security Auditor** - Security vulnerabilities
4. **Compliance Checker** - Regulatory compliance

## API Endpoints

### Orchestration
```bash
POST /api/v1/orchestrate
Authorization: Bearer <token>

{
  "client_issue": "Users cannot authenticate",
  "priority": "high",
  "client_context": {
    "environment": "Active Directory",
    "location": "Atlanta HQ",
    "users_affected": 45
  }
}
```

### Health Checks
- `GET /health` - Full health status
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /health/startup` - Startup probe

### Metrics
- `GET /metrics` - Prometheus metrics

## Environment Variables

### Required (Store in secrets)
- `OPENAI_API_KEY` - OpenAI API key for LLM
- `JWT_SECRET_KEY` - Secret key for JWT signing
- `DATABASE_URL` - PostgreSQL connection string

### Optional
- `REDIS_URL` - Redis connection string
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `WORKERS` - Number of Gunicorn workers
- `CACHE_DIR` - File cache directory

## Troubleshooting

### OpenAI API Issues
```bash
# Verify API key
export OPENAI_API_KEY=sk-proj-...
python -c "from openai import OpenAI; print(OpenAI().models.list())"
```

### Database Connection Issues
```bash
# Test connection
psql "postgresql://user:pass@localhost:5432/network_ai"
```

### Cache Lock Issues
```bash
# Clean stale locks
find /var/cache/network-ai/.locks -name "*.lock" -delete
```

## Performance Tuning

### Gunicorn Workers
```bash
# Set workers to (2 * CPU_cores) + 1
export WORKERS=9  # For 4-core system
```

### Cache Configuration
```bash
export CACHE_SHARDS=16  # Increase for high concurrency
export CACHE_LOCK_TIMEOUT=60  # Increase for slow operations
```

## Support
- GitHub Issues: https://github.com/nnmtech/network-consultant-ai/issues
- Email: network-ai-nmtech4u@gmail.com

## License
Proprietary - NMTECH 2026
