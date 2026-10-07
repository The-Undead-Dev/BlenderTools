import os
import sys
import bpy
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)

REPO_ROOT = Path(__file__).parent.parent.parent.parent
debug = os.environ.get('BLENDER_DEBUGGING_ON', 'no').lower() == 'yes'

ADDONS = {
    'send2ue': REPO_ROOT / 'src',
    'ue2rigify': REPO_ROOT / 'src'
}


if bpy.app.version[0] > 2: # type: ignore
    current_script_directories = [
        Path(i.directory)
        for i in bpy.context.preferences.filepaths.script_directories.values()
    ]


    for name, scripts_folder in ADDONS.items():
        if scripts_folder not in current_script_directories:
            script_directory = bpy.context.preferences.filepaths.script_directories.new()
            script_directory.name = name # type: ignore
            script_directory.directory = str(scripts_folder) # type: ignore
        # put the repo addons first so they take precedence over any installed copy in the user addons folder
        addons_folder = os.path.join(str(scripts_folder), 'addons')
        if addons_folder in sys.path:
            sys.path.remove(addons_folder)
        sys.path.insert(0, addons_folder)

    try:
        bpy.ops.script.reload()
    except ValueError:
        pass


for addon in ADDONS.keys():
    try:
        bpy.ops.preferences.addon_enable(module=addon)
    except Exception as e:
        logger.warning(f'Failed to enable addon {addon}: {e}')

if debug:
    try:
        import debugpy
        port = int(os.environ.get('BLENDER_DEBUG_PORT', 5678))
        debugpy.configure(python=os.environ.get('BLENDER_PYTHON_EXE', sys.executable))
        if os.environ.get('TEST_ENVIRONMENT'):
            debugpy.listen(('0.0.0.0', port))
        else:
            debugpy.listen(port)
        logger.info(f'Waiting for debugger to attach on port {port}...')
        debugpy.wait_for_client()
    except ImportError:
        logger.error(
            'Failed to initialize debugger because debugpy is not available '
            'in the current python environment.'
        )


if os.environ.get('TEST_ENVIRONMENT'):
    from send2ue.dependencies.rpc.server import RPCServer
    rpc_server = RPCServer()
    rpc_server.start_server_blocking()
else:
    from send2ue.dependencies.rpc import blender_server
    rpc_server = blender_server.RPCServer()
    rpc_server.start(threaded=True)

print('Blender RPC Server started')