FROM postgres:16-alpine

RUN apk add --no-cache bash ca-certificates tzdata curl coreutils openssl \
  && curl -fsSL https://rclone.org/install.sh | bash \
  && rclone version

COPY ops/backup/backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh
