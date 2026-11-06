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


# structure of a solved GeoStudio 2025 consolidation project (analyses, boundary definitions, contexts)
FULL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<GSIData Version="11.12" AppVersion="25.2.1.39">
  <FileInfo FileVersion="11.08" Title="Layer" Author="Tester" />
  <Analyses Len="2">
    <Analysis><ID>1</ID><Name>In Situ</Name><Kind>SIGMA/W</Kind><Method>Insitu2</Method><GeometryId>1</GeometryId>
      <TimeIncrements><Duration Missing="true" /><TimeSteps Len="1"><TimeStep Save="true" /></TimeSteps></TimeIncrements>
    </Analysis>
    <Analysis><ID>2</ID><Name>Consolidation</Name><Kind>SIGMA/W</Kind><ParentID>1</ParentID>
      <Method>Consolidation</Method><GeometryId>1</GeometryId>
      <TimeIncrements><Duration>1e+08</Duration><IncrementCount>5</IncrementCount></TimeIncrements>
    </Analysis>
  </Analyses>
  <BCs Len="4">
    <BC ID="1" Name="Fixed X" XDisp="DispDisplacementX(Variability=Constant,Value=0)" YDisp="ForceDispUndefined()" />
    <BC ID="3" Name="Fixed X/Y" XDisp="DispDisplacementX(Variability=Constant,Value=0)" YDisp="DispDisplacementY(Variability=Constant,Value=0)" />
    <BC ID="5" Name="Drain" Hydraulic="HydPressureHead(Variability=Constant,Value=0)" />
    <BC ID="9" Name="load" XDisp="DispNormTanX(VariabilityNorm=Constant,DispNorm=50,VariabilityTan=Constant,DispTan=0)" YDisp="DispNormTanY(VariabilityNorm=Constant,DispNorm=0,VariabilityTan=Constant,DispTan=0)" />
  </BCs>
  <Contexts Len="2">
    <Context><AnalysisID>1</AnalysisID>
      <GeometryUsesMaterials Len="1"><GeometryUsesMaterial ID="Regions-1" Entry="1" /></GeometryUsesMaterials>
      <GeometryUsesXDispBCs Len="3"><GeometryUsesXDispBC ID="Lines-2" Entry="1" /><GeometryUsesXDispBC ID="Lines-4" Entry="1" />
        <GeometryUsesXDispBC ID="Lines-1" Entry="3" /></GeometryUsesXDispBCs>
    </Context>
    <Context><AnalysisID>2</AnalysisID>
      <GeometryUsesMaterials Len="1"><GeometryUsesMaterial ID="Regions-1" Entry="1" /></GeometryUsesMaterials>
      <GeometryUsesHydraulicBCs Len="3"><GeometryUsesHydraulicBC ID="Lines-3" Entry="5" />
        <GeometryUsesHydraulicBC ID="Lines-6" Entry="5" /><GeometryUsesHydraulicBC ID="Lines-5" Entry="5" /></GeometryUsesHydraulicBCs>
      <GeometryUsesXDispBCs Len="5"><GeometryUsesXDispBC ID="Lines-2" Entry="1" /><GeometryUsesXDispBC ID="Lines-4" Entry="1" />
        <GeometryUsesXDispBC ID="Lines-1" Entry="3" /><GeometryUsesXDispBC ID="Lines-3" Entry="9" />
        <GeometryUsesXDispBC ID="Lines-6" Entry="9" /></GeometryUsesXDispBCs>
    </Context>
  </Contexts>
  <Coordinates><EngCoords UnitSystem="Metric" /></Coordinates>
  <Geometries Len="1"><Geometry><Name>2D Geometry</Name>
    <Points Len="6"><Point ID="1" X="0" Y="0" /><Point ID="2" X="20" Y="0" /><Point ID="3" X="20" Y="5" />
      <Point ID="4" X="0" Y="5" /><Point ID="5" X="10" Y="5" /><Point ID="6" X="10" Y="1" /></Points>
    <Lines Len="6">
      <Line><ID>1</ID><PointID1>1</PointID1><PointID2>2</PointID2></Line>
      <Line><ID>2</ID><PointID1>2</PointID1><PointID2>3</PointID2></Line>
      <Line><ID>3</ID><PointID1>3</PointID1><PointID2>5</PointID2></Line>
      <Line><ID>6</ID><PointID1>5</PointID1><PointID2>4</PointID2></Line>
      <Line><ID>4</ID><PointID1>4</PointID1><PointID2>1</PointID2></Line>
      <Line><ID>5</ID><PointID1>5</PointID1><PointID2>6</PointID2><Pinned>true</Pinned><IsMeshed>true</IsMeshed></Line>
    </Lines>
    <Regions Len="1"><Region><ID>1</ID><PointIDs>1,2,3,5,4</PointIDs></Region></Regions>
  </Geometry></Geometries>
  <Materials Len="1"><Material><ID>1</ID><Color>RGB=(255,255,128)</Color><Name>clay</Name><SeepModel>SatOnly</SeepModel>
    <SlopeModel>None</SlopeModel><StressModel>LinearElastic</StressModel>
    <StressStrain><UnitWeight>18</UnitWeight><YoungsPrimeModulus>8000</YoungsPrimeModulus>
      <EffectivePoissonsRatio>0.3</EffectivePoissonsRatio><OCRatio Missing="true" /><InitVoidRatio>0.9</InitVoidRatio></StressStrain>
    <Hydraulic KYXRatio="1" KSat="1e-08" Beta="6e-05" UseInitPWP="true" /></Material></Materials>
