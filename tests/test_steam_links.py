from vapora.steam import ItemKind, ItemRef, extract_item_refs


def test_single_link():
    text = "Miren https://store.steampowered.com/app/1888930/The_Last_of_Us_Parte_I/"
    assert extract_item_refs(text) == [ItemRef.app(1888930)]


def test_multiple_links_keep_their_order():
    text = (
        "https://store.steampowered.com/app/1888930/foo "
        "https://store.steampowered.com/app/730/CounterStrike_2/"
    )
    assert extract_item_refs(text) == [ItemRef.app(1888930), ItemRef.app(730)]


def test_duplicate_links_are_reported_once():
    text = "https://store.steampowered.com/app/730/foo https://store.steampowered.com/app/730/bar"
    assert extract_item_refs(text) == [ItemRef.app(730)]


def test_link_without_trailing_slash():
    assert extract_item_refs("https://store.steampowered.com/app/730") == [ItemRef.app(730)]


def test_text_without_links():
    assert extract_item_refs("hola, nada por acá") == []


def test_packages_and_bundles():
    text = (
        "https://store.steampowered.com/bundle/232/Valve_Complete_Pack/ "
        "https://store.steampowered.com/sub/469/ "
        "https://store.steampowered.com/app/730/"
    )
    assert extract_item_refs(text) == [
        ItemRef(ItemKind.BUNDLE, 232),
        ItemRef(ItemKind.PACKAGE, 469),
        ItemRef.app(730),
    ]


def test_same_id_of_different_kind_is_not_a_duplicate():
    text = "https://store.steampowered.com/app/232/ https://store.steampowered.com/bundle/232/"
    assert extract_item_refs(text) == [ItemRef.app(232), ItemRef(ItemKind.BUNDLE, 232)]


def test_link_kind_is_case_insensitive():
    assert extract_item_refs("HTTPS://STORE.STEAMPOWERED.COM/APP/730/") == [ItemRef.app(730)]


def test_ref_url():
    assert ItemRef(ItemKind.BUNDLE, 232).url == "https://store.steampowered.com/bundle/232/"
    assert ItemRef(ItemKind.PACKAGE, 469).url == "https://store.steampowered.com/sub/469/"
