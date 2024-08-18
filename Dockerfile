FROM python:3.12-alpine

WORKDIR /usr/src/app

COPY poetry.lock pyproject.toml ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi -vvvv
COPY . .

WORKDIR /usr/src/app
CMD ["python", "-m", "gitlab_rss_mailer", "/data/config.yml", "/data/cache.json"]
