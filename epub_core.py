"""Core EPUB manipulation logic."""

import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

# XML namespaces used in EPUB
NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


@dataclass
class EpubMetadata:
    title: str = ""
    author: str = ""
    language: str = ""
    publisher: str = ""
    description: str = ""
    identifier: str = ""
    direction: str = "ltr"  # "ltr" or "rtl"
    cover_path: Optional[str] = None  # path inside zip
    cover_media_type: str = "image/jpeg"
    spine_items: list[str] = field(default_factory=list)
    manifest_items: dict[str, dict] = field(default_factory=dict)  # id -> {href, media-type}


class EpubEditor:
    """Reads, modifies and writes EPUB files."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._tmpdir: Optional[Path] = None
        self.metadata = EpubMetadata()
        self._opf_path: Optional[str] = None  # path inside zip
        self._opf_abs: Optional[Path] = None  # absolute path in tmpdir
        self._opf_root: str = ""  # directory containing OPF inside zip
        self._is_loaded = False
        self._errors: list[str] = []

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load(self) -> list[str]:
        """Extract EPUB, parse metadata. Returns list of warnings."""
        self._errors = []
        self._tmpdir = Path(tempfile.mkdtemp(prefix="epub_edit_"))
        try:
            with zipfile.ZipFile(self.path, "r") as zf:
                zf.extractall(self._tmpdir)
        except zipfile.BadZipFile as e:
            self._errors.append(f"Bad ZIP: {e}")
            return self._errors

        self._opf_path = self._find_opf()
        if not self._opf_path:
            self._errors.append("Could not locate OPF file (container.xml missing or malformed).")
            return self._errors

        self._opf_abs = self._tmpdir / self._opf_path
        self._opf_root = str(Path(self._opf_path).parent)
        if self._opf_root == ".":
            self._opf_root = ""

        self._parse_opf()
        self._is_loaded = True
        return self._errors

    def save(self, dest: Optional[str] = None) -> Path:
        """Write modified EPUB. If dest is None, overwrites original."""
        if not self._is_loaded:
            raise RuntimeError("EPUB not loaded")
        self._write_opf()
        out = Path(dest) if dest else self.path
        tmp_out = out.with_suffix(".tmp.epub")
        self._repack(tmp_out)
        tmp_out.replace(out)
        return out

    def cleanup(self):
        """Remove temp directory."""
        if self._tmpdir and self._tmpdir.exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
            self._is_loaded = False

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _find_opf(self) -> Optional[str]:
        container_xml = self._tmpdir / "META-INF" / "container.xml"
        if not container_xml.exists():
            return None
        tree = ET.parse(container_xml)
        root = tree.getroot()
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfiles = root.findall(".//c:rootfile", ns)
        if not rootfiles:
            return None
        return rootfiles[0].get("full-path")

    def _parse_opf(self):
        tree = ET.parse(self._opf_abs)
        root = tree.getroot()

        # Strip namespace for easy access
        def tag(ns_prefix, local):
            return f"{{{NS[ns_prefix]}}}{local}"

        # Metadata
        meta_el = root.find(tag("opf", "metadata"))
        if meta_el is not None:
            def dc(name):
                el = meta_el.find(tag("dc", name))
                return el.text.strip() if el is not None and el.text else ""

            self.metadata.title = dc("title")
            self.metadata.author = dc("creator")
            self.metadata.language = dc("language")
            self.metadata.publisher = dc("publisher")
            self.metadata.description = dc("description")
            self.metadata.identifier = dc("identifier")

        # Manifest
        manifest_el = root.find(tag("opf", "manifest"))
        if manifest_el is not None:
            for item in manifest_el.findall(tag("opf", "item")):
                item_id = item.get("id", "")
                href = item.get("href", "")
                media_type = item.get("media-type", "")
                props = item.get("properties", "")
                self.metadata.manifest_items[item_id] = {
                    "href": href,
                    "media-type": media_type,
                    "properties": props,
                }
                if "cover-image" in props or item_id in ("cover", "cover-image", "cover_image"):
                    if "image" in media_type:
                        opf_dir = Path(self._opf_path).parent
                        self.metadata.cover_path = str(opf_dir / href)
                        self.metadata.cover_media_type = media_type

        # Spine direction
        spine_el = root.find(tag("opf", "spine"))
        if spine_el is not None:
            page_prog = spine_el.get("page-progression-direction", "ltr")
            self.metadata.direction = page_prog
            for itemref in spine_el.findall(tag("opf", "itemref")):
                idref = itemref.get("idref", "")
                if idref:
                    self.metadata.spine_items.append(idref)

    def _write_opf(self):
        tree = ET.parse(self._opf_abs)
        root = tree.getroot()

        def tag(ns_prefix, local):
            return f"{{{NS[ns_prefix]}}}{local}"

        # Update metadata
        meta_el = root.find(tag("opf", "metadata"))
        if meta_el is not None:
            def set_dc(name, value):
                el = meta_el.find(tag("dc", name))
                if el is None:
                    el = ET.SubElement(meta_el, tag("dc", name))
                el.text = value

            set_dc("title", self.metadata.title)
            set_dc("creator", self.metadata.author)
            set_dc("language", self.metadata.language)
            if self.metadata.publisher:
                set_dc("publisher", self.metadata.publisher)
            if self.metadata.description:
                set_dc("description", self.metadata.description)

        # Update spine direction
        spine_el = root.find(tag("opf", "spine"))
        if spine_el is not None:
            spine_el.set("page-progression-direction", self.metadata.direction)

        ET.indent(tree, space="  ")
        tree.write(self._opf_abs, encoding="utf-8", xml_declaration=True)

    def _repack(self, dest: Path):
        """Repack the tmpdir into a new EPUB zip."""
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            # mimetype must be first, uncompressed
            mimetype = self._tmpdir / "mimetype"
            if mimetype.exists():
                zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
            for fpath in sorted(self._tmpdir.rglob("*")):
                if fpath.is_file() and fpath.name != "mimetype":
                    arcname = fpath.relative_to(self._tmpdir)
                    zf.write(fpath, arcname)

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def set_direction(self, direction: str):
        """Set reading direction: 'ltr' or 'rtl'."""
        if direction not in ("ltr", "rtl"):
            raise ValueError("direction must be 'ltr' or 'rtl'")
        self.metadata.direction = direction
        self._patch_html_direction(direction)

    def _patch_html_direction(self, direction: str):
        """Update dir attribute and CSS in HTML content files."""
        for item_id, info in self.metadata.manifest_items.items():
            mt = info.get("media-type", "")
            if mt not in ("application/xhtml+xml", "text/html"):
                continue
            opf_dir = Path(self._opf_path).parent
            abs_path = self._tmpdir / opf_dir / info["href"]
            if not abs_path.exists():
                continue
            try:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
                soup = BeautifulSoup(text, "lxml")
                html_tag = soup.find("html")
                if html_tag:
                    html_tag["dir"] = direction
                    if direction == "rtl":
                        html_tag["xml:lang"] = html_tag.get("xml:lang", self.metadata.language or "ar")
                body_tag = soup.find("body")
                if body_tag:
                    body_tag["dir"] = direction
                abs_path.write_text(str(soup), encoding="utf-8")
            except Exception:
                pass

    def set_cover(self, image_path: str) -> str:
        """
        Replace (or add) cover image.
        Returns the internal path of the cover inside the EPUB.
        """
        from PIL import Image as PILImage

        src = Path(image_path)
        if not src.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Determine extension / media type
        suffix = src.suffix.lower()
        mt_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }
        media_type = mt_map.get(suffix, "image/jpeg")

        # Find where images live inside the EPUB
        opf_dir = Path(self._opf_path).parent
        images_dir = self._tmpdir / opf_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        dest_filename = f"cover{suffix}"
        dest_abs = images_dir / dest_filename

        # Optimise / convert if needed (keep aspect ratio, cap at 2000px)
        if suffix != ".svg":
            img = PILImage.open(src)
            img.thumbnail((2000, 2000), PILImage.LANCZOS)
            save_fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/gif": "GIF"}.get(media_type, "JPEG")
            if save_fmt == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(dest_abs, save_fmt)
        else:
            shutil.copy2(src, dest_abs)

        # Internal href relative to OPF
        cover_href = f"images/{dest_filename}"
        internal_path = str(opf_dir / cover_href)

        self.metadata.cover_path = internal_path
        self.metadata.cover_media_type = media_type

        # Patch OPF manifest
        self._update_opf_cover(cover_href, media_type)
        return internal_path

    def _update_opf_cover(self, cover_href: str, media_type: str):
        tree = ET.parse(self._opf_abs)
        root = tree.getroot()

        def tag(ns_prefix, local):
            return f"{{{NS[ns_prefix]}}}{local}"

        manifest_el = root.find(tag("opf", "manifest"))
        if manifest_el is None:
            return

        # Remove old cover image items
        to_remove = []
        for item in manifest_el.findall(tag("opf", "item")):
            props = item.get("properties", "")
            iid = item.get("id", "")
            if "cover-image" in props or iid in ("cover", "cover-image", "cover_image"):
                if "image" in item.get("media-type", ""):
                    to_remove.append(item)
        for item in to_remove:
            manifest_el.remove(item)

        # Add new cover image item
        new_item = ET.SubElement(manifest_el, tag("opf", "item"))
        new_item.set("id", "cover-image")
        new_item.set("href", cover_href)
        new_item.set("media-type", media_type)
        new_item.set("properties", "cover-image")

        # Add/update <meta name="cover"> in metadata
        meta_el = root.find(tag("opf", "metadata"))
        if meta_el is not None:
            for meta in meta_el.findall(tag("opf", "meta")):
                if meta.get("name") == "cover":
                    meta_el.remove(meta)
            cover_meta = ET.SubElement(meta_el, tag("opf", "meta"))
            cover_meta.set("name", "cover")
            cover_meta.set("content", "cover-image")

        # Update manifest_items cache
        self.metadata.manifest_items["cover-image"] = {
            "href": cover_href,
            "media-type": media_type,
            "properties": "cover-image",
        }

        ET.indent(tree, space="  ")
        tree.write(self._opf_abs, encoding="utf-8", xml_declaration=True)

    def update_metadata(self, **kwargs):
        """Update metadata fields: title, author, language, publisher, description."""
        for k, v in kwargs.items():
            if hasattr(self.metadata, k):
                setattr(self.metadata, k, v)

    def get_cover_abs_path(self) -> Optional[Path]:
        """Return absolute path to cover image in tmpdir, if any."""
        if not self.metadata.cover_path:
            return None
        p = self._tmpdir / self.metadata.cover_path
        return p if p.exists() else None

    def get_spine_count(self) -> int:
        return len(self.metadata.spine_items)

    def get_file_size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0
