// ===========================================================================
// OhlcvUrl.cs - Generate a shareable OHLCV-chart URL from trading data.
//
// Produces the exact #d=... payload understood by ohlcv_url_chart.html, so the
// whole dataset travels inside the link (no server). Pipeline mirrors the web
// app and the Python helper (helper/ohlcv_url.py):
//   1. Columnar binary packing (regular timestamps -> start+interval+count;
//      O/H/L/C quantized to integer ticks then delta -> zigzag -> varint;
//      volume varint, raw or delta).
//   2. raw DEFLATE  (System.IO.Compression.DeflateStream == browser
//      CompressionStream('deflate-raw')).
//   3. URL-safe text: Base64url (default) or a 73-char max-density alphabet.
//
// DEPENDENCIES: only the .NET BCL (System, System.IO.Compression). No
// System.Numerics needed - the max-density encoder uses manual big-number
// division so it compiles cleanly inside NinjaTrader 8 (.NET 4.8) NinjaScript.
//
// ------------------------------ USAGE --------------------------------------
// As a library (e.g. from a NinjaScript indicator/strategy):
//
//     using OhlcvUrlShare;
//     // Build arrays from the chart's bars (oldest -> newest):
//     int n = CurrentBar + 1;
//     var t = new DateTime[n]; var o = new double[n]; var h = new double[n];
//     var l = new double[n];   var c = new double[n]; var v = new double[n];
//     for (int i = 0; i < n; i++) {
//         int b = CurrentBar - i;                 // Bars are newest-first
//         t[n-1-i] = Time[b];  o[n-1-i] = Open[b]; h[n-1-i] = High[b];
//         l[n-1-i] = Low[b];   c[n-1-i] = Close[b]; v[n-1-i] = Volume[b];
//     }
//     string url = OhlcvUrl.GenerateUrl(t, o, h, l, c, v, symbol: Instrument.FullName);
//     Print(url);
//
// As a CLI (compile a console build with the OHLCV_CLI symbol defined):
//     csc /define:OHLCV_CLI OhlcvUrl.cs        ->  OhlcvUrl.exe data.csv [--root URL] [--dense] [--symbol NAME]
//
// Accepted CSV headers (case-insensitive):
//     time   : timestamp | datetime | dts | date | time
//     prices : open|o, high|h, low|l, close|c
//     volume : volume | vol | v          (optional)
//   Timestamps may be ISO dates, "YYYY-MM-DD HH:MM:SS", or epoch seconds/ms.
//   Naive (no-timezone) timestamps are interpreted as UTC.
// ===========================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace OhlcvUrlShare
{
    /// <summary>Static utility that turns OHLCV data into a shareable chart URL.</summary>
    public static class OhlcvUrl
    {
        public const string DefaultRootUrl =
            "https://abelho.github.io/util_many/ohlcv_url_chart.html";

        // 73-char alphabet: RFC-3986 fragment-safe and free of the '&'/'='
        // hash separators. Must match DENSE_ALPHABET in ohlcv_url_chart.html.
        private const string DenseAlphabet =
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-._~!$*+/:@";
        private const int DenseN = 73; // == DenseAlphabet.Length

        // ------------------------------------------------------------------ //
        // Public API
        // ------------------------------------------------------------------ //

        /// <summary>Build a chart URL from in-memory arrays (timestamps as epoch seconds).</summary>
        public static string GenerateUrl(
            long[] epochSeconds, double[] open, double[] high, double[] low, double[] close,
            double[] volume = null, string rootUrl = null, bool dense = false,
            string symbol = null, int priceDecimals = -1, int volDecimals = -1)
        {
            int n = epochSeconds.Length;
            if (open.Length != n || high.Length != n || low.Length != n || close.Length != n)
                throw new ArgumentException("All OHLC arrays must match the timestamp count.");
            bool hasVolume = volume != null;
            if (hasVolume && volume.Length != n)
                throw new ArgumentException("volume must match the number of rows.");

            if (priceDecimals < 0)
                priceDecimals = DetectDecimals(Concat(open, high, low, close));
            priceDecimals = Math.Max(0, Math.Min(priceDecimals, 9));

            bool volFloat = false;
            if (hasVolume)
            {
                if (volDecimals < 0) volDecimals = DetectDecimals(volume);
                volDecimals = Math.Max(0, Math.Min(volDecimals, 9));
                volFloat = volDecimals > 0;
            }
            else volDecimals = 0;

            byte[] bin = PackBinary(epochSeconds, open, high, low, close, volume,
                                    priceDecimals, volDecimals, hasVolume, volFloat);
            return BuildUrl(bin, rootUrl, dense, symbol);
        }

        /// <summary>Build a chart URL from in-memory arrays using DateTime timestamps.
        /// DateTimes with Kind=Unspecified are treated as UTC.</summary>
        public static string GenerateUrl(
            DateTime[] times, double[] open, double[] high, double[] low, double[] close,
            double[] volume = null, string rootUrl = null, bool dense = false,
            string symbol = null, int priceDecimals = -1, int volDecimals = -1)
        {
            var epoch = new long[times.Length];
            for (int i = 0; i < times.Length; i++) epoch[i] = ToEpochSeconds(times[i]);
            return GenerateUrl(epoch, open, high, low, close, volume, rootUrl, dense,
                               symbol, priceDecimals, volDecimals);
        }

        /// <summary>Build a chart URL from an OHLCV CSV file (decimals detected from text).</summary>
        public static string GenerateUrlFromFile(
            string path, string rootUrl = null, bool dense = false, string symbol = null)
        {
            Model m = ParseCsvFile(File.ReadAllText(path));
            if (symbol == null) symbol = Path.GetFileNameWithoutExtension(path);
            byte[] bin = PackBinary(m.Ts, m.O, m.H, m.L, m.C, m.Vol,
                                    m.PriceDecimals, m.VolDecimals, m.HasVolume, m.VolFloat);
            return BuildUrl(bin, rootUrl, dense, symbol);
        }

        // ------------------------------------------------------------------ //
        // URL assembly
        // ------------------------------------------------------------------ //
        private static string BuildUrl(byte[] bin, string rootUrl, bool dense, string symbol)
        {
            byte[] comp = DeflateRaw(bin);
            string payload = dense ? DenseEncode(comp) : Base64Url(comp);
            var sb = new StringBuilder();
            sb.Append(rootUrl ?? DefaultRootUrl).Append("#d=").Append(payload);
            if (dense) sb.Append("&e=1");
            if (!string.IsNullOrEmpty(symbol)) sb.Append("&s=").Append(Uri.EscapeDataString(symbol));
            return sb.ToString();
        }

        // ------------------------------------------------------------------ //
        // Stage 1 - columnar binary packing
        // ------------------------------------------------------------------ //
        private static byte[] PackBinary(
            long[] ts, double[] o, double[] h, double[] l, double[] c, double[] vol,
            int priceDecimals, int volDecimals, bool hasVolume, bool volFloat)
        {
            int n = ts.Length;
            double pscale = Math.Pow(10, priceDecimals);
            double vscale = Math.Pow(10, volDecimals);

            bool tsRegular = true;
            long interval = n >= 2 ? ts[1] - ts[0] : 0;
            for (int i = 2; i < n; i++)
                if (ts[i] - ts[i - 1] != interval) { tsRegular = false; break; }

            var outp = new List<byte>();
            outp.Add(0x4F); outp.Add(0x31);            // magic 'O','1'
            outp.Add(1);                                // version
            int flagsIdx = outp.Count;
            outp.Add(0);                                // flags placeholder
            outp.Add((byte)(priceDecimals & 0xFF));
            outp.Add((byte)(volDecimals & 0xFF));
            WriteVarint(outp, n);

            if (tsRegular)
            {
                WriteVarint(outp, n > 0 ? ts[0] : 0);
                WriteVarint(outp, interval > 0 ? interval : 0);
            }
            else
            {
                WriteVarint(outp, ts[0]);
                for (int i = 1; i < n; i++) WriteVarint(outp, Zigzag(ts[i] - ts[i - 1]));
            }

            double[][] cols = { o, h, l, c };
            foreach (var col in cols)
            {
                long prev = 0;
                for (int i = 0; i < n; i++)
                {
                    long v = RoundHalfUp(col[i] * pscale);
                    WriteVarint(outp, Zigzag(v - prev));
                    prev = v;
                }
            }

            bool volDelta = false;
            if (hasVolume)
            {
                var scaled = new long[n];
                for (int i = 0; i < n; i++) scaled[i] = RoundHalfUp((vol[i]) * vscale);
                var raw = new List<byte>();
                var delta = new List<byte>();
                long prev = 0;
                for (int i = 0; i < n; i++)
                {
                    WriteVarint(raw, scaled[i]);
                    WriteVarint(delta, Zigzag(scaled[i] - prev));
                    prev = scaled[i];
                }
                if (delta.Count < raw.Count) { volDelta = true; outp.AddRange(delta); }
                else outp.AddRange(raw);
            }

            int flags = 0;
            if (tsRegular) flags |= 1;
            if (hasVolume) flags |= 2;
            if (volFloat) flags |= 4;
            if (volDelta) flags |= 8;
            outp[flagsIdx] = (byte)flags;

            return outp.ToArray();
        }

        private static void WriteVarint(List<byte> outp, long n)
        {
            while (n >= 128) { outp.Add((byte)((n % 128) + 128)); n /= 128; }
            outp.Add((byte)n);
        }

        private static long Zigzag(long n) { return n >= 0 ? n * 2 : n * -2 - 1; }

        private static long RoundHalfUp(double x) { return (long)Math.Floor(x + 0.5); }

        // ------------------------------------------------------------------ //
        // Stage 2 - raw DEFLATE (no zlib/gzip wrapper)
        // ------------------------------------------------------------------ //
        private static byte[] DeflateRaw(byte[] data)
        {
            using (var ms = new MemoryStream())
            {
                using (var ds = new DeflateStream(ms, CompressionLevel.Optimal, true))
                    ds.Write(data, 0, data.Length);
                return ms.ToArray();
            }
        }

        // ------------------------------------------------------------------ //
        // Stage 3 - URL-safe text encodings
        // ------------------------------------------------------------------ //
        private static string Base64Url(byte[] d)
        {
            return Convert.ToBase64String(d).Replace('+', '-').Replace('/', '_').TrimEnd('=');
        }

        // Whole-buffer base conversion via manual big-number division (matches
        // the BigInt-based encoder in the HTML/Python). A 2-char prefix records
        // the count of leading zero bytes.
        private static string DenseEncode(byte[] data)
        {
            int lead = 0;
            while (lead < data.Length && data[lead] == 0) lead++;
            int len = data.Length - lead;
            var work = new int[len];
            for (int i = 0; i < len; i++) work[i] = data[lead + i];

            var digits = new List<int>();   // least-significant first
            int start = 0;
            while (start < len)
            {
                int rem = 0;
                for (int i = start; i < len; i++)
                {
                    int acc = rem * 256 + work[i];
                    work[i] = acc / DenseN;
                    rem = acc % DenseN;
                }
                digits.Add(rem);
                while (start < len && work[start] == 0) start++;
            }

            var sb = new StringBuilder();
            sb.Append(DenseAlphabet[lead / DenseN]);
            sb.Append(DenseAlphabet[lead % DenseN]);
            for (int i = digits.Count - 1; i >= 0; i--) sb.Append(DenseAlphabet[digits[i]]);
            return sb.ToString();
        }

        // ------------------------------------------------------------------ //
        // Parsing / detection helpers
        // ------------------------------------------------------------------ //
        private static int DetectDecimals(IEnumerable<double> values)
        {
            int d = 0;
            foreach (var v in values)
            {
                int k = 0;
                while (k < 9 && Math.Abs(v * Math.Pow(10, k) - Math.Round(v * Math.Pow(10, k))) > 1e-9) k++;
                if (k > d) d = k;
            }
            return d;
        }

        private static int DecimalsOfToken(string token)
        {
            token = token.Trim();
            int dot = token.LastIndexOf('.');
            if (dot < 0) return 0;
            for (int i = dot + 1; i < token.Length; i++)
                if (!char.IsDigit(token[i])) return 0;
            return token.Length - dot - 1;
        }

        /// <summary>Parse a timestamp string to epoch seconds (naive values = UTC).</summary>
        public static long ToEpochSeconds(string s)
        {
            s = s.Trim();
            if (s.Length > 0 && IsAllDigits(s))
            {
                long num = long.Parse(s, CultureInfo.InvariantCulture);
                return s.Length >= 12 ? (long)Math.Round(num / 1000.0) : num;
            }
            DateTimeOffset dto;
            if (DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out dto))
                return dto.ToUnixTimeSeconds();
            throw new FormatException("Unparseable timestamp: " + s);
        }

        /// <summary>Convert a DateTime to epoch seconds; Kind=Unspecified is treated as UTC.</summary>
        public static long ToEpochSeconds(DateTime dt)
        {
            if (dt.Kind == DateTimeKind.Unspecified) dt = DateTime.SpecifyKind(dt, DateTimeKind.Utc);
            return new DateTimeOffset(dt.ToUniversalTime()).ToUnixTimeSeconds();
        }

        private static bool IsAllDigits(string s)
        {
            foreach (char ch in s) if (ch < '0' || ch > '9') return false;
            return s.Length > 0;
        }

        private static double[] Concat(params double[][] arrays)
        {
            int total = 0;
            foreach (var a in arrays) total += a.Length;
            var res = new double[total];
            int p = 0;
            foreach (var a in arrays) { Array.Copy(a, 0, res, p, a.Length); p += a.Length; }
            return res;
        }

        // ------------------------------------------------------------------ //
        // CSV parsing
        // ------------------------------------------------------------------ //
        private sealed class Model
        {
            public long[] Ts; public double[] O, H, L, C, Vol;
            public int PriceDecimals, VolDecimals;
            public bool HasVolume, VolFloat;
        }

        private static readonly string[] TimeAliases = { "timestamp", "datetime", "dts", "date", "time" };
        private static readonly string[] OpenAliases = { "open", "o" };
        private static readonly string[] HighAliases = { "high", "h" };
        private static readonly string[] LowAliases = { "low", "l" };
        private static readonly string[] CloseAliases = { "close", "c" };
        private static readonly string[] VolAliases = { "volume", "vol", "v" };

        private static Model ParseCsvFile(string text)
        {
            List<string[]> rows = ParseCsv(text);
            if (rows.Count < 2) throw new InvalidDataException("CSV has no data rows.");

            var header = new string[rows[0].Length];
            for (int i = 0; i < header.Length; i++) header[i] = rows[0][i].Trim().ToLowerInvariant();

            int ti = FindCol(header, TimeAliases);
            int oi = FindCol(header, OpenAliases), hi = FindCol(header, HighAliases);
            int li = FindCol(header, LowAliases), ci = FindCol(header, CloseAliases);
            if (ti < 0) throw new InvalidDataException("No time column (timestamp/datetime/dts/date/time).");
            if (oi < 0 || hi < 0 || li < 0 || ci < 0)
                throw new InvalidDataException("Need open, high, low and close columns.");
            int vi = FindCol(header, VolAliases);
            bool hasVolume = vi >= 0;

            int need = Math.Max(Math.Max(Math.Max(ti, oi), Math.Max(hi, li)), Math.Max(ci, hasVolume ? vi : 0));
            var data = new List<string[]>();
            for (int i = 1; i < rows.Count; i++)
                if (rows[i].Length > need && rows[i][ti].Trim().Length > 0) data.Add(rows[i]);
            if (data.Count == 0) throw new InvalidDataException("CSV has no usable data rows.");

            int priceDecimals = 0;
            foreach (var r in data)
                foreach (int idx in new[] { oi, hi, li, ci })
                    priceDecimals = Math.Max(priceDecimals, DecimalsOfToken(r[idx]));
            priceDecimals = Math.Min(priceDecimals, 9);

            int volDecimals = 0; bool volFloat = false;
            if (hasVolume)
            {
                foreach (var r in data)
                {
                    int d = DecimalsOfToken(r[vi]);
                    if (d > 0) volFloat = true;
                    volDecimals = Math.Max(volDecimals, d);
                }
                volDecimals = Math.Min(volDecimals, 9);
            }

            int n = data.Count;
            var m = new Model
            {
                Ts = new long[n],
                O = new double[n], H = new double[n], L = new double[n], C = new double[n],
                Vol = hasVolume ? new double[n] : null,
                PriceDecimals = priceDecimals, VolDecimals = volDecimals,
                HasVolume = hasVolume, VolFloat = volFloat
            };
            for (int i = 0; i < n; i++)
            {
                var r = data[i];
                m.Ts[i] = ToEpochSeconds(r[ti]);
                m.O[i] = ParseDouble(r[oi]); m.H[i] = ParseDouble(r[hi]);
                m.L[i] = ParseDouble(r[li]); m.C[i] = ParseDouble(r[ci]);
                if (hasVolume) m.Vol[i] = TryParseDouble(r[vi]);
            }
            return m;
        }

        private static int FindCol(string[] header, string[] aliases)
        {
            for (int i = 0; i < header.Length; i++)
                foreach (var a in aliases) if (header[i] == a) return i;
            return -1;
        }

        private static double ParseDouble(string s)
        {
            return double.Parse(s.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture);
        }

        private static double TryParseDouble(string s)
        {
            double v;
            return double.TryParse(s.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out v) ? v : 0.0;
        }

        // RFC-4180 parser (mirrors parseCSV in ohlcv_url_chart.html).
        private static List<string[]> ParseCsv(string csv)
        {
            var rows = new List<string[]>();
            var row = new List<string>();
            var field = new StringBuilder();
            bool inQ = false;
            for (int i = 0; i < csv.Length; i++)
            {
                char ch = csv[i];
                if (inQ)
                {
                    if (ch == '"' && i + 1 < csv.Length && csv[i + 1] == '"') { field.Append('"'); i++; }
                    else if (ch == '"') inQ = false;
                    else field.Append(ch);
                }
                else
                {
                    if (ch == '"') inQ = true;
                    else if (ch == ',') { row.Add(field.ToString()); field.Clear(); }
                    else if (ch == '\n')
                    {
                        row.Add(field.ToString()); field.Clear();
                        if (AnyNonEmpty(row)) rows.Add(row.ToArray());
                        row.Clear();
                    }
                    else if (ch != '\r') field.Append(ch);
                }
            }
            if (field.Length > 0 || row.Count > 0)
            {
                row.Add(field.ToString());
                if (AnyNonEmpty(row)) rows.Add(row.ToArray());
            }
            return rows;
        }

        private static bool AnyNonEmpty(List<string> row)
        {
            foreach (var s in row) if (!string.IsNullOrEmpty(s)) return true;
            return false;
        }

#if OHLCV_CLI
        // Console entry point - excluded from NinjaTrader builds (OHLCV_CLI not defined there).
        public static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.Error.WriteLine("Usage: OhlcvUrl <data.csv> [--root URL] [--dense] [--symbol NAME]");
                return 1;
            }
            string csv = args[0], root = DefaultRootUrl, symbol = null;
            bool dense = false;
            for (int i = 1; i < args.Length; i++)
            {
                switch (args[i])
                {
                    case "--root": root = args[++i]; break;
                    case "--dense": dense = true; break;
                    case "--symbol": symbol = args[++i]; break;
                    default: Console.Error.WriteLine("Unknown arg: " + args[i]); return 1;
                }
            }
            try { Console.WriteLine(GenerateUrlFromFile(csv, root, dense, symbol)); return 0; }
            catch (Exception ex) { Console.Error.WriteLine("Error: " + ex.Message); return 2; }
        }
#endif
    }
}
