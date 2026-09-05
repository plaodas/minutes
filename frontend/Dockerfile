FROM node:18-alpine AS builder
WORKDIR /app

# install deps
COPY package.json package-lock.json* ./
# install dependencies
RUN npm ci || npm install

# build
COPY . .
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
ARG VITE_SHOW_ADMIN_CONTROLS
ENV VITE_SHOW_ADMIN_CONTROLS=${VITE_SHOW_ADMIN_CONTROLS}
# Preload a polyfill so build tools that reference globalThis.crypto work in this environment
# Quote NODE_OPTIONS so the entire `--require <path>` is treated as the env value
RUN NODE_OPTIONS='--require ./scripts/polyfill-global-crypto.cjs' npm run build

FROM nginx:stable-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
