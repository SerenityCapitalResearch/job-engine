#!/usr/bin/env python3
"""Build a resume in Aman's Word format.

  python resume/build_resume.py resume/content/india_gtm.yaml output.docx

The Word file `resume/template.docx` supplies the page size, margins, fonts, bullet style and colours;
the content file supplies only the words. Change the words, never the layout.
"""
import copy
import sys
from xml.sax.saxutils import escape

import yaml
from docx import Document
from docx.oxml import parse_xml

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')
NAVY, BODY, DARK = "1F3864", "333333", "111111"
RIGHT_TAB = 9936  # right edge of the text area in the template


def run(text, color=BODY, bold=False, italic=False, size=None, tab=False):
    rpr = ("<w:b/><w:bCs/>" if bold else "") + ("<w:i/><w:iCs/>" if italic else "")
    rpr += f'<w:color w:val="{color}"/>'
    if size:
        rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    body = "<w:tab/>" if tab else f'<w:t xml:space="preserve">{escape(text)}</w:t>'
    return f"<w:r><w:rPr>{rpr}</w:rPr>{body}</w:r>"


def para(ppr, *runs):
    return parse_xml(f"<w:p {NS}><w:pPr>{ppr}</w:pPr>{''.join(runs)}</w:p>")


def centered(text, after=15, bold=False, color=BODY, size=None):
    return para(f'<w:spacing w:after="{after}"/><w:jc w:val="center"/>', run(text, color, bold, size=size))


def heading(text):
    return para('<w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="%s"/></w:pBdr>'
                '<w:spacing w:before="100" w:after="45"/>' % NAVY, run(text, NAVY, bold=True, size=22))


def body(text, after=15):
    return para(f'<w:spacing w:after="{after}"/><w:jc w:val="both"/>', run(text))


def entry(title, date=""):
    runs = [run(title, DARK, bold=True)]
    if date:
        runs += [run("", BODY, bold=True, tab=True), run(date, DARK, italic=True)]
    return para(f'<w:keepNext/><w:tabs><w:tab w:val="right" w:pos="{RIGHT_TAB}"/></w:tabs><w:spacing w:before="70"/>', *runs)


def subline(text):
    return para("<w:keepNext/>", run(text, BODY, italic=True))


def bullet(text):
    return para('<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>'
                '<w:spacing w:after="20"/><w:jc w:val="both"/>', run(text))


def edu_title(text):
    return para('<w:keepNext/><w:spacing w:before="50"/>', run(text, DARK, bold=True))


def edu_line(text):
    return para("", run(text))


def build(content_path, out_path, template="resume/template.docx"):
    c = yaml.safe_load(open(content_path, encoding="utf-8"))
    doc = Document(template)
    bodyel = doc.element.body
    sect = bodyel.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr")
    for child in list(bodyel):
        if child is not sect:
            bodyel.remove(child)

    out = [centered(c["name"], bold=True, color=NAVY, size=32), centered(c["headline"]),
           centered(c["status"], bold=True), centered(c["contact"], after=40)]
    for sec in c["sections"]:
        out.append(heading(sec["heading"]))
        for i, t in enumerate(sec.get("paragraphs", [])):
            last = i == len(sec["paragraphs"]) - 1
            out.append(body(t, after=60 if last and sec.get("space_after_last") else 15))
        for e in sec.get("entries", []):
            out.append(entry(e["title"], e.get("date", "")))
            if e.get("subtitle"):
                out.append(subline(e["subtitle"]))
            out += [bullet(b) for b in e.get("bullets", [])]
        for e in sec.get("education", []):
            out += [edu_title(e["degree"]), edu_line(e["school"])]
    for el in out:
        sect.addprevious(el)
    doc.core_properties.title = f"{c['name']} - Resume"
    doc.core_properties.author = c["name"]
    doc.save(out_path)
    print("saved", out_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
