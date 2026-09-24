## Breaking Changes
* The minimum supported version is now Blender `5.0`. Support for Blender 3.6–4.x has been removed, including the
  Blender 3.6 rig templates and bone group code. Use UE to Rigify `1.7.x` for those versions.

## Minor Changes
* Added support for Blender `5.1` and `5.2` (Python 3.13)
* Migrated animation baking and NLA code to the slotted Action API (the legacy `Action.fcurves` API was removed in
  Blender 5.0)
* Bone collection visibility now includes nested bone collections

## Bug Fixes
* Fixed bone selection on Blender 5.x (`Bone.select` was removed in favor of `PoseBone.select`)
* Fixed a crash in Blender 5.2 when the addon is re-enabled or scripts are reloaded, caused by re-registering stale
  node tree classes

## Supported Versions
* Blender `5.0`, `5.1`, `5.2`

## Tests Passing On
* Blender `5.2`, `5.0` (installed from blender.org)
* Unreal `5.8`
