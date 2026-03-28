#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Tests for SimStackServer/WaNo/WaNoDSL.py"""
import pytest

from SimStackServer.WaNo.WaNoDSL import (
    Bool,
    Box,
    Choice,
    DynamicChoice,
    File,
    Float,
    Int,
    Matrix,
    MultipleOf,
    NoneNode,
    Root,
    String,
    Switch,
    SwitchOption,
    ThreeRandom,
)


# ---------------------------------------------------------------------------
# to_spec() tests — no model construction, just dict shape
# ---------------------------------------------------------------------------


class TestFloatSpec:
    def test_default(self):
        assert Float("x").to_spec() == {"type": "float", "name": "x", "value": -100.0}

    def test_value(self):
        assert Float("x", value=3.14).to_spec()["value"] == pytest.approx(3.14)

    def test_no_extra_keys_by_default(self):
        assert set(Float("x").to_spec().keys()) == {"type", "name", "value"}

    def test_description(self):
        assert Float("x", description="a float").to_spec()["description"] == "a float"

    def test_visibility(self):
        spec = Float(
            "x",
            visibility_condition="%s == True",
            visibility_var_path="a.b",
        ).to_spec()
        assert spec["visibility_condition"] == "%s == True"
        assert spec["visibility_var_path"] == "a.b"

    def test_import_from(self):
        assert (
            Float("x", import_from="other.path").to_spec()["import_from"]
            == "other.path"
        )

    def test_force_disable(self):
        assert Float("x", force_disable=True).to_spec()["force_disable"] is True

    def test_no_description_key_when_absent(self):
        assert "description" not in Float("x").to_spec()

    def test_no_visibility_keys_when_absent(self):
        spec = Float("x").to_spec()
        assert "visibility_condition" not in spec
        assert "visibility_var_path" not in spec


class TestIntSpec:
    def test_type(self):
        assert Int("n").to_spec()["type"] == "int"

    def test_value_stored_as_float(self):
        assert isinstance(Int("n", value=5).to_spec()["value"], float)

    def test_value(self):
        assert Int("n", value=42).to_spec()["value"] == pytest.approx(42.0)


class TestBoolSpec:
    def test_true(self):
        assert Bool("flag", value=True).to_spec()["value"] is True

    def test_false_default(self):
        assert Bool("flag").to_spec()["value"] is False

    def test_type(self):
        assert Bool("flag").to_spec()["type"] == "bool"


class TestStringSpec:
    def test_default(self):
        assert String("s").to_spec() == {"type": "string", "name": "s", "value": ""}

    def test_value(self):
        assert String("s", value="hello").to_spec()["value"] == "hello"

    def test_dynamic_output(self):
        assert (
            String("s", dynamic_output="out.yml").to_spec()["dynamic_output"]
            == "out.yml"
        )

    def test_no_dynamic_output_key_when_absent(self):
        assert "dynamic_output" not in String("s").to_spec()


class TestFileSpec:
    def test_defaults(self):
        spec = File("f").to_spec()
        assert spec["type"] == "file"
        assert spec["path"] == ""
        assert spec["logical_filename"] == ""
        assert spec["local"] is True

    def test_fields(self):
        spec = File(
            "f", path="data.txt", logical_filename="input.dat", local=False
        ).to_spec()
        assert spec["path"] == "data.txt"
        assert spec["logical_filename"] == "input.dat"
        assert spec["local"] is False


class TestChoiceSpec:
    def test_fields(self):
        spec = Choice("method", ["a", "b", "c"], chosen=1).to_spec()
        assert spec["type"] == "choice"
        assert spec["choices"] == ["a", "b", "c"]
        assert spec["chosen"] == 1

    def test_default_chosen(self):
        assert Choice("m", ["x", "y"]).to_spec()["chosen"] == 0


class TestDynamicChoiceSpec:
    def test_fields(self):
        spec = DynamicChoice(
            "sel",
            collection_path="Tabs.IO.items",
            subpath="name",
            chosen=2,
        ).to_spec()
        assert spec["type"] == "dynamic_choice"
        assert spec["collection_path"] == "Tabs.IO.items"
        assert spec["subpath"] == "name"
        assert spec["chosen"] == 2


