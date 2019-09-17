FROM alpine

RUN apk add --update \
   bash \
   curl \
   libffi-dev \
   python3 \
   python3-dev \
   py-pip \
   uwsgi \
   musl-dev \
   gcc \
   openssl-dev \
   vim

RUN pip3 install --upgrade pip
RUN pip install --upgrade setuptools


RUN pip3 install flask-jwt \
        cryptography \
        jinja2 \
        pyyaml \
        kubernetes \
        bcrypt \
        requests


RUN curl -o /bin/kubectl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl
RUN chmod 755 /bin/kubectl

#Picking up our SNAPI pieces
RUN pip install https://gitlab.sas.com/pemcne/python-snapi/repository/archive.tar.gz

RUN mkdir -p /app
RUN mkdir -p /probe
RUN chmod 2755 /probe
ADD app /app
RUN chmod 755 /app/start.sh
RUN chmod 755 /app/*.py

RUN cd /app
ENTRYPOINT /app/start.sh

