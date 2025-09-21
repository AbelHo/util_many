# util_many
Simple Utility Websites

A collection of useful standalone HTML utility websites that run entirely in your browser. No server required, no data collection - everything runs locally for privacy and speed.

## 🛠️ Available Utilities

### 🔗 QR Code Generator
Generate QR codes from any text, URL, or data. Features include:
- Customizable sizes (100px to 500px)
- Multiple QR service providers
- Direct download or copy image links
- No external dependencies - works offline

### 🔐 Password Generator
Create secure, customizable passwords with various options:
- Adjustable length (4-128 characters)
- Character type selection (uppercase, lowercase, numbers, symbols)
- Exclude similar characters option
- Bulk password generation (up to 50 at once)
- Password strength indicator
- Copy individual or all passwords
- Export passwords to text file

### 🎨 Color Palette Generator
Generate beautiful color palettes and explore color harmonies:
- Multiple harmony types (complementary, triadic, analogous, monochromatic, tetradic)
- Customizable base colors and palette sizes
- Copy color codes in HEX, RGB, and HSL formats
- Save and load palettes locally
- Export palettes as CSS, JSON, or text files
- Interactive color previews

### 📝 Text Encoder/Decoder
Encode and decode text using various formats:
- **Base64** - Standard base64 encoding/decoding
- **URL Encoding** - URL-safe character encoding
- **HTML Entities** - HTML entity encoding with named entities
- **Unicode** - Unicode escape sequences (JavaScript format)
- **Hexadecimal** - Hex representation of text
- **Binary** - Binary representation of text
- Character count tracking
- Swap input/output functionality
- Copy output to clipboard

### 📋 JSON Formatter
Format, validate, and beautify JSON data:
- Real-time JSON validation
- Customizable indentation (2 spaces, 4 spaces, tabs)
- Sort keys alphabetically
- Unicode escape options
- Minify JSON functionality
- Interactive tree view of JSON structure
- Size and complexity statistics
- Load sample JSON for testing
- Copy formatted output

### 📏 Unit Converter
Convert between different units of measurement:
- **Length** - meters, kilometers, inches, feet, yards, miles, etc.
- **Weight** - grams, kilograms, pounds, ounces, stones, tons
- **Temperature** - Celsius, Fahrenheit, Kelvin, Rankine
- **Area** - square meters, acres, hectares, square feet, etc.
- **Volume** - liters, gallons, quarts, cubic meters, etc.
- **Speed** - m/s, km/h, mph, knots
- **Time** - seconds, minutes, hours, days, weeks, months, years
- Quick conversion references
- Conversion history with local storage
- Formula display for calculations

## 🚀 Features

- **Privacy First**: All tools run entirely in your browser - no data is sent to any server
- **Offline Capable**: Works without internet connection (after initial load)
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **No Installation**: Just open the HTML files in any modern browser
- **Local Storage**: Saves your preferences and history locally
- **Fast and Lightweight**: Minimal dependencies, optimized for performance

## 🌐 Usage

1. **Online**: Visit the [GitHub Pages site](https://abelbo.github.io/util_many/) (if available)
2. **Local**: Download the repository and open `index.html` in your browser
3. **Standalone**: Each utility can be used independently - just open any HTML file in the `utilities/` folder

## 🔧 Technical Details

- Pure HTML, CSS, and JavaScript
- No build process required
- No external dependencies (except for QR code generation which uses public APIs)
- Modern browser features used (ES6+, CSS Grid, Flexbox)
- Local storage for settings and history
- Responsive design with mobile-first approach

## 📁 File Structure

```
util_many/
├── index.html                    # Main landing page
├── utilities/
│   ├── qr-generator.html        # QR Code Generator
│   ├── password-generator.html  # Password Generator
│   ├── color-palette.html       # Color Palette Generator
│   ├── text-encoder.html        # Text Encoder/Decoder
│   ├── json-formatter.html      # JSON Formatter
│   └── unit-converter.html      # Unit Converter
├── README.md
└── LICENSE
```

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Add new utilities
- Improve existing tools
- Fix bugs or enhance performance
- Improve documentation
- Add new features

## 📄 License

MIT License - see LICENSE file for details.

## 🔗 Links

- Repository: https://github.com/AbelHo/util_many
- Issues: https://github.com/AbelHo/util_many/issues
- License: [MIT](LICENSE)