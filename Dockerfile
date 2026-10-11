# Hugging Face Spaces (Docker) / any container host.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
# Serves the committed data/all_rankings.json and re-scrapes it every night at 03:00 UTC.
CMD ["python", "src/pogo_ui.py", "--hosted", "--host", "0.0.0.0", "--port", "7860", "--refresh-hour", "3"]
