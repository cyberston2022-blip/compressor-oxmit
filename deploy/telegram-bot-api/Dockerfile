FROM aiogram/telegram-bot-api:latest
USER root
RUN apk add --no-cache bash && mkdir -p /var/lib/telegram-bot-api && chown -R 1000:1000 /var/lib/telegram-bot-api
VOLUME ["/var/lib/telegram-bot-api"]
EXPOSE 8081
ENTRYPOINT ["/bin/sh", "-c", "umask 000; exec /usr/local/bin/telegram-bot-api \"$@\"", "--"]
