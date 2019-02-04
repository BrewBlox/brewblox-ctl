FROM arm32v6/alpine
WORKDIR /output

COPY ./brewblox_ctl_lib/* /app/source/
COPY ./entrypoint.sh /app/

CMD [ "sh", "/app/entrypoint.sh" ]
