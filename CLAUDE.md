# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Community fork (poly-hammer) of Epic's BlenderTools: two Blender addons for Blender → Unreal Engine workflows, living in `src/addons/`:

- **send2ue** ("Send to Unreal") — exports selected Blender assets (meshes, skeletons, animations, grooms) and imports them into a running Unreal Editor.
- **ue2rigify** ("UE to Rigify") — node-based retargeting between Unreal skeletons and Blender's Rigify rigs.

Supported range is Blender 5.0 → 5.2 and Unreal 5.6 → 5.8. Code must stay compatible across that range (see version compatibility below).

## Commands

Python 3.11 venv at `.venv` (`pip install -r requirements.txt`; it includes `fake-bpy-module` for editor type hints). It's used for Blender 5.0 and all Unreal versions. Blender 5.1/5.2 run Python 3.13 and need a 3.13 venv at `.py3.13-venv` for `scripts/launch.py`.

```shell
# Launch Blender / Unreal with dev paths + optional debugpy (also exposed as VSCode build tasks, Ctrl+Shift+B)
python scripts/launch.py blender 5.2 no      # <app> <version> <debug yes|no>
python scripts/launch.py unreal 5.8 no
# Override exe locations via BLENDER_EXE_PATH / UNREAL_EXE_PATH in a repo-root .env (see .env.example)

# Tests — must be run from inside tests/
cd tests && python run_tests.py
# Single file / single test (comma-separated lists):
EXCLUSIVE_TEST_FILES=test_send2ue_cubes.py EXCLUSIVE_TESTS=test_default_send_to_unreal python run_tests.py
# Run against Docker containers instead of local apps (what CI does; needs GITHUB_TOKEN to pull ghcr.io/poly-hammer images):
DOCKER_ENVIRONMENT=yes BLENDER_VERSION=5.2 UNREAL_VERSION=5.8 python run_tests.py

# Docs (mkdocs, sources in docs/)
mkdocs serve
```

Lint config is `pycodestyle` in `tox.ini` (max line length 99).

Hot-reload addon code in a running Blender (Script Editor):
```python
import sys; sys.path.append(r'<repo>\scripts')
import dev_helpers; dev_helpers.reload_addon_source_code(['send2ue', 'ue2rigify'])
```

## Testing model

Tests are **integration tests that drive live apps over RPC**, not in-process unit tests. `tests/run_tests.py` uses `ContainerTestManager` to run unittest files on the host, which talk to Blender (port 9997, or 8997 in containers) and Unreal (9998/8998) through the `rpc` package in `src/addons/send2ue/dependencies/rpc`.

- Running locally: open Blender with the addons installed and start servers via `Pipeline > Utilities > Start RPC Servers`; open the Unreal test project (`tests/test_files/unreal_projects/test01`) with Python remote execution enabled.
- `tests/utils/blender.py` defines `BlenderRemoteCalls` — static methods decorated with `rpc.factory.remote_class` whose bodies execute *inside Blender*, not in the test process. Same pattern for Unreal in `send2ue/dependencies/unreal.py` (`UnrealRemoteCalls`). Code in these classes must be self-contained (imports resolved remotely).
- `tests/utils/base_test_case.py` holds the shared test logic: `BaseSend2ueTestCase` provides generic `run_*_tests` / `assert_*` helpers, and concrete test files (e.g. `test_send2ue_cubes.py`) set `self.file_name` to a `.blend` in `tests/test_files` and `@unittest.skip` inherited tests that don't apply.
- Results are written as xunit XML to `tests/results/`.
- CI (`.github/workflows/tests.yml`) runs the Docker path, but still targets the old Blender 3.6/UE 5.3 and 4.2/UE 5.4 pairs until 5.x images are published; verify locally for now.
- New features are expected to come with a test.

## Architecture

Both addons follow the same layout: `__init__.py` (bl_info + register/unregister and a `modules` list reloaded with `importlib.reload` when `SEND2UE_DEV` / `UE2RIGIFY_DEV` is set), `properties.py` (all property definitions), `operators.py` (entry points that call into `core/`), `core/` (logic), `ui/`, `constants.py`. When adding a new module to an addon, add it to that `modules` list so dev reloads pick it up.

### send2ue
- **Blender → Unreal transport**: `dependencies/remote_execution.py` (Unreal's UDP/TCP Python remote execution) is used to bootstrap an RPC server inside Unreal (`unreal.bootstrap_unreal_with_rpc_server`); subsequent calls go through `UnrealRemoteCalls` in `dependencies/unreal.py`. Anything that must run in Unreal lives there.
- **Pipeline**: `core/export.py` gathers assets, runs `core/validations.py`, exports FBX/ABC to a temp folder, and `core/ingest.py` imports them into Unreal. `export.py` exports FBX through `core/io/fbx_b4.py`, which monkeypatches Blender's bundled `io_scene_fbx` exporter.
- **Settings**: `resources/settings.json` is the schema from which scene property groups are generated (`core/settings.py`, `properties.py`); `resources/setting_templates/*.json` are user-loadable presets. Adding a user-facing setting usually means editing `settings.json`, not just `properties.py`.
- **Extensions**: `core/extension.py` defines `ExtensionBase` with lifecycle hooks (`pre_operation`, `pre_validations`, `pre_/post_mesh_export`, `pre_/post_import`, `filter_objects`, `update_asset_data`, `draw_*`, ...). Built-in extensions live in `resources/extensions/`; users can point at an external extensions repo. `ExtensionFactory` discovers classes via AST, turns their annotated properties into a property group under `scene.send2ue.extensions.<name>`, and registers their operators. Many optional features (affixes, combine_assets, instance_assets, use_collections_as_folders, ue2rigify integration) are implemented as extensions — prefer that route for new optional behavior.

### ue2rigify
- `core/templates.py` manages rig templates in `resources/rig_templates/b4_0/<template>/` (metarigs, node/link JSON). The `b4_0` folder name is kept for compatibility with user-saved templates. `core/nodes.py` builds the node editor for FK/source-to-deform mappings; `core/scene.py` switches between modes (source, metarig, FK/control) by building/constraining rigs.

## Blender version compatibility

- Blender 5.0+ only has the slotted Action API; `Action.fcurves` no longer exists. Use `get_action_fcurves`, `remove_action_fcurve`, `assign_action` and `assign_strip_action_slot` in each addon's `core/utilities.py` (the addons are independent, so each has its own copy; remote test code in `tests/utils/blender.py` has inlined versions).
- Blender 5.0 runs Python 3.11 and 5.1/5.2 run Python 3.13, so avoid relying on `exec()` + `locals()` (PEP 667) and `load_module()`. Python 3.13 also dedents `__doc__`, so never match docstrings against source text (the RPC factory strips them by AST position).
- `Bone.select` no longer exists in Blender 5.0+; use `PoseBone.select` (or `EditBone.select` in edit mode).
- Differences between 5.0 and 5.1+ exist in the vendored FBX exporter internals (e.g. shape-key tuples in `core/io/fbx_b4.py`); keep code tolerant of both.
- Unreal 5.6+ uses Interchange for FBX by default; send2ue needs the legacy importer (`Interchange.FeatureFlags.Import.FBX=False`).

## Releases

Each addon has a `release_notes.md` used as the GitHub release body and a version in `bl_info` in its `__init__.py`. Releases are cut by the manual `release.yml` workflow, which runs `scripts/create_release.py` to package and publish the zip(s). PRs target the `main` branch.
