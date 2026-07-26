# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-26

### Added

- Initial release.
- Decorator API (`@limiter.limit("5/minute")`) and dependency API
  (`Depends(RateLimiter("5/minute"))`).
- Pluggable async storage backends: in-memory (default), Redis, Memcached and
  SQLite, installed via optional extras.
- Strategies: fixed window (default), sliding window, moving window and token
  bucket with configurable burst.
- Key strategies: per-IP (default), per-user with a configurable missing-user
  policy, and global limits.
- Escalating temporary bans with a configurable breach threshold and penalty.
- Runtime editing of limits without restarting the application.
- Configurable `429` responses and rate limit headers.
- Exemptions by IP, key, or predicate.
- WebSocket rate limiting.
- Fully typed (`py.typed`), checked with mypy in strict mode.

[Unreleased]: https://github.com/Yura2108/fastapi-limitex/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Yura2108/fastapi-limitex/releases/tag/v0.1.0
