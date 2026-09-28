from bot import build_embed, format_contents
from steam import parse_app_data, parse_bundle_data, parse_package_data


def test_dlc_shows_base_game():
    data = parse_app_data(2778580, {
        "type": "dlc",
        "name": "ELDEN RING Shadow of the Erdtree",
        "fullgame": {"appid": "1245620", "name": "ELDEN RING"},
    })
    assert data["dlc_of"] == "ELDEN RING"
    assert format_contents(data) == "🧩 DLC de **ELDEN RING**"


def test_package_parsing():
    data = parse_package_data(469, {
        "name": "The Orange Box",
        "page_image": "https://example.com/header.jpg",
        "apps": [{"id": i, "name": f"Juego {i}"} for i in range(1, 8)],
        "price": {"currency": "USD", "initial": 1049, "final": 1049, "discount_percent": 0, "individual": 1158},
    })
    assert data["kind"] == "sub"
    assert data["final_cents"] == 1049
    assert data["initial_cents"] == 1158  # lo que cuesta todo por separado
    assert data["discount_percent"] == 9
    assert data["included_count"] == 7
    assert format_contents(data) == "📦 Paquete con 7 productos: Juego 1, Juego 2, Juego 3, Juego 4 y 3 más"


def test_bundle_parsing():
    data = parse_bundle_data(232, {
        "name": "Valve Complete Pack",
        "appids": list(range(18)),
        "main_capsule": "https://example.com/capsule.jpg",
        "initial_price": 7584,
        "final_price": 6824,
        "formatted_final_price": "$68.24 USD",
    })
    assert data["kind"] == "bundle"
    assert data["currency"] == "USD"
    assert data["final_cents"] == 6824
    assert data["discount_percent"] == 10
    assert format_contents(data) == "📦 Bundle con 18 productos"


def test_bundle_embed_url_and_footer():
    data = parse_bundle_data(232, {"name": "Valve Complete Pack", "final_price": 6824,
                                   "formatted_final_price": "$68.24 USD", "appids": [1, 2]})
    embed = build_embed(data, {"oficial": 1550.0, "cripto": 1623.0})
    assert embed.url == "https://store.steampowered.com/bundle/232/"
    assert embed.footer.text.startswith("Bundle 232")
    assert "💳 Mercado Pago" in [f.name for f in embed.fields]
