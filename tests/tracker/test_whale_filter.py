from whale_tracker.tracker.whales.filter import select_leaderboard_candidates


def test_select_leaderboard_candidates_unions_pnl_and_volume_wallets() -> None:
    pnl_entries = {
        "wallet-pnl": {"proxyWallet": "wallet-pnl", "pnl": 100},
        "wallet-both": {"proxyWallet": "wallet-both", "pnl": 50},
    }
    volume_entries = {
        "wallet-both": {"proxyWallet": "wallet-both", "vol": 1_000},
        "wallet-volume": {"proxyWallet": "wallet-volume", "vol": 500},
    }

    candidates = select_leaderboard_candidates(
        pnl_entries=pnl_entries,
        volume_entries=volume_entries,
        wallet_count=2,
    )

    assert [candidate.proxy_wallet for candidate in candidates] == [
        "wallet-pnl",
        "wallet-both",
        "wallet-volume",
    ]
    assert candidates[0].pnl_entry == pnl_entries["wallet-pnl"]
    assert candidates[0].volume_entry is None
    assert candidates[1].pnl_entry == pnl_entries["wallet-both"]
    assert candidates[1].volume_entry == volume_entries["wallet-both"]
    assert candidates[2].pnl_entry is None
    assert candidates[2].volume_entry == volume_entries["wallet-volume"]
    assert all(candidate.candidate_collection_complete for candidate in candidates)


def test_select_leaderboard_candidates_marks_incomplete_short_collection() -> None:
    candidates = select_leaderboard_candidates(
        pnl_entries={"wallet-pnl": {"proxyWallet": "wallet-pnl"}},
        volume_entries={},
        wallet_count=2,
    )

    assert [candidate.proxy_wallet for candidate in candidates] == ["wallet-pnl"]
    assert candidates[0].candidate_collection_complete is False
