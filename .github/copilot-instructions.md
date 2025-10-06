# util_many - Simple Utility Websites

util_many is a collection of standalone HTML utility websites that are deployed via GitHub Pages. The repository contains client-side JavaScript applications that require no build process or server infrastructure.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Repository Structure
- `csv_to_srt.html` - CSV/XLSX to SRT subtitle converter utility
- `sync_max_distance.html` - Frame distance calculator for audio/video synchronization
- `.github/workflows/update-readme.yml` - Automated workflow that updates README.md based on HTML files
- `README.md` - Auto-generated documentation listing available utilities
- `LICENSE` - MIT license file
- `.gitignore` - Standard ignore patterns for temporary and build files

### Dependencies and Requirements
- No build tools, package managers, or local dependencies required
- All applications run entirely in the browser using vanilla JavaScript
- External dependency: `xlsx@0.18.5` library loaded from CDN (https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js)
- Python 3 (for local testing via HTTP server)
- Modern web browser for testing functionality

### Local Development and Testing
NEVER CANCEL: Local testing setup takes 5-10 seconds. Set timeout to 30+ seconds.

1. **Start local HTTP server for testing**:
   ```bash
   cd /path/to/util_many
   python3 -m http.server 8000
   ```
   - Server starts immediately, listen for "Serving HTTP on 0.0.0.0 port 8000"
   - Access utilities at http://localhost:8000/[filename].html
   - NEVER CANCEL: Keep server running for entire testing session

2. **Test CSV to SRT Converter**:
   - Navigate to http://localhost:8000/csv_to_srt.html
   - Create test CSV with required columns: `Start (s),Stop (s),Behavior type,Behavior,Subject`
   - Test both drag-and-drop and browse file functionality
   - Verify SRT output format is correct with proper timing and subtitle structure
   - Test with both CSV and XLSX files

3. **Test Frame Distance Calculator**:
   - Navigate to http://localhost:8000/sync_max_distance.html
   - Test calculation with different FPS values (default: 30, test with 60, 24, etc.)
   - Test both Air (343 m/s) and Water (1500 m/s) sound speed options
   - Verify calculations are mathematically correct: max_distance = speed / fps

## Deployment and CI/CD

### GitHub Pages Deployment
- Repository uses GitHub Pages for hosting at https://AbelHo.github.io/util_many/
- No build process required - HTML files are served directly
- Changes pushed to main branch are automatically deployed

### Automated README Updates
- `.github/workflows/update-readme.yml` automatically updates README.md when HTML files change
- Workflow extracts titles from HTML files and generates utility list
- NEVER CANCEL: Workflow completes in 30-60 seconds. Set timeout to 120+ seconds.
- Triggered on pushes to main branch that modify `.html` files or manual dispatch

## Validation Requirements

### Manual Testing Scenarios
ALWAYS run through these complete end-to-end scenarios after making changes:

1. **CSV to SRT Converter Full Workflow**:
   - Start local HTTP server
   - Create sample CSV file with proper headers and data
   - Upload file via drag-and-drop OR browse button
   - Click "Convert & Download SRT"
   - Verify SRT file downloads with correct format and timing
   - Validate subtitle numbering, timestamps, and content are accurate

2. **Frame Distance Calculator Full Workflow**:
   - Load the calculator page
   - Enter different FPS values (test at least 24, 30, 60)
   - Switch between Air and Water medium options
   - Click Calculate and verify results update correctly
   - Confirm mathematical accuracy: distance = speed / fps, sync_distance = distance / 2

3. **GitHub Pages Live Testing**:
   - After deployment, test utilities at https://AbelHo.github.io/util_many/
   - Verify all functionality works identically to local version
   - Check that external CDN dependencies load correctly

### Code Quality Checks
- No linting, build tools, or automated tests exist in this repository
- Manual code review and browser testing are the primary validation methods
- Always test in at least one modern browser (Chrome, Firefox, or Edge)
- Verify JavaScript console shows no errors during normal operation

## Common Development Tasks

### Adding New Utilities
1. Create new HTML file in repository root
2. Include proper `<title>` tag for automatic README generation
3. Test functionality locally using HTTP server
4. Push to main branch - README.md will update automatically via workflow
5. VALIDATION: Test the new utility on live GitHub Pages site

### Modifying Existing Utilities
1. Always test locally first using the validation scenarios above
2. Pay special attention to:
   - CSV parsing logic and required column headers in csv_to_srt.html
   - Mathematical calculations in sync_max_distance.html  
   - File upload and download functionality
   - Cross-browser compatibility for JavaScript features
3. Verify external CDN dependencies still load if modified

### Debugging Issues
- Use browser developer tools console for JavaScript errors
- Test with different file types and edge cases
- Verify CDN resources are accessible (may be blocked in some environments)
- Check GitHub Pages deployment status if live site differs from local testing

## File Structure Reference
```
util_many/
├── .github/
│   └── workflows/
│       └── update-readme.yml     # Auto-README generation
├── .gitignore                    # Standard ignore patterns
├── LICENSE                       # MIT license
├── README.md                     # Auto-generated utility list
├── csv_to_srt.html              # CSV/XLSX to SRT converter
└── sync_max_distance.html       # Frame distance calculator
```

## Key Implementation Details

### CSV to SRT Converter
- Supports both CSV and XLSX input formats
- Required columns: `Start (s)`, `Stop (s)`, `Behavior type`, `Behavior`, `Subject`  
- Flexible header detection (checks first two rows)
- Outputs standard SRT subtitle format with proper timing
- Uses xlsx library from CDN for Excel file support

### Frame Distance Calculator
- Calculates maximum sound travel distance in one video frame
- Supports Air (343 m/s) and Water (1500 m/s) sound speeds
- Provides synchronization distance recommendations
- Real-time calculation updates on parameter changes
- Formula: max_distance = sound_speed / fps, sync_distance = max_distance / 2

Remember: This is a simple, standalone website collection with no complex build processes. Focus on browser compatibility, user experience, and mathematical accuracy in calculations.