</GSIData>"""


def test_import_full_project(tmp_path):
    p = read_gsz(make_gsz(tmp_path / "full.gsz", FULL))
    assert (p.title, p.author) == ("Layer", "Tester")
    m = p.materials[0]
    assert (m.name, m.stress_model, m.hyd_model, m.unit_weight, m.E, m.nu, m.e0, m.k_sat, m.mv) == \
        ("clay", "linear_elastic", "saturated", 18, 8000, 0.3, 0.9, 1e-8, 6e-5)
    ins, con = p.analyses
    assert (ins.kind, ins.stress_type, con.stress_type, con.parent_id, con.duration, con.n_steps) == \
        ("stress", "insitu", "consolidation", ins.id, 1e8, 5)
    assert p.mesh_lines == [[[10, 5], [10, 1]]]
    by = {(b.type, tuple(map(tuple, b.points))): b for b in p.boundary_conditions}
    for seg in (((20, 5), (10, 5)), ((10, 5), (0, 5))):
        assert by[("pressure", seg)].value == 50 and by[("pressure", seg)].analyses == [con.id]
    assert by[("fixed_xy", ((0, 0), (20, 0)))].analyses == []                       # used by both analyses
    assert by[("pressure_head", ((10, 5), (10, 1)))].analyses == [con.id]           # interior drain
    from stratalab.solver import verify
    assert verify(p, con) == []


def test_full_project_export_round_trip(tmp_path):
    p = read_gsz(make_gsz(tmp_path / "full.gsz", FULL))
    out = tmp_path / "again.gsz"
    assert write_gsz(p, out) == []
    q = read_gsz(out)
    key = lambda pr: sorted((b.type, b.value, tuple(map(tuple, b.points)), tuple(pr.analysis(i).name for i in b.analyses))
                            for b in pr.boundary_conditions)
    assert key(q) == key(p)
    assert [(a.name, a.stress_type) for a in q.analyses] == [(a.name, a.stress_type) for a in p.analyses]
    assert q.mesh_lines == p.mesh_lines


def test_imported_consolidation_solves(tmp_path):
    p = read_gsz(make_gsz(tmp_path / "full.gsz", FULL))
    from stratalab.solver import solve
    for a in p.analyses:
        a.mesh_size = 0.5
    r = solve(p, p.analyses[1])
    assert r["settlement_history"][-1] > r["settlement_history"][0] > 0


# structure of a GeoStudio 2026 SLOPE/W project (entry and exit, piezometric line)
SLOPE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<GSIData Version="11.15" AppVersion="26.1.0.1261">
  <FileInfo FileVersion="11.15" RevNumber="1" />
  <Analyses Len="1"><Analysis><ID>1</ID><Name>Slope Stability</Name><Kind>SLOPE/W</Kind>
    <Method>Morgenstern-Price</Method><GeometryId>1</GeometryId></Analysis></Analyses>
  <Contexts Len="1"><Context><AnalysisID>1</AnalysisID><GeometryUsesMaterials Len="2">
    <GeometryUsesMaterial ID="Regions-1" Entry="2" /><GeometryUsesMaterial ID="Regions-2" Entry="1" />
  </GeometryUsesMaterials></Context></Contexts>
  <Coordinates><EngCoords UnitSystem="Metric" /></Coordinates>
  <Geometries Len="1"><Geometry><Name>2D Geometry</Name>
    <Points Len="7"><Point ID="1" X="0" Y="0" /><Point ID="2" X="50" Y="0" /><Point ID="3" X="50" Y="10" />
      <Point ID="4" X="15" Y="10" /><Point ID="5" X="0" Y="10" /><Point ID="6" X="50" Y="20" />
      <Point ID="7" X="30" Y="20" /></Points>
    <Regions Len="2"><Region><ID>1</ID><PointIDs>1,2,3,4,5</PointIDs></Region>
      <Region><ID>2</ID><PointIDs>4,3,6,7</PointIDs></Region></Regions>
  </Geometry></Geometries>
  <Materials Len="2">
    <Material><ID>1</ID><Name>sand</Name><SlopeModel>MohrCoulomb</SlopeModel><StressStrain>
      <UnitWeight>20</UnitWeight><CohesionPrime>2</CohesionPrime><PhiPrime>33</PhiPrime></StressStrain></Material>
    <Material><ID>2</ID><Name>clay</Name><SlopeModel>MohrCoulomb</SlopeModel><StressStrain>
      <UnitWeight>18</UnitWeight><CohesionPrime>10</CohesionPrime><PhiPrime>25</PhiPrime></StressStrain></Material>
  </Materials>
  <StabilityItems Len="1"><StabilityItem><AnalysisID>1</AnalysisID><Entry>
    <DataPoints Len="3"><DataPoint Number="1" X="0" Y="8" /><DataPoint Number="2" X="25" Y="12" />
      <DataPoint Number="3" X="50" Y="16" /></DataPoints>
    <SlipSurface><EntryExit><LeftSideLeftPt X="3" Y="10" /><LeftSideRightPt X="15" Y="10" /><LeftInc>8</LeftInc>
      <RightSideLeftPt X="32" Y="20" /><RightSideRightPt X="46" Y="20" /><RightInc>8</RightInc></EntryExit>
      <DirectionOfSlip>RightToLeft</DirectionOfSlip></SlipSurface>
    <PiezometricSurfaces Len="1"><PiezometricSurface><ID>1</ID><DataPoints Len="3"><DataPoint>1</DataPoint>
      <DataPoint>2</DataPoint><DataPoint>3</DataPoint></DataPoints></PiezometricSurface></PiezometricSurfaces>
  </Entry></StabilityItem></StabilityItems>
  <WaterItems Len="1"><WaterItem><AnalysisID>1</AnalysisID><Entry><ResultInputInfo><Option>PiezoSurface</Option>
    </ResultInputInfo><UnitWaterWeight>9.807</UnitWaterWeight></Entry></WaterItem></WaterItems>
</GSIData>"""