class TestMatrixSpec:
    def test_minimal(self):
        spec = Matrix("m", rows=2, cols=3).to_spec()
        assert spec["rows"] == 2
        assert spec["cols"] == 3
        assert "col_header" not in spec
        assert "row_header" not in spec
        assert "data_text" not in spec

    def test_headers(self):
        spec = Matrix(
            "m", rows=1, cols=2, col_header=["A", "B"], row_header=["R1"]
        ).to_spec()
        assert spec["col_header"] == ["A", "B"]
        assert spec["row_header"] == ["R1"]

    def test_data_text(self):
        assert Matrix("m", data_text="1 2\n3 4").to_spec()["data_text"] == "1 2\n3 4"


class TestNoneNodeSpec:
    def test_spec(self):
        assert NoneNode("placeholder").to_spec() == {
            "type": "none",
            "name": "placeholder",
        }


class TestThreeRandomSpec:
    def test_type(self):
        assert ThreeRandom("rand").to_spec()["type"] == "three_random"

    def test_value(self):
        assert ThreeRandom("rand", value="abc").to_spec()["value"] == "abc"


class TestBoxSpec:
    def test_empty(self):
        spec = Box("group").to_spec()
        assert spec["type"] == "dict"
        assert spec["children"] == []

    def test_with_children(self):
        spec = Box("group", Float("x", value=1.0), Int("n", value=2)).to_spec()
        assert len(spec["children"]) == 2
        assert spec["children"][0]["type"] == "float"
        assert spec["children"][1]["type"] == "int"

    def test_style(self):
        assert Box("group", style="tabs").to_spec()["style"] == "tabs"

    def test_no_style_key_when_absent(self):
        assert "style" not in Box("group").to_spec()

    def test_nested(self):
        spec = Box("outer", Box("inner", Float("x"))).to_spec()
        assert spec["children"][0]["type"] == "dict"
        assert spec["children"][0]["children"][0]["type"] == "float"


class TestSwitchSpec:
    def test_fields(self):
        spec = Switch(
            "sw",
            SwitchOption("optA", Box("A", Float("x"))),
            SwitchOption("optB", Box("B", Int("n"))),
            switch_path="Settings.method",
        ).to_spec()
        assert spec["type"] == "switch"
        assert spec["switch_path"] == "Settings.method"
        assert len(spec["options"]) == 2
        assert spec["options"][0]["switch_name"] == "optA"
        assert spec["options"][1]["switch_name"] == "optB"

    def test_option_child_spec(self):
        spec = Switch(
            "sw",
            SwitchOption("A", Float("x", value=1.0)),
        ).to_spec()
        assert spec["options"][0]["spec"]["type"] == "float"
        assert spec["options"][0]["spec"]["value"] == pytest.approx(1.0)


class TestMultipleOfSpec:
    def test_empty_items(self):
        spec = MultipleOf("mol", template=[String("name"), Float("mass")]).to_spec()
        assert spec["type"] == "multipleof"
        assert len(spec["template"]["children"]) == 2
        assert spec["items"] == []

    def test_template_types(self):
        spec = MultipleOf("mol", template=[String("name"), Float("mass")]).to_spec()
        assert spec["template"]["children"][0]["type"] == "string"
        assert spec["template"]["children"][1]["type"] == "float"

    def test_with_items(self):
        spec = MultipleOf(
            "mol",
            template=[String("name"), Float("mass")],
            items=[
                [String("name", value="H2O"), Float("mass", value=18.015)],
                [String("name", value="CO2"), Float("mass", value=44.01)],
            ],
        ).to_spec()
        assert len(spec["items"]) == 2
        assert spec["items"][0]["children"][0]["value"] == "H2O"
        assert spec["items"][1]["children"][1]["value"] == pytest.approx(44.01)


class TestRootSpec:
    def test_minimal(self):
        spec = Root("MyWaNo").to_spec()
        assert spec["type"] == "root"
        assert spec["name"] == "MyWaNo"
        assert spec["exec_command"] == ""
        assert spec["output_files"] == []
        assert spec["input_files"] == []
        assert spec["children"] == []

    def test_children(self):
        spec = Root("R", Float("x"), Int("n")).to_spec()
        assert len(spec["children"]) == 2

    def test_input_files_format(self):
        spec = Root("R", input_files=[("input.dat", "data/input.dat")]).to_spec()
        assert spec["input_files"] == [
            {"logical_filename": "input.dat", "path": "data/input.dat"}
        ]

    def test_output_files(self):
        spec = Root("R", output_files=["out.yml", "report.html"]).to_spec()
        assert spec["output_files"] == ["out.yml", "report.html"]

    def test_exec_command(self):
        assert Root("R", exec_command="echo hi").to_spec()["exec_command"] == "echo hi"


