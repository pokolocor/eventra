"""Swappable data providers (news + market data).

Every provider implements a small abstract interface so a real vendor
(Bloomberg, Polygon, Alpaca, Benzinga, CoinGecko, ...) can replace the bundled
demo providers without touching the agent logic.
"""
