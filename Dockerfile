# Hosts the bundled C/WASM browser preview; does not implement a calendar backend.
# Override NGINX_IMAGE with a reviewed digest for a reproducible base image.
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:stable-alpine
FROM ${NGINX_IMAGE}
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY dist-preview/index.html \
     dist-preview/styles.css \
     dist-preview/app.mjs \
     dist-preview/config.mjs \
     dist-preview/dates.mjs \
     dist-preview/events.mjs \
     dist-preview/google.mjs \
     dist-preview/renderer.mjs \
     dist-preview/manifest.webmanifest \
     dist-preview/icon.svg \
     dist-preview/icon-192.png \
     dist-preview/icon-512.png \
     dist-preview/paperweek-preview.wasm \
     dist-preview/build-info.json \
     dist-preview/sw.js \
     dist-preview/LICENSE.txt \
     dist-preview/THIRD_PARTY.md \
     /usr/share/nginx/html/
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
# Skip the base image's configuration-modifying entrypoint: rootfs is read-only.
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
