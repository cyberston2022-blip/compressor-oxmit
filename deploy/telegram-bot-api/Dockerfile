# Official tdlib/telegram-bot-api built from a pinned upstream commit.
FROM debian:12-slim AS build
ARG TBAPI_COMMIT=master
RUN apt-get update && apt-get install -y --no-install-recommends \
      git cmake ninja-build make g++ gperf libssl-dev zlib1g-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --recursive --depth 1 https://github.com/tdlib/telegram-bot-api.git /src \
    && cd /src \
    && if [ "$TBAPI_COMMIT" != "master" ]; then \
         git fetch --depth 1 origin "$TBAPI_COMMIT" && git checkout FETCH_HEAD \
         && git submodule update --init --recursive; fi
WORKDIR /src/build
RUN cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr/local .. \
    && cmake --build . --target install -j "$(nproc)"

FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libssl3 zlib1g bash ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api
# Run as uid 1000 (same UID as the oxmit bot container user) so downloaded
# files are owned by the bot's UID. tdlib creates files mode 0640 - owner-
# readable is then always sufficient for the bot, regardless of umask.
RUN useradd -u 1000 -m botapi \
    && mkdir -p /var/lib/telegram-bot-api \
    && chown -R 1000:1000 /var/lib/telegram-bot-api
USER 1000
VOLUME ["/var/lib/telegram-bot-api"]
EXPOSE 8081
ENTRYPOINT ["/bin/sh", "-c", "umask 022; exec /usr/local/bin/telegram-bot-api \"$@\"", "--"]
