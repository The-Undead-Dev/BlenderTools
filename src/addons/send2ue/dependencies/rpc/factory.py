import os
import re
import ast
import sys
import logging
import types
import inspect
import textwrap
import unittest
from typing import Any, Iterator, Optional, Union, List, Tuple, Callable
from xmlrpc.client import Fault

from .client import RPCClient
from .validations import (
    validate_key_word_parameters,
    validate_class_method,
    get_source_file_path,
    get_line_link,
    validate_arguments,
    validate_file_is_saved,
)

logger = logging.getLogger(__package__)


class RPCFactory:
    def __init__(self, rpc_client, remap_pairs=None, default_imports=None):
        self.rpc_client = rpc_client
        self.file_path = None
        self.remap_pairs = remap_pairs
        self.default_imports = default_imports or []

    @staticmethod
    def _remove_docstring(code):
        """
        Removes the docstring lines from the function code. The lines are found by their position in the parsed code,
        since python 3.13+ dedents __doc__, so it no longer matches the source text.

        :param list code: A list of code lines.
        :returns: The code lines without the docstring.
        :rtype: list
        """
        function_node = ast.parse('\n'.join(code)).body[0]
        first_statement = function_node.body[0]
        is_docstring = (
            isinstance(first_statement, ast.Expr) and
            isinstance(first_statement.value, ast.Constant) and
            isinstance(first_statement.value.value, str)
        )
        # keep the docstring if it is the only statement, so the function body is not empty
        if is_docstring and len(function_node.body) > 1:
            del code[first_statement.lineno - 1:first_statement.end_lineno]
        return code

    @staticmethod
    def _save_execution_history(code, function, args):
        """
        Saves out the executed code to a file.

        :param list code: A list of code lines.
        :param callable function: A function.
        :param list args: A list of function arguments.
        """
        history_file_path = os.environ.get('RPC_EXECUTION_HISTORY_FILE')

        if history_file_path and os.path.exists(os.path.dirname(history_file_path)):
            file_size = 0
            if os.path.exists(history_file_path):
                file_size = os.path.getsize(history_file_path)

            with open(history_file_path, 'a') as history_file:
                # add the imports used by the module loading code if the file is empty
                if file_size == 0:
                    history_file.write('import sys\nimport importlib.util\n')

                # space out the functions
                history_file.write(f'\n\n')

                for line in code:
                    history_file.write(f'{line}\n')

                # convert the args to strings
                formatted_args = []
                for arg in args:
                    if isinstance(arg, str):
                        formatted_args.append(f'r"{arg}"')
                    else:
                        formatted_args.append(str(arg))

                # write the call with the arg values
                params = ", ".join(formatted_args) if formatted_args else ''
                history_file.write(f'{function.__name__}({params})\n')

    def _get_callstack_references(self, code, function):
        """
        Gets all references for the given code.

        :param list[str] code: The code of the callable.
        :param callable function: A callable.
        :return str: The new code of the callable with all its references added.
        """
        import_code = self.default_imports

        client_module = inspect.getmodule(function)
        self.file_path = get_source_file_path(function)

        # if a list of remap pairs have been set, the file path will be remapped to the new server location
        # Note: The is useful when the server and client are not on the same machine.
        server_module_path = self.file_path
        for client_path_root, matching_server_path_root in self.remap_pairs or []:
            if self.file_path.startswith(client_path_root):
                server_module_path = os.path.join(
                    matching_server_path_root,
                    self.file_path.replace(client_path_root, '').replace(os.sep, '/').strip('/')
                )
                break

        for key in dir(client_module):
            for line_number, line in enumerate(code):
                if line.startswith('def '):
                    continue

                if key in re.split(r'\.|\(| ', line.strip()):
                    if os.path.basename(self.file_path) == '__init__.py':
                        base_name = os.path.basename(os.path.dirname(self.file_path))
                    else:
                        base_name = os.path.basename(self.file_path)

                    module_name, file_extension = os.path.splitext(base_name)

                    # add the source file to the import code. Like the removed load_module(), an existing module
                    # of the same name is executed into rather than replaced, e.g. unreal.py extends the builtin
                    # unreal module on the unreal server.
                    spec_code = (
                        f'{module_name}_spec = importlib.util.spec_from_file_location('
                        f'"{module_name}", r"{server_module_path}")'
                    )
                    if spec_code not in import_code:
                        import_code.extend([
                            'import sys',
                            'import importlib.util',
                            spec_code,
                            f'{module_name} = sys.modules.get("{module_name}") or '
                            f'importlib.util.module_from_spec({module_name}_spec)',
                            f'sys.modules["{module_name}"] = {module_name}',
                            f'{module_name}_spec.loader.exec_module({module_name})'
                        ])

                    # relatively import the module from the source file
                    relative_import_code = f'from {module_name} import {key}'
                    if relative_import_code not in import_code:
                        import_code.append(relative_import_code)

                    break

        return textwrap.indent('\n'.join(import_code), ' ' * 4)

    def _get_code(self, function):
        """
        Gets the code from a callable.

        :param callable function: A callable.
        :return str: The code of the callable.
        """
        code = textwrap.dedent(inspect.getsource(function)).split('\n')
        code = [line for line in code if not line.startswith(('@', '#'))]

        # remove the doc string
        code = self._remove_docstring(code)

        # get import code and insert them inside the function
        import_code = self._get_callstack_references(code, function)
        code.insert(1, import_code)

        return code

    def _register(self, function):
        """
        Registers a given callable with the server.

        :param  callable function: A callable.
        :return: The code of the function.
        :rtype: list
        """
        code = self._get_code(function)
        try:
            # if additional paths are explicitly set, then use them. This is useful with the client is on another
            # machine and the python paths are different
            additional_paths = list(filter(None, os.environ.get('RPC_ADDITIONAL_PYTHON_PATHS', '').split(',')))

            if not additional_paths:
                # otherwise use the current system path
                additional_paths = sys.path

            response = self.rpc_client.proxy.add_new_callable(
                function.__name__, '\n'.join(code),
                additional_paths
            )
            if os.environ.get('RPC_DEBUG'):
                logger.debug(response)

        except ConnectionRefusedError:
            server_name = os.environ.get(f'RPC_SERVER_{self.rpc_client.port}', self.rpc_client.port)
            raise ConnectionRefusedError(f'No connection could be made with "{server_name}"')

        return code

    def run_function_remotely(self, function, args):
        """
        Handles running the given function on remotely.

        :param callable function: A function reference.
        :param tuple(Any) args: The function's arguments.
        :return callable: A remote callable.
        """
        validate_arguments(function, args)

        # get the remote function instance
        code = self._register(function)
        remote_function = getattr(self.rpc_client.proxy, function.__name__)
        self._save_execution_history(code, function, args)

        current_frame = inspect.currentframe()
        outer_frame_info = inspect.getouterframes(current_frame)
        # step back 2 frames in the callstack
        caller_frame = outer_frame_info[2][0]
        # create a trace back that is relevant to the remote code rather than the code transporting it
        call_traceback = types.TracebackType(None, caller_frame, caller_frame.f_lasti, caller_frame.f_lineno)
        # call the remote function
        if not self.rpc_client.marshall_exceptions:
            # if exceptions are not marshalled then receive the default Fault
            return remote_function(*args)

        # otherwise catch them and add a line link to them
        try:
            return remote_function(*args)
        except Exception as exception:
            stack_trace = str(exception) + get_line_link(function)
            if isinstance(exception, Fault):
                raise Fault(exception.faultCode, exception.faultString)
            raise exception.__class__(stack_trace).with_traceback(call_traceback)


