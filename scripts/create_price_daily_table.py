from app.db import engine
from app.models.price_daily import PriceDaily


def main() -> None:
    PriceDaily.__table__.create(bind=engine, checkfirst=True)
    print("price_daily table ensured.")


if __name__ == "__main__":
    main()
