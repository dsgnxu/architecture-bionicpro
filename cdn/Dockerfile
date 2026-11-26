FROM nginx:1.27-alpine
RUN mkdir -p /var/cache/nginx/reports \
    && chown -R nginx:nginx /var/cache/nginx
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
  CMD wget -qO- http://127.0.0.1/health || exit 1
