#!/usr/bin/env python3
"""
ohlcv_url.py - Generate a shareable OHLCV-chart URL from trading data.

Produces the exact #d=... payload understood by ``ohlcv_url_chart.html`` so the
whole dataset travels inside the link (no server). The data pipeline mirrors the
web app:

    1. Columnar binary packing
         - regular timestamps  -> start + interval + count
           irregular           -> start + zigzag-varint deltas (epoch seconds)
         - O/H/L/C quantized to integer ticks (x10^decimals, lossless),
           then per-column delta -> zigzag -> varint
         - volume quantized + varint (raw or delta, whichever is smaller)
    2. raw DEFLATE  (zlib, wbits=-15)  == browser CompressionStream('deflate-raw')
    3. URL-safe text in the hash fragment:
         - default : Base64url
         - dense   : custom 73-char URL-fragment-safe alphabet (~3-5% shorter)

Use as a module:

    from ohlcv_url import generate_url_from_file, generate_url
    url = generate_url_from_file("data.csv")                 # default root URL
    url = generate_url_from_file("data.csv", root_url="https://host/x.html",
                                 dense=True, symbol="AAPL")
    url = generate_url(timestamps, opens, highs, lows, closes, volumes)

Use as a CLI:

    python ohlcv_url.py data.csv
    python ohlcv_url.py data.csv --root https://host/ohlcv_url_chart.html --dense
    python ohlcv_url.py data.csv --symbol AAPL --open      # also open in browser

Accepted CSV headers (case-insensitive):
    time   : timestamp | datetime | dts | date | time
    prices : open|o, high|h, low|l, close|c
    volume : volume | vol | v          (optional)
    timestamps may be ISO dates, "YYYY-MM-DD HH:MM:SS", or epoch seconds/ms.
    Naive (no-timezone) timestamps are interpreted as UTC.
"""

from __future__ import annotations

import math
import zlib
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

DEFAULT_ROOT_URL = "https://abelho.github.io/util_many/ohlcv_url_chart.html"

# 73-char alphabet: all RFC-3986 fragment-safe and free of the '&'/'=' hash
# separators. Must match DENSE_ALPHABET in ohlcv_url_chart.html exactly.
DENSE_ALPHABET = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                  "abcdefghijklmnopqrstuvwxyz-._~!$*+/:@")
_DENSE_N = len(DENSE_ALPHABET)

_TIME_ALIASES = ("timestamp", "datetime", "dts", "date", "time")
_OPEN_ALIASES = ("open", "o")
_HIGH_ALIASES = ("high", "h")
_LOW_ALIASES = ("low", "l")
_CLOSE_ALIASES = ("close", "c")
_VOL_ALIASES = ("volume", "vol", "v")


# --------------------------------------------------------------------------- #
# Low-level integer codecs (match the JS implementation)
# --------------------------------------------------------------------------- #
def _write_varint(out: bytearray, n: int) -> None:
    """Unsigned LEB128."""
    n = int(n)
    while n >= 128:
        out.append((n % 128) + 128)
        n //= 128
    out.append(n)


def _zigzag(n: int) -> int:
    return n * 2 if n >= 0 else n * -2 - 1


def _round_half_up(x: float) -> int:
    """Match JS Math.round (round half toward +Infinity)."""
    return math.floor(x + 0.5)


# --------------------------------------------------------------------------- #
# Stage 1 - columnar binary packing
# --------------------------------------------------------------------------- #
def _pack_binary(ts: Sequence[int], o, h, l, c, vol,
                 price_decimals: int, vol_decimals: int,
                 has_volume: bool, vol_float: bool) -> bytes:
    n = len(ts)
    pscale = 10 ** price_decimals
    vscale = 10 ** vol_decimals

    ts_regular = True
    interval = ts[1] - ts[0] if n >= 2 else 0
    for i in range(2, n):
        if ts[i] - ts[i - 1] != interval:
            ts_regular = False
            break

    out = bytearray()
    out += b"O1"          # magic
    out.append(1)         # version
    flags_idx = len(out)
    out.append(0)         # flags placeholder
    out.append(price_decimals & 0xFF)
    out.append(vol_decimals & 0xFF)
    _write_varint(out, n)

    if ts_regular:
        _write_varint(out, ts[0] if n else 0)
        _write_varint(out, interval if interval > 0 else 0)
    else:
        _write_varint(out, ts[0])
        for i in range(1, n):
            _write_varint(out, _zigzag(ts[i] - ts[i - 1]))

    for col in (o, h, l, c):
        prev = 0
        for i in range(n):
            v = _round_half_up(col[i] * pscale)
            _write_varint(out, _zigzag(v - prev))
            prev = v

    vol_delta = False
    if has_volume:
        scaled = [_round_half_up((vol[i] or 0) * vscale) for i in range(n)]
        raw = bytearray()
        delta = bytearray()
        prev = 0
        for i in range(n):
            _write_varint(raw, scaled[i])
            _write_varint(delta, _zigzag(scaled[i] - prev))
            prev = scaled[i]
        if len(delta) < len(raw):
            vol_delta = True
            out += delta
        else:
            out += raw

    flags = 0
    if ts_regular:
        flags |= 1
    if has_volume:
        flags |= 2
    if vol_float:
        flags |= 4
    if vol_delta:
        flags |= 8
    out[flags_idx] = flags
    return bytes(out)


