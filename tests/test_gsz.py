"""GeoStudio .gsz import / export (geometry)."""
import zipfile

import pytest

from stratalab.examples import layered_slope_with_water
from stratalab.fileio import load_project
from stratalab.gsz import read_gsz, write_gsz

# same structure as a file saved by GeoStudio 2025.2 (geometry only)
SAMPLE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<GSIData Version="11.12" AppVersion="25.2.1.39">
  <FileInfo FileVersion="11.12" AppVersion="25.2.1.39" RevNumber="2" />
  <Coordinates><EngCoords HorzScale="200" UnitSystem="Metric" VertScale="200" /></Coordinates>
  <Geometries Len="1">
    <Geometry>
      <Name>2D Geometry</Name>
      <Points Len="6">
        <Point ID="1" X="0" Y="0" /><Point ID="2" X="40" Y="0" /><Point ID="3" X="40" Y="10" />
        <Point ID="4" X="0" Y="10" /><Point ID="5" X="40" Y="18" /><Point ID="6" X="20" Y="18" />
      </Points>
      <Lines Len="7">
        <Line><ID>1</ID><PointID1>1</PointID1><PointID2>2</PointID2></Line>
      </Lines>
      <Regions Len="2">
        <Region><ID>1</ID><PointIDs>1,2,3,4</PointIDs><MaterialID>2</MaterialID></Region>
        <Region><ID>2</ID><PointIDs>4,3,5,6</PointIDs><MaterialID>1</MaterialID></Region>
      </Regions>
    </Geometry>
  </Geometries>
  <Materials Len="2">
    <Material><ID>1</ID><Name>Clay</Name><UnitWeight>19</UnitWeight><CohesionPrime>8</CohesionPrime>
      <PhiPrime>24</PhiPrime></Material>
    <Material><ID>2</ID><Name>Sand</Name><UnitWeight>20.5</UnitWeight><PhiPrime>35</PhiPrime></Material>
  </Materials>
</GSIData>"""


def make_gsz(path, xml=SAMPLE):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("sample.xml", xml)
    return path


def test_import_geometry_and_materials(tmp_path):
    p = read_gsz(make_gsz(tmp_path / "sample.gsz"))
    assert len(p.regions) == 2
    assert p.regions[0].points == [[0, 0], [40, 0], [40, 10], [0, 10]]
    names = {m.id: m.name for m in p.materials}
    assert names[p.regions[0].material_id] == "Sand" and names[p.regions[1].material_id] == "Clay"
    clay = next(m for m in p.materials if m.name == "Clay")
    assert (clay.unit_weight, clay.cohesion, clay.phi) == (19, 8, 24)


def test_import_without_materials_and_clockwise_region(tmp_path):
    xml = SAMPLE.replace("<MaterialID>2</MaterialID>", "").replace("<MaterialID>1</MaterialID>", "") \
        .replace("<PointIDs>1,2,3,4</PointIDs>", "<PointIDs>4,3,2,1</PointIDs>")
    xml = xml[:xml.index("<Materials")] + "</GSIData>"
    p = load_project(make_gsz(tmp_path / "geom.gsz", xml))
    assert len(p.materials) == 1 and all(r.material_id == p.materials[0].id for r in p.regions)
    from stratalab.geometry import polygon_area
    assert all(polygon_area(r.points) > 0 for r in p.regions)


def test_export_round_trip(tmp_path):
    q = layered_slope_with_water()
    out = tmp_path / "out.gsz"
    write_gsz(q, out)
    with zipfile.ZipFile(out) as z:
        xml = z.read(z.namelist()[0]).decode()
    assert xml.startswith("<?xml") and "<GSIData" in xml
    back = read_gsz(out)
    assert [sorted(map(tuple, r.points)) for r in back.regions] == [sorted(map(tuple, r.points)) for r in q.regions]
    # shared vertices are written once
    assert xml.count("<Point ") == len({tuple(pt) for r in q.regions for pt in r.points})


def test_not_a_gsz(tmp_path):
    bad = tmp_path / "bad.gsz"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="not a GeoStudio"):
        read_gsz(bad)
