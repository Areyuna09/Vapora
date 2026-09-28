from steam import extract_steam_items, parse_app_data, store_url


def test_single_link():
    text = "Miren https://store.steampowered.com/app/1888930/The_Last_of_Us_Parte_I/"
    assert extract_steam_items(text) == [("app", 1888930)]


def test_multiple_links():
    text = (
        "https://store.steampowered.com/app/1888930/foo "
        "https://store.steampowered.com/app/730/CounterStrike_2/"
    )
    assert extract_steam_items(text) == [("app", 1888930), ("app", 730)]


def test_duplicate_links():
    text = (
        "https://store.steampowered.com/app/730/foo "
        "https://store.steampowered.com/app/730/bar"
    )
    assert extract_steam_items(text) == [("app", 730)]


def test_link_without_trailing_slash():
    assert extract_steam_items("https://store.steampowered.com/app/730") == [("app", 730)]


def test_no_links():
    assert extract_steam_items("hola, nada por acá") == []


def test_bundle_and_sub_links():
    text = (
        "https://store.steampowered.com/bundle/232/Valve_Complete_Pack/ "
        "https://store.steampowered.com/sub/469/ "
        "https://store.steampowered.com/app/730/"
    )
    assert extract_steam_items(text) == [("bundle", 232), ("sub", 469), ("app", 730)]


def test_same_id_different_kind_is_not_duplicate():
    text = "https://store.steampowered.com/app/232/ https://store.steampowered.com/bundle/232/"
    assert extract_steam_items(text) == [("app", 232), ("bundle", 232)]


def test_store_url():
    assert store_url("bundle", 232) == "https://store.steampowered.com/bundle/232/"


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
