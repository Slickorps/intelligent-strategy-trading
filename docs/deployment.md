# Deployment Guide

## Docker Deployment

### Quick Start

```bash
# Build and start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI application |
| PostgreSQL | 5432 | Database (optional) |
| Redis | 6379 | Cache (optional) |
| nginx | 80/443 | Reverse proxy (production) |
| Jupyter | 8888 | Analysis notebooks |

### Production Deployment

```bash
# Start with nginx and SSL
docker-compose --profile production up -d

# Or with Jupyter
docker-compose --profile jupyter up -d
```

### Environment Variables

```bash
# Create .env file
cp .env.example .env

# Edit as needed
DEBUG=false
DATABASE_URL=postgresql://postgres:postgres@db:5432/ist
REDIS_URL=redis://redis:6379/0
```

### Volume Mounts

- `./data:/app/data` - Market data files
- `./config:/app/config` - Strategy configurations
- `./logs:/app/logs` - Application logs
- `postgres_data` - Database persistence
- `redis_data` - Cache persistence

### SSL Certificates (Production)

Place certificates in `./ssl/`:
- `cert.pem` - SSL certificate
- `key.pem` - Private key

### Updating

```bash
# Pull latest
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### Troubleshooting

```bash
# Check logs
docker-compose logs api

# Shell into container
docker-compose exec api bash

# Restart service
docker-compose restart api

# Clean rebuild
docker-compose down -v
docker-compose up -d --build
```