# ---------------------------------------------------------------------------
# to_model() tests — verify live model data
# ---------------------------------------------------------------------------


class TestToModel:
    def test_float(self):
        model = Float("temp", value=300.0).to_model()
        assert model.get_name() == "temp"
        assert model.get_data() == pytest.approx(300.0)

    def test_int(self):
        model = Int("steps", value=100).to_model()
        assert model.get_name() == "steps"
        assert model.get_data() == pytest.approx(100.0)

    def test_bool_true(self):
        model = Bool("flag", value=True).to_model()
        assert model.get_data() is True

    def test_bool_false(self):
        model = Bool("flag", value=False).to_model()
        assert model.get_data() is False

    def test_string(self):
        model = String("label", value="hello").to_model()
        assert model.get_data() == "hello"

    def test_file_name(self):
        model = File("f", path="data.txt", logical_filename="input.dat").to_model()
        assert model.get_name() == "f"

    def test_choice_returns_selected_string(self):
        model = Choice("method", ["dft", "mp2", "ccsd"], chosen=1).to_model()
        assert model.get_data() == "mp2"

    def test_none_node(self):
        model = NoneNode("placeholder").to_model()
        assert model.get_name() == "placeholder"

    def test_box_child_access(self):
        model = Box("Settings", Float("T", value=300.0), Int("N", value=10)).to_model()
        assert model["T"].get_data() == pytest.approx(300.0)
        assert model["N"].get_data() == pytest.approx(10.0)

    def test_multiple_of_items(self):
        model = MultipleOf(
            "molecules",
            template=[String("name"), Float("mass")],
            items=[
                [String("name", value="H2O"), Float("mass", value=18.015)],
            ],
        ).to_model()
        assert len(model.list_of_dicts) == 1
        assert model.list_of_dicts[0]["name"].get_data() == "H2O"
        assert model.list_of_dicts[0]["mass"].get_data() == pytest.approx(18.015)


# ---------------------------------------------------------------------------
# Root.to_model() — integration
# ---------------------------------------------------------------------------


class TestRootToModel:
    def test_basic(self):
        model = Root(
            "MyWaNo",
            Float("temperature", value=300.0),
            exec_command="echo hello",
            output_files=["out.yml"],
        ).to_model()
        assert model["temperature"].get_data() == pytest.approx(300.0)
        assert model.exec_command == "echo hello"
        assert "out.yml" in model.output_files

    def test_nested_box(self):
        model = Root(
            "R",
            Box(
                "Settings",
                Float("T", value=400.0),
                Bool("verbose", value=True),
            ),
        ).to_model()
        assert model["Settings"]["T"].get_data() == pytest.approx(400.0)
        assert model["Settings"]["verbose"].get_data() is True

    def test_input_files(self):
        model = Root(
            "R",
            input_files=[("run.sh", "scripts/run.sh")],
        ).to_model()
        assert ("run.sh", "scripts/run.sh") in model.input_files

    def test_deeply_nested(self):
        model = Root(
            "Deep",
            Box(
                "Outer",
                Box(
                    "Inner",
                    Float("value", value=42.0),
                ),
            ),
        ).to_model()
        assert model["Outer"]["Inner"]["value"].get_data() == pytest.approx(42.0)

    def test_multiple_of_in_root(self):
        model = Root(
            "R",
            MultipleOf(
                "atoms",
                template=[String("element"), Float("charge")],
                items=[
                    [String("element", value="C"), Float("charge", value=6.0)],
                    [String("element", value="H"), Float("charge", value=1.0)],
                ],
            ),
        ).to_model()
        assert len(model["atoms"].list_of_dicts) == 2
        assert model["atoms"].list_of_dicts[0]["element"].get_data() == "C"
        assert model["atoms"].list_of_dicts[1]["charge"].get_data() == pytest.approx(
            1.0
        )

    def test_round_trip_spec(self):
        """Builder → to_spec → Root.from_spec → to_spec produces same dict."""
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

        original_spec = Root(
            "RT",
            Box("S", Float("T", value=300.0), Int("N", value=5)),
            exec_command="run.sh",
            output_files=["out.yml"],
        ).to_spec()

        model = WaNoModelRoot.from_spec(original_spec)
        round_tripped = model.to_spec()

        assert round_tripped["name"] == "RT"
        assert round_tripped["exec_command"] == "run.sh"
        assert round_tripped["output_files"] == ["out.yml"]
        assert round_tripped["children"][0]["name"] == "S"
        assert round_tripped["children"][0]["children"][0]["value"] == pytest.approx(
            300.0
        )
        assert round_tripped["children"][0]["children"][1]["value"] == pytest.approx(
            5.0
        )


