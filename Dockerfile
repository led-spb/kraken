FROM python:2.7-slim

ADD ./requirements /tmp/requirements
ADD ./app /home/kraken/app
ADD ./wait-for-it.sh /home/kraken/

RUN pip install --no-cache -r /tmp/requirements
WORKDIR /home/kraken

# EXPOSE 8080
CMD ["/bin/sh", "kraken.sh", "-v", "discovery", "localhost"]
