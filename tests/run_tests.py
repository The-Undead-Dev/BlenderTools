# Copyright Epic Games, Inc. All Rights Reserved.

import os
import sys
import logging
DEBUGGING_ON = os.environ.get('DEBUGGING_ON', 'no').lower() == 'yes'
DOCKER_ENVIRONMENT = os.environ.get('DOCKER_ENVIRONMENT', 'no').lower() == 'yes'
if DOCKER_ENVIRONMENT:
    os.environ['TEST_ENVIRONMENT'] = '1'

# adds the rpc module to the path
sys.path.append(os.path.join(os.path.dirname(__file__), os.path.pardir, 'src', 'addons', 'send2ue', 'dependencies'))

from utils.container_test_manager import ContainerTestManager

BLENDER_ADDONS = os.environ.get('BLENDER_ADDONS', 'send2ue,ue2rigify')

BLENDER_VERSION = os.environ.get('BLENDER_VERSION', '5.2')
UNREAL_VERSION = os.environ.get('UNREAL_VERSION', '5.8')

# switch ports depending on whether in test environment or not
BLENDER_PORT = os.environ.get('BLENDER_PORT', '9997')
UNREAL_PORT = os.environ.get('UNREAL_PORT', '9998')
BLENDER_CONTAINER_DEBUG_PORT = os.environ.get('BLENDER_DEBUG_PORT', '5668')
UNREAL_CONTAINER_DEBUG_PORT = os.environ.get('UNREAL_DEBUG_PORT', '5669')
if os.environ.get('TEST_ENVIRONMENT'):
    BLENDER_PORT = os.environ.get('BLENDER_PORT', '8997')
    UNREAL_PORT = os.environ.get('UNREAL_PORT', '8998')

TEST_ENVIRONMENT = os.environ.get('TEST_ENVIRONMENT')
HOST_REPO_FOLDER = os.environ.get('HOST_REPO_FOLDER', os.path.normpath(os.path.join(os.getcwd(), os.pardir)))
CONTAINER_REPO_FOLDER = os.environ.get('CONTAINER_REPO_FOLDER', '/tmp/blender_tools/')
HOST_TEST_FOLDER = os.environ.get('HOST_TEST_FOLDER', os.getcwd())
CONTAINER_TEST_FOLDER = os.environ.get('CONTAINER_TEST_FOLDER', f'{CONTAINER_REPO_FOLDER}tests')
ALWAYS_PULL = bool(int(os.environ.get('ALWAYS_PULL', '0')))
EXCLUSIVE_TEST_FILES = list(filter(None, os.environ.get('EXCLUSIVE_TEST_FILES', '').split(','))) or None
if EXCLUSIVE_TEST_FILES == ['all']:
    EXCLUSIVE_TEST_FILES = []
EXCLUSIVE_TESTS = list(filter(None, os.environ.get('EXCLUSIVE_TESTS', '').split(','))) or None
if EXCLUSIVE_TESTS == ['all']:
    EXCLUSIVE_TESTS = []


