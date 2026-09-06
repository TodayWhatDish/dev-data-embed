from app.app_logger.logger import init_logger
from app.domain.domain_init import init_from_db


def main():
    init_logger()
    init_from_db()


if __name__ == "__main__":
    main()
