# Python 3.12 + Debian(glibc).
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: 컨테이너는 일회성이라 .pyc 를 남길 이유가 없다
# PYTHONUNBUFFERED: 안 켜면 print/로그가 버퍼에 갇혀 docker logs 에 안 보인다
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# app/core/config.py 의 ROOT 가 이 경로가 된다 (config.py 기준 3단계 위)
WORKDIR /app

# --- 의존성 레이어 (코드보다 먼저, 따로 깐다) ---
# 임베딩은 OpenAI API 로 돈다(config.py 의 EMBED_MODEL). 그래서 torch/sentence-transformers 를
# 아예 설치하지 않는다 - pyproject.toml 의 optional 그룹 'local' 로 갈라 두었다.
#
# pyproject.toml 만 먼저 복사한다. 이 파일이 안 바뀌면 아래 pip install 레이어는 캐시된다.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .


# --- 코드 레이어 (자주 바뀌므로 맨 뒤) ---
COPY app/ ./app/
COPY pipeline/ ./pipeline/

# app/core/trace.py 가 logs/query_log.jsonl 을 append 로 여는데 디렉터리는 만들지 않는다.
# .dockerignore 로 logs/ 를 뺐으므로 여기서 만들어 둔다 - 없으면 첫 /ask 가 FileNotFoundError 로 죽는다.
RUN mkdir -p logs

EXPOSE 8000

# exec form은 $PORT 를 치환 못 한다 - Railway가 컨테이너에 주입하는 PORT를 그대로 듣는다.
# 로컬처럼 PORT가 없으면 8000으로 기본값을 둔다.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
