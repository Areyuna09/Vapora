from bot import build_embed, format_money, format_price, format_reviews
from steam import parse_app_data, parse_reviews


def test_format_money_argentine_style():
    assert format_money(2999, "USD") == "USD 29,99"
    assert format_money(123456, "USD") == "USD 1.234,56"


def test_format_price_with_discount():
    data = {"final_cents": 2999, "initial_cents": 5999, "currency": "USD", "discount_percent": 50}
    assert format_price(data) == "**USD 29,99**\n~~USD 59,99~~ (-50%)"


def test_format_price_without_discount():
    data = {"final_cents": 999, "initial_cents": 999, "currency": "USD", "discount_percent": 0}
    assert format_price(data) == "**USD 9,99**"


def test_format_price_free_and_unavailable():
    assert format_price({"is_free": True}) == "**Gratis**"
    assert format_price({}) == "Sin precio disponible"


def test_parse_reviews():
    payload = {
        "success": 1,
        "query_summary": {"review_score_desc": "Muy positivas", "total_positive": 92766,
                          "total_negative": 16971, "total_reviews": 109737},
    }
    reviews = parse_reviews(payload)
    assert reviews == {"description": "Muy positivas", "total": 109737, "positive_percent": 85}
    assert format_reviews(reviews) == "Muy positivas\n85% de 109.737"


def test_parse_reviews_without_reviews():
    assert parse_reviews({"success": 1, "query_summary": {"total_reviews": 0}}) is None


def test_parse_extra_fields():
    data = {
        "name": "Juego",
        "release_date": {"coming_soon": False, "date": "28 MAR 2023"},
        "genres": [{"id": "1", "description": "Acción"}, {"id": "25", "description": "Aventura"}],
        "developers": ["Naughty Dog LLC"],
    }
    result = parse_app_data(1, data)
    assert result["release_date"] == "28 MAR 2023"
    assert result["genres"] == ["Acción", "Aventura"]


def test_build_embed_fields():
    data = parse_app_data(1888930, {
        "name": "The Last of Us™ Parte I",
        "header_image": "https://example.com/header.jpg",
        "price_overview": {"currency": "USD", "initial": 5999, "final": 2999, "discount_percent": 50},
        "release_date": {"coming_soon": False, "date": "28 MAR 2023"},
        "genres": [{"description": "Acción"}],
    })
    data["reviews"] = {"description": "Muy positivas", "total": 100, "positive_percent": 85}
    embed = build_embed(1888930, data)
    names = [f.name for f in embed.fields]
    assert names == ["💵 Precio Steam (AR)", "⭐ Reseñas", "📅 Lanzamiento"]
    assert embed.description.endswith("🎭 Acción")
    assert embed.image.url == "https://example.com/header.jpg"
