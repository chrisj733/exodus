FROM registry.unx.sas.com/vendor/docker.io/library/alpine:3.11.5 as base

FROM base as builder

RUN apk add --no-cache ca-certificates
ADD https://certificates.sas.com/pki/SASSHA2RootCA.509.txt /usr/local/share/ca-certificates/cs-cert-sas-root-ca.crt
ADD https://certificates.sas.com/pki/SASSHA2IssuingCA01.509.txt /usr/local/share/ca-certificates/cs-cert-sasca01x.crt
ADD https://certificates.sas.com/pki/SASSHA2IssuingCA02.509.txt /usr/local/share/ca-certificates/cs-cert-sasca02x.crt
#### suppress stderr due to a superfluous warning from update-ca-certificates
RUN update-ca-certificates 2>/dev/null || true

RUN \
    set -ex ; \
    mkdir /install ; \
    apk add --no-cache --update \
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
        vim \
    ; \
    :

RUN \
    set -ex ; \
    pip3 install --upgrade pip ; \
    :

RUN \
    set -ex ; \
    pip3 install --prefix=/install \
        flask-jwt \
        cryptography \
        jinja2 \
        pyyaml \
        kubernetes \
        bcrypt \
        requests \
        https://gitlab.sas.com/pemcne/python-snapi/repository/archive.tar.gz

FROM base

COPY --from=builder /install/lib/python3.8/site-packages /usr/lib/python3.8/site-packages/

RUN \
    set -ex ; \
    mkdir /install ; \
    apk add --no-cache --update \
        curl \
        python3 \
        vim \
    ; \
    :

RUN curl -o /bin/kubectl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl
RUN chmod 755 /bin/kubectl

# This cert bundle must be added after ca-certificates/curl packages are installed
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

RUN mkdir -p /app
RUN mkdir -p /probe
RUN chmod 2755 /probe
ADD app /app
RUN chmod 755 /app/start.sh
RUN chmod 755 /app/*.py

RUN cd /app
USER nobody
ENTRYPOINT /app/start.sh