# ---------------------------------------------------------------------------
# Complex realistic example: GROMACS-style molecular dynamics WaNo
# ---------------------------------------------------------------------------

# Build the WaNo once at module level so every test method shares it.
# This also serves as a readable, self-documenting example of the DSL.
_MD_WANO = Root(
    "MolecularDynamics",
    # ── System composition ──────────────────────────────────────────────────
    Box(
        "System",
        MultipleOf(
            "components",
            template=[
                String("molecule_name"),
                Int("count"),
                Float("charge_e"),
            ],
            items=[
                [
                    String("molecule_name", value="water"),
                    Int("count", value=1000),
                    Float("charge_e", value=0.0),
                ],
                [
                    String("molecule_name", value="NaCl"),
                    Int("count", value=50),
                    Float("charge_e", value=0.0),
                ],
            ],
        ),
        Choice(
            "force_field",
            ["AMBER99SB-ILDN", "CHARMM36m", "GROMOS54A7", "OPLS-AA"],
            chosen=1,
            description="Force-field parameter set",
        ),
        File("topology", path="system.top", logical_filename="topology.top"),
        File(
            "initial_coordinates",
            path="system.gro",
            logical_filename="coordinates.gro",
        ),
    ),
    # ── Run parameters ──────────────────────────────────────────────────────
    Box(
        "Simulation",
        Float("timestep_ps", value=0.002, description="Integration timestep in ps"),
        Int("n_steps", value=500000, description="Total number of MD steps"),
        Float("temperature_K", value=300.0),
        # Ensemble selector: three mutually-exclusive sub-parameter sets
        Switch(
            "ensemble",
            SwitchOption(
                "NVT",
                Box(
                    "NVT",
                    Choice(
                        "thermostat",
                        ["v-rescale", "Nose-Hoover", "Berendsen"],
                        chosen=0,
                    ),
                    Float("tau_t_ps", value=0.1),
                ),
            ),
            SwitchOption(
                "NPT",
                Box(
                    "NPT",
                    Choice(
                        "thermostat",
                        ["v-rescale", "Nose-Hoover", "Berendsen"],
                        chosen=1,
                    ),
                    Float("tau_t_ps", value=0.1),
                    Choice(
                        "barostat",
                        ["Parrinello-Rahman", "Berendsen", "MTTK"],
                        chosen=0,
                    ),
                    Float("tau_p_ps", value=2.0),
                    Float("ref_pressure_bar", value=1.0),
                ),
            ),
            SwitchOption(
                "NVE",
                Box(
                    "NVE",
                    Bool("remove_com_motion", value=True),
                ),
            ),
            switch_path="Simulation.ensemble",
        ),
    ),
    # ── Non-bonded interactions ─────────────────────────────────────────────
    Box(
        "NonBonded",
        Float("cutoff_nm", value=1.2),
        Float("ewald_rtol", value=1.0e-5),
        Choice("coulomb_type", ["PME", "Cut-off", "Ewald", "P3M-AD"], chosen=0),
        Choice("vdw_type", ["Cut-off", "PME", "Shift"], chosen=0),
        Bool("dispersion_correction", value=True),
    ),
    # ── Output frequencies ──────────────────────────────────────────────────
    Box(
        "Output",
        Int("nstxout", value=5000, description="Coordinate write frequency (steps)"),
        Int("nstvout", value=5000, description="Velocity write frequency (steps)"),
        Int("nstfout", value=0, description="Force write frequency (steps)"),
        Int("nstlog", value=500, description="Log write frequency (steps)"),
        Int("nstener", value=500, description="Energy write frequency (steps)"),
        Bool("compressed_trajectory", value=True),
    ),
    # ── Constraint settings ─────────────────────────────────────────────────
    Box(
        "Constraints",
        Choice(
            "constraint_algorithm",
            ["LINCS", "SHAKE"],
            chosen=0,
        ),
        Choice(
            "constraints",
            ["none", "h-bonds", "all-bonds", "h-angles", "all-angles"],
            chosen=1,
        ),
        Int("lincs_order", value=4),
        Int("lincs_iter", value=1),
        Bool("continuation", value=False, description="Restart from checkpoint"),
    ),
    # ── Provenance ──────────────────────────────────────────────────────────
    ThreeRandom("job_id"),
    # ── WaNo metadata ───────────────────────────────────────────────────────
    exec_command=(
        "gmx grompp -f md.mdp -c coordinates.gro -p topology.top -o run.tpr && "
        "gmx mdrun -v -deffnm md"
    ),
    output_files=["md.xtc", "md.edr", "md.gro", "md.log"],
    input_files=[
        ("topology.top", "system.top"),
        ("coordinates.gro", "system.gro"),
    ],
)


