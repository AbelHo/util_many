---
name: candle-stick-url
description: "Generate, explain, validate, or troubleshoot shareable OHLCV candlestick-chart URLs for this repository. Use when a user asks to turn a CSV, trading-data file, or in-memory timestamp/open/high/low/close[/volume] arrays into a link for ohlcv_url_chart.html, choose Base64url versus dense encoding, set a chart symbol or root URL, open the result, or diagnose CSV and URL-decoding problems."
---

# Candle-Stick URL

Generate links that carry the complete OHLCV dataset in the URL fragment and open in the repository's static candlestick + volume chart. Use the existing Python helper as the source of truth; do not reimplement its binary codec in shell, JavaScript, or ad hoc Python.

## Locate the utility

Resolve the repository root before invoking anything. The project-relative helper is:

```text
helper/ohlcv_url_chart.html/ohlcv_url.py
```

The default chart root is:

```text
https://abelho.github.io/util_many/ohlcv_url_chart.html
```

If the user supplies a different deployment URL, pass it as a hash-free `--root` value. Do not append `#d=...` yourself.

## Choose the workflow

1. Use the CLI for a CSV file.
2. Use `generate_url(...)` for arrays already available in Python.
3. For inline CSV text, write it only to a temporary file or parse it into arrays, then use one of the same two paths. Do not create a permanent sample or data file unless the user asks for one.
4. Use the browser chart as a fallback when Python is unavailable: open `ohlcv_url_chart.html`, drop/select the CSV, and copy the generated URL.

## Generate from CSV

Run from the repository root:

```bash
python3 helper/ohlcv_url_chart.html/ohlcv_url.py DATA.csv
```

Add options only when requested or useful:

```bash
python3 helper/ohlcv_url_chart.html/ohlcv_url.py DATA.csv \
  --root https://host.example/ohlcv_url_chart.html \
  --symbol AAPL \
  --dense
```

- Print and return the complete stdout URL exactly as produced.
- Use `--symbol NAME` for the chart title. Without it, the CLI uses the CSV filename stem.
- Prefer default Base64url for links shared through chat, Markdown, or email. Use `--dense` when the user wants the shortest link or the dataset produces a long URL; it adds the `&e=1` marker required by the chart.
- Use `--open` only when the user explicitly asks to open the chart in the default browser. It has an external side effect; otherwise return the URL without opening anything.
- Keep the URL's `#d=...`, `&e=1`, and optional `&s=...` fragment intact. Do not decode, line-wrap, normalize, or re-encode it before handing it off.

The helper uses only the Python standard library. No pip install or build step is required.

## Generate from in-memory arrays

Import the helper from its directory and pass equal-length arrays in oldest-to-newest order:

```python
import sys
sys.path.insert(0, "helper/ohlcv_url_chart.html")
from ohlcv_url import generate_url

url = generate_url(
    timestamps, opens, highs, lows, closes, volumes,
    root_url="https://abelho.github.io/util_many/ohlcv_url_chart.html",
    symbol="AAPL",
    dense=False,
)
print(url)
```

`timestamps` may contain epoch seconds, epoch milliseconds, `datetime` objects, ISO/date-time strings, or `YYYY-MM-DD HH:MM:SS` strings. Naive date-times are interpreted as UTC. Pass `volumes=None` to omit the volume trace; otherwise its length must match the OHLC arrays.

Use `price_decimals=` or `vol_decimals=` only when the caller needs an explicit precision. Otherwise the helper detects precision and clamps it to at most 9 decimal places. The packed result is lossless within that stored precision.

## Validate input before running

Accept CSV headers case-insensitively. Require one time column and all four price columns; allow volume to be absent:

| Field | Accepted headers |
|---|---|
| time | `timestamp`, `datetime`, `dts`, `date`, `time` |
| open | `open`, `o` |
| high | `high`, `h` |
| low | `low`, `l` |
| close | `close`, `c` |
| volume | `volume`, `vol`, `v` |

Before invoking the helper, check the following when the user has not supplied a clearly valid file:

- The file has a header and at least one usable data row.
- Every required column is present and numeric price values are parseable.
- Timestamps are parseable as ISO/date-time or epoch seconds/milliseconds.
- Rows are ordered oldest-to-newest unless the user intentionally requests another order. The helper preserves input order; it does not sort bars.
- Missing or nonnumeric volume is not silently treated as a meaningful value. The current file parser converts an invalid volume token to `0.0`; mention this behavior if it affects the result and ask before correcting source data.

Do not invent, interpolate, sort, or silently drop market data. If a required value or timestamp is ambiguous, report the exact validation error and ask for corrected input.

## Explain or troubleshoot a URL

Treat the URL fragment as the data-bearing part. The format is:

```text
<root>#d=<payload>[&e=1][&s=<url-encoded-symbol>]
```

- Default payloads are unpadded Base64url over raw DEFLATE bytes.
- Dense payloads use the chart's custom 73-character alphabet and require `e=1`.
- `s` is URL-encoded display text and is optional.
- The chart decodes the fragment client-side; the dataset does not need a server endpoint.

When diagnosing a failed link, check in this order:

1. Preserve the full fragment, especially `&` separators and the leading `#`.
2. Confirm that a dense payload has `e=1` and that a default payload does not need it.
3. Confirm that the URL root points to the actual `ohlcv_url_chart.html` deployment.
4. Regenerate from the original CSV with the helper instead of editing the payload by hand.
5. If a link is very long, try `--dense` or reduce the number of rows only with the user's approval. The chart warns around 16,000 characters and strongly warns around 64,000 characters; chat applications and browsers may impose their own limits.

Do not claim that a URL is private merely because its fragment is normally omitted from HTTP requests. Anyone who receives the link can inspect the data, and the URL may remain in browser history, logs, or copied messages. Warn users before embedding confidential or personally identifying data.

## Deliver the result

Return the generated URL prominently, plus only the useful context: row count if known, symbol, encoding, and any validation or URL-length warning. For very long URLs, place the exact value in a fenced `text` block so Markdown does not alter it. State that opening the URL renders the Plotly candlestick chart and an optional volume subplot with no backend.

If generation fails, preserve the helper's error message, identify the offending input category, and provide the smallest correction needed. Never substitute a guessed URL.

## Compatibility reference

Read [references/ohlcv-url-spec.md](references/ohlcv-url-spec.md) when implementing another generator, comparing Python/C#/browser output, or investigating a codec mismatch. The reference records the exact v1 container and interoperability constraints; the repository helper remains the preferred generator.
