# folio

A terminal-native EPUB editor with a keyboard-driven TUI.

```
  ╔═╗╔═╗╦  ╦╔═╗
  ╠╣ ║ ║║  ║║ ║
  ╩  ╚═╝╩═╝╩╚═╝
  epub editor · terminal-native
```

## Features

- **LTR ↔ RTL** — flip reading direction across the entire book (spine + all HTML content files)
- **Cover image** — replace or add a cover; auto-resizes and converts formats (JPG, PNG, WebP, SVG, …)
- **Metadata editor** — title, author, language, publisher, description
- **File browser** — navigate your filesystem to pick an EPUB
- **20 themes** — live preview as you scroll through them
- **Activity log** — every operation is recorded in-session

## Requirements

- Python 3.10+
- pip dependencies: `textual>=8.0`, `rich>=13`, `pillow>=10`, `lxml>=5`, `beautifulsoup4>=4.12`

## Installation

```bash
pip install .
folio                      # launch welcome screen
folio /path/to/book.epub   # open a specific file directly
```

Or run without installing (dev mode):

```bash
pip install -e .
./folio
```

## Keybindings

### Welcome screen
| Key | Action |
|-----|--------|
| `Enter` | Open selected / typed EPUB |
| `Esc` | Quit |

### Editor
| Key | Action |
|-----|--------|
| `d` | Toggle reading direction (LTR ↔ RTL) |
| `c` | Set cover image |
| `m` | Edit metadata |
| `t` | Choose theme (live preview) |
| `s` | Save (overwrite) |
| `S` | Save As… |
| `q` / `Esc` | Close file |
| `Ctrl+C` | Quit |

### File browser
| Key | Action |
|-----|--------|
| `Enter` | Open dir / select EPUB |
| `Backspace` / `←` | Go to parent directory |
| `Esc` | Cancel |
