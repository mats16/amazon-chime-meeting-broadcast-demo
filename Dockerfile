FROM python:3.8.2

ENV DEBIAN_FRONTEND noninteractive

ENV CHROME_VERSION=80.0.3987.16

RUN adduser --disabled-password --system broadcast && \
    apt-get update && \
    apt-get install -y \
        fonts-noto-cjk \
        pulseaudio \
        xvfb \
        chromium=${CHROME_VERSION}* \
        ffmpeg \
        curl \
        unzip && \
    apt-get remove -y curl unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install chromedriver-binary==${CHROME_VERSION}

COPY requirements.txt ./
RUN pip install -r ./requirements.txt

USER broadcast
WORKDIR /home/broadcast
RUN mkdir -p .pulse && echo "default-server = 127.0.0.1" > .pulse/client.conf

COPY docker-entrypoint.sh /usr/local/bin/
COPY broadcast.py ./

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "broadcast.py"]