# --------------------------------------------------------------------------- #
# Stage 2 - raw DEFLATE
# --------------------------------------------------------------------------- #
def _deflate_raw(data: bytes) -> bytes:
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return co.compress(data) + co.flush()


# --------------------------------------------------------------------------- #
# Stage 3 - URL-safe text encodings
# --------------------------------------------------------------------------- #
def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _dense_encode(data: bytes) -> str:
    lead = 0
    while lead < len(data) and data[lead] == 0:
        lead += 1
    num = int.from_bytes(data[lead:], "big") if lead < len(data) else 0
    digits = ""
    while num > 0:
        digits = DENSE_ALPHABET[num % _DENSE_N] + digits
        num //= _DENSE_N
    return DENSE_ALPHABET[lead // _DENSE_N] + DENSE_ALPHABET[lead % _DENSE_N] + digits


# --------------------------------------------------------------------------- #
# Parsing / detection helpers
# --------------------------------------------------------------------------- #
def _decimals_of(token: str) -> int:
    token = token.strip()
    if "." not in token:
        return 0
    frac = token.rsplit(".", 1)[1]
    return len(frac) if frac.isdigit() else 0


def _detect_decimals_floats(values: Iterable[float]) -> int:
    d = 0
    for v in values:
        k = 0
        while k < 9 and abs(v * (10 ** k) - round(v * (10 ** k))) > 1e-9:
            k += 1
        d = max(d, k)
    return d


def to_epoch_seconds(value) -> int:
    """Accept int/float (s or ms), datetime, or string; return epoch seconds (UTC)."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(round(dt.timestamp()))
    if isinstance(value, (int, float)):
        n = float(value)
        return int(round(n / 1000.0)) if abs(n) >= 1e12 else int(round(n))
    s = str(value).strip()
    if s.isdigit():
        return int(s) // 1000 if len(s) >= 12 else int(s)
    t = s.replace(" ", "T", 1)
    utc = False
    if t[-1:] in ("Z", "z"):
        t = t[:-1]
        utc = True
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        dt = datetime.fromisoformat(t.split("T")[0])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elif utc:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(round(dt.timestamp()))


def _find_col(header: List[str], aliases: Sequence[str]) -> int:
    for i, h in enumerate(header):
        if h in aliases:
            return i
    return -1


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _encode(ts, o, h, l, c, vol, price_decimals, vol_decimals,
            has_volume, vol_float, root_url, dense, symbol) -> str:
    from urllib.parse import quote
    binary = _pack_binary(ts, o, h, l, c, vol, price_decimals, vol_decimals,
                          has_volume, vol_float)
    comp = _deflate_raw(binary)
    payload = _dense_encode(comp) if dense else _b64url_encode(comp)
    frag = "#d=" + payload
    if dense:
        frag += "&e=1"
    if symbol:
        frag += "&s=" + quote(str(symbol), safe="")
    return (root_url or DEFAULT_ROOT_URL) + frag


def generate_url(timestamps: Sequence,
                 opens: Sequence[float], highs: Sequence[float],
                 lows: Sequence[float], closes: Sequence[float],
                 volumes: Optional[Sequence[float]] = None,
                 root_url: str = DEFAULT_ROOT_URL,
                 dense: bool = False,
                 symbol: Optional[str] = None,
                 price_decimals: Optional[int] = None,
                 vol_decimals: Optional[int] = None) -> str:
    """Build a chart URL from in-memory OHLCV arrays.

    timestamps may be epoch seconds/ms, datetime objects, or strings.
    Decimal precision is auto-detected from the values unless given.
    """
    ts = [to_epoch_seconds(t) for t in timestamps]
    n = len(ts)
    if not (len(opens) == len(highs) == len(lows) == len(closes) == n):
        raise ValueError("All OHLC arrays must have the same length as timestamps.")
    has_volume = volumes is not None
    if has_volume and len(volumes) != n:
        raise ValueError("volumes must match the number of rows.")

    if price_decimals is None:
        price_decimals = _detect_decimals_floats(
            list(opens) + list(highs) + list(lows) + list(closes))
    price_decimals = max(0, min(price_decimals, 9))

    vol_float = False
    if vol_decimals is None and has_volume:
        vol_decimals = _detect_decimals_floats(volumes)
    vol_decimals = max(0, min(vol_decimals or 0, 9))
    if has_volume:
        vol_float = vol_decimals > 0

    return _encode(ts, opens, highs, lows, closes, volumes,
                   price_decimals, vol_decimals, has_volume, vol_float,
                   root_url, dense, symbol)


def parse_csv_file(path: str):
    """Return (ts, o, h, l, c, vol|None, price_decimals, vol_decimals,
    has_volume, vol_float) detected from a CSV file (string-accurate decimals)."""
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh) if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        raise ValueError("CSV has no data rows.")
    header = [c.strip().lower() for c in rows[0]]
    ti = _find_col(header, _TIME_ALIASES)
    oi = _find_col(header, _OPEN_ALIASES)
    hi = _find_col(header, _HIGH_ALIASES)
    li = _find_col(header, _LOW_ALIASES)
    ci = _find_col(header, _CLOSE_ALIASES)
    if ti < 0:
        raise ValueError("No time column (timestamp/datetime/dts/date/time).")
    if min(oi, hi, li, ci) < 0:
        raise ValueError("Need open, high, low and close columns.")
    vi = _find_col(header, _VOL_ALIASES)
    has_volume = vi >= 0

    need = max(ti, oi, hi, li, ci, vi if has_volume else 0)
    data = [r for r in rows[1:] if len(r) > need and r[ti].strip() != ""]
    if not data:
        raise ValueError("CSV has no usable data rows.")

    price_decimals = 0
    for r in data:
        for idx in (oi, hi, li, ci):
            price_decimals = max(price_decimals, _decimals_of(r[idx]))
    price_decimals = min(price_decimals, 9)

    vol_decimals = 0
    vol_float = False
    if has_volume:
        for r in data:
            d = _decimals_of(r[vi])
            if d > 0:
                vol_float = True
            vol_decimals = max(vol_decimals, d)
        vol_decimals = min(vol_decimals, 9)

    ts, o, h, l, c = [], [], [], [], []
    vol = [] if has_volume else None
    for r in data:
        ts.append(to_epoch_seconds(r[ti]))
        o.append(float(r[oi]))
        h.append(float(r[hi]))
        l.append(float(r[li]))
        c.append(float(r[ci]))
        if has_volume:
            try:
                vol.append(float(r[vi]))
            except ValueError:
                vol.append(0.0)
    return ts, o, h, l, c, vol, price_decimals, vol_decimals, has_volume, vol_float


def generate_url_from_file(path: str,
                           root_url: str = DEFAULT_ROOT_URL,
                           dense: bool = False,
                           symbol: Optional[str] = None) -> str:
    """Build a chart URL from a CSV file. Decimals are detected from the text
    (so the URL is byte-faithful to the file's precision)."""
    (ts, o, h, l, c, vol, price_decimals, vol_decimals,
     has_volume, vol_float) = parse_csv_file(path)
    if symbol is None:
        import os
        symbol = os.path.splitext(os.path.basename(path))[0]
    return _encode(ts, o, h, l, c, vol, price_decimals, vol_decimals,
                   has_volume, vol_float, root_url, dense, symbol)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate a shareable OHLCV-chart URL from a CSV file.")
    parser.add_argument("csv", help="Path to an OHLCV CSV file.")
    parser.add_argument("--root", default=DEFAULT_ROOT_URL,
                        help="Root chart URL (default: %(default)s)")
    parser.add_argument("--dense", action="store_true",
                        help="Use the max-density URL encoding (~3-5%% shorter).")
    parser.add_argument("--symbol", default=None,
                        help="Chart title/symbol (default: CSV filename).")
    parser.add_argument("--open", action="store_true",
                        help="Open the generated URL in the default browser.")
    args = parser.parse_args(argv)

    url = generate_url_from_file(args.csv, root_url=args.root,
                                 dense=args.dense, symbol=args.symbol)
    print(url)
    if args.open:
        import webbrowser
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
