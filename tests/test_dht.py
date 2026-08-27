import asyncio

from openclaw_mesh.network.dht import (
    Contact,
    KademliaDHT,
    RoutingTable,
    hash_key,
    xor_distance,
)


def test_dht_xor_distance_and_hashing():
    key1 = hash_key("node_alpha")
    key2 = hash_key("node_beta")
    assert len(key1) == 40
    assert len(key2) == 40

    d = xor_distance(key1, key2)
    assert d > 0
    assert xor_distance(key1, key1) == 0


def test_dht_routing_table_and_buckets():
    local_id = hash_key("local_agent")
    rt = RoutingTable(local_id, k=5)

    contacts = [
        Contact(node_id=hash_key(f"peer_{i}"), host="192.168.1.10", port=8770 + i, name=f"peer-{i}")
        for i in range(10)
    ]

    for c in contacts:
        rt.add_contact(c)

    assert rt.count_contacts() == 10

    # Recherche des plus proches
    closest = rt.find_closest_contacts(hash_key("target_search"), count=3)
    assert len(closest) == 3


def test_dht_local_storage_and_skill_advertising():
    dht = KademliaDHT(name="dht-paris")

    # 1. Enregistrement et récupération clé-valeur
    dht.store_local("config:cluster", {"replicas": 3, "tls": True})
    val = dht.get_local("config:cluster")
    assert val == {"replicas": 3, "tls": True}

    # 2. Publication d'une compétence IA
    skill_key = dht.advertise_skill(
        "vlm_analyze", {"host": "10.0.0.5", "port": 8770, "gpu": "RTX 4090"}
    )
    assert len(skill_key) == 40

    # 3. Résolution de la compétence
    res = dht.lookup_skill("vlm_analyze")
    assert res is not None
    assert res["gpu"] == "RTX 4090"


def _make_node(name, port):
    return KademliaDHT(name=name, host="127.0.0.1", port=port)


def test_dht_network_ping_and_bootstrap():
    """Deux nœuds UDP s'échangent un ping et s'inscrivent mutuellement dans la table de routage."""

    async def _run():
        node_a = _make_node("dht-a", 8781)
        node_b = _make_node("dht-b", 8782)
        host_a, port_a = await node_a.start_network()
        host_b, port_b = await node_b.start_network()

        contact_b = Contact(node_id=node_b.node_id, host=host_b, port=port_b, name="dht-b")
        reachable = await node_a.bootstrap([contact_b], timeout=2.0)
        assert reachable == 1
        assert node_a.routing_table.count_contacts() >= 1

        assert await node_a.ping(contact_b, timeout=2.0) is True
        assert node_a.routing_table.count_contacts() >= 1

        await node_a.stop_network()
        await node_b.stop_network()

    asyncio.run(_run())


def test_dht_network_store_and_find_value():
    """Un nœud dépose une valeur et un pair la retrouve via FIND_VALUE distribué."""

    async def _run():
        node_a = _make_node("dht-a", 8783)
        node_b = _make_node("dht-b", 8784)
        await node_a.start_network()
        host_b, port_b = await node_b.start_network()

        # A join B
        await node_a.bootstrap(
            [Contact(node_id=node_b.node_id, host=host_b, port=port_b, name="dht-b")]
        )

        payload = {"host": "10.0.0.5", "port": 8770, "gpu": "RTX 4090"}
        stored = await node_b.store_distributed("skill:llm", payload, ttl=60)
        assert stored is True

        # A doit retrouver la valeur déployée sur B via recherche distribuée
        found = await node_a.find_value_distributed("skill:llm", timeout=2.0)
        assert found == payload

        await node_a.stop_network()
        await node_b.stop_network()

    asyncio.run(_run())


def test_dht_network_multihop_lookup():
    """Recherche distribuée routée A -> B -> C où la valeur n'existe que sur C."""

    async def _run():
        node_a = _make_node("dht-a", 8785)
        node_b = _make_node("dht-b", 8786)
        node_c = _make_node("dht-c", 8787)
        _, port_a = await node_a.start_network()
        host_b, port_b = await node_b.start_network()
        host_c, port_c = await node_c.start_network()

        # Topologie en chaîne : A -> B -> C
        await node_a.bootstrap(
            [Contact(node_id=node_b.node_id, host=host_b, port=port_b, name="dht-b")]
        )
        await node_c.bootstrap(
            [Contact(node_id=node_b.node_id, host=host_b, port=port_b, name="dht-b")]
        )
        await node_b.bootstrap(
            [
                Contact(node_id=node_a.node_id, host="127.0.0.1", port=port_a, name="dht-a"),
                Contact(node_id=node_c.node_id, host=host_c, port=port_c, name="dht-c"),
            ]
        )

        # La valeur n'est déposée QUE sur C (locale) — A doit la retrouver en routant via B.
        payload = {"node": "c", "gpu": "Apple M3"}
        node_c.store_local("skill:vlm", payload)

        found = await node_a.find_value_distributed("skill:vlm", timeout=2.0)
        assert found == payload

        # find_node_distributed doit renvoyer C comme contact proche.
        target_id = hash_key("skill:vlm")
        closest = await node_a.find_node_distributed(target_id, timeout=2.0)
        ids = {c.node_id for c in closest}
        assert node_c.node_id in ids

        await node_a.stop_network()
        await node_b.stop_network()
        await node_c.stop_network()

    asyncio.run(_run())
