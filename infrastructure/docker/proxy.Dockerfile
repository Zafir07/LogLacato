# Imagem do proxy de entrada: compila o painel React e o serve com o Caddy.
# Contexto de build: raiz do repositório (definido no docker-compose.yml).

FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2
COPY infrastructure/proxy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv/frontend
