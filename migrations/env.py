"""alembic 실행 환경. 운영 DB 스키마 변경용이며 저장소 루트에서 실행한다:  alembic upgrade head

접속은 서버와 같은 engine(SUPABASE_DB_URL)으로 한다 - alembic.ini 에 URL 을 두지 않는다.
alembic.ini 는 Windows 에서 cp949 로 읽혀 한글을 넣으면 깨진다 - 설명은 여기에 쓴다.
"""

from logging.config import fileConfig

from alembic import context

from app.core.db import Base, engine

# app/models/* 를 전부 import 해야 autogenerate 가 모델과 DB 를 비교할 수 있다 (load_csv.py 와 같은 이유)
from app.models import chunk, common, pet, product, purchase, question, user  # noqa: F401

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """DB 에 붙지 않고 SQL 만 뽑는다:  alembic upgrade head --sql"""
    url = engine.url.render_as_string(hide_password=False)
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