if __name__ == '__main__':
    # define additional environment variables
    environment = {
        'SEND2UE_DEV': '1',
        'UE2RIGIFY_DEV': '1',
        'BLENDER_DEBUG_PORT': BLENDER_CONTAINER_DEBUG_PORT,
        'UNREAL_DEBUG_PORT': UNREAL_CONTAINER_DEBUG_PORT,
        'BLENDER_ADDONS': BLENDER_ADDONS,
        'BLENDER_PORT': BLENDER_PORT,
        'BLENDER_VERSION': BLENDER_VERSION,
        'UNREAL_VERSION': UNREAL_VERSION,
        'UNREAL_PORT': UNREAL_PORT,
        'HOST_REPO_FOLDER': HOST_REPO_FOLDER,
        'CONTAINER_REPO_FOLDER': CONTAINER_REPO_FOLDER,
        'HOST_TEST_FOLDER': HOST_TEST_FOLDER,
        'CONTAINER_TEST_FOLDER': CONTAINER_TEST_FOLDER,
        'RPC_TRACEBACK_FILE': '/tmp/blender/send2ue/data/traceback.log',
        'RPC_TIME_OUT': '120'
    }
    # make sure this is set in the current environment
    os.environ.update(environment)

    # add the test environment variable if specified
    if DOCKER_ENVIRONMENT:
        os.environ['RPC_TRACEBACK_FILE'] = os.path.join(HOST_TEST_FOLDER, 'data', 'traceback.log')
        environment['TEST_ENVIRONMENT'] = '1'
        if DEBUGGING_ON:
            environment['BLENDER_DEBUGGING_ON'] = 'yes'
            environment['UNREAL_DEBUGGING_ON'] = 'yes'
            environment['BLENDER_DEBUG_PORT'] = BLENDER_CONTAINER_DEBUG_PORT
            environment['UNREAL_DEBUG_PORT'] = UNREAL_CONTAINER_DEBUG_PORT

    # define the additional volume paths
    # this is the temp data location where send2ue export/imports data
    host_temp_folder = os.path.join(HOST_TEST_FOLDER, 'data')
    volumes = [
        f'{HOST_REPO_FOLDER}:{CONTAINER_REPO_FOLDER}'
    ]
    shared_volumes = {
        'send2ue-export-data': '/tmp/blender/send2ue/data',
    }

    logging.debug('Launching ContainerTestManager...')
    # instance the container test manager with the blender and unreal containers
    container_test_manager = ContainerTestManager(
        images={
            'blender': {
                'connects_to': 'unreal',
                'refresh': True,
                'always_pull': ALWAYS_PULL,
                'tag': f'blender-linux:{BLENDER_VERSION}',
                'repository': 'ghcr.io/poly-hammer',
                'user': 'root',
                'rpc_port': BLENDER_PORT,
                'debug_port': BLENDER_CONTAINER_DEBUG_PORT,
                'environment': environment,
                'volumes': volumes,
                'command': [
                    'blender',
                    '--background',
                    '--disable-autoexec',
                    '--python-exit-code',
                    '1',
                    '--python',
                    '/tmp/blender_tools/scripts/resources/blender/startup.py',
                ],
                'auth_config': {
                    'username': os.environ.get('GITHUB_USERNAME'),
                    'password': os.environ.get('GITHUB_TOKEN')
                }
            },
            'unreal': {
                'refresh': False,
                'always_pull': ALWAYS_PULL,
                'rpc_port': UNREAL_PORT,
                'debug_port': UNREAL_CONTAINER_DEBUG_PORT,
                'environment': environment,
                'volumes': volumes,
                'tag': f'unreal-linux:{UNREAL_VERSION}',
                'repository': 'ghcr.io/poly-hammer',
                'user': 'ue4',
                'command': [
                    '/home/ue4/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd',
                    '/tmp/blender_tools/tests/test_files/unreal_projects/test01/test01.uproject',
                    '-stdout',
                    '-unattended',
                    '-nopause',
                    '-nullrhi',
                    '-nosplash',
                    '-noloadstartuppackages',
                    '-log',
                    '-ExecutePythonScript=/tmp/blender_tools/scripts/resources/unreal/init_unreal.py',
                ],
                'auth_config': {
                    'username': os.environ.get('GITHUB_USERNAME'),
                    'password': os.environ.get('GITHUB_TOKEN')
                }
            }
        },
        shared_volumes=shared_volumes,
        test_case_folder=HOST_TEST_FOLDER,
        additional_python_paths=[HOST_REPO_FOLDER, CONTAINER_REPO_FOLDER],
        prefix_service_logs=True,
        exclusive_test_files=EXCLUSIVE_TEST_FILES,
        exclusive_tests=EXCLUSIVE_TESTS,
    )
    if TEST_ENVIRONMENT:
        # remove existing containers first
        if os.environ.get('REMOVE_CONTAINERS', '').lower() != 'false':
            container_test_manager.stop()

        container_test_manager.start()

    container_test_manager.run_test_cases()

    if TEST_ENVIRONMENT and os.environ.get('REMOVE_CONTAINERS', '').lower() != 'false':
        container_test_manager.stop()
