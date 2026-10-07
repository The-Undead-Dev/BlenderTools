## Breaking Changes
* The minimum supported versions are now Blender `5.0` and Unreal `5.6`. Support for Blender 3.6–4.x and Unreal
  5.3–5.5 has been removed. Use Send to Unreal `2.6.x` for those versions.
* Send to Unreal requires the Legacy FBX Importer. Set `Interchange.FeatureFlags.Import.FBX=False` under
  `[ConsoleVariables]` in the project's `Config/DefaultEngine.ini`.

## Minor Changes
* Added support for Blender `5.1` and `5.2` (Python 3.13) and Unreal `5.7` and `5.8`
* Migrated animation code to the slotted Action API (the legacy `Action.fcurves` API was removed in Blender 5.0)

## Bug Fixes
* Fixed shape key animation export on Blender 5.1+
* Fixed a NameError when exporting animated dupli instances
* Fixed groom (Alembic) export on Blender 5.x
* Fixed extension property data not being removed on Blender 5.x
* Fixed RPC remote calls failing under Python 3.13 (callable registration and multi-line docstring stripping)
* Fixed the Unreal RPC server bootstrap when a stale server thread exists
* Fixed skeletal mesh LOD settings loading the mesh asset instead of the LOD settings asset
* Fixed removing skeletal mesh LODs on Unreal 5.8 (`SkeletalMesh.remove_lo_ds` was removed)
* Fixed the legacy FBX importer check misreading engine versions like `5.10`, and made its validation error name the
  required console variable

## Supported Versions
* Blender `5.0`, `5.1`, `5.2`
* Unreal `5.6`, `5.7`, `5.8`

## Tests Passing On
* Blender `5.2`, `5.0` (installed from blender.org)
* Unreal `5.8`
