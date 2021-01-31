FROM ubuntu:18.04

WORKDIR /api
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -y update && \
 apt-get -y upgrade && \
 apt-get -y dist-upgrade && \
 apt-get -y autoremove

RUN apt-get install -y \
    openjdk-8-jre \
    python-dev \
    python-tk \
    python-numpy \
    python3-dev \
    python3-tk \
    python3-numpy \
    libpoppler-cpp-dev \
    libpython3-all-dev \
    python3-pip \
    libpython3-all-dev \
    python3-all \
    libzbar0 \
    poppler-utils

 RUN mkdir /files
 RUN pip3 install --upgrade pip

 COPY ./back/requirements.txt ./requirements.txt
 RUN pip3 install -r requirements.txt
 COPY ./ ./

 ENTRYPOINT python3 back/src/server.py
