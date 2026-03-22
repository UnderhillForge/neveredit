"""Legacy setup entry point.

Wheel-focused package metadata now lives in ``setup.cfg`` and ``pyproject.toml``.
This file only retains the historical ``py2app`` application bundle flow.
"""

import os
import os.path
import shutil
import sys

from setuptools import setup


def _read_version():
    namespace = {}
    init_path = os.path.join(os.path.dirname(__file__), '__init__.py')
    with open(init_path, 'r', encoding='utf-8') as handle:
        exec(handle.read(), namespace)
    return namespace['__version__']


def _is_py2app_invocation(argv):
    return 'py2app' in argv


def main():
    if not _is_py2app_invocation(sys.argv):
        setup()
        return

    try:
        import py2app  # noqa: F401
    except ImportError as exc:
        raise SystemExit('py2app is required for macOS app bundle builds') from exc

    version = _read_version()
    name = 'neveredit'
    if 'neveredit' in sys.argv:
        sys.argv.remove('neveredit')
    elif 'neverscript' in sys.argv:
        name = 'neverscript'
        sys.argv.remove('neverscript')

    resources = ['neveredit.jpg', 'help_nwnlexicon.zip']
    if name == 'neveredit':
        mainclass = 'ui/NeverEditMainApp.py'
        resources.append('neveredit.icns')
    else:
        mainclass = 'ui/ScriptEditor.py'
        resources.append('neverscript.icns')

    setup(
        app=[mainclass],
        name=name,
        version=version,
        options={
            'py2app': {
                'argv_emulation': True,
                'compressed': True,
                'strip': True,
                'semi_standalone': False,
                'includes': ['numpy'],
                'resources': resources,
                'plist': {
                    'CFBundleIconFile': name + '.icns',
                    'CFBundleName': name,
                    'CFBundleVersion': version,
                    'NSHumanReadableCopyright': 'Copyright 2005, Peter Gorniak',
                },
            }
        },
    )

    to_remove = [
        ('OpenGL', 'doc'),
        ('OpenGL', 'Demo'),
        ('OpenGL', 'Tk'),
        ('GLU', 'EXT'),
        ('GLU', 'SGI'),
    ]

    app_path = os.path.join('dist', name + '.app')
    for path, dirs, files in os.walk(app_path):
        for filename in files:
            for parent_name, target_name in to_remove:
                if ((os.path.split(path)[-1] == parent_name and filename == target_name) or
                        filename.endswith('.cached')):
                    print('removing', os.path.join(path, filename))
                    os.remove(os.path.join(path, filename))
                    break
        for dirname in dirs:
            for parent_name, target_name in to_remove:
                if ((os.path.split(path)[-1] == parent_name and dirname == target_name) or
                        os.path.split(path)[-1] == 'GL'):
                    print('removing', os.path.join(path, dirname))
                    shutil.rmtree(os.path.join(path, dirname))
                    break


if __name__ == '__main__':
    main()