def remote_call(port, default_imports=None, remap_pairs=None):
    """
    A decorator that makes this function run remotely.

    :param Enum port: The name of the port application i.e. maya, blender, unreal.
    :param list[str] default_imports: A list of import commands that include modules in every call.
    :param list(tuple) remap_pairs: A list of tuples with first value being the client file path root and the
    second being the matching server path root. This can be useful if the client and server are on two different file
    systems and the root of the import paths need to be dynamically replaced.
    """
    def decorator(function):
        def wrapper(*args, **kwargs):
            validate_file_is_saved(function)
            validate_key_word_parameters(function, kwargs)
            rpc_factory = RPCFactory(
                rpc_client=RPCClient(port),
                remap_pairs=remap_pairs,
                default_imports=default_imports
            )
            return rpc_factory.run_function_remotely(function, args)
        return wrapper
    return decorator


def remote_class(decorator):
    """
    A decorator that makes this class run remotely.

    :param remote_call decorator: The remote call decorator.
    :return: A decorated class.
    """
    def decorate(cls):
        for attribute, value in cls.__dict__.items():
            validate_class_method(cls, value)
            if callable(getattr(cls, attribute)):
                setattr(cls, attribute, decorator(getattr(cls, attribute)))
        return cls
    return decorate

def execute_remotely(
        port: int,
        function: Callable, 
        args: Optional[Union[List, Tuple]] = None,
        kwargs: Optional[dict] = None,
        remap_pairs: Optional[List[Tuple[str, str]]] = None,
        default_imports: Optional[List[str]] = None,
    ):
    """
    Executes the given function remotely.
    """
    if not args:
        args = []

    validate_file_is_saved(function)
    validate_key_word_parameters(function, kwargs)
    rpc_factory = RPCFactory(
        rpc_client=RPCClient(port),
        remap_pairs=remap_pairs,
        default_imports=default_imports
    )
    return rpc_factory.run_function_remotely(function, args)

