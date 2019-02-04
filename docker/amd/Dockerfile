FROM alpine
WORKDIR /app

COPY ./source /app/source
COPY ./entrypoint.sh /app/

RUN ls /app/source

CMD [ "sh", "/app/entrypoint.sh" ]