class TestMolecularDynamicsWaNo:
    """Full integration test using a realistic GROMACS-style MD WaNo."""

    # ── Spec structure ───────────────────────────────────────────────────────

    def test_root_metadata(self):
        spec = _MD_WANO.to_spec()
        assert spec["name"] == "MolecularDynamics"
        assert "gmx grompp" in spec["exec_command"]
        assert "gmx mdrun" in spec["exec_command"]
        assert set(spec["output_files"]) == {"md.xtc", "md.edr", "md.gro", "md.log"}
        assert {"logical_filename": "topology.top", "path": "system.top"} in spec[
            "input_files"
        ]

    def test_top_level_box_names(self):
        spec = _MD_WANO.to_spec()
        child_names = [c["name"] for c in spec["children"]]
        assert "System" in child_names
        assert "Simulation" in child_names
        assert "NonBonded" in child_names
        assert "Output" in child_names
        assert "Constraints" in child_names
        assert "job_id" in child_names

    def test_multipleof_template_shape(self):
        spec = _MD_WANO.to_spec()
        system = next(c for c in spec["children"] if c["name"] == "System")
        mol = next(c for c in system["children"] if c["name"] == "components")
        assert mol["type"] == "multipleof"
        template_types = [c["type"] for c in mol["template"]["children"]]
        assert template_types == ["string", "int", "float"]

    def test_multipleof_has_two_items(self):
        spec = _MD_WANO.to_spec()
        system = next(c for c in spec["children"] if c["name"] == "System")
        mol = next(c for c in system["children"] if c["name"] == "components")
        assert len(mol["items"]) == 2
        assert mol["items"][0]["children"][0]["value"] == "water"
        assert mol["items"][1]["children"][0]["value"] == "NaCl"

    def test_switch_has_three_options(self):
        spec = _MD_WANO.to_spec()
        sim = next(c for c in spec["children"] if c["name"] == "Simulation")
        switch = next(c for c in sim["children"] if c["name"] == "ensemble")
        assert switch["type"] == "switch"
        assert switch["switch_path"] == "Simulation.ensemble"
        option_names = [o["switch_name"] for o in switch["options"]]
        assert option_names == ["NVT", "NPT", "NVE"]

    def test_npt_option_has_barostat(self):
        spec = _MD_WANO.to_spec()
        sim = next(c for c in spec["children"] if c["name"] == "Simulation")
        switch = next(c for c in sim["children"] if c["name"] == "ensemble")
        npt_spec = next(
            o["spec"] for o in switch["options"] if o["switch_name"] == "NPT"
        )
        child_names = [c["name"] for c in npt_spec["children"]]
        assert "barostat" in child_names
        assert "tau_p_ps" in child_names
        assert "ref_pressure_bar" in child_names

    def test_force_field_choice_spec(self):
        spec = _MD_WANO.to_spec()
        system = next(c for c in spec["children"] if c["name"] == "System")
        ff = next(c for c in system["children"] if c["name"] == "force_field")
        assert ff["type"] == "choice"
        assert "CHARMM36m" in ff["choices"]
        assert ff["choices"][ff["chosen"]] == "CHARMM36m"

    def test_description_propagated(self):
        spec = _MD_WANO.to_spec()
        sim = next(c for c in spec["children"] if c["name"] == "Simulation")
        timestep = next(c for c in sim["children"] if c["name"] == "timestep_ps")
        assert "timestep" in timestep["description"].lower()

    # ── Live model ───────────────────────────────────────────────────────────

    def test_model_construction_succeeds(self):
        model = _MD_WANO.to_model()
        assert model.get_name() == "MolecularDynamics"

    def test_model_scalar_access(self):
        model = _MD_WANO.to_model()
        assert model["Simulation"]["timestep_ps"].get_data() == pytest.approx(0.002)
        assert model["Simulation"]["n_steps"].get_data() == pytest.approx(500000.0)
        assert model["Simulation"]["temperature_K"].get_data() == pytest.approx(300.0)

    def test_model_nonbonded(self):
        model = _MD_WANO.to_model()
        nb = model["NonBonded"]
        assert nb["cutoff_nm"].get_data() == pytest.approx(1.2)
        assert nb["ewald_rtol"].get_data() == pytest.approx(1.0e-5)
        assert nb["coulomb_type"].get_data() == "PME"
        assert nb["dispersion_correction"].get_data() is True

    def test_model_output_frequencies(self):
        model = _MD_WANO.to_model()
        out = model["Output"]
        assert out["nstxout"].get_data() == pytest.approx(5000.0)
        assert out["nstfout"].get_data() == pytest.approx(0.0)
        assert out["compressed_trajectory"].get_data() is True

    def test_model_constraints(self):
        model = _MD_WANO.to_model()
        cst = model["Constraints"]
        assert cst["constraint_algorithm"].get_data() == "LINCS"
        assert cst["constraints"].get_data() == "h-bonds"
        assert cst["lincs_order"].get_data() == pytest.approx(4.0)
        assert cst["continuation"].get_data() is False

    def test_model_multipleof_items(self):
        model = _MD_WANO.to_model()
        components = model["System"]["components"]
        assert len(components.list_of_dicts) == 2
        assert components.list_of_dicts[0]["molecule_name"].get_data() == "water"
        assert components.list_of_dicts[0]["count"].get_data() == pytest.approx(1000.0)
        assert components.list_of_dicts[1]["molecule_name"].get_data() == "NaCl"
        assert components.list_of_dicts[1]["count"].get_data() == pytest.approx(50.0)

    def test_model_force_field(self):
        model = _MD_WANO.to_model()
        assert model["System"]["force_field"].get_data() == "CHARMM36m"

    def test_model_input_files(self):
        model = _MD_WANO.to_model()
        lf_names = [lf for lf, _ in model.input_files]
        assert "topology.top" in lf_names
        assert "coordinates.gro" in lf_names

    def test_model_output_files(self):
        model = _MD_WANO.to_model()
        assert set(model.output_files) == {"md.xtc", "md.edr", "md.gro", "md.log"}

    # ── Round-trip ───────────────────────────────────────────────────────────

    def test_round_trip_preserves_structure(self):
        """Builder → model → to_spec → from_spec → model: data survives two hops."""
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

        spec1 = _MD_WANO.to_spec()
        model1 = WaNoModelRoot.from_spec(spec1)
        spec2 = model1.to_spec()
        model2 = WaNoModelRoot.from_spec(spec2)

        # Scalar deep inside a nested box survives two serialisation round-trips
        assert model2["NonBonded"]["cutoff_nm"].get_data() == pytest.approx(1.2)
        assert model2["Simulation"]["temperature_K"].get_data() == pytest.approx(300.0)

    def test_round_trip_preserves_multipleof(self):
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

        model = WaNoModelRoot.from_spec(
            WaNoModelRoot.from_spec(_MD_WANO.to_spec()).to_spec()
        )
        components = model["System"]["components"]
        assert len(components.list_of_dicts) == 2
        assert components.list_of_dicts[0]["molecule_name"].get_data() == "water"

    def test_round_trip_preserves_switch_options(self):
        # Note: WaNoSwitchModel._name is the currently-selected option's name
        # (matching XML-path behaviour), so after a round-trip the switch
        # element carries the selected option name rather than "ensemble".
        # Search by type to find it reliably.
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

        spec = WaNoModelRoot.from_spec(_MD_WANO.to_spec()).to_spec()
        sim = next(c for c in spec["children"] if c["name"] == "Simulation")
        switch = next(c for c in sim["children"] if c["type"] == "switch")
        assert len(switch["options"]) == 3
        assert switch["options"][1]["switch_name"] == "NPT"
