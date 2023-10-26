FROM python:3.11

LABEL "com.github.actions.name"="ChatGPT Reviewer"
LABEL "com.github.actions.description"="Automated pull requests reviewing and issues triaging with ChatGPT"

WORKDIR /app

COPY ./app /app

RUN pip install --no-cache-dir -r /app/requirements.txt

ENTRYPOINT [ "/app/main.py" ]