def test_import_slope_project_and_solve(tmp_path):
    p = read_gsz(make_gsz(tmp_path / "slope.gsz", SLOPE))
    a = p.analyses[0]
    assert (a.kind, a.method, a.pwp) == ("slope", "morgenstern_price", "piezometric")
    assert p.piezometric_line == [[0, 8], [25, 12], [50, 16]]
    s = a.search
    assert (s.mode, s.entry_x1, s.entry_x2, s.exit_x1, s.exit_x2, s.n_entry, s.n_exit) == \
        ("entry_exit", 32, 46, 3, 15, 9, 9)
    names = {m.id: m.name for m in p.materials}
    assert [names[r.material_id] for r in p.regions] == ["clay", "sand"]
    from stratalab.solver import solve
    crit = solve(p, a)["critical"]
    # GeoStudio 2026.1 (SLOPE/W, Morgenstern-Price) gives 1.225 for this model: circle centre
    # (8.0, 41.35), R 32.1, entering the crest at x = 32 and leaving at the toe x = 15
    assert abs(crit["fos"] - 1.225) < 0.01
    sf = crit["surface"]
    assert abs(sf["x1"] - 15) < 0.01 and abs(sf["x2"] - 32) < 0.01
    assert abs(sf["xc"] - 8.0) < 1.5 and abs(sf["R"] - 32.1) < 2.0


def test_slope_project_export_round_trip(tmp_path):
    p = read_gsz(make_gsz(tmp_path / "slope.gsz", SLOPE))
    out = tmp_path / "again.gsz"
    assert write_gsz(p, out) == []
    q = read_gsz(out)
    a, b = p.analyses[0], q.analyses[0]
    assert (b.kind, b.method, b.pwp) == (a.kind, a.method, a.pwp)
    assert vars(b.search) == vars(a.search) and q.piezometric_line == p.piezometric_line
    assert [(m.name, m.cohesion, m.phi, m.unit_weight) for m in q.materials] == \
        [(m.name, m.cohesion, m.phi, m.unit_weight) for m in p.materials]
