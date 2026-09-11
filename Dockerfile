# Python 3.12 + Debian(glibc). alpine 은 musl 이라 sqlite-vec 바이너리가 없다.
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
# render.yaml 의 persistent disk 가 /app/data 에 마운트된다 - 마운트는 기존 디렉터리를
# 덮어쓰는 게 아니라 통째로 가리므로, data/master 를 여기 구워넣어도 런타임엔 안 보인다.
# 그래서 마운트 경로 밖(/app/_seed_master)에 구워두고, 컨테이너 시작 시 디스크가 비어있으면
# 거기서 한 번만 복사해온다 (디스크는 영속적이라 이후 재시작부턴 안 건드림).
COPY data/master/ ./_seed_master/

# app/core/trace.py 가 logs/query_log.jsonl 을 append 로 여는데 디렉터리는 만들지 않는다.
# .dockerignore 로 logs/ 를 뺐으므로 여기서 만들어 둔다 - 없으면 첫 /ask 가 FileNotFoundError 로 죽는다.
RUN mkdir -p logs

EXPOSE 8000

# --host 0.0.0.0 필수. 기본값 127.0.0.1 이면 컨테이너 안에서만 들리고 -p 로 뚫어도 안 닿는다.
CMD ["sh", "-c", "[ -d data/master ] || cp -r _seed_master data/master; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
