# VoltIQ web app image: builds the React app and serves it with nginx, which
# also forwards /api/* to the API container, so the browser needs one address.
#   docker build -f deploy/web.Dockerfile -t voltiq-web .
FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
ENV VITE_API_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
