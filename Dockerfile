FROM python:3.8.3-buster

ENV DEBIAN_FRONTEND noninteractive

RUN adduser --disabled-password --system broadcast && \
    apt-get update && \
    apt-get install -y \
        fonts-noto-cjk \
        pulseaudio \
        xvfb \
        ffmpeg \
        curl \
        unzip && \
    apt-get remove -y curl unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ARG CHROME_VERSION="google-chrome-stable"
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
  && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update -qqy \
  && apt-get -qqy install \
    ${CHROME_VERSION:-google-chrome-stable} \
  && rm /etc/apt/sources.list.d/google-chrome.list \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

ARG CHROME_DRIVER_VERSION
RUN if [ -z "$CHROME_DRIVER_VERSION" ]; \
  then CHROME_MAJOR_VERSION=$(google-chrome --version | sed -E "s/.* ([0-9]+)(\.[0-9]+){3}.*/\1/") \
    && CHROME_DRIVER_VERSION=$(wget --no-verbose -O - "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION}"); \
  fi \
  && echo "Using chromedriver version: "$CHROME_DRIVER_VERSION \
  && pip install chromedriver-binary==${CHROME_DRIVER_VERSION}

COPY requirements.txt ./
RUN pip install -r ./requirements.txt

USER broadcast
WORKDIR /home/broadcast
RUN mkdir -p .pulse && echo "default-server = 127.0.0.1" > .pulse/client.conf

COPY docker-entrypoint.sh /usr/local/bin/
COPY broadcast.py ./

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "-u", "broadcast.py"]
