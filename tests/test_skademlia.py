from openclaw_mesh.network.skademlia import (
    SKademliaNodeValidator,
    SKademliaPuzzleSolver,
    count_leading_zero_bits,
)


def test_leading_zero_bits():
    assert count_leading_zero_bits(b"\x00\x00\x0f") == 20
    assert count_leading_zero_bits(b"\x00\xff") == 8
    assert count_leading_zero_bits(b"\x80") == 0


def test_skademlia_static_puzzle_mining_and_verification():
    pub_key = "x25519_test_public_key_abc123"
    # Use low difficulty for fast test execution
    difficulty = 8

    nonce, node_id_hex = SKademliaPuzzleSolver.mine_static_puzzle(
        public_key=pub_key,
        difficulty=difficulty,
        max_iterations=100_000,
    )

    assert len(node_id_hex) == 40  # 160-bit SHA-1 hex

    # Verify valid puzzle
    is_valid = SKademliaPuzzleSolver.verify_static_puzzle(
        public_key=pub_key,
        static_nonce=nonce,
        node_id_hex=node_id_hex,
        difficulty=difficulty,
    )
    assert is_valid is True

    # Tampered nonce should fail
    is_invalid = SKademliaPuzzleSolver.verify_static_puzzle(
        public_key=pub_key,
        static_nonce=nonce + 1,
        node_id_hex=node_id_hex,
        difficulty=difficulty,
    )
    assert is_invalid is False


def test_skademlia_dynamic_puzzle():
    node_id_hex = "a" * 40
    challenge = "random_network_challenge_123"
    difficulty = 6

    nonce = SKademliaPuzzleSolver.solve_dynamic_puzzle(
        node_id_hex, challenge, difficulty=difficulty
    )
    valid = SKademliaPuzzleSolver.verify_dynamic_puzzle(
        node_id_hex, challenge, nonce, difficulty=difficulty
    )
    assert valid is True


def test_skademlia_validator():
    validator = SKademliaNodeValidator(static_difficulty=6, dynamic_difficulty=6)
    pub_key = "validator_pubkey_test"
    nonce, node_id_hex = SKademliaPuzzleSolver.mine_static_puzzle(pub_key, difficulty=6)

    assert validator.validate_peer_identity(node_id_hex, pub_key, nonce) is True
    # Cached validation
    assert validator.validate_peer_identity(node_id_hex, pub_key, nonce) is True
