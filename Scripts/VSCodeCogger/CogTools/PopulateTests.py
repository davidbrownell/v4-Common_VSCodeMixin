# ----------------------------------------------------------------------
# |
# |  PopulateTests.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2022-10-21 10:46:18
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2022
# |  Distributed under the Boost Software License, Version 1.0. See
# |  accompanying file LICENSE_1_0.txt or copy at
# |  http://www.boost.org/LICENSE_1_0.txt.
# |
# ----------------------------------------------------------------------
"""Searches for and creates debug profiles for all tests found"""

import os
import sys
import textwrap

from pathlib import Path
from typing import Dict, List

import cog                                  # type: ignore  # pylint: disable=import-error

from Common_Foundation.ContextlibEx import ExitStack
from Common_Foundation.EnumSource import EnumSource
from Common_Foundation import PathEx
from Common_Foundation import Types


# ----------------------------------------------------------------------
_CONFIGURATIONS: Dict[
    str,                                    # TestParser name
    str,                                    # VSCode template
] =                                         {
    # ----------------------------------------------------------------------
    "Pytest": textwrap.dedent(
        """\
        {{
            // {filename}
            "name": "{name}",

            "presentation": {{
                "hidden": false,
                "group": "{group}",
            }},

            "type": "python",
            "request": "launch",
            "justMyCode": false,
            "console": "integratedTerminal",

            "module": "pytest",

            "args": [
                "-o",
                "python_files=*Test.py",
                "-vv",
                "{basename}",

                "--capture=no",  // Do not capture stderr/stdout

                // To run a test method within a class, use the following expression
                // with the `-k` argument that follows:
                //
                //      <class_name> AND <test_name> [AND NOT <other_test_name>]
                //

                // "-k", "test_name or expression",

                // Insert custom program args here
            ],

            "cwd": "{dirname}"
        }},
        """,
    ),

    # ----------------------------------------------------------------------
    "PythonUnittest": textwrap.dedent(
        """\
        {{
            // {filename}
            "name": "{name}",

            "presentation": {{
                "hidden": false,
                "group": "{{group}}",
            }},

            "type": "python",
            "request": "launch",
            "justMyCode": false,
            "console": "integratedTerminal",

            "program": "{filename}",

            "args": [
                // Insert custom program args here
            ],

            "cwd": "{dirname}"
        }},
        """,
    ),
}


# ----------------------------------------------------------------------
sys.path.insert(0, str(PathEx.EnsureDir(Path(Types.EnsureValid(os.getenv("DEVELOPMENT_ENVIRONMENT_FOUNDATION"))))))
with ExitStack(lambda: sys.path.pop(0)):
    from RepositoryBootstrap.SetupAndActivate import DynamicPluginArchitecture  # type: ignore  # pylint: disable=import-error


# ----------------------------------------------------------------------
def Execute() -> None:
    source_dir = Path(cog.inFile).parent.parent
    len_source_dir_parts = len(source_dir.parts)

    # Get all of the tests
    test_filenames: List[Path] = []

    for root, _, filenames in EnumSource(source_dir):
        if not (root.name.endswith("Tests") and root.name != "Tests"):
            continue

        for filename in filenames:
            if filename == "__init__.py":
                continue

            ext = os.path.splitext(filename)[1]

            if ext != ".py":
                continue

            test_filenames.append(root / filename)

    # Group the tests
    if not test_filenames:
        return

    groups: Dict[str, List[Path]] = {}
    test_names_lookup: Dict[str, int] = {}

    for test_filename in test_filenames:
        test_name = test_filename.name

        if test_name in test_names_lookup:
            test_names_lookup[test_name] += 1
        else:
            test_names_lookup[test_name] = 1

        group_name = Path(*test_filename.parts[len_source_dir_parts:]).parent.as_posix()

        groups.setdefault(group_name, []).append(test_filename)

    # Load the test parsers
    test_parsers = [
        mod.TestParser()
        for mod in DynamicPluginArchitecture.EnumeratePlugins("DEVELOPMENT_ENVIRONMENT_TEST_PARSERS")
    ]

    # ----------------------------------------------------------------------
    def Print(
        value: str,
    ) -> None:
        cog.outl(value)

    # ----------------------------------------------------------------------

    Print(
        textwrap.dedent(
            """\
            //
            // This content can be updated by running 'VSCodeCogger' from the command line.
            //
            """,
        ).rstrip(),
    )

    for group_name, filenames in groups.items():
        Print(
            textwrap.dedent(
                """
                // ----------------------------------------------------------------------
                // |
                // |  {}
                // |
                // ----------------------------------------------------------------------
                """,
            ).format(group_name).rstrip(),
        )

        for filename in filenames:
            for test_parser in test_parsers:
                if test_parser.IsSupportedTestItem(filename):
                    Print(
                        _CONFIGURATIONS[test_parser.name].format(
                            filename=filename.as_posix(),
                            dirname=filename.parent.as_posix(),
                            basename=filename.name,
                            group=group_name,
                            name="{}{}".format(
                                filename.stem,
                                "" if test_names_lookup[filename.name] == 1 else " --- {}".format(group_name),
                            ),
                        ).rstrip(),
                    )

                    break

    Print("")


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if os.environ.get("__extracting_documentation__", None) is None:
    Execute()
