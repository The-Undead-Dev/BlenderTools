# Upgrade send2ue + ue2rigify to Blender 5.2 / Unreal 5.8

## Context
Both addons were last maintained for Blender 3.6–5.0 and UE 5.3–5.4. Audits of the code against Blender 4.5/5.0/5.1/5.2 and UE 5.8.2 turned up hard breakages on the target versions:
- The legacy `Action.fcurves` API was removed in Blender 5.0, and about 15 call sites use it.
- The FBX exporter monkeypatch unpacks 4-tuples, but Blender 5.1 passes 5-tuples.
- A removed Alembic argument breaks groom export.
- In the RPC server, `exec()` + `locals()` fails under Python 3.13, which Blender 5.1/5.2 use. This breaks every remote call the tests make into Blender.

**Decisions:**
- The new supported range is **Blender 5.0 → 5.2** and **UE 5.6 → 5.8**. Code paths for older versions get deleted.
- Keep the legacy FBX importer. The `Interchange.FeatureFlags.Import.FBX` cvar still exists in 5.8 (`InterchangeFbxTranslator.cpp:36`).
- CI workflows stay untouched for now; verification is local.

Runtime Pythons: Blender 5.0 uses 3.11, Blender 5.1/5.2 use 3.13, and UE 5.8 uses 3.11.

## 1. Remove support for older versions
- **send2ue:**
  - Delete `src/addons/send2ue/core/io/fbx_b3.py`.
  - Collapse the major-version branch in `core/export.py:export_fbx_file` (line ~83) so it always calls `io.fbx_b4.export`.
  - Update `core/io/__init__.py` imports if they reference `fbx_b3`.
- **ue2rigify:**
  - Delete `resources/rig_templates/b3_6/`.
  - Remove the `b3_6` / `b4_0` selection in `constants.py:38`, `core/templates.py:25`, `core/utilities.py:1195` and `tests/utils/base_test_case.py:1480`. Keep the `b4_0` folder name to avoid churning template paths and user-saved templates.
  - Remove every `bpy.app.version[0] < 4` / `> 2` / `<= 2` branch in `core/scene.py` (1305, 1360, 1387, 1412, 1433, 1441) and `core/utilities.py` (453–492, bone groups/layers). Keep only the bone-collections path, and switch it to `data.collections_all` so nested collections are included.
- **send2ue `dependencies/unreal.py:1105` `is_using_legacy_fbx_importer`:**
  - Drop the fragile float parse of the version string (`"5.10"` parses as 5.1). On 5.6+, always read the cvar.
  - Treat an empty or unknown cvar value as "not legacy", but make the validation error in `core/validations.py:343` name the cvar and point to the docs.
- **`bl_info["blender"]`** becomes `(5, 0, 0)` in both `__init__.py` files.

## 2. Slotted Action API (Blender 5.0+)
- Add helpers to `send2ue/core/utilities.py` and duplicate them in `ue2rigify/core/utilities.py`, since the two addons are independent:
  - `get_action_fcurves(action, slot=None)`: with a slot, returns the fcurves from `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)`. With no slot, iterates every channelbag across `action.layers[*].strips[*].channelbags`.
  - `remove_action_fcurve(action, fcurve)`: removes the fcurve through its owning channelbag.
  - `assign_action(anim_data, action)`: sets `anim_data.action`. If `anim_data.action_slot` is still None, picks the first slot in `anim_data.action_suitable_slots`, or creates one with `action.slots.new('OBJECT', <id name>)`.
- Replace every `.fcurves` use:
  - send2ue: `core/utilities.py` 218, 907–909, 1461, 1571; `resources/extensions/instance_assets.py:163`.
  - ue2rigify: `core/scene.py` 140 (use `strip.action_slot`), 471–479, 1239–1240; `core/utilities.py` 120, 225.
  - tests: `tests/utils/blender.py:646`. It runs remotely, so the helper logic is inlined there.
- Wherever something is removed while iterating, iterate over a `list(...)` copy.
- Use `assign_action` wherever an action moves between rigs: `ue2rigify/core/scene.py:204–207`, `core/utilities.py:1062`, and `tests/utils/blender.py:413,417`. For the new empty actions from `scene.py:1106` that go into NLA strips (`scene.py:325,1109`, `utilities.py:655`), make sure `strip.action_slot` gets set after baking.

## 3. Other Blender 5.x API fixes
- **`core/io/fbx_b4.py`:**
  - Line 119: unpack the shape-key tuple as `(channel_key, geom_key, *_)` so it works with both the 4-item (5.0) and 5-item (5.1+) forms.
  - Line 173: import `ObjectWrapper` from `fbx_utils`. Today it raises a NameError on animated duplis.
  - Lines 20–26: replace `SourceFileLoader(...).load_module()` with `importlib.import_module('io_scene_fbx.export_fbx_bin')`, since `addons_core` is on `sys.path`. Keep the loader as a fallback if the import fails.
