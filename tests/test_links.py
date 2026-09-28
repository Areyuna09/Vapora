from steam import extract_app_ids, parse_app_data


def test_single_link():
    text = "Miren https://store.steampowered.com/app/1888930/The_Last_of_Us_Parte_I/"
    assert extract_app_ids(text) == [1888930]


def test_multiple_links():
    text = (
        "https://store.steampowered.com/app/1888930/foo "
        "https://store.steampowered.com/app/730/CounterStrike_2/"
    )
    assert extract_app_ids(text) == [1888930, 730]


def test_duplicate_links():
    text = (
        "https://store.steampowered.com/app/730/foo "
        "https://store.steampowered.com/app/730/bar"
    )
    assert extract_app_ids(text) == [730]


def test_link_without_trailing_slash():
    assert extract_app_ids("https://store.steampowered.com/app/730") == [730]


def test_no_links():
    assert extract_app_ids("hola, nada por acá") == []


def test_parse_discounted_price():
    data = {
        "name": "The Last of Us™ Parte I",
        "is_free": False,
        "price_overview": {
            "currency": "USD",
            "initial": 5999,
            "final": 2999,
            "discount_percent": 50,
            "initial_formatted": "$59.99",
            "final_formatted": "$29.99 USD",
        },
    }
    result = parse_app_data(1888930, data)
    assert result["price"] == "$29.99 USD"
    assert result["currency"] == "USD"
    assert result["final_cents"] == 2999
    assert result["initial_cents"] == 5999
    assert result["discount_percent"] == 50


def test_parse_no_discount_is_zero():
    data = {
        "name": "Juego",
        "price_overview": {"currency": "USD", "initial": 999, "final": 999,
                           "discount_percent": 0, "final_formatted": "$9.99 USD"},
    }
    assert parse_app_data(1, data)["discount_percent"] == 0


def test_parse_free_game():
    result = parse_app_data(730, {"name": "Counter-Strike 2", "is_free": True})
    assert result["is_free"] is True
    assert result["price"] is None
