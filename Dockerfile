FROM python:3.13.9-slim-bookworm
WORKDIR /bot
COPY bot.py arena_model.py mechfight.py ./
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