def _make_remote(
        port: int, 
        remap_pairs: Optional[List[Tuple[str, str]]] = None, 
        default_imports: Optional[List[str]] = None
    ):
    def decorator(function):
        def wrapper(*args, **kwargs):
            validate_key_word_parameters(function, kwargs)
            return execute_remotely(
                function=function,
                args=args,
                kwargs=kwargs,
                port=port,
                remap_pairs=remap_pairs,
                default_imports=default_imports
            )

        return wrapper

    return decorator


def get_all_parent_classes(cls) -> Iterator[Any]:
    """
    Gets all parent classes recursively upward from the given class.
    """
    for _cls in cls.__bases__:
        if object not in _cls.__bases__ and len(_cls.__bases__) >= 1:
            yield from get_all_parent_classes(_cls)
        yield _cls

def make_remote(
        reference: Any, 
        port: Optional[int] = None,
        default_imports: Optional[List[str]] = None,
    ) -> Callable:
    """
    Makes the given class or function run remotely when invoked.
    """
    if not default_imports:
        default_imports = ['import unreal']
    remap_pairs = []
    unreal_port = int(os.environ.get('UNREAL_PORT', 9998))

    # use a different remap pairs when inside a container
    if os.environ.get('TEST_ENVIRONMENT'):
        unreal_port = int(os.environ.get('UNREAL_PORT', 8998))
        remap_pairs = [(os.environ.get('HOST_REPO_FOLDER', ''), os.environ.get('CONTAINER_REPO_FOLDER', ''))]

    if not port:
        port = unreal_port

    # if this is not a class then decorate it
    if not inspect.isclass(reference):
        return _make_remote(
            port=port,
            remap_pairs=remap_pairs,
            default_imports=default_imports
        )(reference)

    # if this is a class then decorate all its methods
    methods = {}
    for _cls in [*get_all_parent_classes(reference), reference]:
        for attribute, value in _cls.__dict__.items():
            # dont look at magic methods
            if not attribute.startswith('__'):
                validate_class_method(_cls, value)
                # note that we use getattr instead of passing the value directly.
                methods[attribute] = _make_remote(
                    port=port,
                    remap_pairs=remap_pairs,
                    default_imports=default_imports
                )(getattr(_cls, attribute))

    # return a new class with the decorated methods all in the same class
    return type(
        reference.__name__,
        (object,),
        methods
    )


class RPCTestCase(unittest.TestCase):
    """
    Subclasses unittest.TestCase to implement a RPC compatible TestCase.
    """
    port = None
    remap_pairs = None
    default_imports = None

    @classmethod
    def run_remotely(cls, method, args):
        """
        Run the given method remotely.

        :param callable method: A method to wrap.
        """
        default_imports = cls.__dict__.get('default_imports', None)
        port = cls.__dict__.get('port', None)
        remap_pairs = cls.__dict__.get('remap_pairs', None)
        rpc_factory = RPCFactory(
            rpc_client=RPCClient(port),
            default_imports=default_imports,
            remap_pairs=remap_pairs
        )
        return rpc_factory.run_function_remotely(method, args)

    def _callSetUp(self):
        """
        Overrides the TestCase._callSetUp method by passing it to be run remotely.
        Notice None is passed as an argument instead of self. This is because only static methods
        are allowed by the RPCClient.
        """
        self.run_remotely(self.setUp, [None])

    def _callTearDown(self):
        """
        Overrides the TestCase._callTearDown method by passing it to be run remotely.
        Notice None is passed as an argument instead of self. This is because only static methods
        are allowed by the RPCClient.
        """
        # notice None is passed as an argument instead of self so self can't be used
        self.run_remotely(self.tearDown, [None])

    def _callTestMethod(self, method):
        """
        Overrides the TestCase._callTestMethod method by capturing the test case method that would be run and then
        passing it to be run remotely. Notice no arguments are passed. This is because only static methods
        are allowed by the RPCClient.

        :param callable method: A method from the test case.
        """
        self.run_remotely(method, [])
