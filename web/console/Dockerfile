# Review console: built with Node, served by an unprivileged nginx that proxies /api to the core.
FROM node:22-bookworm AS build
WORKDIR /repo/web/console
COPY data/policies/clauses.json /repo/data/policies/clauses.json
COPY web/console/package.json web/console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/console/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY web/console/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /repo/web/console/dist/console/browser /usr/share/nginx/html
EXPOSE 8080
