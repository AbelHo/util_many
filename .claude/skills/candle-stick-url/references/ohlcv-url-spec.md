# OHLCV URL specification

Use this reference only when a task needs codec-level interoperability or a precise explanation of the generated link. For normal URL generation, call `helper/ohlcv_url_chart.html/ohlcv_url.py` instead.

## Source of truth

- Python implementation: `helper/ohlcv_url_chart.html/ohlcv_url.py`
- Browser decoder/encoder: `ohlcv_url_chart.html`
- Optional BCL/NinjaTrader implementation: `helper/ohlcv_url_chart.html/OhlcvUrl.cs`

All three implementations target the same payload format and can decode one another's output after compression and text encoding are reversed.

## Pipeline

1. Normalize timestamps to integer epoch seconds.
2. Quantize OHLC values to integer ticks using `10 ** price_decimals`.
3. Pack columns into the v1 binary container below.
4. Compress with raw DEFLATE, not zlib-wrapped DEFLATE or gzip.
5. Encode the compressed bytes as either unpadded Base64url or dense base-73 text.
6. Append the payload to the chart root as a URL fragment.

Python uses `zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)`. The browser uses `CompressionStream("deflate-raw")`; compressed bytes can differ while decoding to the same model.

## Binary container v1

The bytes before compression are laid out as follows:

```text
magic           2 bytes: ASCII O1
version         1 byte: 1
flags           1 byte:
                  bit 0: timestamps are regular
                  bit 1: volume is present
                  bit 2: volume has fractional precision
                  bit 3: volume uses delta encoding
priceDecimals   1 byte, 0..9
volDecimals     1 byte, 0..9
rowCount        unsigned LEB128 varint
timestamps      regular: start, positive interval
                irregular: start, then n-1 zigzag-varint deltas
OHLC            four columns; each value is a scaled integer delta,
                zigzag encoded and then unsigned LEB128 encoded
volume          if present: raw unsigned varints or delta zigzag-varints
```

Regular timestamps store the first timestamp and interval, but only use that representation when every adjacent interval is identical. The Python and browser implementations use JS-compatible round-half-up behavior for quantization (`floor(x + 0.5)` in Python, `Math.round` in JavaScript).

## Text encodings

Default Base64url uses the RFC 4648 URL-safe alphabet, replaces `+` with `-`, `/` with `_`, and removes trailing `=` padding. It is the safest choice for chat, Markdown, and email.

Dense encoding converts the entire compressed byte string to base 73. Its alphabet must remain exactly:

```text
0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-._~!$*+/:@
```

The first two dense characters record the number of leading zero bytes. The URL must include `&e=1` so the browser selects dense decoding. The alphabet excludes `&` and `=` because those delimit hash parameters.

## Fragment fields

```text
#d=<payload>
#d=<payload>&e=1
#d=<payload>&s=<encodeURIComponent(symbol)>
#d=<payload>&e=1&s=<encodeURIComponent(symbol)>
```

The root URL should be hash-free. The fragment is interpreted entirely in the browser and is not sent as part of the normal HTTP request, but it is still exposed to anyone with the URL and may be retained by clients.

## Precision and volume behavior

CSV parsing detects decimal places from the original text, capped at 9. Array-based generation detects floating-point precision, also capped at 9, unless an explicit precision is supplied. Volume is optional. When volume is present, the encoder chooses raw or delta varints according to which is shorter; fractional volume sets the `volFloat` flag and uses `volDecimals` when reconstructed.

## Canonical examples

CLI:

```bash
python3 helper/ohlcv_url_chart.html/ohlcv_url.py data.csv
python3 helper/ohlcv_url_chart.html/ohlcv_url.py data.csv --dense --symbol AAPL
```

Module:

```python
from ohlcv_url import generate_url_from_file, generate_url

url = generate_url_from_file("data.csv")
url = generate_url_from_file("data.csv", dense=True, symbol="AAPL")
url = generate_url(timestamps, opens, highs, lows, closes, volumes,
                   root_url="https://host/ohlcv_url_chart.html",
                   symbol="BTCUSD")
```
