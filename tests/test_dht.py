import pytest
from openclaw_mesh.network.dht import (
    KademliaDHT,
    Contact,
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
    skill_key = dht.advertise_skill("vlm_analyze", {"host": "10.0.0.5", "port": 8770, "gpu": "RTX 4090"})
    assert len(skill_key) == 40

    # 3. Résolution de la compétence
    res = dht.lookup_skill("vlm_analyze")
    assert res is not None
    assert res["gpu"] == "RTX 4090"
