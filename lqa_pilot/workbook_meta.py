"""Small OOXML custom properties; keep run identity off the single visible sheet."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

CUSTOM = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CTYPE = "http://schemas.openxmlformats.org/package/2006/content-types"

def read_metadata(path):
    if not Path(path).is_file():
        return {}
    with ZipFile(path) as z:
        if "docProps/custom.xml" not in z.namelist():
            return {}
        return {p.attrib["name"]: "".join(p.itertext()) for p in ET.fromstring(z.read("docProps/custom.xml"))}

def write_metadata(path, values):
    path = Path(path)
    staging = path.with_suffix(".meta.tmp")
    with ZipFile(path) as src, ZipFile(staging, "w", ZIP_DEFLATED) as dst:
        root = ET.fromstring(src.read("docProps/custom.xml")) if "docProps/custom.xml" in src.namelist() else ET.Element(f"{{{CUSTOM}}}Properties")
        for p in list(root):
            if p.attrib.get("name") in values:
                root.remove(p)
        next_id = max([int(p.attrib["pid"]) for p in root]+[1])+1
        for name,value in values.items():
            prop = ET.SubElement(root, f"{{{CUSTOM}}}property", {"fmtid":"{D5CDD505-2E9C-101B-9397-08002B2CF9AE}", "pid":str(next_id), "name":name})
            ET.SubElement(prop, f"{{{VT}}}lpwstr").text = str(value)
            next_id += 1
        rels = ET.fromstring(src.read("_rels/.rels"))
        rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
        if not any(p.attrib.get("Type") == rel_type for p in rels):
            ET.SubElement(rels, f"{{{REL}}}Relationship", {"Id":"rIdLqaMetadata", "Type":rel_type, "Target":"docProps/custom.xml"})
        types = ET.fromstring(src.read("[Content_Types].xml"))
        if not any(p.attrib.get("PartName") == "/docProps/custom.xml" for p in types):
            ET.SubElement(types, f"{{{CTYPE}}}Override", {"PartName":"/docProps/custom.xml", "ContentType":"application/vnd.openxmlformats-officedocument.custom-properties+xml"})
        replacements = {"docProps/custom.xml":root, "_rels/.rels":rels, "[Content_Types].xml":types}
        for name in src.namelist():
            if name not in replacements:
                dst.writestr(name, src.read(name))
        for name,part in replacements.items():
            dst.writestr(name, ET.tostring(part, encoding="utf-8", xml_declaration=True))
    staging.replace(path)
