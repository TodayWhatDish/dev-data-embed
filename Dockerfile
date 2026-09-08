# Python 3.12 + Debian(glibc). alpine 은 musl 이라 sqlite-vec 바이너리가 없다.
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: 컨테이너는 일회성이라 .pyc 를 남길 이유가 없다
# PYTHONUNBUFFERED: 안 켜면 print/로그가 버퍼에 갇혀 docker logs 에 안 보인다
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# app/core/config.py 의 ROOT 가 이 경로가 된다 (config.py 기준 3단계 위)
WORKDIR /app

# --- 의존성 레이어 (코드보다 먼저, 따로 깐다) ---
# torch 를 CPU 전용 인덱스에서 먼저 박는다. 이걸 안 하면 sentence-transformers 가
# CUDA 빌드(2.5GB+)를 끌고 온다 - app/core/config.py 의 EMBED_DEVICE='cpu' 라 GPU 는 안 쓴다.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# pyproject.toml 만 먼저 복사한다. 이 파일이 안 바뀌면 아래 pip install 레이어는 캐시된다.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# --- 코드 레이어 (자주 바뀌므로 맨 뒤) ---
COPY app/ ./app/
COPY pipeline/ ./pipeline/
COPY data/master/ ./data/master/

# app/core/trace.py 가 logs/query_log.jsonl 을 append 로 여는데 디렉터리는 만들지 않는다.
# .dockerignore 로 logs/ 를 뺐으므로 여기서 만들어 둔다 - 없으면 첫 /ask 가 FileNotFoundError 로 죽는다.
RUN mkdir -p logs

EXPOSE 8000

# --host 0.0.0.0 필수. 기본값 127.0.0.1 이면 컨테이너 안에서만 들리고 -p 로 뚫어도 안 닿는다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
