# Copilot Instructions for `util_many`

This repository contains small, self-contained web utilities, primarily implemented as single-file HTML+JS apps. The project is designed for simplicity, discoverability, and ease of use via GitHub Pages.

## Project Structure & Patterns
- **Each utility = one HTML file** (optionally with a JS file). Example: `camera_fov.html` + `camera_fov.js`.
- **No build step**: All code is plain HTML/JS/CSS, directly runnable in browsers. No npm, bundlers, or frameworks.
- **No package.json**: There are no Node.js dependencies or scripts.
- **Data files**: Example calibration JSONs are included for demo/testing.
- **README.md** and GitHub Actions auto-list all HTML utilities with links for easy discovery.

## Key Files & Conventions
- `README.md`: Auto-generated list of utilities. **Do not manually edit**; see workflow below.
- `.github/workflows/update-readme.yml`: On HTML file changes, auto-updates `README.md` with links to all HTML utilities, extracting titles from `<title>`, `<h1>`, or filename.
- `.gitignore`: Ignores editor files, temp files, and future build artifacts.
- `camera_fov.html`/`camera_fov.js`: Example of a utility with drag-and-drop JSON, live editing, and FOV calculation.
- `csv_to_srt.html`: Example of a utility with drag-and-drop, file parsing, and download.

## Developer Workflow
- **To add a new utility:**
  1. Create a new `.html` file (optionally with a `.js` file for logic).
  2. Use `<script src="...js"></script>` if splitting logic.
  3. Push to `main`. The `README.md` will update automatically via GitHub Actions.
- **No local build/test required**: Open HTML files directly in a browser for development and testing.
- **For GitHub Pages:** URLs are `https://AbelHo.github.io/util_many/<filename>.html`.
- **Github Actions**: Only used for updating `README.md`. When new HTML files are added to the repository:
  1. The workflow automatically detects HTML file changes on push to main
  2. Scans all HTML files in the root directory
  3. Extracts meaningful titles using a fallback hierarchy (title tag → header tags → filename)
  4. Regenerates the README.md with updated utility links pointing to GitHub Pages
  5. Commits and pushes changes only if the README was actually modified
  6. The implementation is minimal and surgical, adding exactly the functionality needed without disrupting existing code or workflow patterns.

## Project-Specific Patterns
- **Drag-and-drop** and file input are common for user data import. When you are asked to implement a file input/upload feature, always include drag and drop support as well.
- **No external dependencies** except for CDN JS (e.g., xlsx.js in `csv_to_srt.html`).
- **All logic is client-side**; no backend or server code.
- **Minimal CSS** for clarity and usability.
- **Project Description Meta Tag**: Write a description of this project in detail. It will be in the `<meta name="description" content="...">` tag in the `head` section of the HTML files.
- **Meta Keywords Tag**: Include relevant keywords in a `<meta name="keywords" content="...">` tag in the `head` section of the HTML files. This will help improve searchability and categorization of the utilities within the project.
- **Programmer Reference Summary Comment**: At the top of each HTML file in a hidden section, include a multi-line comment summarizing the utility's purpose, key features, and usage instructions for developers who may work on or maintain the code in the future. For every important changes, update this comment to reflect the current state of the utility.

## Example: Adding a Utility
```html
<!-- my_tool.html -->
<!DOCTYPE html>
<html><head><title>My Tool</title></head>
<body>
  <h2>My Tool</h2>
  <script>
    // JS logic here
  </script>
</body></html>
```

## Integration & Automation
- **README.md is managed by workflow**: Do not edit manually.
- **No test suite or CI for code**: Only the README update workflow exists.

## See Also
- [README.md](../README.md)
- [.github/workflows/update-readme.yml](../.github/workflows/update-readme.yml)

---
If any conventions or patterns are unclear, please ask for clarification or examples from the codebase.