- **`core/export.py:116`:** drop `visible_objects_only=True`; the argument was removed in 5.0.
- **`core/extension.py:414` `remove_property_data`:** replace the dict-style `scene.get()` / `del`, which silently does nothing on 5.x, with `bpy.context.scene.send2ue.property_unset(Extensions.NAME)`, guarded by `hasattr`.
- **Positional override dicts:** change them to `with bpy.context.temp_override(**override):`. The call sites are `send2ue/core/utilities.py:1022` and `:1039` (`resize_object` has no callers, so delete it) and `ue2rigify/core/utilities.py:726`. The pattern to copy is at `ue2rigify/core/utilities.py:~709`.
- **`ue2rigify/core/utilities.py:913/1071`** saves and restores pose-bone custom properties through `bone.items()`. Real IDProperties such as IK_FK still work. The concern is RNA props like `rigify_type`, which are no longer included. Check that the mannequin tests still pass; add explicit RNA copying only if they don't.

## 4. RPC / Python 3.13
- `send2ue/dependencies/rpc/base_server.py:208` and `rpc/factory.py:43`: run `exec(code, namespace)` with an explicit dict and read the callable from `namespace`. This is the PEP 667 fix.
- `rpc/factory.py:117`: make the regex a raw string.
- `rpc/factory.py:126` generates code that uses `load_module()`. Switch it to `importlib.util.spec_from_file_location` + `exec_module`, the same pattern as `core/extension.py:287`. Do the same at `tests/utils/container_test_manager.py:43`.
- `dependencies/unreal.py:190` bootstrap: `thread.kill()` doesn't exist. Replace it with shutting down the existing server (`server.shutdown()`) or skipping if one is already running.

## 5. Unreal 5.8 API fixes
- `dependencies/unreal.py`:
  - Lines 636–641: `SkeletalMeshComponent.skeletal_mesh` becomes `get_skeletal_mesh_asset()`.
  - Line 972: `EditorLevelLibrary.get_editor_world()` becomes `get_editor_subsystem(UnrealEditorSubsystem).get_editor_world()`.
  - Line 495: add the missing f-string prefix.
  - Lines 1416–1417: load `lod_settings_path`, not `asset_path`.
- FBX import-data property names in `resources/settings.json` are applied by name (`unreal.py:348–361`), so any rename in 5.8 surfaces as an error in the tests. Fix those as they appear.

## 6. Tooling, tests and docs
- **`scripts/launch.py`:**
  - Blender 5.1/5.2 map to a new `.py3.13-venv`; 5.0 stays on `.venv` (3.11). Remove the 3.10 and 3.9 venvs.
  - All UE versions use `.venv`.
  - Fix the `app_version` global bug at line 120 so it uses `version`.
  - Update `validate_venv`'s version hint.
- **`.vscode/tasks.json`:** options become Blender 5.0/5.1/5.2 and UE 5.6/5.7/5.8, with defaults 5.2 and 5.8.
- **`tests/run_tests.py`:** defaults become `BLENDER_VERSION='5.2'` and `UNREAL_VERSION='5.8'`. Fix the missing comma after `'-noloadstartuppackages'`.
- **`tests/test_files/unreal_projects/test01`:**
  - `.uproject` `EngineAssociation` becomes `"5.8"`.
  - Add `[ConsoleVariables]` `Interchange.FeatureFlags.Import.FBX=False` to `Config/DefaultEngine.ini`.
- **`requirements.txt`:** bump the `fake-bpy-module` pin to a 5.x build and `debugpy` to a version that supports 3.13. Document creating `.py3.13-venv` in `docs/contributing/development.md`.
- **`CLAUDE.md`:** update the supported range, the venv notes and the version-branching section.
- **Docs:** state the supported range in `docs/send2ue/introduction/quickstart.md` and in the ue2rigify docs, and remove the 3.6→4.0 metarig FAQ.
- **Releases:**
  - Bump send2ue to 2.7.0 and ue2rigify to 1.8.0 in `bl_info`.
  - Rewrite both `release_notes.md` files for the new range, flagging the breaking minimum-version change.
- **CI (`.github/workflows/`):** left unchanged for now. The workflows still test 3.6/5.3 and 4.2/5.4, which are now unsupported. As a follow-up, move them to 5.x pairs once `blender-linux:5.x` / `unreal-linux:5.8` images are published to ghcr.io/poly-hammer.

## Verification
1. **Static checks:**
   - Run `pycodestyle src/addons` (`tox.ini`).
   - Run `grep -rn "\.fcurves\b\|bpy.app.version\|load_module\|visible_objects_only" src tests`; it should find only the intended uses.
2. **Blender smoke test, per version (5.0, 5.1, 5.2):**
   - `blender --background --factory-startup --python-expr` with the addon path appended.
   - Enable `send2ue` + `ue2rigify` (and `rigify`) and confirm they register without errors.
3. **Live integration tests** (see CLAUDE.md "Testing model"):
   - Set `UNREAL_EXE_PATH` to the UE 5.8 `UnrealEditor.exe` in `.env`.
   - `python scripts/launch.py unreal 5.8 no` (the project upgrades to 5.8 on first open).
   - `python scripts/launch.py blender 5.2 no`, then Pipeline > Utilities > Start RPC Servers.
   - `cd tests && python run_tests.py`. Priority order: `test_send2ue_cubes.py`, `test_send2ue_mannequins.py` (animation, fcurves, shape keys), `test_ue2rigify_mannequins.py` (baking, slots), then the extension tests.
   - Repeat the Blender side on 5.0 to cover the lower bound (4-tuple shape keys, Python 3.11).
4. **Manual check in Blender 5.2:** send the mannequin with an animation to UE 5.8 through the UI, and confirm the mesh, skeleton, animation and custom-property curves arrive correctly.
