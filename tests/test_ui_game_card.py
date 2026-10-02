from datetime import date

from helpers import make_item

from vapora.pricing import ExchangeRates, PesoConverter, Taxes
from vapora.sales import AUTUMN_COLOR, SteamSale
from vapora.steam import ItemKind, Reviews
from vapora.ui.game_card import build_description, build_game_card, describe_contents
from vapora.ui.style import BRAND_COLOR


def field_names(embed) -> list[str]:
    return [field.name for field in embed.fields]


def test_card_of_a_game_on_sale(converter: PesoConverter):
    item = make_item(
        1888930,
        "The Last of Us™ Parte I",
        price_cents=2999,
        initial_cents=5999,
        discount=50,
        description="Una aventura.",
        image_url="https://example.com/header.jpg",
        release_date="28 MAR 2023",
        genres=("Acción", "Aventura"),
        developers=("Naughty Dog LLC",),
        reviews=Reviews("Muy positivas", 100, 85),
    )
    embed = build_game_card(item, converter)

    assert embed.title == "🇦🇷 The Last of Us™ Parte I"
    assert embed.url == "https://store.steampowered.com/app/1888930/"
    assert embed.description == "Una aventura.\n\n🎭 Acción · Aventura"
    assert field_names(embed) == [
        "💵 Precio Steam (AR)",
        "💳 Mercado Pago",
        "🟣 ARQ",
        "⭐ Reseñas",
        "📅 Lanzamiento",
        "🛠️ Desarrollador",
    ]
    assert embed.fields[0].value == "**USD 29,99**\n~~USD 59,99~~ (-50%)"
    assert embed.fields[1].value == "**$ 56.246,24**"
    assert embed.fields[2].value == "**$ 48.686,97**"
    assert embed.image.url == "https://example.com/header.jpg"
    assert embed.footer.text == (
        "AppID 1888930 • Datos de Steam\nOficial $ 1.550,00 · ARQ $ 1.623,44 · IVA 21% (sin IIBB)"
    )


def test_card_without_exchange_rates_shows_only_steam_price():
    no_rates = PesoConverter(ExchangeRates(), Taxes())
    for converter in (None, no_rates):
        embed = build_game_card(make_item(), converter)
        assert field_names(embed) == ["💵 Precio Steam (AR)"]
        assert embed.footer.text == "AppID 1 • Datos de Steam"


def test_free_game_has_no_peso_prices(converter: PesoConverter):
    embed = build_game_card(make_item(730, "Counter-Strike 2", price_cents=None, is_free=True), converter)
    assert field_names(embed) == ["💵 Precio Steam (AR)"]
    assert embed.fields[0].value == "**Gratis**"


def test_unreleased_game_is_labeled_coming_soon():
    embed = build_game_card(make_item(release_date="Próximamente", coming_soon=True))
    assert "📅 Próximamente" in field_names(embed)


def test_card_shows_at_most_two_developers_and_four_genres():
    item = make_item(developers=("A", "B", "C"), genres=("1", "2", "3", "4", "5"))
    embed = build_game_card(item)
    assert embed.fields[-1].value == "A, B"
    assert embed.description == "🎭 1 · 2 · 3 · 4"


def test_argentine_game_is_highlighted_first():
    description = build_description(make_item(argentine=True, description="Un juego."))
    assert description == "🧉 **¡Juego argentino!** Hecho por un estudio de acá 💙\n\nUn juego."
    assert build_description(make_item()) is None


def test_dlc_names_its_base_game():
    assert describe_contents(make_item(dlc_of="ELDEN RING")) == "🧩 DLC de **ELDEN RING**"


def test_package_lists_what_it_includes():
    names = tuple(f"Juego {i}" for i in range(1, 8))
    package = make_item(469, "The Orange Box", kind=ItemKind.PACKAGE, included=names, included_count=7)
    assert (
        describe_contents(package) == "📦 Paquete con 7 productos: Juego 1, Juego 2, Juego 3, Juego 4 y 3 más"
    )


def test_bundle_only_counts_products():
    bundle = make_item(232, "Valve Complete Pack", kind=ItemKind.BUNDLE, included_count=18)
    assert describe_contents(bundle) == "📦 Bundle con 18 productos"
    assert describe_contents(make_item(kind=ItemKind.BUNDLE, included_count=1)) == "📦 Bundle con 1 producto"


def test_plain_game_has_no_contents_line():
    assert describe_contents(make_item()) is None


def test_bundle_card_links_to_the_bundle(converter: PesoConverter):
    bundle = make_item(232, "Valve Complete Pack", kind=ItemKind.BUNDLE, price_cents=6824, included_count=2)
    embed = build_game_card(bundle, converter)
    assert embed.url == "https://store.steampowered.com/bundle/232/"
    assert embed.footer.text.startswith("Bundle 232 • Datos de Steam")
    assert "💳 Mercado Pago" in field_names(embed)


def test_card_takes_the_color_of_the_running_sale():
    autumn = SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂", AUTUMN_COLOR)
    next_fest = SteamSale("Steam Next Fest", date(2026, 10, 19), date(2026, 10, 26), "🧪")
    assert build_game_card(make_item(), sale=autumn).color.value == 0xE67E22
    assert build_game_card(make_item(), sale=next_fest).color == BRAND_COLOR  # sin color propio
    assert build_game_card(make_item()).color == BRAND_COLOR  # sin rebaja
