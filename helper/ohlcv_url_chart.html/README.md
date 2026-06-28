# helper/ — OHLCV chart URL generators

Generate a shareable URL for [`ohlcv_url_chart.html`](../ohlcv_url_chart.html)
outside the browser. The whole OHLCV dataset is packed into the URL hash
(`#d=…`); opening the link renders the candlestick + volume chart with no server.

Both generators emit the identical format (columnar delta/varint packing →
raw DEFLATE → Base64url, or an optional `--dense` encoding) and default to the
root URL `https://abelho.github.io/util_many/ohlcv_url_chart.html`.

## Accepted CSV
Headers are case-insensitive; the time column and OHLC are required, volume is optional:

| Purpose | Accepted header names |
|---|---|
| time   | `timestamp` · `datetime` · `dts` · `date` · `time` |
| open   | `open` · `o` |
| high   | `high` · `h` |
| low    | `low` · `l` |
| close  | `close` · `c` |
| volume | `volume` · `vol` · `v` |

Timestamps may be ISO dates, `YYYY-MM-DD HH:MM:SS`, or epoch seconds/ms.
Naive (no-timezone) timestamps are interpreted as **UTC**.

```csv
timestamp,open,high,low,close,volume
2024-01-02,185.64,186.95,185.32,185.92,52000000
2024-01-03,184.22,185.88,183.43,184.25,58400000
```

## Python — [`ohlcv_url.py`](ohlcv_url.py)
Standard library only (no pip installs).

CLI:
```bash
python ohlcv_url.py data.csv
python ohlcv_url.py data.csv --root https://host/ohlcv_url_chart.html --dense --symbol AAPL
python ohlcv_url.py data.csv --open        # also open in the default browser
```

Module:
```python
from ohlcv_url import generate_url_from_file, generate_url

url = generate_url_from_file("data.csv")                      # default root URL
url = generate_url_from_file("data.csv", dense=True, symbol="AAPL")

# From in-memory arrays (timestamps: epoch s/ms, datetime, or strings):
url = generate_url(timestamps, opens, highs, lows, closes, volumes,
                   root_url="https://host/ohlcv_url_chart.html", symbol="BTCUSD")
```

## C# / NinjaTrader NinjaScript — [`OhlcvUrl.cs`](OhlcvUrl.cs)
BCL only (`System.IO.Compression`); no `System.Numerics` needed, so it compiles
cleanly inside NinjaTrader 8 (.NET 4.8).

**Use in NinjaScript** — drop `OhlcvUrl.cs` into
`Documents\NinjaTrader 8\bin\Custom\AddOns\` (or paste into the NinjaScript
Editor). The console `Main` is excluded unless the `OHLCV_CLI` symbol is defined,
so there is no entry-point conflict. Then from an indicator/strategy:

```csharp
using OhlcvUrlShare;

int n = CurrentBar + 1;
var t = new DateTime[n]; var o = new double[n]; var h = new double[n];
var l = new double[n];   var c = new double[n]; var v = new double[n];
for (int i = 0; i < n; i++) {            // Bars are newest-first; emit oldest->newest
    int b = CurrentBar - i;
    t[n-1-i] = Time[b];  o[n-1-i] = Open[b];  h[n-1-i] = High[b];
    l[n-1-i] = Low[b];   c[n-1-i] = Close[b]; v[n-1-i] = Volume[b];
}
string url = OhlcvUrl.GenerateUrl(t, o, h, l, c, v, symbol: Instrument.FullName);
Print(url);
```

DateTimes with `Kind == Unspecified` (typical for NinjaTrader bar times) are
treated as UTC, so the chart shows the same wall-clock as the bars.

**Use as a CLI** (standalone console build):
```bash
csc /define:OHLCV_CLI OhlcvUrl.cs
OhlcvUrl data.csv --root https://host/ohlcv_url_chart.html --dense --symbol AAPL
```

## Notes
- Output is **lossless** within the decimal precision present in the data
  (auto-detected per column).
- `dense`/`--dense` uses a 73-char URL-fragment-safe alphabet (~3–5% shorter).
  The default Base64url is the most robust through chat apps, markdown and email.
- Compressed bytes differ slightly between Python (zlib), C# (`DeflateStream`)
  and the browser, but all decode to the same chart — they are interchangeable.
