# Docker (optional containerisation)

The full stack is three tiers (Python fleet, Python bridge, Next.js
dashboard) that can run directly on a host (see `README.md`). Container
layouts are provided here for reproducible deployment.

> Note: this sandbox has no Docker daemon, so these images are NOT built or
> tested here — they are provided for host environments with Docker. The
> build prompt explicitly allows this: do not sacrifice actual functionality
> merely to force everything into Docker (§36).

## docker-compose.yml (repo root)

```yaml
version: "3.9"
services:
  fleet:
    build: docker/fleet
    command: python3 -m robotics_ws.supervisor --seed 7
    network_mode: host            # Zenoh multicast scouting + UDP fallback
    volumes:
      - ../configs:/app/configs
      - ../scenarios:/app/scenarios
      - ../models:/app/models
  bridge:
    build: docker/fleet
    command: python3 -m robotics_ws.telemetry_bridge
    network_mode: host
    depends_on: [fleet]
  dashboard:
    build: docker/dashboard
    network_mode: host
    environment:
      - BRIDGE_PORT=8010
```

## docker/fleet/Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY robotics_ws /app/robotics_ws
RUN pip install --no-cache-dir eclipse-zenoh python-socketio aiohttp numpy pytest
CMD ["python3", "-m", "robotics_ws.supervisor", "--seed", "7"]
```

## docker/dashboard/Dockerfile

```dockerfile
FROM node:24-slim AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN npm install
COPY . .
RUN npm run build

FROM node:24-slim
WORKDIR /app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
CMD ["node", "server.js"]
```

`network_mode: host` keeps Zenoh peer discovery and the 18 m radio-range
model meaningful on a single host; for multi-host deployments, configure
Zenoh peers via `listen`/`connect` locators instead of multicast scouting.
