"""A small Word (.docx) writer: headings, paragraphs, monospaced blocks, tables and pictures. Enough for
the design report, without extra libraries. Word, LibreOffice and Google Docs open the files."""
from __future__ import annotations

import struct
import zipfile
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
EMU_PER_PX = 9525


def _png_size(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Pictures must be PNG.")
    return struct.unpack(">II", data[16:24])


def _run(text, bold=False, mono=False, size=None, color=None):
    props = ""
    if bold:
        props += "<w:b/>"
    if mono:
        props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
    if color:
        props += f'<w:color w:val="{color}"/>'
    if size:
        props += f'<w:sz w:val="{int(size * 2)}"/>'
    parts = str(text).split("\n")
    out = []
    for i, t in enumerate(parts):
        if i:
            out.append("<w:br/>")
        out.append(f'<w:t xml:space="preserve">{escape(t)}</w:t>')
    return f"<w:r>{'<w:rPr>' + props + '</w:rPr>' if props else ''}{''.join(out)}</w:r>"


class Document:
    def __init__(self):
        self.body: list[str] = []
        self.media: list[bytes] = []

    def heading(self, text, level=1):
        self.body.append(f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>{_run(text)}</w:p>')

    def paragraph(self, text="", bold=False, color=None):
        self.body.append(f"<w:p>{_run(text, bold=bold, color=color) if text else ''}</w:p>")

    def mono(self, text):
        self.body.append(f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>{_run(text, mono=True, size=8.5)}</w:p>')

    def table(self, rows, header=True, widths=None):
        if not rows:
            return
        n = max(len(r) for r in rows)
        grid = "".join(f'<w:gridCol w:w="{int(w)}"/>' for w in (widths or [9000 // n] * n))
        trs = []
        for i, r in enumerate(rows):
            tcs = []
            for c in list(r) + [""] * (n - len(r)):
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="E8EEF6"/>' if header and i == 0 else ""
                tcs.append(f"<w:tc><w:tcPr>{shade}</w:tcPr><w:p><w:pPr><w:spacing w:after=\"0\"/></w:pPr>"
                           f"{_run(c, bold=header and i == 0, size=9)}</w:p></w:tc>")
            trs.append("<w:tr>" + "".join(tcs) + "</w:tr>")
        borders = "".join(f'<w:{b} w:val="single" w:sz="4" w:color="B9C6D6"/>'
                          for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
        self.body.append(f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>{borders}</w:tblBorders>'
                         f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl><w:p/>')

    def picture(self, png: bytes, width_cm: float = 16.0):
        w, h = _png_size(png)
        self.media.append(png)
        k = len(self.media)
        cx = int(width_cm / 2.54 * 914400)
        cy = int(cx * h / w)
        self.body.append(
            f'<w:p><w:r><w:drawing><wp:inline><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{k}" name="Picture {k}"/>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{k}" name="image{k}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="rIdImg{k}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            f'</wp:inline></w:drawing></w:r></w:p>')

    def page_break(self):
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def save(self, path, title="Report", author="GeoLab"):
        sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" '
                'w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>')
        doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>'
               + "".join(self.body) + sect + "</w:body></w:document>")
        styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
                  '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" '
                  'w:cs="Nirmala UI"/><w:sz w:val="21"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
                  '<w:spacing w:after="120"/></w:pPr></w:pPrDefault></w:docDefaults>'
                  + "".join(f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/>'
                            f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr>'
                            f'<w:keepNext/><w:spacing w:before="{240 if i == 1 else 160}" w:after="80"/>'
                            f'<w:outlineLvl w:val="{i - 1}"/></w:pPr><w:rPr><w:b/><w:color w:val="1D4E89"/>'
                            f'<w:sz w:val="{36 if i == 1 else 28 if i == 2 else 24}"/></w:rPr></w:style>'
                            for i in (1, 2, 3))
                  + '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
                  '<w:qFormat/></w:style></w:styles>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/styles" Target="styles.xml"/>'
                + "".join(f'<Relationship Id="rIdImg{k}" Type="http://schemas.openxmlformats.org/officeDocument/'
                          f'2006/relationships/image" Target="media/image{k}.png"/>'
                          for k in range(1, len(self.media) + 1)) + "</Relationships>")
        ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types '
                  'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                  '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                  '<Default Extension="xml" ContentType="application/xml"/>'
                  '<Default Extension="png" ContentType="image/png"/>'
                  '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
                  'officedocument.wordprocessingml.document.main+xml"/>'
                  '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
                  'officedocument.wordprocessingml.styles+xml"/>'
                  '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-'
                  'package.core-properties+xml"/></Types>')
        root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                     'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                     'relationships/officeDocument" Target="word/document.xml"/>'
                     '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/'
                     'metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
                'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                f'<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator></cp:coreProperties>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ctypes)
            z.writestr("_rels/.rels", root_rels)
            z.writestr("docProps/core.xml", core)
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", styles)
            z.writestr("word/_rels/document.xml.rels", rels)
            for k, data in enumerate(self.media, 1):
                z.writestr(f"word/media/image{k}.png", data)
